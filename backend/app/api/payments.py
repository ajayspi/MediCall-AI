"""Payments API — intent + webhook, gateway SDKs env-gated (G6-Q5 wired).

spec-payments.md (approved 2026-09-25): consultations + prescription refills
bill; the kind->gateway fallback map (razorpay links / phonepe UPI / cashfree
subscriptions) lives in app.services.payments; POST /api/payments/webhook is
verified by the shared X-Service-Token AND the per-gateway signature (Q4/A4a)
and is identity-free by design — gateway callbacks carry no user token. Live
gateway SDK requests fire only when the gateway's env keys are present (501
otherwise; manual stays keyless). This router NEVER imports a gateway SDK.
"""
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.auth import get_current_user
from app.db.postgres import (
    create_notification,
    create_payment,
    find_payment_by_gateway_ref,
    get_appointment,
    get_call,
    get_clinic,
    get_payment,
    list_payments,
    service_request_ctx,
    update_call_state,
    update_payment_status,
)
from app.schemas.payment import (
    PAYMENT_GATEWAYS,
    PAYMENT_STATUSES,
    PaymentCreate,
    PaymentStatusUpdate,
)
from app.services.payments import (
    KIND_TO_GATEWAYS,
    PAYMENT_KINDS,
    detect_gateway,
    dispatch_gateway_request,
    extract_gateway_ref,
    gateway_env_ready,
    next_status,
    verify_webhook_request,
    webhook_status_for,
)
from app.services.notifications import send_notification

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
        "kind": getattr(p, "kind", None),
        "expires_at": (
            p.expires_at.isoformat() if getattr(p, "expires_at", None) else None
        ),
    }


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def _gateway_webhook_secrets(gateway: str):
    """Env secrets for a gateway's webhook verifier, or None if unconfigured."""
    if gateway == "razorpay":
        secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        return {"secret": secret} if secret else None
    if gateway == "phonepe":
        salt = os.environ.get("PHONEPE_SALT_KEY", "")
        return {"salt_key": salt} if salt else None
    if gateway == "cashfree":
        secret = os.environ.get("CASHFREE_WEBHOOK_SECRET", "")
        return {"secret": secret} if secret else None
    return None


async def _send_notification_payment_link(clinic_id, payment_id, appointment_id) -> None:
    """G6-Q8 payment_link leg: deliver the link to the caller's phone.

    The Q5 sign-off requires link/UPI payment URLs to reach the caller's phone;
    Q8 dispatches that through send_notification (WhatsApp-first with SMS/email
    fallback). This is a RECORDED, NON-FATAL side effect (Q3=A3a): a missing
    phone, missing PAYMENT_LINK_BASE_URL, or absent channel keys must never
    fail or 501 the payment create — the row is written with status=queued.
    """
    try:
        appt = await get_appointment(appointment_id) if appointment_id else None
        phone = (appt.patient_phone or "").strip() if appt else ""
        base = os.environ.get("PAYMENT_LINK_BASE_URL", "").rstrip("/")
        if not phone or not base:
            return
        clinic = await get_clinic(clinic_id)
        clinic_name = clinic.name if clinic else "MediCall"
        lang = (appt.patient_language or "en") if appt else "en"
        url = f"{base}/pay/{payment_id}"
        result = send_notification(
            "payment_link",
            phone,
            lang,
            {"url": url, "clinic": clinic_name},
            env=os.environ,
        )
        async with service_request_ctx():
            await create_notification(
                clinic_id=clinic_id,
                kind="payment_link",
                recipient=phone,
                language=lang,
                params=json.dumps({"url": url, "clinic": clinic_name}),
                channel=result["channel"],
                provider=result["provider"],
                status=result["status"],
                template=result["message"],
            )
    except Exception:
        # Best-effort side effect — swallow (never break the payment response).
        pass


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
    """Create a payment intent — env-gated gateway dispatch (Q5/A5a).

    `manual` (offline/dev invoices) is always allowed keyless. razorpay /
    phonepe / cashfree answer 501 when their env keys are absent (mirrors the
    SSO/telephony pattern) so the contract surface is live and the SDK request
    only fires on a configured host; kind must map to the gateway per A2a.
    """
    cid = _uuid(data.clinic_id, "clinic_id")
    if data.gateway not in PAYMENT_GATEWAYS:
        raise HTTPException(status_code=422, detail=f"invalid gateway: {data.gateway}")
    if data.kind not in PAYMENT_KINDS:
        raise HTTPException(status_code=422, detail=f"invalid kind: {data.kind}")
    if data.gateway != "manual" and data.gateway not in KIND_TO_GATEWAYS.get(data.kind, ()):
        raise HTTPException(
            status_code=422,
            detail=f"gateway {data.gateway} not valid for kind {data.kind}",
        )
    if data.gateway != "manual" and not gateway_env_ready(data.gateway):
        raise HTTPException(status_code=501, detail=f"gateway {data.gateway} not configured")
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
        kind=data.kind,
    )
    if data.gateway != "manual":
        result = dispatch_gateway_request(data.gateway, data.kind, row)
        if result is None:
            raise HTTPException(
                status_code=502, detail=f"gateway {data.gateway} request failed"
            )
    if data.kind in ("link", "upi"):
        # G6-Q8 payment_link leg: dispatch to the caller's phone (non-fatal).
        await _send_notification_payment_link(cid, row.id, appointment_id)
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


@router.post("/webhook")
async def payments_webhook(request: Request):
    """Gateway -> server webhook (identity-free by design, Q4/A4a).

    Verified by the shared X-Service-Token (WEBHOOK_SERVICE_TOKEN) AND the
    per-gateway signature (X-Razorpay-Signature / X-VERIFY /
    X-Verify-Hmac-Sha256). Writes run under service_request_ctx() because
    auth.uid() is NULL here — payments_manage carries the app.service_request
    bypass clause. Idempotent by gateway_ref (uq_payments_gateway_ref): a
    replayed webhook updates the same row. On captured, the linked call in
    PAYMENT_SENT advances to COMPLETE (the Q3/A3a loop).
    """
    token = request.headers.get("X-Service-Token", "")
    if token != os.environ.get("WEBHOOK_SERVICE_TOKEN", "dev-service-token"):
        raise HTTPException(status_code=401, detail="invalid service token")
    raw = await request.body()
    try:
        payload = json.loads(raw.decode()) if raw else {}
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="invalid JSON body")
    gateway = str(payload.get("gateway", "") or detect_gateway(payload)).lower()
    if gateway not in PAYMENT_GATEWAYS or gateway == "manual":
        raise HTTPException(status_code=422, detail=f"invalid gateway: {gateway}")
    secrets = _gateway_webhook_secrets(gateway)
    if secrets is None:
        raise HTTPException(status_code=503, detail=f"gateway {gateway} not configured")
    if not verify_webhook_request(gateway, raw, request.headers, secrets):
        raise HTTPException(status_code=401, detail=f"invalid {gateway} signature")
    ref = extract_gateway_ref(gateway, payload)
    incoming = webhook_status_for(gateway, payload)
    if not ref:
        raise HTTPException(status_code=422, detail="no gateway_ref in payload")
    async with service_request_ctx():
        row = await find_payment_by_gateway_ref(gateway, ref)
        if row is None:
            raise HTTPException(status_code=404, detail="payment intent not found")
        nxt = next_status(row.status, incoming)
        if nxt != row.status:
            await update_payment_status(row.id, nxt)
        if nxt == "captured" and row.call_id:
            call = await get_call(row.call_id)
            if call is not None and call.state == "PAYMENT_SENT":
                await update_call_state(row.call_id, "COMPLETE")
    return {
        "status": "ok",
        "gateway": gateway,
        "gateway_ref": ref,
        "payment_status": nxt,
    }