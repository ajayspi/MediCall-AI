"""Call request models (state transitions)."""
from pydantic import BaseModel


class CallStateUpdate(BaseModel):
    # One of the nine G3 states (GREETING..PAYMENT_EXPIRED); the router
    # validates membership in CallState and the STATE_TRANSITIONS table.
    state: str