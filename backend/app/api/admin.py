"""Admin API — Operator admin panel endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List
from uuid import UUID

router = APIRouter()


@router.get("/stats")
async def platform_stats():
    """System-wide stats"""
    # TODO: Query Supabase
    return {
        "total_restaurants": 487,
        "total_calls_today": 0,
        "total_revenue_today": 0,
        "active_calls": 0,
        "mrr": 0,
    }


@router.get("/calls/live")
async def live_calls():
    """Live calls across all restaurants"""
    # TODO: Query Supabase
    return []


@router.get("/restaurants")
async def list_all_restaurants(active: Optional[bool] = None, search: Optional[str] = None):
    """List all restaurants with filters"""
    # TODO: Query Supabase
    return []


@router.get("/revenue")
async def revenue_breakdown():
    """MRR breakdown, COGS, tier distribution"""
    # TODO: Query Supabase
    return {
        "mrr": 0,
        "voice_cogs": 0,
        "tier_distribution": {},
    }


@router.get("/infrastructure")
async def infra_health():
    """Service health telemetry"""
    # TODO: Check all external services
    return {
        "telnyx": "healthy",
        "deepgram": "healthy",
        "openai": "healthy",
        "elevenlabs": "healthy",
        "supabase": "healthy",
        "upstash": "healthy",
        "stripe": "healthy",
        "square": "healthy",
        "celery": "healthy",
    }


@router.get("/audit")
async def audit_log(
    event_type: Optional[str] = None,
    restaurant_id: Optional[str] = None,
    limit: int = 100,
):
    """Security audit trail"""
    # TODO: Query Supabase
    return []


@router.get("/analytics")
async def platform_analytics():
    """Platform performance metrics"""
    # TODO: Query Supabase
    return {
        "completion_rates": {},
        "abandonment_analysis": {},
        "cuisine_performance": {},
    }