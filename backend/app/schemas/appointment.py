"""Appointment request models + status single source."""
from pydantic import BaseModel

# Mirrors postgres_schema.sql appointments.status comment.
APPOINTMENT_STATUSES = ("pending", "confirmed", "completed", "cancelled", "no_show")


class AppointmentCreate(BaseModel):
    clinic_id: str
    patient_name: str = ""
    patient_phone: str = ""
    patient_language: str = "en"  # hi, en, ta, te, bn
    # ISO-8601 datetime, e.g. 2026-09-24T10:30:00+05:30
    scheduled_at: str
    reason: str = ""
    duration_minutes: int = 30
    location: str = ""
    caller_id: str = ""


class AppointmentStatusUpdate(BaseModel):
    status: str