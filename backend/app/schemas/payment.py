"""Payment request models + gateway/status single source (scaffold, G6-Q5).

G6-Q5 (which flows pay / which gateway per flow) is still open: the router
records intent only and never calls a gateway SDK. The gateway set matches
the G5 requirements pins (razorpay / phonepe-pg-sdk / cashfree-pg) + manual;
statuses match Razorpay/PhonePe/Cashfree webhook states so the table survives
the Q5 decision.
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


class PaymentStatusUpdate(BaseModel):
    status: str