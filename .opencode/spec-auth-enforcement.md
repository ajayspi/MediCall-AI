# spec-auth-enforcement.md — Auth Enforcement Phase (g-enforce)

| | |
|---|---|
| **Phase** | G6-Q1 follow-up: flip RLS + guards ON together (Q1/Q2 sign-off 2026-09-25 staged it) |
| **Branch** | `g-enforce` (worktree `.worktrees\g-enforce`, off g-auth tip `c6b59ff`) |
| **Rule** | Test-first (RED → GREEN). Stdlib-only local verification; RLS/GUC runtime proof = CI stack job (no Docker on this PC). |
| **Status** | DRAFT — awaiting sign-off. No implementation before approval. |

## 1. Why this phase exists

`spec-auth.md` Q1/Q2 shipped the guards **as a library only** (`get_current_user`,
`require_roles`, `require_clinic_role` in `app/api/auth.py`) — the 5 domain routers stay
unauthenticated, RLS is `ENABLE`d but **not** `FORCE`d, and the API connects as `medicall`
(the table **owner**, which bypasses RLS). The staged plan: flip guards + `FORCE ROW LEVEL
SECURITY` + a non-owner `medicall_app` connection role **together** in this phase.

## 2. Current state (research, confirmed on-disk 2026-09-25)

| Surface | Truth today |
|---|---|
| Guards | `get_current_user`, `require_roles(*roles)`, `require_clinic_role(clinic_id, *roles)` — defined **before** endpoints in `app/api/auth.py` (FastAPI import-time `Depends`). Not yet used by any domain router. |
| RLS schema | `auth.uid()` → `current_setting('app.current_user_id')`; `CREATE ROLE authenticated NOLOGIN`; `ENABLE ROW LEVEL SECURITY` on users/clinics/clinic_users/calls/appointments/prescriptions/payments; 9 policies (clinic_own_data, users_own_data, clinic_staff_read, calls_create, calls_read, appointments_manage, prescriptions_manage, payments_manage, language_codes_read); GRANTs to `authenticated`. |
| Connection role | `DATABASE_URL=postgresql://medicall:medicall@localhost:5432/medicall` (owner `medicall` = compose `POSTGRES_USER` + schema.sql runs as it). **Owner bypasses RLS** → that's why the unauth'd Phase-1 API works. |
| `init_db` | ORM `Base.metadata.create_all` only. RLS lives in `postgres_schema.sql` (compose init mount `/docker-entrypoint-initdb.d/init.sql`; fresh volume per CI run via `down -v`). |
| `smoke_api.py` | Domain calls **before** the auth block, all unauthenticated; auth round-trip comes last. |
| Users/clinics data | `User.role` / `ClinicUser.role` default `"staff"`. `register()` always creates `staff`. **No membership-creation endpoint exists** (only `list_clinic_memberships`). `create_clinic` does NOT create a membership row. |
| Voice webhooks | `/api/voice/call-completed` (UPDATE calls via `update_call_transcript`), `/livekit-agent-start`, `/webhook/exotel|knowlarity|twilio` — all unauthenticated, write `calls` rows. |
| `clinic_users` table | **No policy at all** → under a non-owner connection it's deny-all → would break `/api/auth/me` memberships + `require_clinic_role`. |
| `clinic_own_data` | `FOR ALL USING (id IN owner-memberships)` — a single-action policy's `USING` doubles as the INSERT `WITH CHECK` → **every clinic INSERT is blocked** under RLS (a new clinic's id can't be in your memberships yet). |

### Ripple findings that the staged plan did not cover (decided here)

1. **Login/OTP/register would 401/404 under RLS.** `find_user`/`create_user`/`set_user_otp`
   run with `auth.uid() = NULL` → `users_own_data FOR ALL USING (id = auth.uid())` blocks
   every row. The auth service path needs a **server-armed service bypass**.
2. **Voice webhooks would fail** their calls-table writes (no user → `calls_create`/`calls_read`
   reject). Webhooks today have **no auth at all**; enforcement is the moment to add a
   shared-secret check and a service bypass for the calls policies.
3. **No first clinic/owner can ever exist.** `register` → staff only; no membership endpoint;
   clinic INSERT blocked without membership. Need a **seeded demo tenant** (only legitimate
   bootstrap in a single-tenancy MVP).
4. **`POST /api/clinics` needs a role gate** (`require_roles` global owner) so a random
   registered user can't self-provision clinics — and `create_clinic` must also insert the
   creator's **owner membership** row, or RLS hides the new clinic from its own creator.

## 3. Decisions (each needs sign-off — see §7)

### Q1 — Router enforcement level
**Recommended (R1):** every endpoint on the 5 domain routers gains `user=Depends(get_current_user)`;
only `POST /api/clinics` additionally uses `require_roles("owner")`. RLS does the tenant
scoping (memberships), guards do identity, the one role gate covers the sole
self-provisioning path. Per-clinic role matrices (`require_clinic_role`) ship later with the
staff-management endpoints.
- **A1a (recommended):** identity everywhere + owner gate on clinic create only.
- **A1b:** full matrix — `require_clinic_role(clinic_id, "owner","staff")` on every
  /{id}-scoped write. More faithful to the role model; heavier now, no endpoints to consume
  it yet (no membership admin).
- **A1c:** `get_current_user` only, no role gates anywhere. Weakest — clinic create becomes
  staff-doable (against the role intent).

### Q2 — Webhook / service authorization
**Recommended (R2):** voice webhook endpoints verify a shared secret
(`X-Service-Token` header == `WEBHOOK_SERVICE_TOKEN` env, code default `dev-service-token`,
prod overrides) → **401 without it** → on success arm a `service_request` contextvar that the
GUC plumbing turns into `SET LOCAL app.service_request = 'on'`. Only the `users_own_data`,
`calls_create`, `calls_read` policies gain an `OR current_setting('app.service_request', true)='on'`
clause — tenant tables (clinics/clinic_users/appointments/prescriptions/payments) stay strict.
External callers cannot set Postgres GUCs through HTTP; arming is server-side authority gated
by the secret.
- **A2a (recommended):** shared service token + service_request GUC on users/calls policies.
- **A2b:** per-provider HMAC signatures (Exotel/Twilio style) — more real-world-correct, but
  provider-spec logic + signature libs = scope creep for this phase; note as follow-up.
- **A2c:** leave webhooks open (status quo). Unacceptable once RLS flips — they'd break *and*
  stay spoofable.

### Q3 — First-owner bootstrap
**Recommended (R3):** a **demo tenant seed** appended to `postgres_schema.sql` (fixed UUIDs +
`INSERT … ON CONFLICT DO NOTHING`): clinic "City Care Demo", owner user
(phone `+91 98765 43210`, email `demo@medicall.in`, global role `owner`, fixed PBKDF2 hash for
dev password, `is_active=true`) + `clinic_users(owner)` membership. Compose runs it on every
fresh volume; `smoke_api.py` logs in as the demo owner and drives all domain calls
authenticated. `.env.example` documents the creds.
- **A3a (recommended):** schema-seeded demo tenant (deterministic, works in CI stack job,
  zero extra surface).
- **A3b:** env-gated bootstrap endpoint (register designated owner when
  `BOOTSTRAP_ADMIN_PHONE` set). More flexible, but a new API surface + "first request wins"
  semantics = more attack/misconfig surface for no current need.
- **A3c:** `register` accepts a role field. **Rejected** — self-serve privilege escalation.

### Q4 — Auth-service DB path under RLS
**Recommended (R4):** the GUC plumbing listens on the engine `begin` event and issues
`SET LOCAL app.current_user_id = <uid>` + `SET LOCAL app.service_request = <flag>` from two
request-scoped `ContextVar`s **on every transaction** — including the ~30 CRUD functions that
open their own `SessionFactory()` (a dependency-only hook would miss them). `service_request`
is armed inside the auth user-CRUD helpers (`find_user`, `create_user`, `set_user_otp`,
`bump_user_otp_attempts`, `clear_user_otp`) — those run pre-authentication by design — and by
the verified webhook endpoints. `get_user` stays strict (post-auth, uid matches).
- **A4a (recommended):** engine begin-event + contextvars + service_request on the
  auth* user CRUD path. `SET LOCAL` is transaction-scoped → no cross-request leakage through
  the pool, covers every session, no per-function session surgery.
- **A4b:** a second dedicated "service" engine/`SessionFactory` for auth+webhook writes.
  Cleaner separation, but two engines, two pools, and re-pointing every auth helper — more
  moving parts for the same guarantee.

## 4. Deliverables

- **A. Guards on the 5 domain routers** — `user=Depends(get_current_user)` on all endpoints
  in `clinics.py`, `calls.py`, `appointments.py`, `prescriptions.py`, `payments.py`;
  `require_roles("owner")` on `POST /api/clinics`. Router set stays 7 (no new routers).
- **B. GUC plumbing** — `ContextVar` pair + `event.listen(engine.sync_engine, "begin")`
  issuing `SET LOCAL app.current_user_id` / `app.service_request` per transaction;
  `service_request` armed by auth user-CRUD helpers and verified webhook endpoints.
- **C. Schema (`postgres_schema.sql`)** —
  - `CREATE ROLE medicall_app LOGIN PASSWORD 'medicall_app'` + `GRANT ALL` on the 7 tenant
    tables + language_codes sequence (keep `authenticated` grants).
  - `ALTER TABLE … FORCE ROW LEVEL SECURITY` on the 7 tenant tables.
  - New policies: `clinic_users_own` (users manage own membership rows) +
    `clinic_users_manage` (existing clinic owner manages that clinic's memberships — enables
    future staff-add); `clinics_create FOR INSERT WITH CHECK (global owner)`; `OR
    service_request` clause on `users_own_data`, `calls_create`, `calls_read`.
  - Demo tenant seed (fixed ids, `ON CONFLICT DO NOTHING`).
- **D. `app/db/postgres.py`** — contextvars + begin-event listener; `service_request`
  arming in the 5 auth user-CRUD fns; `create_clinic` inserts the creator's owner
  `clinic_users` row in the same transaction.
- **E. `app/api/voice.py`** — `X-Service-Token` verification (401 without) on the 4
  write-facing webhook paths → arm `service_request`.
- **F. `smoke_api.py`** — auth **first** (login demo owner → Bearer); `Authorization` on all
  domain calls; webhook header on call-completed; new negative checks (401 unauth domain
  call, 403 staff creates clinic).
- **G. `docker-compose.yml` + `.env.example`** — backend `DATABASE_URL` →
  `medicall_app`; `WEBHOOK_SERVICE_TOKEN`; demo creds documented.
- **H. Docs** — `docs/uml/03-api-contracts.md` auth-required notes; tracker + HANDOVER.

No new tables → UML ER counts (10/14) unchanged. `endpoint_paths` test parser reads
decorators only → router-set assertions unaffected.

## 5. Out of scope / blocked

- Staff/owner **membership-management endpoints** (add/remove staff) — policies staged in C
  make the data layer ready; endpoints are a future phase.
- Per-provider webhook HMAC signatures (A2b) — follow-up.
- CI stack job + live RLS proof — Docker only (no Docker on this PC); authored for CI.
- Frontend changes — mock mode unaffected; real mode already requires login
  (`/login` page + `RequireAuth` + Bearer in `api.ts`).

## 6. Verification plan

Local (this PC): new `tests/test_auth_enforcement.py` (RED → GREEN) — AST/text assertions
that (a) the 5 routers reference the guards, (b) schema contains FORCE/medicall_app/role,
policies, seed, (c) postgres.py has the contextvar/begin-event/service arming, (d) voice
webhooks verify the token, (e) smoke order = auth-first + Bearer; run **all** suites
(222 existing + new) + `compileall`; frontend `npm ci` / lint / `next build` must stay green;
`smoke_api.py` compiles and its flow matches the contract. RLS truth = CI stack job
(`docker compose up` → smoke → `down -v`).

## 7. Commit sequence

spec → RED (`test_auth_enforcement.py` + smoke flow) → feat (A–H) → docs (DONE record,
tracker, HANDOVER, 03-api-contracts).

---
### Status
- **2026-09-25 DRAFT** — research done; awaiting Q1–Q4 sign-off.