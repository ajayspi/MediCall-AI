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

One route has TWO accepted callers, and the order is the whole argument.
GET /cases/{case_id}/e2b.xml was service-token-only because its caller was a
machine. Slice 2.6 added a staff identity as a SECOND way in without touching
the first: the constant-time X-Service-Token compare still runs first and still
short-circuits, and only a caller it rejects is offered get_current_user — the
same primitive, not a copy. So an export job keeps working untouched, a PVOIC
can finally download the artifact, and a request with neither is still 401.
The export gate below is downstream of all of it and unchanged, which is what
keeps a 409 for an unstamped expedited case identical for both callers.

Phase-2 additions keep the same shape. Slice 2A added the E2B(R3) generator and
the STUB gateway adapter (nothing is ever sent from this router). Slice 2E
added the read-only PVOIC compliance views - GET /dashboard, /dashboard/psur
and /audit - which fetch through the existing repository helpers and hand the
rows to the pure helper app/services/pv_dashboard.py, so every number is
assembled in one testable place and the India clock is never re-derived here.

Slice 2D added the MI approved-content knowledge base:

  POST /api/pv/responses                        - append a response version
  GET  /api/pv/responses?product_id=            - version history (audit)
  POST /api/pv/inquiries/{inquiry_id}/answer    - answer one MI inquiry

All three are IDENTITY gated: approved wording is written by a Medical Affairs
officer on a logged-in session, never by the tokenless intake path. The decision
logic (which version is answerable, whether the answer may speak at all, whether
the enquirer's words are also reportable) lives in the pure helper
app/services/medical_info.py; this router only fetches rows, passes them in and
persists what comes back. The answer path NEVER creates a case: an inquiry whose
words carry AE/PQC content is FLAGGED (suggest_report_to_pv) and the intake path
owns the one-business-day handoff, so there is a single source of truth per case.

Slice 2C added the coding layer and the WHO-UMC causality capture:

  POST /api/pv/cases/{case_id}/coding        - code a case's event + product
  POST /api/pv/cases/{case_id}/causality     - capture WHO-UMC causality

Both are IDENTITY gated, because both write a clinical judgement onto a case.
Coding is a LOOKUP, not an opinion: the terms the caller reported are mapped
through whatever dictionary is installed, a miss is reported as a miss, and no
code is ever invented. Causality is CAPTURED, not derived - the reporter's and
the reviewer's own WHO-UMC assessments are validated against the scale and
stored verbatim, and an unattributed review is refused rather than defaulted.
Both rules live in the stdlib-only app/services/coding.py, so they are
unit-testable with no database and no dictionary licence.

The same module owns the EXPEDITED EXPORT GATE that both e2b routes already
share: a serious case that was not expected per the label cannot become an ICSR
until a named reviewer has stamped their own causality category on it. That
stamp is what these two routes exist to write.

Slice 2.6 closed the PVOIC's last end-to-end gap - open a case, take the artifact
away - with two small changes and no new concept:

  GET /api/pv/cases/{case_id}                  - ONE case, the detail page's data
  GET /api/pv/cases/{case_id}/e2b.xml          - + a staff identity as a 2nd caller

The detail read is identity-gated and returns the same _case_row the queue, the
print sheet and both e2b routes already build from, so a field on screen is a
field in the export. The e2b.xml change is additive auth, described above: the
machine path is byte-for-byte the path it was, and the browser is a guest of it,
not its owner.
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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.db.postgres import (
    create_adverse_event,
    create_compliance_event,
    create_medical_inquiry,
    create_notification,
    create_product,
    create_quality_complaint,
    create_response,
    get_adverse_event,
    get_call,
    get_db_session,
    get_medical_inquiry,
    get_product,
    get_quality_complaint,
    list_adverse_events,
    list_compliance_events,
    list_medical_inquiries,
    list_products,
    list_quality_complaints,
    list_responses,
    service_request_ctx,
    update_adverse_event_causality,
    update_adverse_event_coding,
    update_medical_inquiry_answer,
    update_quality_complaint,
    update_response_status,
)
from app.services.coding import (
    causality_capture,
    code_case,
    get_dictionary,
    is_expedited,
    missing_review_stamp,
)
from app.services.e2b import (
    CASE_NOT_FOUND_DETAIL,
    StubGatewayAdapter,
    e2b_export_block,
    e2b_xml_from_case,
)
from app.services.medical_info import (
    answer_medical_inquiry,
    next_version,
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
from app.services.pv_dashboard import (
    AUDIT_MAX_DAYS,
    build_audit_trail,
    build_dashboard_snapshot,
    build_psur_schedule,
)

router = APIRouter(prefix="/api/pv", tags=["pv"])

# The compliance_events audit vocabulary. Both legs are recorded so the trail
# reads as "a case arrived" and then "a complaint moved forward".
PV_INTAKE_EVENT = "pv_case_intake"
PV_DISPOSITION_EVENT = "pqc_disposition"
PV_E2B_EVENT = "pv_e2b_prepared"
# Phase-2 slice 2D: who approved which wording, and what an enquirer was told.
PV_RESPONSE_EVENT = "pv_response_approved"
PV_INQUIRY_ANSWERED_EVENT = "pv_inquiry_answered"
# Phase-2 slice 2C: a dictionary hit (or a reported miss) per case, and the
# WHO-UMC causality assessment the reporter and the reviewer each stated.
PV_CODED_EVENT = "pv_case_coded"
PV_CAUSALITY_EVENT = "pv_causality_captured"


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


class PvCodingRequest(BaseModel):
    """Code a case against the installed dictionary.

    No terms: the text that gets coded is what the caller already reported on
    the case, read by the service. Re-sending it here would let a code be
    attached to words nobody said.
    """

    note: str = ""


class PvCausalityCapture(BaseModel):
    """One WHO-UMC causality capture, in the words of the humans who own it.

    `reporters_assessment` is what the reporter stated, `reviewer_assessment`
    what the reviewer stated. `reviewer` and `reviewed_at` are the reviewer's
    identity and their own moment — both required whenever a reviewer assessment
    is present, because an unattributed review is refused, never defaulted. No
    field here is optional-with-a-fallback: this service has no clock and will
    not invent an assessment to fill a gap.
    """

    reporters_assessment: str = ""
    reviewer_assessment: str = ""
    reviewer: str = ""
    reviewed_at: str = ""


class PvExportRequest(BaseModel):
    clinic_id: str
    format: str = "csv"  # csv (flat E2B) or json (grouped E2B)
    status: str = ""
    serious_only: bool = False
    case_id: str = ""  # optional: restrict the export to ONE case (detail-page download)


class ProductResponseCreate(BaseModel):
    """One approved MI response, in the words the company has approved."""

    clinic_id: str
    product_id: str
    language: str = "en"
    category: str
    response_body: str
    approved_by: str = ""


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


def _slot_key(language: str, category: str) -> str:
    """Canonical (language, category) key for a knowledge-base slot.

    The unit of versioning: exactly one live response per slot. Normalised so
    "Dosing" and "dosing " are the same slot rather than two half-populated
    ones, and so a slot key can be compared straight out of a row.
    """
    lang = " ".join(str(language or "").lower().split())
    cat = " ".join(str(category or "").lower().split())
    return f"{lang}|{cat}"


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
        # Slice 2C: the WHO-UMC categories and the coding result. The three
        # stamp fields travel with the row because the export gate decides on
        # the SAME row the export is built from - one shape, no second fetch.
        "reporter_causality": p.reporter_causality,
        "reviewer_causality": p.reviewer_causality,
        "reviewed_by": p.reviewed_by,
        "reviewed_at": _iso(p.reviewed_at),
        "coding": p.coding_json or {},
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


# ─── MI approved-content knowledge base (identity-gated, slice 2D) ───────────
# Phase 1 could only log an MI question and route it to Medical Affairs. These
# three routes add the answer the desk is ALLOWED to give, in the company's own
# approved wording, and the path that applies it to a stored inquiry.
#
# The rules are not here. Which version is answerable, whether the answer may
# speak at all, and whether the enquirer's words are also reportable are decided
# by app/services/medical_info.py from rows this router already knows how to
# fetch — so every decision is unit-tested without a database and the router
# stays a thin adapter, exactly like the dashboard slice.
#
# THE ANSWER PATH NEVER CREATES A CASE. An inquiry whose words carry AE/PQC
# content is flagged (suggest_report_to_pv) and the intake path owns the
# one-business-day handoff; a second writer would be a second, competing source
# of truth for the same report.


def _response_row(row) -> dict:
    """Serialize a ProductResponse row (the audit view of approved content)."""
    return {
        "id": str(row.id),
        "product_id": str(row.product_id),
        "language": row.language,
        "category": row.category,
        "response_body": row.response_body,
        "version": row.version,
        "is_active": bool(row.is_active),
        "approved_by": row.approved_by,
        "approved_at": _iso(row.approved_at),
        "created_at": _iso(row.created_at),
    }


@router.post("/responses")
async def create_response_ep(data: ProductResponseCreate, user=Depends(get_current_user)):
    """Approve a response and store it as the next version of that slot.

    A (product, language, category) slot has at most ONE live version: pushing
    this one DEACTIVATES the rows it supersedes rather than editing or deleting
    them, so the wording an enquirer actually received stays readable beside the
    wording that replaced it. The version number comes from
    medical_info.next_version over this slot's existing versions.
    """
    cid = _uuid(data.clinic_id, "clinic_id")
    product_id = _uuid(data.product_id, "product_id")
    category = data.category.strip()
    body = data.response_body.strip()
    if not category:
        raise HTTPException(status_code=422, detail="category is required")
    if not body:
        raise HTTPException(status_code=422, detail="response_body is required")

    # Cross-clinic writes are refused as a 404 rather than a 403: a caller must
    # not be able to learn that a product id exists in another tenant.
    product = await get_product(product_id)
    if product is None or str(product.clinic_id) != str(cid):
        raise HTTPException(status_code=404, detail="product not found")

    language = _language(data.language)
    existing = await list_responses(product_id)
    slot_key = _slot_key(language, category)
    slot = [row for row in existing if _slot_key(row.language, row.category) == slot_key]
    version = next_version([row.version for row in slot])

    created = await create_response(
        clinic_id=cid,
        product_id=product_id,
        language=language,
        category=category,
        response_body=body,
        version=version,
        is_active=True,
        approved_by=data.approved_by.strip() or None,
        approved_at=_now(),
    )

    superseded = []
    for prior in slot:
        if prior.is_active and await update_response_status(prior.id, False):
            superseded.append({"id": str(prior.id), "version": prior.version})

    await create_compliance_event(
        clinic_id=cid,
        event_type=PV_RESPONSE_EVENT,
        severity="medium",
        description=(
            f"approved MI response product={product_id} category={category} "
            f"language={language} version={version} "
            f"superseded={len(superseded)} "
            f"approved_by={data.approved_by.strip() or 'unrecorded'}"
        ),
    )

    return {
        "status": "created",
        "version": version,
        "response": _response_row(created),
        "superseded": superseded,
    }


@router.get("/responses")
async def list_responses_ep(
    product_id: str, user=Depends(get_current_user)
):
    """A product's approved-content history, newest version first (audit view).

    Superseded rows are INCLUDED and marked, because the question an auditor
    asks is "what was the approved wording on the day of that call?" — which the
    live-only view cannot answer. `answerable_version` names the row that would
    serve an inquiry today, per (language, category) slot.
    """
    pid = _uuid(product_id, "product_id")
    product = await get_product(pid)
    if product is None:
        raise HTTPException(status_code=404, detail="product not found")

    rows = await list_responses(pid)
    # The answerable version per slot is the HIGHEST live one — a slot is
    # meant to hold exactly one, but a hand-edited row must not make this view
    # name a version the answer path would refuse.
    live: dict = {}
    for row in rows:
        if not row.is_active:
            continue
        key = _slot_key(row.language, row.category)
        live[key] = max(live.get(key, 0), row.version)

    responses = []
    for row in rows:
        entry = _response_row(row)
        entry["answerable_version"] = live.get(_slot_key(row.language, row.category))
        responses.append(entry)
    return {"product_id": str(pid), "responses": responses, "count": len(responses)}


@router.post("/inquiries/{inquiry_id}/answer")
async def answer_medical_inquiry_ep(
    inquiry_id: str, user=Depends(get_current_user)
):
    """Answer one stored MI inquiry from approved content only.

    Three possible outcomes, all produced by the pure service from the rows
    fetched here: the approved response (verbatim, with its version), the
    product's own approved label section (verbatim), or the fixed
    NO_MEDICAL_ADVICE phrase. The FIRST TWO close the inquiry; the refusal does
    NOT — it stays `open` because it promises a Medical Affairs follow-up, and
    an inquiry nobody followed up is a worse record than an open one.

    Every outcome is persisted to medical_inquiries.response_text and audited
    (pv_inquiry_answered), so the trail shows which approved wording was used,
    or that none existed. A refusal is a record too: the gap in the knowledge
    base is exactly what a quality review needs to see.
    """
    iid = _uuid(inquiry_id, "inquiry_id")
    inquiry = await get_medical_inquiry(iid)
    if inquiry is None:
        raise HTTPException(status_code=404, detail="inquiry not found")

    # No product means no approved content to speak from, so the service gets
    # neither a response list nor a label and its refusal is the answer.
    product = await get_product(inquiry.product_id) if inquiry.product_id else None
    rows = await list_responses(inquiry.product_id) if product is not None else []

    answered = answer_medical_inquiry(
        inquiry,
        rows,
        product.approved_label_json if product is not None else None,
    )
    refused = answered["source"] == "no_medical_advice"

    await update_medical_inquiry_answer(
        iid,
        answered["answer"],
        status="open" if refused else "answered",
    )
    await create_compliance_event(
        clinic_id=inquiry.clinic_id,
        event_type=PV_INQUIRY_ANSWERED_EVENT,
        severity="high" if answered["suggest_report_to_pv"] else "medium",
        description=(
            f"MI inquiry answered source={answered['source']} "
            f"category={answered['category']} language={answered['language']} "
            f"version={answered['version'] if answered['version'] else 'none'} "
            f"follow_up_required={refused} "
            f"suggest_report_to_pv={answered['suggest_report_to_pv']} "
            f"case_created=false"
        ),
    )

    return {
        "inquiry_id": str(iid),
        "status": "open" if refused else "answered",
        "answer": answered["answer"],
        "source": answered["source"],
        "version": answered["version"],
        "reasoning": answered["reasoning"],
        "category": answered["category"],
        "language": answered["language"],
        "requires_medical_affairs_follow_up": refused,
        "suggest_report_to_pv": answered["suggest_report_to_pv"],
        "report_reasons": answered["report_reasons"],
        "case_created": False,
        "note": (
            "approved content or the product's approved label only; anything "
            "else is the fixed NO_MEDICAL_ADVICE phrase. Reportable content is "
            "flagged for the PVOIC — this endpoint never opens a case."
        ),
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


# ─── PVOIC compliance dashboard (identity-gated, READ-ONLY) ─────────────────
# Phase-2 slice 2E. Three read routes over the SAME data the officer already
# works with: the queue, the PSUR calendar, the audit trail. No writer, no
# new table, no new dependency, and no second copy of the India clock — every
# number is assembled by the pure helper app/services/pv_dashboard.py from rows
# this router already knows how to fetch.
#
# The dashboard is a VIEW, never a decision: it reports status, deadlines and
# counts, and the PVOIC judges causality, coding and submission.
#
# The case list is fetched with its maximum page size: a dashboard that counted
# only the first page would report a clinic with 300 open cases as having 200.
DASHBOARD_CASE_LIMIT = 200


@router.get("/dashboard")
async def pv_dashboard_ep(clinic_id: str, user=Depends(get_current_user)):
    """The PVOIC's compliance snapshot for one clinic. READ-ONLY.

    One document: case counts by type and status, the India-clock countdowns
    (overdue red flags, everything due in the next 48h), the complaint
    pipeline, the PSUR calendar and the last 7 days of PV audit events.

    Overdue is a flag on an OPEN case, never a status: a case the officer has
    already notified, submitted or closed is not overdue, however late it went.
    """
    cid = _uuid(clinic_id, "clinic_id")
    ae_rows = await list_adverse_events(clinic_id=cid, limit=DASHBOARD_CASE_LIMIT)
    pqc_rows = await list_quality_complaints(clinic_id=cid)
    mi_rows = await list_medical_inquiries(clinic_id=cid)
    product_rows = await list_products(clinic_id=cid)
    audit_rows = await list_compliance_events(clinic_id=cid)

    return {
        "clinic_id": str(cid),
        **build_dashboard_snapshot(
            ae_rows=ae_rows,
            pqc_rows=pqc_rows,
            mi_rows=mi_rows,
            product_rows=product_rows,
            audit_rows=audit_rows,
            now=_now(),
        ),
    }


@router.get("/dashboard/psur")
async def pv_dashboard_psur_ep(clinic_id: str, user=Depends(get_current_user)):
    """The PSUR calendar per product: next window, and whether one is due now.

    Its own endpoint because it is the one view a product owner refreshes on a
    calendar rather than a queue — the schedule itself is the same pure helper
    the snapshot embeds, so the two can never disagree.
    """
    cid = _uuid(clinic_id, "clinic_id")
    product_rows = await list_products(clinic_id=cid)
    return {"clinic_id": str(cid), **build_psur_schedule(product_rows, now=_now())}


@router.get("/audit")
async def pv_audit_ep(
    clinic_id: str, days: int = 30, user=Depends(get_current_user)
):
    """Recent PV compliance_events rows, newest first (default 30 days).

    Only this module's own event types (pv_* / pqc_*) are returned: the same
    table also carries DPDP events, and a breach row in a PV trail would make
    the count meaningless. Read-only, and the window is bounded (1..365 days)
    so a caller cannot ask for the whole table.
    """
    cid = _uuid(clinic_id, "clinic_id")
    try:
        window = int(days)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="days must be an integer")
    if window < 1 or window > AUDIT_MAX_DAYS:
        raise HTTPException(
            status_code=422, detail=f"days must be between 1 and {AUDIT_MAX_DAYS}"
        )

    rows = await list_compliance_events(clinic_id=cid)
    return {"clinic_id": str(cid), **build_audit_trail(rows, days=window, now=_now())}


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
    if data.case_id:
        # Single-case export (the PVOIC detail page): overrides the clinic
        # filter entirely — this row, or a clear 404. Same lookup + RLS as the
        # singular case route, so a case from another clinic cannot leak here.
        cid = _uuid(data.case_id, "case_id")
        row = await get_adverse_event(cid)
        if row is None:
            raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)
        rows = [row]
    else:
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


# ─── Case detail (identity-gated) ───────────────────────────────────────────
@router.get("/cases/{case_id}")
async def get_pv_case_ep(case_id: str, user=Depends(get_current_user)):
    """ONE case, in the same shape the queue, the print sheet and the E2B
    export already use.

    The PVOIC opens a case from the queue and needs the WHO-UMC stamps, the
    coding result and the India clock on one screen. This route exists so that
    screen has ONE source: the identical `_case_row` serializer, so a field the
    officer sees here is the field the regulator was handed, and no UI can show
    a case the export would not.

    READ-ONLY and identity-gated, like the print sheet: viewing a captured
    report is a staff action, never the tokenless intake path.
    """
    row = await get_adverse_event(_uuid(case_id, "case_id"))
    if row is None:
        raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)
    return _case_row(row)


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
# - GET .../e2b.xml is SERVICE-TOKEN guarded like intake, because its original
#   caller is a machine (a safety system or an export job) holding no user
#   session. Phase-2 slice 2.6 made that gate ADDITIVE: the token check runs
#   first and unchanged, and only a caller it rejects is offered the staff
#   identity path (see _staff_identity_or_none below).
# - POST .../e2b is IDENTITY gated, because preparing the artifact for a
#   regulator is a PVOIC action.


async def _e2b_case(case_id: str) -> tuple:
    """(case row, sender case id) for a stored case, or the gate's refusal.

    Returns (row, case, sender_case_id) on success; raises the gate's own
    HTTPException otherwise, so both routes refuse a missing case (404), a case
    that cannot yet be an ICSR (422) and an expedited case with no reviewer
    stamp (409 — REVIEW_GATE_STATUS in app/services/coding.py) from ONE
    decision, not three copies of it.
    """
    cid = _uuid(case_id, "case_id")
    row = await get_adverse_event(cid)
    case = _case_row(row) if row is not None else {}
    status, detail = e2b_export_block(case)
    if status == 404:
        raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)
    if status:
        # The gate owns its status, raised verbatim and never remapped: 422 for
        # a case that is not yet an ICSR, REVIEW_GATE_STATUS for an expedited
        # case with no reviewer stamp, and whatever a future rule adds. Any
        # non-zero refusal raises — an unrecognised one must never be mistaken
        # for permission to export.
        raise HTTPException(status_code=status, detail=detail)
    return row, case, str(cid)


async def _staff_identity_or_none(request: Request, db) -> Optional[Any]:
    """The authenticated staff member behind this request, or None.

    The 2.6 identity fallback for the XML GET, and it is deliberately a CALL to
    `get_current_user` — the same dependency every other identity-gated route in
    this module uses — not a second copy of it. There is exactly one
    implementation of "is this a valid session": the JWT decode, the expiry and
    inactive-user refusals and the RLS user GUC all live in app/api/auth.py. A
    second copy here would be a second answer to a security question, free to
    drift from the first, and drift in the permissive direction.

    `get_current_user` answers a yes/no question with a 401 or a user, and this
    route needs the first shape to become the second. So the 401 — and only the
    401 — is translated into None here, for the CALLER to combine with its own
    decision. A 401 from this helper never leaves this module: the route decides
    what an unauthenticated request looks like on its own gate, which is the
    right to be raised. Anything else is a real failure and propagates.
    """
    try:
        return await get_current_user(request, db)
    except HTTPException as exc:
        if exc.status_code != 401:
            raise
        return None


@router.get("/cases/{case_id}/e2b.xml")
async def get_pv_case_e2b_xml_ep(
    request: Request,
    case_id: str,
    db: AsyncSession = Depends(get_db_session),
):
    """E2B(R3)-shaped XML for ONE validated case. Nothing is submitted.

    Two callers, one document, one gate. The service-token compare runs FIRST and
    exactly as intake does it (constant-time, no session), so a safety system or
    an export job holding only the shared token is unaffected by slice 2.6. Only
    when that check refuses the caller does this route try a staff identity —
    `get_current_user`, the same dependency the rest of the module gates on — so
    a PVOIC can download the artifact from the browser. A request that carries
    neither is 401.

    Auth decides WHO is asking; `_e2b_case` decides WHETHER they may have it, and
    it runs for both callers, so a 404 / 422 / 409 refusal is identical whoever
    asked. The document is generated from the Phase-1 export bundle, so it
    mirrors the JSON/CSV exports key for key, and it is deterministic: the same
    case always produces the same bytes, which is what makes an audit trail of
    "what was generated" meaningful.
    """
    expected = os.environ.get("WEBHOOK_SERVICE_TOKEN", "dev-service-token")
    got = request.headers.get("X-Service-Token", "")
    service_token_ok = hmac.compare_digest(got, expected)
    if not service_token_ok and await _staff_identity_or_none(request, db) is None:
        raise HTTPException(
            status_code=401, detail="service token or staff identity required"
        )

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


# ─── Coding + WHO-UMC causality (identity-gated, slice 2C) ──────────────────
# Two writes that put a clinical judgement on a case, so both need a logged-in
# PVOIC - never the tokenless intake path, which only ever records what a caller
# said.
#
# The rules are in app/services/coding.py: a case is mapped through whatever
# dictionary is installed (a miss is reported as a miss, a code is never
# invented), and a causality assessment is captured exactly as its author stated
# it. This router fetches the row, passes it in, and persists what comes back -
# which for a refused capture is nothing, because the refusal raises first.


@router.post("/cases/{case_id}/coding")
async def code_pv_case_ep(
    case_id: str, data: PvCodingRequest, user=Depends(get_current_user)
):
    """Code a stored case's event term and suspect product. Nothing is inferred.

    Identity gated: a code is a classification, so it is a PVOIC's action. The
    words that get coded are the words the caller already reported on the case -
    this route supplies no terms of its own, so a code can never be attached to
    something nobody said.

    A HIT is stored on the case and audited. A MISS is audited and stored
    nowhere: an uncoded term stays uncoded until a dictionary covers it, and no
    plausible-looking code is fabricated to fill the hole. A miss on the event
    term refuses the WHOLE coding - the product is not reported either, so a
    half-coded case can never be read downstream as a coded one. Once the event
    term is coded, the product is looked up in its own right, and a product
    miss leaves the event code standing.
    """
    cid = _uuid(case_id, "case_id")
    row = await get_adverse_event(cid)
    if row is None:
        raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)

    result = code_case(_case_row(row), get_dictionary())
    if result["coded"]:
        await update_adverse_event_coding(cid, coding=result)

    # Audited as pv_case_coded, hit or miss: the trail must show that the case
    # WAS run through a dictionary and what came back, or a later reader cannot
    # tell an uncoded case from a case nobody tried to code.
    await create_compliance_event(
        clinic_id=row.clinic_id,
        event_type=PV_CODED_EVENT,
        severity="low",
        description=(
            f"case run through dictionary={result['dictionary']}; "
            f"coded={result['coded']} drug_coded={result['drug_coded']} "
            f"reason={result['reason'] or 'hit'} stored={bool(result['coded'])}"
        ),
    )

    return {
        "status": "coded" if result["coded"] else "not_in_dictionary",
        "case_id": str(cid),
        "dictionary": result["dictionary"],
        "coded": result["coded"],
        "drug_coded": result["drug_coded"],
        "reason": result["reason"],
        "event": result["event"],
        "drug": result["drug"],
        "stored": bool(result["coded"]),
        "note": (
            "slice 2C: mapping only, no inference. A miss stores nothing and no "
            "code is invented; a licensed dictionary can be installed later "
            "without a change to this route."
        ),
    }


@router.post("/cases/{case_id}/causality")
async def capture_pv_case_causality_ep(
    case_id: str, data: PvCausalityCapture, user=Depends(get_current_user)
):
    """Capture the WHO-UMC causality assessment the humans actually stated.

    Identity gated: causality is a judgement, and it belongs to the reporter and
    to the reviewing officer - not to this system. The service validates the
    assessment against the WHO-UMC scale and stores it verbatim; it never
    derives a category from seriousness, from the event text or from the coding
    dictionary, and it never supplies a timestamp of its own for a review it
    did not witness.

    A REFUSED capture is a 422 and writes nothing at all - the reporter's half
    does not survive either, so a rejected review cannot leave a partial
    assessment on the case. On success the response says what the export gate
    still wants, which is how a reviewer learns the case is now ready for an
    ICSR (or what is still missing from the stamp).
    """
    cid = _uuid(case_id, "case_id")
    row = await get_adverse_event(cid)
    if row is None:
        raise HTTPException(status_code=404, detail=CASE_NOT_FOUND_DETAIL)

    case = _case_row(row)
    captured = causality_capture(
        reporters_assessment=data.reporters_assessment,
        reviewer_assessment=data.reviewer_assessment,
        reviewer=data.reviewer,
        reviewed_at=data.reviewed_at,
    )
    if not captured["valid"]:
        raise HTTPException(
            status_code=422,
            detail=f"{captured['error']}: {captured['detail']}",
        )

    # The service already proved this is readable ISO-8601, so the parse only
    # shapes it for the column. A value it cannot shape is left NULL, which
    # leaves the export gate closed — the fail-closed direction, never a stamp
    # that is not there.
    reviewed_at = None
    if captured["reviewed_at"]:
        try:
            reviewed_at = datetime.fromisoformat(captured["reviewed_at"])
        except (TypeError, ValueError):
            reviewed_at = None
    await update_adverse_event_causality(
        cid,
        reporter_causality=captured["reporters_assessment"],
        reviewer_causality=captured["reviewer_assessment"],
        reviewed_by=captured["reviewed_by"],
        reviewed_at=reviewed_at,
    )

    # Audited as pv_causality_captured: WHO-UMC, verbatim, attributed. This is
    # the row that makes "who decided this was probable, and when" answerable
    # months later without reconstructing the case.
    await create_compliance_event(
        clinic_id=row.clinic_id,
        event_type=PV_CAUSALITY_EVENT,
        severity="medium",
        description=(
            f"WHO-UMC causality captured on the {captured['scale']} scale; "
            f"reporter={captured['reporters_assessment'] or '-'} "
            f"reviewer={captured['reviewer_assessment'] or '-'} "
            f"reviewed_by={captured['reviewed_by'] or '-'} "
            f"reviewed_at={captured['reviewed_at'] or '-'} system_assigned=false"
        ),
    )

    # What the export gate still needs, computed from the values just accepted.
    case["reporter_causality"] = captured["reporters_assessment"]
    case["reviewer_causality"] = captured["reviewer_assessment"]
    case["reviewed_by"] = captured["reviewed_by"]
    case["reviewed_at"] = captured["reviewed_at"]
    return {
        "status": "captured",
        "case_id": str(cid),
        "scale": captured["scale"],
        "reporters_assessment": captured["reporters_assessment"],
        "reporters_assessment_verbatim": captured["reporters_assessment_verbatim"],
        "reviewer_assessment": captured["reviewer_assessment"],
        "reviewed_by": captured["reviewed_by"],
        "reviewed_at": captured["reviewed_at"],
        "system_assigned": captured["system_assigned"],
        "export_gate": {
            "expedited": is_expedited(case),
            "missing_review_stamp": missing_review_stamp(case),
        },
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
