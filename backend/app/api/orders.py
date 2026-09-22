"""Orders API — Order CRUD"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

router = APIRouter()


class OrderItem(BaseModel):
    menu_item_id: str
    name: str
    quantity: int
    price_cents: int
    modifiers: List[str] = []


class OrderCreate(BaseModel):
    restaurant_id: str
    call_id: str
    items: List[OrderItem]
    total_cents: int


class OrderUpdate(BaseModel):
    state: Optional[str] = None
    pos_order_id: Optional[str] = None


class OrderResponse(BaseModel):
    id: UUID
    call_id: UUID
    restaurant_id: UUID
    items: List[OrderItem]
    total_cents: int
    state: str
    pos_order_id: Optional[str]
    created_at: str


@router.get("/restaurant/{restaurant_id}")
async def list_orders(restaurant_id: str, state: Optional[str] = None):
    """List orders for a restaurant"""
    # TODO: Query Supabase
    return []


@router.get("/{order_id}")
async def get_order(order_id: str):
    """Get order by ID"""
    # TODO: Query Supabase
    raise HTTPException(404, "Not found")


@router.post("/")
async def create_order(order: OrderCreate):
    """Create new order from call"""
    # TODO: Save to Supabase
    return {"id": "new-order-id", "state": "PLACED"}


@router.patch("/{order_id}")
async def update_order(order_id: str, update: OrderUpdate):
    """Update order state"""
    # TODO: Update in Supabase
    return {"id": order_id, **update.model_dump(exclude_unset=True)}