"""Payment request models + gateway/status single source (G6-Q5 answered).

spec-payments.md (approved 2026-09-25): consultations + prescription refills
bill; kind -> gateway map lives in app.services.payments (razorpay=links,
phonepe=UPI fallback, cashfree=subscriptions); webhooks verify per-gateway HMAC
+ the shared service token; live SDK calls stay env-gated (501 without keys).
The router records intent and dispatches the gateway request only when the
gateway's env keys are present — it never imports an SDK.
"""
from pydantic import BaseModel

PAYMENT_GATEWAYS = ("razorpay", "phonepe", "cashfree", "manual")
PAYMENT_STATUSES = ("pending", "captured", "failed", "refunded")


class PaymentCreate(BaseModel):
    clinic_id: str
    call_id: str = ""
    appointment_id: str = ""
    amount: float
    currency: str = "INR"
    gateway: str = "manual"
    gateway_ref: str = ""
    kind: str = "consultation"  # consultation / refill / subscription


class PaymentStatusUpdate(BaseModel):
    status: str