"""Call request models (state transitions)."""
from pydantic import BaseModel


class CallStateUpdate(BaseModel):
    # One of the nine G3 states (GREETING..PAYMENT_EXPIRED); the router
    # validates membership in CallState and the STATE_TRANSITIONS table.
    state: str


class ConsentUpdate(BaseModel):
    # DPDP per-call recording consent (spec-dpdp-q2.md G6-Q2 Q1=A1): one of
    # unknown / granted / denied; the router validates against
    # consent.RECORDING_CONSENT_STATES. denied revokes (blocks future egress).
    consent: str