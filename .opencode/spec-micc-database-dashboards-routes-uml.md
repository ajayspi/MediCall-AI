# SPEC: MediCall AI — Database Schemas, Dashboards, Routes & UML Diagrams

## Goal
Spec-first design of the MediCall AI database layer, dashboard interfaces, API routes, and UML diagrams for an Indian Medical Call Center. Replaces Supabase with local PostgreSQL + pgvector, adapts all code for voice-first multi-language (Hindi/English/Tamil/Telugu/Bengali) medical call flow with Indian payment gateways and telephony providers.

**Core Differentiator**: Voice-first call state machine + pgvector for medical embeddings + multi-language STT/TTS + Indian payment/telephony integrations.

## Non-Goals
- No Supabase integration (deferred to future project)
- No restaurant/order/Square/Stripe code
- No monolithic HMS features (out of scope for call center)
- No single-tenant deployment as default

## Existing Codebase Context (from Project Audit)

### Files to REPLACE (Supabase → PostgreSQL)
| File | Current | replacement |
|------|---------|-------------|
| `backend/supabase_schema.sql` | Restaurant-focused Supabase schema | `postgres_schema.sql` — Medical call center + pgvector |
| `backend/app/db/supabase.py` | Supabase client (`create_client`) | `backend/app/db/postgres.py` — Async SQLAlchemy + asyncpg |
| `backend/app/api/orders.py` | Restaurant orders API | Medical call-related API endpoints |
| `backend/app/api/payments.py` | Stripe/Square payments | Indian gateways: Razorpay + PhonePe + Cashfree |
| `backend/app/api/admin.py` | Restaurant admin panel | Medical admin panel (clinics, doctors, patients) |
| `backend/app/Models/order.py` | Restaurant order model | `call.py` — Medical call state machine (KEPT/adapted) |
| `backend/app/Models/restaurant.py` | Restaurant model | Adapt for medical patients/providers |

### Files to KEEP (adapt for medical)
| File | Adaptation |
|------|------------|
| `backend/main.py` | Medical API routes |
| `backend/app/models/call.py` | Medical call state machine (KEPT, already voice-first) |
| `backend/app/api/voice.py` | Multi-provider telephony (Exotel/Knowlarity/Twilio) |
| `backend/app/services/livekit_agent.py` | Medical agent logic |
| `backend/app/services/llm.py` | Medical prompts |
| `backend/app/services/stt.py` | Multi-language STT (Deepgram 5 languages) |
| `backend/app/services/tts.py` | Multi-language TTS (ElevenLabs) |
| `backend/app/db/redis.py` | Keep as-is |
| `backend/Dockerfile` | Adapt for PostgreSQL + pgvector |

## 1. Database Schemas (PostgreSQL + pgvector)

### 1.1 `backend/postgres_schema.sql`
New schema replacing `supabase_schema.sql`. Medical call center focused with pgvector for embeddings.

```sql
-- TalkByte AI → MediCall AI Migration: PostgreSQL + pgvector Schema
-- Run: psql -U ubuntu -d mediacall -f backend/postgres_schema.sql

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core: Clinics/Facilities (replaces restaurants)
CREATE TABLE clinics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    phone_number TEXT NOT NULL,
    address TEXT,
    city TEXT NOT NULL,
    state TEXT NOT NULL,
    pincode TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    closing_time TIME DEFAULT '22:00',
    ai_instructions TEXT DEFAULT '',
    plan TEXT DEFAULT 'starter',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Multi-tenant: Clinic staff/users
CREATE TABLE clinic_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'staff', -- owner, staff, readonly, triage_agent
    language_pref TEXT DEFAULT 'en', -- hi, en, ta, te, bn
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(clinic_id, user_id)
);

-- Calls (core entity: voice-first medical call center)
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    caller_number TEXT NOT NULL,
    caller_language TEXT DEFAULT 'en', -- hi, en, ta, te, bn
    state TEXT DEFAULT 'GREETING', -- GREETING, TRIAGE, APPOINTMENT, PRESCRIPTION, COMPLETE, ESCALATED, DROPPED
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    transcript JSONB DEFAULT '[]', -- Multi-language transcript [{"role":"caller","text":"...","language":"hi"}]
    stt_confidence REAL DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    triage_severity TEXT, -- green, amber, red, critical (from triage AI)
    diagnosed_conditions JSONB DEFAULT '[]', -- SNOMED CT codes
    prescription_issued BOOLEAN DEFAULT FALSE,
    appointment_scheduled BOOLEAN DEFAULT FALSE,
    appointment_id UUID,
    escalated_to_human BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments (derived from call triage)
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    patient_name TEXT,
    patient_phone TEXT,
    patient_language TEXT DEFAULT 'en',
    caller_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, confirmed, completed, cancelled, no_show
    reason TEXT, -- chief complaint summary
    doctor_id UUID,
    duration_minutes INTEGER DEFAULT 30,
    location TEXT, -- clinic address or telemedicine link
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Prescriptions (from call triage + doctor review)
CREATE TABLE prescriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    patient_name TEXT,
    patient_phone TEXT,
    patient_language TEXT DEFAULT 'en',
    caller_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    medication TEXT NOT NULL,
    dosage TEXT,
    frequency TEXT,
    instructions TEXT,
    doctor_id UUID,
    status TEXT DEFAULT 'pending', -- pending, approved, sent_pharmacy, dispensed
    pharmacy_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Medical embeddings (pgvector for similar call search, symptom clustering)
CREATE TABLE call_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    embedding VECTOR(1536), -- 1536-dim embedding (Deepgram/ElevenLabs/LLM)
    embedding_type TEXT DEFAULT 'call_analysis', -- call_analysis, triage_summary, prescription_summary
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indian languages reference (for STT/TTS model mapping)
CREATE TABLE language_codes (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE, -- hi, en, ta, te, bn
    script TEXT DEFAULT 'Latin/Devanagari/Tamil/Telugu/Bengali',
    deepgram_model TEXT DEFAULT 'nova-3', -- model name or identifier
    elevenlabs_voice_id TEXT, -- voice identifier for TTS
    is_active BOOLEAN DEFAULT TRUE
);

INSERT INTO language_codes (code, script, deepgram_model, elevenlabs_voice_id, is_active) VALUES
('en', 'Latin', 'nova-3', NULL, TRUE),
('hi', 'Devanagari', 'nova-3', NULL, TRUE),
('ta', 'Tamil', 'nova-3', NULL, TRUE),
('te', 'Telugu', 'nova-3', NULL, TRUE),
('bn', 'Bengali', 'nova-3', NULL, TRUE);

-- Call sessions / active calls (lightweight tracking)
CREATE TABLE call_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    clinic_id UUID REFERENCES clinics(id) ON DELETE SET NULL,
    livekit_room TEXT, -- LiveKit room ID for this call
    livekit_participant_id TEXT,
    status TEXT DEFAULT 'idle', -- idle, recording, in_progress, completed, failed
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ,
    CONSTRAINT fk_call FOREIGN KEY (call_id) REFERENCES calls(id) ON DELETE CASCADE
);

-- Indexes for call center performance
CREATE INDEX idx_calls_clinic ON calls(clinic_id);
CREATE INDEX idx_calls_state ON calls(state);
CREATE INDEX idx_calls_language ON calls(caller_language);
CREATE INDEX idx_calls_started ON calls(started_at DESC);
CREATE INDEX idx_appointments_clinic_status ON appointments(clinic_id, status);
CREATE INDEX idx_appointments_scheduled ON appointments(scheduled_at);
CREATE INDEX idx_calls_triage ON calls(triage_severity) WHERE triage_severity IS NOT NULL;
CREATE INDEX idx_call_embeddings_call ON call_embeddings(call_id);

-- pgvector similarity search function: find similar calls
CREATE OR REPLACE FUNCTION search_similar_calls(
    clinic_uuid UUID,
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    similarity REAL
) LANGUAGE sql AS $$
    SELECT
        c.id,
        1 - (ce.embedding <=> query_embedding) AS similarity
    FROM call_embeddings ce
    JOIN calls c ON ce.call_id = c.id
    WHERE c.clinic_id = clinic_uuid
      AND c.state IN ('COMPLETE', 'ESCALATED')
    ORDER BY ce.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- pgvector similarity search: find calls with similar symptoms
CREATE OR REPLACE FUNCTION search_calls_by_symptoms(
    clinic_uuid UUID,
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 10
)
RETURNS TABLE (
    call_id UUID,
    caller_number TEXT,
    similarity REAL,
    state TEXT,
    severity TEXT
) LANGUAGE sql AS $$
    SELECT
        c.id AS call_id,
        c.caller_number,
        1 - (ce.embedding <=> query_embedding) AS similarity,
        c.state,
        c.triage_severity
    FROM call_embeddings ce
    JOIN calls c ON ce.call_id = c.id
    WHERE c.clinic_id = clinic_uuid
    ORDER BY ce.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- Trigger for updated_at on core tables
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER update_clinics_updated_at BEFORE UPDATE ON clinics
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_calls_updated_at BEFORE UPDATE ON calls
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_appointments_updated_at BEFORE UPDATE ON appointments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_prescriptions_updated_at BEFORE UPDATE ON prescriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Row Level Security (RLS) — multi-tenant
ALTER TABLE clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinic_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;

-- Clinic owners see their own clinic
CREATE POLICY clinic_own_data ON clinics
    FOR ALL USING (
        id IN (
            SELECT clinic_id FROM clinic_users 
            WHERE user_id = auth.uid() AND role = 'owner'
        )
    );

-- Staff can read clinic
CREATE POLICY clinic_staff_read ON clinics
    FOR SELECT USING (
        id IN (
            SELECT clinic_id FROM clinic_users 
            WHERE user_id = auth.uid()
        )
    );

-- Staff can create/read calls
CREATE POLICY calls_create ON calls
    FOR INSERT WITH CHECK (clinic_id IN (
        SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
    ));

CREATE POLICY calls_read ON calls
    FOR SELECT USING (clinic_id IN (
        SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
    ));

-- Appointments: clinic staff can manage
CREATE POLICY appointments_manage ON appointments
    FOR ALL USING (clinic_id IN (
        SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
    ));

-- Language codes: always readable
CREATE POLICY language_codes_read ON language_codes
    FOR SELECT USING (is_active = TRUE);
```

### 1.2 `backend/app/db/postgres.py`
Async SQLAlchemy + asyncpg replacement for `supabase.py`:

```python
"""Async PostgreSQL + pgvector database client for MediCall AI."""
from sqlalchemy import (
    create_engine, Engine, event, inspect, text,
    MetaData, Table, Column, UUID, String, Text, Integer, DateTime, 
    Boolean, JSONB, ForeignKey, PrimaryKeyConstraint, Index
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, declared_attr, Mapped, mapped_column
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
import asyncpg
import os
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

Base = declarative_base()

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://ubuntu:password@localhost:5432/mediacall")
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "30"))
SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")

# Engine factory
def get_engine() -> AsyncEngine:
    """Create async SQLAlchemy engine with pgvector support."""
    if os.getenv("DB_ENV") == "test":
        engine: AsyncEngine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            poolclass=NullPool,
        )
    else:
        engine: AsyncEngine = create_async_engine(
            DATABASE_URL,
            echo=os.getenv("DB_ECHO", "false").lower() == "true",
            poolclass=AsyncAdaptedQueuePool,
            pool_size=POOL_SIZE,
            max_overflow=MAX_OVERFLOW,
            pool_timeout=30,
        )
    return engine

engine: AsyncEngine = get_engine()

# Region: Database Models (SQLAlchemy 2.0 style)

class Clinic(Base):
    __tablename__ = "clinics"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
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
    plan: Mapped[str] = mapped_column(String(50), default="starter")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ClinicUser(Base):
    __tablename__ = "clinic_users"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("clinics.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUID, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="staff") -- owner, staff, readonly, triage_agent
    language_pref: Mapped[str] = mapped_column(String(5), default="en") -- hi, en, ta, te, bn
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (UniqueConstraint("clinic_id", "user_id"),)

class Call(Base):
    __tablename__ = "calls"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("clinics.id"), nullable=False)
    caller_number: Mapped[str] = mapped_column(String(30), nullable=False)
    caller_language: Mapped[str] = mapped_column(String(5), default="en") -- hi, en, ta, te, bn
    state: Mapped[str] = mapped_column(String(20), default="GREETING") -- GREETING, TRIAGE, APPOINTMENT, PRESCRIPTION, COMPLETE, ESCALATED, DROPPED
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    transcript: Mapped[List[Dict]] = mapped_column(JSONB, default=[])
    stt_confidence: Mapped[float] = mapped_column(default=0.0)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    triage_severity: Mapped[Optional[str]] = mapped_column(String(10)) -- green, amber, red, critical
    diagnosed_conditions: Mapped[List[str]] = mapped_column(JSONB, default="[]")
    prescription_issued: Mapped[bool] = mapped_column(Boolean, default=False)
    appointment_scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    appointment_id: Mapped[Optional[UUID]] = mapped_column(UUID, ForeignKey("appointments.id"), nullable=True)
    escalated_to_human: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Appointment(Base):
    __tablename__ = "appointments"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("clinics.id"), nullable=False)
    patient_name: Mapped[Optional[str]] = mapped_column(String(255))
    patient_phone: Mapped[Optional[str]] = mapped_column(String(30))
    patient_language: Mapped[str] = mapped_column(String(5), default="en")
    caller_id: Mapped[Optional[UUID]] = mapped_column(UUID, ForeignKey("calls.id"), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending") -- pending, confirmed, completed, cancelled, no_show
    reason: Mapped[Optional[str]] = mapped_column(Text)
    doctor_id: Mapped[Optional[UUID]] = mapped_column(UUID, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    location: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Prescription(Base):
    __tablename__ = "prescriptions"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    clinic_id: Mapped[UUID] = mapped_column(UUID, ForeignKey("clinics.id"), nullable=False)
    patient_name: Mapped[Optional[str]] = mapped_column(String(255))
    patient_phone: Mapped[Optional[str]] = mapped_column(String(30))
    patient_language: Mapped[str] = mapped_column(String(5), default="en")
    caller_id: Mapped[Optional[UUID]] = mapped_column(UUID, ForeignKey("calls.id"), nullable=True)
    medication: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage: Mapped[Optional[str]] = mapped_column(String(100))
    frequency: Mapped[Optional[str]] = mapped_column(String(50))
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    doctor_id: Mapped[Optional[UUID]] = mapped_column(UUID, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending") -- pending, approved, sent_pharmacy, dispensed
    pharmacy_name: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class CallEmbedding(Base):
    __tablename__ = "call_embeddings"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    call_id: Mapped[UUID] = mapped_column(UUID, unique=True, nullable=False)
    embedding: Mapped[List[float]] = mapped_column(Vector(1536), nullable=False) -- pgvector
    embedding_type: Mapped[str] = mapped_column(String(30), default="call_analysis")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class LanguageCode(Base):
    __tablename__ = "language_codes"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(5), unique=True) -- hi, en, ta, te, bn
    script: Mapped[str] = mapped_column(String(30), default="Latin/Devanagari/Tamil/Telugu/Bengali")
    deepgram_model: Mapped[str] = mapped_column(String(50), default="nova-3")
    elevenlabs_voice_id: Mapped[Optional[str]] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

# Dependency injection for async session
async def get_db_session() -> AsyncSession:
    """Get async database session."""
    async with AsyncSession(engine) as session:
        yield session

# Region: Session-scoped engine initialization

async def init_db():
    """Initialize database: create tables if not exist."""
    async with engine.begin() as conn:
        # Run SQL file for pgvector functions and triggers
        # Read and execute postgres_schema.sql
        pass  # Handled by migration tool in production

async def get_clinic(clinic_id: UUID) -> Optional[Clinic]:
    """Get clinic by ID."""
    async with get_db_session() as session:
        result = await session.get(Clinic, clinic_id)
        return result

async def list_clinic_calls(clinic_id: UUID, state: Optional[str] = None) -> List[Call]:
    """List calls for a clinic, optionally filtered by state."""
    async with get_db_session() as session:
        query = select(Call).where(Call.clinic_id == clinic_id)
        if state:
            query = query.where(Call.state == state)
        result = await session.execute(query.order_by(Call.started_at.desc()))
        return result.scalars().all()

# Additional helper functions for call center operations
# - create_call, update_call_state, complete_call, escalate_call
# - schedule_appointment, update_appointment_status
# - create_prescription, update_prescription_status
# - search_similar_calls (via raw SQL pgvector)
# - log_call_embedding, get_call_embedding