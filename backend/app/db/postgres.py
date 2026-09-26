"""Async PostgreSQL + pgvector database client for MediCall AI.

Local PostgreSQL with pgvector for the Medical Call Center domain:
voice-first calls, multi-language STT/TTS (hi/en/ta/te/bn), Indian
payment gateways (Razorpay/PhonePe/Cashfree), Indian telephony
(Exotel/Knowlarity/Twilio India).

Conventions: asyncpg driver, pgvector for embeddings (similar-call
search, symptom clustering), UTC tz-aware timestamps, SQLAlchemy 2.0
typed models mirroring backend/postgres_schema.sql.
"""

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.models.call import CallState, TriageSeverity
from app.services.compliance import breach_notification_deadline
from app.services.retention import retention_deadline
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    delete,
    event,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

# ─── Environment & Configuration ──────────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://medicall:medicall@localhost:5432/medicall",
)

POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
SQL_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"


# ─── Engine Factory ────────────────────────────────────────────────────────


def get_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine with pgvector support."""
    if os.getenv("DB_ENV") == "test":
        return create_async_engine(
            DATABASE_URL,
            echo=SQL_ECHO,
            poolclass=NullPool,
        )
    return create_async_engine(
        DATABASE_URL,
        echo=SQL_ECHO,
        poolclass=AsyncAdaptedQueuePool,
        pool_size=POOL_SIZE,
        max_overflow=MAX_OVERFLOW,
        pool_timeout=POOL_TIMEOUT,
    )


engine: AsyncEngine = get_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


# ─── RLS GUC plumbing (spec-auth-enforcement.md Q4/A4a) ──────────────────────
# Every transaction on the shared engine sets the RLS GUCs from request-scoped
# contextvars, so `auth.uid()` (postgres_schema.sql) always sees the current
# request's user — in the auth dependency's own session, in get_db_session, and
# in every CRUD function's private SessionFactory() session. `SET LOCAL` is
# transaction-scoped: pooled connections reset automatically, so one request's
# user id can never leak into the next request.

_current_user_id: ContextVar[Optional[str]] = ContextVar(
    "current_user_id", default=None
)
_service_request: ContextVar[bool] = ContextVar("service_request", default=False)


def set_current_user_id(value: Optional[str]) -> None:
    """Record the authenticated user for the request's DB transactions.

    Called by the get_current_user dependency AFTER token decode and BEFORE any
    query (auth.uid() then scopes every policy to this user). Database ids are
    stripped of quotes defensively before being inlined into the GUC SQL.
    """
    _current_user_id.set(value.replace("'", "") if value else None)


@contextmanager
def service_request_ctx() -> Iterator[None]:
    """Arm the server-side service bypass for the wrapped block.

    Only pre-authentication paths use this (auth user CRUD, verified voice
    webhooks, create_clinic's owner-membership insert). The policies in
    postgres_schema.sql decide what a service-armed transaction may touch
    (users_own_data, calls_create/calls_read, clinic_users_service_insert).
    External callers cannot set Postgres GUCs over HTTP — arming is server-side
    authority only.
    """
    token = _service_request.set(True)
    try:
        yield
    finally:
        _service_request.reset(token)


@event.listens_for(engine.sync_engine, "begin")
def _set_rls_gucs(conn) -> None:
    """SET LOCAL the RLS GUCs at the start of every transaction."""
    uid = _current_user_id.get()
    conn.exec_driver_sql(
        "SET LOCAL app.current_user_id = " + ("'" + uid + "'" if uid else "NULL")
    )
    conn.exec_driver_sql(
        "SET LOCAL app.service_request = "
        + ("'on'" if _service_request.get() else "'off'")
    )


# ─── Base & Helpers ────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


def now_tz() -> datetime:
    """Current UTC datetime with timezone."""
    return datetime.now(timezone.utc)


# ─── Enums (canonical definitions live in app.models.call) ────────────────

# Supported caller/patient languages (Hindi, English, Tamil, Telugu, Bengali):
# single source = app/services/languages.py (G6-Q4 Q2=A1). This import makes
# the same tuple object available to every consumer (no drift between copies).
from app.services.languages import SUPPORTED_LANGUAGES


# ─── Database Models ───────────────────────────────────────────────────────


class Clinic(Base):
    """Clinic/facility entity."""

    __tablename__ = "clinics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(30), nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[Optional[str]] = mapped_column(String(10))
    latitude: Mapped[Optional[float]] = mapped_column()
    longitude: Mapped[Optional[float]] = mapped_column()
    closing_time: Mapped[str] = mapped_column(String(5), default="22:00")
    ai_instructions: Mapped[str] = mapped_column(Text, default="")
    # starter, growth, enterprise
    plan: Mapped[str] = mapped_column(String(50), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return f"<Clinic id={self.id} name={self.name} city={self.city}>"


class User(Base):
    """Application user (Phase-1 auth, G6-Q1): email and/or phone identity."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # pbkdf2_sha256$iter$salt$hash (NULL for SSO-only users)
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    # HMAC-SHA256 of the last issued OTP (code never stored raw)
    otp_code_hash: Mapped[Optional[str]] = mapped_column(String(64))
    otp_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    # owner, staff, triage_agent, doctor, readonly
    role: Mapped[str] = mapped_column(String(20), default="staff")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.name}>"


class ClinicUser(Base):
    """Multi-tenant clinic staff/users."""

    __tablename__ = "clinic_users"
    __table_args__ = (UniqueConstraint("clinic_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # owner, staff, triage_agent, doctor, readonly
    role: Mapped[str] = mapped_column(String(20), default="staff")
    # hi, en, ta, te, bn
    language_pref: Mapped[str] = mapped_column(String(5), default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )

    def __repr__(self) -> str:
        return f"<ClinicUser clinic={self.clinic_id} role={self.role}>"


class Call(Base):
    """Core: voice-first medical call record."""

    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    caller_number: Mapped[str] = mapped_column(String(30), nullable=False)
    # hi, en, ta, te, bn
    caller_language: Mapped[str] = mapped_column(String(5), default="en")
    # GREETING, TRIAGE, APPOINTMENT, PRESCRIPTION, COMPLETE, ESCALATED, DROPPED
    state: Mapped[str] = mapped_column(String(20), default="GREETING")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Multi-language transcript:
    # [{"role": "caller", "text": "...", "language": "hi"}, ...]
    transcript: Mapped[list] = mapped_column(JSONB, default=list)
    stt_confidence: Mapped[float] = mapped_column(default=0.0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    # green, amber, red, critical (from AI triage)
    triage_severity: Mapped[Optional[str]] = mapped_column(String(20))
    # SNOMED CT code list
    diagnosed_conditions: Mapped[list] = mapped_column(JSONB, default=list)
    prescription_issued: Mapped[bool] = mapped_column(Boolean, default=False)
    appointment_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True
    )
    escalated_to_human: Mapped[bool] = mapped_column(Boolean, default=False)
    # DPDP (G6-Q2 Q1=A1): unknown / granted / denied — the egress gate reads it.
    recording_consent: Mapped[str] = mapped_column(String(10), default="unknown")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    embedding_rel: Mapped[Optional["CallEmbedding"]] = relationship(
        back_populates="call", cascade="all, delete-orphan", uselist=False
    )

    def __repr__(self) -> str:
        return (
            f"<Call id={self.id} clinic={self.clinic_id} "
            f"state={self.state} lang={self.caller_language}>"
        )


class Appointment(Base):
    """Appointment derived from call triage + scheduling."""

    __tablename__ = "appointments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_name: Mapped[Optional[str]] = mapped_column(String(255))
    patient_phone: Mapped[Optional[str]] = mapped_column(String(30))
    patient_language: Mapped[str] = mapped_column(String(5), default="en")
    caller_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id"), nullable=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # pending, confirmed, completed, cancelled, no_show
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # chief complaint summary
    reason: Mapped[Optional[str]] = mapped_column(Text)
    doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    # clinic address or telemedicine link
    location: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<Appointment id={self.id} clinic={self.clinic_id} "
            f"status={self.status}>"
        )


class Prescription(Base):
    """Prescription from call triage + doctor review."""

    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    patient_name: Mapped[Optional[str]] = mapped_column(String(255))
    patient_phone: Mapped[Optional[str]] = mapped_column(String(30))
    patient_language: Mapped[str] = mapped_column(String(5), default="en")
    caller_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id"), nullable=True
    )
    medication: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[Optional[str]] = mapped_column(String(100))
    frequency: Mapped[Optional[str]] = mapped_column(String(50))
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    doctor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # pending, approved, sent_pharmacy, dispensed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    pharmacy_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<Prescription id={self.id} med={self.medication} "
            f"clinic={self.clinic_id}>"
        )


class CallEmbedding(Base):
    """pgvector embedding for similar-call search and triage patterns."""

    __tablename__ = "call_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # 1536-dim pgvector embedding
    embedding: Mapped[list] = mapped_column(Vector(1536), nullable=False)
    # call_analysis, triage_summary, prescription_summary, speaker_embedding
    embedding_type: Mapped[str] = mapped_column(
        String(30), default="call_analysis"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )

    call: Mapped["Call"] = relationship(back_populates="embedding_rel")

    def __repr__(self) -> str:
        return f"<CallEmbedding id={self.id} type={self.embedding_type}>"


class LanguageCode(Base):
    """Indian languages reference — STT/TTS model mapping."""

    __tablename__ = "language_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # hi, en, ta, te, bn
    code: Mapped[str] = mapped_column(String(5), unique=True)
    script: Mapped[str] = mapped_column(String(30))
    # Deepgram model name/identifier
    deepgram_model: Mapped[str] = mapped_column(String(50), default="nova-3")
    elevenlabs_voice_id: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<LanguageCode code={self.code} script={self.script}>"


class CallSession(Base):
    """LiveKit room mapping for active calls."""

    __tablename__ = "call_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calls.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    clinic_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clinics.id"), nullable=True
    )
    livekit_room: Mapped[Optional[str]] = mapped_column(String(255))
    livekit_participant_id: Mapped[Optional[str]] = mapped_column(String(255))
    # idle, recording, in_progress, completed, failed
    status: Mapped[str] = mapped_column(String(20), default="idle")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    last_heartbeat: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )

    def __repr__(self) -> str:
        return f"<CallSession call={self.call_id} status={self.status}>"


class Payment(Base):
    """Payments — scaffold (G6-Q5: flows/gateways open; records intent only)."""

    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    appointment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="SET NULL"),
        nullable=True,
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    # razorpay, phonepe, cashfree, manual
    gateway: Mapped[Optional[str]] = mapped_column(String(20))
    gateway_ref: Mapped[Optional[str]] = mapped_column(String(255))
    # pending, captured, failed, refunded
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # consultation / refill / subscription (spec-payments.md Q1/A1a, Q2/A2a)
    kind: Mapped[str] = mapped_column(String(20), default="consultation")
    # Intent TTL — the PAYMENT_SENT -> PAYMENT_EXPIRED leg. The column is
    # recorded at creation; an automated expiry sweep is a follow-up (needs
    # the scheduler — Docker/CI territory).
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} clinic={self.clinic_id} "
            f"{self.amount} {self.currency} {self.status}>"
        )


class Notification(Base):
    """Notifications — WhatsApp-first delivery records (G6-Q8)."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    # payment_link, appointment_reminder, no_show_followup, otp, payment_receipt
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(120), nullable=False)
    language: Mapped[str] = mapped_column(String(5), default="en")
    # JSON-encoded template params (spec-notifications-q8.md Q2=A2c)
    params: Mapped[Optional[str]] = mapped_column(Text)
    # whatsapp / sms / email / push
    channel: Mapped[Optional[str]] = mapped_column(String(20))
    # meta / knowlarity / msg91 / smtp / fcm
    provider: Mapped[Optional[str]] = mapped_column(String(20))
    provider_ref: Mapped[Optional[str]] = mapped_column(String(255))
    # queued, sent, failed
    status: Mapped[str] = mapped_column(String(20), default="queued")
    template: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} clinic={self.clinic_id} "
            f"kind={self.kind} {self.channel}/{self.provider} {self.status}>"
        )


class ComplianceEvent(Base):
    """DPDP compliance event record (spec-dpdp-q2.md G6-Q2 Q3=A1)."""

    __tablename__ = "compliance_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    # data_breach, consent_withdrawal, gdpr_request
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    # low, medium, high, critical
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    # open, reported, closed
    status: Mapped[str] = mapped_column(String(20), default="open")
    description: Mapped[Optional[str]] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    # detected_at + DPDP_BREACH_NOTIFICATION_HOURS (72h default) — computed at
    # insert via compliance.breach_notification_deadline.
    notification_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<ComplianceEvent id={self.id} clinic={self.clinic_id} "
            f"type={self.event_type} {self.status}>"
        )


# ─── Pharmacovigilance / MICC models (spec-micc-pv-module.md) ──────────────
# The call centre is a COLLECTOR: these rows hold what a caller reported about
# a medicine, never a clinical conclusion. Matching postgres_schema.sql.


class Product(Base):
    """Product dictionary a PV case is reported against."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "name",
            "strength",
            "dosage_form",
            name="uq_products_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    generic_name: Mapped[Optional[str]] = mapped_column(String(255))
    strength: Mapped[Optional[str]] = mapped_column(String(60))
    dosage_form: Mapped[Optional[str]] = mapped_column(String(60))
    manufacturer: Mapped[Optional[str]] = mapped_column(String(255))
    # Approved label snapshot in force at the time of the report — the basis
    # for the expectedness call, which the officer makes downstream.
    approved_label_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<Product id={self.id} name={self.name} "
            f"strength={self.strength} clinic={self.clinic_id}>"
        )


class AdverseEvent(Base):
    """Individual case safety report (ICH E2B minimum) from a call."""

    __tablename__ = "adverse_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    # hcp / consumer / caregiver — the reporter's qualification (E2B source).
    reporter_type: Mapped[Optional[str]] = mapped_column(String(40))
    reporter_contact: Mapped[Optional[dict]] = mapped_column(JSONB)
    patient_age: Mapped[Optional[str]] = mapped_column(String(20))
    patient_sex: Mapped[Optional[str]] = mapped_column(String(20))
    patient_initials: Mapped[Optional[str]] = mapped_column(String(20))
    # VERBATIM caller speech — not a clinical description.
    event_text: Mapped[Optional[str]] = mapped_column(Text)
    event_onset_date: Mapped[Optional[Any]] = mapped_column(Date)
    outcome: Mapped[Optional[str]] = mapped_column(String(40))
    # ICH E2A criteria the caller reported, as a list of canonical slugs.
    seriousness_flags: Mapped[list] = mapped_column(JSONB, default=list)
    expectedness: Mapped[Optional[str]] = mapped_column(String(40))
    # The reporter's own words about the suspect drug. Recorded, never produced.
    causality_reporter: Mapped[Optional[str]] = mapped_column(Text)
    # FALSE = E2B minimum not yet met: stored and chased, never dropped.
    e2b_minimum_met: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="new")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    # India clock at intake: 15 calendar days serious, 90 non-serious.
    notification_deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    source_channel: Mapped[Optional[str]] = mapped_column(String(30))
    recording_consent: Mapped[Optional[str]] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<AdverseEvent id={self.id} clinic={self.clinic_id} "
            f"status={self.status} e2b={self.e2b_minimum_met}>"
        )


class QualityComplaint(Base):
    """Product quality complaint (EU GMP Ch. 8 defect + investigation)."""

    __tablename__ = "quality_complaints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    batch_no: Mapped[Optional[str]] = mapped_column(String(60))
    expiry: Mapped[Optional[Any]] = mapped_column(Date)
    defect_description: Mapped[Optional[str]] = mapped_column(Text)
    photos_url: Mapped[Optional[dict]] = mapped_column(JSONB)
    severity: Mapped[Optional[str]] = mapped_column(String(20))
    # captured -> investigating -> disposition -> capa (forward-only, capa is
    # terminal) — enforced by pharmacovigilance.next_pqc_status.
    investigation_status: Mapped[str] = mapped_column(
        String(30), default="captured"
    )
    disposition: Mapped[Optional[str]] = mapped_column(Text)
    capa_ref: Mapped[Optional[str]] = mapped_column(String(120))
    recording_consent: Mapped[Optional[str]] = mapped_column(String(30))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<QualityComplaint id={self.id} product={self.product_id} "
            f"status={self.investigation_status}>"
        )


class MedicalInquiry(Base):
    """Medical information inquiry — a question about a medicine."""

    __tablename__ = "medical_inquiries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clinic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinics.id", ondelete="CASCADE"),
        nullable=False,
    )
    call_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL"), nullable=True
    )
    product_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="SET NULL"),
        nullable=True,
    )
    question_text: Mapped[Optional[str]] = mapped_column(Text)
    # dosing, interactions, side_effect, indication, other
    category: Mapped[Optional[str]] = mapped_column(String(40))
    language: Mapped[Optional[str]] = mapped_column(String(5))
    response_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_tz, onupdate=now_tz
    )

    def __repr__(self) -> str:
        return (
            f"<MedicalInquiry id={self.id} product={self.product_id} "
            f"status={self.status} lang={self.language}>"
        )


# ─── Session Management ────────────────────────────────────────────────────


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session (use as FastAPI dependency)."""
    async with SessionFactory() as session:
        yield session


def get_engine_fresh() -> AsyncEngine:
    """Get a fresh engine instance (useful for testing)."""
    return get_engine()


# ─── CRUD operations for the MediCall AI workflow ──────────────────────────


async def create_clinic(
    name: str,
    phone_number: str,
    city: str,
    state: str,
    owner_user_id: Optional[uuid.UUID] = None,
    **kwargs: Any,
) -> Clinic:
    """Create a new clinic + the creator's owner membership row.

    The clinics_create RLS policy requires a global-owner user (the router gates
    this endpoint with require_roles('owner')) and clinic_users_service_insert
    permits the membership insert only on the server-side service path — both
    supplied here, in one transaction. Without the membership row, RLS would
    hide the new clinic from its own creator.
    """
    async with SessionFactory() as session:
        stmt = (
            insert(Clinic)
            .values(
                name=name,
                phone_number=phone_number,
                city=city,
                state=state,
                **kwargs,
            )
            .returning(Clinic)
        )
        with service_request_ctx():
            result = await session.execute(stmt)
            clinic = result.scalar_one()
            if owner_user_id is not None:
                await session.execute(
                    insert(ClinicUser).values(
                        clinic_id=clinic.id,
                        user_id=owner_user_id,
                        role="owner",
                    )
                )
            await session.commit()
        return clinic


async def get_clinic(clinic_id: uuid.UUID) -> Optional[Clinic]:
    """Get clinic by ID."""
    async with SessionFactory() as session:
        return await session.get(Clinic, clinic_id)


async def list_clinics(active_only: Optional[bool] = None) -> list[Clinic]:
    """List clinics, optionally active-only, ordered by name (admin page)."""
    async with SessionFactory() as session:
        query = select(Clinic)
        if active_only is not None:
            query = query.where(Clinic.is_active.is_(active_only))
        query = query.order_by(Clinic.name)
        result = await session.execute(query)
        return list(result.scalars().all())


async def update_clinic(
    clinic_id: uuid.UUID, **fields: Any
) -> Optional[Clinic]:
    """Update editable clinic settings; returns the updated row or None."""
    allowed = {
        "name", "phone_number", "address", "city", "state", "pincode",
        "closing_time", "ai_instructions", "plan", "is_active",
    }
    values = {k: v for k, v in fields.items() if k in allowed and v is not None}
    values["updated_at"] = now_tz()
    async with SessionFactory() as session:
        stmt = (
            update(Clinic)
            .where(Clinic.id == clinic_id)
            .values(**values)
            .returning(Clinic)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none()


async def list_clinic_calls(
    clinic_id: uuid.UUID,
    state: Optional[str] = None,
    language: Optional[str] = None,
) -> list[Call]:
    """Backward-compatible wrapper over list_calls (kept for G2 callers)."""
    return await list_calls(
        clinic_id=clinic_id, state=state, language=language
    )


async def get_call(call_id: uuid.UUID) -> Optional[Call]:
    """Get a call by ID."""
    async with SessionFactory() as session:
        return await session.get(Call, call_id)


async def list_calls(
    clinic_id: uuid.UUID,
    state: Optional[str] = None,
    language: Optional[str] = None,
    severity: Optional[str] = None,
    from_: Optional[datetime] = None,
    to: Optional[datetime] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Call]:
    """List calls for a clinic, newest first, with optional filters.

    severity filters on triage_severity; from_/to bound started_at; limit
    capped at 200 by the API router.
    """
    async with SessionFactory() as session:
        query = select(Call).where(Call.clinic_id == clinic_id)
        if state:
            query = query.where(Call.state == state)
        if language:
            query = query.where(Call.caller_language == language)
        if severity:
            query = query.where(Call.triage_severity == severity)
        if from_:
            query = query.where(Call.started_at >= from_)
        if to:
            query = query.where(Call.started_at <= to)
        query = query.order_by(Call.started_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_call(
    clinic_id: uuid.UUID,
    caller_number: str,
    caller_language: str = "en",
    state: str = CallState.GREETING.value,
    **kwargs: Any,
) -> Call:
    """Create a new call record."""
    async with SessionFactory() as session:
        stmt = (
            insert(Call)
            .values(
                clinic_id=clinic_id,
                caller_number=caller_number,
                caller_language=caller_language,
                state=state,
                **kwargs,
            )
            .returning(Call)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def update_call_state(call_id: uuid.UUID, new_state: str) -> bool:
    """Update call state in the state machine."""
    async with SessionFactory() as session:
        stmt = (
            update(Call)
            .where(Call.id == call_id)
            .values(state=new_state, updated_at=now_tz())
            .returning(Call.state)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one() is not None


async def update_call_transcript(
    call_id: uuid.UUID,
    transcript: list,
    ended_at: Optional[datetime] = None,
    duration_seconds: int = 0,
) -> bool:
    """Persist the final transcript + end metadata (G4 /call-completed, D1).

    Idempotent by call_id; ended_at defaults to now when not provided by the
    agent payload.
    """
    async with SessionFactory() as session:
        stmt = (
            update(Call)
            .where(Call.id == call_id)
            .values(
                transcript=transcript,
                ended_at=ended_at or now_tz(),
                duration_seconds=duration_seconds,
                updated_at=now_tz(),
            )
            .returning(Call.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def update_call_consent(call_id: uuid.UUID, consent: str) -> bool:
    """Set the per-call recording-consent flag (G6-Q2 Q1=A1).

    Values: unknown / granted / denied (validated at the API layer against
    consent.RECORDING_CONSENT_STATES). Rides the calls RLS — clinic staff
    write under membership, the in-call voice path under service_request.
    """
    async with SessionFactory() as session:
        stmt = (
            update(Call)
            .where(Call.id == call_id)
            .values(recording_consent=consent, updated_at=now_tz())
            .returning(Call.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def create_appointment(
    clinic_id: uuid.UUID,
    patient_name: str,
    patient_phone: str,
    patient_language: str = "en",
    caller_id: Optional[uuid.UUID] = None,
    scheduled_at: Optional[datetime] = None,
    **kwargs: Any,
) -> Appointment:
    """Create a new appointment."""
    async with SessionFactory() as session:
        stmt = (
            insert(Appointment)
            .values(
                clinic_id=clinic_id,
                patient_name=patient_name,
                patient_phone=patient_phone,
                patient_language=patient_language,
                caller_id=caller_id,
                scheduled_at=scheduled_at,
                **kwargs,
            )
            .returning(Appointment)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def get_appointment(appointment_id: uuid.UUID) -> Optional[Appointment]:
    """Get an appointment by ID."""
    async with SessionFactory() as session:
        return await session.get(Appointment, appointment_id)


async def list_appointments(
    clinic_id: uuid.UUID,
    status: Optional[str] = None,
    from_: Optional[datetime] = None,
    to: Optional[datetime] = None,
) -> list[Appointment]:
    """List appointments for a clinic, soonest first, optional filters."""
    async with SessionFactory() as session:
        query = select(Appointment).where(Appointment.clinic_id == clinic_id)
        if status:
            query = query.where(Appointment.status == status)
        if from_:
            query = query.where(Appointment.scheduled_at >= from_)
        if to:
            query = query.where(Appointment.scheduled_at <= to)
        query = query.order_by(Appointment.scheduled_at)
        result = await session.execute(query)
        return list(result.scalars().all())


async def update_appointment_status(appointment_id: uuid.UUID, status: str) -> bool:
    """Update appointment status; returns True if a row was updated."""
    async with SessionFactory() as session:
        stmt = (
            update(Appointment)
            .where(Appointment.id == appointment_id)
            .values(status=status, updated_at=now_tz())
            .returning(Appointment.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def create_prescription(
    clinic_id: uuid.UUID,
    patient_name: str,
    patient_phone: str,
    medication: str,
    dosage: str = "",
    frequency: str = "",
    instructions: str = "",
    caller_id: Optional[uuid.UUID] = None,
    **kwargs: Any,
) -> Prescription:
    """Create a new prescription."""
    async with SessionFactory() as session:
        stmt = (
            insert(Prescription)
            .values(
                clinic_id=clinic_id,
                patient_name=patient_name,
                patient_phone=patient_phone,
                medication=medication,
                dosage=dosage,
                frequency=frequency,
                instructions=instructions,
                caller_id=caller_id,
                **kwargs,
            )
            .returning(Prescription)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def get_prescription(prescription_id: uuid.UUID) -> Optional[Prescription]:
    """Get a prescription by ID."""
    async with SessionFactory() as session:
        return await session.get(Prescription, prescription_id)


async def list_prescriptions(
    clinic_id: uuid.UUID, status: Optional[str] = None
) -> list[Prescription]:
    """List prescriptions for a clinic, newest first, optional status."""
    async with SessionFactory() as session:
        query = select(Prescription).where(Prescription.clinic_id == clinic_id)
        if status:
            query = query.where(Prescription.status == status)
        query = query.order_by(Prescription.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def update_prescription_status(prescription_id: uuid.UUID, status: str) -> bool:
    """Update prescription status; returns True if a row was updated."""
    async with SessionFactory() as session:
        stmt = (
            update(Prescription)
            .where(Prescription.id == prescription_id)
            .values(status=status, updated_at=now_tz())
            .returning(Prescription.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def create_payment(
    clinic_id: uuid.UUID,
    amount: float,
    currency: str = "INR",
    gateway: Optional[str] = None,
    gateway_ref: Optional[str] = None,
    call_id: Optional[uuid.UUID] = None,
    appointment_id: Optional[uuid.UUID] = None,
    status: str = "pending",
    kind: str = "consultation",
    expires_at: Optional[datetime] = None,
) -> Payment:
    """Create a payment intent (spec-payments.md, G6-Q5).

    Records the intent (consultation/refill/subscription) with an expiry TTL
    for the PAYMENT_EXPIRED leg. The gateway SDK request itself is dispatched
    by the router under service_request_ctx() — this fn only persists.
    """
    if expires_at is None:
        expires_at = now_tz() + timedelta(hours=24)
    async with SessionFactory() as session:
        stmt = (
            insert(Payment)
            .values(
                clinic_id=clinic_id,
                call_id=call_id,
                appointment_id=appointment_id,
                amount=amount,
                currency=currency or "INR",
                gateway=gateway,
                gateway_ref=gateway_ref,
                status=status,
                kind=kind,
                expires_at=expires_at,
            )
            .returning(Payment)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def find_payment_by_gateway_ref(
    gateway: str, gateway_ref: str
) -> Optional[Payment]:
    """Find a payment intent by (gateway, gateway_ref) — webhook idempotency.

    gateway_ref is UNIQUE (partial index uq_payments_gateway_ref) so a
    replayed webhook lands on the same row.
    """
    async with SessionFactory() as session:
        stmt = select(Payment).where(
            Payment.gateway == gateway, Payment.gateway_ref == gateway_ref
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def list_payments(
    clinic_id: uuid.UUID, status: Optional[str] = None
) -> list[Payment]:
    """List payments for a clinic, newest first, optional status."""
    async with SessionFactory() as session:
        query = select(Payment).where(Payment.clinic_id == clinic_id)
        if status:
            query = query.where(Payment.status == status)
        query = query.order_by(Payment.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def get_payment(payment_id: uuid.UUID) -> Optional[Payment]:
    """Get a payment by ID."""
    async with SessionFactory() as session:
        return await session.get(Payment, payment_id)


async def update_payment_status(payment_id: uuid.UUID, status: str) -> bool:
    """Update payment status; returns True if a row was updated."""
    async with SessionFactory() as session:
        stmt = (
            update(Payment)
            .where(Payment.id == payment_id)
            .values(status=status, updated_at=now_tz())
            .returning(Payment.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


# ─── PV / MICC CRUD (spec-micc-pv-module.md) ────────────────────────────────
# Thin persistence only: every rule (classification, the E2B minimum, the
# ICH E2A flags, the India clock, the complaint state machine) lives in
# app/services/pharmacovigilance.py, so it is testable without a database.


async def create_product(
    clinic_id: uuid.UUID,
    name: str,
    generic_name: Optional[str] = None,
    strength: Optional[str] = None,
    dosage_form: Optional[str] = None,
    manufacturer: Optional[str] = None,
    approved_label_json: Optional[dict] = None,
) -> Product:
    """Add a product to a clinic's dictionary (uq_products_identity dedupes)."""
    async with SessionFactory() as session:
        stmt = (
            insert(Product)
            .values(
                clinic_id=clinic_id,
                name=name,
                generic_name=generic_name,
                strength=strength,
                dosage_form=dosage_form,
                manufacturer=manufacturer,
                approved_label_json=approved_label_json,
            )
            .returning(Product)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def find_product(
    clinic_id: uuid.UUID, name: str
) -> Optional[Product]:
    """Look a product up by name within a clinic (catalogue re-import)."""
    async with SessionFactory() as session:
        stmt = select(Product).where(
            Product.clinic_id == clinic_id, Product.name == name
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def list_products(
    clinic_id: uuid.UUID, is_active: Optional[bool] = None
) -> list[Product]:
    """List a clinic's product dictionary, name order."""
    async with SessionFactory() as session:
        query = select(Product).where(Product.clinic_id == clinic_id)
        if is_active is not None:
            query = query.where(Product.is_active.is_(is_active))
        query = query.order_by(Product.name)
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_adverse_event(clinic_id: uuid.UUID, **fields) -> AdverseEvent:
    """Persist one individual case safety report.

    `fields` carries what the intake endpoint resolved: the E2B minimum result,
    the ICH E2A flags, the computed notification_deadline and the parent call.
    """
    async with SessionFactory() as session:
        stmt = (
            insert(AdverseEvent)
            .values(clinic_id=clinic_id, **fields)
            .returning(AdverseEvent)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def get_adverse_event(case_id: uuid.UUID) -> Optional[AdverseEvent]:
    """Get one adverse event by ID."""
    async with SessionFactory() as session:
        return await session.get(AdverseEvent, case_id)


async def list_adverse_events(
    clinic_id: uuid.UUID,
    status: Optional[str] = None,
    serious_only: bool = False,
    limit: int = 50,
) -> list[AdverseEvent]:
    """List a clinic's cases, SOONEST SUBMISSION DEADLINE FIRST.

    The PV dashboard's working order: an overdue serious case must float to
    the top, which created_at-descending would bury.
    """
    async with SessionFactory() as session:
        query = select(AdverseEvent).where(AdverseEvent.clinic_id == clinic_id)
        if status:
            query = query.where(AdverseEvent.status == status)
        query = query.order_by(
            AdverseEvent.notification_deadline.asc(),
            AdverseEvent.received_at.desc(),
        )
        result = await session.execute(query)
        rows = list(result.scalars().all())
        if serious_only:
            rows = [r for r in rows if r.seriousness_flags]
        return rows[: max(1, min(limit, 200))]


async def create_quality_complaint(
    clinic_id: uuid.UUID, **fields
) -> QualityComplaint:
    """Persist one product quality complaint (defect, batch, photos)."""
    async with SessionFactory() as session:
        stmt = (
            insert(QualityComplaint)
            .values(clinic_id=clinic_id, **fields)
            .returning(QualityComplaint)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def get_quality_complaint(complaint_id: uuid.UUID) -> Optional[QualityComplaint]:
    """Get one quality complaint by ID."""
    async with SessionFactory() as session:
        return await session.get(QualityComplaint, complaint_id)


async def list_quality_complaints(
    clinic_id: uuid.UUID, investigation_status: Optional[str] = None
) -> list[QualityComplaint]:
    """List a clinic's complaints, newest first, optional status filter."""
    async with SessionFactory() as session:
        query = select(QualityComplaint).where(
            QualityComplaint.clinic_id == clinic_id
        )
        if investigation_status:
            query = query.where(
                QualityComplaint.investigation_status == investigation_status
            )
        query = query.order_by(QualityComplaint.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def update_quality_complaint(
    complaint_id: uuid.UUID,
    investigation_status: Optional[str] = None,
    disposition: Optional[str] = None,
    capa_ref: Optional[str] = None,
) -> bool:
    """Move a complaint forward. The caller MUST have validated the step.

    Only what is passed is written, so a disposition-only PATCH cannot
    silently reset the state machine. Returns True if a row was updated.
    """
    values: dict[str, Any] = {}
    if investigation_status is not None:
        values["investigation_status"] = investigation_status
    if disposition is not None:
        values["disposition"] = disposition
    if capa_ref is not None:
        values["capa_ref"] = capa_ref
    if not values:
        return False
    values["updated_at"] = now_tz()
    async with SessionFactory() as session:
        stmt = (
            update(QualityComplaint)
            .where(QualityComplaint.id == complaint_id)
            .values(**values)
            .returning(QualityComplaint.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def create_medical_inquiry(clinic_id: uuid.UUID, **fields) -> MedicalInquiry:
    """Persist one medical information inquiry for the MI team."""
    async with SessionFactory() as session:
        stmt = (
            insert(MedicalInquiry)
            .values(clinic_id=clinic_id, **fields)
            .returning(MedicalInquiry)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def list_medical_inquiries(
    clinic_id: uuid.UUID, status: Optional[str] = None
) -> list[MedicalInquiry]:
    """List a clinic's inquiries, newest first, optional status filter."""
    async with SessionFactory() as session:
        query = select(MedicalInquiry).where(
            MedicalInquiry.clinic_id == clinic_id
        )
        if status:
            query = query.where(MedicalInquiry.status == status)
        query = query.order_by(MedicalInquiry.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_notification(
    clinic_id: uuid.UUID,
    kind: str,
    recipient: str,
    language: str = "en",
    params: Optional[str] = None,
    channel: Optional[str] = None,
    provider: Optional[str] = None,
    provider_ref: Optional[str] = None,
    status: str = "queued",
    template: Optional[str] = None,
) -> Notification:
    """Persist one delivery record (spec-notifications-q8.md Q4=A4a).

    Called by the identity-gated /send endpoint; the payment-create hook runs
    it inside service_request_ctx() so the RLS bypass (notifications_send)
    covers server-side extends. The row feeds the DPDP audit trail (G6-Q2).
    """
    async with SessionFactory() as session:
        stmt = (
            insert(Notification)
            .values(
                clinic_id=clinic_id,
                kind=kind,
                recipient=recipient,
                language=language,
                params=params,
                channel=channel,
                provider=provider,
                provider_ref=provider_ref,
                status=status,
                template=template,
            )
            .returning(Notification)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def list_notifications(
    clinic_id: uuid.UUID, status: Optional[str] = None
) -> list[Notification]:
    """List delivery records for a clinic, newest first, optional status."""
    async with SessionFactory() as session:
        query = select(Notification).where(Notification.clinic_id == clinic_id)
        if status:
            query = query.where(Notification.status == status)
        query = query.order_by(Notification.created_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def create_compliance_event(
    clinic_id: uuid.UUID,
    event_type: str,
    severity: str = "medium",
    description: Optional[str] = None,
    detected_at: Optional[datetime] = None,
) -> ComplianceEvent:
    """Record a compliance event with its 72-hr DPDP breach deadline (G6-Q2).

    notification_deadline = detected_at + DPDP_BREACH_NOTIFICATION_HOURS
    (default 72h) via compliance.breach_notification_deadline — a bad/missing
    env value cannot zero the deadline (falls back to 72).
    """
    detected = detected_at or now_tz()
    async with SessionFactory() as session:
        stmt = (
            insert(ComplianceEvent)
            .values(
                clinic_id=clinic_id,
                event_type=event_type,
                severity=severity,
                description=description,
                detected_at=detected,
                notification_deadline=breach_notification_deadline(detected),
                status="open",
            )
            .returning(ComplianceEvent)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def list_compliance_events(
    clinic_id: uuid.UUID, status: Optional[str] = None
) -> list[ComplianceEvent]:
    """List compliance events for a clinic, newest first, optional status."""
    async with SessionFactory() as session:
        query = select(ComplianceEvent).where(
            ComplianceEvent.clinic_id == clinic_id
        )
        if status:
            query = query.where(ComplianceEvent.status == status)
        query = query.order_by(ComplianceEvent.detected_at.desc())
        result = await session.execute(query)
        return list(result.scalars().all())


async def update_compliance_event(
    event_id: uuid.UUID,
    status: Optional[str] = None,
    severity: Optional[str] = None,
) -> bool:
    """Update status/severity; status='reported' stamps reported_at (never
    un-stamps it on a later 'closed' transition)."""
    values: dict[str, Any] = {}
    if status is not None:
        values["status"] = status
        if status == "reported":
            values["reported_at"] = now_tz()
    if severity is not None:
        values["severity"] = severity
    if not values:
        return False
    values["updated_at"] = now_tz()
    async with SessionFactory() as session:
        stmt = (
            update(ComplianceEvent)
            .where(ComplianceEvent.id == event_id)
            .values(**values)
            .returning(ComplianceEvent.id)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one_or_none() is not None


async def purge_expired(
    kind: str, env: Optional[dict] = None, now: Optional[datetime] = None
) -> int:
    """Delete rows past their retention deadline (G6-Q2 Q2=A1).

    Driven by the Docker/CI scheduler cron — NEVER auto-runs on this PC.
    `calls` purge cascade-deletes call_embeddings via FK; the audit category
    (`audit`, 6 yr) covers compliance_events; `recordings` are external
    MinIO/S3 objects (LiveKit egress) with no row here — their purge is a
    Docker follow-on. Returns the number of rows deleted.
    """
    cutoff = retention_deadline(now_tz() if now is None else now, kind, env=env)
    model = {
        "calls": Call,
        "notifications": Notification,
        "audit": ComplianceEvent,
    }.get(kind)
    if model is None:
        return 0
    async with SessionFactory() as session:
        stmt = delete(model).where(model.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount if result.rowcount is not None else 0


# ─── G6-Q9 MVP KPI aggregates ──────────────────────────────────────────────
# Per-KPI read-only rollups over calls / appointments / payments /
# notifications (spec-kpis-q9.md Q3=A1: pure computed, no writes). Every
# query filters on clinic_id and the window; RLS still applies because the
# queries run as the authenticated app user (clinic membership). The service
# layer (services/analytics.py) shapes these into the payload + derives rates.


async def compute_volume(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Call volume: total, by_state, by_day, duration sum/count.

    by_day uses func.date(Call.started_at) so the payload is a plain
    YYYY-MM-DD key map for the dashboard volume chart.
    """
    async with SessionFactory() as session:
        base = (Call.clinic_id == clinic_id,
                Call.started_at >= from_, Call.started_at <= to)
        total = (
            await session.execute(select(func.count(Call.id)).where(*base))
        ).scalar_one()
        state_rows = (
            await session.execute(
                select(Call.state, func.count(Call.id))
                .where(*base)
                .group_by(Call.state)
            )
        ).all()
        day_rows = (
            await session.execute(
                select(func.date(Call.started_at), func.count(Call.id))
                .where(*base)
                .group_by(func.date(Call.started_at))
            )
        ).all()
        duration_sum, duration_count = (
            await session.execute(
                select(
                    func.coalesce(func.sum(Call.duration_seconds), 0),
                    func.count(Call.duration_seconds),
                ).where(*base)
            )
        ).one()
        by_state = {state: n for state, n in state_rows}
        by_day = {str(day): n for day, n in day_rows}
        return {
            "total": total,
            "by_state": by_state,
            "by_day": by_day,
            "duration_sum": int(duration_sum or 0),
            "duration_count": int(duration_count or 0),
        }


async def compute_resolution(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Terminal outcome counts: COMPLETE / DROPPED / ESCALATED / PAYMENT_EXPIRED.

    PAYMENT_SENT is in-progress by design — the resolution_rate in the
    service derives from these four buckets only.
    """
    terminal = ("COMPLETE", "DROPPED", "ESCALATED", "PAYMENT_EXPIRED")
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Call.state, func.count(Call.id))
                .where(
                    Call.clinic_id == clinic_id,
                    Call.started_at >= from_,
                    Call.started_at <= to,
                    Call.state.in_(terminal),
                )
                .group_by(Call.state)
            )
        ).all()
    counts = {"COMPLETE": 0, "DROPPED": 0, "ESCALATED": 0, "PAYMENT_EXPIRED": 0}
    for state, n in rows:
        counts[state] = n
    return counts


async def compute_triage(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Severity distribution (green/amber/red/critical) + untriaged bucket."""
    async with SessionFactory() as session:
        base = (Call.clinic_id == clinic_id,
                Call.started_at >= from_, Call.started_at <= to)
        total = (
            await session.execute(select(func.count(Call.id)).where(*base))
        ).scalar_one()
        rows = (
            await session.execute(
                select(Call.triage_severity, func.count(Call.id))
                .where(*base, Call.triage_severity.isnot(None))
                .group_by(Call.triage_severity)
            )
        ).all()
    counts = {"green": 0, "amber": 0, "red": 0, "critical": 0}
    for severity, n in rows:
        if severity in counts:
            counts[severity] = n
    counts["untriaged"] = total - sum(counts.values())
    return counts


async def compute_language(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Calls per caller_language (hi/en/ta/te/bn); null/unknown -> unknown."""
    known = ("hi", "en", "ta", "te", "bn")
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Call.caller_language, func.count(Call.id))
                .where(
                    Call.clinic_id == clinic_id,
                    Call.started_at >= from_,
                    Call.started_at <= to,
                )
                .group_by(Call.caller_language)
            )
        ).all()
    counts = {"hi": 0, "en": 0, "ta": 0, "te": 0, "bn": 0, "unknown": 0}
    for language, n in rows:
        counts[language if language in known else "unknown"] += n
    return counts


async def compute_no_show(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Terminal appointment counts: no_show / completed / cancelled.

    pending/confirmed bookings are excluded (they are not yet due); the
    service derives no_show_rate from these three.
    """
    terminal = ("no_show", "completed", "cancelled")
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(Appointment.status, func.count(Appointment.id))
                .where(
                    Appointment.clinic_id == clinic_id,
                    Appointment.scheduled_at >= from_,
                    Appointment.scheduled_at <= to,
                    Appointment.status.in_(terminal),
                )
                .group_by(Appointment.status)
            )
        ).all()
    counts = {"no_show": 0, "completed": 0, "cancelled": 0}
    for status, n in rows:
        counts[status] = n
    return counts


async def compute_revenue(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Captured / refunded sums + captured by kind + currency (default INR)."""
    async with SessionFactory() as session:
        base = (Payment.clinic_id == clinic_id,
                Payment.created_at >= from_, Payment.created_at <= to)
        refunded = (
            await session.execute(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .where(*base, Payment.status == "refunded")
            )
        ).scalar_one()
        kind_rows = (
            await session.execute(
                select(Payment.kind, func.sum(Payment.amount))
                .where(*base, Payment.status == "captured")
                .group_by(Payment.kind)
            )
        ).all()
        currency = (
            await session.execute(
                select(Payment.currency).where(*base).limit(1)
            )
        ).scalar()
    captured = 0.0
    by_kind = {"consultation": 0.0, "refill": 0.0, "subscription": 0.0}
    for kind, amount in kind_rows:
        amount = float(amount or 0)
        captured += amount
        if kind in by_kind:
            by_kind[kind] = amount
    return {
        "captured": round(captured, 2),
        "refunded": round(float(refunded or 0), 2),
        "by_kind": by_kind,
        "currency": currency or "INR",
    }


async def compute_delivery(
    clinic_id: uuid.UUID, from_: datetime, to: datetime
) -> dict:
    """Per-kind {sent, failed} counts for notifications in the window.

    queued rows are in-flight and excluded from both buckets; the service
    derives total + success_rate per kind.
    """
    async with SessionFactory() as session:
        rows = (
            await session.execute(
                select(
                    Notification.kind,
                    Notification.status,
                    func.count(Notification.id),
                )
                .where(
                    Notification.clinic_id == clinic_id,
                    Notification.created_at >= from_,
                    Notification.created_at <= to,
                    Notification.status.in_(("sent", "failed")),
                )
                .group_by(Notification.kind, Notification.status)
            )
        ).all()
    per_kind = {}
    for kind, status, n in rows:
        entry = per_kind.setdefault(kind, {"sent": 0, "failed": 0})
        entry[status] = n
    return per_kind


# ─── Platform aggregates (G6-Q11 — /api/admin router, role-gated) ───────────
# Cross-tenant read-only aggregates for the platform admin surface. Each fn
# arms service_request_ctx() internally (the auth-CRUD pattern) so the RLS
# FORCE policies admit the reads; the ONLY gate is require_roles(
# "platform_admin") at the API layer — clinic-scoped code never calls these.

TERMINAL_STATES = ("COMPLETE", "DROPPED", "ESCALATED", "PAYMENT_EXPIRED")


async def platform_overview() -> dict:
    """Cross-clinic headline numbers for the admin overview page."""
    today = now_tz().replace(hour=0, minute=0, second=0, microsecond=0)
    with service_request_ctx():
        async with SessionFactory() as session:
            clinics_total = (
                await session.execute(select(func.count(Clinic.id)))
            ).scalar_one()
            clinics_active = (
                await session.execute(
                    select(func.count(Clinic.id)).where(Clinic.is_active.is_(True))
                )
            ).scalar_one()
            calls_today = (
                await session.execute(
                    select(func.count(Call.id)).where(Call.started_at >= today)
                )
            ).scalar_one()
            live_calls = (
                await session.execute(
                    select(func.count(Call.id)).where(
                        Call.state.notin_(TERMINAL_STATES)
                    )
                )
            ).scalar_one()
            revenue_today = (
                await session.execute(
                    select(func.coalesce(func.sum(Payment.amount), 0)).where(
                        Payment.created_at >= today,
                        Payment.status == "captured",
                    )
                )
            ).scalar_one()
    return {
        "clinics_total": int(clinics_total),
        "clinics_active": int(clinics_active),
        "calls_today": int(calls_today),
        "live_calls": int(live_calls),
        "revenue_today_inr": round(float(revenue_today or 0), 2),
    }


async def platform_clinics() -> list[dict]:
    """Every clinic with MTD/today/live call aggregates, ordered by name.

    Serialized inside the session block (ORM attribute reads must not outlive
    the session close).
    """
    month_start = now_tz().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today = now_tz().replace(hour=0, minute=0, second=0, microsecond=0)
    with service_request_ctx():
        async with SessionFactory() as session:
            clinics = (
                (await session.execute(select(Clinic).order_by(Clinic.name)))
                .scalars()
                .all()
            )
            mtd_rows = (
                await session.execute(
                    select(Call.clinic_id, func.count(Call.id))
                    .where(Call.started_at >= month_start)
                    .group_by(Call.clinic_id)
                )
            ).all()
            today_rows = (
                await session.execute(
                    select(Call.clinic_id, func.count(Call.id))
                    .where(Call.started_at >= today)
                    .group_by(Call.clinic_id)
                )
            ).all()
            live_rows = (
                await session.execute(
                    select(Call.clinic_id, func.count(Call.id))
                    .where(Call.state.notin_(TERMINAL_STATES))
                    .group_by(Call.clinic_id)
                )
            ).all()
            mtd = {cid: n for cid, n in mtd_rows}
            tc = {cid: n for cid, n in today_rows}
            lv = {cid: n for cid, n in live_rows}
            out = [
                {
                    "id": str(c.id),
                    "name": c.name,
                    "city": c.city,
                    "state": c.state,
                    "plan": c.plan,
                    "is_active": c.is_active,
                    "calls_mtd": int(mtd.get(c.id, 0)),
                    "calls_today": int(tc.get(c.id, 0)),
                    "live_calls": int(lv.get(c.id, 0)),
                }
                for c in clinics
            ]
    return out


async def platform_patients() -> list[dict]:
    """Distinct callers across clinics (admin patients view).

    A caller may span clinics, so the row carries their most recent call's
    clinic (id + name) and state; counts aggregate over all their calls.
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            rows = (
                await session.execute(
                    select(
                        Call.caller_number,
                        Call.caller_language,
                        func.count(Call.id),
                        func.min(Call.started_at),
                        func.max(Call.started_at),
                    )
                    .where(Call.caller_number.isnot(None))
                    .group_by(Call.caller_number, Call.caller_language)
                )
            ).all()
            latest_rows = (
                await session.execute(
                    select(
                        Call.caller_number,
                        Call.clinic_id,
                        Clinic.name,
                        Call.state,
                    )
                    .join(Clinic, Call.clinic_id == Clinic.id)
                    .where(Call.caller_number.isnot(None))
                    .order_by(Call.started_at.desc())
                )
            ).all()
    latest = {}
    for number, clinic_id, clinic_name, state in latest_rows:
        latest.setdefault(number, (str(clinic_id), clinic_name, state))
    out = []
    for number, language, count, first_at, last_at in rows:
        clinic_id, clinic_name, state = latest.get(number, (None, None, None))
        out.append(
            {
                "caller_number": number,
                "clinic_id": clinic_id,
                "clinic_name": clinic_name,
                "language": language,
                "first_call_at": first_at.isoformat() if first_at else None,
                "last_call_at": last_at.isoformat() if last_at else None,
                "call_count": int(count),
                "last_state": state,
            }
        )
    out.sort(key=lambda r: r["last_call_at"] or "", reverse=True)
    return out


async def platform_revenue() -> dict:
    """Cross-clinic revenue: captured/pending/failed/refunded sums + counts,
    captured by gateway, and captured by clinic (top first)."""
    with service_request_ctx():
        async with SessionFactory() as session:
            status_rows = (
                await session.execute(
                    select(
                        Payment.status,
                        func.coalesce(func.sum(Payment.amount), 0),
                        func.count(Payment.id),
                    ).group_by(Payment.status)
                )
            ).all()
            gateway_rows = (
                await session.execute(
                    select(
                        Payment.gateway,
                        func.coalesce(func.sum(Payment.amount), 0),
                        func.count(Payment.id),
                    )
                    .where(Payment.status == "captured")
                    .group_by(Payment.gateway)
                )
            ).all()
            clinic_rows = (
                await session.execute(
                    select(
                        Clinic.id,
                        Clinic.name,
                        func.coalesce(func.sum(Payment.amount), 0),
                        func.count(Payment.id),
                    )
                    .join(Payment, Payment.clinic_id == Clinic.id)
                    .where(Payment.status == "captured")
                    .group_by(Clinic.id, Clinic.name)
                    .order_by(func.sum(Payment.amount).desc())
                )
            ).all()
    totals = {"captured": 0.0, "pending": 0.0, "failed": 0.0, "refunded": 0.0}
    count_by_status = {"captured": 0, "pending": 0, "failed": 0, "refunded": 0}
    for status, amount, n in status_rows:
        if status in totals:
            totals[status] = round(float(amount or 0), 2)
            count_by_status[status] = int(n)
    by_gateway = {
        gateway or "unknown": {
            "captured_inr": round(float(amount or 0), 2),
            "count": int(n),
        }
        for gateway, amount, n in gateway_rows
    }
    by_clinic = [
        {
            "clinic_id": str(cid),
            "clinic_name": name,
            "captured_inr": round(float(amount or 0), 2),
            "count": int(n),
        }
        for cid, name, amount, n in clinic_rows
    ]
    return {
        "captured_inr": totals["captured"],
        "pending_inr": totals["pending"],
        "failed_inr": totals["failed"],
        "refunded_inr": totals["refunded"],
        "count": count_by_status["captured"],
        "by_gateway": by_gateway,
        "by_clinic": by_clinic,
    }


async def platform_calls(limit: int = 50, offset: int = 0) -> list[dict]:
    """Recent calls across clinics (admin live feed), newest first.

    limit capped at 200 (mirrors the clinic-scoped list_calls pagination).
    """
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    with service_request_ctx():
        async with SessionFactory() as session:
            rows = (
                await session.execute(
                    select(
                        Call.id,
                        Call.clinic_id,
                        Clinic.name.label("clinic_name"),
                        Call.caller_number,
                        Call.caller_language,
                        Call.state,
                        Call.triage_severity,
                        Call.started_at,
                        Call.duration_seconds,
                    )
                    .join(Clinic, Call.clinic_id == Clinic.id)
                    .order_by(Call.started_at.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
    return [
        {
            "id": str(cid),
            "clinic_id": str(clinic_id),
            "clinic_name": clinic_name,
            "caller_number": caller_number,
            "language": caller_language,
            "state": state,
            "severity": triage_severity,
            "started_at": started_at.isoformat() if started_at else None,
            "duration_seconds": int(duration or 0),
        }
        for (
            cid,
            clinic_id,
            clinic_name,
            caller_number,
            caller_language,
            state,
            triage_severity,
            started_at,
            duration,
        ) in rows
    ]


async def log_call_embedding(
    call_id: uuid.UUID,
    embedding: list,
    embedding_type: str = "call_analysis",
) -> CallEmbedding:
    """Insert or update a call embedding (call_id is UNIQUE)."""
    async with SessionFactory() as session:
        existing = (
            await session.execute(
                select(CallEmbedding).where(CallEmbedding.call_id == call_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.embedding = embedding
            existing.embedding_type = embedding_type
            await session.commit()
            return existing
        stmt = (
            insert(CallEmbedding)
            .values(
                call_id=call_id,
                embedding=embedding,
                embedding_type=embedding_type,
            )
            .returning(CallEmbedding)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


async def get_call_embedding(call_id: uuid.UUID) -> Optional[CallEmbedding]:
    """Retrieve call embedding by call_id."""
    async with SessionFactory() as session:
        return (
            await session.execute(
                select(CallEmbedding).where(CallEmbedding.call_id == call_id)
            )
        ).scalar_one_or_none()


async def list_language_codes(active_only: bool = True) -> list[LanguageCode]:
    """List language codes, optionally active-only."""
    async with SessionFactory() as session:
        query = select(LanguageCode)
        if active_only:
            query = query.where(LanguageCode.is_active.is_(True))
        query = query.order_by(LanguageCode.code)
        result = await session.execute(query)
        return list(result.scalars().all())


# ─── Auth CRUD (Phase-1, G6-Q1 — used by app/api/auth.py) ───────────────────

async def create_user(
    name: str,
    password_hash: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    role: str = "staff",
) -> User:
    """Create an application user (register flow).

    Pre-authentication code path: runs with NO current user, so the service
    bypass is armed (users_own_data OR app.service_request allows the insert).
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            stmt = (
                insert(User)
                .values(
                    name=name,
                    phone=phone,
                    email=(email or "").lower() or None,
                    password_hash=password_hash,
                    role=role,
                )
                .returning(User)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.scalar_one()


async def get_user(user_id: uuid.UUID) -> Optional[User]:
    """Fetch a user by id."""
    async with SessionFactory() as session:
        return await session.get(User, user_id)


async def find_user(username: str) -> Optional[User]:
    """Find a user by phone (exact) or email (case-insensitive).

    Pre-authentication (login/OTP lookup): service bypass armed so the row is
    visible before any token exists.
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            if username.startswith("+"):
                stmt = select(User).where(User.phone == username)
            else:
                stmt = select(User).where(User.email == username.strip().lower())
            result = await session.execute(stmt)
            return result.scalar_one_or_none()


async def set_user_otp(
    user_id: uuid.UUID, code_hash: str, expires_at: datetime
) -> None:
    """Store the hashed OTP + expiry; resets the attempt counter.

    Pre-authentication path -> service bypass armed.
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    otp_code_hash=code_hash,
                    otp_expires_at=expires_at,
                    otp_attempts=0,
                    updated_at=now_tz(),
                )
                .returning(User.id)
            )
            await session.execute(stmt)
            await session.commit()


async def bump_user_otp_attempts(user_id: uuid.UUID) -> int:
    """Increment the failed-OTP counter; returns the new count.

    Pre-authentication path -> service bypass armed.
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            user = await session.get(User, user_id)
            if user is None:
                return 0
            user.otp_attempts = (user.otp_attempts or 0) + 1
            await session.commit()
            return user.otp_attempts


async def clear_user_otp(user_id: uuid.UUID) -> None:
    """Wipe OTP state after a successful verification.

    Pre-authentication path -> service bypass armed.
    """
    with service_request_ctx():
        async with SessionFactory() as session:
            stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    otp_code_hash=None,
                    otp_expires_at=None,
                    otp_attempts=0,
                    updated_at=now_tz(),
                )
                .returning(User.id)
            )
            await session.execute(stmt)
            await session.commit()


async def list_clinic_memberships(user_id: uuid.UUID) -> list[ClinicUser]:
    """Clinic memberships for /api/auth/me."""
    async with SessionFactory() as session:
        stmt = select(ClinicUser).where(ClinicUser.user_id == user_id)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ─── Migration Entrypoint ──────────────────────────────────────────────────


async def init_db() -> None:
    """Create all tables (dev/test). Prod uses postgres_schema.sql + Alembic."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


# ─── Main ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import asyncio

    async def _self_check() -> None:
        tables = sorted(Base.metadata.tables.keys())
        print("MediCall AI Async PostgreSQL Client")
        print(f"Database URL: {DATABASE_URL}")
        print(f"Tables: {', '.join(tables)}")

    asyncio.run(_self_check())
