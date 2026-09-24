# SPEC: MediCall AI — Idea Refinement Gap Audit

## Goal
Answer "did I miss anything in refining the idea" with a verifiable gap list between the approved direction (Indian voice-first Medical Call Center: PostgreSQL + pgvector, 5-language STT/TTS, Exotel/Knowlarity/Twilio India, Razorpay/PhonePe/Cashfree, FHIR/ABDM-ready) and what actually exists in the repo. No code changes in this spec — audit only, then sign-off on the fix list.

## Non-Goals
- No implementation, no file edits, no new dashboards/routes/UML in this spec.
- No Supabase reintroduction. No restaurant/Stripe/Square/Telnyx-US scope.
- No full HMS/inpatient build-out (call-center-first remains the scope).

## What Exists (verified this session, evidence-backed)
- `backend/postgres_schema.sql` — NEW medical schema (clinics, calls, appointments, prescriptions, call_embeddings, language_codes). Present.
- `backend/app/db/postgres.py` — NEW SQLAlchemy layer. Present BUT broken (see gaps).
- Deleted: 13 restaurant files (`supabase_schema.sql`, `supabase.py`, `orders.py`, `restaurants.py`, `payments.py`, `admin.py`, `order.py`, `restaurant.py`, `pos/base.py`, `pos/square.py`, `rag.py`, `workers/__init__.py`, `workers/celery_app.py`). Verified deleted via directory reads (`backend/app/api/` = only `voice.py`; `backend/app/db/` = only `redis.py`; `backend/app/models/` = only `call.py`; `backend/app/workers/` = empty).
- NOT yet migrated: `backend/main.py`, `backend/app/models/call.py`, `backend/app/api/voice.py`, `backend/requirements.txt`, `backend/app/services/pos/` (dir still listed), frontend, `docker-compose.yml`, env examples, tests, linters, UML.

## Gaps Found (load-bearing first)

### G1 — `backend/main.py` is broken and off-brand (BLOCKER)
- Still imports deleted modules: `from app.api import voice, orders, restaurants, payments, admin`, `from app.db.supabase import init_supabase`, `from app.workers.celery_app import celery_app`. App cannot start.
- Title/description still "TalkByte AI / AI Phone Ordering System for Australian Restaurants". Health check returns `talkbyte-api`.
- Expected: import only existing routers (voice + new calls/appointments/prescriptions/payments/clinics), lifespan inits `postgres.py` engine, title "MediCall AI", health returns `medicall-api`.

### G2 — `backend/app/db/postgres.py` has Python syntax errors (BLOCKER)
- Uses `--` (SQL comment) inside Python code, e.g. `default="starter") -- starter, growth, enterprise`. `--` is not a Python comment; file cannot import.
- `from sqlalchemy import Vector` is wrong; pgvector provides `from pgvector.sqlalchemy import Vector`.
- `Mapped[UUID]` uses SQLAlchemy's UUID type as annotation without `import uuid`; `relationship` never imported but used; `Call.embedding_rel = "CallEmbedding"` string assignment is not a relationship.
- `ClinicUser.__table_args__` is a dict, must be tuple of constraints.
- `get_db_session()` uses `yield` but is typed `-> AsyncSession` (needs `AsyncGenerator` + `@asynccontextmanager` or FastAPI `Depends` pattern).
- `log_call_embedding()` calls `session.get(CallEmbedding, call_id)` but PK is `id`, not `call_id` — lookup will always miss.
- Expected: file parses (`ast.parse` green), imports clean, models match `postgres_schema.sql` column-for-column.

### G3 — Two competing call state machines (BLOCKER)
- `backend/app/models/call.py` = restaurant flow: GREETING → TAKING_ORDER → CONFIRMING → CONFIRMED → PAYMENT_SENT, fields `restaurant_id`, `order_items`, states `POS_FAILED`, `TRANSFER_TO_HUMAN`.
- `backend/app/db/postgres.py` = medical flow: GREETING / TRIAGE / APPOINTMENT / PRESCRIPTION / COMPLETE / ESCALATED / DROPPED.
- `postgres_schema.sql` comment header still describes the OLD restaurant chain (TAKING_ORDER/CONFIRMING...).
- Expected: single medical state machine everywhere; `models/call.py` either deleted or rewritten as pure transition validator over the medical states (no restaurant fields).

### G4 — `backend/app/api/voice.py` still US-restaurant telephony (BLOCKER)
- Telnyx-only webhook (`call_control_id`), `restaurant_id` in `LiveKitStart`, TODOs for room dispatch/transcript save, "finalize order" language.
- Expected per spec-micc-india: Exotel + Knowlarity + Twilio India webhooks → LiveKit SIP room, `clinic_id`, 5-language tag (`hi/en/ta/te/bn`), transcript save to `calls.transcript`, escalation path.

### G5 — `backend/requirements.txt` stale + missing (MAJOR)
- Still pins `stripe`, `celery`, `gunicorn`, `psycopg2-binary`, dubious `sqlalchemy-asyncio==2.0.30` (not a real package name; async support ships inside SQLAlchemy).
- Has `exotel`, `twilio` but no Knowlarity client; payment libs (`razorpay`, `phonepe`, `cashfree-pg`) unpinned to spec versions; no `pytest`, `pytest-asyncio`, `ruff`/`flake8` for the red-green-lint workflow.
- Expected: Stripe/Celery/Gunicorn removed (or justified), Knowlarity path decided, dev/test/lint deps added.

### G6 — Idea-level refinements never locked (MAJOR — this is the "missed anything" list)
Not specified anywhere yet, each needs a decision before build:
1. AuthN/Z: OTP + password + SSO (Google/Microsoft/ABHA)? Role matrix (owner/staff/triage_agent/doctor/readonly)?
2. Consent & DPDP Act 2023: per-call recording consent flag, data localization, 72-hr breach flow, retention policy?
3. Clinical safety: triage guardrails (no diagnosis/dosage from AI), escalation triggers, red-team list, temperature≈0 paths?
4. Languages: exact 5 (hi/en/ta/te/bn) for MVP; fallback chain when STT confidence low; per-language TTS voice map?
5. Payments: which flows need money (appointment fee? teleconsult prepay?) and which gateway per flow + webhook idempotency?
6. Telephony routing: primary vs fallback among Exotel/Knowlarity/Twilio India; concurrent-call target; recording via LiveKit egress → MinIO/S3?
7. EHR/ABDM phasing: Phase 1 = no EHR writes (transcript only) vs minimal Appointment/Prescription FHIR resources now?
8. Notifications: SMS/WhatsApp/email/push provider per language; appointment reminders + no-show flow?
9. Analytics: which KPIs are MVP (call volume, triage mix, language dist, no-show, revenue)?
10. Deployment: `docker-compose.yml` services (postgres+pgvector, redis, backend, frontend?), Railway/Vercel Mumbai region, env var list?

### G7 — Frontend / infra / docs unaudited (MINOR, but blocks "done")
- `frontend/src/app/` routes, design-system tokens, clinic (7-tab) + admin (9-view) shells: existence unverified.
- `docker-compose.yml`, `.env.example`, `railway.toml`, `vercel.json`: not read this session; DB URL/env names may still reference Supabase.
- No tests, no linter config, no UML diagrams (ER/state-machine/API-contracts/data-flow/deployment) exist yet.

## Affected Files
- Read-only audit: `backend/main.py`, `backend/requirements.txt`, `backend/app/db/postgres.py`, `backend/app/models/call.py`, `backend/app/api/voice.py`, `backend/postgres_schema.sql`, directory listings above.
- Spec outputs (this task): `.opencode/spec-idea-refinement-gaps.md` (this file).
- Future fix scope (NOT this task): files in G1–G5 + frontend/infra + tests + UML.

## Expected Behavior (of this audit spec)
- A reviewer can open each G-item, open the named file:line, and confirm the gap exists without running anything.
- Sign-off means: "yes, G1–G7 is the complete fix list and G6 decisions are answered" — then implementation proceeds one task per fresh session.

## Acceptance Criteria
- [ ] G1–G5 each names the exact file + broken symbol (import name, title string, syntax pattern) — done above.
- [ ] G6 lists the 10 open idea decisions with options (not solutions) — done above.
- [ ] No code written or modified by this spec task (only this `.md` file created).
- [ ] Spec shown to user with explicit STOP for sign-off — this message is that stop.
- [ ] On approval, next session starts with G1+G2 (make the app import) before any dashboards/routes/UML.

## Risks
| Risk | Mitigation |
|------|------------|
| `postgres.py` `--` comments mean nothing in the DB layer is importable; any test run now is red for the wrong reason | Fix G2 first; do not write feature tests against a non-parsing module |
| Two state machines diverge silently (DB says TRIAGE, validator says TAKING_ORDER) | G3 mandates a single source of truth before any call-flow code |
| Telnyx-US assumptions leak into Indian telephony build | G4 blocks voice work until Exotel/Knowlarity/Twilio-India contract is chosen |
| Scope creep into full HMS | Non-goals + G6-Q7 phasing (transcript-only Phase 1) hold the line |

## Sign-off Record (2026-09-22)
- **Status**: APPROVED — G1–G7 confirmed as the complete fix list.
- **G6-Q1 Auth**: Full incl. ABHA login (OTP + password + Google/Microsoft SSO + ABHA).
- **G6-Q6 Telephony**: Multiple fallback sources — wire Exotel + Knowlarity + Twilio India all with fallback chain, no single primary.
- **G6-Q7 EHR/ABDM**: Transcript only for Phase 1 (no EHR writes; calls/appointments/prescriptions local only).
- **G6-Q2/Q3/Q4/Q5/Q8/Q9/Q10** (consent-retention, guardrails, language fallback, payment flows, notifications, KPIs, deploy topology): still open — answer before their respective build sessions.
- **Next**: fresh session, one task, starting with G1+G2 (make the app import: fix `main.py`, rewrite `postgres.py` so it parses).

## Implementation Record — G1+G2 DONE (2026-09-23)
- **Tests first (red)**: `backend/tests/test_g1_g2.py` (11 stdlib-only tests) ran RED pre-fix: 5 failures + 3 errors, confirming every G1/G2 claim.
- **G1 `main.py`**: deleted imports (`orders`, `restaurants`, `payments`, `admin`, `supabase.init`, `celery_app`) removed; title "MediCall AI", health `medicall-api`, lifespan awaits `init_db` from `app.db.postgres`, CORS scoped to `FRONTEND_URL`.
- **G2 `postgres.py`**: full rewrite — `#` comments only, `Vector` from `pgvector.sqlalchemy`, `uuid`/`relationship`/`UniqueConstraint` fixed, `get_db_session` is a typed async generator, `log_call_embedding` queries by `call_id`, proper `Call`↔`CallEmbedding` relationship, `CallSession` model added to match schema.
- **Verify**: 11/11 tests GREEN (`python3 tests/test_g1_g2.py` → OK); `py_compile` clean on all touched files; empty `app/services/pos/` removed.
- **Deferred (env has no third-party deps: fastapi/sqlalchemy/pytest/ruff absent)**: live `import main` / DB round-trip and ruff lint — tracked under G5 (requirements cleanup adds pytest/ruff); runtime verification belongs in Docker/CI.
- **Next in queue**: G3 (single medical state machine) → G4 (Exotel/Knowlarity/Twilio India voice) → G5 (requirements).

## Implementation Record — G3 DONE (2026-09-23)
- **Tests first (red)**: `backend/tests/test_g3_state_machine.py` (9 stdlib tests) ran RED pre-fix: 5 failures + 3 errors.
- **`app/models/call.py`**: rewritten as canonical medical state machine (stdlib-only): 9 states (GREETING/TRIAGE/APPOINTMENT/PRESCRIPTION/COMPLETE/ESCALATED/DROPPED/PAYMENT_SENT/PAYMENT_EXPIRED), terminal COMPLETE/ESCALATED/DROPPED, `clinic_id` + `caller_language` + `triage_severity` fields; restaurant states/fields gone.
- **`app/db/postgres.py`**: duplicate `CallState`/`TriageSeverity` enums deleted; now `from app.models.call import CallState, TriageSeverity` — single source of truth.
- **`postgres_schema.sql`**: stale restaurant-chain comment replaced with medical chain.
- **Verify**: G3 9/9 GREEN; G1+G2 11/11 still GREEN (no regression); `py_compile` clean.
- **Scoped out (belongs to G4)**: `services/livekit_agent.py` still restaurant-flavored end-to-end ("Mama's Pizzeria", `order_items`, `rag_menu`, `TAKING_ORDER` literal) — full agent rewrite is G4 voice-pipeline work, not G3.
- **Next in queue**: G4 (Exotel/Knowlarity/Twilio India voice) → G5 (requirements).

## Implementation Record — G4 SPEC DRAFTED, PENDING SIGN-OFF (2026-09-24)
- **Spec**: `.opencode/spec-g4-voice-pipeline.md` (in `.worktrees\g4-voice`) — scope
  (voice.py + livekit_agent.py + new stdlib `services/telephony.py` +
  `services/agent_logic.py` + medical llm.py/stt.py/tts.py + postgres
  `update_call_transcript`), evidence-backed webhook contract for all three
  providers, RED test plan, 3 decisions (D1 transcript path, D2 escalation MVP,
  D3 default language = hi). STOP for sign-off sent to user — no code written for G4.
- **Startup verified GREEN 2026-09-24** on `master`: G1+G2 11/11, G3 9/9,
  py_compile clean; branch `g4-voice` + worktree `.worktrees\g4-voice` created.
- **Launcher fixed & committed** (master `15106d4`): `start-worktree.ps1` failed
  to parse under PS 5.1 (UTF-8 em-dash read as ANSI → broken string terminator);
  saved with UTF-8 BOM; `git worktree add` aborted on NativeCommandError
  (git info writes to stderr while `$ErrorActionPreference='Stop'`) — stderr
  quieted under a scoped EAP. Worktree copy of the launcher is stale (pre-fix);
  always run the script from project root.
- **Next after sign-off**: write `tests/test_g4_voice.py` RED → implement →
  GREEN + py_compile → commit on `g4-voice` → then G5 (requirements).

## Implementation Record — G4 APPROVED (2026-09-24)
- Spec `spec-g4-voice-pipeline.md` **APPROVED** by user, all decisions locked:
  D1 agent→`/call-completed` persistence; D2 escalation MVP (flag + message +
  room event, PSTN stub); D3 `DEFAULT_CALLER_LANGUAGE=hi`.
- Implementation session continues on `g4-voice` immediately (tests RED first).

## Implementation Record — G4 DONE (2026-09-24)
- **GREEN verified**: `tests/test_g4_voice.py` 33/33, G1+G2 11/11, G3 9/9,
  py_compile exit 0 over all 10 touched modules. Commit `g4-voice d8b7239`.
- Delivered: 3 provider webhooks (`/webhook/{exotel,knowlarity,twilio}`) +
  `/livekit-agent-start` + `/call-completed` in `app/api/voice.py`; medical
  agent on G3 state machine in `livekit_agent.py`; new stdlib
  `services/telephony.py` (defensive parsers → normalized `ProviderEvent`,
  vendor field shapes verified 2026-09-24) and `services/agent_logic.py`
  (system prompt, `MEDICAL_FUNCTIONS` single source, `apply_intent`,
  transcript append, 5-language STT/TTS helpers); medical
  llm.py/stt.py/tts.py; `postgres.py::update_call_transcript`; `.env.example`
  +`DEFAULT_CALLER_LANGUAGE=hi` + `DEFAULT_CLINIC_ID`.
- RED captured pre-fix: 16 failures/errors (Telnyx/restaurant leftovers, missing
  modules/helpers) — first GREEN run had 1 failure that was a **test bug, not
  code**: `async def` functions are `ast.AsyncFunctionDef`, a SIBLING of
  `ast.FunctionDef`, so the walker skipped them; fixed by matching
  `(ast.FunctionDef, ast.AsyncFunctionDef)`.
- **Gotcha (one-line rule)**: in stdlib `ast` checks, match
  `isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))` — `FunctionDef`
  alone silently misses every `async def`.
- **Next**: G5 (requirements: drop stripe/celery, add pytest/ruff, Knowlarity
  client) → clinic (7-tab) + admin (9-view) dashboards → API routes → UML.

## Implementation Record — G5 DONE (2026-09-24)
- **Spec**: `.opencode/spec-g5-requirements-knowlarity.md` — APPROVED in-session
  via question tool; locked decisions: D1 in-house httpx Knowlarity client (no
  maintained PyPI SDK exists), D2 single requirements.txt with
  `# --- dev/test ---` section, D3 pinned pytest==8.3.5 /
  pytest-asyncio==0.25.3 / ruff==0.11.9.
- **GREEN verified**: `tests/test_g5_reqs.py` 18/18, G1+G2 11/11, G3 9/9,
  G4 33/33 (no regression), `py_compile` exit 0 over all touched modules.
  RED captured pre-fix: 5 failures + 1 error (stale pins, missing dev deps,
  wrong payment pins, missing env var, knowlarity.py import).
- **`backend/requirements.txt`**: dropped `stripe`, `celery`, `gunicorn`,
  `psycopg2-binary`, `sqlalchemy-asyncio` (NOT a real package); payments pinned
  to verified real SDKs — `razorpay==2.0.1`, `phonepe-pg-sdk-python==2.3.0`
  (import name `phonepe_sdk`; `phonepe==1.0.0` was a wrong/nonexistent name),
  `cashfree-pg==6.0.1` — verified against PyPI 2026-09-24; dev/test section
  added.
- **`backend/app/services/knowlarity.py`** (new): stdlib-importable Knowlarity
  SR API client — `KnowlarityConfig` + `from_env()`, `headers()`
  (`authorization` + `x-api-key`), URL builders (`call/makecall`,
  `call/campaign`, `call/campaign/order-status/?order_id=`), `makecall_payload`,
  `campaign_payload` (default tz `Asia/Kolkata`, `yyyy-MM-dd HH:mm`
  start_time), defensive `_id_of`; transport (`make_call`, `place_campaign`,
  `campaign_status`) imports httpx lazily — same pattern as telephony.py.
  Endpoints verified developer.knowlarity.com + Gupshup docs 2026-09-24.
- **`backend/.env.example`**: +`KNOWLARITY_AUTHORIZATION=` with SR-auth comment.
- **Gotcha (one-line rule)**: `datetime.UTC` (class attr) is NOT available on
  every runtime while `datetime.utcnow()` IS deprecated — use
  `datetime.now(timezone.utc)` (works everywhere, no deprecation warning, and
  a DeprecationWarning on stderr makes PowerShell report a bogus exit 1 via
  `2>&1` even when tests pass — keep warnings out of the code; check
  `$LASTEXITCODE` for the honest exit code).
- **Next**: clinic (7-tab) + admin (9-view) dashboards → API routes → UML →
  Docker/CI integration stage (real provider round-trips, live STT/TTS/LLM,
  LiveKit room lifecycle, `/call-completed` + `update_call_transcript` DB path).

## Implementation Record — DASHBOARDS DONE (2026-09-24)
- **Spec**: `.opencode/spec-dashboards-clinic-admin.md` — APPROVED via question
  tool; locked decisions: **D1** = clinic nav exactly 7 tabs, Settings in the
  header (not the sidebar), **D2** = scope = dashboards + tokens + minimal
  toolchain fix (marketing site / full design system stay queued), **D3** =
  Tailwind v4 CSS-first migration. Branch `gd-dashboards` off `g4-voice`
  tip `503fad6`: spec `555bb6b` → RED test `71bcb67` → feat `4f639df`.
- **RED verified**: `tests/test_dashboards.py` 34 tests, 30 failures against
  the restaurant/broken frontend (every gap mapped: Supabase import, v3
  toolchain, no postcss config, sky-blue v3 config, restaurant group, TalkByte
  branding, no `(clinic)`/components).
- **GREEN verified**: 34/34; full regression G1+G2 11/11, G3 9/9, G4 33/33,
  G5 18/18 (105 total), `py_compile` exit 0. Green needed 2 fixes: contiguous
  "MediCall AI" in root page (see gotcha) + test-data filename correction.
- **Toolchain (D3)**: `src/app/globals.css` rewritten CSS-first —
  `@import "tailwindcss"` + `@theme` tokens (medical teal primary 50–950,
  `--color-background/surface`, severity green/amber/red/critical, multilingual
  font stack hi/en/ta/te/bn scripts), `@layer base/components` (card,
  btn-primary/secondary); `frontend/postcss.config.mjs` = `@tailwindcss/postcss`;
  `tailwind.config.js` DELETED; `autoprefixer` dropped from package.json;
  `@tailwindcss/postcss` added (`^4.0.0`); `next.config.js` Supabase image
  domain removed (standalone output + `/api` proxy rewrite kept).
- **Cleanup**: `(restaurant)/` group deleted; root `page.tsx` = branded
  placeholder (no TalkByte); root `layout.tsx` = MediCall AI metadata, dark
  `colorscheme` tokens on body.
- **Components** (`frontend/src/components/`): `nav.ts` single source —
  `CLINIC_NAV` (7 hrefs) + `ADMIN_NAV` (9 hrefs), SVG path icons; `sidebar.tsx`
  (client: brand logo = teal cross+waves, active tab state, mobile FAB +
  overlay, user section) + `header.tsx` (settings gear when `settingsHref`
  passed — clinic shell passes `/settings`, D1); `card.tsx`, `stat-card.tsx`,
  `badge.tsx`; `language-badge.tsx` (hi/हिन्दी en/English ta/தமிழ் te/తెలుగు
  bn/বাংলা), `severity-badge.tsx` (4 levels), `call-state-badge.tsx` (9 G3
  states), `mock.ts` (medical India mock: +91, ₹, gateways Razorpay/PhonePe/
  Cashfree, telephony Exotel/Knowlarity/Twilio-India, 9 providers infra).
- **Pages** (16, static server components, mock data only — no API wiring):
  `(clinic)/layout.tsx` + dashboard, live-calls, triage-queue, appointments,
  prescriptions, patients, analytics (Settings via header); `(admin)/layout.tsx`
  + page(Overview), live-monitor, clinics, doctors, patients, revenue,
  billing, infrastructure, audit.
- **Gotcha (one-line rule)**: gradient/theme spans that SPLIT a brand string
  (`MediCall <span>AI</span>`) break `assertIn("MediCall AI", file)` source
  checks — keep brand strings contiguous and apply the span class to the whole
  string.
- **Gotcha (one-line rule)**: Next.js tab pages live at `(group)/<tab>/page.tsx`
  — acceptance tests must expect filename `page`, not the tab name; my
  `CLINIC_TAB_FILES` used `("dashboard","dashboard")` and failed once on the
  correct impl (admin side had it right with `("", "page")`).
- **Next**: API routes phase (`main.py` already expects calls/appointments/
  prescriptions/payments/clinics routers) → UML → Docker/CI integration stage
  (live provider round-trips, real Deepgram/ElevenLabs/OpenAI, LiveKit room
  lifecycle, `/call-completed` + `update_call_transcript` DB path, ruff
  actually run, `next build`).

## Implementation Record — API ROUTES DONE (2026-09-24)
- **Spec**: `.opencode/spec-api-routes.md` — APPROVED via question tool; locked
  decisions: **D1** = backend routers only (frontend wiring of the 16 mock pages
  moves to Docker/CI where `next build` can verify it), **D2** = minimal
  `payments` table + scaffold router (records intent only — NO gateway SDK
  calls; G6-Q5 gated; statuses chosen to match gateway webhook states),
  **D3** = new `app/schemas/` package (one module per domain + status/gateway
  constants as validation single source). Branch `ga-api-routes` off
  `gd-dashboards` tip `640ab2c`: spec `9437649` → RED test `72e3e96` →
  feat `3ff3f66`.
- **RED verified**: `tests/test_api_routes.py` 36 tests, **32 failures** against
  the voice-only state (every gap mapped: 5 missing routers, no schemas/ package,
  no Payment model / Numeric import, no clinic list/update, no call get/list
  (severity/date/pagination), no appointment/prescription get/list/status, no
  payment CRUD, no payments table, main.py including 1 of 6 routers).
- **GREEN verified**: 36/36; full regression G1+G2 11/11, G3 9/9, G4 33/33,
  G5 18/18, dashboards 34/34 (**105 total; 141 with the new suite**);
  `py_compile` exit 0 over all 16 touched modules.
- **GREEN needed 3 fixes**: (1) test-helper bug — `include_router(<mod>.router)`
  `args[0].attr` is ALWAYS `'router'`; read `args[0].value.id` for the module
  (see gotcha); (2) `payments.py` docstring listed 3 of 4 gateways — the
  `manual` literal was missing (self-documenting routers keep acceptance
  literal-checks honest); (3) bonus: the leftover scan caught a stale
  `postgres_schema.sql` comment "replaces restaurants from TalkByte AI" → now
  "medical call center tenants" (no prior scan covered backend files).
- **Delivered**: 5 self-contained routers (`APIRouter(prefix="/api/<name>",
  tags=[...])` — full paths in decorators; voice stays include-time-prefixed in
  main.py and is untouched); `app/schemas/` package (clinic/call/appointment/
  prescription/payment request models; `APPOINTMENT_STATUSES`,
  `PRESCRIPTION_STATUSES`, `PAYMENT_STATUSES`, `PAYMENT_GATEWAYS` constants);
  `postgres.py` += `Payment` ORM + 14 CRUD helpers (`list_calls` supersedes
  `list_clinic_calls`, which stays a thin wrapper); `postgres_schema.sql` +=
  payments table (NUMERIC(10,2) amount, INR default, gateway
  razorpay|phonepe|cashfree|manual, status pending|captured|failed|refunded) +
  index + trigger + RLS + grant; `main.py` registers all 6 routers, stale
  comment gone. Call state PATCH validates against `STATE_TRANSITIONS` before
  the raw setter (invalid → 409). Query key `from`/`to` via FastAPI `Query`
  alias on the `from_` kwarg.
- **Contract for Docker/CI**: endpoint table in `spec-api-routes.md` — smoke it
  over HTTP next stage: clinics (list/create/get/patch), calls (list with
  state|language|severity|from|to|limit|offset + detail + PATCH state 409-on-
  invalid + transcript GET), appointments/prescriptions/payments (list/create/
  detail + status PATCH, 422 on invalid status).
- **Gotcha (one-line rule)**: in `ast`, `app.include_router(clinics.router)`
  gives `args[0].attr == "router"` for EVERY router — the module name is
  `args[0].value.id`; assert that or all routers mask as `'router'`.
- **Gotcha (one-line rule)**: schema/gateway constant LITERALS asserted by
  source-level acceptance tests must appear in the router file's own text —
  keep routers self-documenting (docstring lists the full value set) or the
  assertion reads empty/partial text.
- **Next**: UML diagrams (ER / state machine / API contracts / data flow /
  deployment) → Docker/CI integration stage (frontend wiring to these
  endpoints, `next build`, live provider round-trips, `/call-completed` +
  `update_call_transcript` DB path, ruff actually run).
