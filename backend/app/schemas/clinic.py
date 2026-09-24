"""Clinic request models (admin management + clinic settings)."""
from typing import Optional
from pydantic import BaseModel


class ClinicCreate(BaseModel):
    name: str
    phone_number: str
    city: str
    state: str
    address: str = ""
    pincode: str = ""
    closing_time: str = "22:00"
    ai_instructions: str = ""
    # starter, growth, enterprise
    plan: str = "starter"
    is_active: bool = True


class ClinicUpdate(BaseModel):
    """Partial update — the router applies only fields the client actually sent."""

    name: Optional[str] = None
    phone_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    closing_time: Optional[str] = None
    ai_instructions: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None