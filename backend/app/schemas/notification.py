"""Notification request models + kind single source (G6-Q8 answered).

spec-notifications-q8.md (approved 2026-09-25): WhatsApp-first multi-channel
layer (whatsapp/sms/email/push); the manual POST /api/notifications/send
endpoint 501s without any channel keys; upstream hooks (the payment-create
payment_link leg) are non-fatal and record status=queued instead.
"""

from pydantic import BaseModel

NOTIFICATION_KINDS = (
    "payment_link",
    "appointment_reminder",
    "no_show_followup",
    "otp",
    "payment_receipt",
)


class NotificationSend(BaseModel):
    clinic_id: str
    kind: str
    recipient: str  # phone for whatsapp/sms/push; email address for email
    language: str = "en"  # hi / en / ta / te / bn
    params: dict = {}


class NotificationStatusUpdate(BaseModel):
    status: str