"""Auth Enforcement phase (spec-auth-enforcement.md) — RED contracts.

Tests the enforcement flip WITHOUT a live Postgres (same pattern as test_auth's
schema block): structural AST/text assertions that the guards are wired onto the
5 domain routers, the RLS flip (FORCE + medicall_app role + new policies + demo
seed) is staged in postgres_schema.sql, the GUC plumbing + service bypass exist in
postgres.py, voice webhooks verify a service token, and smoke_api.py authenticates
before any domain call.

RED before implementation (2026-09-25): every assertion here FAILS on g-auth's
current code — routers carry no guards, schema has no medicall_app/FORCE/service
policies/seed, postgres.py has no GUC begin-event, voice.py has no token check,
smoke does domain calls unauthenticated.
"""
import ast
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
API_DIR = BACKEND / "app" / "api"
SCHEMA = BACKEND / "postgres_schema.sql"
POSTGRES = BACKEND / "app" / "db" / "postgres.py"
VOICE = API_DIR / "voice.py"
SMOKE = BACKEND / "scripts" / "smoke_api.py"
COMPOSE = BACKEND.parent / "docker-compose.yml"
ENV_EXAMPLE = BACKEND / ".env.example"

ROUTER_MODULES = ("clinics", "calls", "appointments", "prescriptions", "payments")
TENANT_TABLES = (
    "users",
    "clinics",
    "clinic_users",
    "calls",
    "appointments",
    "prescriptions",
    "payments",
)
AUTH_USER_CRUD = (
    "find_user",
    "create_user",
    "set_user_otp",
    "bump_user_otp_attempts",
    "clear_user_otp",
)
VOICE_WEBHOOKS = ("call_completed", "start_livekit_agent", "exotel_webhook",
                  "knowlarity_webhook", "twilio_webhook")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def fns(tree) -> dict:
    """{name: node} for every function in a module AST."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def router_endpoints(tree) -> dict:
    """{func_name: [(method, path)]} for endpoints decorated with @router.<method>."""
    out = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and getattr(dec.func.value, "id", None) == "router"
                and isinstance(dec.func.attr, str)
                and dec.func.attr in {"get", "post", "patch", "put", "delete"}
            ):
                out.setdefault(node.name, []).append(dec.func.attr)
    return out


def fn_block(text: str, name: str) -> str:
    """The source text of one function (via AST line offsets), or ''.

    Slices by LINE, not by character offset: splitlines(keepends=True) keeps
    each line intact so text[node.lineno-1:node.end_lineno] spans the def line
    down to the function's last line.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    node = fns(tree).get(name)
    if node is None:
        return ""
    lines = text.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno])


def args_reference_guard(node) -> bool:
    """True if the function's parameter list mentions Depends or require_roles.

    The routers use the established untyped form ``user=Depends(get_current_user)``
    (same style as auth.py's /me), so both the annotation and the DEFAULT VALUE
    are inspected — a bare ``user: User`` annotation would not carry the guard.
    """
    if node is None:
        return False
    args = node.args.args
    defaults = [None] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
    for a, d in zip(args, defaults):
        parts = []
        if a.annotation is not None:
            parts.append(ast.unparse(a.annotation))
        if d is not None:
            parts.append(ast.unparse(d))
        for src in parts:
            if "Depends(get_current_user)" in src or "Depends(require_roles" in src or "Depends(require_clinic_role" in src:
                return True
    return False


# ─── Router guard wiring (Q1/A1a) ────────────────────────────────────────────

class TestRouterGuards(unittest.TestCase):
    def test_every_domain_endpoint_requires_auth(self):
        for mod in ROUTER_MODULES:
            text = read(API_DIR / f"{mod}.py")
            tree = ast.parse(text)
            eps = router_endpoints(tree)
            self.assertGreater(len(eps), 0, f"{mod}: no endpoints found")
            for name in eps:
                self.assertTrue(
                    args_reference_guard(fns(tree).get(name)),
                    f"{mod}.{name}: missing Depends(get_current_user)/role guard",
                )

    def test_clinics_create_is_owner_gated(self):
        text = read(API_DIR / "clinics.py")
        tree = ast.parse(text)
        eps = router_endpoints(tree)
        create = [n for n, ms in eps.items() if "post" in ms]
        self.assertEqual(len(create), 1, "clinics: expected exactly one POST endpoint")
        block = fn_block(text, create[0])
        self.assertIn("require_roles", block)
        self.assertIn('"owner"', block)

    def test_routers_import_guards_library(self):
        for mod in ROUTER_MODULES:
            text = read(API_DIR / f"{mod}.py")
            self.assertIn("get_current_user", text, f"{mod}: guard not imported/used")


# ─── Schema: role flip, FORCE, new policies, demo seed (C) ───────────────────

class TestSchemaEnforcement(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCHEMA)

    def test_medicall_app_role_created_with_login(self):
        self.assertIn("CREATE ROLE medicall_app", self.text)
        self.assertIn("LOGIN", self.text.split("CREATE ROLE medicall_app", 1)[1])

    def test_medicall_app_grants_all_tenant_tables(self):
        for table in TENANT_TABLES:
            self.assertIn(f"GRANT ALL ON {table} TO medicall_app", self.text)

    def test_force_row_level_security_on_all_tenant_tables(self):
        for table in TENANT_TABLES:
            self.assertIn(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY", self.text)

    def test_clinic_users_policies_exist(self):
        self.assertIn("clinic_users_own", self.text)
        self.assertIn("clinic_users_manage", self.text)

    def test_clinics_create_insert_policy_exists(self):
        block = self.text.split("CREATE POLICY clinics_create", 1)[1] if "CREATE POLICY clinics_create" in self.text else ""
        self.assertIn("FOR INSERT", block)
        self.assertIn("WITH CHECK", block)

    def test_service_request_clause_on_auth_and_calls_policies(self):
        for policy in ("users_own_data", "calls_create", "calls_read", "calls_update"):
            block = self.text.split(f"CREATE POLICY {policy}", 1)[1].split("CREATE POLICY", 1)[0]
            self.assertIn("app.service_request", block, f"{policy}: missing service bypass")

    def test_demo_tenant_seed_present(self):
        self.assertIn("demo@medicall.in", self.text)
        self.assertIn("+919876543210", self.text)
        self.assertIn("ON CONFLICT DO NOTHING", self.text)

    def test_demo_owner_seeded_with_global_owner_role(self):
        # The demo user INSERT carries role 'owner' so clinics_create's WITH CHECK
        # and POST /api/clinics' require_roles('owner') gate both admit it.
        seed_block = self.text.split("demo@medicall.in", 1)[1] if "demo@medicall.in" in self.text else ""
        self.assertIn("'owner'", seed_block)

    def test_existing_policies_preserved(self):
        for policy in ("payments_manage", "appointments_manage", "prescriptions_manage"):
            self.assertIn(f"CREATE POLICY {policy}", self.text)


# ─── GUC plumbing + service bypass + create_clinic ownership (B/D) ───────────

class TestGucPlumbing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(POSTGRES)

    def test_begin_event_listener_sets_gucs(self):
        self.assertIn('event.listens_for(engine.sync_engine, "begin")', self.text)
        self.assertIn("SET LOCAL app.current_user_id", self.text)
        self.assertIn("SET LOCAL app.service_request", self.text)

    def test_contextvars_defined(self):
        self.assertIn("ContextVar", self.text)
        self.assertIn("current_user_id", self.text)
        self.assertIn("service_request", self.text)

    def test_auth_user_crud_arms_service_bypass(self):
        for fn in AUTH_USER_CRUD:
            block = fn_block(self.text, fn)
            self.assertIn("service_request", block, f"{fn}: service bypass not armed")

    def test_create_clinic_creates_owner_membership(self):
        block = fn_block(self.text, "create_clinic")
        self.assertIn("ClinicUser", block)
        self.assertIn("owner", block)


# ─── Voice webhooks verify a service token (E/Q2) ────────────────────────────

class TestVoiceServiceToken(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(VOICE)

    def test_webhook_secret_env_defined(self):
        self.assertIn("WEBHOOK_SERVICE_TOKEN", self.text)

    def test_all_webhook_endpoints_verify_token(self):
        for name in VOICE_WEBHOOKS:
            block = fn_block(self.text, name)
            self.assertTrue(
                "_verify_service_token" in block or "WEBHOOK_SERVICE_TOKEN" in block,
                f"{name}: no service-token check",
            )


# ─── smoke_api.py authenticates before domain calls (F) ──────────────────────

class TestSmokeAuthenticatesFirst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SMOKE)

    def test_login_before_first_domain_call(self):
        create = self.text.find("POST", self.text.find("/api/clinics"))
        login = self.text.find("/api/auth/login")
        self.assertGreater(login, 0, "smoke: no /api/auth/login")
        self.assertLess(login, create, "smoke: domain call before login")

    def test_domain_calls_carry_bearer(self):
        self.assertIn("Bearer", self.text)
        self.assertIn("Authorization", self.text)

    def test_call_completed_sends_service_token(self):
        self.assertIn("X-Service-Token", self.text)

    def test_new_negative_checks_present(self):
        self.assertIn("401", self.text)  # unauth domain call rejected
        self.assertIn("403", self.text)  # staff cannot create a clinic


# ─── compose + .env.example run as medicall_app (G) ──────────────────────────

class TestComposeAppRole(unittest.TestCase):
    def test_backend_connects_as_medicall_app(self):
        text = read(COMPOSE)
        self.assertIn("medicall_app", text)

    def test_webhook_token_env_wired(self):
        for text in (read(COMPOSE), read(ENV_EXAMPLE)):
            self.assertIn("WEBHOOK_SERVICE_TOKEN", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)