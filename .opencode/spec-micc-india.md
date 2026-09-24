# SPEC: Indian Medical Information Call Center (MICC) Customization

## Goal
Transform the TalkByte AI restaurant voice ordering system into a **Medical Information Call Center (MICC)** platform for the Indian market with:
- **Local PostgreSQL database** (replacing Supabase) with pgvector for RAG
- **Indian languages**: Hindi + English + 3 major regional (Tamil, Telugu, Bengali)
- **Multiple Indian payment gateways** (Razorpay, PhonePe, Cashfree)
- **Multiple telephony providers** (Exotel, Knowlarity, Twilio India)
- **Medical domain** adaptations (HIPAA-ready, medical terminology, appointment booking, prescription refill triage)
- **Local databases only** (no Supabase dependency) — Supabase connection deferred to future project

## Non-Goals
- Supabase integration (deferred to separate future project)
- Restaurant-specific features (menu RAG, Square POS, Stripe AU)
- Australian telephony (Telnyx) — replaced with Indian providers
- Australian compliance — replaced with Indian healthcare regulations

## Affected Files (from existing TalkByte clone)

### Database Layer (Replace Supabase → Local PostgreSQL)
| File | Change |
|------|--------|
| `backend/app/db/supabase.py` | **DELETE** → Replace with `postgres.py` using asyncpg/SQLAlchemy |
| `backend/app/db/redis.py` | Keep (local Redis) |
| `backend/supabase_schema.sql` | **DELETE** → Replace with `postgres_schema.sql` |
| All API files (`backend/app/api/*.py`) | Replace `get_supabase()` → `get_db()` dependency |
| `backend/app/services/rag.py` | Replace pgvector calls → local PostgreSQL pgvector |
| `backend/app/workers/__init__.py` | Update DB calls |

### Language & Localization
| File | Change |
|------|--------|
| `backend/app/services/livekit_agent.py` | Replace `language="en-AU"` → dynamic language detection (Hindi/English/Tamil/Telugu/Bengali) |
| `backend/app/services/stt.py` | Deepgram → support `hi-IN`, `ta-IN`, `te-IN`, `bn-IN`, `en-IN` |
| `backend/app/services/tts.py` | ElevenLabs → support Indian voices for each language |
| `backend/app/services/llm.py` | System prompt → medical domain, multi-language support |
| Frontend i18n | Add Hindi/Tamil/Telugu/Bengali translations |

### Payments (Replace Stripe AU → Multiple Indian Gateways)
| File | Change |
|------|--------|
| `backend/app/api/payments.py` | **DELETE** → New `payments_india.py` with Razorpay/PhonePe/Cashfree |
| `backend/app/services/sms.py` | Telnyx SMS → Exotel/Knowlarity/Gupshup for OTP/payment links |

### Telephony (Replace Telnyx → Multiple Indian Providers)
| File | Change |
|------|--------|
| `backend/app/api/voice.py` | Telnyx webhook → Multi-provider webhook handler (Exotel/Knowlarity/Twilio) |
| `backend/app/services/livekit_agent.py` | SIP config → Multi-provider SIP config |

### Domain Adaptation (Restaurant → Medical Call Center)
| File | Change |
|------|--------|
| `backend/app/models/call.py` | State machine: GREETING → TRIAGE → INFO_PROVIDED → APPOINTMENT_BOOKED / PRESCRIPTION_TRIAGE / ESCALATED |
| `backend/app/models/order.py` | **DELETE** → New `appointment.py`, `prescription.py`, `triage.py` |
| `backend/app/models/restaurant.py` | **DELETE** → New `clinic.py`, `doctor.py`, `patient.py` |
| `backend/app/api/orders.py` | **DELETE** → New `appointments.py`, `prescriptions.py`, `triage.py` |
| `backend/app/services/pos/` | **DELETE** → New `ehr.py` (EHR integration), `hospitalis.py` |
| Frontend dashboard tabs | Replace 7 restaurant tabs → Medical tabs (Live Calls, Triage, Appointments, Prescriptions, Patients, Analytics, Settings) |

### Configuration & Deployment
| File | Change |
|------|--------|
| `.env.example` | Indian env vars (Razorpay keys, Exotel keys, Indian PostgreSQL URL) |
| `docker-compose.yml` | Add local PostgreSQL + pgvector container |
| `railway.toml` | Update for Indian deployment |
| `README.md` | Update for MICC India |

## Expected Behavior

1. **Inbound Call Flow (India)**:
   - Call arrives via Exotel/Knowlarity/Twilio India
   - Language detected from caller ID / IVR selection
   - Deepgram STT with appropriate language model (`hi-IN`, `ta-IN`, `te-IN`, `bn-IN`, `en-IN`)
   - GPT-4.1 with medical system prompt in detected language
   - ElevenLabs TTS with Indian voice for detected language
   - Medical triage → Appointment booking / Prescription refill / Escalation

2. **Multi-language Support**:
   - Hindi (primary) + English + Tamil + Telugu + Bengali
   - Dynamic language switching mid-call
   - Medical terminology in each language

3. **Payments** (if applicable for paid consultations):
   - Razorpay / PhonePe / Cashfree integration
   - UPI, NetBanking, Card, Wallet support
   - Payment links via SMS/WhatsApp

4. **Database (Local PostgreSQL)**:
   - Tables: `clinics`, `doctors`, `patients`, `calls`, `appointments`, `prescriptions`, `triage_records`, `medical_knowledge` (pgvector)
   - pgvector for medical knowledge base RAG
   - Row-level security equivalent via application logic

5. **Telephony**:
   - Exotel webhook handler
   - Knowlarity webhook handler
   - Twilio India webhook handler
   - Unified LiveKit SIP integration

## Acceptance Criteria Checklist

### Database
- [ ] Local PostgreSQL with pgvector runs via `docker-compose up`
- [ ] `postgres_schema.sql` creates all medical tables + pgvector index
- [ ] `backend/app/db/postgres.py` provides `get_db()` dependency
- [ ] All API endpoints use `get_db()` instead of `get_supabase()`
- [ ] `backend/supabase_schema.py` and `supabase.py` deleted

### Languages
- [ ] STT works for: `hi-IN`, `ta-IN`, `te-IN`, `bn-IN`, `en-IN`
- [ ] TTS works for: Hindi, Tamil, Telugu, Bengali, English (Indian voices)
- [ ] LLM system prompt loads in detected language
- [ ] Language detection from caller IVR / caller ID prefix

### Payments
- [ ] Razorpay integration for payment links
- [ ] PhonePe integration for UPI
- [ ] Cashfree integration for subscriptions
- [ ] Webhook handlers for all three gateways

### Telephony
- [ ] Exotel webhook handler
- [ ] Knowlarity webhook handler
- [ ] Twilio India webhook handler
- [ ] Unified SIP config for LiveKit

### Medical Domain
- [ ] Call state machine: GREETING → TRIAGE → INFO_PROVIDED → APPOINTMENT_BOOKED / PRESCRIPTION_REFILL / ESCALATED
- [ ] Models: `clinic.py`, `doctor.py`, `patient.py`, `appointment.py`, `prescription.py`, `triage.py`
- [ ] Medical knowledge base with pgvector embeddings
- [ ] HIPAA-ready audit logging

### Frontend
- [ ] Medical dashboard tabs: Live Calls, Triage Queue, Appointments, Prescriptions, Patients, Analytics, Settings
- [ ] Admin panel: Clinics, Doctors, Patients, Revenue, Billing, Infrastructure, Audit, Analytics
- [ ] i18n: Hindi, Tamil, Telugu, Bengali, English

### Infrastructure
- [ ] `docker-compose.yml` includes local PostgreSQL + pgvector
- [ ] `.env.example` has all Indian env vars
- [ ] `README.md` updated for MICC India

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| pgvector not available in local PostgreSQL | High | Use official `pgvector/pgvector` Docker image |
| Deepgram Indian language accuracy | Medium | Test with real Indian audio samples |
| ElevenLabs Indian voice quality | Medium | Test voices; fallback to Google TTS |
| Multiple telephony provider complexity | High | Abstract provider interface; test each separately |
| Medical compliance (HIPAA/Indian DPDP) | High | Audit logging, encryption, access controls |
| pgvector performance at scale | Medium | HNSW index, proper dimension (1536) |
| Multi-gateway payment reconciliation | Medium | Idempotency keys, unified webhook handler |

## Spec Status
**Status**: DRAFT — Awaiting sign-off before implementation