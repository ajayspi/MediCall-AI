"""MVP KPI analytics — pure shaping + rate math (spec-kpis-q9.md G6-Q9).

The DB layer returns raw aggregates; every derived number (rates, averages,
period windows) lives here so the contract is testable without a database.
Sign-off 2026-09-25 (question tool): Q1=A3 seven KPIs incl. notification
delivery success; Q2=A2 per-KPI endpoints; Q3=A1 pure computed — zero schema
writes, reads ride existing RLS; Q4=A1 optional from/to with a 30-day default
and 366-day cap, naive inputs assumed UTC.

Import roots restricted to the stdlib {datetime, collections, typing} — the
strict-leaf gate the RED suite enforces.
"""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Optional

DEFAULT_PERIOD_DAYS = 30
PERIOD_MAX_DAYS = 366

# Market context cards — display-only constants, never enforced thresholds.
# 2026 sources: Hyro 2026 AI Agent Benchmark Report (human FCR 70-79%);
# Interactly benchmark (spec-multifit-healthcare.md): 72% of requests resolved
# without front-desk; Caller Digital / Haptik / Ukti India no-show data
# (baseline 18-25% -> voice-reminder target 8-12%; reminder confirmation
# 75-85%). The dashboard renders these as "vs benchmark" reference cards.
BENCHMARKS: dict = {
    "resolution": {
        "human_fcr_pct": [70, 79],
        "interactly_virtual_receptionist_pct": 72,
    },
    "no_show": {
        "india_baseline_pct": [18, 25],
        "voice_reminder_target_pct": [8, 12],
    },
    "confirmation": {
        "voice_reminder_confirmation_pct": [75, 85],
    },
    "sources": [
        "Hyro 2026 AI Agent Benchmark Report",
        "Interactly benchmark (spec-multifit-healthcare.md)",
        "Caller Digital India no-show analysis 2026",
        "Haptik voice-AI healthcare benchmarks 2026",
        "Ukti AI healthcare voice-agent outcomes 2026",
    ],
}


def _parse(value, what: str) -> datetime:
    """ISO-8601 date/datetime -> tz-aware datetime; naive assumed UTC."""
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            raise ValueError(f"invalid {what}: {value!r}") from None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def resolve_period(from_=None, to=None, now=None):
    """(from_dt, to_dt) for a KPI window.

    Defaults: to = now, from = to - 30 days. Raises ValueError on from > to,
    a window wider than 366 days, or unparseable input (router maps it to
    422). Naive datetimes are assumed UTC (same rule as retention).
    """
    now = now or datetime.now(timezone.utc)
    to_dt = _parse(to, "to") if to is not None else now
    from_dt = (
        _parse(from_, "from")
        if from_ is not None
        else to_dt - timedelta(days=DEFAULT_PERIOD_DAYS)
    )
    if from_dt > to_dt:
        raise ValueError("from must not be after to")
    if (to_dt - from_dt) > timedelta(days=PERIOD_MAX_DAYS):
        raise ValueError(f"period exceeds {PERIOD_MAX_DAYS} days")
    return from_dt, to_dt


def resolution_rate(
    completed: int, dropped: int, escalated: int, payment_expired: int
) -> Optional[float]:
    """Share of terminal calls that reached COMPLETE; None when none exist.

    Terminal outcomes are COMPLETE + DROPPED + ESCALATED + PAYMENT_EXPIRED.
    PAYMENT_SENT is in-progress (the webhook advances it to COMPLETE), so it
    is deliberately excluded from the denominator.
    """
    terminal = completed + dropped + escalated + payment_expired
    if terminal <= 0:
        return None
    return completed / terminal


def no_show_rate(no_show: int, completed: int, cancelled: int) -> Optional[float]:
    """Share of terminal appointments that were no-shows; None when none."""
    terminal = no_show + completed + cancelled
    if terminal <= 0:
        return None
    return no_show / terminal


def success_rate(sent: int, failed: int) -> Optional[float]:
    """Delivery success share; None when no sent/failed rows exist."""
    total = sent + failed
    if total <= 0:
        return None
    return sent / total


def shape_volume(raw: dict) -> dict:
    """raw {total, by_state, by_day, duration_sum, duration_count} -> payload."""
    count = int(raw.get("duration_count") or 0)
    total = int(raw.get("duration_sum") or 0)
    avg = round(total / count, 2) if count else None
    return {
        "total": raw.get("total", 0),
        "by_state": raw.get("by_state", {}),
        "by_day": raw.get("by_day", {}),
        "avg_duration_seconds": avg,
    }


def shape_delivery(raw: dict) -> dict:
    """raw {kind: {sent, failed}} -> {kind: {sent, failed, total, success_rate}}.

    Kind-ordered (OrderedDict) so the payload is stable across responses.
    """
    out: OrderedDict = OrderedDict()
    for kind, counts in sorted(raw.items()):
        sent = int(counts.get("sent") or 0)
        failed = int(counts.get("failed") or 0)
        out[kind] = {
            "sent": sent,
            "failed": failed,
            "total": sent + failed,
            "success_rate": success_rate(sent, failed),
        }
    return out