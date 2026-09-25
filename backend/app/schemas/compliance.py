"""Compliance event request models (spec-dpdp-q2.md G6-Q2 Q3=A1).

The DPDP 72-hr breach flow + consent-lifecycle + data-subject-request
records. The router validates event_type/severity/status membership against
compliance.COMPLIANCE_EVENT_TYPES / SEVERITIES / STATUSES; the DB helper
computes notification_deadline = detected_at + 72h at insert.
"""

from pydantic import BaseModel


class ComplianceEventCreate(BaseModel):
    clinic_id: str
    event_type: str  # data_breach, consent_withdrawal, gdpr_request
    severity: str = "medium"  # low, medium, high, critical
    description: str | None = None


class ComplianceEventUpdate(BaseModel):
    status: str | None = None  # open, reported, closed
    severity: str | None = None  # low, medium, high, critical