# HANDOVER — MediCall AI → next OpenCode session

Read this file first. It is the full state of the project. The spec tracker
`.opencode/spec-idea-refinement-gaps.md` holds the detailed records; this file
is the launchpad.

## 1. What this is
- **MediCall AI**: a NEW, separate healthcare company (voice-first Indian
  Medical Call Center). It is NOT Talkbyte.
- **Project home (work here ONLY)**:
  `C:\Users\vigilare\OneDrive - Vigilare BP PVT LTD\Documents\MediCall-AI\`
- **NEVER touch**: `C:\Users\vigilare\Talkbyte\` (original Talkbyte: 3 versions
  + docs + .git — verbatim intact). `Documents\Talkbyte_clone\` is the frozen
  archive of earlier work; do not edit it either.

## 2. Where development stands
- ✅ **G1+G2 DONE** — `backend/main.py` imports clean + "MediCall AI" branding;
  `backend/app/db/postgres.py` rewritten (parses, pgvector-correct).
  Proof: `backend/tests/test_g1_g2.py` 11/11 GREEN.
- ✅ **G3 DONE** — single medical state machine; `app/models/call.py` is the
  canonical owner (`CallState`, `TriageSeverity`, `STATE_TRANSITIONS`, 9 states,
  terminal COMPLETE/ESCALATED/DROPPED); `postgres.py` imports from it.
  Proof: `backend/tests/test_g3_state_machine.py` 9/9 GREEN.
- ✅ **G4 DONE** — voice pipeline: Exotel/Knowlarity/Twilio-India webhooks →
  `ProviderEvent` → LiveKit agent on the G3 state machine; 5-language STT/TTS
  (hi/en/ta/te/bn), escalation MVP, `/call-completed` endpoint.
  Proof: `backend/tests/test_g4_voice.py` 33/33 GREEN.
- ✅ **G5 DONE** — `requirements.txt` rewritten (verified payment pins:
  razorpay==2.0.1, phonepe-pg-sdk-python==2.3.0, cashfree-pg==6.0.1; dev:
  pytest 8.3.5, pytest-asyncio 0.25.3, ruff 0.11.9); in-house httpx Knowlarity
  SR client. Proof: `backend/tests/test_g5_reqs.py` 18/18 GREEN.
- ✅ **DASHBOARDS DONE** — clinic (7-tab) + admin (9-view) shells, Tailwind v4
  CSS-first teal tokens, 16 mock pages (`mock.ts`), nav.ts single source.
  Proof: `backend/tests/test_dashboards.py` 34/34 GREEN.
- ✅ **API ROUTES DONE** — `clinics`/`calls`/`appointments`/`prescriptions`/
  `payments` routers + `app/schemas/` package + postgres CRUD + new `payments`
  table; `main.py` registers all 6 routers. Payments = scaffold only (G6-Q5
  still open — records intent, never calls a gateway SDK). Branch
  `ga-api-routes` off `gd-dashboards` tip. Live wiring of the 16 pages moves to
  Docker/CI (D1). Proof: `backend/tests/test_api_routes.py` 36/36 GREEN.
- ✅ **UML DIAGRAMS DONE** — `docs/uml/` 00-index + 01-er (9 tables, 13 FK
  edges) + 02-state-machine (mermaid edges test-asserted EQUAL to
  `STATE_TRANSITIONS`, cannot drift) + 03-api-contracts (6 prefixes, 21
  endpoints, 409/422/404) + 04-data-flow + 05-deployment + 06-call-lifecycle.
  Docs-only phase (zero code changes). Branch `g-uml` off `ga-api-routes`
  tip. Proof: `backend/tests/test_uml_diagrams.py` 21/21 GREEN; regression
  162/162.
- ✅ **DOCKER/CI INTEGRATION DONE** — first phase with REAL frontend
  verification: `npm install` (lockfile committed) + `npm run lint` (0 errors)
  + `next build` **exit 0** (19 routes). Fixed 6 build/CI-breaking defects
  (lockfile, public/, `next lint`→eslint flat, healthcheck `requests`→httpx,
  `/call-completed` transcript wiring, react-19 peer conflicts) + the
  **route-group collision** caught by the first real build: `(admin)` group had
  no URL segment (resolved bare `/patients`… colliding with `(clinic)` and the
  `/` landing) → real `admin/` segment. Delivered: `src/lib/api.ts` typed
  client + react-query hooks with `NEXT_PUBLIC_USE_MOCK` fallback (proof pages
  live-calls + dashboard wire in; 14 stay on mock), `backend/scripts/
  smoke_api.py` stdlib HTTP smoke of the 03-api-contracts surface,
  `.github/workflows/ci.yml` 3 jobs (backend stdlib+ruff, frontend
  ci+lint+build, stack compose up + smoke + teardown). Branch `g-ci` off
  `g-uml` tip. Proof: `tests/test_docker_ci.py` 18/18 GREEN; regression
  **180/180**; eslint 0; next build exit 0.
- ✅ **AUTH (G6-Q1) DONE** — stdlib AuthN/Z core + local-schema repair: PBKDF2
  passwords (210k iters), hashed 6-digit OTP (TTL+cap), JWT-shaped HMAC-SHA256
  tokens (12h), role matrix incl. `doctor`; `users` table + `auth.uid()` GUC
  RLS (ENABLED, NOT FORCED — owner-bypass keeps the unauth API working;
  enforcement stages next phase), `clinic_users.user_id → users(id)`;
  `app/api/auth.py` router (register/login/otp/me/logout/providers + SSO 501
  gates) + guards library (`get_current_user`/`require_roles`/
  `require_clinic_role`), 7th router in `main.py`; frontend `/login` page
  (password + OTP tabs + offline demo), `AuthProvider`/`RequireAuth` guard in
  the clinic+admin layouts (skipped unless `NEXT_PUBLIC_USE_MOCK === "false"`),
  api.ts Bearer auth surface; `smoke_api.py` register→login→me round-trip; UML
  docs 01-er (10 tables/14 edges) + 03-api-contracts (`/api/auth`). Branch
  `g-auth` off `g-ci` tip `81587ef`. Proof: `tests/test_auth.py` 42/42 GREEN;
  regression **222/222**; compileall 0; eslint 0; next build exit 0 (20 routes).
- ✅ **AUTH ENFORCEMENT (Q1-staged) DONE** — the 5 domain routers are now
  identity-gated end-to-end: every endpoint takes `Depends(get_current_user)`
  (401 without a Bearer JWT), `POST /api/clinics` additionally
  `require_roles("owner")` (403 for staff) and auto-appoints the creator as
  clinic owner. RLS flips together: `medicall_app` non-owner LOGIN role +
  `FORCE ROW LEVEL SECURITY` on all 7 tenant tables + demo tenant seed (owner
  `+919876543210`/`DemoPass!2026`). Per-transaction RLS GUCs via
  ContextVars + engine `begin` listener (`SET LOCAL app.current_user_id` /
  `app.service_request`); service bypass armed on auth CRUD + verified
  webhooks (`X-Service-Token` == `WEBHOOK_SERVICE_TOKEN`, 401 otherwise;
  new `calls_update` policy for state/transcript UPDATEs). Voice
  `call_completed` persists transcripts under the bypass. `smoke_api.py` is
  auth-first (demo-owner login → Bearer everywhere) with 401/403 negative
  checks; compose + `.env.example` connect as `medicall_app` with
  `WEBHOOK_SERVICE_TOKEN`. Branch `g-enforce` off `g-auth` tip `c6b59ff`
  (spec `0d918f8` → APPROVED `e6533dc` → RED `0b12af3` → feat `69b9eae`).
  Proof: `tests/test_auth_enforcement.py` 24/24 GREEN; regression
  **246/246**; compileall 0. RLS/GUC *runtime* truth = the ci.yml stack job
  on a Docker host (authored; still to run — no Docker on this PC).
- ✅ **PAYMENTS (G6-Q5) DONE** — flows + gateway wiring decided by sign-off
  (Q1=A1a consult+refill bill, Q2=A2a kind→gateway: razorpay=links,
  phonepe=UPI fallback, cashfree=subscriptions, Q3=A3a in-call waits in
  PAYMENT_SENT, Q4=A4a per-gateway HMAC + shared token + unified webhook,
  Q5=A5a stdlib layer now / SDK env-gated). New `app/services/payments.py`
  stdlib gateway layer: builders (link/UPI/order/subscription shapes) +
  Razorpay/PhonePe/Cashfree webhook signature verifiers (HMAC vectors) +
  status/ref extraction + transition rules + env gate + lazy SDK dispatch.
  `POST /api/payments/webhook` — identity-free BY DESIGN (verified by
  `X-Service-Token` + per-gateway signature), writes under `service_request_ctx`
  (new `payments_manage` service clause; enforcement suite got an explicit
  `IDENTITY_FREE_ENDPOINTS` carve-out), idempotent by `gateway_ref` (new UNIQUE
  partial index), `captured` advances the linked call `PAYMENT_SENT → COMPLETE`.
  `payments` += `kind`/`expires_at`; create is env-gated 501 (manual keyless);
  compose + `.env.example` carry the G5 canonical gateway keys. Gotcha fixed in
  RED: env-key names follow G5's `.env.example` (`PHONEPE_SALT_KEY/INDEX`,
  `CASHFREE_WEBHOOK_SECRET`, `RAZORPAY_WEBHOOK_SECRET`), not my first-pass
  guesses. Branch `g-payments` off `g-enforce` tip `0e1cb87` (spec DRAFT →
  APPROVED → RED `0b12af3`-style 36 FAIL → feat `d61a4ea`). Proof:
  `tests/test_payments_q5.py` 36/36 GREEN; regression **282/282**; compileall 0.
  Live SDK round-trips + webhook happy-path runtime = ci.yml stack job on a
  Docker host (authored; still to run).
- ✅ **CLINICAL GUARDRAILS (G6-Q3) DONE** — spec-first + tests-first on the new
  `app/services/guardrails.py`: layered escalation triggers (Q1=A1a — severity
  red/critical OR red-flag keyword OR explicit intent; reason records the
  source), deterministic output guard (Q2=A2a — FORBIDDEN_CLAIMS scan → fixed
  per-language refusal phrase before TTS; a diagnosis/dosage claim is never
  spoken), 12-category red-flag catalog (Q3=A3a — cardiac / respiratory /
  severe_bleeding / stroke / seizure / poisoning / anaphylaxis / burns /
  head_injury / pregnancy_emergency / self_harm / choking), red-team vector
  table = the acceptance suite (Q4=A4a — 21 vectors: 13 escalate, 4 refuse, 4
  benign no-false-positive). `livekit_agent` wired: a red-flag keyword beats
  LLM severity (deterministic temperature≈0 escalate + per-language handoff
  phrase — fixes the hardcoded-English D2 leg); every agent reply is
  output-guarded before TTS. Zero env keys, no tables, no endpoints. Branch
  `g-guardrails` off `g-payments` tip `4812795` (spec DRAFT → APPROVED
  `31b28d1` → RED 37-test 36-fail → feat `0df6962`). Proof:
  `tests/test_guardrails_q3.py` 37/37 GREEN; regression **319/319**;
  compileall 0.
- ✅ **NOTIFICATIONS (G6-Q8) DONE** — WhatsApp-first messaging layer,
  sign-off Q1=A1c (Meta Cloud API primary; SMS Knowlarity→MSG91 fallback;
  email SMTP per kind), Q2=A2c (full catalog: payment_link /
  appointment_reminder / no_show_followup / otp / payment_receipt with
  per-kind channel orders and per-language templates for all 5 languages;
  push=FCM env-gated kind stub), Q3=A3a (env-gated stdlib request builders +
  `channel_env_ready` + lazy `dispatch_channel` — a provider client imports
  only on a keyed host; `send_notification` walks DEFAULT_CHANNEL_ORDER with
  the first ready channel; manual POST `/api/notifications/send` 501s without
  keys; **upstream hooks never fail or 501**), Q4=A4a (new `notifications`
  table + `uq_notifications_provider_ref` partial unique + `notifications_send`
  policy with the `app.service_request` OR-clause mirroring `payments_manage`).
  New `app/services/notifications.py` (catalog single source, 5×5 templates +
  email subjects, channel env gates + provider resolution, request builders,
  lazy dispatch, send orchestration with injectable dispatch for tests) +
  `app/api/notifications.py` 8th router (identity-gated GET "" list + POST
  /send), schema table + policy + grants, `postgres.py` `Notification` ORM +
  `create_notification`/`list_notifications`, payments `create_payment` hook
  for kind link/upi (`_send_notification_payment_link` — delivers the
  PAYMENT_LINK_BASE_URL/pay/<id> link to the linked appointment's phone,
  recorded non-fatal, never breaks/501s a payment), `.env.example` + compose
  channel keys, `smoke_api.py` 501 gate check. Branch `g-notify` off
  `g-guardrails` tip `c01bbac` (spec `2aa98f8` APPROVED → RED `791a942` →
  feat `9bfa49c` → docs tip).
  Proof: `tests/test_notifications_q8.py` 52/52 GREEN; regression
  **371/371**; compileall 0.
- ✅ **LANGUAGES (G6-Q4) DONE** — language layer hardening, sign-off Q1=A1
  (confidence-low STT fallback chain: `resolve_stt_language` — confidence ≥
  threshold or None keeps the call language, < threshold falls the operative
  language to English for that turn; `STT_CONFIDENCE_THRESHOLD` env default
  0.6; additive `stt_stream_with_scores` yields transcript/confidence/
  operative-language — the G4 `stt_stream` is untouched), Q2=A1 (new stdlib
  `app/services/languages.py` single-source catalog: SUPPORTED_LANGUAGES /
  STT_TAGS / IVR_DIGIT_LANGUAGES / TTS_VOICE_ENV_KEYS / LANGUAGE_FALLBACK_CHAIN
  + `is_supported_language` + `resolve_stt_language`; agent_logic re-exports
  the G4-pinned helpers unchanged; postgres.py + services/notifications.py
  import the tuple from there — the 3 app copies are gone), Q3=A1 (5-language
  `GREETING_TEMPLATES` + `greeting_for_language` in agent_logic; livekit_agent
  greeting now localized — before, the opening TEXT was always English while
  the TTS voice was per-language), Q4=A1 (canonical `ELEVENLABS_VOICE_ID_{CODE}`
  keys documented in .env.example — the legacy `_HINDI/_TAMIL/...` names never
  fired because the code always built the {CODE} form). Branch `g-languages`
  off `g-notify` tip `394192c` (spec `1e868e9` APPROVED → RED `e2f636f` →
  feat `fcdc589` → docs tip). Proof: `tests/test_languages_q4.py` 55/55 GREEN;
  regression **426/426**; compileall 0.
- ▶️ **NEXT: live provider round-trips behind CI secrets** (Deepgram/
  ElevenLabs/OpenAI + LiveKit rooms + real gateway SDK dispatch + signed
  webhook end-to-end) and **run the ci.yml stack job on a Docker host** (RLS/
  GUC runtime proof + smoke_api.py webhook flow); then merge branch tips to main.
- ⏳ **After**: Interactly-parity build (benchmarks + integration catalog are
  specced in `spec-multifit-healthcare.md`, NOT built).

## 3. Decisions already locked (do not relitigate)
- G1–G7 = the complete fix list (approved 2026-09-22).
- Auth MVP: full incl. ABHA login (OTP + password + Google/Microsoft SSO + ABHA).
- Telephony: ALL THREE providers wired with fallback chain (Exotel +
  Knowlarity + Twilio India), no single primary.
- EHR/ABDM Phase 1: transcript-only, no EHR writes.
- Stack: LiveKit Agents (primary) / TEN (multimodal fallback) / Bolna (OSS
  fallback); Deepgram STT + ElevenLabs TTS, 5 languages (hi/en/ta/te/bn);
  Razorpay/PhonePe/Cashfree; PostgreSQL + pgvector local (no Supabase).

## 4. Still open (answer before the session that needs them)
G6-Q2 consent/retention (DPDP), Q9 MVP KPIs, Q10 deploy topology.

## 5. Verify first (before any edit)
```
powershell -ExecutionPolicy Bypass -File start-worktree.ps1
```
Must print STARTUP GREEN (runs both suites + py_compile). Full runs:
`python3 tests/test_g1_g2.py` and `python3 tests/test_g3_state_machine.py`
from `backend\`. This PC has NO third-party packages (no fastapi/sqlalchemy/
pytest/ruff) — tests are stdlib-only by design; live DB/runtime checks belong
in Docker/CI. **Frontend IS real-verifiable here**: `npm ci && npm run lint &&
npm run build` in `frontend\` (node v24 + npm 11; first done in g-ci — exit 0).
Git common dir = `MediCall-AI\.git` (the main tree IS the repo's master working
tree — keep it clean; each phase gets its own `.worktrees\<name>` branch via
`start-worktree.ps1 -Branch <name>`).

## 6. Spec index (`.opencode/`)
- `spec-idea-refinement-gaps.md` — master tracker: gaps, sign-off, G-records ← START HERE
- `spec-payments.md` — G6-Q5 payment flows + gateway wiring (Q1–Q5 APPROVED; DONE)
- `spec-notifications-q8.md` — G6-Q8 WhatsApp-first notifications (Q1–Q4 APPROVED; DONE)
- `spec-languages-q4.md` — G6-Q4 language layer: STT confidence fallback, single-source catalog, greetings, TTS voice keys (Q1–Q4 APPROVED; DONE)
- `spec-guardrails-q3.md` — G6-Q3 clinical guardrails (Q1–Q4 APPROVED; DONE)
- `spec-docker-ci.md` — Docker/CI phase spec (Q1 local+CI, Q2 client+2 pages, Q3 3-job workflow; DONE)
- `spec-auth.md` — AuthN/Z (G6-Q1) + local-schema repair (Q1–Q4 APPROVED; DONE)
- `spec-uml-diagrams.md` — UML phase spec (Mermaid, docs/uml/, 5+1 diagrams)
- `spec-micc-india.md` — India-market requirements (approved)
- `spec-multifit-healthcare.md` — platform vision + Interactly research
- `spec-micc-database-dashboards-routes-uml.md` — DB/dashboards/routes/UML plan
- `spec-design-system.md` — design tokens/components (pending build)

## 7. Session rules (non-negotiable)
1. Spec-first: clarify → research on-disk (don't assume) → update spec →
   STOP for sign-off → implement only on approval.
2. One task per session (next = auth enforcement: guards on the 5 domain
   routers + FORCE RLS + `medicall_app` role).
3. Tests first (RED), implement to GREEN, refactor, lint-equivalent
   (`py_compile`/`compileall`; ruff runs in CI; eslint + next build are real
   locally since g-ci).
4. PowerShell only: no `&&`, no `tail/head/grep`, quote spaced paths.
5. Never write code into `C:\Users\vigilare\Talkbyte\` or `Talkbyte_clone\`.
