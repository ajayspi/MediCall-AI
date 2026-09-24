"""Calls API — list/detail/state/transcript (API routes phase).

List is clinic-scoped with optional state/language/severity/date filters and
pagination; state transitions are validated against the G3 state machine
(STATE_TRANSITIONS) BEFORE the raw DB setter — invalid transition = 409.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.db.postgres import get_call, list_calls, update_call_state
from app.models.call import STATE_TRANSITIONS, CallState, TriageSeverity
from app.schemas.call import CallStateUpdate

router = APIRouter(prefix="/api/calls", tags=["calls"])

# Filter whitelists (mirror models.call enums + postgres SUPPORTED_LANGUAGES).
CALL_LANGUAGE_FILTERS = ("hi", "en", "ta", "te", "bn")
CALL_SEVERITY_FILTERS = ("green", "amber", "red", "critical")
MAX_LIMIT = 200
DEFAULT_LIMIT = 50


def call_row(c) -> dict:
    """Serialize a Call ORM row to the API response shape (incl. transcript)."""
    return {
        "id": str(c.id),
        "clinic_id": str(c.clinic_id),
        "caller_number": c.caller_number,
        "caller_language": c.caller_language,
        "state": c.state,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "duration_seconds": c.duration_seconds,
        "transcript": c.transcript or [],
        "stt_confidence": c.stt_confidence,
        "triage_severity": c.triage_severity,
        "diagnosed_conditions": c.diagnosed_conditions or [],
        "prescription_issued": c.prescription_issued,
        "appointment_scheduled": c.appointment_scheduled,
        "appointment_id": str(c.appointment_id) if c.appointment_id else None,
        "escalated_to_human": c.escalated_to_human,
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def _parse_dt(value: str, what: str):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"invalid {what}")


@router.get("")
async def list_calls_ep(
    clinic_id: str,
    state: str = "",
    language: str = "",
    severity: str = "",
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
):
    """List calls for a clinic, newest first, with optional filters."""
    cid = _uuid(clinic_id, "clinic_id")
    if state and state not in {s.value for s in CallState}:
        raise HTTPException(status_code=422, detail=f"invalid state: {state}")
    if language and language not in CALL_LANGUAGE_FILTERS:
        raise HTTPException(status_code=422, detail=f"invalid language: {language}")
    if severity and severity not in CALL_SEVERITY_FILTERS:
        raise HTTPException(status_code=422, detail=f"invalid severity: {severity}")
    limit = min(max(limit, 1), MAX_LIMIT)
    rows = await list_calls(
        clinic_id=cid,
        state=state or None,
        language=language or None,
        severity=severity or None,
        from_=_parse_dt(from_, "from"),
        to=_parse_dt(to, "to"),
        limit=limit,
        offset=max(offset, 0),
    )
    return [call_row(r) for r in rows]


@router.get("/{call_id}")
async def get_call_ep(call_id: str):
    """Call detail (record view, transcript, severity)."""
    cid = _uuid(call_id, "call_id")
    row = await get_call(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return call_row(row)


@router.patch("/{call_id}/state")
async def update_call_state_ep(call_id: str, data: CallStateUpdate):
    """Transition a call's state — validated against the G3 state machine."""
    cid = _uuid(call_id, "call_id")
    try:
        new_state = CallState(data.state)
    except ValueError:
        raise HTTPException(
            status_code=422, detail=f"invalid state: {data.state}"
        )
    row = await get_call(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    try:
        current = CallState(row.state)
    except ValueError:
        current = None
    if current is None or new_state not in STATE_TRANSITIONS.get(current, []):
        raise HTTPException(
            status_code=409,
            detail=f"invalid transition {row.state} -> {new_state.value}",
        )
    ok = await update_call_state(cid, new_state.value)
    if not ok:
        raise HTTPException(status_code=404, detail="call not found")
    return {"call_id": str(cid), "state": new_state.value, "updated": ok}


@router.get("/{call_id}/transcript")
async def get_call_transcript_ep(call_id: str):
    """Transcript for a call (multi-language turns JSONB)."""
    cid = _uuid(call_id, "call_id")
    row = await get_call(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="call not found")
    return {"call_id": str(cid), "transcript": row.transcript or []}