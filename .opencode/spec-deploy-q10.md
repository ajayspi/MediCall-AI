# SPEC: G6-Q10 — Deploy Topology (last open G6 question)

## Goal

Answer the last open idea-refinement item (tracker line 59): the deployment topology —
compose service list (postgres+pgvector, redis?, backend, frontend?), the
Railway/Vercel realization of the `DATA_RESIDENCY_REGION="in"` pin, and the final env
var list. Also close the Q2-deferred retention-purge schedule ("Docker/CI cron").

## §0 Sign-off Record (2026-09-25, question tool — all four answered)

| **Status** | DRAFT → APPROVED (signed off 2026-09-25, question tool, Q1=A1 Q2=A1 Q3=A2 Q4=A3) → **GREEN** (implemented 2026-09-25; regression **561/561** = 519 + 42, compileall 0; RED `ac9c571` → feat `1f1411c` → docs) | |
| Q | Choice | Meaning |
|---|--------|---------|
| Q1 | **A1 — Drop redis from compose** | Remove the `redis` service, `redis-data` volume, and `REDIS_URL` from docker-compose.yml + 05-deployment; keep `backend/app/db/redis.py` and the `redis==5.0.1` pin as a documented future-cache stub (zero callers today). Stack = postgres+pgvector, backend, frontend. |
| Q2 | **A1 — Single root-context Dockerfile** | Rewrite `backend/Dockerfile` to root-context COPYs (`COPY backend/…`); compose builds with `context: .` + `dockerfile: backend/Dockerfile`; add root `.dockerignore` (+ `frontend/.dockerignore`) so both compose and Railway (root build context) work from ONE file. |
| Q3 | **A2 — Railway asia-southeast1 (nearest managed)** | RESEARCH: Railway has NO Mumbai region today (4 Metal regions: `us-west2`, `us-east4-eqdc4a`, `europe-west4-drams3a`, `asia-southeast1-eqsg3a`; region select Pro-plan only; docs.railway.com/deployments/regions, fetched 2026-09-25). Vercel `bom1` (Mumbai) stays pinned for the frontend (vercel.json). Backend + Postgres live on Railway Singapore; the `DATA_RESIDENCY_REGION="in"` pin is realized as the **documented posture "nearest-available"** + zero-retention BAA notes (data physically in Singapore — user's informed choice; NOT in-country). |
| Q4 | **A3 — Full phase + railway.json** | Compose fixes + `scripts/purge_expired.py` + GitHub Actions scheduled purge (daily 03:00 UTC + `workflow_dispatch`) + env var catalog doc (`docs/DEPLOYMENT.md`) + 05-deployment update + `railway.json` (schema-valid; config-as-code is DEPRECATED by Railway — legacy support to 2026-12-01, IaC migration note documented, plugin + secrets via dashboard/CLI). |

## Scope (implementation)

1. `docker-compose.yml`: drop redis service/volume/`REDIS_URL`; backend
   `DATABASE_URL` → `postgresql+asyncpg://medicall_app:…` (create_async_engine
   rejects the non-async scheme — would have broken the stack job at runtime);
   backend build `context: .` + `dockerfile: backend/Dockerfile`; add the DPDP env
   block (`DATA_RESIDENCY_REGION=in` pinned, `DPDP_BREACH_NOTIFICATION_HOURS`,
   `RETENTION_{CALLS,RECORDINGS,NOTIFICATIONS,AUDIT}_DAYS`, `DPO_NAME`, `DPO_EMAIL`
   passthrough). Healthchecks untouched (httpx).
2. `backend/Dockerfile`: root-context rewrite (`COPY backend/requirements.txt` +
   `COPY backend/ ./`); keep `python:3.12-slim` (matches pinned asyncpg==0.29.0
   wheels + ci.yml python 3.12; local `py -3.14.7` dev toolchain is independent).
3. `.dockerignore` (root) + `frontend/.dockerignore`: exclude node_modules/.git/
   .next/.venv/__pycache__/.env (keep `.env.example` via `!.env.example`).
4. `railway.toml`: add `[deploy] region = "asia-southeast1"` + DPDP defaults to
   `[env]`. `railway.json` (new): schema-valid ($schema URL), build =
   DOCKERFILE/backend/Dockerfile, deploy = healthcheck `/health` + timeout 300 +
   ON_FAILURE retries 10 + `region: "asia-southeast1"` (the config-as-code region
   pin). NO `services` array (unsupported by the schema — Postgres plugin via
   dashboard/`railway add`).
5. `backend/scripts/purge_expired.py`: one-shot purger — iterates
   `retention_categories()`, calls `app.db.postgres.purge_expired` per kind under
   `asyncpg`, prints per-kind deleted counts (recordings = external objects, no
   rows; env `RETENTION_*` overrides honored). Runs in the backend image or on a
   host with deps; never auto-runs on import.
6. `.github/workflows/purge.yml`: scheduled daily `03:00 UTC` (`cron`,
   `workflow_dispatch`) → `docker compose run --rm backend
   python scripts/purge_expired.py`.
7. `docs/DEPLOYMENT.md` (new): runbook — compose bring-up, Railway steps
   (asia-southeast1, Postgres plugin, secrets to dashboard), Vercel bom1,
   **the full env var catalog** (every key from `backend/.env.example`, grouped,
   with config source + secret flags), region note (nearest-available + BAA),
   purge, config-as-code deprecation note.
8. `docs/uml/05-deployment.md`: no redis node; DPDP/region/env-contract updates.
9. `backend/.env.example`: DPDP comment lines "…is the Q10 deploy-topology
   session's job" → resolved wording; Redis section `REDIS_URL` → the two
   `UPSTASH_REDIS_REST_*` vars redis.py actually reads (stub, no callers —
   documented).
10. `.github/workflows/ci.yml`: stack step name reworded without redis.
11. `NOTION_PROJECT.md`: env line swap (REDIS_URL → UPSTASH pair) in the local-dev block.
12. `HANDOVER.md` + tracker: Q10 DONE record, G6 fully answered, gotchas.

## Non-Goals

- No live provider round-trips / real cloud provisioning from this PC (no creds;
  runs go to a Docker host / Railway/Vercel dashboards later). Same caveat as prior
  phases: the ci.yml stack job remains the runtime proof (authored, not run here —
  no Docker on this PC).
- No alembic migrations this phase: `init_db` = create_all (dev/test only,
  postgres.py:1646); prod schema path stays `postgres_schema.sql` (compose initdb
  mount / psql at provision). `alembic` pin stays aspirational.
- No frontend code changes; no new API endpoints; no `purge` API endpoint (ops-only
  script + schedule).

## Acceptance Criteria

- `backend/tests/test_deploy_q10.py` GREEN (source-assertion suite, stdlib only).
- Full regression: 519 prior + new suite ALL PASS via `py -3.14 -m unittest`;
  `compileall -q app scripts tests main.py` exit 0.
- `docker compose config` would validate (can't run Docker here — text-pinned).
- Every env var key in `backend/.env.example` appears in `docs/DEPLOYMENT.md`.
- `railway.json` parses; `vercel.json` still pins `bom1`; `DATA_RESIDENCY_REGION=in`
  in compose + railway.toml; `asia-southeast1` in railway.toml + railway.json +
  DEPLOYMENT.md; purge scheduled at 03:00 UTC.

## Risks

| Risk | Mitigation |
|------|------------|
| Compose/CI runtime still unverifiable locally (no Docker) | Text-pinned RED suite + ci.yml stack job remains the runtime proof; fixes target defects the stack job WOULD have caught (+asyncpg scheme, root-context COPYs) |
| Railway config-as-code deprecated (2026-12-01) | DEPLOYMENT.md migration note to Railway IaC/Public API; region pin also in toml + docs; Postgres/secrets are dashboard-side anyway |
| "nearest-available" ≠ in-country data | User chose A2 knowingly; BAA + posture notes in DEPLOYMENT.md + compliance.py stays the documented posture |
| 05-deployment legacy claims (redis) drift | RED suite asserts zero redis mentions; env contract line updated |