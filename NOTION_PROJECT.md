# MediCall AI — Notion Project Documentation

> **Copy this content into a new Notion page** to create your project workspace.

---

## 🎯 Project Overview

| Property | Value |
|----------|-------|
| **Project Name** | MediCall AI |
| **Tagline** | Medical Call AI for India |
| **Repository** | https://github.com/ajayspi/MediCall-AI (Private) |
| **Status** | 🚧 Active Development |
| **Domain** | medicall.ai (planned) |
| **Target Market** | India — Medical Information Call Centers |
| **Primary Languages** | Hindi, English, Tamil, Telugu, Bengali |

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MediCall AI Architecture                 │
├─────────────────────────────────────────────────────────────────┤
│  Telephony (Exotel/Knowlarity/Twilio India)                     │
│                         ↓                                       │
│              LiveKit SIP → LiveKit Agents                       │
│                         ↓                                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │ Deepgram STT│→ │  GPT-4.1    │→ │ ElevenLabs  │             │
│  │ (hi/ta/te/  │  │ Medical     │  │ TTS (Indian │             │
│  │  bn/en-IN)  │  │ Prompt      │  │ Voices)     │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                         ↓                                       │
│              Medical Logic (Triage/Appointment/Prescription)    │
│                         ↓                                       │
│              Local PostgreSQL + pgvector (RAG)                  │
│                         ↓                                       │
│         Razorpay / PhonePe / Cashfree (Payments)                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📋 Task Board

### Phase 1: Database Migration (Week 1-2)
- [ ] **Delete** `backend/app/db/supabase.py` and `backend/supabase_schema.sql`
- [ ] **Create** `backend/app/db/postgres.py` with asyncpg/SQLAlchemy
- [ ] **Create** `backend/postgres_schema.sql` with medical tables + pgvector
- [ ] **Update** `docker-compose.yml` → add local PostgreSQL + pgvector
- [ ] **Update** all API files → replace `get_supabase()` → `get_db()`

### Phase 2: Language Support (Week 2-3)
- [ ] **STT**: Deepgram models `hi-IN`, `ta-IN`, `te-IN`, `bn-IN`, `en-IN`
- [ ] **TTS**: ElevenLabs Indian voices for each language
- [ ] **LLM**: Medical system prompts in 5 languages
- [ ] **Language Detection**: From caller ID prefix / IVR selection

### Phase 3: Payments (Week 3)
- [ ] Razorpay integration (cards, UPI, netbanking)
- [ ] PhonePe integration (UPI)
- [ ] Cashfree integration (subscriptions)
- [ ] Webhook handlers for all three

### Phase 4: Telephony (Week 3-4)
- [ ] Exotel webhook handler
- [ ] Knowlarity webhook handler
- [ ] Twilio India webhook handler
- [ ] Unified LiveKit SIP configuration

### Phase 5: Medical Domain (Week 4-5)
- [ ] **Models**: `clinic.py`, `doctor.py`, `patient.py`, `appointment.py`, `prescription.py`, `triage.py`
- [ ] **State Machine**: GREETING → TRIAGE → APPOINTMENT / PRESCRIPTION / ESCALATION
- [ ] **Medical RAG**: pgvector embeddings for medical knowledge base
- [ ] **HIPAA/DPDP**: Audit logging, encryption

### Phase 6: Frontend (Week 5-6)
- [ ] Medical Dashboard: Live Calls, Triage, Appointments, Prescriptions, Patients, Analytics, Settings
- [ ] Admin Panel: Clinics, Doctors, Patients, Revenue, Billing, Infrastructure, Audit, Analytics
- [ ] i18n: Hindi, Tamil, Telugu, Bengali, English

---

## 📁 Repository Structure

```
MediCall-AI/
├── .github/                    # GitHub workflows
├── .opencode/                  # Specs & configs
│   └── spec-micc-india.md      # Full spec
├── backend/
│   ├── main.py                 # FastAPI entry
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── postgres_schema.sql     # Medical DB schema
│   ├── .env.example
│   └── app/
│       ├── api/                # voice, appointments, prescriptions, triage, clinics, doctors, patients, payments
│       ├── services/           # livekit_agent, stt, tts, llm, rag, ehr, sms
│       ├── models/             # call, appointment, prescription, triage, clinic, doctor, patient
│       ├── db/                 # postgres.py, redis.py
│       └── workers/            # celery tasks
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── src/
│       ├── app/
│       │   ├── page.tsx        # Landing page
│       │   ├── (clinic)/       # 7-tab medical dashboard
│       │   └── (admin)/        # 9-view admin panel
│       ├── components/
│       └── lib/
├── docker-compose.yml          # Local dev: backend, frontend, postgres+pgvector, redis
├── railway.toml                # Backend deployment
├── vercel.json                 # Frontend deployment
├── .gitignore
└── README.md
```

---

## 🔑 Environment Variables (`.env.example`)

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/medicall
PGVECTOR_DIMENSIONS=1536

# Redis
REDIS_URL=redis://localhost:6379

# Telephony (Multi-provider)
EXOTEL_API_KEY=xxx
EXOTEL_SID=xxx
KNOWLARITY_API_KEY=xxx
TWILIO_ACCOUNT_SID=xxx
TWILIO_AUTH_TOKEN=xxx

# LiveKit
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=xxx
LIVEKIT_API_SECRET=xxx

# STT/TTS
DEEPGRAM_API_KEY=xxx
OPENAI_API_KEY=xxx
ELEVENLABS_API_KEY=xxx

# Payments (Multi-gateway)
RAZORPAY_KEY_ID=xxx
RAZORPAY_KEY_SECRET=xxx
PHONEPE_MERCHANT_ID=xxx
PHONEPE_SALT_KEY=xxx
CASHFREE_APP_ID=xxx
CASHFREE_SECRET_KEY=xxx

# Frontend
NEXT_PUBLIC_BACKEND_URL=http://localhost:8001
```

---

## 📚 Key Specifications

- **Full Spec**: [`.opencode/spec-micc-india.md`](.opencode/spec-micc-india.md)
- **Languages**: Hindi (hi-IN), English (en-IN), Tamil (ta-IN), Telugu (te-IN), Bengali (bn-IN)
- **STT**: Deepgram Nova-3 (multilingual)
- **TTS**: ElevenLabs Indian voices (Hindi, Tamil, Telugu, Bengali, English)
- **LLM**: GPT-4.1 with Structured Outputs for medical functions
- **Database**: PostgreSQL 16 + pgvector (HNSW index)
- **Payments**: Razorpay (cards/UPI), PhonePe (UPI), Cashfree (subscriptions)
- **Telephony**: Exotel + Knowlarity + Twilio India → LiveKit SIP

---

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/ajayspi/MediCall-AI.git
cd MediCall-AI

# 2. Configure
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# Fill in all API keys

# 3. Database
# Run postgres_schema.sql in PostgreSQL

# 4. Run
docker-compose up -d
# OR
cd backend && pip install -r requirements.txt && uvicorn main:app --reload
cd frontend && npm install && npm run dev
```

---

## 📊 Key Metrics to Track

| Metric | Target |
|--------|--------|
| STT Accuracy (Hindi) | >95% |
| STT Accuracy (Regional) | >90% |
| E2E Latency | <800ms |
| Triage Accuracy | >95% |
| Appointment Booking Success | >90% |
| Uptime | 99.9% |

---

## 🔗 Links

- **GitHub**: https://github.com/ajayspi/MediCall-AI
- **Spec**: `.opencode/spec-micc-india.md`
- **Railway**: (configure after deploy)
- **Vercel**: (configure after deploy)

---

## 📝 Notes

> This project replaces the TalkByte restaurant voice ordering system with a Medical Information Call Center for India. All Supabase dependencies removed — local PostgreSQL + pgvector only. Supabase connection deferred to future project.

---

*Generated for Notion import — copy this entire content into a new Notion page.*