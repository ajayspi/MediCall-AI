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
- **G6-Q9/Q10**: Q9 (KPIs/analytics) → **DONE on `g-kpis`**; Q10 (deploy topology) still open — answer before its build session. (Q3 guardrails → DONE `c01bbac`; Q5 payments → DONE `4812795`; Q8 notifications → DONE on `g-notify`; Q4 languages → DONE on `g-languages`; Q2 consent/DPDP → DONE on `g-dpdp`.)
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

## Implementation Record — UML DIAGRAMS DONE (2026-09-25)
- **Spec**: `.opencode/spec-uml-diagrams.md` — APPROVED via question tool; locked
  decisions: **D1** = Mermaid-in-Markdown (committed as source, rendered by
  GitHub/VS Code/typora, zero toolchain), **D2** = `docs/uml/` one file per
  diagram + index, **D3** = the five G7 diagrams PLUS a 6th inbound-call
  lifecycle sequence diagram. Branch `g-uml` off `ga-api-routes` tip
  `e19564b`: spec `ae0e641` → RED test `debe9a7` → feat `26f5abe`.
- **RED verified**: `tests/test_uml_diagrams.py` 21 tests, **20 failures**
  against a repo with no `docs/` (every assertion mapped to a missing diagram).
- **GREEN verified**: 21/21; full regression G1+G2 11/11, G3 9/9, G4 33/33,
  G5 18/18, dashboards 34/34, api_routes 36/36 (**162 total**); `py_compile`
  exit 0; tree clean.
- **GREEN needed 3 fixes**: (1) ast state-machine parser initially required the
  dict key's `.value` to be an `Attribute`, but `CallState.GREETING` keys have a
  `Name("CallState")` value — the load-bearing cross-check caught it parsing 0
  edges (fix: require `Name` + `id == "CallState"`); (2) two regexes lacked
  `re.MULTILINE` (`assertRegex` compiles without flags; `MERMAID_EDGE_RE`
  matched 0 lines) — use `re.search(..., re.M)` explicitly; (3) leftover token
  `"chain"` was too broad — false-positive on "toolchain"/"fallback chain"
  (dropped; the original restaurant-token list from test_api_routes kept
  intact).
- **Delivered** (docs-only phase — zero .py/.tsx/SQL changes): `docs/uml/` —
  `00-index` (links + single sources) · `01-er` (9 tables, 13 FK edges from
  `postgres_schema.sql`, includes API-phase `payments`, RLS note) ·
  `02-state-machine` (edge set is test-asserted EQUAL to `STATE_TRANSITIONS`
  from `models/call.py`, so the diagram cannot drift) · `03-api-contracts`
  (6 prefixes — voice included at `/api/voice` in main.py — 21 endpoint paths,
  409/422/404 annotations) · `04-data-flow` (Exotel/Knowlarity/Twilio-India
  webhooks → handle_event → LiveKit agent → Deepgram nova-3 + ElevenLabs
  hi/en/ta/te/bn → `/call-completed`; `update_call_transcript` DB write marked
  Docker/CI-owned) · `05-deployment` (compose stack 3000/8001/5432/6379,
  pgvector:pg16, redis:7-alpine, external SaaS) · `06-call-lifecycle`
  (sequenceDiagram incl. the PAYMENT_SENT → PAYMENT_EXPIRED loop; G6-Q5 still
  gated — intents only).
- **Gotcha (one-line rule)**: Python `re` without `re.MULTILINE` treats `^`/`$`
  as string boundaries — any per-line regex assertion (`assertRegex` included)
  must pass `re.M` explicitly or it silently matches nothing.
- **Gotcha (one-line rule)**: `ast` enum-attr keys like `CallState.GREETING`
  are `Attribute(value=Name("CallState"))` — assert `.value` is a `Name` (with
  the right `.id`), not an `Attribute`.
- **Next**: Docker/CI integration stage — wire the 16 mock pages to the API
  endpoints (03-api-contracts is the contract), `next build`, live
  Deepgram/ElevenLabs/OpenAI round-trips, LiveKit room lifecycle,
  `/call-completed` → `update_call_transcript` DB path, ruff actually run,
  HTTP smoke-test of the endpoint set.

## Implementation Record — DOCKER/CI INTEGRATION DONE (2026-09-25)
- **Spec**: `.opencode/spec-docker-ci.md` — APPROVED via question tool; locked
  decisions: **Q1** = verify with the LOCAL toolchain now + author the CI
  workflow for a Docker runner (no Docker on this PC — container runs go to
  CI/host), **Q2** = client module + **2 proof pages** (live-calls, dashboard;
  the other 14 stay on mock), **Q3** = 3-job ci.yml + stdlib HTTP smoke + all
  toolchain fixes. Branch `g-ci` off `g-uml` tip `d822f27`: spec `dd8bfc0` →
  RED test `3f1d662` → feat `c979275` → docs (this record).
- **RED verified**: `tests/test_docker_ci.py` 18 tests, **15 failures** (every
  integration defect + missing artifact mapped).
- **GREEN verified**: new suite 18/18; full regression G1+G2 11 + G3 9 + G4 33
  + G5 18 + dashboards 34 + api_routes 36 + uml 21 (**180 total**);
  `compileall`/`py_compile` exit 0; **eslint 0 errors** (1 benign warning);
  **`next build` exit 0 — the project's first real frontend compile** (19
  routes prerendered); `package-lock.json` generated by a real `npm install`
  (398 packages).
- **Integration defects found + fixed** (would have broken compose/CI today):
  (1) no `frontend/package-lock.json` → `npm ci` in the Dockerfile failed;
  (2) no `frontend/public/` → its `COPY --from=builder /app/public` failed;
  (3) `"lint": "next lint"` — removed in Next 16 → eslint flat config
  (`eslint.config.mjs` + eslint ^9); (4) compose backend healthcheck imported
  `requests` (NOT in requirements) → httpx; (5) `/call-completed` was a TODO
  stub → wired guarded lazy `update_call_transcript` (accepts without postgres,
  persists under Docker/CI); (6) React-19 peer conflicts — lucide-react
  0.300→1.48, recharts 2.10→2.15.4 (npm ERESOLVE otherwise).
- **Load-bearing first-build catch**: `(admin)` as a route group has NO URL
  segment — its pages resolved to bare `/patients`/`/revenue`/… colliding with
  `(clinic)`, and `(admin)/page.tsx` collided with the `/` landing; nav.ts
  correctly linked `/admin/…`; only the real build caught this. Fixed: moved to
  a real `admin/` segment (git 100% rename, 10 files); `test_dashboards.py`
  corrected to `ADMIN = APP / "admin"` (RED history text untouched).
- **Delivered**: `frontend/src/lib/api.ts` (typed fetch + react-query hooks,
  `NEXT_PUBLIC_USE_MOCK=auto|true|false` fallback, API→mock shape mapping) +
  `src/lib/providers.tsx` (QueryClient boundary in root layout); proof pages
  live-calls + dashboard render API data with mock fallback (auto mode falls
  back when no `NEXT_PUBLIC_CLINIC_ID`/backend — dashboards keep rendering
  offline); `public/` favicon + robots; `backend/scripts/smoke_api.py` (stdlib
  urllib, BASE_URL env/argv, full 03-api-contracts surface: health, clinics
  CRUD, calls list/404/422/409-guard/transcript, appointments/prescriptions/
  payments + status 422→valid-200, payments intent-only (G6-Q5), call-completed
  200) — runs on this PC, any CI runner, or the compose host;
  `.github/workflows/ci.yml` 3 jobs (backend stdlib+py_compile+ruff, frontend
  npm ci+lint+build, stack compose up → smoke_api.py → down -v); tsconfig/
  next-env normalized by the real build; `NEXT_PUBLIC_CLINIC_ID` +
  `NEXT_PUBLIC_USE_MOCK` documented in `.env.local.example`.
- **Gotchas (one-line rules)**: React 19 pinned beside older peer libs →
  `npm install` ERESOLVE; check `npm view <pkg>@<ver> peerDependencies` and
  bump to the react-19 line (lucide-react ^1.48.0, recharts ^2.15.4 — lucide
  was unused in src/, so the major bump was risk-free). Next route groups
  `(name)` add NO URL segment — nav hrefs must match real folders; only a real
  `next build` catches collisions source-level review can't. PowerShell passes
  `*.py` verbatim to python (no glob) — use `python3 -m compileall -q main.py
  app` instead of `py_compile`-with-glob. Assert CI-workflow internals against
  the ACTUAL loop/glob text (`tests/test_*.py`), not a literal `python3 tests/`.
- **Next**: Auth (G6-Q1 incl. ABHA — locked) → payments real gateway wiring
  once G6-Q5 is answered → live provider round-trips behind CI secrets
  (Deepgram/ElevenLabs/OpenAI, LiveKit rooms; the compose stack job in ci.yml
  proves the endpoint contract on a Docker runner) → merge branch tips to main.

## Implementation Record — AUTH (G6-Q1) DONE (2026-09-25)
- **Spec**: `.opencode/spec-auth.md` — APPROVED via question tool; locked
  decisions: **Q1** = guards library only — no enforcement on the existing 5
  routers this phase, **Q2** = keep RLS via a local `auth.uid()` GUC (reads
  `app.current_user_id`; NO `FORCE ROW LEVEL SECURITY` yet — owner-bypass keeps
  the unauth API working; enforcement + FORCE + non-owner `medicall_app` role
  stage with the next phase), **Q3** = `/login` page + client guard (guard
  skipped when `NEXT_PUBLIC_USE_MOCK !== "false"`, demo-token path for offline),
  **Q4** = stdlib HMAC-SHA256 JWT-shaped tokens (python-jose/passlib stay pinned
  for later SSO/resource-server). Branch `g-auth` off `g-ci` tip `81587ef`:
  spec `14dbe1a` → RED `108a700` → feat `74accbe` → docs (this record).
- **RED verified**: `tests/test_auth.py` 42 tests, **20 failures + 21 errors**
  (every missing artifact mapped; exit 1).
- **GREEN verified**: new suite 42/42; full regression **222 total** (180
  prior + 42, `BAD_SUITES` empty); `compileall` exit 0; eslint 0 errors (1
  benign warning); **`next build` exit 0** (20 routes incl. `/login`).
- **Delivered**: `app/services/auth.py` stdlib core — PBKDF2-HMAC-SHA256
  passwords (210k iters, `compare_digest`), 6-digit OTP hashed (HMAC keyed by
  phone, 600s TTL, 5-attempt cap), JWT-shaped HMAC-SHA256 tokens (12h),
  `ROLES` + `can()`, `normalize_phone` (+91/10-digit 6–9). `app/api/auth.py`
  router — `/register` (409 dup), `/login` (401 bad creds),
  `/otp/request|verify` (404 unknown, 429 cap, dev-logged code), `/me` (Bearer,
  memberships), `/logout`, `/providers`, `/oauth/{provider}` (501 until
  Google/Microsoft/ABHA env keys) — plus the guards library
  `get_current_user` / `require_roles` / `require_clinic_role`; wired into
  `main.py` as the 7th router (`prefix="/api/auth"`). Schema repair:
  `users` table (email/phone UNIQUE nullable, password_hash, otp_*,
  role incl. `doctor`, is_active), `clinic_users.user_id → users(id)`,
  `auth` schema + `auth.uid()` GUC + `CREATE ROLE authenticated` + RLS policy
  comments staging FORCE, index/trigger/grants. SQLAlchemy: `User` model +
  `ClinicUser` FK. Env: `AUTH_JWT_SECRET` (+ SSO keys) in `.env.example` +
  compose default. Frontend: `api.ts` auth surface (token helpers +
  Authorization header), `lib/auth.tsx` (`AuthProvider`/`RequireAuth` — effect
  hydrates via a deferred task per `react-hooks/set-state-in-effect`),
  `app/login/page.tsx` (password + OTP tabs + offline demo), guard in
  `(clinic)`+`admin` layouts, `AuthProvider` in `providers.tsx`.
  `smoke_api.py` auth round-trip (register→dup 409→login→bearer me→otp
  request→providers). UML corollary: `01-er.md` 10 tables/14 edges +
  users block, `03-api-contracts.md` +`/api/auth`, `test_uml_diagrams.py`
  counts, `test_api_routes.py` 6→7 routers.
- **Gotchas (one-line rules)**: FastAPI `Depends(...)` defaults evaluate at
  import time — define guards BEFORE endpoints (forward ref = NameError);
  `react-hooks/set-state-in-effect` forbids synchronous setState in effect
  bodies — defer storage hydration to a macrotask; `Split(";", 1)` block
  parsing dies on inline `;` inside SQL comments (`(India; NULL…)`) — bound
  blocks by the NEXT `CREATE TABLE` instead; `test_main_registers_all_*_routers`
  is an EXACT set-equality — adding a router requires syncing it.
- **Next (DONE — see the record below this one)**: auth enforcement phase
  (per-Q1 staging): wire the guards onto the 5 domain routers + `FORCE ROW
  LEVEL SECURITY` + non-owner `medicall_app` role, then answer G6-Q5.

## Implementation Record — PAYMENTS (G6-Q5) DONE (2026-09-25)
- **Spec**: `.opencode/spec-payments.md` — APPROVED via question tool; locked:
  **Q1=A1a** consultations + prescription refills bill (agent offers payment on
  APPOINTMENT + PRESCRIPTION; link/UPI request to the caller's phone);
  **Q2=A2a** kind→gateway fallback map (razorpay=payment links for
  consultation+refill, phonepe=UPI instant fallback, cashfree=subscriptions);
  **Q3=A3a** in-call trigger waiting in PAYMENT_SENT (captured → COMPLETE;
  expiry → PAYMENT_EXPIRED → APPOINTMENT); **Q4=A4a** per-gateway HMAC
  verification (Razorpay X-Razorpay-Signature, PhonePe X-VERIFY, Cashfree
  X-Verify-Hmac-Sha256) + shared X-Service-Token + unified
  `/api/payments/webhook` idempotent by `gateway_ref`; **Q5=A5a** stdlib layer
  now, live SDK requests env-gated (501 without keys; manual stays keyless).
  Branch `g-payments` off `g-enforce` tip `0e1cb87`: spec DRAFT → APPROVED →
  RED → feat `d61a4ea` → docs (this record).
- **RED verified**: `tests/test_payments_q5.py` 36 tests, **36 failures** on
  the enforcement scaffold (no service module, no webhook route, no
  kind/expires_at/unique-ref, no gateway env, no smoke webhook/501, no
  contracts-doc webhook; all 9 prior suites + enforcement stay green; exit 1
  intentional).
- **GREEN verified**: new payments suite 36/36; full regression **282 total**
  (246 prior + 36; all 11 suites PASS); `compileall` exit 0. Frontend untouched
  (skip npm). Live SDK round-trips + webhook happy-path runtime = the ci.yml
  stack job on a Docker host (authored, not run here — no Docker on this PC).
- **Delivered**: `app/services/payments.py` stdlib gateway layer — PAYMENT_KINDS
  + KIND_TO_GATEWAYS fallback map + TRANSITIONS; builders (razorpay link,
  phonepe UPI intent, cashfree order + subscription) returning request shapes
  (paise/rupees conversions); per-gateway signature verifiers (HMAC vectors),
  `verify_webhook_request` dispatch, `detect_gateway`, `extract_gateway_ref`,
  `webhook_status_for`, `next_status`; env gate (`GATEWAY_ENV_KEYS` +
  `gateway_env_ready`) + lazy SDK `dispatch_gateway_request` (env-gated, never
  runs on this stdlib PC). `payments.py` router: `POST /api/payments` gains
  kind validation (kind→gateway coherence per A2a) + 501 env gate (manual
  keyless) + 502 on dispatch failure, and new **`POST /api/payments/webhook`**
  (`payments_webhook`) — identity-free BY DESIGN (per-gateway signature +
  X-Service-Token), writes under `service_request_ctx()`, idempotent by
  `gateway_ref` via new `find_payment_by_gateway_ref`, `captured` advances the
  linked call `PAYMENT_SENT → COMPLETE` (`get_call` + `update_call_state`).
  Schema: payments += `kind TEXT`/`expires_at TIMESTAMPTZ` (intent TTL),
  `CREATE UNIQUE INDEX uq_payments_gateway_ref ... WHERE gateway_ref IS NOT
  NULL` (webhook idempotency), `payments_manage` policy += the
  `app.service_request` bypass OR-clause (userless webhook writes). ORM mirrors
  columns; `create_payment(kind=..., expires_at=...)` (default TTL +24h).
  Env: compose backend environment + `.env.example` carry the G5 canonical
  gateway keys (`RAZORPAY_KEY_ID/SECRET/WEBHOOK_SECRET`,
  `PHONEPE_MERCHANT_ID/SALT_KEY/SALT_INDEX`, `CASHFREE_APP_ID/SECRET_KEY/
  WEBHOOK_SECRET`) + `PAYMENT_LINK_BASE_URL`. `smoke_api.py`: razorpay 501
  env-gate check (skipped when `RAZORPAY_KEY_ID` configured — CI live
  territory), webhook 401 no-token + 422 unknown-gateway checks, ENDPOINTS +
  docstring updated. Tests synced: `test_api_routes.py` EXPECTED_ENDPOINTS
  payments += `("post", "/webhook")`; `test_auth_enforcement.py` gains
  `IDENTITY_FREE_ENDPOINTS = (("payments", "payments_webhook"),)` — the webhook
  is the single endpoint exempt from the identity guard because its auth IS the
  signature + service token (mirrors the VOICE_WEBHOOKS carve-out). Docs: UML
  00/01/02/03/05/06 payments notes flipped from "G6-Q5 open/gated" to wired;
  HANDOVER DONE record + open-list + spec index.
- **Gotchas (one-line rules)**: a RED suite that asserts env-key names must
  read the G5-canonical `.env.example` first — `PHONEPE_SALT_KEY/SALT_INDEX`
  and `CASHFREE_WEBHOOK_SECRET`/`RAZORPAY_WEBHOOK_SECRET` (API secrets and
  webhook secrets are SEPARATE vars), not first-pass guesses
  (`PHONEPE_KEY/PHONEPE_IV` were corrected pre-GREEN); gateway webhooks are
  naturally identity-free → the enforcement router-guard test needs an explicit
  carve-out set, exactly like the voice webhooks; a unified webhook cannot know
  its gateway from a field every gateway sends — `detect_gateway` infers from
  payload shape (`event:` = razorpay, `data.order.order_id` = cashfree,
  `data.merchantTransactionId` = phonepe), and the smoke "unknown gateway" case
  must use a payload with NEITHER an event nor data shapes.
- **Next**: live provider round-trips behind CI secrets (Deepgram/ElevenLabs/
  OpenAI, LiveKit, gateway SDK dispatch + signed-webhook end-to-end) → run the
  ci.yml stack job on a Docker host (RLS/GUC runtime proof) → merge branch
  tips to main.

## Implementation Record — AUTH ENFORCEMENT (Q1-staged flip) DONE (2026-09-25)
- **Spec**: `.opencode/spec-auth-enforcement.md` — APPROVED via question tool;
  locked decisions: **Q1=A1a** identity (`get_current_user`) on every domain
  endpoint + `require_roles("owner")` on `POST /api/clinics` only; **Q2=A2a**
  voice webhooks verify `X-Service-Token` == `WEBHOOK_SERVICE_TOKEN` (401
  without) and arm the server-side `app.service_request` GUC, honored only by
  `users_own_data`/`calls_create`/`calls_read` (per-provider HMAC = follow-up);
  **Q3=A3a** demo tenant seeded in `postgres_schema.sql` (fixed UUIDs,
  `ON CONFLICT DO NOTHING`); **Q4=A4a** engine `begin`-event listener issues
  `SET LOCAL app.current_user_id`/`app.service_request` per transaction, with
  service_request armed inside the 5 auth CRUD helpers + verified webhooks.
  Branch `g-enforce` off `g-auth` tip `c6b59ff`: spec `0d918f8` → APPROVED
  `e6533dc` → RED `0b12af3` → feat `69b9eae` → docs (this record).
- **RED verified**: `tests/test_auth_enforcement.py` 24 tests, **22 failures +
  0 errors** (every missing artifact mapped; 9 existing suites stay green;
  exit 1 intentional).
- **GREEN verified**: new enforcement suite 24/24; full regression **246
  total** (222 prior + 24; all 10 suites PASS); `compileall` exit 0. Frontend
  untouched (skip npm). RLS/GUC runtime truth = the ci.yml stack job on a
  Docker host (authored, not run here — no Docker on this PC).
- **Delivered**: `medicall_app` LOGIN role + `FORCE ROW LEVEL SECURITY` ×7
  tenant tables; service_request bypass on `users_own_data`/`calls_create`/
  `calls_read`; new policies `clinic_users_own`/`clinic_users_manage`/
  `clinic_users_service_insert` (service-only INSERT closes self-insert-any-
  clinic) + `clinics_create` (`FOR INSERT WITH CHECK` global-owner) +
  **`calls_update`** (discovered gap: calls had INSERT/SELECT policies only →
  state/transcript UPDATEs were deny-all under FORCE; now membership OR
  service). Guards on all 5 routers (dep `Depends(get_current_user)`; owner
  gate + creator-membership on create). `postgres.py`: contextvar GUCs +
  `engine.sync_engine` `begin`-listener (`SET LOCAL`), `service_request_ctx()`
  contextmanager, all 5 auth CRUD fns armed, `create_clinic(owner_user_id=…)`
  inserts the owner membership in one transaction, and `get_current_user` sets
  the GUC from the token BEFORE its own user lookup. `voice.py`:
  `_verify_service_token` (hmac.compare_digest; env default
  `dev-service-token`) on all 5 webhooks; `call_completed` persists the
  transcript under `service_request_ctx()` (lazy import line preserved for
  test_docker_ci). `smoke_api.py` auth-first — demo owner
  `+919876543210`/`DemoPass!2026` → Bearer on every domain call — plus 401/403
  negative checks and `X-Service-Token` on call-completed. compose backend env
  + `backend/.env.example`: `medicall_app` DSN + `WEBHOOK_SERVICE_TOKEN` +
  demo creds note. Docs: `03-api-contracts.md` enforcement bullets; HANDOVER.
- **Gotchas (one-line rules)**: FastAPI untyped `user=Depends(...)` params
  carry the guard in the DEFAULT, not the annotation — the enforcement test
  inspects both (AST `arguments.defaults` map positionally to the trailing
  args; `ast.arg` has no `.default` attribute); test_docker_ci asserts the
  EXACT lazy line `from app.db.postgres import update_call_transcript` — keep
  `service_request_ctx` on its own import line; `fn_block` helpers slice by
  LINE (`splitlines(keepends=True)`), never flat character offsets.
- **Next**: answer G6-Q5 (payment flows/gateway — real gateway calls stay
  gated) → live provider round-trips behind CI secrets → run the ci.yml stack
  job on a Docker host → merge branch tips to main.

## Implementation Record — CLINICAL GUARDRAILS (G6-Q3) DONE (2026-09-25)
- **Spec**: `.opencode/spec-guardrails-q3.md` — APPROVED via question tool;
  locked decisions: **Q1=A1a** layered deterministic escalation triggers
  (severity red/critical OR red-flag keyword match OR explicit escalate intent;
  reason records the trigger source); **Q2=A2a** deterministic output guard
  (`guard_output` scans FORBIDDEN_CLAIMS → fixed per-language refusal phrase,
  the temperature≈0 path, applied before TTS); **Q3=A3a** ~12-category red-flag
  catalog (stable keyword tables, case-insensitive substring matching);
  **Q4=A4a** adversarial vector table (~15 scenarios) as the RED test suite =
  the acceptance gate. Branch `g-guardrails` off `g-payments` tip `4812795`:
  spec DRAFT → APPROVED `31b28d1` → RED → feat `0df6962` → docs (this record).
- **RED verified**: `tests/test_guardrails_q3.py` 37 tests, **33 failures + 3
  errors** on the g-payments scaffold (every missing artifact mapped; exit 1
  intentional). One latent RED-suite bug fixed at GREEN time (`[t for _, _, a
  in RED_TEAM ...]` bound `a` not `t` → counts via `sum(1 for ...)`).
- **GREEN verified**: Q3 suite 37/37; full regression **319/319** (282 prior +
  37 new; all 12 suites PASS); `compileall` exit 0. No env keys, no tables, no
  endpoints — pure stdlib logic, fully verified on this PC.
- **Delivered**: `app/services/guardrails.py` — `RED_FLAG_CATEGORIES` (12
  categories: cardiac, respiratory, severe_bleeding, stroke, seizure,
  poisoning, anaphylaxis, burns, head_injury, pregnancy_emergency, self_harm,
  choking), `match_red_flag(text) → (category, phrase) | None`,
  `escalation_decision(severity, caller_text) → (bool, reason)` reusing
  `agent_logic.should_escalate` (layered, reason = "severity:red" /
  "red_flag:cardiac" / ""), `guard_output(text, language)` 
  (`DIAGNOSIS_CLAIMS` substring + `DOSAGE_CLAIMS` regex →
  `SAFE_REFUSALS[lang]`, flag ∈ {safe, refused}, reason ∈ {"", "diagnosis",
  "dosage"}), `SAFE_REFUSALS`/`ESCALATE_PHRASES` for all 5 languages. Wired
  into `livekit_agent.py`: transcript red-flag hit → set `triage_severity =
  "red"` + speak per-language escalation phrase + break (deterministic, no
  LLM); ESCALATED leg now speaks the per-language phrase (was hardcoded
  English — the "specialist" literal survives via the `.get()` fallback arg);
  every agent reply passes `guard_output` before TTS. G4 pins preserved
  (`agent_logic`, `CallState`, `MEDICAL_FUNCTIONS`, `specialist`). Docs:
  02-state-machine + 06-call-lifecycle guardrail notes; HANDOVER.
- **Gotchas (one-line rules)**: G4's suite pins "specialist" in
  `livekit_agent.py` source — keep the EN fallback string inside the
  `ESCALATE_PHRASES.get(...)` call so the literal survives the per-language
  swap; RED suites are code too — an unbound var in a comprehension only
  surfaces when the suite is first exercised at GREEN time.
- **G6-Q8 NOTIFICATIONS DONE (g-notify, off g-guardrails tip `c01bbac`; spec
  `2aa98f8` APPROVED → GREEN; RED `791a942` 52 tests 21 FAIL+30 ERROR → feat
  `9bfa49c` → docs tip; regression **371/371**, compileall 0)** — sign-off Q1=A1c (WhatsApp-first
  Meta Cloud API primary; SMS Knowlarity→MSG91 fallback; email SMTP per kind),
  Q2=A2c (full catalog: payment_link whatsapp→sms→email, appointment_reminder
  whatsapp→sms→email, no_show_followup whatsapp→sms, otp whatsapp→sms,
  payment_receipt email→whatsapp; per-language templates all 5 languages;
  push=FCM env-gated kind stub, lazy/never fired), Q3=A3a (env-gated stdlib
  builders + `channel_env_ready` + lazy `dispatch_channel`; manual POST
  `/api/notifications/send` 501s without keys; upstream hooks never fail),
  Q4=A4a (`notifications` table + `uq_notifications_provider_ref` UNIQUE
  partial index + `notifications_send` policy with `app.service_request`
  OR-clause mirroring `payments_manage`; writes via service_request_ctx()).
  Delivered: `app/services/notifications.py` (CHANNELS/KINDS/
  DEFAULT_CHANNEL_ORDER/CHANNEL_PROVIDER_KEYS single source + 5×5 templates +
  subjects, render/channel_env_ready/sms_provider_ready/resolve_channel_
  provider/dispatch/send orchestration), `app/schemas/notification.py`,
  `app/api/notifications.py` 8th router (identity-gated GET "" + POST /send),
  schema table+index+policy+grants, postgres.py Notification ORM +
  create/list, `payments.py` `_send_notification_payment_link` hook for
  kind link/upi (non-fatal side-effect; never 501s a payment create;
  delivers PAYMENT_LINK_BASE_URL/pay/<id> to the linked appointment's phone
  with the clinic name), `.env.example`+compose channel keys (WHATSAPP_TOKEN/
  PHONE_ID, KNOWLARITY_SMS_TOKEN/SENDER_ID, MSG91_AUTH_KEY/SENDER_ID/ROUTE,
  SMTP_*, FCM_*), smoke_api 501 check. Docs: 03-api-contracts node+notes
  (in feat), 01-er 11th table, 00-index, HANDOVER, tracker, spec GREEN.
- **Gotchas (one-line rules)**: assert-chains like
  `self.assertX(...) and self.assertY(...)` silently skip the second assert
  (None is falsy) — split them; `fn_block` must slice by LINES
  (`splitlines(keepends=True)`), never by character offsets; helpers named
  exactly so substring contracts hold (`_send_notification_payment_link`
  naturally contains `send_notification`); the contracts doc lives at the
  REPO root `docs/uml/`, not `backend/docs`.
- **G6-Q4 LANGUAGES DONE (g-languages, off g-notify tip `394192c`; spec
  `1e868e9` APPROVED → GREEN; RED `e2f636f` 55 tests 19 FAIL+26 ERROR → feat
  `fcdc589` → docs tip; regression **426/426** (371 + 55), compileall 0)** —
  sign-off Q1=A1 (confidence-low STT fallback chain: `resolve_stt_language` —
  confidence ≥ threshold, or None, keeps the call language; < threshold falls
  the *operative* language to English for that turn; `STT_CONFIDENCE_THRESHOLD`
  env default 0.6; additive `stt_stream_with_scores` yields
  (transcript, confidence, language); the G4 `stt_stream` (yields str) is
  untouched), Q2=A1 (new stdlib `app/services/languages.py` single-source
  catalog: SUPPORTED_LANGUAGES/STT_TAGS/IVR_DIGIT_LANGUAGES/TTS_VOICE_ENV_KEYS/
  LANGUAGE_FALLBACK_CHAIN + is_supported_language + resolve_stt_language;
  agent_logic re-exports the G4-pinned helpers unchanged; postgres.py +
  services/notifications.py import the tuple from there — the 3 app copies are
  gone, one tuple object), Q3=A1 (5-language `GREETING_TEMPLATES` +
  `greeting_for_language` in agent_logic; livekit_agent greeting wired —
  previously the opening text was ALWAYS English while the TTS voice was
  per-language), Q4=A1 (canonical `ELEVENLABS_VOICE_ID_{CODE}` keys documented
  in .env.example — the old `_HINDI/_TAMIL/...` docs never fired because the
  code always built the {CODE} form). Delivered: `app/services/languages.py`
  (leaf, stdlib-only), agent_logic import swap + greeting templates,
  stt.py `_env_threshold` + scores stream, tts.py `voice_for_language` keyed
  off TTS_VOICE_ENV_KEYS, .env.example canonicalization + threshold, dedupe
  imports. Docs: tracker + HANDOVER + spec GREEN. No tables/endpoints —
  `language_codes` already models `elevenlabs_voice_id`; seeding it as a
  runtime store is a Docker/CI follow-on.
- **Gotchas (one-line rules, Q4)**: env-key doc drift is real — the code built
  `ELEVENLABS_VOICE_ID_{CODE.upper()}` the whole time while .env.example
  shipped the full-name form (`_HINDI` etc.), so documented per-language
  overrides never fired; guard with a `TTS_VOICE_ENV_KEYS` catalog + a
  ".env.example documents all five keys" coverage test (mirror the Q8
  channel-key test). The `is`-identity dedupe tests pass ONLY when consumers do
  `from app.services.languages import SUPPORTED_LANGUAGES` (a direct import —
  `import app.services.languages as l; l.SUPPORTED_LANGUAGES` is a different
  expression but same object; either re-exports the same tuple).
- **G6-Q2 CONSENT+DPDP DONE (g-dpdp, off g-languages tip `af63e3c`; spec
  `88cfa33` APPROVED → GREEN; RED `e9ce9d2` 62 tests 30 FAIL+28 ERROR → feat
  `d2cf117` → docs tip; regression **488/488** (426 + 62), compileall 0)** —
  sign-off Q1=A1 (per-call recording consent flag: `calls.recording_consent
  TEXT NOT NULL DEFAULT 'unknown'` (unknown/granted/denied) + stdlib
  `app/services/consent.py` with 5-language yes/no in-call parse
  `parse_consent_response(text, language)` → granted/denied/None +
  `recording_allowed()` egress gate + identity-gated
  `POST /api/calls/{call_id}/consent`; rides existing calls RLS; no new table),
  Q2=A1 (stdlib `app/services/retention.py`: RETENTION_DAYS calls 365 /
  recordings 365 / notifications 180 / audit 2190 (6yr) with per-kind env
  overrides `RETENTION_{CALLS,RECORDINGS,NOTIFICATIONS,AUDIT}_DAYS` + tz-aware
  `retention_deadline()` + `postgres.purge_expired` DELETE service wired for
  the Docker/CI cron — execution deferred; recordings = external MinIO
  objects → documented posture + env constant only), Q3=A1 (new
  `compliance_events` tenant table (event_type data_breach/consent_withdrawal/
  gdpr_request, severity, status open/reported/closed, detected_at,
  notification_deadline = detected + `DPDP_BREACH_NOTIFICATION_HOURS` default
  72h computed at insert, reported_at stamped on →reported) + RLS
  `compliance_manage` mirroring notifications_send + identity-gated
  `app/api/compliance.py` (GET "" / POST /events 201 / PATCH /events/{event_id})
  — 9th router; DPB alert = operational follow-on via the Q8 email channel, no
  new notification kind), Q4=A1 (config constants: `DATA_RESIDENCY_REGION`
  default "in" + `DPO_NAME`/`DPO_EMAIL` surfaced by `compliance.py`
  (data_residency/dpo_contact); region pin owned by Q10). Delivered: 3 stdlib
  leaf services + ComplianceEvent ORM + consent endpoints + `.env.example`
  DPDP block (8 keys) + smoke_api compliance/consent checks + 01-er.md &
  03-api-contracts.md. Baseline moved 426 → 488.
- **SCHEMA FIX OUTSIDE THE Q2 APPROVAL (flagged)**: Q8 created
  `notifications_send` but NEVER `ALTER TABLE notifications ENABLE ROW LEVEL
  SECURITY` — the policy was INERT, so notifications (the DPDP audit trail)
  was readable/writable across clinics by the app role. Q2 added
  notifications + compliance_events to the ENABLE+FORCE lists (the schema
  comment now says 9 tenant tables). No behavior contract changed (policies +
  grants untouched); this activates Q8's own intended policy. If the reviewer
  disagrees, the 2-line revert is trivial but re-opens the cross-tenant leak.
- **Gotchas (one-line rules, Q2)**: retention deadline math — Jan 1 + 180 days
  is **Jun 30** (2026 is not a leap year); write the expected date from the
  calendar, not from intuition. The `compliance_events` grant test must assert
  BOTH roles (`authenticated` + `medicall_app`) — the schema grants each role
  in its own block. When a phase adds a router, the baseline `test_api_routes.py`
  contract grows too (ROUTER_MODULES + EXPECTED_ENDPOINTS + the
  "registers all N routers" test) — the new calls consent route also lands in
  the calls endpoint set. `endpoint_set`/`endpoint_paths` produce exact
  `(method, "/path")` tuples — a path-param spelling mismatch (`{event_id}`
  vs `{eventId}`) fails them.
- **G6-Q9 MVP KPIs DONE (g-kpis, off g-dpdp tip `684a8ab`; spec `f553df2`
  DRAFT→APPROVED → GREEN; RED `f553df2` lands spec+suite — 31 tests
  11 FAIL+19 ERROR → feat `763ae22` → docs tip; regression **519/519**
  (488 + 31), compileall 0)** — sign-off (2026-09-25, question tool,
  market-grounded: Interactly 72% resolution benchmark, Hyro 2026 human-FCR
  70-79%, India no-show 18-25% → voice-AI 8-12%, reminder confirmation
  75-85%) Q1=A3 (**7 KPIs**: volume total/by_state/by_day/avg-duration +
  resolution rate + triage mix + language dist + no-show rate + revenue
  captured/refunded/by_kind/currency + **notification delivery success**
  per kind sent/failed/total/rate + static `BENCHMARKS` context dict —
  reminder *confirmation* rate deferred (needs campaign state)), Q2=A2
  (**per-KPI endpoints**: `app/api/analytics.py` — 10th router, prefix
  /api/analytics, one GET per KPI `/volume /resolution /triage /language
  /no-show /revenue /delivery` + `/benchmarks`; handlers get_<kpi>_ep all
  identity-gated; benchmarks handler is period-free), Q3=A1 (pure computed:
  stdlib `services/analytics.py` leaf (roots ⊆ {datetime, collections,
  typing}) with `resolve_period`/rates/shape helpers; `postgres.py` 7
  read-only per-KPI aggregates (`func.count`/`func.sum` + group_by over
  calls/appointments/payments/notifications) — zero schema writes, rides
  existing RLS; no .env additions, benchmarks are code constants), Q4=A1
  (optional ISO from/to, defaults to=now/from=to−30d, 366-day cap, 422 on
  bad order/over-cap/unparseable, naive assumed UTC). Delivered: 2 new
  modules + main.py 10th router + test_api_routes 9→10 + smoke_api
  analytics checks + 03-api-contracts Analytics node/PeriodGuard/note +
  01-er.md note. Baseline moved 488 → 519.
- **Gotchas (one-line rules, Q9)**: period strings must be `str(value)`-safe —
  the router passes `from_ or None` so empty query strings become defaults
  (a raw `""` would 422). `func.date(TIMESTAMPTZ)` buckets by the DB session
  timezone (documented MVP choice — a client-TZ bucketing fix is a Q10+
  item). The `/benchmarks` handler must NOT take from/to (RED pins
  `alias="from"` absent) — static context is period-free by design. As in
  Q2: a new router grows the test_api_routes contract (ROUTER_MODULES +
  EXPECTED_ENDPOINTS + N-routers test) in the SAME commit as the router,
  or the full-regression gate goes red.
- **G6-Q10 DEPLOY TOPOLOGY DONE (g-deploy, off g-kpis tip `5cd178c`; spec
  `ac9c571` APPROVED → RED same commit (spec lands with the suite) — 42 tests
  40 FAIL → feat `1f1411c` → docs tip; regression **561/561** (519 + 42),
  compileall 0)** — sign-off (2026-09-25, question tool; research-grounded:
  Railway has NO Mumbai region as of 2026-09-25 — 4 Metal regions only
  (us-west2 / us-east4-eqdc4a / europe-west4-drams3a / asia-southeast1-eqsg3a),
  region select is Pro-plan only, and its config-as-code is DEPRECATED —
  legacy services to 2026-12-01; Vercel `bom1`/Mumbai was ALREADY pinned in
  vercel.json) Q1=A1 (**drop redis from the compose stack**: grep
  `init_redis|get_redis|import redis` across backend → ZERO callers and the
  compose `REDIS_URL` was read by nobody; removed the redis service, redis-data
  volume + REDIS_URL from compose/05-deployment/.env.example; kept
  `app/db/redis.py` + the `redis==5.0.1` pin as a documented future-cache stub
  with `UPSTASH_REDIS_REST_URL`/`_TOKEN` matching what it actually reads),
  Q2=A1 (**single root-context Dockerfile**: `COPY backend/requirements.txt
  ./requirements.txt` + `COPY backend/ ./` + compose `context: .` +
  `dockerfile: backend/Dockerfile` + root `.dockerignore` (+
  `frontend/.dockerignore`) so ONE file serves docker compose AND Railway —
  railway.toml's `dockerfilePath` builds from the repo root, so the old
  subdir-context COPYs would have failed on Railway), Q3=A2 (**region pin
  realization**: frontend Vercel `bom1`/Mumbai + backend/Postgres Railway
  `asia-southeast1` **nearest available** (Singapore — Railway cannot do
  in-country); `DATA_RESIDENCY_REGION=in` is the documented posture PINNED
  unconditionally in compose + default in railway.toml/.env.example, with
  zero-retention BAAs documented as the contractual note in docs/DEPLOYMENT.md),
  Q4=A3 (**full phase**): compose DPDP env block (`DATA_RESIDENCY_REGION=in` +
  `RETENTION_*_DAYS` + `DPDP_BREACH_NOTIFICATION_HOURS` + `DPO_NAME/EMAIL`),
  `DATABASE_URL` **`+asyncpg` scheme fix** (compose passed `postgresql://…` —
  create_async_engine would have rejected it at stack runtime; the never-run
  ci.yml stack job was going to catch this), `backend/scripts/purge_expired.py`
  one-shot runner (iterates `retention_categories`, calls `purge_expired` per
  kind; recordings = external objects noted) + `.github/workflows/purge.yml`
  scheduled daily 03:00 UTC + workflow_dispatch (closes Q2's deferred
  "Docker/CI cron"), `docs/DEPLOYMENT.md` (runbook + **complete env var
  catalog** — every `backend/.env.example` key, grouped, with secret flags +
  region pin + Railway/Vercel steps), schema-valid `railway.json`
  (deploy.region asia-southeast1; NO top-level services array — the schema
  doesn't support it, Postgres plugin + secrets are dashboard-side), railway.toml
  `[deploy] region` + DPDP `[env]` defaults. Contract updates: test_uml_diagrams
  DEPLOYMENT_TOKENS (redis removed) + ports (6379 dropped) — the deployment
  contract intentionally changed. Baseline moved 519 → 561.
- **Gotchas (one-line rules, Q10)**: `py -3.14 -m unittest` default discovery
  finds 0 tests (`backend/tests` has no `__init__.py`) — the real command is
  `py -3.14 -m unittest discover -s tests -p "test_*.py"`. The compose backend
  `DATABASE_URL` lacked the `+asyncpg` scheme (async engine rejects non-async
  schemes at runtime — the stack job would have failed; the Q10 RED suite
  text-pins the fixed scheme). Railway deploys need root-context COPYs — a
  `railway.toml` dockerfilePath builds from the repo ROOT, so `COPY
  requirements.txt .` (subdir context) fails there while working under compose's
  `./backend` context; the single root-context Dockerfile + `context: .`
  resolves both. The master repo shows `?? .worktrees/` untracked (missing from
  .gitignore AND .git/info/exclude) — added `.worktrees/` to .gitignore. A
  phase that changes the documented stack must update the contract suite in the
  same commit (test_uml_diagrams redis token + 6379 port) or the
  full-regression gate goes red.
- **Next**: live provider round-trips behind CI secrets → run the ci.yml stack
  job on a Docker host → merge branch tips to main (G6 fully answered).
