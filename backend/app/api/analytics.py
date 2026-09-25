"""Analytics API — MVP KPI endpoints (spec-kpis-q9.md G6-Q9).

Sign-off 2026-09-25 (question tool): Q2=A2 per-KPI endpoints — one GET per
KPI under /api/analytics (volume / resolution / triage / language / no-show /
revenue / delivery) plus /benchmarks for the static market-context dict.
Q3=A1 pure computed: every call runs a read-only aggregate over the existing
calls / appointments / payments / notifications tables (rides their RLS —
clinic membership via the per-request GUC), zero schema writes. Q4=A1:
optional from/to (default last 30 days, 366-day cap, naive assumed UTC),
422 on bad order / over-cap / unparseable. Identity-gated like every domain
endpoint; the dashboard paints its Overview/Analytics tabs with these.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.auth import get_current_user
from app.db.postgres import (
    compute_delivery,
    compute_language,
    compute_no_show,
    compute_resolution,
    compute_revenue,
    compute_triage,
    compute_volume,
)
from app.services import analytics as anl

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=422, detail=f"invalid {what}")


def _period(from_: str, to: str):
    """Resolve the optional window; ValueError (bad order/cap/format) -> 422."""
    try:
        return anl.resolve_period(from_ or None, to or None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


def _period_payload(from_dt, to_dt) -> dict:
    return {
        "from": from_dt.isoformat(),
        "to": to_dt.isoformat(),
        "days": (to_dt - from_dt).days,
    }


@router.get("/volume")
async def get_volume_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Call volume: total, by_state, by_day + avg duration (window)."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    raw = await compute_volume(cid, from_dt, to_dt)
    return {"period": _period_payload(from_dt, to_dt), "calls": anl.shape_volume(raw)}


@router.get("/resolution")
async def get_resolution_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Resolution rate — COMPLETE / terminal (excl. in-progress PAYMENT_SENT)."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    counts = await compute_resolution(cid, from_dt, to_dt)
    return {
        "period": _period_payload(from_dt, to_dt),
        "resolution_rate": anl.resolution_rate(
            counts["COMPLETE"], counts["DROPPED"],
            counts["ESCALATED"], counts["PAYMENT_EXPIRED"],
        ),
        "counts": counts,
    }


@router.get("/triage")
async def get_triage_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Severity distribution (green/amber/red/critical) + untriaged."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    mix = await compute_triage(cid, from_dt, to_dt)
    return {"period": _period_payload(from_dt, to_dt), "triage_mix": mix}


@router.get("/language")
async def get_language_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Calls per language (hi/en/ta/te/bn) + unknown bucket."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    dist = await compute_language(cid, from_dt, to_dt)
    return {"period": _period_payload(from_dt, to_dt), "language_dist": dist}


@router.get("/no-show")
async def get_no_show_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """No-show rate over terminal appointments (no_show/completed/cancelled)."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    counts = await compute_no_show(cid, from_dt, to_dt)
    return {
        "period": _period_payload(from_dt, to_dt),
        "no_show_rate": anl.no_show_rate(
            counts["no_show"], counts["completed"], counts["cancelled"]
        ),
        "counts": counts,
    }


@router.get("/revenue")
async def get_revenue_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Captured / refunded sums + captured by kind + currency."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    rev = await compute_revenue(cid, from_dt, to_dt)
    return {"period": _period_payload(from_dt, to_dt), "revenue": rev}


@router.get("/delivery")
async def get_delivery_ep(
    clinic_id: str,
    from_: str = Query("", alias="from"),
    to: str = Query("", alias="to"),
    user=Depends(get_current_user),
):
    """Notification delivery success per kind (sent/failed/total/rate)."""
    cid = _uuid(clinic_id, "clinic_id")
    from_dt, to_dt = _period(from_, to)
    raw = await compute_delivery(cid, from_dt, to_dt)
    return {"period": _period_payload(from_dt, to_dt), "delivery": anl.shape_delivery(raw)}


@router.get("/benchmarks")
async def get_benchmarks_ep(user=Depends(get_current_user)):
    """Static market-context cards (display-only, never enforced).

    No clinic_id / period — the dict is the same for every tenant and the
    dashboard renders it as 'vs benchmark' reference cards.
    """
    return anl.BENCHMARKS