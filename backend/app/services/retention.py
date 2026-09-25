"""G6-Q2 retention module — data retention policy (Q2=A1).

The DPDP/HIPAA-equivalent posture (spec-multifit-healthcare.md): audit logs
retained 6 yr, operational records shorter. This module is the single source
for how long each category of data lives:

* `RETENTION_DAYS` — calls 365, recordings 365, notifications 180, audit 2190
  (6 yr; compliance_events rows are the audit category).
* `RETENTION_ENV_KEYS` — per-kind env override names
  (RETENTION_CALLS_DAYS / RETENTION_RECORDINGS_DAYS /
  RETENTION_NOTIFICATIONS_DAYS / RETENTION_AUDIT_DAYS).
* `retention_days(kind, env)` — effective days for a kind (env override wins;
  invalid/empty falls back to the constant).
* `retention_deadline(created_at, kind, env)` — the tz-aware cutoff a row must
  be purged after.
* `retention_categories()` — the ordered kind tuple.

`postgres.purge_expired` consumes this: DELETE rows whose created_at is past
the deadline, driven by the Docker/CI scheduler cron (execution deferred —
nothing auto-runs on this PC). "recordings" are external MinIO/S3 objects
(LiveKit egress), so their retention is a documented posture constant here;
the object-purge job is a Docker follow-on.

Stdlib-only leaf (os/datetime/typing).
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

# Days-per-category (audit = 2190 = 6 yr per DPDP/HIPAA-equivalent).
RETENTION_DAYS = {"calls": 365, "recordings": 365, "notifications": 180, "audit": 2190}

# Per-kind env override names (documented in .env.example).
RETENTION_ENV_KEYS = {
    "calls": "RETENTION_CALLS_DAYS",
    "recordings": "RETENTION_RECORDINGS_DAYS",
    "notifications": "RETENTION_NOTIFICATIONS_DAYS",
    "audit": "RETENTION_AUDIT_DAYS",
}


def retention_categories() -> Tuple[str, ...]:
    """The ordered retention categories (calls, recordings, notifications, audit)."""
    return tuple(RETENTION_DAYS.keys())


def retention_days(kind: str, env: Optional[dict] = None) -> int:
    """Effective retention days for a kind — env override, else the constant."""
    source = os.environ if env is None else env
    raw = source.get(RETENTION_ENV_KEYS.get(kind, ""), "")
    try:
        return int(raw) if str(raw).strip() else RETENTION_DAYS[kind]
    except (TypeError, ValueError, KeyError):
        return RETENTION_DAYS[kind]


def retention_deadline(
    created_at: datetime, kind: str, env: Optional[dict] = None, now: Optional[datetime] = None
) -> datetime:
    """Tz-aware cutoff: a `kind` row older than this is past retention.

    Naive input is assumed UTC (this app stores TIMESTAMPTZ). `now` is
    accepted for symmetric clocking with purge_expired but unused in the math
    (deadline is purely created_at + days).
    """
    days = retention_days(kind, env=env)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at + timedelta(days=days)