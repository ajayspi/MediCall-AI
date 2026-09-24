# SPEC: G5 — Requirements cleanup + Knowlarity client

Status: **PENDING SIGN-OFF** (drafted 2026-09-24). Approval unlocks
implementation on branch `g4-voice` (worktree `.worktrees\g4-voice`,
startup GREEN as of G4 DONE).

## 1. Goal

Resolve tracker record G5 (MAJOR) — `backend/requirements.txt` is stale/missing
— plus the Knowlarity client gap:

- **Drop** unneeded/stale pins: `stripe`, `celery`, `gunicorn`, `psycopg2-binary`
  (asyncpg is the async driver already in use), `sqlalchemy-asyncio==2.0.30`
  (NOT a real package name; async support ships inside SQLAlchemy 2.0).
- **Fix** payment pins to verified real packages (see §3 — evidence-backed via
  PyPI 2026-09-24).
- **Add** dev/test/lint deps for the red-green-lint workflow: `pytest`,
  `pytest-asyncio`, `ruff` (handover: "add pytest/ruff"; landed visibly so
  Docker/CI installs one file).
- **Knowlarity path decided**: implement an in-house client against the public
  Knowlarity SR API via `httpx` (already a dependency). Knowlarity has **no
  maintained official PyPI SDK**, so an httpx client is the correct call.

No runtime code paths change: `main.py`/`app` imports are untouched; nothing
currently calls outbound dialing (that wiring belongs to the routes/dashboards
tasks). This task is dependency hygiene + the client primitive + tests.

## 2. Non-Goals (this task)

- Wiring outbound dialing into `voice.py` / dashboards (later routes task).
- SMS via Knowlarity/Gupshup (G6-Q8 notifications).
- Exotel/Twilio client implementations (G4 wired inbound parsers; outbound
  clients are a later telephony task — audit only flagged Knowlarity).
- Installing packages on this PC (no third-party deps by design — Docker/CI
  installs; tests stay stdlib-only).
- G6 open questions (Q2–Q5, Q8–Q10) — none block G5.

## 3. Dependency pins (evidence-backed 2026-09-24)

| Package | Decision | Evidence |
|---|---|---|
| `stripe==8.0.0` | **REMOVE** | Restaurant-only; Indian gateways replace it |
| `celery==5.4.0` | **REMOVE** | No task infra in repo (`app/workers` deleted in G1; G1 test guard lists `app.workers.celery_app` as deleted-module) |
| `gunicorn==22.0.0` | **REMOVE** | `main.py` runs uvicorn; Docker/CI can use it directly |
| `psycopg2-binary==2.9.9` | **REMOVE** | `asyncpg` is the driver (`DATABASE_URL` uses `postgresql+asyncpg://`) |
| `sqlalchemy-asyncio==2.0.30` | **REMOVE** | Not a real PyPI package name; SQLAlchemy 2.0 has native async |
| `razorpay` | **PIN `razorpay==2.0.1`** | Official SDK; 2.0.1 latest (2026-03-09) |
| `phonepe` | **REPLACE with `phonepe-pg-sdk-python==2.3.0`** | Official PhonePe SDK import name `phonepe_sdk`; `phonepe==1.0.0` is a wrong/nonexistent name. Comment: may need `--index-url` to PhonePe's repo per docs |
| `cashfree-pg` | **PIN `cashfree-pg==6.0.1`** | Official (Cashfree Payments); 6.0.1 current; `1.0.0` unverifiable |
| `exotel==1.0.0`, `twilio==9.0.0` | **KEEP** | Audit flagged only missing Knowlarity, not these |
| `pytest`, `pytest-asyncio`, `ruff` | **ADD** in dev/test section | `pytest==8.3.5`, `pytest-asyncio==0.25.3`, `ruff==0.11.9` |
| Everything else | **KEEP** | fastapi/uvicorn/httpx/pydantic/asyncpg/sqlalchemy/pgvector/openai/deepgram-sdk/livekit-*/elevenlabs/tenacity/structlog/prometheus-client/python-json-logger/alembic/redis/python-dotenv/python-jose/passlib/python-multipart |

## 4. Files

| File | Change |
|---|---|
| `backend/requirements.txt` | Rewrite: drops + corrected pins + `# --- dev/test ---` section (pytest/pytest-asyncio/ruff). Single file (D2 decision). |
| `backend/app/services/knowlarity.py` | **NEW, stdlib-importable.** `KnowlarityConfig` dataclass + `from_env()`; `headers()`, URL builders (makecall / campaign / order-status), `makecall_payload()`, `campaign_payload()` (default tz `Asia/Kolkata`, formatted start_time), `_id_of()` (request/order id extractor). Transport methods (`make_call`, `place_campaign`, `campaign_status`) import `httpx` **lazily** so the module imports cleanly on this PC — same pattern as G4 `telephony.py`. |
| `backend/.env.example` | Add `KNOWLARITY_AUTHORIZATION=` + comment that headers are `authorization` + `x-api-key` (SR API). Keep `KNOWLARITY_API_KEY`, `KNOWLARITY_SIP_URI`. |
| `backend/tests/test_g5_reqs.py` | **NEW** — see §5. |

Endpoints verified (developer.knowlarity.com + Gupshuf-knowlarity docs):
`POST {base}/call/makecall`, `POST {base}/call/campaign`,
`GET {base}/call/campaign/order-status/?order_id=…`, base
`https://kpi.knowlarity.com/Basic/v1/account`.

## 5. Test plan (RED first — `backend/tests/test_g5_reqs.py`, stdlib-only)

RED pre-fix (each maps to a current gap): requirements still lists stripe/celery
(fail); no pytest/ruff (fail); no dev section; payments unpinned wrong
(razorpay==1.4.1 present, `phonepe` name present); `services/knowlarity.py`
missing (import error).

1. `requirements.txt` source checks (parse lines):
   - no `stripe`, `celery`, `gunicorn`, `psycopg2-binary`, `sqlalchemy-asyncio`
   - `pytest`, `pytest-asyncio`, `ruff` present **and uncommented**
   - `razorpay==2.0.1`, `phonepe-pg-sdk-python`, `cashfree-pg` present; bare
     `phonepe` name absent
   - `asyncpg` still present
2. `.env.example` contains `KNOWLARITY_AUTHORIZATION`.
3. Behavioral (import `services/knowlarity.py` directly — stdlib):
   - `from_env` reads `KNOWLARITY_API_KEY` / `KNOWLARITY_AUTHORIZATION` /
     `KNOWLARITY_SIP_URI` (monkeypatched `os.environ`)
   - `headers()` → `x-api-key` + `authorization` + JSON accept/content-type
   - URL builders → correct endpoints (+ order-status query param)
   - `makecall_payload` → has `k_number`, `agent_number`, `customer_number`,
     `caller_id`, `additional_params.uniqueid`
   - `campaign_payload` → `sound_id` cast to str, default timezone
     `Asia/Kolkata`, explicit `start_time` honored when given, `k_number`
     present
   - `_id_of` picks `request_id`/`order_id`/`id` defensively, else `""`
   - config with empty keys still constructs (transport errors happen at call
     time, Docker/CI)

Verify after implementation (from `backend\`): `python3 tests/test_g5_reqs.py`
+ G1/G2 + G3 + G4 suites all GREEN, then
`python3 -m py_compile app/services/knowlarity.py main.py app/api/voice.py …`
(all touched modules; requirements.txt is not compiled).

## 6. Decisions needed before/at sign-off

- **D1 — Knowlarity transport** (recommended): in-house `httpx` client against
  the public SR API (`x-api-key` + `authorization` headers), stdlib-importable
  core with lazy transport. Alternative (rejected): adding an unofficial PyPI
  "knowlarity" wrapper — unmaintained, unpinnable to spec.
- **D2 — requirements layout** (recommended): single `requirements.txt` with a
  `# --- dev/test ---` section (one install target for Docker/CI, matches the
  simple current setup). Alternative: split `requirements-dev.txt`.
- **D3 — dev pins** (recommended): `pytest==8.3.5`, `pytest-asyncio==0.25.3`,
  `ruff==0.11.9` — all real releases; Docker/CI validates on install.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Wrong payment pins break Docker install | Pins verified against PyPI 2026-09-24; phonepe index caveat documented in the file |
| Knowlarity API drift (documented JSON + auth may vary by plan) | Config-driven base_url/keys, defensive `_id_of`, live sampling at integration stage |
| Lazy httpx import hides transport bugs locally | Transport methods are thin; request builders + payloads are fully unit-tested; live path in Docker/CI |

## 8. Sign-off

- **Status**: ☑ APPROVED (2026-09-24) — D1 in-house httpx client, D2 single
  file + dev section, D3 pinned pytest 8.3.5 / pytest-asyncio 0.25.3 /
  ruff 0.11.9.
- **Approver / date**: User via question tool, 2026-09-24
- **Next after approval**: write `tests/test_g5_reqs.py` RED → implement files
  → GREEN + py_compile → commit on `g4-voice` → then G-dashboards (clinic
  7-tab + admin 9-view).

## 9. Delivered record

- **Date**: 2026-09-24
- **Files**: `backend/requirements.txt` (rewrite), `backend/app/services/knowlarity.py`
  (new), `backend/.env.example` (+KNOWLARITY_AUTHORIZATION), `backend/tests/test_g5_reqs.py`
  (new).
- **Verify**: `python3 tests/test_g5_reqs.py` + G1/G2 + G3 + G4 suites GREEN,
  `py_compile` clean on touched modules.