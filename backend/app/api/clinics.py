"""Clinics API — admin clinic management + clinic settings (API routes phase).

Serves the admin clinics list and the clinic Settings page: list, create,
get, and partial settings update (PATCH applies only sent fields via
ClinicUpdate + exclude_unset).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user, require_roles
from app.db.postgres import create_clinic, get_clinic, list_clinics, update_clinic
from app.schemas.clinic import ClinicCreate, ClinicUpdate

router = APIRouter(prefix="/api/clinics", tags=["clinics"])

# Editable settings fields, mirrored by ClinicUpdate (kept here for the row
# serializer + update_clinic whitelist in postgres.py).
SETTING_FIELDS = (
    "name",
    "phone_number",
    "address",
    "city",
    "state",
    "pincode",
    "closing_time",
    "ai_instructions",
    "plan",
    "is_active",
)


def clinic_row(c) -> dict:
    """Serialize a Clinic ORM row to the API response shape."""
    return {
        "id": str(c.id),
        "name": c.name,
        "phone_number": c.phone_number,
        "address": c.address,
        "city": c.city,
        "state": c.state,
        "pincode": c.pincode,
        "latitude": c.latitude,
        "longitude": c.longitude,
        "closing_time": c.closing_time,
        "ai_instructions": c.ai_instructions,
        "plan": c.plan,
        "is_active": c.is_active,
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


@router.get("")
async def list_clinics_ep(is_active: bool = True, user=Depends(get_current_user)):
    """List clinics, active by default (admin clinics page).

    RLS scopes the rows to the caller's clinic memberships.
    """
    rows = await list_clinics(active_only=is_active)
    return [clinic_row(r) for r in rows]


@router.post("", status_code=201)
async def create_clinic_ep(data: ClinicCreate, user=Depends(require_roles("owner"))):
    """Create a clinic (platform owner only) — the creator becomes its owner."""
    row = await create_clinic(
        name=data.name,
        phone_number=data.phone_number,
        city=data.city,
        state=data.state,
        address=data.address or None,
        pincode=data.pincode or None,
        closing_time=data.closing_time,
        ai_instructions=data.ai_instructions,
        plan=data.plan,
        is_active=data.is_active,
        owner_user_id=user.id,
    )
    return clinic_row(row)


@router.get("/{clinic_id}")
async def get_clinic_ep(clinic_id: str, user=Depends(get_current_user)):
    """Clinic detail + settings (clinic Settings page)."""
    cid = _uuid(clinic_id, "clinic_id")
    row = await get_clinic(cid)
    if row is None:
        raise HTTPException(status_code=404, detail="clinic not found")
    return clinic_row(row)


@router.patch("/{clinic_id}")
async def update_clinic_ep(
    clinic_id: str, data: ClinicUpdate, user=Depends(get_current_user)
):
    """Partial settings update — only the fields the client sent."""
    cid = _uuid(clinic_id, "clinic_id")
    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")
    row = await update_clinic(cid, **updates)
    if row is None:
        raise HTTPException(status_code=404, detail="clinic not found")
    return clinic_row(row)