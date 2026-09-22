"""Call state machine"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List, Dict
from datetime import datetime


class CallState(str, Enum):
    GREETING = "GREETING"
    TAKING_ORDER = "TAKING_ORDER"
    CONFIRMING = "CONFIRMING"
    CONFIRMED = "CONFIRMED"
    PAYMENT_SENT = "PAYMENT_SENT"
    COMPLETE = "COMPLETE"
    TRANSFER_TO_HUMAN = "TRANSFER_TO_HUMAN"
    CALL_DROPPED = "CALL_DROPPED"
    POS_FAILED = "POS_FAILED"
    PAYMENT_EXPIRED = "PAYMENT_EXPIRED"


STATE_TRANSITIONS = {
    CallState.GREETING: [CallState.TAKING_ORDER, CallState.TRANSFER_TO_HUMAN],
    CallState.TAKING_ORDER: [CallState.CONFIRMING, CallState.TRANSFER_TO_HUMAN],
    CallState.CONFIRMING: [CallState.CONFIRMED, CallState.TAKING_ORDER, CallState.TRANSFER_TO_HUMAN],
    CallState.CONFIRMED: [CallState.PAYMENT_SENT, CallState.TRANSFER_TO_HUMAN],
    CallState.PAYMENT_SENT: [CallState.COMPLETE, CallState.PAYMENT_EXPIRED],
    CallState.COMPLETE: [],
}


@dataclass
class Call:
    id: str
    restaurant_id: str
    caller_number: str
    state: CallState
    started_at: datetime
    ended_at: Optional[datetime] = None
    transcript: List[Dict] = None
    stt_confidence: float = 0.0
    order_items: List[Dict] = None

    def __post_init__(self):
        if self.transcript is None:
            self.transcript = []
        if self.order_items is None:
            self.order_items = []

    def can_transition(self, new_state: CallState) -> bool:
        return new_state in STATE_TRANSITIONS.get(self.state, [])

    def transition(self, new_state: CallState) -> bool:
        if self.can_transition(new_state):
            self.state = new_state
            return True
        return False