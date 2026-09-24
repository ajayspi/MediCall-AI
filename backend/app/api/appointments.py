"""Appointments API — list/create/detail/status (API routes phase).

Status transitions are validated against APPOINTMENT_STATUSES (schemas
appointment.py single source) — invalid status = 422, missing row = 404.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.db.postgres import (
    create_appointment,
    get_appointment,
    list_appointments,
    update_appointment_status,
)
from app.schemas.appointment import (
    APPOINTMENT_STATUSES,
    AppointmentCreate,
    AppointmentStatusUpdate,
)

router = APIRouter(prefix="/api/appointments", tags=["appointments"])


def appointment_row(a) -> dict:
    """Serialize an Appointment ORM row."""
    return {
        "id": str(a.id),
        "clinic_id": str(a.clinic_id),
        "patient_name": a.patient_name,
        "patient_phone": a.patient_phone,
        "patient_language": a.patient_language,
        "caller_id": str(a.caller_id) if a.caller_id else None,
        "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else None,
        "status": a.status,
        "reason": a.reason,
        "doctor_id": str(a.doctor_id) if a.doctor_id else None,
        "duration_minutes": a.duration_minutes,
        "location": a.location,
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
async def list_appointments_ep(
    clinic_id: str,
    status: str = "",
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """List appointments for a clinic, soonest first, optional status/date."""
    cid = _uuid(clinic_id, "clinic_id")
    if status and status not in APPOINTMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    rows = await list_appointments(
        clinic_id=cid,
        status=status or None,
        from_=_parse_dt(from_, "from"),
        to=_parse_dt(to, "to"),
    )
    return [appointment_row(r) for r in rows]


@router.post("", status_code=201)
async def create_appointment_ep(data: AppointmentCreate, user=Depends(get_current_user)):
    """Create an appointment (from call triage or manual booking)."""
    cid = _uuid(data.clinic_id, "clinic_id")
    scheduled = _parse_dt(data.scheduled_at, "scheduled_at")
    if scheduled is None:
        raise HTTPException(status_code=422, detail="scheduled_at required")
    caller_id = _uuid(data.caller_id, "caller_id") if data.caller_id else None
    row = await create_appointment(
        clinic_id=cid,
        patient_name=data.patient_name or None,
        patient_phone=data.patient_phone or None,
        patient_language=data.patient_language,
        caller_id=caller_id,
        scheduled_at=scheduled,
        reason=data.reason or None,
        duration_minutes=data.duration_minutes,
        location=data.location or None,
    )
    return appointment_row(row)


@router.get("/{appointment_id}")
async def get_appointment_ep(appointment_id: str, user=Depends(get_current_user)):
    """Appointment detail."""
    aid = _uuid(appointment_id, "appointment_id")
    row = await get_appointment(aid)
    if row is None:
        raise HTTPException(status_code=404, detail="appointment not found")
    return appointment_row(row)


@router.patch("/{appointment_id}/status")
async def update_appointment_status_ep(
    appointment_id: str,
    data: AppointmentStatusUpdate,
    user=Depends(get_current_user),
):
    """Update appointment status (pending/confirmed/completed/cancelled/no_show)."""
    if data.status not in APPOINTMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {data.status}")
    aid = _uuid(appointment_id, "appointment_id")
    ok = await update_appointment_status(aid, data.status)
    if not ok:
        raise HTTPException(status_code=404, detail="appointment not found")
    return {"appointment_id": str(aid), "status": data.status, "updated": ok}