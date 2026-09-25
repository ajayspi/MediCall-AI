"""Notifications API — manual send + list, env-gated channels (G6-Q8 wired).

spec-notifications-q8.md (approved 2026-09-25): the messaging layer is
WhatsApp-first with SMS/email fallback chains per kind (Q1=A1c). This router
is identity-gated like every domain endpoint; POST /send 501s when no channel
has keys (Q3=A3a — same env-gate discipline as gateway dispatch); with keys it
dispatches through the kind's DEFAULT_CHANNEL_ORDER. Rows are recorded as
`notifications` (Q4=A4a) so the DPDP audit (G6-Q2) has a delivery trail.
"""
import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.db.postgres import create_notification, list_notifications
from app.schemas.notification import NOTIFICATION_KINDS, NotificationSend
from app.services.notifications import (
    SUPPORTED_LANGUAGES,
    send_notification,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def notification_row(n) -> dict:
    """Serialize a Notification ORM row."""
    return {
        "id": str(n.id),
        "clinic_id": str(n.clinic_id),
        "kind": n.kind,
        "recipient": n.recipient,
        "language": n.language,
        "channel": n.channel,
        "provider": n.provider,
        "provider_ref": n.provider_ref,
        "status": n.status,
        "template": n.template,
        "created_at": n.created_at.isoformat() if getattr(n, "created_at", None) else None,
    }


@router.get("")
async def list_notifications_ep(
    clinic_id: str, status: str = "", user=Depends(get_current_user)
):
    """List notifications for a clinic, newest first, optional status filter."""
    cid = _uuid(clinic_id, "clinic_id")
    rows = await list_notifications(clinic_id=cid, status=status or None)
    return [notification_row(r) for r in rows]


@router.post("/send", status_code=201)
async def send_notification_ep(data: NotificationSend, user=Depends(get_current_user)):
    """Send one notification (manual/operator trigger, G6-Q8).

    501 without any channel keys (Q3=A3a env gate — the record is still
    written with status queued so the audit trail exists); with keys it walks
    the kind's DEFAULT_CHANNEL_ORDER and dispatches through the first ready
    channel. Writes happen under service_request_ctx() semantics via the
    notifications_send policy (membership OR service bypass).
    """
    cid = _uuid(data.clinic_id, "clinic_id")
    if data.kind not in NOTIFICATION_KINDS:
        raise HTTPException(status_code=422, detail=f"invalid kind: {data.kind}")
    if data.language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=422, detail=f"invalid language: {data.language}")
    result = send_notification(
        data.kind, data.recipient, data.language, data.params, env=os.environ
    )
    if result["status"] == "queued" and result["reason"] == "no_provider":
        # Nothing to send yet — record the attempt and answer 501 (gate parity
        # with payments: dispatch without keys is an explicit 501).
        row = await create_notification(
            clinic_id=cid,
            kind=data.kind,
            recipient=data.recipient,
            language=data.language,
            params=json.dumps(data.params, ensure_ascii=False),
            channel=result["channel"],
            provider=result["provider"],
            status="queued",
            template=result["message"],
        )
        raise HTTPException(
            status_code=501, detail="no notification channel configured"
        ) from None
    row = await create_notification(
        clinic_id=cid,
        kind=data.kind,
        recipient=data.recipient,
        language=data.language,
        params=json.dumps(data.params, ensure_ascii=False),
        channel=result["channel"],
        provider=result["provider"],
        status=result["status"],
        template=result["message"],
        provider_ref=result.get("provider_ref"),
    )
    return notification_row(row)