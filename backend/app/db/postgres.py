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
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.call import CallState, TriageSeverity
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
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

# Supported caller/patient languages: Hindi, English, Tamil, Telugu, Bengali.
SUPPORTED_LANGUAGES = ("hi", "en", "ta", "te", "bn")


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
) -> Payment:
    """Create a payment intent record (scaffold — no gateway SDK call, G6-Q5)."""
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
            )
            .returning(Payment)
        )
        result = await session.execute(stmt)
        await session.commit()
        return result.scalar_one()


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
