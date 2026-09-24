"""Prescription request models + status single source."""
from pydantic import BaseModel

# Mirrors postgres_schema.sql prescriptions.status comment.
PRESCRIPTION_STATUSES = ("pending", "approved", "sent_pharmacy", "dispensed")


class PrescriptionCreate(BaseModel):
    clinic_id: str
    patient_name: str = ""
    patient_phone: str = ""
    patient_language: str = "en"  # hi, en, ta, te, bn
    medication: str
    dosage: str = ""
    frequency: str = ""
    instructions: str = ""
    pharmacy_name: str = ""
    caller_id: str = ""


class PrescriptionStatusUpdate(BaseModel):
    status: str