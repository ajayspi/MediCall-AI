"""G6-Q10 deploy-topology acceptance tests (stdlib only).

RED before implementation (2026-09-25, spec-deploy-q10.md — sign-off Q1=A1 drop
redis, Q2=A1 single root-context Dockerfile, Q3=A2 Railway asia-southeast1
nearest-available + Vercel bom1, Q4=A3 full phase + railway.json). Defects the
suite pins: compose still runs a vestigial redis service + passes a non-async
DATABASE_URL scheme + passes ZERO DPDP env vars; backend/Dockerfile COPYs are
subdir-context (railway.toml builds from the repo ROOT — would fail on Railway);
no .dockerignore; no purge script / schedule (Q2 deferred item); no env catalog
doc; railway.toml/railway.json carry no region pin; .env.example still says the
region pin "is the Q10 … session's job" and documents REDIS_URL against a
client that reads UPSTASH_REDIS_REST_*; ci.yml + 05-deployment still claim redis.

GREEN after implementation: compose = postgres+pgvector / backend / frontend only,
DATABASE_URL has the +asyncpg scheme, DPDP block incl DATA_RESIDENCY_REGION=in;
backend/Dockerfile COPYs from the root context; root + frontend .dockerignore
exist; purge_expired.py + .github/workflows/purge.yml (03:00 UTC + dispatch);
docs/DEPLOYMENT.md env catalog covers EVERY backend/.env.example key + region
notes (asia-southeast1 / nearest-available / bom1 / BAA); railway.toml +
railway.json pin region + DPDP defaults; .env.example uses UPSTASH_REDIS_REST_*
and the Q10 wiring wording; ci.yml + 05-deployment have zero redis mentions.

Run: python3 tests/test_deploy_q10.py  (exit 0 = green)
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

COMPOSE = ROOT / "docker-compose.yml"
BACKEND_DF = BACKEND / "Dockerfile"
ROOT_DOCKERIGNORE = ROOT / ".dockerignore"
FRONTEND_DOCKERIGNORE = FRONTEND / ".dockerignore"
RAILWAY_TOML = ROOT / "railway.toml"
RAILWAY_JSON = ROOT / "railway.json"
PURGE_SCRIPT = BACKEND / "scripts" / "purge_expired.py"
PURGE_WORKFLOW = ROOT / ".github" / "workflows" / "purge.yml"
DEPLOY_DOC = ROOT / "docs" / "DEPLOYMENT.md"
ENV_EXAMPLE = BACKEND / ".env.example"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_05 = ROOT / "docs" / "uml" / "05-deployment.md"

DPDP_VARS = (
    "DATA_RESIDENCY_REGION",
    "DPDP_BREACH_NOTIFICATION_HOURS",
    "RETENTION_CALLS_DAYS",
    "RETENTION_RECORDINGS_DAYS",
    "RETENTION_NOTIFICATIONS_DAYS",
    "RETENTION_AUDIT_DAYS",
    "DPO_NAME",
    "DPO_EMAIL",
)

ENV_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)\s*=", re.M)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def read_json(path: Path):
    try:
        return json.loads(read(path))
    except (json.JSONDecodeError, ValueError):
        return {}


def service_block(name: str, text: str) -> str:
    """The compose service block for `name` (lines between its header and the next)."""
    start = re.search(rf"^\s{{2}}{name}:\s*$", text, re.M)
    if not start:
        return ""
    nxt = re.search(rf"^\s{{2}}[a-z_]+:\s*$", text[start.end():], re.M)
    return text[start.start(): start.end() + (nxt.start() if nxt else len(text) - start.end())]


class TestComposeServices(unittest.TestCase):
    def setUp(self):
        self.text = read(COMPOSE)

    def test_postgres_backend_frontend_present(self):
        for name in ("postgres", "backend", "frontend"):
            self.assertTrue(
                re.search(rf"^\s{{2}}{name}:\s*$", self.text, re.M),
                f"compose missing service {name!r}",
            )

    def test_redis_service_absent(self):
        self.assertIsNone(
            re.search(r"^\s{2}redis:\s*$", self.text, re.M), "redis service must be gone"
        )

    def test_redis_url_absent(self):
        self.assertNotIn("REDIS_URL", self.text)

    def test_redis_data_volume_absent(self):
        self.assertNotIn("redis-data", self.text)

    def test_database_url_asyncpg_scheme(self):
        self.assertIn(
            "postgresql+asyncpg://medicall_app:medicall_app@postgres:5432/medicall",
            self.text,
            "backend DATABASE_URL must carry the +asyncpg scheme (async engine)",
        )

    def test_dpdp_region_pin_pinned(self):
        self.assertIn("DATA_RESIDENCY_REGION=in", self.text)

    def test_dpdp_env_passthrough(self):
        for var in DPDP_VARS:
            self.assertIn(var, self.text, f"compose missing DPDP env {var}")

    def test_backend_build_root_context(self):
        block = service_block("backend", self.text)
        self.assertTrue(
            re.search(r"^\s+context: \.\s*$", block, re.M),
            "backend build context must be the repo root (exact `.` line)",
        )
        self.assertIn("dockerfile: backend/Dockerfile", block)


class TestBackendDockerfile(unittest.TestCase):
    def setUp(self):
        self.text = read(BACKEND_DF)

    def test_root_context_requirements_copy(self):
        self.assertIn("COPY backend/requirements.txt ./requirements.txt", self.text)

    def test_root_context_app_copy(self):
        self.assertIn("COPY backend/ ./", self.text)

    def test_no_subdir_context_copies_left(self):
        self.assertNotIn("COPY requirements.txt .", self.text)
        self.assertNotIn("COPY . .", self.text)

    def test_python_312_image(self):
        self.assertIn("FROM python:3.12-slim", self.text)


class TestDockerignore(unittest.TestCase):
    def test_root_dockerignore_exists_and_excludes(self):
        text = read(ROOT_DOCKERIGNORE)
        self.assertTrue(text, "root .dockerignore missing")
        for token in ("node_modules", ".git", ".next", ".venv", "__pycache__", ".env"):
            self.assertIn(token, text, f".dockerignore missing {token!r}")

    def test_root_keeps_env_example(self):
        text = read(ROOT_DOCKERIGNORE)
        self.assertIn("!.env.example", text, ".env.example must survive the root build context")

    def test_frontend_dockerignore(self):
        text = read(FRONTEND_DOCKERIGNORE)
        self.assertTrue(text, "frontend/.dockerignore missing")
        for token in ("node_modules", ".next"):
            self.assertIn(token, text, f"frontend/.dockerignore missing {token!r}")


class TestRailway(unittest.TestCase):
    def test_railway_toml_region_pin(self):
        text = read(RAILWAY_TOML)
        self.assertIn("asia-southeast1", text, "railway.toml must pin deploy.region")

    def test_railway_toml_dpdp_region_default(self):
        text = read(RAILWAY_TOML)
        self.assertIn('DATA_RESIDENCY_REGION = "in"', text)

    def test_railway_json_valid_and_pinned(self):
        cfg = read_json(RAILWAY_JSON)
        self.assertIn("$schema", cfg)
        self.assertEqual(cfg.get("$schema"), "https://railway.com/railway.schema.json")
        build = cfg.get("build") or {}
        self.assertEqual(build.get("builder"), "DOCKERFILE")
        self.assertEqual(build.get("dockerfilePath"), "backend/Dockerfile")
        deploy = cfg.get("deploy") or {}
        self.assertEqual(deploy.get("region"), "asia-southeast1")
        self.assertEqual(deploy.get("healthcheckPath"), "/health")
        self.assertEqual(deploy.get("restartPolicyType"), "ON_FAILURE")

    def test_railway_json_no_services_array(self):
        self.assertTrue(RAILWAY_JSON.is_file(), "railway.json must exist")
        cfg = read_json(RAILWAY_JSON)
        self.assertNotIn("services", cfg, "config-as-code schema has no top-level services[]")


class TestPurgeScript(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue(PURGE_SCRIPT.is_file(), "backend/scripts/purge_expired.py missing")

    def test_imports_purge_expired(self):
        text = read(PURGE_SCRIPT)
        self.assertIn("from app.db.postgres import purge_expired", text)

    def test_iterates_retention_categories(self):
        text = read(PURGE_SCRIPT)
        self.assertIn("retention_categories", text)

    def test_calls_purge_per_kind(self):
        text = read(PURGE_SCRIPT)
        self.assertIn("purge_expired(", text)
        self.assertIn("recordings", text, "recordings = external objects must be noted")

    def test_main_guard(self):
        text = read(PURGE_SCRIPT)
        self.assertIn('if __name__ == "__main__":', text)


class TestPurgeWorkflow(unittest.TestCase):
    def setUp(self):
        self.text = read(PURGE_WORKFLOW)

    def test_workflow_exists(self):
        self.assertTrue(self.text, ".github/workflows/purge.yml missing")

    def test_scheduled_0300_utc(self):
        self.assertIn("schedule:", self.text)
        self.assertIn("03:00", self.text)

    def test_manual_dispatch(self):
        self.assertIn("workflow_dispatch", self.text)

    def test_runs_compose_purge(self):
        self.assertIn("docker compose run --rm backend", self.text)
        self.assertIn("scripts/purge_expired.py", self.text)


class TestDeploymentDoc(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DEPLOY_DOC.is_file(), "docs/DEPLOYMENT.md missing")

    def test_env_catalog_covers_every_env_example_key(self):
        env_keys = set(ENV_KEY_RE.findall(read(ENV_EXAMPLE)))
        self.assertTrue(env_keys, ".env.example keys not parseable")
        doc = read(DEPLOY_DOC)
        missing = sorted(k for k in env_keys if k not in doc)
        self.assertEqual(missing, [], f"DEPLOYMENT.md catalog missing: {missing}")

    def test_secret_flags_present(self):
        doc = read(DEPLOY_DOC)
        self.assertIn("Secret", doc, "catalog must flag secrets")

    def test_region_notes(self):
        doc = read(DEPLOY_DOC)
        for token in ("asia-southeast1", "nearest-available", "bom1", "BAA"):
            self.assertIn(token, doc, f"DEPLOYMENT.md missing region note {token!r}")

    def test_region_pin_documented(self):
        doc = read(DEPLOY_DOC)
        self.assertIn("DATA_RESIDENCY_REGION", doc)
        self.assertIn('"in"', doc)

    def test_purge_documented(self):
        doc = read(DEPLOY_DOC)
        self.assertIn("purge_expired", doc)

    def test_compose_services_documented(self):
        doc = read(DEPLOY_DOC)
        for token in ("postgres", "backend", "frontend", "pgvector"):
            self.assertIn(token, doc, f"DEPLOYMENT.md missing service {token!r}")


class TestEnvExample(unittest.TestCase):
    def setUp(self):
        self.text = read(ENV_EXAMPLE)

    def test_upstash_vars_documented(self):
        self.assertIn("UPSTASH_REDIS_REST_URL", self.text)
        self.assertIn("UPSTASH_REDIS_REST_TOKEN", self.text)

    def test_redis_url_gone(self):
        self.assertNotIn("REDIS_URL", self.text)

    def test_q10_stale_wording_gone(self):
        self.assertNotIn("is the Q10", self.text, "region-pin comment still says Q10 owns it")

    def test_q10_resolution_documented(self):
        self.assertIn("asia-southeast1", self.text)


class TestCiWorkflow(unittest.TestCase):
    def test_stack_step_has_no_redis(self):
        text = read(CI_WORKFLOW)
        self.assertNotIn("redis", text.lower(), "ci.yml still names redis in the stack")


class TestDeploymentDiagram(unittest.TestCase):
    def setUp(self):
        self.text = read(DEPLOY_05)

    def test_no_redis_mention(self):
        self.assertNotIn("redis", self.text.lower(), "05-deployment still shows redis")

    def test_region_and_env_contract(self):
        for token in ("DATA_RESIDENCY_REGION", "asia-southeast1", "bom1", "DATABASE_URL"):
            self.assertIn(token, self.text, f"05-deployment missing {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)