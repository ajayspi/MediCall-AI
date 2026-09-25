-- MediCall AI — PostgreSQL + pgvector Schema
-- Run: psql -U ubuntu -d mediacall -f backend/postgres_schema.sql
-- Migration: Supabase → Local PostgreSQL + pgvector
-- Medical Call Center domain: voice-first, multi-language, Indian telephony/payments

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Core: Clinics/Facilities (medical call center tenants)
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

-- Auth: application users (Phase-1 auth, G6-Q1 — email and/or phone identity)
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE,          -- NULL for phone-only registrations
    phone TEXT UNIQUE,          -- +91xxxxxxxxxx India (NULL for email-only)
    name TEXT NOT NULL,
    password_hash TEXT,         -- pbkdf2_sha256$iter$salt$hash (NULL for SSO-only)
    otp_code_hash TEXT,         -- HMAC-SHA256 of last issued OTP (code never stored raw)
    otp_expires_at TIMESTAMPTZ,
    otp_attempts INTEGER DEFAULT 0,
    role TEXT DEFAULT 'staff',  -- owner, staff, triage_agent, doctor, readonly
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Multi-tenant: Clinic staff/users
CREATE TABLE clinic_users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'staff', -- owner, staff, triage_agent, doctor, readonly
    language_pref TEXT DEFAULT 'en', -- hi, en, ta, te, bn
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(clinic_id, user_id)
);

-- Calls (core entity: voice-first medical call center)
-- State machine: GREETING -> TRIAGE -> APPOINTMENT / PRESCRIPTION -> COMPLETE
--                with branches: ESCALATED / DROPPED at each stage, PAYMENT_SENT / PAYMENT_EXPIRED loop
CREATE TABLE calls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    caller_number TEXT NOT NULL,
    caller_language TEXT DEFAULT 'en', -- hi, en, ta, te, bn (5 Indian languages)
    state TEXT DEFAULT 'GREETING', -- GREETING, TRIAGE, APPOINTMENT, PRESCRIPTION, COMPLETE, ESCALATED, DROPPED
    started_at TIMESTAMPTZ DEFAULT NOW(),
    ended_at TIMESTAMPTZ,
    transcript JSONB DEFAULT '[]', -- Multi-language transcript:
                                    -- [{"role":"caller","text":"...","language":"hi"},{"role":"agent","text":"...","language":"en"}]
    stt_confidence REAL DEFAULT 0,
    duration_seconds INTEGER DEFAULT 0,
    triage_severity TEXT, -- green, amber, red, critical (from AI triage)
    diagnosed_conditions JSONB DEFAULT '[]', -- SNOMED CT code list
    prescription_issued BOOLEAN DEFAULT FALSE,
    appointment_scheduled BOOLEAN DEFAULT FALSE,
    appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
    escalated_to_human BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Appointments (derived from call triage + scheduling)
CREATE TABLE appointments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID REFERENCES clinics(id) ON DELETE CASCADE,
    patient_name TEXT,
    patient_phone TEXT,
    patient_language TEXT DEFAULT 'en', -- hi, en, ta, te, bn
    caller_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending', -- pending, confirmed, completed, cancelled, no_show
    reason TEXT, -- chief complaint summary (from triage AI)
    doctor_id UUID, -- references practitioners/users who are doctors
    duration_minutes INTEGER DEFAULT 30,
    location TEXT, -- clinic address or telemedicine link (LiveKit room URL)
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
    doctor_id UUID, -- references prescribing doctor
    status TEXT DEFAULT 'pending', -- pending, approved, sent_pharmacy, dispensed
    pharmacy_name TEXT, -- Razorpay/PhonePe/Cashfree integrated pharmacy
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Medical embeddings (pgvector for similar call search, symptom clustering, triage pattern matching)
CREATE TABLE call_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    embedding VECTOR(1536), -- 1536-dim embedding (Deepgram → LLM → ElevenLabs pipeline)
    embedding_type TEXT DEFAULT 'call_analysis', -- call_analysis, triage_summary, prescription_summary, speaker_embedding
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indian languages reference (for STT/TTS model mapping and UI localization)
CREATE TABLE language_codes (
    id SERIAL PRIMARY KEY,
    code TEXT NOT NULL UNIQUE, -- hi, en, ta, te, bn
    script TEXT DEFAULT 'Latin/Devanagari/Tamil/Telugu/Bengali',
    deepgram_model TEXT DEFAULT 'nova-3', -- Deepgram model name/identifier
    elevenlabs_voice_id TEXT, -- ElevenLabs voice ID for TTS
    is_active BOOLEAN DEFAULT TRUE
);

-- Seed Indian language codes for STT/TTS
INSERT INTO language_codes (code, script, deepgram_model, elevenlabs_voice_id, is_active) VALUES
('en', 'Latin', 'nova-3', NULL, TRUE),
('hi', 'Devanagari', 'nova-3', NULL, TRUE),
('ta', 'Tamil', 'nova-3', NULL, TRUE),
('te', 'Telugu', 'nova-3', NULL, TRUE),
('bn', 'Bengali', 'nova-3', NULL, TRUE);

-- Call sessions / active call tracking (Lightweight LiveKit room mapping)
CREATE TABLE call_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    call_id UUID UNIQUE REFERENCES calls(id) ON DELETE CASCADE,
    clinic_id UUID REFERENCES clinics(id) ON DELETE SET NULL,
    livekit_room TEXT, -- LiveKit room ID for this call
    livekit_participant_id TEXT, -- Remote participant ID (caller/agent)
    status TEXT DEFAULT 'idle', -- idle, recording, in_progress, completed, failed
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    call_id UUID REFERENCES calls(id) ON DELETE SET NULL,
    appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL,
    amount NUMERIC(10,2) NOT NULL,
    currency TEXT DEFAULT 'INR',
    gateway TEXT, -- razorpay, phonepe, cashfree, manual
    gateway_ref TEXT,
    status TEXT DEFAULT 'pending', -- pending, captured, failed, refunded
    kind TEXT DEFAULT 'consultation', -- consultation, refill, subscription (G6-Q5)
    expires_at TIMESTAMPTZ, -- intent TTL: PAYMENT_SENT -> PAYMENT_EXPIRED leg
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Notifications (spec-notifications-q8.md G6-Q8): WhatsApp-first delivery
-- records for the DPDP audit trail. status: queued / sent / failed; channel:
-- whatsapp / sms / email / push; provider: meta / knowlarity / msg91 / smtp /
-- fcm. params holds the JSON-encoded template params.
CREATE TABLE notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE,
    kind TEXT NOT NULL, -- payment_link, appointment_reminder, no_show_followup, otp, payment_receipt
    recipient TEXT NOT NULL, -- phone for whatsapp/sms/push; email address for email
    language TEXT DEFAULT 'en', -- hi/en/ta/te/bn
    params TEXT, -- JSON-encoded template params
    channel TEXT,
    provider TEXT,
    provider_ref TEXT,
    status TEXT DEFAULT 'queued', -- queued, sent, failed
    template TEXT, -- rendered message at send time
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);

-- Indexes for call center performance (critical for high-concurrency workload)
CREATE INDEX idx_calls_clinic ON calls(clinic_id);
CREATE INDEX idx_calls_state ON calls(state);
CREATE INDEX idx_calls_language ON calls(caller_language);
CREATE INDEX idx_calls_started ON calls(started_at DESC);
CREATE INDEX idx_calls_triage ON calls(triage_severity) WHERE triage_severity IS NOT NULL;
CREATE INDEX idx_appointments_clinic_status ON appointments(clinic_id, status);
CREATE INDEX idx_appointments_scheduled ON appointments(scheduled_at);
CREATE INDEX idx_appointments_status ON appointments(status);
CREATE INDEX idx_clinics_active ON clinics(is_active);
CREATE INDEX idx_clinic_users_clinic ON clinic_users(clinic_id);
CREATE INDEX idx_clinic_users_user ON clinic_users(user_id);
CREATE INDEX idx_users_role ON users(role) WHERE is_active = TRUE;
CREATE INDEX idx_call_embeddings_call ON call_embeddings(call_id);
CREATE INDEX idx_payments_clinic_status ON payments(clinic_id, status);
CREATE INDEX idx_notifications_clinic_status ON notifications(clinic_id, status);

-- Webhook idempotency (spec-payments.md Q4/A4a): at most one intent per
-- gateway reference, so a replayed gateway webhook updates the same row.
-- Partial index: manual intents (gateway_ref NULL) may repeat.
CREATE UNIQUE INDEX uq_payments_gateway_ref ON payments(gateway_ref)
    WHERE gateway_ref IS NOT NULL;

-- Delivery idempotency (spec-notifications-q8.md Q4/A4a): at most one row per
-- provider reference (a provider delivery ID), so retries/replays never
-- duplicate rows. Partial index: queued sends (provider_ref NULL) may repeat.
CREATE UNIQUE INDEX uq_notifications_provider_ref ON notifications(provider_ref)
    WHERE provider_ref IS NOT NULL;

-- pgvector similarity search function: find calls with similar patterns
CREATE OR REPLACE FUNCTION search_similar_calls(
    clinic_uuid UUID,
    query_embedding VECTOR(1536),
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    call_id UUID,
    similarity REAL
) LANGUAGE sql AS $$
    SELECT
        c.id AS call_id,
        1 - (ce.embedding <=> query_embedding) AS similarity
    FROM call_embeddings ce
    JOIN calls c ON ce.call_id = c.id
    WHERE c.clinic_id = clinic_uuid
      AND c.ended_at IS NOT NULL -- only completed calls for analysis
    ORDER BY ce.embedding <=> query_embedding
    LIMIT match_count;
$$;

-- pgvector similarity search: find calls by symptom pattern
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

-- pgvector similarity search: find related calls (same patient, different time)
CREATE OR REPLACE FUNCTION search_related_calls(
    clinic_uuid UUID,
    call_id UUID,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    related_call_id UUID,
    caller_number TEXT,
    similarity REAL,
    state TEXT
) LANGUAGE sql AS $$
    DECLARE
        target_embedding VECTOR(1536);
        target_language TEXT;
    BEGIN
        -- Get the embedding and language of the reference call
        SELECT ce.embedding, c.caller_language
        INTO target_embedding, target_language
        FROM call_embeddings ce
        JOIN calls c ON ce.call_id = c.id
        WHERE c.id = call_id AND c.clinic_id = clinic_uuid;

        RETURN QUERY
        SELECT
            c.id AS related_call_id,
            c.caller_number,
            1 - (ce.embedding <=> target_embedding) AS similarity,
            c.state
        FROM call_embeddings ce
        JOIN calls c ON ce.call_id = c.id
        WHERE c.clinic_id = clinic_uuid
          AND c.id != call_id
          AND c.caller_language = target_language -- same language calls
        ORDER BY ce.embedding <=> target_embedding
        LIMIT match_count;
    END;
$$;

-- Trigger for automatic updated_at on core tables
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

CREATE TRIGGER update_payments_updated_at BEFORE UPDATE ON payments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Auth: local replacement for Supabase's auth.uid() (spec-auth.md Q2).
-- The API sets app.current_user_id per request; auth.uid() reads it back.
-- RLS is ENABLED but NOT FORCED this phase: the table (owner) connection
-- bypasses it, so the unauthenticated Phase-1 API keeps working. Enforcement
-- (FORCE ROW LEVEL SECURITY + a non-owner medicall_app role + per-request
-- GUC) lands together with the router guards in the enforcement phase.
CREATE SCHEMA IF NOT EXISTS auth;

CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.current_user_id', true), '')::uuid
$$;

-- Role the GRANTs below target (Supabase 'authenticated' role recreated
-- locally so the schema loads on plain PostgreSQL instead of failing).
CREATE ROLE authenticated NOLOGIN;

-- Runtime connection role for the API (spec-auth-enforcement.md Q4/A4a): a
-- NON-owner so RLS applies to every API statement even without FORCE. DDL
-- (init_db / schema load) still runs as the owner (medicall). Dev creds only —
-- prod overrides via DATABASE_URL + role provisioning.
CREATE ROLE medicall_app LOGIN PASSWORD 'medicall_app';

-- Row Level Security (RLS) — multi-tenant data isolation
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinics ENABLE ROW LEVEL SECURITY;
ALTER TABLE clinic_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE calls ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE prescriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- FORCE the flip (spec-auth-enforcement.md): the owner (medicall) must not
-- bypass RLS once the runtime connects as medicall_app; FORCE makes the
-- policies binding for EVERY role, including the table owner. These 7 tenant
-- tables are the only RLS-enabled ones (language_codes is read-only reference
-- data and deliberately left out).
ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE clinics FORCE ROW LEVEL SECURITY;
ALTER TABLE clinic_users FORCE ROW LEVEL SECURITY;
ALTER TABLE calls FORCE ROW LEVEL SECURITY;
ALTER TABLE appointments FORCE ROW LEVEL SECURITY;
ALTER TABLE prescriptions FORCE ROW LEVEL SECURITY;
ALTER TABLE payments FORCE ROW LEVEL SECURITY;

-- Clinic owners see their own clinic data
CREATE POLICY clinic_own_data ON clinics
    FOR ALL USING (
        id IN (
            SELECT clinic_id FROM clinic_users 
            WHERE user_id = auth.uid() AND role = 'owner'
        )
    );

-- Users manage their own profile row. An authenticated request sees only its
-- own row (auth.uid() = id); the server-side auth service path (login/OTP/
-- register lookups + writes, which run BEFORE any token exists) passes through
-- the app.service_request GUC. External callers cannot set PG GUCs over HTTP —
-- arming is server-side authority only (spec-auth-enforcement.md Q4/A4a).
CREATE POLICY users_own_data ON users
    FOR ALL USING (
        id = auth.uid()
        OR current_setting('app.service_request', true) = 'on'
    );

-- Staff can read clinic info
CREATE POLICY clinic_staff_read ON clinics
    FOR SELECT USING (
        id IN (
            SELECT clinic_id FROM clinic_users 
            WHERE user_id = auth.uid()
        )
    );

-- Staff can create calls for their clinic. The voice webhook path (verified
-- service token, no end-user JWT) passes through app.service_request.
CREATE POLICY calls_create ON calls
    FOR INSERT WITH CHECK (
        clinic_id IN (
            SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
        )
        OR current_setting('app.service_request', true) = 'on'
    );

-- Staff can read calls for their clinic; verified webhooks pass through too.
CREATE POLICY calls_read ON calls
    FOR SELECT USING (
        clinic_id IN (
            SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
        )
        OR current_setting('app.service_request', true) = 'on'
    );

-- Staff can update their clinic's calls (state machine + metadata setters);
-- the transcript persistence path (verified webhook) passes through too.
-- Discovered during enforcement: calls had INSERT/SELECT policies only, so
-- UPDATEs (update_call_state, update_call_transcript) were RLS-deny-all.
CREATE POLICY calls_update ON calls
    FOR UPDATE USING (
        clinic_id IN (
            SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
        )
        OR current_setting('app.service_request', true) = 'on'
    );

-- Appointments: clinic staff can manage (CRUD)
CREATE POLICY appointments_manage ON appointments
    FOR ALL USING (clinic_id IN (
        SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
    ));

-- Prescriptions: clinic staff can manage
CREATE POLICY prescriptions_manage ON prescriptions
    FOR ALL USING (clinic_id IN (
        SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
    ));

-- Payments: clinic staff can manage payments for their clinic; the userless
-- gateway webhook (POST /api/payments/webhook, spec-payments.md Q4/A4a) writes
-- under the server's service bypass (app.service_request = 'on' via
-- service_request_ctx()).
CREATE POLICY payments_manage ON payments
    FOR ALL USING (
        clinic_id IN (
            SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
        )
        OR current_setting('app.service_request', true) = 'on'
    );

-- Notifications: clinic staff read/send for their clinic; server-side sends
-- (the payment-create hook and the manual endpoint) write under the service
-- bypass via service_request_ctx() — mirrors payments_manage (G6-Q8 Q4/A4a).
CREATE POLICY notifications_send ON notifications
    FOR ALL USING (
        clinic_id IN (
            SELECT clinic_id FROM clinic_users WHERE user_id = auth.uid()
        )
        OR current_setting('app.service_request', true) = 'on'
    );

-- Clinic memberships: users read their own rows; a clinic owner reads their
-- clinic's rows; ONLY the server-side service path may INSERT them this phase
-- (create_clinic assigns the creator's owner row; the future staff-add
-- endpoint gets its own policy or continues on the service path).
CREATE POLICY clinic_users_own ON clinic_users
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY clinic_users_manage ON clinic_users
    FOR SELECT USING (clinic_id IN (
        SELECT clinic_id FROM clinic_users
        WHERE user_id = auth.uid() AND role = 'owner'
    ));

CREATE POLICY clinic_users_service_insert ON clinic_users
    FOR INSERT WITH CHECK (current_setting('app.service_request', true) = 'on');

-- Clinic creation is platform-owner only (require_roles('owner') at the API
-- layer too). The owner role is seeded via the demo tenant — register() cannot
-- grant it, so there is no self-serve path. clinic_own_data above keeps
-- SELECT/UPDATE/DELETE scoped to one's owned clinics.
CREATE POLICY clinics_create ON clinics
    FOR INSERT WITH CHECK (EXISTS (
        SELECT 1 FROM users WHERE id = auth.uid() AND role = 'owner'
    ));

-- Language codes: always readable (reference data)
CREATE POLICY language_codes_read ON language_codes
    FOR SELECT USING (is_active = TRUE);

-- Grant permissions for authenticated users (Supabase auth → PostgreSQL auth bridge)
GRANT ALL ON clinics TO authenticated;
GRANT ALL ON clinic_users TO authenticated;
GRANT ALL ON users TO authenticated;
GRANT ALL ON calls TO authenticated;
GRANT ALL ON appointments TO authenticated;
GRANT ALL ON prescriptions TO authenticated;
GRANT ALL ON payments TO authenticated;
GRANT ALL ON notifications TO authenticated;
GRANT USAGE, SELECT ON sequence language_codes_id_seq TO authenticated;

-- Grant permissions for the API runtime role (medicall_app) — identical surface
-- so a non-owner connection can execute every Phase-1 statement (RLS then
-- applies per-policy). language_codes stays read-only reference data.
GRANT ALL ON clinics TO medicall_app;
GRANT ALL ON clinic_users TO medicall_app;
GRANT ALL ON users TO medicall_app;
GRANT ALL ON calls TO medicall_app;
GRANT ALL ON appointments TO medicall_app;
GRANT ALL ON prescriptions TO medicall_app;
GRANT ALL ON payments TO medicall_app;
GRANT ALL ON notifications TO medicall_app;
GRANT SELECT ON language_codes TO medicall_app;
GRANT USAGE, SELECT ON sequence language_codes_id_seq TO medicall_app;

-- ─── Demo tenant seed (spec-auth-enforcement.md Q3/A3a) ─────────────────────
-- The ONLY bootstrap in the RLS world: register() creates staff users only (no
-- memberships) and clinic INSERT is owner-gated, so without this seed no first
-- clinic/owner could ever exist. Fixed ids keep smoke/CI deterministic;
-- ON CONFLICT DO NOTHING makes the seed idempotent. Dev creds — prod replaces
-- them with real provisioning. Owner login: +919876543210 / DemoPass!2026.
INSERT INTO users (id, name, phone, email, password_hash, role, is_active)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    'City Care Demo Owner',
    '+919876543210',
    'demo@medicall.in',
    'pbkdf2_sha256$210000$f5e1e09bd2b39174bb70e78ec72e77a8$0c8be14df7ff2bb1280624f6f4c8232b093235be251035c8c7b8e469d4521fc6',
    'owner',
    TRUE
)
ON CONFLICT DO NOTHING;

INSERT INTO clinics (id, name, phone_number, address, city, state, pincode, plan, is_active)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    'City Care Demo Clinic',
    '+91 98765 43210',
    '12 MG Road',
    'Bengaluru',
    'Karnataka',
    '560001',
    'starter',
    TRUE
)
ON CONFLICT DO NOTHING;

INSERT INTO clinic_users (clinic_id, user_id, role)
VALUES (
    '22222222-2222-2222-2222-222222222222',
    '11111111-1111-1111-1111-111111111111',
    'owner'
)
ON CONFLICT DO NOTHING;