"""Payments API — scaffold only (API routes phase).

G6-Q5 (which flows pay / which gateway per flow) is still OPEN: this router
records payment intent only — it NEVER calls a gateway SDK. Gateways are
razorpay / phonepe / cashfree / manual (PAYMENT_GATEWAYS in app.schemas.payment);
statuses (pending / captured / failed / refunded) match the gateways' webhook
states so the table survives the Q5 decision.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.db.postgres import create_payment, get_payment, list_payments, update_payment_status
from app.schemas.payment import (
    PAYMENT_GATEWAYS,
    PAYMENT_STATUSES,
    PaymentCreate,
    PaymentStatusUpdate,
)

router = APIRouter(prefix="/api/payments", tags=["payments"])


def payment_row(p) -> dict:
    """Serialize a Payment ORM row."""
    return {
        "id": str(p.id),
        "clinic_id": str(p.clinic_id),
        "call_id": str(p.call_id) if p.call_id else None,
        "appointment_id": str(p.appointment_id) if p.appointment_id else None,
        "amount": float(p.amount) if p.amount is not None else None,
        "currency": p.currency,
        "gateway": p.gateway,
        "gateway_ref": p.gateway_ref,
        "status": p.status,
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


@router.get("")
async def list_payments_ep(
    clinic_id: str, status: str = "", user=Depends(get_current_user)
):
    """List payments for a clinic, newest first, optional status filter."""
    cid = _uuid(clinic_id, "clinic_id")
    if status and status not in PAYMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {status}")
    rows = await list_payments(clinic_id=cid, status=status or None)
    return [payment_row(r) for r in rows]


@router.post("", status_code=201)
async def create_payment_ep(data: PaymentCreate, user=Depends(get_current_user)):
    """Record a payment intent (scaffold — no gateway SDK call, G6-Q5)."""
    cid = _uuid(data.clinic_id, "clinic_id")
    if data.gateway not in PAYMENT_GATEWAYS:
        raise HTTPException(status_code=422, detail=f"invalid gateway: {data.gateway}")
    call_id = _uuid(data.call_id, "call_id") if data.call_id else None
    appointment_id = (
        _uuid(data.appointment_id, "appointment_id") if data.appointment_id else None
    )
    row = await create_payment(
        clinic_id=cid,
        call_id=call_id,
        appointment_id=appointment_id,
        amount=data.amount,
        currency=data.currency or "INR",
        gateway=data.gateway,
        gateway_ref=data.gateway_ref or None,
    )
    return payment_row(row)


@router.get("/{payment_id}")
async def get_payment_ep(payment_id: str, user=Depends(get_current_user)):
    """Payment detail."""
    pid = _uuid(payment_id, "payment_id")
    row = await get_payment(pid)
    if row is None:
        raise HTTPException(status_code=404, detail="payment not found")
    return payment_row(row)


@router.patch("/{payment_id}/status")
async def update_payment_status_ep(
    payment_id: str, data: PaymentStatusUpdate, user=Depends(get_current_user)
):
    """Update payment status (pending/captured/failed/refunded)."""
    if data.status not in PAYMENT_STATUSES:
        raise HTTPException(status_code=422, detail=f"invalid status: {data.status}")
    pid = _uuid(payment_id, "payment_id")
    ok = await update_payment_status(pid, data.status)
    if not ok:
        raise HTTPException(status_code=404, detail="payment not found")
    return {"payment_id": str(pid), "status": data.status, "updated": ok}