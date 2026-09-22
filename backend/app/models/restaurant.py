"""Restaurant model"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Restaurant:
    id: str
    name: str
    phone_number: str
    telnyx_number: Optional[str] = None
    address: Optional[str] = None
    closing_time: str = "22:00"
    ai_instructions: str = ""
    active: bool = True
    plan: str = "starter"
    pos_provider: Optional[str] = "square"
    pos_config: dict = None
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.pos_config is None:
            self.pos_config = {}