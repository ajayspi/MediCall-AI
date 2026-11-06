# MediCall AI — Medical Call AI for India

**Multi-language voice AI for medical call centers** — Hindi, Tamil, Telugu, Bengali, English. Local PostgreSQL + pgvector, Razorpay/PhonePe/Cashfree, Exotel/Knowlarity/Twilio India.

## Architecture

```
Exotel/Knowlarity/Twilio India → LiveKit SIP → LiveKit Agents
                                              ↓
        ┌───────────────────────┐  ┌───────────────────────┐
        │   Deepgram STT        │→ │      GPT-4.1          │
        │ (hi-IN, ta-IN, te-IN, │  │  Medical Prompt       │
        │  bn-IN, en-IN)        │  │  (Structured Outputs) │
        └───────────────────────┘  └───────────────────────┘
                                              ↓
                                    ┌───────────────────────┐
                                    │   ElevenLabs TTS      │
                                    │ (Indian Voices)       │
                                    └───────────────────────┘
                                              ↓
                              Medical Logic (Triage/Appointment/Prescription)
                                              ↓
                              Local PostgreSQL + pgvector (RAG)
                                              ↓
                              Razorpay / PhonePe / Cashfree (Payments)
```

## Tech Stack

| Layer | Choice |
|-------|--------|
| Telephony | Exotel + Knowlarity + Twilio India |
| Voice Orchestration | LiveKit Agents |
| STT | Deepgram Nova-3 (hi-IN, ta-IN, te-IN, bn-IN, en-IN) |
| LLM | GPT-4.1 (Structured Outputs) |
| TTS | ElevenLabs (Indian Voices) |
| Backend | FastAPI + Python 3.12 |
| Frontend | Next.js 16 (App Router) + React 19 |
| Database | PostgreSQL 16 + pgvector (Local) |
| Cache/Queue | Redis + Celery |
| Payments | Razorpay + PhonePe + Cashfree |
| EHR Integration | Custom adapters (Petpooja/Posist) |
| Deployment | Railway (backend) + Vercel (frontend) |

## Project Structure

```
medicall-ai/
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
│       └── workers/            # celery tasks (EHR retry, payment expiry, SMS)
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── Dockerfile
│   ├── .env.local.example
│   └── src/
│       ├── app/
│       │   ├── page.tsx        # Landing page
│       │   ├── (clinic)/       # 7-tab medical dashboard
│       │   │   ├── dashboard/
│       │   │   ├── live-calls/
│       │   │   ├── appointments/
│       │   │   ├── prescriptions/
│       │   │   ├── patients/
│       │   │   ├── analytics/
│       │   │   └── settings/
│       │   └── (admin)/        # 9-view admin panel
│       │       ├── overview/
│       │       ├── live-monitor/
│       │       ├── clinics/
│       │       ├── doctors/
│       │       ├── patients/
│       │       ├── revenue/
│       │       ├── billing/
│       │       ├── infrastructure/
│       │       ├── audit/
│       │       └── analytics/
│       ├── components/
│       └── lib/
├── docker-compose.yml          # Local dev: backend, frontend, postgres+pgvector, redis
├── railway.toml                # Backend deployment
├── vercel.json                 # Frontend deployment
├── .gitignore
├── NOTION_PROJECT.md           # Notion import file
└── README.md
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.12+
- PostgreSQL 16 + pgvector
- Redis
- Exotel, Knowlarity, Twilio India, LiveKit, Deepgram, OpenAI, ElevenLabs, Razorpay, PhonePe, Cashfree accounts

### 1. Clone and Configure
```bash
git clone https://github.com/ajayspi/MediCall-AI.git
cd MediCall-AI
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# Fill in all API keys
```

### 2. Database Setup
```bash
# Run in PostgreSQL with pgvector extension
cat backend/postgres_schema.sql
```

### 3. Local Development
```bash
# Start all services
docker-compose up -d

# Or run individually:
# Backend
cd backend && pip install -r requirements.txt && uvicorn main:app --reload

# Frontend
cd frontend && npm install && npm run dev
```

### 4. Access
- Frontend: http://localhost:3000
- Backend API: http://localhost:8001
- API Docs: http://localhost:8001/docs

## Key Features

### Medical Dashboard (7 tabs)
1. **Overview** - KPIs, call volume charts, recent triage/appointments
2. **Live Calls** - Real-time call cards with timers, audio intercept, language detection
3. **Triage Queue** - Active triage cases with severity, patient info, doctor assignment
4. **Appointments** - 4-stage pipeline (Requested → Confirmed → Completed → Cancelled)
5. **Prescriptions** - Prescription refill requests, doctor approval, pharmacy sync
6. **Patients** - Patient directory with medical history, language preference, contact info
7. **Analytics** - Call volume, triage outcomes, appointment completion, language distribution
8. **Settings** - Voice persona, greeting script, language config, EHR integration

### Admin Panel (9 views)
1. **Overview** - System KPIs, call volume, MRR, clinic leaderboard
2. **Live Monitor** - Active fleet calls with audio intercept, language filter
3. **Clinics** - Multi-tenant clinic directory with health scores, EHR status
4. **Doctors** - Doctor directory with specialization, language, availability
5. **Patients** - Patient directory with medical history, language preference
6. **Revenue** - MRR breakdown, consultation fees, COGS analysis
7. **Billing** - Subscription lifecycle, payment gateway sync, invoices
8. **Infrastructure** - 9 service health telemetry (Exotel, Knowlarity, Twilio, Deepgram, OpenAI, ElevenLabs, Razorpay, PhonePe, Cashfree, PostgreSQL, Redis, LiveKit)
9. **Audit Log** - Security trail (CALL, TRIAGE, APPOINTMENT, PRESCRIPTION, PAYMENT, ESCALATION)

### Medical Call State Machine
```
GREETING → LANGUAGE_DETECT → TRIAGE → INFO_PROVIDED 
                                    ↓
                        ┌───────────┴───────────┐
                        ↓                       ↓
                 APPOINTMENT_BOOKED      PRESCRIPTION_REFILL
                        ↓                       ↓
                   CONFIRMED              DOCTOR_APPROVAL
                        ↓                       ↓
                   COMPLETED              PHARMACY_SYNC
                                    ↓
                              ESCALATED (if needed)
```

## Deployment

### Railway (Backend)
```bash
# railway.toml configured
railway login
railway up
```

### Vercel (Frontend)
```bash
# Connect GitHub repo to Vercel
# Set environment variables
vercel deploy
```

## Key Architectural Decisions

1. **Multi-provider Telephony** — Exotel + Knowlarity + Twilio India for redundancy
2. **Local PostgreSQL + pgvector** — No Supabase dependency, full data sovereignty
3. **Multi-gateway Payments** — Razorpay (cards/UPI) + PhonePe (UPI) + Cashfree (subscriptions)
4. **Multi-language STT/TTS** — Deepgram Nova-3 + ElevenLabs for 5 Indian languages
5. **Medical Domain** — HIPAA-ready, DPDP-compliant, audit logging, encryption
6. **Strategy Pattern** — EHR adapters (Petpooja/Posist), Payment gateways, Telephony providers swappable

## Sprint Status

- ⏳ Sprint 1: Database Migration (PostgreSQL + pgvector)
- ⏳ Sprint 2: Multi-language STT/TTS + Medical Prompts
- ⏳ Sprint 3: Payments (Razorpay/PhonePe/Cashfree)
- ⏳ Sprint 4: Telephony (Exotel/Knowlarity/Twilio India)
- ⏳ Sprint 5: Medical Domain (Triage/Appointment/Prescription)
- ⏳ Sprint 6: Frontend Dashboards (Clinic + Admin)
- ⏳ Production deployment & live clinic onboarding

## License

Proprietary — MediCall AI

<!-- about-me -->
## About me

<p>
  <img alt="HFI Certified User Experience Analyst (CXA)" src="https://img.shields.io/badge/HFI-Certified%20UX%20Analyst%20(CXA)-1a3a52?style=flat-square">
  <a href="https://www.linkedin.com/in/aigrowthandautomationleader/"><img alt="LinkedIn" src="https://img.shields.io/badge/LinkedIn-aigrowthandautomationleader-0A66C2?style=flat-square&logo=linkedin&logoColor=white"></a>
  <a href="https://designjoom.com"><img alt="designjoom.com" src="https://img.shields.io/badge/designjoom.com-Portfolio-0b1220?style=flat-square&logo=astro&logoColor=white"></a>
</p>

**A V Ajay Kiran** — AI Growth & Digital Transformation Leader with 14+ years across AI
product development, SEO and performance marketing, UX strategy and workflow automation,
working with teams across India, Germany, the US and Australia.

**Certified:** HFI Certified User Experience Analyst (CXA) — Human Factors International.

**Capabilities**

- **AI & Growth** — Generative AI · LLM workflows · Prompt engineering · AI product development · AI content & video · Workflow automation · Growth strategy · SEO/SEM · Performance marketing · CRO · Go-to-market · Content strategy · Marketing automation
- **UX & Product** — UX strategy · User research · Information architecture · Wireframing & prototyping · Design systems · Usability testing · Product strategy
- **Engineering** — TypeScript · Python · React 19 · Next.js · Astro · FastAPI · Three.js · Tailwind CSS · PostgreSQL · Docker · Vite · Zustand
- **Analytics** — GA4 · Search Console · Looker Studio · Hotjar · Mixpanel · Microsoft Clarity · Google Ads · Semrush · Ahrefs

**Find me** — [LinkedIn](https://www.linkedin.com/in/aigrowthandautomationleader/) ·
[designjoom.com](https://designjoom.com) · [ajayspi@gmail.com](mailto:ajayspi@gmail.com)
