"""Order model"""
from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from enum import Enum


class OrderState(str, Enum):
    PLACED = "PLACED"
    LINK_SENT = "LINK_SENT"
    PAID = "PAID"
    SYNCED = "SYNCED"
    FAILED = "FAILED"


@dataclass
class OrderItem:
    menu_item_id: str
    name: str
    quantity: int
    price_cents: int
    modifiers: List[str] = None

    def __post_init__(self):
        if self.modifiers is None:
            self.modifiers = []


@dataclass
class Order:
    id: str
    call_id: str
    restaurant_id: str
    items: List[OrderItem]
    total_cents: int
    state: OrderState
    pos_order_id: Optional[str] = None
    created_at: datetime = None
    paid_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

    def calculate_total(self) -> int:
        return sum(item.price_cents * item.quantity for item in self.items)