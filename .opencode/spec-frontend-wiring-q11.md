# SPEC: G6-Q11 — Frontend Wiring + Platform Admin (complete the UI)

## Goal

Make the application's UI complete: wire the remaining mock pages to their real
backend endpoints, and add the platform-level backend surface the admin views
need. Signed scope = **A3 Full platform build** (question tool, 2026-09-26):
clinic-side 1:1 wiring + the mappable admin pages + a new role-gated `/api/admin`
router (platform clinics/patients/revenue aggregates) + a "recent callers"
patient view derived from `/api/calls`. Outcome: **13 of 17 pages live** — the
4 remaining admin views (doctors / billing / infrastructure / audit) stay on
mock because no backend entity exists for them this phase.

## §0 Sign-off Record (2026-09-26, question tool — scope A3)

| **Status** | DRAFT → APPROVED (signed off 2026-09-26, question tool, scope=A3) → **RED** (suite authored) → **GREEN** (implementation) | | |
| Q | Choice | Meaning |
|---|--------|---------|
| Q1 | **A3 — Full platform build** | Wire all clinic pages (triage-queue, appointments, prescriptions, analytics, patients) + admin overview/live-monitor/clinics/patients/revenue; add a role-gated `/api/admin` router with platform aggregates; patients pages derive "recent callers" from `/api/calls`. |
| Q2 | **A1 — `platform_admin` role (weight 6, above owner)** | Additive role-matrix extension in `services/auth.py` (`ROLES` + `ROLE_WEIGHTS`); `can(platform_admin, r)` = True for every clinic role. Seeded via the demo tenant (`platform@medicall.in`, `ON CONFLICT DO NOTHING`) — register() cannot grant it (no self-serve path, same as owner). |
| Q3 | **A1 — Aggregates ride `app.service_request`, gated by role at the API** | Each `/api/admin` endpoint requires `require_roles("platform_admin")`; the aggregate DB reads arm `service_request_ctx()` internally (the auth-CRUD pattern). Extends the only read policy missing the bypass among the admin's tables: `clinic_staff_read` FOR SELECT gains the `app.service_request = 'on'` OR-clause (no suite pins that policy's exact text — verified). |
| Q4 | **A1 — 5 admin endpoints** | `GET /api/admin` (overview), `/clinics`, `/patients`, `/revenue`, `/calls` — all `Depends(require_roles("platform_admin"))`. |
| Q5 | **A1 — Clinic patients = recent callers from `/api/calls`** | Client-side aggregation (unique `caller_number`, call count, last call, language) off `GET /api/calls?...&limit=200` — exactly as signed. |
| Q6 | **A1 — doctors/billing/infrastructure/audit stay mock** | No `doctors`/`billing`/`plans`/`audit_actions` tables exist; infrastructure = external SaaS ops status. Pages keep rendering mock with a documented "no backend entity yet" note. |

## Scope (implementation)

### Backend (platform surface)

1. `app/services/auth.py`: `ROLES += ("platform_admin",)`; `ROLE_WEIGHTS["platform_admin"] = 6`
   (above owner=5); comment notes the platform superuser sits above the clinic matrix.
2. `postgres_schema.sql`:
   - `clinic_staff_read` FOR SELECT gains `OR current_setting('app.service_request', true) = 'on'`
     with a comment (platform aggregates read clinic rows under server-side authority, mirroring
     `users_own_data` / `payments_manage`; the API gate is `require_roles("platform_admin")`).
   - Demo tenant seed adds `platform@medicall.in` (role `platform_admin`, fixed UUID,
     `ON CONFLICT DO NOTHING`) — an operator account for the admin UI.
3. `app/db/postgres.py` — 5 new platform aggregates (async, read-only, RLS-riding:
   each internally `with service_request_ctx():` around its `SessionFactory` block, the
   auth-CRUD pattern):
   - `platform_overview()` → `{clinics_total, clinics_active, calls_today, live_calls, revenue_today_inr}`
   - `platform_clinics()` → per clinic (ordered by name): `{id, name, city, state, plan, is_active, calls_mtd, calls_today, live_calls}`
   - `platform_patients()` → distinct callers across clinics: `{caller_number, clinic_id, clinic_name, language, first_call_at, last_call_at, call_count, last_state}`
   - `platform_revenue()` → `{captured_inr, pending_inr, failed_inr, refunded_inr, count, by_gateway: {gateway: {captured_inr, count}}, by_clinic: [{clinic_id, clinic_name, captured_inr, count}]}`
   - `platform_calls(limit, offset)` → recent calls cross-clinic (newest first, limit ≤ 200):
     `{id, clinic_id, clinic_name, caller_number, language, state, severity, started_at, duration_seconds}`
4. `app/api/admin.py` (new, 11th router) — prefix `/api/admin`, all endpoints
   `Depends(require_roles("platform_admin"))`, thin handlers calling the platform fns
   (self-documenting docstring, no banned tokens).
5. `main.py`: `include_router(admin.router)`.

### Backend contract suite updates (SAME commit as feat — the Q10 lesson)

6. `tests/test_api_routes.py`: `test_main_registers_all_ten_routers` → **eleven** (exact set
   + admin); `ROUTER_MODULES += "admin"`; `EXPECTED_ENDPOINTS["admin"]` = the exact 5 GETs;
   docstring "…G6-Q9 added analytics (tenth); G6-Q11 added admin (eleventh)".

### Frontend (all 10 wired pages + client)

7. `src/lib/api.ts`:
   - `authFetch(path)` — Bearer + Accept + throw-on-!ok (dedupes the fetchCalls pattern).
   - Types matching the backend serializers: `ApiAppointment`, `ApiPrescription`,
     `ApiAdminOverview`, `ApiAdminClinic`, `ApiAdminPatient`, `ApiAdminRevenue`,
     `ApiAdminCall`; analytics payload types.
   - Clinic hooks (clinic_id from `NEXT_PUBLIC_CLINIC_ID`, the existing pattern):
     `useAppointments`, `usePrescriptions`, `useAnalyticsKpis` (fires the 8
     `/api/analytics/*` GETs in parallel), `useRecentCallers` (limit=200 → group by caller).
   - Admin hooks (NO clinic_id — platform scope): `useAdminOverview`, `useAdminClinics`,
     `useAdminPatients`, `useAdminRevenue`, `useAdminLiveCalls`.
   - `formatINR(value)` — ₹ with Indian grouping (no `$` anywhere — suite-pinned).
   - USE_MOCK `auto|true|false` semantics identical to `useTodayCalls`: hook enabled when
     `!= "true"`, auto-falls-back to the mock fixture on error/empty.
8. Page conversions (swap the mock import → hook, keep the JSX shape; the hook embeds the
   same mock fixture as fallback, so offline dev still renders):
   - Clinic: `(clinic)/triage-queue` (useCalls, non-terminal filter), `appointments`,
     `prescriptions`, `analytics`, `patients` (recent callers).
   - Admin: `admin/page` (overview), `live-monitor`, `clinics`, `patients`, `revenue`.
9. `docs/uml/03-api-contracts.md`: add the `/api/admin` node (5 endpoints, platform_admin
   gate, service-bypass note); `docs/uml/00-index.md` if it enumerates prefixes.

## Non-Goals

- No new tables / entities (patients/doctors/billing/audit aggregates derive from
  calls/payments/clinics only; no `patients`, `audit_actions`, `billing` tables added).
- No changes to the existing clinic-scoped endpoints or analytics router (backend 561-suite
  surface untouched apart from the additive admin router + role + policy).
- No live provider/DB runtime from this PC: platform aggregates are verified by the
  source-assertion RED suite + full regression; the ci.yml stack job stays the runtime proof.
- No merge of branch tips to main (stays a per-phase worktree, per convention).
- Mock fixtures stay in `components/mock.ts` (test_dashboards pins `+91`/`₹`); the 4
  unwired admin pages keep rendering them.

## Acceptance Criteria

- `backend/tests/test_frontend_wiring_q11.py` GREEN (source-assertion suite, stdlib only).
- Full regression: **561 prior + new suite** ALL PASS via
  `py -3.14 -m unittest discover -s tests -p "test_*.py"` from `backend`;
  `py -3.14 -m compileall -q app scripts tests main.py` exit 0.
- `test_api_routes.py` updated in the feat commit: 11 routers exact set, admin endpoints exact.
- The 10 wired pages import `@/lib/api` and no longer import `@/components/mock`; the 4
  unwired admin pages still import mock and carry a "no backend entity yet" note.
- No `$[0-9]` anywhere in `frontend/src` (existing suite rule); mock.ts keeps `+91` and `₹`.
- Frontend toolchain (npm lint/build) re-verified locally if the worktree allows it
  (eslint 0 errors, `next build` exit 0) — the py source-suite remains the hard gate.

## Risks

| Risk | Mitigation |
|------|------------|
| Route-inventory exact-set suite breaks when admin lands | `test_api_routes.py` updated in the same feat commit (Q10 lesson) |
| `platform_admin` above owner in `can()` widens owner-gated endpoints | RLS `clinics_create` checks the literal role='owner', so no silent DB bypass; platform_admin is seeded, never self-served |
| clinics policy extension loosens clinic reads | FOR SELECT only + server-side arm authority only; normal JWTs still pass the membership check |
| npm ci/build on a OneDrive worktree hits MAX_PATH | g-ci proved the toolchain; if npm fails here, the py source-suite remains the gate and npm stays CI-owned |
| Frontend analytics charts map to shifted analytics payload keys | FEAT reads `compute_*`/shape output before mapping; charts render from `by_day`/`by_language`/`by_severity` payloads |