"""Pharmacovigilance / MICC API — intake, dashboard, E2B export, print view.

spec-micc-pv-module.md (approved): a call-centre agent captures what a caller
REPORTED about a medicine. This router records that verbatim and nothing more —
no causal assessment, no clinical conclusion, no advice. Every rule (contact
classification, the ICH E2B minimum, the ICH E2A flags, the India 15/90-day
clock, the complaint state machine, the E2B export, the print sheet) lives in
app/services/pharmacovigilance.py, which is stdlib-only and headless-testable.
This module stays thin, exactly like the payments and voice routers.

Enforcement mirrors the house pattern:
- POST /cases is the ONE service-token path. The caller is on the phone with
  no session, so it verifies the shared X-Service-Token and then arms
  service_request_ctx() to write under the RLS bypass (the four *_manage
  policies carry the same clause as payments_manage). It is identity-free by
  design.
- Every other route is identity-gated on get_current_user.
- Each intake and each disposition change writes a compliance_events audit
  row, so the PV trail is reconstructable from the audit log alone.
- A serious-case pv_alert to the PVOIC mailbox is best-effort: a missing
  mailbox or SMTP key never fails an intake that has already stored the case.
"""

import base64
import hmac
import os
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.postgres import (
    create_adverse_event,
    create_compliance_event,
    create_medical_inquiry,
    create_notification,
    create_product,
    create_quality_complaint,
    get_adverse_event,
    get_call,
    get_quality_complaint,
    list_adverse_events,
    service_request_ctx,
    update_quality_complaint,
)
from app.services.e2b import (
    CASE_NOT_FOUND_DETAIL,
    StubGatewayAdapter,
    e2b_export_block,
    e2b_xml_from_case,
)
from app.services.notifications import send_notification
from app.services.pharmacovigilance import (
    PQC_TRANSITIONS,
    PV_LANGUAGES,
    build_e2b_case,
    classify_contact_type,
    classify_seriousness,
    compute_reporting_deadline,
    export_csv_text,
    next_pqc_status,
    parse_product_csv,
    render_case_html,
    validate_minimum_criteria,
)

router = APIRouter(prefix="/api/pv", tags=["pv"])

# The compliance_events audit vocabulary. Both legs are recorded so the trail
# reads as "a case arrived" and then "a complaint moved forward".
PV_INTAKE_EVENT = "pv_case_intake"
PV_DISPOSITION_EVENT = "pqc_disposition"
PV_E2B_EVENT = "pv_e2b_prepared"


# ─── Request models ─────────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    clinic_id: str
    name: str
    generic_name: str = ""
    strength: str = ""
    dosage_form: str = ""
    manufacturer: str = ""


class ProductImport(BaseModel):
    clinic_id: str
    csv_text: str


class PvCaseCreate(BaseModel):
    """One caller report. Every field is what was said, not interpreted."""

    clinic_id: str
    call_id: str = ""
    language: str = "en"
    # Caller speech. The agent puts the complaint here; classification reads it.
    event_text: str = ""
    question_text: str = ""
    defect_description: str = ""
    # ICH E2A criteria the caller reported — flags only, never free text.
    seriousness_flags: list = []
    product_id: str = ""
    product_name: str = ""
    product_strength: str = ""
    batch_no: str = ""
    expiry: str = ""
    photos_url: list = []
    reporter_type: str = ""
    reporter_contact: dict = {}
    patient: dict = {}
    event_onset_date: str = ""
    outcome: str = ""
    expectedness: str = ""
    # The reporter's own words about the suspect drug. Stored verbatim.
    causality_reporter: str = ""


class ComplaintUpdate(BaseModel):
    investigation_status: str = ""
    disposition: str = ""
    capa_ref: str = ""


class PvExportRequest(BaseModel):
    clinic_id: str
    format: str = "csv"  # csv (flat E2B) or json (grouped E2B)
    status: str = ""
    serious_only: bool = False


# ─── Helpers ────────────────────────────────────────────────────────────────
def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def _optional_uuid(value: str, what: str) -> Optional[uuid.UUID]:
    return _uuid(value, what) if value else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return "" if value is None else str(value)


def _parse_iso(value: str) -> datetime:
    """ISO string -> aware datetime; unparseable/absent input falls back to now."""
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return _now()
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _optional_date(value: str, what: str) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid {what}: {value}")


def _language(value: str) -> str:
    """A supported notification language, or English."""
    code = str(value or "").lower()
    return code if code in PV_LANGUAGES else "en"


def _contact_text(data: PvCaseCreate) -> str:
    """Whichever field the agent actually filled in for this call."""
    for field in (data.event_text, data.question_text, data.defect_description):
        if field and field.strip():
            return field
    return ""


def _case_row(p) -> dict:
    """Serialize an AdverseEvent ORM row into the E2B/print case shape."""
    return {
        "id": str(p.id),
        "case_type": "AE",
        "clinic_id": str(p.clinic_id),
        "call_id": str(p.call_id) if p.call_id else None,
        "product_id": str(p.product_id) if p.product_id else None,
        "reporter_type": p.reporter_type,
        "reporter_contact": p.reporter_contact or {},
        "patient_age": p.patient_age,
        "patient_sex": p.patient_sex,
        "patient_initials": p.patient_initials,
        "event_text": p.event_text,
        "event_onset_date": _iso(p.event_onset_date),
        "outcome": p.outcome,
        "seriousness_flags": p.seriousness_flags or [],
        "expectedness": p.expectedness,
        "causality_reporter": p.causality_reporter,
        "e2b_minimum_met": bool(p.e2b_minimum_met),
        "status": p.status,
        "received_at": _iso(p.received_at),
        "notification_deadline": _iso(p.notification_deadline),
        "notified_at": _iso(p.notified_at),
        "source_channel": p.source_channel,
        "recording_consent": p.recording_consent,
    }


# ─── Product dictionary (identity-gated) ────────────────────────────────────
@router.post("/products")
async def create_product_ep(data: ProductCreate, user=Depends(get_current_user)):
    """Add a product to the clinic's PV dictionary."""
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="name is required")
    row = await create_product(
        clinic_id=_uuid(data.clinic_id, "clinic_id"),
        name=data.name.strip(),
        generic_name=data.generic_name.strip() or None,
        strength=data.strength.strip() or None,
        dosage_form=data.dosage_form.strip() or None,
        manufacturer=data.manufacturer.strip() or None,
    )
    return {
        "status": "created",
        "product": {
            "id": str(row.id),
            "name": row.name,
            "generic_name": row.generic_name,
            "strength": row.strength,
            "dosage_form": row.dosage_form,
            "manufacturer": row.manufacturer,
        },
    }


@router.post("/products/import")
async def import_products_ep(data: ProductImport, user=Depends(get_current_user)):
    """Bulk-load the product dictionary from CSV text.

    Rows without a name are reported and skipped — a nameless product cannot
    be referenced by a case. The response separates imported rows from errors
    so a partial catalogue is never mistaken for a clean load.
    """
    cid = _uuid(data.clinic_id, "clinic_id")
    rows, errors = parse_product_csv(data.csv_text)
    imported = []
    for entry in rows:
        created = await create_product(
            clinic_id=cid,
            name=entry.get("name", ""),
            generic_name=entry.get("generic_name") or None,
            strength=entry.get("strength") or None,
            dosage_form=entry.get("dosage_form") or None,
            manufacturer=entry.get("manufacturer") or None,
        )
        imported.append(str(created.id))
    return {
        "status": "imported",
        "imported": len(imported),
        "product_ids": imported,
        "errors": errors,
    }


# ─── Intake (service-token verified, identity-free) ─────────────────────────
@router.post("/cases")
async def create_pv_case_ep(request: Request, data: PvCaseCreate):
    """Capture one caller report as a PV case (voice/agent path).

    Guarded by the shared service token, NOT a user JWT: the caller is on the
    phone. Verified requests arm service_request_ctx() so the four *_manage
    RLS policies admit the write (external callers cannot set the GUC over
    HTTP, and without the token this endpoint 401s).

    Classification -> E2B minimum -> ICH E2A flags -> India clock, then the
    case is stored on the right table. An incomplete case is stored with
    e2b_minimum_met=false and a follow-up, never dropped.
    """
    # Constant-time token compare, inlined rather than reusing the voice
    # router's helper so this endpoint's ONLY guard is visible in one place.
    # The env default matches the compose / .env.example dev value and MUST be
    # overridden in prod.
    expected = os.environ.get("WEBHOOK_SERVICE_TOKEN", "dev-service-token")
    got = request.headers.get("X-Service-Token", "")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="invalid or missing service token")

    cid = _uuid(data.clinic_id, "clinic_id")
    call_uuid = _optional_uuid(data.call_id, "call_id")
    product_uuid = _optional_uuid(data.product_id, "product_id")
    patient = data.patient or {}
    reporter = data.reporter_contact or data.reporter_type

    text = _contact_text(data)
    contact = classify_contact_type(text, data.language)
    is_serious, criteria = classify_seriousness(data.seriousness_flags)
    e2b_met, missing = validate_minimum_criteria(
        data.event_text or text,
        reporter,
        patient,
        data.product_name or data.product_id,
    )
    received = _now()
    deadline, days_remaining = compute_reporting_deadline(is_serious, received)

    # Recording consent is a property of the PARENT CALL, not of this payload:
    # the agent never decides it, and a PV case must never widen it.
    recording_consent = None
    if call_uuid is not None:
        call = await get_call(call_uuid)
        recording_consent = getattr(call, "recording_consent", None) if call else None

    common = {
        "call_id": call_uuid,
        "product_id": product_uuid,
        "recording_consent": recording_consent,
        "received_at": received,
    }

    row = None
    if contact == "AE":
        initials = patient.get("initials") or patient.get("patient_initials") or ""
        row = await create_adverse_event(
            clinic_id=cid,
            **common,
            reporter_type=data.reporter_type or None,
            reporter_contact=data.reporter_contact or None,
            patient_age=str(patient.get("age") or "") or None,
            patient_sex=str(patient.get("sex") or "") or None,
            patient_initials=str(initials) or None,
            event_text=data.event_text or text,
            event_onset_date=_optional_date(data.event_onset_date, "event_onset_date"),
            outcome=data.outcome or None,
            seriousness_flags=criteria,
            expectedness=data.expectedness or None,
            causality_reporter=data.causality_reporter or None,
            e2b_minimum_met=e2b_met,
            status="new",
            notification_deadline=deadline,
            source_channel="voice",
        )
    elif contact == "PQC":
        row = await create_quality_complaint(
            clinic_id=cid,
            **common,
            batch_no=data.batch_no or None,
            expiry=_optional_date(data.expiry, "expiry"),
            defect_description=data.defect_description or text,
            photos_url=data.photos_url or None,
            investigation_status="captured",
        )
    elif contact == "MI":
        row = await create_medical_inquiry(
            clinic_id=cid,
            **common,
            question_text=data.question_text or text,
            category="other",
            language=_language(data.language),
            status="open",
        )

    # Audit: the trail must be reconstructable from compliance_events alone.
    await create_compliance_event(
        clinic_id=cid,
        event_type=PV_INTAKE_EVENT,
        severity="high" if is_serious else "medium",
        description=(
            f"{contact} captured"
            + (f" serious={','.join(criteria)}" if criteria else "")
            + (f" e2b_missing={','.join(missing)}" if missing else " e2b_minimum_met")
            + f" deadline={deadline.isoformat()}"
        ),
        detected_at=received,
    )

    # A serious case has 15 days to reach the regulator, so tell the PVOIC
    # mailbox now. NON-FATAL by design (mirrors the payment_link hook): a
    # missing PV_PVOIC_EMAIL, an unready SMTP channel or any dispatch error
    # must never fail an intake whose case is already stored.
    mailbox = os.environ.get("PV_PVOIC_EMAIL", "").strip()
    if is_serious and row is not None and mailbox:
        try:
            alert = send_notification(
                "pv_alert",
                mailbox,
                _language(data.language),
                {"case_id": str(row.id), "deadline": deadline.isoformat()},
                env=os.environ,
            )
            async with service_request_ctx():
                await create_notification(
                    clinic_id=cid,
                    kind="pv_alert",
                    recipient=mailbox,
                    language=_language(data.language),
                    params=f'{{"case_id": "{row.id}", "deadline": "{deadline.isoformat()}"}}',
                    channel=alert["channel"],
                    provider=alert["provider"],
                    status=alert["status"],
                    template=alert["message"],
                )
        except Exception:
            # Best-effort side effect — swallow (never break the intake).
            pass

    return {
        "status": "captured" if row is not None else "not_a_pv_case",
        "contact_type": contact,
        "case_id": str(row.id) if row is not None else None,
        "is_serious": is_serious,
        "seriousness_criteria": criteria,
        "e2b_minimum_met": e2b_met,
        "e2b_missing": missing,
        "notification_deadline": deadline.isoformat(),
        "days_remaining": days_remaining,
        "recording_consent": recording_consent,
    }


# ─── Dashboard (identity-gated) ─────────────────────────────────────────────
@router.get("/cases")
async def list_pv_cases_ep(
    clinic_id: str,
    status: str = "",
    serious_only: bool = False,
    user=Depends(get_current_user),
):
    """List a clinic's cases, soonest submission deadline first.

    Ordering is the point: an overdue serious case must not sit below a week
    of routine traffic, so every row also carries days_remaining and overdue.
    """
    rows = await list_adverse_events(
        clinic_id=_uuid(clinic_id, "clinic_id"),
        status=status or None,
        serious_only=serious_only,
    )
    cases = []
    for row in rows:
        case = _case_row(row)
        _, days_remaining = compute_reporting_deadline(
            bool(case["seriousness_flags"]),
            _parse_iso(case["received_at"]),
            now=_now(),
        )
        case["days_remaining"] = days_remaining
        case["overdue"] = days_remaining < 0
        cases.append(case)
    return {"cases": cases, "count": len(cases)}


# ─── Export (identity-gated) ────────────────────────────────────────────────
@router.post("/export")
async def export_pv_ep(data: PvExportRequest, user=Depends(get_current_user)):
    """Export cases in the E2B(R3) minimum shape.

    format="json" returns the grouped data-element bundle; format="csv" the
    flat, one-row-per-case interchange. Both are built from the same bundle,
    so the two exports can never drift.
    """
    fmt = (data.format or "csv").lower()
    if fmt not in ("csv", "json"):
        raise HTTPException(status_code=422, detail=f"invalid format: {data.format}")
    rows = await list_adverse_events(
        clinic_id=_uuid(data.clinic_id, "clinic_id"),
        status=data.status or None,
        serious_only=data.serious_only,
    )
    bundles = [build_e2b_case(_case_row(row)) for row in rows]
    if fmt == "json":
        return {"format": "json", "count": len(bundles), "cases": bundles}
    return PlainTextResponse(
        export_csv_text(bundles),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="pv-e2b-export.csv"'
        },
    )


# ─── Print view (identity-gated) ────────────────────────────────────────────
@router.get("/cases/{case_id}/print")
async def print_pv_case_ep(case_id: str, user=Depends(get_current_user)):
    """Self-contained printable case sheet — captured facts only.

    Carries the SOURCE DATA ONLY / NO_MEDICAL_ADVICE banner, and deliberately
    shows no cause, no diagnosis and no advice: the sheet is a record of what
    was reported, for the pharmacovigilance officer to act on.
    """
    row = await get_adverse_event(_uuid(case_id, "case_id"))
    if row is None:
        raise HTTPException(status_code=404, detail="case not found")
    return HTMLResponse(render_case_html(_case_row(row)))


# ─── E2B(R3) XML + gateway adapter (phase-2 slice 2A) ───────────────────────
# NOTHING LEAVES THE SYSTEM FROM HERE. The generator is Phase-1-bundle-driven
# (app/services/e2b.py) and the only adapter in this slice is a stub: the
# NCC-PvPI E2B-XML endpoint, its credentials and a validated environment (GVP
# Module I QMS) are deployment configuration, and a PVOIC signs off and sends.
#
# Gating differs by caller, deliberately:
# - GET .../e2b.xml is SERVICE-TOKEN guarded like intake, because its caller is
#   a machine (a safety system or an export job) holding no user session.
# - POST .../e2b is IDENTITY gated, because preparing the artifact for a
#   regulator is a PVOIC action.


async def _e2b_case(case_id: str) -> tuple:
    """(case row, sender case id) for a stored case, or the gate's refusal.

    Returns (row, case, sender_case_id) on success; raises the gate's own
    HTTPException otherwise, so both routes refuse a missing case (404) and a
    case that cannot yet be an ICSR (422) from ONE decision, not two copies of
    it.
    """
    cid = _uuid(case_id, "case_id")
    row = await get_adverse_event(cid)
    case = _case_row(row) if row is not None else {}
    status, detail = e2b_export_block(case)
    if status == 404:
        raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)
    if status == 422:
        raise HTTPException(status_code=422, detail=detail)
    return row, case, str(cid)


@router.get("/cases/{case_id}/e2b.xml")
async def get_pv_case_e2b_xml_ep(request: Request, case_id: str):
    """E2B(R3)-shaped XML for ONE validated case. Nothing is submitted.

    Service-token guarded exactly like intake (constant-time compare, no user
    identity on the path). The document is generated from the Phase-1 export
    bundle, so it mirrors the JSON/CSV exports key for key, and it is
    deterministic: the same case always produces the same bytes, which is what
    makes an audit trail of "what was generated" meaningful.
    """
    expected = os.environ.get("WEBHOOK_SERVICE_TOKEN", "dev-service-token")
    got = request.headers.get("X-Service-Token", "")
    if not hmac.compare_digest(got, expected):
        raise HTTPException(status_code=401, detail="invalid or missing service token")

    _row, case, sender_case_id = await _e2b_case(case_id)
    xml = e2b_xml_from_case(build_e2b_case(case), sender_case_id)
    return Response(
        content=xml,
        media_type="application/xml",
        headers={
            "Content-Disposition": f'attachment; filename="e2b-{sender_case_id}.xml"'
        },
    )


@router.post("/cases/{case_id}/e2b")
async def prepare_pv_case_e2b_submission_ep(case_id: str, user=Depends(get_current_user)):
    """Prepare a case's ICSR and hand it to the gateway adapter. NOTHING IS SENT.

    Identity gated: this is the PVOIC's step. The artifact is generated, passed
    to the STUB adapter, and the acknowledgement comes back in the response for
    sign-off — there is no endpoint, credential or client in this slice, and
    `submitted` is a constant false so no consumer can read a preparation as a
    transmission.

    The day-zero clock is deliberately untouched: preparing is not submitting,
    and the compliance_events row records what was built, for which channel,
    with which receipt — the audit trail has to show the difference between
    "generated" and "sent".
    """
    row, case, sender_case_id = await _e2b_case(case_id)
    xml = e2b_xml_from_case(build_e2b_case(case), sender_case_id)

    # The only adapter this slice ships. A live adapter is a separate, validated
    # deployment concern (endpoint + MAH credentials + TLS), never this call.
    adapter = StubGatewayAdapter()
    reply = adapter.submit(xml.encode("utf-8"))

    await create_compliance_event(
        clinic_id=row.clinic_id,
        event_type=PV_E2B_EVENT,
        severity="high" if case["seriousness_flags"] else "medium",
        description=(
            f"E2B(R3) XML prepared for submission; channel={adapter.channel()} "
            f"sender_case_id={sender_case_id} xml_bytes={len(xml.encode('utf-8'))} "
            f"receipt={reply.receipt_id} submitted=false"
        ),
    )

    return {
        "status": "prepared_not_submitted",
        # The sender's own case identifier IS the stored case id in this slice;
        # they are echoed separately because a gateway receipt keys on the C.1.8.1
        # value, and the XML generator must not be the only place that lives.
        "case_id": sender_case_id,
        "sender_case_id": sender_case_id,
        "channel": adapter.channel(),
        "xml": xml,
        "payload": base64.b64encode(reply.payload).decode("ascii"),
        "gateway_reply": reply.as_dict(),
        "submitted": False,
        "note": (
            "slice 2A: generated and staged for a PVOIC, not sent. The NCC-PvPI "
            "endpoint and MAH credentials are deployment configuration."
        ),
    }


# ─── Quality complaint disposition (identity-gated) ─────────────────────────
@router.patch("/complaints/{complaint_id}")
async def update_complaint_ep(
    complaint_id: str, data: ComplaintUpdate, user=Depends(get_current_user)
):
    """Move a complaint forward one legal step.

    The state machine is forward-only (captured -> investigating -> disposition
    -> capa, capa terminal), so an out-of-order step is a 409 conflict rather
    than a 500 — the caller asked for something the process does not allow,
    and silently accepting it would corrupt the audit trail.
    """
    cid = _uuid(complaint_id, "complaint_id")
    row = await get_quality_complaint(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="complaint not found")
    target = data.investigation_status.strip()
    if not target:
        raise HTTPException(status_code=422, detail="investigation_status is required")

    approved = next_pqc_status(row.investigation_status, target)
    if approved is None:
        allowed = ", ".join(PQC_TRANSITIONS.get(row.investigation_status, ())) or "none"
        raise HTTPException(
            status_code=409,
            detail=(
                f"illegal transition {row.investigation_status} -> {target}; "
                f"allowed from {row.investigation_status}: {allowed}"
            ),
        )

    updated = await update_quality_complaint(
        cid,
        investigation_status=approved,
        disposition=data.disposition or None,
        capa_ref=data.capa_ref or None,
    )
    if not updated:
        raise HTTPException(status_code=409, detail="complaint not updated")

    await create_compliance_event(
        clinic_id=row.clinic_id,
        event_type=PV_DISPOSITION_EVENT,
        severity="medium",
        description=(
            f"{row.investigation_status} -> {approved}"
            + (f" capa={data.capa_ref}" if data.capa_ref else "")
        ),
    )
    return {
        "status": "updated",
        "complaint_id": str(cid),
        "investigation_status": approved,
        "previous_status": row.investigation_status,
    }
