"""Platform admin router (G6-Q11, spec-frontend-wiring-q11.md).

Role-gated cross-tenant read surface for the admin area:

    GET /api/admin           — platform overview (clinic/call/revenue counts)
    GET /api/admin/clinics   — every clinic + MTD/today/live call aggregates
    GET /api/admin/patients  — distinct callers across clinics
    GET /api/admin/revenue   — captured/pending + by gateway + by clinic
    GET /api/admin/calls     — recent calls across clinics (live feed)

Every endpoint requires the platform_admin role (weight 6, above owner). The
aggregates in app/db/postgres.py arm app.service_request internally (the
auth-CRUD pattern) so RLS FORCE admits the cross-tenant reads; the JWT role is
the entry gate. platform_admin is seeded out-of-band (demo tenant seed) —
register() cannot grant it, so there is no self-serve path.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import require_roles
from app.db.postgres import (
    platform_calls,
    platform_clinics,
    platform_overview,
    platform_patients,
    platform_revenue,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("")
async def admin_overview(user=Depends(require_roles("platform_admin"))):
    """Headline cross-clinic counts for the admin dashboard."""
    return await platform_overview()


@router.get("/clinics")
async def admin_clinics(user=Depends(require_roles("platform_admin"))):
    """Every clinic with MTD/today/live call aggregates, ordered by name."""
    return await platform_clinics()


@router.get("/patients")
async def admin_patients(user=Depends(require_roles("platform_admin"))):
    """Distinct callers across clinics, most recently active first."""
    return await platform_patients()


@router.get("/revenue")
async def admin_revenue(user=Depends(require_roles("platform_admin"))):
    """Cross-clinic revenue: status sums + captured by gateway and by clinic."""
    return await platform_revenue()


@router.get("/calls")
async def admin_calls(
    limit: int = 50,
    offset: int = 0,
    user=Depends(require_roles("platform_admin")),
):
    """Recent calls across clinics (newest first), limit capped at 200."""
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="limit must be 1..200")
    return await platform_calls(limit=limit, offset=offset)