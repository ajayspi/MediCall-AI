"""Restaurants API — Restaurant management"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

router = APIRouter()


class RestaurantCreate(BaseModel):
    name: str
    phone_number: str
    telnyx_number: Optional[str] = None
    address: Optional[str] = None
    closing_time: Optional[str] = "22:00"
    ai_instructions: Optional[str] = ""


class RestaurantUpdate(BaseModel):
    name: Optional[str] = None
    phone_number: Optional[str] = None
    telnyx_number: Optional[str] = None
    address: Optional[str] = None
    closing_time: Optional[str] = None
    ai_instructions: Optional[str] = None
    active: Optional[bool] = None


class RestaurantResponse(BaseModel):
    id: UUID
    name: str
    phone_number: str
    telnyx_number: Optional[str]
    address: Optional[str]
    closing_time: str
    ai_instructions: str
    active: bool
    plan: str
    created_at: str


@router.get("/")
async def list_restaurants(active: Optional[bool] = None):
    """List all restaurants"""
    # TODO: Query Supabase
    return []


@router.get("/{restaurant_id}")
async def get_restaurant(restaurant_id: str):
    """Get restaurant by ID"""
    # TODO: Query Supabase
    raise HTTPException(404, "Not found")


@router.get("/{restaurant_id}/menu")
async def get_menu(restaurant_id: str):
    """Get restaurant menu with pgvector RAG"""
    # TODO: Query Supabase with pgvector
    return []


@router.post("/")
async def create_restaurant(restaurant: RestaurantCreate):
    """Create new restaurant"""
    # TODO: Save to Supabase
    return {"id": "new-restaurant-id"}


@router.patch("/{restaurant_id}")
async def update_restaurant(restaurant_id: str, update: RestaurantUpdate):
    """Update restaurant"""
    # TODO: Update in Supabase
    return {"id": restaurant_id, **update.model_dump(exclude_unset=True)}