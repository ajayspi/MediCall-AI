"""Docker/CI integration stage acceptance tests (stdlib only).

RED before implementation (2026-09-25, spec-docker-ci.md Q1/Q2/Q3 approved:
local-toolchain verify + author CI; client module + 2 proof pages; 3-job
ci.yml + HTTP smoke + toolchain fixes): integration defects present —
no frontend/package-lock.json (frontend Dockerfile's `npm ci` cannot run), no
frontend/public/ (its COPY fails), package.json `lint` = removed `next lint`,
compose backend healthcheck imports `requests` (not in requirements),
voice.py /call-completed is a TODO stub, no .github/ workflow, no api client,
no smoke script.

GREEN after implementation:
- frontend/package-lock.json committed; frontend/public/ exists (favicon +
  robots) so the Dockerfile COPY resolves.
- package.json lint script is eslint-based (not `next lint`).
- docker-compose.yml backend healthcheck needs no `requests` (uses httpx).
- voice.py call_completed wires the guarded lazy import + call of
  update_call_transcript (TODO comment gone from that handler).
- .github/workflows/ci.yml exists with backend / frontend / stack jobs
  (stack = docker compose up + backend/scripts/smoke_api.py + teardown).
- backend/scripts/smoke_api.py: stdlib (urllib) HTTP smoke of the
  03-api-contracts surface (/health, clinics CRUD, calls list/detail/state-
  409/transcript, appointments/prescriptions/payments status-PATCH 422).
- frontend/src/lib/api.ts: typed fetch client + react-query hooks with
  NEXT_PUBLIC_USE_MOCK fallback; the 2 proof pages (live-calls, dashboard)
  import it; the other 14 pages stay on mock.
- No restaurant/TalkByte leftovers in any new file.

Run: python3 tests/test_docker_ci.py  (exit 0 = green)
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

LOCKFILE = FRONTEND / "package-lock.json"
PUBLIC_DIR = FRONTEND / "public"
PACKAGE_JSON = FRONTEND / "package.json"
COMPOSE = ROOT / "docker-compose.yml"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
VOICE = BACKEND / "app" / "api" / "voice.py"
SMOKE = BACKEND / "scripts" / "smoke_api.py"
API_CLIENT = FRONTEND / "src" / "lib" / "api.ts"

PROOF_PAGES = (
    FRONTEND / "src" / "app" / "(clinic)" / "live-calls" / "page.tsx",
    FRONTEND / "src" / "app" / "(clinic)" / "dashboard" / "page.tsx",
)

SMOKE_ENDPOINTS = (
    "/health",
    "/api/clinics",
    "/api/calls",
    "/api/calls/{call_id}/state",
    "/api/calls/{call_id}/transcript",
    "/api/appointments",
    "/api/appointments/{appointment_id}/status",
    "/api/prescriptions/{prescription_id}/status",
    "/api/payments/{payment_id}/status",
)

RESTAURANT_LEFTOVERS = (
    "talkbyte",
    "mama's",
    "margherita",
    "ord-0",
    "australia",
    "telnyx",
    "square",
    "stripe",
    "restaurant",
)

NEW_FILES = (CI_WORKFLOW, SMOKE, API_CLIENT, PUBLIC_DIR / "favicon.svg", PUBLIC_DIR / "robots.txt")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def read_json(path: Path):
    try:
        return json.loads(read(path))
    except (json.JSONDecodeError, ValueError):
        return {}


class TestFrontendToolchain(unittest.TestCase):
    def test_lockfile_committed(self):
        self.assertTrue(LOCKFILE.is_file(), "frontend/package-lock.json missing (npm ci needs it)")
        pkg = read_json(LOCKFILE)
        self.assertIn("lockfileVersion", pkg, "package-lock.json is not a lockfile")

    def test_public_dir_with_assets(self):
        self.assertTrue(PUBLIC_DIR.is_dir(), "frontend/public/ missing (Dockerfile COPY needs it)")
        self.assertTrue((PUBLIC_DIR / "favicon.svg").is_file(), "public/favicon.svg missing")
        self.assertTrue((PUBLIC_DIR / "robots.txt").is_file(), "public/robots.txt missing")

    def test_lint_script_is_eslint_not_next_lint(self):
        pkg = read_json(PACKAGE_JSON)
        lint = (pkg.get("scripts") or {}).get("lint", "")
        self.assertTrue(lint, "package.json has no lint script")
        self.assertIn("eslint", lint.lower(), f"lint script must be eslint-based, got: {lint!r}")
        self.assertNotIn("next lint", lint.lower(), "`next lint` was removed in Next 16")


class TestComposeHealthcheck(unittest.TestCase):
    def test_backend_healthcheck_needs_no_requests(self):
        text = read(COMPOSE)
        m = re.search(r"healthcheck:.*?(?=\n\s{4}[a-z_]+:|\Z)", text, re.S)
        self.assertTrue(m, "backend healthcheck block not found in docker-compose.yml")
        block = m.group(0)
        self.assertNotIn("import requests", block, "healthcheck must not rely on `requests`")
        self.assertIn("httpx", block, "healthcheck should use httpx (already in requirements.txt)")

    def test_healthcheck_dependency_in_requirements(self):
        reqs = read(BACKEND / "requirements.txt")
        self.assertIn("httpx", reqs, "httpx must stay in requirements.txt for the healthcheck")


class TestTranscriptWiring(unittest.TestCase):
    def test_call_completed_wires_update_call_transcript(self):
        text = read(VOICE)
        self.assertIn("from app.db.postgres import update_call_transcript", text)
        self.assertIn("await update_call_transcript(", text)

    def test_call_completed_has_no_todo_stub(self):
        text = read(VOICE)
        start = text.find("async def call_completed")
        self.assertGreaterEqual(start, 0, "call_completed handler missing")
        handler = text[start:]
        self.assertNotIn("TODO(Docker/CI)", handler, "call_completed should be wired, not stubbed")


class TestCIWorkflow(unittest.TestCase):
    def test_workflow_exists(self):
        self.assertTrue(CI_WORKFLOW.is_file(), ".github/workflows/ci.yml missing")

    def test_three_jobs_present(self):
        text = read(CI_WORKFLOW)
        for job in ("backend", "frontend", "stack"):
            self.assertIn(job, text, f"ci.yml missing job {job!r}")

    def test_jobs_have_expected_steps(self):
        text = read(CI_WORKFLOW)
        for step in ("setup-python", "python3 tests/", "py_compile", "ruff check ", "npm ci", "npm run build", "docker compose up", "smoke_api.py", "docker compose down"):
            self.assertIn(step, text, f"ci.yml missing step {step!r}")


class TestSmokeScript(unittest.TestCase):
    def test_stdlib_only(self):
        text = read(SMOKE)
        self.assertIn("urllib", text, "smoke_api.py must be stdlib (urllib) — no third-party imports")
        for banned in ("import requests", "from fastapi", "import httpx"):
            self.assertNotIn(banned, text, f"smoke_api.py must not use {banned}")

    def test_endpoint_surface_covered(self):
        text = read(SMOKE)
        for ep in SMOKE_ENDPOINTS:
            self.assertIn(ep, text, f"smoke_api.py missing endpoint {ep}")

    def test_status_code_checks(self):
        text = read(SMOKE)
        for code, label in (("409", "invalid transition"), ("422", "invalid status"), ("404", "missing row")):
            self.assertIn(code, text, f"smoke_api.py missing {code} check")
            self.assertIn(label, text.lower(), f"smoke_api.py missing explanation for {code}")

    def test_url_base_configurable(self):
        text = read(SMOKE)
        self.assertIn("BASE_URL", text, "smoke_api.py should take a BASE_URL (env or argv)")


class TestApiClient(unittest.TestCase):
    def test_client_module_exists(self):
        text = read(API_CLIENT)
        self.assertIn("fetch", text, "api.ts must use fetch")
        self.assertIn("useQuery", text, "api.ts must expose react-query hooks")
        self.assertIn("NEXT_PUBLIC_USE_MOCK", text, "api.ts must honor NEXT_PUBLIC_USE_MOCK fallback")

    def test_two_proof_pages_import_client(self):
        for page in PROOF_PAGES:
            text = read(page)
            self.assertIn("@/lib/api", text, f"{page.name} must import the api client")

    def test_hooks_cover_calls_domain(self):
        text = read(API_CLIENT)
        self.assertIn("useCalls", text, "api.ts must expose useCalls for the proof pages")


class TestNoLeftovers(unittest.TestCase):
    def test_new_files_clean(self):
        for path in NEW_FILES:
            low = read(path).lower()
            for token in RESTAURANT_LEFTOVERS:
                self.assertNotIn(token, low, f"{path.name} contains leftover {token!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)