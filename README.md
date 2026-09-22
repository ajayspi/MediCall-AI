# TalkByte AI — Restaurant Voice Ordering System

AI phone ordering system for Australian restaurants. Caller rings → AI answers → takes order → sends SMS payment link → pushes to POS.

## Architecture

```
Telnyx → LiveKit Agents → Deepgram Flux STT → GPT-4.1 → ElevenLabs TTS
                                    ↓
                              Supabase (Postgres + pgvector)
                                    ↓
                              Stripe Payment Links + Square POS
```

## Tech Stack

| Layer | Choice |
|-------|--------|
| Telephony | Telnyx ($0.018/min AU) |
| Voice Orchestration | LiveKit Agents |
| STT | Deepgram Flux (<70ms TTFT) |
| LLM | GPT-4.1 (Structured Outputs) |
| TTS | ElevenLabs |
| Backend | FastAPI + Python 3.12 |
| Frontend | Next.js 16 (App Router) + React 19 |
| Database | Supabase (Postgres 16 + pgvector) |
| Cache/Queue | Upstash Redis + Celery |
| Payments | Stripe Payment Links |
| POS | Square (primary), Lightspeed/Kounta (Phase 2) |
| Deployment | Railway (backend) + Vercel (frontend) |

## Project Structure

```
talkbyte/
├── backend/
│   ├── main.py                 # FastAPI entry
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── supabase_schema.sql     # Database schema
│   └── app/
│       ├── api/                # FastAPI routes
│       │   ├── voice.py        # Telnyx webhook + LiveKit
│       │   ├── orders.py       # Order CRUD
│       │   ├── restaurants.py  # Restaurant management
│       │   ├── payments.py     # Stripe + payment links
│       │   └── admin.py        # Admin panel endpoints
│       ├── services/
│       │   ├── livekit_agent.py
│       │   ├── stt.py          # Deepgram Flux
│       │   ├── tts.py          # ElevenLabs streaming
│       │   ├── llm.py          # GPT-4.1 with functions
│       │   ├── rag.py          # pgvector menu search
│       │   ├── pos/            # POS integrations
│       │   │   ├── base.py
│       │   │   └── square.py
│       │   └── sms.py
│       ├── models/
│       │   ├── call.py         # State machine
│       │   ├── order.py
│       │   └── restaurant.py
│       ├── db/
│       │   ├── supabase.py
│       │   └── redis.py
│       └── workers/
│           └── celery_app.py   # POS retry, payment expiry
├── frontend/
│   ├── package.json
│   ├── next.config.js
│   ├── tailwind.config.js
│   ├── Dockerfile
│   └── src/
│       ├── app/
│       │   ├── (restaurant)/   # Restaurant dashboard (7 tabs)
│       │   └── (admin)/        # Admin panel (9 views)
│       ├── components/
│       └── lib/
├── docker-compose.yml
└── supabase_schema.sql
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Node.js 20+
- Python 3.12+
- Supabase account
- Upstash Redis account
- Telnyx, LiveKit, Deepgram, OpenAI, ElevenLabs, Stripe, Square accounts

### 1. Clone and Configure
```bash
git clone <repo>
cd talkbyte
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local
# Fill in all API keys
```

### 2. Database Setup
```bash
# Run in Supabase SQL Editor
cat backend/supabase_schema.sql
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

### Restaurant Dashboard (7 tabs)
1. **Overview** - KPIs, call volume charts, recent orders
2. **Live Calls** - Real-time call cards with timers, audio intercept
3. **Orders** - 4-stage pipeline (Placed → Link Sent → Paid → Synced)
4. **Menu** - Category filtering, availability toggle
5. **Analytics** - Hourly volume, 7-day revenue, peak heatmaps
6. **Billing** - Plan usage, tier upgrade, invoices
7. **Settings** - Voice persona, greeting script, POS status

### Admin Panel (9 views)
1. **Overview** - System KPIs, MRR, fleet leaderboard
2. **Live Monitor** - Active fleet calls with audio intercept
3. **Restaurants** - 487-tenant directory with health scores
4. **Users** - RBAC across all venues
5. **Revenue** - MRR breakdown, COGS analysis
6. **Billing** - Subscription lifecycle, Stripe sync
7. **Infrastructure** - 9 service health telemetry
8. **Audit Log** - Security trail (ORDER, ESCALATION, BILLING, POS)
9. **Analytics** - Platform performance, cuisine completion

### Call State Machine
```
GREETING → TAKING_ORDER → CONFIRMING → CONFIRMED → PAYMENT_SENT → COMPLETE
                ↓              ↓
         TRANSFER_TO_HUMAN  TRANSFER_TO_HUMAN
                ↓
            CALL_DROPPED
                ↓
            POS_FAILED → email fallback
                ↓
            PAYMENT_EXPIRED (30 min)
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

1. **Telnyx over Twilio** — 64% cheaper for AU calls
2. **LiveKit over custom WebSocket** — SIP bridging, agent framework built-in
3. **Supabase over separate Postgres + Qdrant** — pgvector eliminates vector DB
4. **Upstash Redis** — Serverless, zero ops, 30min call session TTL
4. **Stripe Payment Links** — Customer pays on phone, no hardware needed
5. **Strategy pattern for POS** — Square / Lightspeed / Kounta swappable

## Sprint Status

- ✅ Sprint 1: Voice Pipeline MVP
- ✅ Sprint 2: Payments + POS
- ✅ Sprint 3: Restaurant Dashboard (7 tabs)
- ✅ Sprint 4: Operator Admin Panel (9 views)
- ⏳ Production deployment & live venue onboarding

## License

Proprietary — TalkByte AI