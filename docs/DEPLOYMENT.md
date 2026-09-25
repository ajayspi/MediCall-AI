# MediCall AI — Deployment

G6-Q10 deployment topology (spec-deploy-q10.md) — the single reference for how
the compose stack, Railway, Vercel, the region pin and the retention purge fit
together.

## Topology (one paragraph)

**Docker Compose stack** (this repo, `docker compose up`): `postgres`
(`pgvector/pgvector:pg16`, init script `backend/postgres_schema.sql` — tables,
RLS FORCE, roles, grants, seed) → `backend` (FastAPI, uvicorn, `python:3.12-slim`
image built from the **repo root** so docker compose and Railway share one
Dockerfile) → `frontend` (Next.js standalone). The cache client
(`backend/app/db/redis.py`, Upstash REST) has **zero callers** — it was dropped
from the stack (sign-off Q1=A1) and kept only as a documented future-cache stub.

**Cloud homes:** frontend = **Vercel** (region `bom1` — Mumbai, already pinned
in `vercel.json`); backend + Postgres = **Railway** (region `asia-southeast1` —
Singapore; see region pin below). Live provider round-trips (Deepgram,
ElevenLabs, OpenAI, LiveKit, telephony, gateways) stay behind CI secrets; no
real credentials ever commit.

## Bring-up (local / single Docker host)

```bash
docker compose up -d --build        # postgres + backend + frontend
curl http://localhost:8001/health   # backend
curl http://localhost:3000          # frontend
```

- Backend healthcheck gates on postgres `service_healthy` (no `requests` — the
  healthcheck uses `httpx`, which is in `requirements.txt`).
- `postgres_schema.sql` is the prod schema path (initdb mount locally / psql at
  provision on the cloud host). `init_db()` (create_all) is dev/test only;
  Alembic stays a pin, not wired (postgres.py:1646).
- The root `.dockerignore` keeps `node_modules/.git/.next/.venv/.worktrees`
  out of root-context builds; `frontend/.dockerignore` does the same for the
  frontend context.

## Region pin — data residency (G6-Q2 -> G6-Q10, sign-off Q3=A2)

`DATA_RESIDENCY_REGION="in"` is the **documented posture**, pinned
unconditionally in docker-compose.yml and defaulted in railway.toml /
.env.example. The physical placement (2026-09-25 research):

| Layer | Home | Region | Notes |
|---|---|---|---|
| Frontend | Vercel | **`bom1` (Mumbai)** | `vercel.json` `"regions": ["bom1"]` |
| Backend + Postgres | Railway | `asia-southeast1` (Singapore) | **nearest available** — Railway has NO Mumbai region (4 Metal regions: us-west2, us-east4-eqdc4a, europe-west4-drams3a, asia-southeast1-eqsg3a; docs.railway.com/deployments/regions; region select is Pro-plan only) |

Because Railway cannot host in-country, the pin is realized as
**"nearest-available"**: the app-level `DATA_RESIDENCY_REGION="in"` posture,
the Mumbai frontend edge, and **zero-retention BAAs** with the SaaS providers
(Deepgram, ElevenLabs, OpenAI, LiveKit, telephony, gateways) as a contractual
note. If hard in-country residency is ever required, run this same compose on
an Indian host (e.g. AWS ap-south-1 Mumbai EC2) — no code change needed.

## Railway (backend + Postgres)

1. `railway init` / create project; set environment **region
   `asia-southeast1`** (service settings; Pro plan) — also mirrored as
   `deploy.region` in `railway.json` + `railway.toml`.
2. Add the **Postgres plugin** (`railway add postgresql`); copy its
   `DATABASE_URL` into backend variables as
   `postgresql+asyncpg://…` (asyncpg scheme required).
3. Provision the schema once: `railway run psql -f backend/postgres_schema.sql`
   against the plugin DB — or mount it as the initdb script on a fresh volume.
4. Set remaining variables in the dashboard (secrets): every `Secret? = Yes`
   row in the catalog below. Non-secret defaults are in `railway.toml [env]`.
5. Healthcheck `/health` (timeout 300, ON_FAILURE restart x10) is pre-wired.

> ⚠️ **Railway config-as-code is DEPRECATED** (docs.railway.com/reference/
> config-as-code): legacy `railway.toml`/`railway.json` keep working for legacy
> services only until **2026-12-01**. Migrate to Railway Infrastructure-as-Code
> (Public API / IaC) before that date; region pin + Postgres plugin stay
> dashboard-side regardless.

## Vercel (frontend)

- `vercel.json`: framework nextjs, `"regions": ["bom1"]` (Mumbai), function
  maxDuration 30, env `NEXT_PUBLIC_BACKEND_URL` → backend host
  (`@medicall-backend-url` project var), `NEXT_PUBLIC_ENVIRONMENT=production`,
  `NEXT_PUBLIC_DEBUG=false`.
- The Next standalone build runs locally via `frontend/Dockerfile` (compose) or
  in Vercel's build pipeline; `/api/*` rewrites proxy to
  `NEXT_PUBLIC_BACKEND_URL` (next.config.js).

## Retention purge (G6-Q2 -> G6-Q10, sign-off Q4=A3)

- `backend/scripts/purge_expired.py` — one-shot runner over
  `app.services.retention.retention_categories()` calling
  `postgres.purge_expired` (calls 365d / notifications 180d / audit 2190d;
  recordings = external MinIO/S3 objects, noted, no rows). Env `RETENTION_*`
  overrides honored. Never auto-runs on import.
- `.github/workflows/purge.yml` — scheduled **daily 03:00 UTC**
  (`docker compose run --rm backend python scripts/purge_expired.py`) or
  manual `workflow_dispatch`. On Railway, the same script can run from a
  scheduled job/container with `DATABASE_URL` set.

## Env var catalog (complete — source of truth: `backend/.env.example`)

Convention: every key below appears in `.env.example`; `Secret? = Yes` means
the value must come from the platform secret store (Railway dashboard / Vercel
project vars / CI secrets), never from git. "Where" = the file(s) that pass it.

### Core / app
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `ENVIRONMENT` | compose, railway.toml | No | development / production |
| `DEBUG` | compose, railway.toml | No | true in dev |
| `LOG_LEVEL` | compose, railway.toml | No | debug / info |
| `FRONTEND_URL` | compose, .env.example | No | CORS + payment links origin |
| `AUTH_JWT_SECRET` | compose | **Yes** | prod: long random value |
| `WEBHOOK_SERVICE_TOKEN` | compose | **Yes** | voice webhook `X-Service-Token` |
| `AUTH_TOKEN_TTL_SECONDS` | backend | No | 43200 |
| `OTP_TTL_SECONDS` | backend | No | 600 |
| `DEFAULT_CALLER_LANGUAGE` | backend | No | hi (default caller lang) |
| `DEFAULT_CLINIC_ID` | backend | No | single-clinic MVP stamp |

### Database
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `DATABASE_URL` | compose / Railway | **Yes** | `postgresql+asyncpg://…` (async scheme required) |

### Cache (future stub — no callers, not in the stack)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `UPSTASH_REDIS_REST_URL` | .env.example | **Yes** | app/db/redis.py reads this |
| `UPSTASH_REDIS_REST_TOKEN` | .env.example | **Yes** | password to the REST URL |

### Telephony (India, multi-provider)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `EXOTEL_API_KEY` | backend | **Yes** | Exotel |
| `EXOTEL_SID` | backend | **Yes** | Exotel |
| `EXOTEL_TOKEN` | backend | **Yes** | Exotel |
| `KNOWLARITY_API_KEY` | backend | **Yes** | Knowlarity (x-api-key) |
| `KNOWLARITY_AUTHORIZATION` | backend | **Yes** | Knowlarity SR API auth header |
| `KNOWLARITY_SIP_URI` | backend | No | Knowlarity SIP target |
| `TWILIO_ACCOUNT_SID` | backend | **Yes** | Twilio India |
| `TWILIO_AUTH_TOKEN` | backend | **Yes** | Twilio India |
| `TWILIO_PHONE_NUMBER` | backend | No | Twilio India number |

### Voice — LiveKit / STT / TTS / LLM
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `LIVEKIT_URL` | backend | No | wss://your-project.livekit.cloud |
| `LIVEKIT_API_KEY` | backend | **Yes** | LiveKit |
| `LIVEKIT_API_SECRET` | backend | **Yes** | LiveKit |
| `DEEPGRAM_API_KEY` | backend | **Yes** | multi-language STT |
| `STT_CONFIDENCE_THRESHOLD` | backend | No | 0.6 floor (G6-Q4 Q1=A1) |
| `OPENAI_API_KEY` | backend | **Yes** | GPT triage agent |
| `ELEVENLABS_API_KEY` | backend | **Yes** | multi-language TTS |
| `ELEVENLABS_VOICE_ID` | backend | No | generic fallback voice |
| `ELEVENLABS_VOICE_ID_HI` | backend | No | Hindi (canonical, G6-Q4 Q4=A1) |
| `ELEVENLABS_VOICE_ID_EN` | backend | No | English |
| `ELEVENLABS_VOICE_ID_TA` | backend | No | Tamil |
| `ELEVENLABS_VOICE_ID_TE` | backend | No | Telugu |
| `ELEVENLABS_VOICE_ID_BN` | backend | No | Bengali |

### Payments (India, multi-gateway)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `RAZORPAY_KEY_ID` | compose | **Yes** | gates dispatch (501 without) |
| `RAZORPAY_KEY_SECRET` | compose | **Yes** | |
| `RAZORPAY_WEBHOOK_SECRET` | compose | **Yes** | webhook signature verify |
| `PHONEPE_MERCHANT_ID` | compose | **Yes** | PhonePe |
| `PHONEPE_SALT_KEY` | compose | **Yes** | PhonePe |
| `PHONEPE_SALT_INDEX` | compose | No | 1 |
| `CASHFREE_APP_ID` | compose | **Yes** | Cashfree |
| `CASHFREE_SECRET_KEY` | compose | **Yes** | Cashfree |
| `CASHFREE_WEBHOOK_SECRET` | compose | **Yes** | Cashfree |
| `PAYMENT_LINK_BASE_URL` | compose | No | gateway callback/link base |

### Notifications (WhatsApp-first, G6-Q8)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `WHATSAPP_TOKEN` | compose | **Yes** | gates WhatsApp dispatch |
| `WHATSAPP_PHONE_ID` | compose | **Yes** | WhatsApp Business phone id |
| `KNOWLARITY_SMS_TOKEN` | compose | **Yes** | Knowlarity SMS |
| `KNOWLARITY_SMS_SENDER_ID` | compose | No | Knowlarity SMS sender |
| `MSG91_AUTH_KEY` | compose | **Yes** | MSG91 |
| `MSG91_SENDER_ID` | compose | No | MSG91 |
| `MSG91_ROUTE` | compose | No | 4 |
| `SMTP_HOST` | compose | No | email channel |
| `SMTP_PORT` | compose | No | 587 |
| `SMTP_USER` | compose | **Yes** | |
| `SMTP_PASSWORD` | compose | **Yes** | |
| `SMTP_FROM` | compose | No | noreply@medicall.in |
| `FCM_SERVER_KEY` | compose | **Yes** | push |
| `FCM_SENDER_ID` | compose | No | push |

### DPDP Act 2023 + data residency (G6-Q2 -> G6-Q10)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `RETENTION_CALLS_DAYS` | compose, railway.toml | No | 365 |
| `RETENTION_RECORDINGS_DAYS` | compose, railway.toml | No | 365 (external objects) |
| `RETENTION_NOTIFICATIONS_DAYS` | compose, railway.toml | No | 180 |
| `RETENTION_AUDIT_DAYS` | compose, railway.toml | No | 2190 (6 yr, compliance_events) |
| `DPDP_BREACH_NOTIFICATION_HOURS` | compose, railway.toml | No | 72 |
| `DATA_RESIDENCY_REGION` | compose (PINNED `in`), railway.toml, .env.example | No | documented posture — see region pin |
| `DPO_NAME` | compose | No | designated DPO |
| `DPO_EMAIL` | compose | **Yes** | DPO contact |

### Auth — SSO/OIDC (gated until keys set)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | backend | No | Google SSO |
| `GOOGLE_OAUTH_CLIENT_SECRET` | backend | **Yes** | Google SSO |
| `MICROSOFT_OAUTH_TENANT_ID` | backend | No | Microsoft SSO |
| `MICROSOFT_OAUTH_CLIENT_ID` | backend | No | Microsoft SSO |
| `MICROSOFT_OAUTH_CLIENT_SECRET` | backend | **Yes** | Microsoft SSO |
| `ABHA_OAUTH_CLIENT_ID` | backend | No | ABDM/ABHA SSO |
| `ABHA_OAUTH_CLIENT_SECRET` | backend | **Yes** | ABDM/ABHA SSO |

### Frontend client (not in .env.example — Vercel project vars)
| Variable | Where | Secret? | Notes |
|---|---|---|---|
| `NEXT_PUBLIC_BACKEND_URL` | compose, vercel.json | No | backend origin for /api rewrites |
| `NEXT_PUBLIC_ENVIRONMENT` | compose, vercel.json | No | development / production |
| `NEXT_PUBLIC_DEBUG` | compose, vercel.json | No | false in prod |
| `NEXT_PUBLIC_USE_MOCK` | frontend | No | mock-data fallback flag (api.ts) |

## CI / smoke

- `.github/workflows/ci.yml`: backend (all stdlib suites + py_compile + ruff),
  frontend (npm ci + lint + build), stack (compose up → `smoke_api.py` →
  teardown) — the runtime proof that the running systems match
  `docs/uml/03-api-contracts.md`. `smoke_api.py` covers /health, clinics CRUD,
  calls, appointments, prescriptions, payments, notifications, compliance /
  consent and analytics.
- `.github/workflows/purge.yml`: the retention purge (see above).