# SPEC: MediCall AI — AuthN/Z (G6-Q1) + Local-Schema Repair (g-auth)

- Branch: `g-auth` (off `g-ci` tip `81587ef`) · Worktree: `.worktrees\g-auth`
- Status: **APPROVED 2026-09-25 — decisions recorded below. Spec commit follows
  this file; implementation begins after the RED suite is committed.**
- Locked source decision (tracker sign-off 2026-09-22): **G6-Q1 = Full auth incl.
  ABHA login (OTP + password + Google/Microsoft SSO + ABHA)**; role matrix
  `owner/staff/triage_agent/doctor/readonly`.

## Recorded decisions (question-tool sign-off 2026-09-25)
- **Q1 Router enforcement**: **Guards library only.** `get_current_user` /
  `require_roles` / `require_clinic_role` ship as an exported library; the 5
  existing domain routers + their 36 API tests stay untouched this phase.
- **Q2 RLS treatment**: **Local `auth.uid()` GUC function.** Create an `auth`
  schema with `auth.uid()` reading `current_setting('app.current_user_id')`;
  keep every policy + the `authenticated` role/grants so the schema loads on
  local postgres. **Enforcement intentionally staged**: table owner bypasses
  RLS while `FORCE ROW LEVEL SECURITY` stays off, so today's unauthenticated
  API surface keeps working. The next phase (enforcement) flips
  `FORCE ROW LEVEL SECURITY` + a non-owner `medicall_app` connection role + the
  per-request GUC as ONE atomic change.
- **Q3 Frontend scope**: **Include `/login` page + client guard.** Password +
  OTP tabs, auth context, route guard on `(clinic)` + `admin` layouts; guard
  skipped when `NEXT_PUBLIC_USE_MOCK !== "false"` (offline/dev), hard-guarded
  in production mode. Real `npm lint` + `next build` verification this phase.
- **Q4 Token format**: **Stdlib HMAC-SHA256 JWT-shaped tokens** (header.payload
  .signature, base64url, claims sub/role/iat/exp) — unit-tested on this PC;
  python-jose stays pinned for later SSO/OAuth2 resource-server flows.

## Goal
Ship the auth layer the locked decision demands, in the project's established
shape (stdlib-testable core, Docker-runs-the-rest), **and** repair the schema
defects that stop `postgres_schema.sql` from loading on local PostgreSQL — the
compose initdb runs this file, so the stack cannot come up today.

## Environment findings (verified this session, evidence-backed)
- `backend/requirements.txt` **already pins the auth stack**:
  `python-jose[cryptography]==3.3.0`, `passlib[bcrypt]==1.7.4`,
  `python-multipart==0.0.9` → Docker-side JWT/bcrypt was always planned. This PC
  is stdlib-only (no pip) → the auth CORE must be stdlib (hashlib/secrets/hmac),
  exactly like `app/services/telephony.py`.
- **`postgres_schema.sql` cannot load on local postgres** (compose initdb):
  line 33 `clinic_users.user_id UUID REFERENCES auth.users(id)` (no `auth.users`
  locally); 7 RLS policies call `auth.uid()` (no such function); `GRANT … TO
  authenticated` targets a role that doesn't exist; there is **no `users` table
  at all**; `clinic_users` role comment misses `doctor`.
- `app/db/postgres.py`: 9 SQLAlchemy models, no `User`; `ClinicUser.user_id` is
  a bare UUID with NO FK (line 151-153). `init_db()` = `Base.metadata.create_all`
  (picks up a new model automatically).
- `backend/tests/test_uml_diagrams.py` asserts **exactly 9 tables / 13 FK
  edges**; `docs/uml/01-er.md` mirrors them → `users` makes 10 tables / 14 edges.
- `backend/.env.example` + `docker-compose.yml` have NO auth envs.
- Frontend real-verifiable since g-ci (`npm ci && lint && build` exit 0);
  `src/lib/api.ts` client + `NEXT_PUBLIC_USE_MOCK` pattern exists; no auth UI.

## Deliverables

### A. Schema + SQLAlchemy (make the stack load, RLS intact)
- `postgres_schema.sql`:
  1. `CREATE SCHEMA IF NOT EXISTS auth;` + `auth.uid()` plpgsql fn returning
     `current_setting('app.current_user_id', true)::uuid` (NULL when unset).
  2. `CREATE ROLE authenticated NOLOGIN;` before the grants (schema loads).
  3. Add `users` table — `id UUID PK`, `email TEXT UNIQUE`, `phone TEXT UNIQUE`
     (both nullable, ≥1 at register; India = phone primary), `name TEXT NOT
     NULL`, `password_hash TEXT` (NULL for SSO-only), `otp_code_hash TEXT`,
     `otp_expires_at TIMESTAMPTZ`, `otp_attempts INT DEFAULT 0`,
     `role TEXT DEFAULT 'staff'`, `is_active BOOL DEFAULT TRUE`,
     `created_at/updated_at TIMESTAMPTZ` + `update_updated_at` trigger.
  4. Fix `clinic_users.user_id` → `REFERENCES users(id) ON DELETE CASCADE`.
  5. Role comments on `users` + `clinic_users` → `owner, staff, triage_agent,
     doctor, readonly` (adds `doctor`).
  6. Keep all RLS policies (now loadable). **No FORCE RLS this phase**
     (owner bypass; enforcement staged per Q2) — noted in a schema comment.
- `app/db/postgres.py`: add `User` model (mirrors the table);
  `ClinicUser.user_id` → `ForeignKey("users.id", ondelete="CASCADE")`;
  `init_db()` unchanged.

### B. `app/services/auth.py` — stdlib core (unit-testable on this PC)
- Passwords: PBKDF2-HMAC-SHA256, per-user 16-byte salt, 210k iterations —
  `hash_password(pw)` / `verify_password(pw, stored)` via
  `hmac.compare_digest`; stored form `pbkdf2_sha256$<iter>$<salt_hex>$<hex>`.
- OTP: `generate_otp()` (6-digit, `secrets`), `hash_otp(code, phone)` (HMAC —
  never stored plaintext), `verify_otp(code, stored, expires_at, attempts)`
  (TTL + attempt cap 5). `OTP_TTL_SECONDS = 600`.
- Tokens: `create_token(user_id, role, secret, ttl=43200)` /
  `decode_token(token, secret, now)` — JWT-shaped HMAC-SHA256 base64url,
  claims sub/role/iat/exp; raises Expired/Invalid.
- Roles: `ROLES = ("owner","staff","triage_agent","doctor","readonly")`,
  `can(role, required)` with owner>doctor>triage_agent>staff>readonly.
- `normalize_phone(phone)` → `+91xxxxxxxxxx` or raise (10-digit India).

### C. `app/api/auth.py` — FastAPI router (Docker/CI runtime, py_compile locally)
- `POST /api/auth/register` `{name, phone?, email?, password}` → 201; 409 dup
  phone/email; password ≥ 8.
- `POST /api/auth/login` `{username, password}` (username = phone or email) →
  `{access_token, token_type, user}`; 401 bad creds.
- `POST /api/auth/otp/request` `{phone}` → 200 `{status:"otp_sent",
  expires_in}`; code hashed+stored, dev-logged (SMS provider gated); 404
  unknown phone; 429 capped.
- `POST /api/auth/otp/verify` `{phone, code}` → `{access_token, user}`.
- `GET /api/auth/me` (Bearer) → user + memberships `[{clinic_id, role}]`.
- `POST /api/auth/logout` → 200 ack (stateless).
- `GET /api/auth/providers` → `{password, otp, google, microsoft, abha}` with
  `configured` flags from env-key presence.
- `POST /api/auth/oauth/{provider}` (google|microsoft|abha) → 501 unless keys
  present; guarded lazy import (pattern: voice `call_completed`, payments
  G6-Q5). No live provider calls this PC (no keys).
- Security deps exported: `get_current_user` (Bearer), `require_roles(*roles)`
  (403), `require_clinic_role(clinic_id, *roles)` (403).
- Wire router into `backend/main.py` (`/api/auth`).

### D. Env + compose
- `.env.example`: `AUTH_JWT_SECRET=`, `AUTH_TOKEN_TTL_SECONDS=43200`,
  `OTP_TTL_SECONDS=600`, `GOOGLE_OAUTH_CLIENT_ID/SECRET=`,
  `MICROSOFT_OAUTH_TENANT_ID/CLIENT_ID/SECRET=`, `ABHA_OAUTH_CLIENT_ID/SECRET=`.
- `docker-compose.yml`: backend env gains
  `AUTH_JWT_SECRET=${AUTH_JWT_SECRET:-dev-secret-change-me}` (keyless compose
  up stays clean).

### E. Frontend — `/login` + guard (Q3 approved)
- `src/lib/api.ts`: extend with auth surface — `apiPost`, `register`,
  `loginPassword`, `loginOtpRequest`, `loginOtpVerify`, `fetchMe`, token
  helpers (`getToken/setToken/clearToken`), and attach `Authorization: Bearer`
  to existing fetchers when a token exists.
- `src/lib/auth.tsx`: `AuthProvider` (client) — token in localStorage,
  exposes `{ user, token, login, logout, loading }`; mounts inside
  `src/lib/providers.tsx` tree.
- `src/app/login/page.tsx`: client page, password + OTP tabs, calls the api
  client; in `NEXT_PUBLIC_USE_MOCK=true` mode offers a "Continue with demo
  data" action (sets a demo token) so offline dev still reaches dashboards.
- Guard: `(clinic)/layout.tsx` + `admin/layout.tsx` wrap children in
  `<RequireAuth mode={USE_MOCK}>` — redirects to `/login` when
  `NEXT_PUBLIC_USE_MOCK === "false"` and no token; skipped in true/auto.
- `.env.local.example`: unchanged semantics (`NEXT_PUBLIC_USE_MOCK` already
  documented); add `NEXT_PUBLIC_AUTH_ENABLED=auto` note if needed (default
  follows USE_MOCK).

### F. Docs corollary (keeps UML suite green)
- `docs/uml/01-er.md`: +`users` table, +edge `clinic_users.user_id → users`
  (10 tables / 14 edges); `docs/uml/03-api-contracts.md`: +`/api/auth`
  endpoints. `test_uml_diagrams.py`: ER_TABLES 9→10, ER_EDGES +1, users spot
  columns, docstring count updated.

### G. RED acceptance suite + smoke extension
- `backend/tests/test_auth.py` — stdlib, ≈24 tests (§Verification).
- `backend/scripts/smoke_api.py`: auth round-trip — register unique phone →
  login → Bearer `me`; otp/request 200; register-dup 409 — proves the REAL
  Docker-side auth path in the ci.yml stack job. ci.yml unchanged.

## Verification (this PC + CI as before)
- RED before implementation: `test_auth.py` fails (missing artifacts); UML
  suite fails on ER counts (schema drift); regression 180/180 intact.
- GREEN: `test_auth.py` ≈24/24; full regression **180 + 24 ≈ 204**; `compileall`
  0; `npm run lint` + `npm run build` exit 0 (real, incl. login page + guard);
  ci.yml stack job runs smoke incl. auth on a Docker host later.

## Status (2026-09-25) — IMPLEMENTED, GREEN
- Commits: spec `14dbe1a` → RED `108a700` (42 tests: 20 fail + 21 err) →
  feat `74accbe` → docs `…` (this record); worktree `g-auth` off `g-ci`
  tip `81587ef`.
- The suite ended at **42 tests** (not ≈24) — service crypto/roles/phone +
  schema repair + router/env/compose + frontend + smoke/ER assertions.
- GREEN: `test_auth.py` 42/42; full regression **222/222** (180 prior + 42,
  `BAD_SUITES` empty); `compileall` exit 0; eslint 0 errors (1 benign
  warning); **`next build` exit 0** (20 routes incl. `/login`). The ci.yml
  stack job (smoke incl. the auth round-trip) still runs on a Docker host.
- Test refinements during GREEN (documented in the suite): `verify_otp`'s
  valid-case passes the keying `phone` (stored OTP hashes are HMAC keyed by
  phone — the 4-arg call cannot recompute them); the doctor-role block check
  bounds by the NEXT `CREATE TABLE` (an inline `;` inside a SQL comment
  truncated the old split); api_routes router set synced 6→7 (auth); UML ER
  counts 9→10 tables / 13→14 edges + users spot columns.

## Non-Goals (hold the line)
- NO real SMS / SSO provider calls (no keys presented — same discipline as
  payments/telephony/STT-TTS; endpoints gated in-code).
- NO password-reset email flow (OTP covers recovery this phase).
- NO refresh tokens / revocation list (stateless JWT, 12h TTL, Phase 1).
- NO auth enforcement on the 5 domain routers or the 16 dashboard pages beyond
  the `/login` guard (Q1: guards as library; enforcement next phase).
- NO ABHA/FHIR data exchange (G6-Q7 transcript-only Phase 1 holds).
- NO FORCE RLS / non-owner connection role (staged with enforcement, Q2).

## Risks
| Risk | Mitigation |
|---|---|
| RLS defined-but-inert looks like a gap | Deliberate staging (Q2): policies load, owner-bypass keeps today's unauth API working; FORCE + `medicall_app` role flip with enforcement next phase (noted in schema comment) |
| `/login` guard breaks offline dev | Guard skipped when `NEXT_PUBLIC_USE_MOCK !== "false"`; demo-token path for true/auto |
| passlib/python-jose pinned but unused | Intentional — SSO/OAuth2 needs them; test_g5_reqs pins stay asserted |
| JWT dev-secret default in compose | `dev-secret-change-me` + `.env.example` production guidance; tokens only issued consistently with the same secret |
| Schema change ripples into UML suite | §F updates assertions + diagrams in the same commit |
| ~204-test regression loop cost | stdlib suites ~4s total; eslint+next build for the frontend deltas |