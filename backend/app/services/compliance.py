"""G6-Q2 compliance module — DPDP breach flow + posture (Q3=A1 / Q4=A1).

The buildable part of the 72-hr breach flow + the localization/DPO posture:

* `COMPLIANCE_EVENT_TYPES` — data_breach / consent_withdrawal / gdpr_request.
* `SEVERITIES` / `STATUSES` — low..critical; open -> reported -> closed.
* `DPDP_BREACH_NOTIFICATION_HOURS` — 72 (DPDP Act 2023); env override
  DPDP_BREACH_NOTIFICATION_HOURS.
* `breach_notification_deadline(detected_at, env)` — detected_at + 72h (tz-
  aware; naive input assumed UTC). Stored on compliance_events.notification_
  deadline at insert; the "overdue" computation an operator reads to trigger
  the actual DPB/affected-user alert (dispatch itself is operational — a Q8
  email-channel follow-on, NOT a new notification kind).
* `data_residency(env)` — documented residency region (DATA_RESIDENCY_REGION,
  default "in"). The actual region pin (docker-compose / provider region /
  zero-retention BAAs) belongs to the Q10 deploy topology session.
* `dpo_contact(env)` — (name, email) from DPO_NAME / DPO_EMAIL.

Stdlib-only leaf (os/datetime/typing).
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

COMPLIANCE_EVENT_TYPES = ("data_breach", "consent_withdrawal", "gdpr_request")
SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("open", "reported", "closed")

# DPDP Act 2023: notify the Data Protection Board + affected users within 72 hr.
DPDP_BREACH_NOTIFICATION_HOURS = 72


def breach_notification_deadline(
    detected_at: datetime, env: Optional[dict] = None, now: Optional[datetime] = None
) -> datetime:
    """detected_at + DPDP_BREACH_NOTIFICATION_HOURS (default 72h), tz-aware.

    Naive input is assumed UTC (TIMESTAMPTZ convention). Bad/empty env values
    fall back to the 72h constant — config can never zero the deadline.
    """
    source = os.environ if env is None else env
    raw = source.get("DPDP_BREACH_NOTIFICATION_HOURS", "")
    try:
        hours = int(raw) if str(raw).strip() else DPDP_BREACH_NOTIFICATION_HOURS
    except (TypeError, ValueError):
        hours = DPDP_BREACH_NOTIFICATION_HOURS
    if detected_at.tzinfo is None:
        detected_at = detected_at.replace(tzinfo=timezone.utc)
    return detected_at + timedelta(hours=hours)


def data_residency(env: Optional[dict] = None) -> str:
    """Documented data-residency region (DATA_RESIDENCY_REGION, default 'in')."""
    source = os.environ if env is None else env
    region = (source.get("DATA_RESIDENCY_REGION") or "in").strip()
    return region or "in"


def dpo_contact(env: Optional[dict] = None) -> Tuple[str, str]:
    """(DPO name, DPO email) from DPO_NAME / DPO_EMAIL ('' when unset)."""
    source = os.environ if env is None else env
    return (source.get("DPO_NAME") or "", source.get("DPO_EMAIL") or "")