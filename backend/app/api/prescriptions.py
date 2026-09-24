"""Prescriptions API — list/create/detail/status (API routes phase).

Status transitions are validated against PRESCRIPTION_STATUSES (schemas
prescription.py single source) — invalid status = 422, missing row = 404.
"""
import uuid

from fastapi import APIRouter, HTTPException

from app.db.postgres import (
    create_prescription,
    get_prescription,
    list_prescriptions,
    update_prescription_status,
)
from app.schemas.prescription import (
    PRESCRIPTION_STATUSES,
    PrescriptionCreate,
    PrescriptionStatusUpdate,
)

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


def prescription_row(p) -> dict:
    """Serialize a Prescription ORM row."""
    return {
        "id": str(p.id),
        "clinic_id": str(p.clinic_id),
        "patient_name": p.patient_name,
        "patient_phone": p.patient_phone,
        "patient_language": p.patient_language,
        "caller_id": str(p.caller_id) if p.caller_id else None,
        "medication": p.medication,
        "dosage": p.dosage,
        "frequency": p.frequency,
        "instructions": p.instructions,
        "doctor_id": str(p.doctor_id) if p.doctor_id else None,
        "status": p.status,
        "pharmacy_name": p.pharmacy_name,
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


@router.get("")
async def list_prescriptions_ep(clinic_id: str, status: str = ""):
    """List prescriptions for a clinic, optional status filter."""
    cid = _uuid(clinic_id, "clinic_id")
    if status and status not in PRESCRIPTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    rows = await list_prescriptions(clinic_id=cid, status=status or None)
    return [prescription_row(r) for r in rows]


@router.post("", status_code=201)
async def create_prescription_ep(data: PrescriptionCreate):
    """Create a prescription (from call triage or doctor review)."""
    cid = _uuid(data.clinic_id, "clinic_id")
    caller_id = _uuid(data.caller_id, "caller_id") if data.caller_id else None
    row = await create_prescription(
        clinic_id=cid,
        patient_name=data.patient_name or None,
        patient_phone=data.patient_phone or None,
        patient_language=data.patient_language,
        medication=data.medication,
        dosage=data.dosage or None,
        frequency=data.frequency or None,
        instructions=data.instructions or None,
        caller_id=caller_id,
        pharmacy_name=data.pharmacy_name or None,
    )
    return prescription_row(row)


@router.get("/{prescription_id}")
async def get_prescription_ep(prescription_id: str):
    """Prescription detail."""
    pid = _uuid(prescription_id, "prescription_id")
    row = await get_prescription(pid)
    if row is None:
        raise HTTPException(status_code=404, detail="prescription not found")
    return prescription_row(row)


@router.patch("/{prescription_id}/status")
async def update_prescription_status_ep(
    prescription_id: str, data: PrescriptionStatusUpdate
):
    """Update prescription status (pending/approved/sent_pharmacy/dispensed)."""
    if data.status not in PRESCRIPTION_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {data.status}")
    pid = _uuid(prescription_id, "prescription_id")
    ok = await update_prescription_status(pid, data.status)
    if not ok:
        raise HTTPException(status_code=404, detail="prescription not found")
    return {"prescription_id": str(pid), "status": data.status, "updated": ok}