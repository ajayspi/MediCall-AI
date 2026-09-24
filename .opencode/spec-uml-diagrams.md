# SPEC: MediCall AI — UML Diagrams (ER / state machine / API contracts / data flow / deployment)

- Branch: `g-uml` (off `ga-api-routes` tip `e19564b`) · Worktree: `.worktrees\g-uml`
- Status: **DRAFT — pending sign-off. No files written yet.**

## Goal
Close tracker gap G7 ("no UML diagrams (ER/state-machine/API-contracts/data-flow/deployment) exist yet"): deliver five renderable architecture diagrams as real repo artifacts so the system's contracts are visible next to the code that implements them. This is a **docs-only** phase — no `.py`, no `.tsx`, no SQL changes.

## Existing state (verified this session)
| Area | Status |
|---|---|
| Diagrams | None anywhere in the repo (no `docs/` dir, no mermaid files). Umbrella `spec-micc-database-dashboards-routes-uml.md` titled the phase but contains no diagram section. |
| Source of truth per diagram | ER: `backend/postgres_schema.sql` (9 tables — incl. the API-phase `payments`); state machine: `backend/app/models/call.py` (`CallState` 9 states + `STATE_TRANSITIONS`, single source); API contracts: the 6 routers just shipped in `ga-api-routes`; data flow: `app/api/voice.py` + `app/services/` livekit agent; deployment: `docker-compose.yml` + `Dockerfile`s + env examples. |
| Test harness | `backend/tests/` stdlib source-level acceptance pattern (test_dashboards.py / test_api_routes.py) — the new diagram tests mirror it. |

## Non-Goals (hold the line)
- No code changes of any kind (no Python/TS/SQL edits).
- No diagram-rendering toolchain installs (no Java/Graphviz/mermaid-cli — this PC has no pip/npm for backend tests; diagrams are committed as **Mermaid source in Markdown**, renderable on GitHub/VS Code/typora with zero deps).
- Diagrams describe the **current** system; they are not a redesign wish-list. Where the tracker already decided something (G6-Q5 payments open, `/call-completed` write pending Docker/CI), the diagram marks it rather than inventing it.

## Deliverables

### `docs/uml/` directory (format + layout per D1/D2 below)
1. **`00-index.md`** — one-line description + mermaid render link per diagram, pointers to the single sources (schema.sql, models/call.py, routers).
2. **`01-er.md`** — `erDiagram`: the 9 tables (clinics, clinic_users, calls, appointments, prescriptions, call_embeddings, language_codes, call_sessions, payments) with PK/FK edges matching `postgres_schema.sql` (calls.appointment_id -> appointments, payments -> clinics/calls/appointments, clinic_users unique (clinic_id,user_id)); RLS note (clinic-scoped via `auth.uid()`).
3. **`02-state-machine.md`** — `stateDiagram-v2`: the 9 `CallState` values with EXACTLY the `STATE_TRANSITIONS` edges from `models/call.py` (`GREETING->TRIAGE`, `TRIAGE->{APPOINTMENT,PRESCRIPTION,ESCALATED,DROPPED}`, `APPOINTMENT->{COMPLETE,PRESCRIPTION,?}`, `PRESCRIPTION->{PAYMENT_SENT,COMPLETE,?}`, `PAYMENT_SENT->{COMPLETE,PAYMENT_EXPIRED,DROPPED}`, `PAYMENT_EXPIRED->{APPOINTMENT,ESCALATED,DROPPED}`, COMPLETE/ESCALATED/DROPPED terminal) + `note right` that invalid transitions get 409 from the calls router. **Constraint: the diagram must match the code — the acceptance test reads `models/call.py`'s `STATE_TRANSITIONS` via ast and cross-checks the mermaid edge set.**
4. **`03-api-contracts.md`** — `flowchart LR` (or sequence-free graph): the 6 routers (`/api/voice`, `/api/clinics`, `/api/calls`, `/api/appointments`, `/api/prescriptions`, `/api/payments`) with each endpoint from the API-routes contract table (list/create/get/patch + the calls sub-endpoints `/state` + `/transcript`), plus `verif` annotations for the acceptance-tested behaviors (409 invalid transition, 422 invalid status, 404 missing row).
5. **`04-data-flow.md`** — `flowchart LR`: the voice pipeline — Exotel / Knowlarity / Twilio-India → `voice.py` webhooks → `ProviderEvent` → state machine → LiveKit agent dispatch → Deepgram STT + ElevenLabs TTS (5 languages hi/en/ta/te/bn) → `/call-completed` → `update_call_transcript` (marked **TODO: Docker/CI owns the DB write**).
6. **`05-deployment.md`** — `flowchart` (or mermaid `architecture-beta`): services — Next standalone frontend → FastAPI backend (uvicorn) → PostgreSQL 16 + pgvector → Upstash Redis (stub) → LiveKit server + agents → external SaaS (Deepgram, ElevenLabs, OpenAI, 3 telephony providers); env vars `DATABASE_URL`, `REDIS_URL`, `LIVEKIT_URL` etc; Docker Compose as the single stack entry; RLS/auth noted as later phase (G6-Q1).

### Acceptance tests — `backend/tests/test_uml_diagrams.py` (stdlib, source-level)
Mirrors `test_dashboards.py`/`test_api_routes.py`: reads the mermaid files as text (+ ast for `models/call.py`), asserts:
1. All 6 files exist under `docs/uml/` (5 diagrams + index).
2. Each diagram file opens with the right mermaid type header (`erDiagram` / `stateDiagram-v2` / `flowchart ...`).
3. ER: all 9 table names present + the FK edges (clinics→clinic_users, clinics→calls, calls→appointments, clinics→appointments, clinics→prescriptions, calls→prescriptions, calls→call_embeddings, clinics→payments, calls→payments nullable, appointments→payments nullable, call_sessions→calls) as mermaid relationship lines.
4. State machine: 9 state names present; the mermaid edge set **equals** `STATE_TRANSITIONS` parsed from `models/call.py` via ast (this is the load-bearing cross-check — the diagram can't drift from the code).
5. API contracts: all 6 router paths + the 5 method/path endpoint strings per router (reuses the `EXPECTED_ENDPOINTS`-style contract from test_api_routes).
6. Data flow: Exotel, Knowlarity, Twilio, Deepgram, ElevenLabs, LiveKit, postgres all present; `/call-completed` present.
7. Deployment: frontend, backend(api), postgres, redis, livekit, docker-compose all present.
8. No restaurant/TalkByte leftovers in the new files (extends the existing token scan).
- **RED now**: `docs/uml/` doesn't exist → most tests fail. **GREEN after**: new suite passes + full regression stays 105+36 (no code touched) + `py_compile` untouched (docs-only, still run for belt-and-braces).

## Files
- **New**: `docs/uml/00-index.md`, `01-er.md`, `02-state-machine.md`, `03-api-contracts.md`, `04-data-flow.md`, `05-deployment.md`; `backend/tests/test_uml_diagrams.py`.
- **Edit (DONE record only)**: `.opencode/spec-idea-refinement-gaps.md`, `HANDOVER.md` (mark UML done, next = Docker/CI integration stage).

## Verify commands
```
python3 tests/test_uml_diagrams.py     # new phase — expect OK
python3 tests/test_api_routes.py && python3 tests/test_dashboards.py && python3 tests/test_g1_g2.py && python3 tests/test_g3_state_machine.py && python3 tests/test_g4_voice.py && python3 tests/test_g5_reqs.py   # regression
```

## Decisions for sign-off (this STOP)
- **D1 Format**: Mermaid-in-Markdown, committed as source (recommended — renders on GitHub/VS Code, zero deps) | PlantUML `.puml` (needs Java to render) | Graphviz `.dot` (needs Graphviz).
- **D2 Layout**: `docs/uml/` one file per diagram + index (recommended — each diagram independently linkable, matches G7's five named diagrams) | single consolidated `docs/technical-design.md` (one file, five mermaid blocks).
- **D3 Scope**: the five G7 diagrams (recommended) | the five **plus a 6th inbound-call lifecycle sequence diagram** (`phone → provider webhook → agent → triage → appointment/prescription → complete`, showing the payment loop) | ER + state-machine only.

## Risks
| Risk | Mitigation |
|---|---|
| Diagram drifts from code | Load-bearing cross-check: state-machine test parses `STATE_TRANSITIONS` from ast and asserts the mermaid edge set EQUALS it; ER/API tests check the entity/endpoint sets |
| Mermaid not renderable locally (no renderer) | GitHub/VS Code render natively; source-level assertions still verify structure; rendering verified in Docker/CI-adjacent step or editor |
| Docs phase feels thin | It closes G7 (the last open audit gap) and gives the Docker/CI stage a reviewable deployment/API picture to build against |