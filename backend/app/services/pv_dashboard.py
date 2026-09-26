"""PVOIC compliance dashboard (spec-micc-pv-phase2.md slice 2E) - PURE logic.

A STDLIB-ONLY leaf (calendar / datetime / math / typing), the same shape as
app/services/pharmacovigilance.py and app/services/e2b.py: it takes rows that
have ALREADY been fetched and assembles the compliance numbers, so every
figure is unit-testable with no database, no FastAPI and no network. The
/api/pv router fetches through the existing repository helpers and passes the
rows in; nothing here knows about HTTP, SQLAlchemy or sessions.

WHAT THIS IS: a read-only view of what the PVOIC must act on today -
case counts, the India-clock countdown with overdue red flags, the complaint
pipeline, the PSUR calendar and the recent audit trail. It is a VIEW, never a
decision: it reports status, deadlines and counts, and the officer judges
causality, coding and submission, exactly as in Phase 1.

THE CLOCK IS NOT RE-DERIVED HERE. compute_reporting_deadline() is imported
from the Phase-1 module and is the single definition of the 15/90-day India
clocks; this module only measures the countdown from the case's legal
notification_deadline (the value written at intake by that same function, and
the record a regulator submission would cite).

PSUR (research-micc-process.md 3.3, D&C Act / NDCT 2019): every 6 months for
the first 2 years from approval, then annually for the next 2 years. After the
fourth year the obligation continues under a different reporting model that is
OUT of this module's scope, so the schedule says "N/A" rather than inventing a
cadence the guidance does not state here.

DETERMINISM: every list is sorted on a stable key and every mapping is
key-sorted, so the same rows always produce byte-identical JSON - which is what
makes a snapshot something you can diff between two days.
"""

import calendar
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.services.pharmacovigilance import (
    PQC_STATUSES,
    classify_seriousness,
    compute_reporting_deadline,
)

# ─── Catalogs ───────────────────────────────────────────────────────────────

# An AE case is ACTIONABLE (open) until it has been notified, submitted or
# closed. An overdue case is a flag on an open case, never a status: a case
# reported late is a fact, and the officer's own status is what they set.
TERMINAL_CASE_STATUSES = ("notified", "submitted", "closed")
KNOWN_CASE_STATUSES = ("new", "open") + TERMINAL_CASE_STATUSES

# The compliance_events types this module owns. The PV trail is reconstructable
# from these rows alone (Phase-1 contract), so a DPDP event on the same table
# (data_breach, consent_withdrawal) is deliberately NOT counted here.
PV_AUDIT_TYPE_PREFIXES = ("pv", "pqc")

# A case due inside the next two days is what a PVOIC works TODAY; the horizon
# is inclusive, so a case due in exactly 48h still shows as upcoming.
UPCOMING_HORIZON_HOURS = 48
AUDIT_WINDOW_DAYS = 7
AUDIT_MAX_DAYS = 365

# PSUR windows in months from approval, with their cadence. Index is 1-based so
# the label reads the way the guidance does ("6-monthly #3", "annual #5").
PSUR_WINDOWS: Tuple[Tuple[int, str], ...] = (
    (6, "6-monthly"),
    (12, "6-monthly"),
    (18, "6-monthly"),
    (24, "6-monthly"),
    (36, "annual"),
    (48, "annual"),
)
PSUR_SCHEDULE_LABEL = "6-monthly x2y, then annual x2y"
# The anchor in this slice: products carry no approval-date column, so the PSUR
# calendar counts from when the product entered the dictionary. Documented on
# the payload so a reader never mistakes it for a regulatory approval date.
PSUR_ANCHOR_FIELD = "created_at"
PSUR_NO_WINDOW = "N/A"


# ─── Row / value helpers (ORM row or dict, datetime or ISO string) ─────────
def _get(row: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict OR an ORM row, without importing SQLAlchemy."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _status(row: Any) -> str:
    return _text(_get(row, "status")).strip().lower()


def _is_open(status: str) -> bool:
    return status not in TERMINAL_CASE_STATUSES


def _as_aware(value: Optional[datetime]) -> Optional[datetime]:
    """Naive datetimes are treated as UTC - the Phase-1 convention."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _as_dt(value: Any) -> Optional[datetime]:
    """datetime / ISO string / None -> aware datetime (unparseable -> None)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _as_aware(value)
    if isinstance(value, date):
        return _as_aware(datetime(value.year, value.month, value.day))
    try:
        return _as_aware(datetime.fromisoformat(str(value)))
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> Optional[date]:
    moment = _as_dt(value)
    return moment.date() if moment is not None else None


def _iso(value: Any) -> str:
    moment = _as_dt(value)
    return moment.isoformat() if moment is not None else ""


def _reference(now: Optional[datetime]) -> datetime:
    """The clock this snapshot is taken at; a caller-supplied `now` wins."""
    return _as_aware(now) or datetime.now(timezone.utc)


def _days_remaining(deadline: datetime, now: datetime) -> int:
    """Whole days from `now` to `deadline`, rounded UP.

    The same convention compute_reporting_deadline uses (0 on the deadline day,
    negative once overdue), so the countdown on a case, on the queue and on the
    dashboard can never disagree by a day.
    """
    return int(math.ceil((deadline - now).total_seconds() / 86400.0))


def _count_by(rows: Sequence[Any], key: str) -> Dict[str, int]:
    """Sorted {value: count} for a text field, skipping blank values."""
    counts: Dict[str, int] = {}
    for row in rows or ():
        value = _text(_get(row, key)).strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {name: counts[name] for name in sorted(counts)}


# ─── The India clock, reused ────────────────────────────────────────────────
def case_clock(row: Any, now: datetime) -> Optional[Dict[str, Any]]:
    """The countdown for one case, from the Phase-1 clock.

    The deadline is the case's own notification_deadline when stored (the legal
    record) and the clock's value otherwise; days_remaining is measured from
    that deadline with the clock's own rounding. Returns None for a row with
    no day zero, which has no clock to count - an incomplete case must never
    fabricate one.
    """
    received = _as_dt(_get(row, "received_at"))
    if received is None:
        return None

    serious, _criteria = classify_seriousness(_get(row, "seriousness_flags"))
    computed, _days = compute_reporting_deadline(serious, received, now=now)
    stored = _as_dt(_get(row, "notification_deadline"))
    deadline = stored if stored is not None else computed

    return {
        "case_id": _text(_get(row, "id")),
        "status": _status(row),
        "is_serious": serious,
        "notification_deadline": deadline.isoformat(),
        "days_remaining": _days_remaining(deadline, now),
    }


# ─── PSUR calendar ──────────────────────────────────────────────────────────
def _add_months(anchor: date, months: int) -> date:
    """Calendar-month arithmetic, clamped at the month end (31 Jan + 6m = 31 Jul).

    The guidance says "6 months from approval", which is a calendar statement:
    a 30-day block would drift the deadline by a day per window.
    """
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def psur_schedule(anchor: Any) -> List[Dict[str, Any]]:
    """The full PSUR window list for an anchor date, oldest first."""
    start = _as_date(anchor)
    if start is None:
        return []
    windows = []
    for index, (months, cadence) in enumerate(PSUR_WINDOWS, start=1):
        due = _add_months(start, months)
        windows.append(
            {
                "index": index,
                "cadence": cadence,
                "label": f"{cadence} #{index}",
                "months_after_anchor": months,
                "due_date": due.isoformat(),
            }
        )
    return windows


def psur_next_window(anchor: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The next PSUR window for an anchor, and whether a window is open now.

    due_now is TRUE when a submission window is OPEN: the most recent window's
    due date has arrived and a later one has not, or today is the final
    window's own day. That is the compliance reading - a period whose report is
    owed. It is False when the next window has not opened yet, and False once
    the schedule has ended (past the fourth year), where the obligation moves
    to a reporting model this module does not model and says N/A.
    """
    reference = _reference(now)
    start = _as_date(anchor)
    result: Dict[str, Any] = {
        "anchor": start.isoformat() if start is not None else None,
        "age_days": None,
        "due_now": False,
        "next": None,
        "next_label": PSUR_NO_WINDOW,
        "next_due_date": None,
        "days_remaining": None,
    }
    if start is None:
        return result

    result["age_days"] = (reference.date() - start).days
    windows = psur_schedule(start)
    if not windows:
        return result

    today = reference.date()
    dates = [_as_date(w["due_date"]) for w in windows]
    pending = [w for w, due in zip(windows, dates) if due > today]
    if pending:
        upcoming = pending[0]
        result["next"] = upcoming
        result["next_label"] = upcoming["label"]
        result["next_due_date"] = upcoming["due_date"]
        result["days_remaining"] = (_as_date(upcoming["due_date"]) - today).days
    result["due_now"] = any(due <= today for due in dates) and (
        bool(pending) or today <= dates[-1]
    )
    return result


def build_psur_schedule(products: Any, now: Optional[datetime] = None) -> Dict[str, Any]:
    """The PSUR schedule for a product dictionary, sorted by product name.

    Inactive products are excluded: a withdrawn product's calendar is not a
    live compliance obligation and must not put a false red on the dashboard.
    """
    reference = _reference(now)
    entries = []
    for product in products or ():
        if _get(product, "is_active") is False:
            continue
        window = psur_next_window(_get(product, PSUR_ANCHOR_FIELD), now=reference)
        entries.append(
            {
                "product_id": _text(_get(product, "id")),
                "product_name": _text(_get(product, "name")),
                "anchor": window["anchor"],
                "anchor_field": PSUR_ANCHOR_FIELD,
                "age_days": window["age_days"],
                "due_now": window["due_now"],
                "next_window": window["next_label"],
                "next_due_date": window["next_due_date"],
                "days_remaining": window["days_remaining"],
            }
        )
    entries.sort(key=lambda e: (e["product_name"], e["product_id"]))
    return {
        "schedule": PSUR_SCHEDULE_LABEL,
        "anchor_field": PSUR_ANCHOR_FIELD,
        "products": len(entries),
        "due_now": sum(1 for e in entries if e["due_now"]),
        "entries": entries,
    }


# ─── Audit trail ────────────────────────────────────────────────────────────
def is_pv_audit_event(event_type: Any) -> bool:
    """True for the compliance_events types the PV module itself writes."""
    return _text(event_type).strip().lower().startswith(PV_AUDIT_TYPE_PREFIXES)


def build_audit_trail(events: Any, days: int = AUDIT_WINDOW_DAYS,
                      now: Optional[datetime] = None) -> Dict[str, Any]:
    """PV compliance_events rows inside the window, newest first.

    DPDP events on the same table are excluded - this trail is the PV
    reconstructability contract, and mixing a data_breach row into a PSUR
    count would make the number meaningless.
    """
    reference = _reference(now)
    window = max(1, min(int(days or AUDIT_WINDOW_DAYS), AUDIT_MAX_DAYS))
    cutoff = reference - timedelta(days=window)

    rows = []
    for event in events or ():
        if not is_pv_audit_event(_get(event, "event_type")):
            continue
        detected = _as_dt(_get(event, "detected_at"))
        if detected is None or detected < cutoff:
            continue
        rows.append(
            {
                "id": _text(_get(event, "id")),
                "event_type": _text(_get(event, "event_type")),
                "severity": _text(_get(event, "severity")),
                "status": _text(_get(event, "status")),
                "detected_at": detected.isoformat(),
                "description": _text(_get(event, "description")),
            }
        )
    # Newest first, id as the tie-break so equal timestamps never reorder.
    rows.sort(key=lambda e: (_as_dt(e["detected_at"]), e["id"]), reverse=True)

    counts: Dict[str, int] = {}
    for row in rows:
        counts[row["event_type"]] = counts.get(row["event_type"], 0) + 1
    return {
        "window_days": window,
        "count": len(rows),
        "by_event_type": {name: counts[name] for name in sorted(counts)},
        "events": rows,
    }


# ─── Case / complaint / inquiry counts ──────────────────────────────────────
def _pqc_pipeline(complaints: Any) -> Dict[str, Any]:
    """The complaint state machine, counted. PQC_STATUSES order is preserved."""
    counts: Dict[str, int] = {}
    for complaint in complaints or ():
        stage = _text(_get(complaint, "investigation_status")).strip().lower()
        counts[stage or "unknown"] = counts.get(stage or "unknown", 0) + 1
    pipeline = {stage: counts.get(stage, 0) for stage in PQC_STATUSES}
    for stage in sorted(set(counts) - set(PQC_STATUSES)):
        pipeline[stage] = counts[stage]
    return {
        "total": len(list(complaints or ())),
        "by_investigation_status": pipeline,
        "by_disposition": _count_by(complaints or (), "disposition"),
    }


def _ae_statuses(cases: Any) -> Dict[str, Any]:
    """AE counts by status. `open` INCLUDES overdue (a flag, not a status) and
    any status outside the known vocabulary, both documented subsets."""
    rows = list(cases or ())
    counts: Dict[str, int] = {}
    for row in rows:
        status = _status(row)
        counts[status] = counts.get(status, 0) + 1
    terminal = sum(counts.get(name, 0) for name in TERMINAL_CASE_STATUSES)
    return {
        "open": len(rows) - terminal,
        "overdue": 0,  # filled by the clock, kept in one place for the reader
        "notified": counts.get("notified", 0),
        "submitted": counts.get("submitted", 0),
        "closed": counts.get("closed", 0),
        "unknown": sum(
            1 for row in rows if _status(row) not in KNOWN_CASE_STATUSES
        ),
        "total": len(rows),
    }


# ─── The snapshot ───────────────────────────────────────────────────────────
def build_dashboard_snapshot(
    ae_rows: Any = None,
    pqc_rows: Any = None,
    mi_rows: Any = None,
    product_rows: Any = None,
    audit_rows: Any = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Assemble the PVOIC compliance snapshot from already-fetched rows.

    Every number is derived here from the rows handed in - there is no stub
    value and no default that hides an empty clinic. The caller owns the
    database; this function owns the arithmetic, so the two can be tested
    independently.
    """
    reference = _reference(now)
    cases = list(ae_rows or ())
    complaints = list(pqc_rows or ())
    inquiries = list(mi_rows or ())

    overdue: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []
    for row in cases:
        clock = case_clock(row, reference)
        if clock is None or not _is_open(clock["status"]):
            continue
        deadline = _as_dt(clock["notification_deadline"])
        # Overdue is the TIMESTAMP comparison (now past the legal deadline),
        # not days_remaining < 0: the clock rounds up, so a case a few hours
        # past its deadline still reads 0 days remaining on the deadline day.
        # The flag is the fact; days_overdue is the whole days it has slipped.
        if deadline < reference:
            overdue.append(
                {
                    "case_id": clock["case_id"],
                    "status": clock["status"],
                    "is_serious": clock["is_serious"],
                    "notification_deadline": clock["notification_deadline"],
                    "days_overdue": max(0, -clock["days_remaining"]),
                }
            )
        else:
            hours = (deadline - reference).total_seconds() / 3600.0
            if hours <= UPCOMING_HORIZON_HOURS:
                entry = dict(clock)
                entry["hours_remaining"] = round(hours, 2)
                upcoming.append(entry)

    overdue.sort(key=lambda e: (_as_dt(e["notification_deadline"]), e["case_id"]))
    upcoming.sort(key=lambda e: (_as_dt(e["notification_deadline"]), e["case_id"]))

    by_status = _ae_statuses(cases)
    by_status["overdue"] = len(overdue)

    return {
        "generated_at": reference.isoformat(),
        "cases": {
            "by_type": {
                "ae": len(cases),
                "pqc": len(complaints),
                "mi": len(inquiries),
                "total": len(cases) + len(complaints) + len(inquiries),
            },
            "by_status": by_status,
        },
        "clocks": {
            "horizon_hours": UPCOMING_HORIZON_HOURS,
            "overdue_count": len(overdue),
            "overdue": overdue,
            "upcoming_count": len(upcoming),
            "upcoming": upcoming,
        },
        "pqc": _pqc_pipeline(complaints),
        "mi": {"total": len(inquiries), "by_status": _count_by(inquiries, "status")},
        "psur": build_psur_schedule(product_rows, now=reference),
        "audit": build_audit_trail(audit_rows, days=AUDIT_WINDOW_DAYS, now=reference),
    }
