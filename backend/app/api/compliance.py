"""Compliance API — DPDP breach flow + consent lifecycle events (G6-Q2 Q3=A1).

spec-dpdp-q2.md (approved 2026-09-25): the buildable part of the 72-hr breach
flow is the event record. POST /api/compliance/events stores a
data_breach / consent_withdrawal / gdpr_request row with its computed
notification_deadline (= detected_at + DPDP_BREACH_NOTIFICATION_HOURS, default
72h); GET lists clinic events; PATCH moves status open -> reported -> closed
(status='reported' stamps reported_at). The actual DPB/affected-user alert is
an operational follow-on (Q8 email channel), NOT a notification kind.

Identity-gated like every domain endpoint; row scoping is enforced by the
compliance_manage RLS policy (clinic membership OR app.service_request) —
mirrors notifications_send / payments_manage.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.db.postgres import (
    create_compliance_event,
    list_compliance_events,
    update_compliance_event,
)
from app.schemas.compliance import ComplianceEventCreate, ComplianceEventUpdate
from app.services.compliance import (
    COMPLIANCE_EVENT_TYPES,
    SEVERITIES,
    STATUSES,
)

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def compliance_row(ev) -> dict:
    """Serialize a ComplianceEvent ORM row (incl. the 72-hr deadline)."""
    return {
        "id": str(ev.id),
        "clinic_id": str(ev.clinic_id),
        "event_type": ev.event_type,
        "severity": ev.severity,
        "status": ev.status,
        "description": ev.description,
        "detected_at": ev.detected_at.isoformat() if ev.detected_at else None,
        "notification_deadline": (
            ev.notification_deadline.isoformat()
            if ev.notification_deadline
            else None
        ),
        "reported_at": ev.reported_at.isoformat() if ev.reported_at else None,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
        "updated_at": ev.updated_at.isoformat() if ev.updated_at else None,
    }


@router.get("")
async def list_compliance_events_ep(
    clinic_id: str,
    status: str = Query("", alias="status"),
    user=Depends(get_current_user),
):
    """List compliance events for a clinic, newest first, optional status."""
    cid = _uuid(clinic_id, "clinic_id")
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=422, detail=f"invalid status: {status} (open/reported/closed)"
        )
    rows = await list_compliance_events(clinic_id=cid, status=status or None)
    return [compliance_row(r) for r in rows]


@router.post("/events", status_code=201)
async def create_compliance_event_ep(
    data: ComplianceEventCreate, user=Depends(get_current_user)
):
    """Record a compliance event; stores the computed 72-hr DPDP deadline."""
    if data.event_type not in COMPLIANCE_EVENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid event_type: {data.event_type} "
            f"({', '.join(COMPLIANCE_EVENT_TYPES)})",
        )
    if data.severity not in SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid severity: {data.severity} "
            f"({', '.join(SEVERITIES)})",
        )
    cid = _uuid(data.clinic_id, "clinic_id")
    row = await create_compliance_event(
        clinic_id=cid,
        event_type=data.event_type,
        severity=data.severity,
        description=data.description,
    )
    return compliance_row(row)


@router.patch("/events/{event_id}")
async def update_compliance_event_ep(
    event_id: str, data: ComplianceEventUpdate, user=Depends(get_current_user)
):
    """Update status/severity. Setting status='reported' stamps reported_at
    server-side (DPB alert sent); closing never un-stamps it."""
    eid = _uuid(event_id, "event_id")
    if data.status is not None and data.status not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid status: {data.status} (open/reported/closed)",
        )
    if data.severity is not None and data.severity not in SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid severity: {data.severity} ({', '.join(SEVERITIES)})",
        )
    ok = await update_compliance_event(
        eid, status=data.status, severity=data.severity
    )
    if not ok:
        raise HTTPException(status_code=404, detail="compliance event not found")
    return {
        "event_id": str(eid),
        "status": data.status,
        "severity": data.severity,
        "reported_at": "stamped when status -> reported",
    }