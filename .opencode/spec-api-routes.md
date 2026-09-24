# SPEC: MediCall AI — API Routes (calls / appointments / prescriptions / payments / clinics)

- Branch: `ga-api-routes` (off `gd-dashboards` tip `640ab2c`) · Worktree: `.worktrees\ga-api-routes`
- Status: **DRAFT — pending sign-off. No code written yet.**

## Goal
Build the REST API layer that the 16 dashboard pages (clinic 7-tab + admin 9-view) will consume: five new FastAPI routers — `calls`, `appointments`, `prescriptions`, `payments`, `clinics` — plus Pydantic schemas, the missing postgres CRUD helpers, and a minimal `payments` table. Register all routers in `backend/main.py` (currently voice-only). Frontend scope decided by D1 below.

## Existing state (verified this session, evidence-backed)

| Area | Status |
|---|---|
| `backend/main.py` | Registers **only** `voice.router` at `/api/voice`; comment "calls/appointments/prescriptions/payments land in G4+" is stale (G4 done, routers never added). |
| `backend/app/db/postgres.py` | ORM: Clinic, ClinicUser, Call, Appointment, Prescription, CallEmbedding, LanguageCode, CallSession. CRUD: `create_clinic`, `get_clinic`, `list_clinic_calls(clinic_id, state, language)`, `create_call`, `update_call_state`, `update_call_transcript`, `create_appointment`, `create_prescription`, `log_call_embedding`, `get_call_embedding`, `list_language_codes`, `init_db`, `get_db_session`. |
| Missing CRUD | No appointment get/list/status-update; no prescription get/list/status-update; no clinic list/update; **no payments model at all**. |
| `backend/app/api/` | Only `voice.py` (3 webhooks + livekit-agent-start + call-completed). Inline `BaseModel` style. |
| `backend/postgres_schema.sql` | No `payments` table (payments exist only as `PAYMENT_SENT/PAYMENT_EXPIRED` call states). |
| Frontend | 16 pages, all static server components consuming `mock.ts` — `mock.ts` header: *"The API-routes phase replaces this with live backend data."* No `/api/` fetches exist. |

## Non-Goals (hold the line)
- No auth middleware — G6-Q1 (ABHA/SSO/OTP) is its own later phase; multi-tenant scoping here is by `clinic_id` query param. RLS in `postgres_schema.sql` stays as-is.
- No payment-gateway SDK calls — G6-Q5 (which flow pays / which gateway) is still open. `POST /api/payments` only records intent (gateway/ref captured if supplied), never calls Razorpay/PhonePe/Cashfree.
- No `/call-completed` → `update_call_transcript` DB write — Docker/CI stage owns that path (voice.py TODO stands).
- No UML, no docker-compose, no Dockerfile changes, no new frontend visuals (only the wiring D1 approves).
- No EHR/ABDM writes (G6-Q7: transcript-only Phase 1).

## API contract (single source → Docker/CI will smoke-test this exact shape)

### `/api/clinics`
| Method/Path | Purpose | Notes |
|---|---|---|
| `GET /api/clinics?is_active=` | Admin clinics list | order by name ASC |
| `POST /api/clinics` | Create clinic | name/phone_number/city/state required; 201 |
| `GET /api/clinics/{clinic_id}` | Clinic detail + settings | 404 if missing |
| `PATCH /api/clinics/{clinic_id}` | Update settings | phone/address/city/state/pincode/closing_time/ai_instructions/plan/is_active |

### `/api/calls`
| Method/Path | Purpose | Notes |
|---|---|---|
| `GET /api/calls?clinic_id=&state=&language=&severity=&from=&to=&limit=50&offset=0` | List calls | started_at DESC; filters: state ∈ 9 G3 states, language ∈ hi/en/ta/te/bn, severity ∈ green/amber/red/critical, ISO datetime range, limit cap 200 |
| `GET /api/calls/{call_id}` | Call detail incl. transcript | 404 if missing |
| `PATCH /api/calls/{call_id}/state` | State transition | body `{"state": ...}`; validated against `STATE_TRANSITIONS` (models/call.py) — invalid transition = 409 |
| `GET /api/calls/{call_id}/transcript` | Transcript JSONB | 404 if missing |

### `/api/appointments`
| Method/Path | Purpose | Notes |
|---|---|---|
| `GET /api/appointments?clinic_id=&status=&from=&to=` | List | status ∈ pending/confirmed/completed/cancelled/no_show (schema line 74); scheduled_at ASC |
| `POST /api/appointments` | Create | patient_name/phone required, scheduled_at required → 201 |
| `GET /api/appointments/{id}` | Detail | 404 if missing |
| `PATCH /api/appointments/{id}/status` | Status update | body `{"status": ...}`; validated against the 5 statuses → 422 otherwise; 404 if missing |

### `/api/prescriptions`
| Method/Path | Purpose | Notes |
|---|---|---|
| `GET /api/prescriptions?clinic_id=&status=` | List | status ∈ pending/approved/sent_pharmacy/dispensed (schema line 96) |
| `POST /api/prescriptions` | Create | patient_name/medication required → 201 |
| `GET /api/prescriptions/{id}` | Detail | 404 if missing |
| `PATCH /api/prescriptions/{id}/status` | Status update | validated against the 4 statuses → 422; 404 if missing |

### `/api/payments` (new minimal table — D2)
| Method/Path | Purpose | Notes |
|---|---|---|
| `GET /api/payments?clinic_id=&status=` | List | status ∈ pending/captured/failed/refunded; created_at DESC |
| `POST /api/payments` | Record intent (scaffold) | amount/currency(INR)/gateway(razorpay\|phonepe\|cashfree\|manual)/gateway_ref/status; **no SDK call** — 201 |
| `GET /api/payments/{id}` | Detail | 404 if missing |
| `PATCH /api/payments/{id}/status` | Status update | validated against the 4 statuses → 422; 404 if missing |

### `payments` table (added to `postgres_schema.sql` + ORM)
`id UUID PK`, `clinic_id UUID FK→clinics`, `call_id UUID FK→calls NULL`, `appointment_id UUID FK→appointments NULL`, `amount NUMERIC(10,2) NOT NULL`, `currency TEXT DEFAULT 'INR'`, `gateway TEXT` (`razorpay|phonepe|cashfree|manual`), `gateway_ref TEXT`, `status TEXT DEFAULT 'pending'` (`pending|captured|failed|refunded`), `created_at/updated_at TIMESTAMPTZ`; index `(clinic_id, status)`; RLS + trigger + updated_at, mirrors existing tables. `init_db()` picks it up via metadata (Docker/CI runs the SQL file).

## New postgres CRUD helpers (extend `postgres.py`)
- `list_clinics(active_only=None) -> list[Clinic]` (name ASC)
- `update_clinic(clinic_id, **fields) -> Optional[Clinic]`
- `get_appointment(appointment_id)`, `list_appointments(clinic_id, status=None, from_=None, to=None)` (scheduled_at ASC), `update_appointment_status(appointment_id, status) -> bool`
- `get_prescription(prescription_id)`, `list_prescriptions(clinic_id, status=None)`, `update_prescription_status(prescription_id, status) -> bool`
- `get_call(call_id)`, `list_calls(clinic_id, state/language/severity/from_/to/limit/offset)` (supersedes + extends `list_clinic_calls` — keep the old name as a thin wrapper or migrate callers; single internal `list_calls` used by the router)
- `create_payment(...)`, `list_payments(clinic_id, status=None)`, `get_payment(payment_id)`, `update_payment_status(payment_id, status) -> bool`
- Call state transition is validated in the router against `STATE_TRANSITIONS` **before** calling existing `update_call_state` (it is a raw setter).

## Pydantic schemas (D3)
New `backend/app/schemas/` package: `__init__.py`, `clinic.py`, `call.py`, `appointment.py`, `prescription.py`, `payment.py`. Each router imports its request models from here (voice.py keeps its inline models — not part of this phase). Request models only where a body exists (POST/PATCH); responses return plain dicts/ORM-fields via FastAPI (no response_model ceremony, keeps Docker/CI assertions simple). All field names snake_case, matching ORM columns + SQL.

## Files
- **New**: `backend/app/api/clinics.py`, `calls.py`, `appointments.py`, `prescriptions.py`, `payments.py`; `backend/app/schemas/{__init__,clinic,call,appointment,prescription,payment}.py`; `backend/tests/test_api_routes.py`
- **Edit**: `backend/main.py` (register 6 routers — voice + 5 new, drop stale comment); `backend/app/db/postgres.py` (Payment ORM + the CRUD list above); `backend/postgres_schema.sql` (payments table + index + RLS + trigger)
- **If D1 = frontend wiring**: `frontend/src/lib/api.ts` (typed fetch helpers) + pages swap `mock.ts` imports for api calls (mock.ts retained as seed/fallback types where needed)

## Test plan (RED → GREEN, stdlib-only, mirrors `test_dashboards.py` source-level pattern)
`backend/tests/test_api_routes.py` asserts by `ast` + substring over file text (no third-party imports — this PC has no fastapi/pydantic/sqlalchemy):
1. `main.py` includes all 6 routers with correct prefixes/tags (ast `include_router` calls).
2. Each of the 5 router files defines the exact endpoints above (method decorators + path strings, ast).
3. `schemas/` package: each module exists and exports the expected request models (ast class defs incl. `BaseModel` subclassing) + required field names.
4. `postgres.py`: `Payment` ORM class present; each new CRUD helper is an `async def` (ast — remember the `AsyncFunctionDef` gotcha); `STATE_TRANSITIONS` import used in the calls router.
5. `postgres_schema.sql`: `CREATE TABLE payments` with the 4 statuses + gateway values substring-verified.
6. Invariant guards: voice.py endpoint set unchanged (no regression), no restaurant/TalkByte strings in new files, `mock.ts` header comment updated only under D1.
- **RED now**: routers + schemas + Payment + most CRUD missing → most tests fail.
- **GREEN after**: new phase tests pass + **full regression 105/105** (G1+G2 11 · G3 9 · G4 33 · G5 18 · dashboards 34) + `py_compile` exit 0 over all touched files (PowerShell: check `$LASTEXITCODE`, stderr warnings avoided).

## Verify commands
```
python3 tests/test_api_routes.py          # new phase — expect OK
python3 tests/test_g1_g2.py && python3 tests/test_g3_state_machine.py && python3 tests/test_g4_voice.py && python3 tests/test_g5_reqs.py && python3 tests/test_dashboards.py
py_compile app\main.py app\api\*.py app\schemas\*.py app\db\postgres.py
```

## Decisions for sign-off (this STOP)
- **D1 Scope**: backend routers only | backend + full frontend wiring (16 pages) | backend + api client + core clinic pages (dashboard/calls/appointments/prescriptions).
- **D2 Payments**: minimal `payments` table + scaffold router (recommended) | router serves derived call-state data only (no table) | defer payments router + table entirely (payments stay mock-only).
- **D3 Schemas**: new `app/schemas/` package (recommended) | inline `BaseModel` per router (voice.py style).

## Risks
| Risk | Mitigation |
|---|---|
| Payments table without gateway = half-contract | Gated explicitly on G6-Q5; scaffold records intent only, statuses chosen to match Razorpay/PhonePe/Cashfree webhook states so the table survives the Q5 decision |
| Frontend wiring unverifiable locally (no node_modules) | Source-level tests assert import/endpoint wiring; real `next build` lands in Docker/CI stage |
| Acceptance tests test the file, not the socket | Endpoint table above is the contract; Docker/CI stage smoke-tests it over HTTP against a live DB |
| State transition updates bypass the state machine | Router validates against `STATE_TRANSITIONS` before the raw setter; 409 on invalid |