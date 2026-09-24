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
- ▶️ **NEXT: G6-Q5 payments** — real gateway wiring (Razorpay/PhonePe/
  Cashfree; intent-only today) once Q5 is answered. Then: live
  Deepgram/ElevenLabs/OpenAI + LiveKit room round-trips behind CI secrets; run
  the ci.yml stack job on a Docker host; then merge branch tips to main.
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
G6-Q2 consent/retention (DPDP), Q3 clinical guardrails, Q4 language fallback,
Q5 payment flows, Q8 notifications, Q9 MVP KPIs, Q10 deploy topology.

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
