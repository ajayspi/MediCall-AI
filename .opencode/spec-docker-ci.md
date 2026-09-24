# SPEC: MediCall AI — Docker/CI Integration Stage (g-ci)

- Branch: `g-ci` (off `g-uml` tip `d822f27`) · Worktree: `.worktrees\g-ci`
- Status: **APPROVED 2026-09-25 + DONE** — Q1 local-toolchain verify + author CI
  (no Docker on this PC; node/npm are real and the frontend verified locally) ·
  Q2 client module + 2 proof pages (live-calls, dashboard) · Q3 3-job ci.yml +
  smoke_api.py + toolchain fixes. See tracker DONE record + commits `3f1d662`
  (RED, 15 failures) → `c979275` (feat) → docs commit.

## Goal
Make the stack coincide with runtime reality: fix the integration defects that
would break `docker compose up`/CI **today**, do the frontend→API wiring that
the API phase deferred (D1), and author the CI pipeline + HTTP smoke that prove
the running stack matches the 03-api-contracts diagram — verifying **locally
everything this PC can verify for real**, and shipping the rest as executable
artifacts for the CI/host that has Docker.

## Environment findings (verified this session)
| Capability | State |
|---|---|
| Docker on this PC | **ABSENT** — no container runs locally, ever |
| node / npm | **v24.18.0 / 11.16.0 present** — `npm ci`, `next build`, eslint, tsc are REAL-verifiable for the first time |
| Python | 3.14.7 stdlib-only (no pip) — backend stays source-level, as before |
| Frontend | Next **16.0.0** + React **19.0.0**, Tailwind v4, TS 5.3, react-query + zustand + recharts installed (unused), `output: "standalone"` + `/api/:path*` rewrite → backend, 16 mock pages on `mock.ts`/`nav.ts` single sources |
| CI | **No `.github/`** — nothing exists |

### Integration defects found (would break build/CI today)
1. `frontend/Dockerfile` runs `npm ci` but **`package-lock.json` doesn't exist** → build fails.
2. `frontend/Dockerfile` does `COPY --from=builder /app/public ./public` but **`frontend/public/` doesn't exist** → build fails.
3. `package.json` script `"lint": "next lint"` — **removed in Next 16** → `npm run lint` errors.
4. `docker-compose.yml` backend healthcheck runs `python -c "import requests; ..."` — **`requests` is not in requirements.txt** (httpx is) → healthcheck crashes.
5. `voice.py` `/call-completed` is a **TODO stub** — `update_call_transcript(call_id, transcript, ended_at, duration_seconds)` already exists in `postgres.py` (lines 602+), needs the guarded lazy import wired.
6. Risk: `@types/react ^18.2.0` vs `react 19.0.0` pinned — may break `tsc`; surfaced by the real build (either bump types or adjust code).

## Non-Goals (hold the line)
- NO live provider calls on this PC (no keys presented; Deepgram/ElevenLabs/OpenAI round-trips and LiveKit room lifecycle are exercised by the **Linux CI job** behind secrets, and stay marked TODO in-code until secrets exist).
- NO payment-gateway SDK calls (G6-Q5 still open; scaffold unchanged).
- NO backend runtime on this PC (no pip) — the FastAPI app itself runs in Docker/CI only.
- No auth wiring (G6-Q1 later phase).

## Deliverables

### A. Frontend → API wiring (D1 completion)
- New `frontend/src/lib/api.ts` — typed `fetch` client (GET/POST/PATCH) + react-query hooks per domain (calls, clinics, appointments, prescriptions, payments) using `NEXT_PUBLIC_BACKEND_URL` (existing rewrite keeps `/api/...` relative).
- **Mock-fallback strategy (env `NEXT_PUBLIC_USE_MOCK=auto|true|false`, default `auto`)**: SWR-style — fetch the API; on failure/unavailable, fall back to existing `mock.ts` data. Dashboards render offline in dev, hit the real API in prod. Pages swap `@/components/mock` imports → `@/lib/api` hooks (data shapes kept compatible so components barely change).
- `next build` + eslint + tsc run locally = the behavioral proof.

### B. Toolchain / Docker fixes
- Generate + commit `frontend/package-lock.json` (via real `npm install`).
- Add `frontend/public/` (favicon.svg + robots.txt) so the Dockerfile COPY resolves.
- Replace `"lint": "next lint"` with eslint-flat or `eslint .` (config added) — confirm green locally.
- Fix compose backend healthcheck to use a stdlib-safe dependency actually in requirements (httpx) or urllib.
- `voice.py`: wire `/call-completed` → guarded lazy `from app.db.postgres import update_call_transcript` + call (source-tested; only executes when sqlalchemy is importable = Docker runtime).

### C. CI pipeline + smoke (authored here, runs on the Linux runner once a remote exists)
- `.github/workflows/ci.yml` with three jobs:
  1. **backend**: checkout → setup-python 3.12 → pip install -r requirements.txt → run ALL stdlib suites (`tests/test_*.py` + `py_compile`) → `ruff check .`
  2. **frontend**: setup-node 20 → `npm ci` → `npm run lint` → `npm run build`
  3. **stack**: docker compose up -d → wait for health → `python backend/scripts/smoke_api.py` against the compose backend → teardown. (Job 3 runs on `ubuntu-latest`; live-provider secrets block stays explicit.)
- `backend/scripts/smoke_api.py` — **stdlib-only** HTTP smoke covering the 03-api-contracts surface: `/health`, clinics list/create/get/patch, calls list(+state filter)/detail/state-PATCH-409/transcript, appointments + prescriptions + payments list/create/detail + status-PATCH-422, voice `/api/voice` ping (webhook endpoints return 200/json on empty payloads where safe).

### D. Acceptance suite — `backend/tests/test_docker_ci.py` (stdlib, source-level)
Asserts: lockfile exists · `public/` exists · `lint` script ≠ `next lint` · `requests` no longer in healthcheck / replacement dep present in requirements · `voice.py` contains guarded `update_call_transcript` import+call · `ci.yml` has the 3 jobs + names · `smoke_api.py` exists and contains the endpoint paths (`/health`, `/api/clinics`, `/api/calls/{call_id}/state` 409, `/transcript`, status PATCH 422) · no restaurant leftovers in new files.
- RED now (nothing exists) → GREEN after A–C. Regression stays **162/162** + new suite.

## Verify commands (this PC)
```
# real frontend verification (new!)
npm ci && npm run lint && npm run build        # in frontend/, exit 0
python3 tests/test_docker_ci.py                # new suite
python3 tests/test_api_routes.py …             # full regression 162/162
python3 -m py_compile backend/app/api/voice.py
```

## Files touched
- New: `frontend/package-lock.json`, `frontend/public/favicon.svg`, `frontend/public/robots.txt`, `frontend/src/lib/api.ts`, `frontend/eslint.config.{mjs}` (flat) or `.eslintrc`, `.github/workflows/ci.yml`, `backend/scripts/smoke_api.py`, `backend/tests/test_docker_ci.py`.
- Edit: 16 page files (mock → api hooks, ~minimal diff), few components if types demand, `frontend/package.json` (lint script), `docker-compose.yml` (healthcheck), `backend/app/api/voice.py` (transcript wiring), `backend/Dockerfile` (only if smoke needs it — prefer not), tracker + `HANDOVER.md` (DONE record).
- Docs-only corollary: `docs/uml/05-deployment.md` + `03-api-contracts.md` get a one-line "verified by ci.yml/smoke_api.py" pointer if approved (keep diagrams truthful).

## Risks
| Risk | Mitigation |
|---|---|
| React 19 / @types/react 18 type break surfaces in `next build` | Real build now catches it; bump `@types/react` to v19 in the same fix commit |
| No git remote → CI workflow can't run yet | Authored + tested at source level; runtime evidence comes when a remote/host exists (designbox/prostudiox or GitHub remote) |
| Mock-fallback makes API wiring bugs invisible locally | `smoke_api.py` + CI stack job are the real check; source suite asserts the client calls the right endpoints |
| `npm install` churn / node_modules bloat on this PC | `npm ci` from committed lockfile; node_modules gitignored; only the lockfile lands in the commit |

## Decisions for sign-off (this STOP)
- **Q1 — Verification target**: (A) Local-toolchain verify now (real `next build`/lint) + author CI job 3 for the Docker runner (recommended) · (B) B also stand up a remote Docker host NOW (designbox/prostudiox: install docker, request live keys, run the full stack smoke this session — much larger scope) · (C) local only, author no workflow.
- **Q2 — Frontend wiring**: (A) `api.ts` client + react-query hooks + auto mock-fallback across all 16 pages (recommended) · (B) client module + wire only 2 proof pages, rest stays mock · (C) hard wiring, no fallback (blank UI without live backend).
- **Q3 — CI artifact shape**: (A) ci.yml 3 jobs + smoke_api.py + toolchain fixes (recommended) · (B) A + `scripts/docker-up.ps1` (compose up/down/wait + env example) · (C) toolchain fixes only, no workflow yet.