"""G6-Q11 Frontend wiring + platform admin — RED contracts (stdlib only).

RED before implementation (2026-09-26, spec-frontend-wiring-q11.md, scope A3
signed via question tool): the UI is only 30% live — `(clinic)` triage-queue /
appointments / prescriptions / analytics / patients and `admin` overview /
live-monitor / clinics / patients / revenue all render `components/mock`
fixtures; there is NO `/api/admin` router (main.py includes 10 routers, the
tenth is analytics); `services/auth.py` ROLES has no `platform_admin`;
`postgres_schema.sql` clinic_staff_read has no app.service_request OR-clause
and the demo seed has no operator account; `src/lib/api.ts` has no per-domain
hooks (only useCalls/useTodayCalls).

GREEN after implementation (same spec):
- main.py includes ELEVEN routers — {voice, auth, clinics, calls, appointments,
  prescriptions, payments, notifications, compliance, analytics, admin}.
- app/api/admin.py (new, 11th router): prefix "/api/admin", EXACTLY 5 GET
  endpoints ("" overview, /clinics, /patients, /revenue, /calls), every one
  gated by Depends(require_roles("platform_admin")).
- app/db/postgres.py: 5 new RLS-riding platform aggregates (platform_overview,
  platform_clinics, platform_patients, platform_revenue, platform_calls), each
  arming app.service_request via service_request_ctx() internally (the
  auth-CRUD pattern) so the platform views read across tenants.
- services/auth.py: platform_admin added to ROLES with ROLE_WEIGHTS 6 (above
  owner=5); postgres_schema.sql: clinic_staff_read FOR SELECT gains the
  app.service_request OR-clause + demo seed gains platform@medicall.in.
- src/lib/api.ts: authFetch + ApiAppointment/ApiPrescription/ApiAdmin* types +
  clinic hooks (useAppointments, usePrescriptions, useAnalyticsKpis,
  useRecentCallers) + admin hooks (useAdminOverview, useAdminClinics,
  useAdminPatients, useAdminRevenue, useAdminLiveCalls); USE_MOCK auto/true/
  false semantics identical to useTodayCalls; admin hooks are platform-scoped
  (no clinic_id query param).
- 10 pages convert from mock to @/lib/api: (clinic)/triage-queue, appointments,
  prescriptions, analytics, patients + admin/page, live-monitor, clinics,
  patients, revenue. The 4 entity-less admin pages (doctors, billing,
  infrastructure, audit) STAY on mock with a documented "no backend entity"
  note; components/mock.ts keeps its +91/₹ fixtures.

Run: python3 tests/test_frontend_wiring_q11.py  (exit 0 = green)
"""
import ast
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
API_DIR = BACKEND / "app" / "api"
DB_DIR = BACKEND / "app" / "db"
SERVICES_DIR = BACKEND / "app" / "services"
MAIN = BACKEND / "main.py"
SCHEMA = BACKEND / "postgres_schema.sql"

SRC = ROOT / "frontend" / "src"
LIB = SRC / "lib"
COMPONENTS = SRC / "components"
CLINIC_APP = SRC / "app" / "(clinic)"
ADMIN_APP = SRC / "app" / "admin"

ADMIN_ROUTER = API_DIR / "admin.py"
AUTH_SVC = SERVICES_DIR / "auth.py"
POSTGRES = DB_DIR / "postgres.py"
API_TS = LIB / "api.ts"
MOCK_TS = COMPONENTS / "mock.ts"

KNOWN_ROUTERS = {
    "voice", "auth", "clinics", "calls", "appointments", "prescriptions",
    "payments", "notifications", "compliance", "analytics",
}

ADMIN_ENDPOINTS = {
    ("get", ""),
    ("get", "/clinics"),
    ("get", "/patients"),
    ("get", "/revenue"),
    ("get", "/calls"),
}

PLATFORM_FNS = (
    "platform_overview",
    "platform_clinics",
    "platform_patients",
    "platform_revenue",
    "platform_calls",
)

ANALYTICS_ENDPOINTS = (
    "/api/analytics/volume", "/api/analytics/resolution", "/api/analytics/triage",
    "/api/analytics/language", "/api/analytics/no-show", "/api/analytics/revenue",
    "/api/analytics/delivery", "/api/analytics/benchmarks",
)

CLINIC_NEW_ENDPOINTS = ("/api/appointments", "/api/prescriptions") + ANALYTICS_ENDPOINTS
ADMIN_ENDPOINT_PATHS = ("/api/admin", "/api/admin/clinics", "/api/admin/patients",
                        "/api/admin/revenue", "/api/admin/calls")

CLINIC_NEW_HOOKS = ("useAppointments", "usePrescriptions", "useAnalyticsKpis",
                    "useRecentCallers")
ADMIN_NEW_HOOKS = ("useAdminOverview", "useAdminClinics", "useAdminPatients",
                   "useAdminRevenue", "useAdminLiveCalls")

# page subdir under (clinic)/ or admin/; "" means the index page (admin/page.tsx)
CLINIC_WIRED = ("triage-queue", "appointments", "prescriptions", "analytics", "patients")
ADMIN_WIRED = ("", "live-monitor", "clinics", "patients", "revenue")
ADMIN_UNWIRED = ("doctors", "billing", "infrastructure", "audit")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def py_tree(path: Path):
    text = read(path)
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def router_objects(tree) -> dict:
    """{name: prefix} for `name = APIRouter(prefix=..., tags=...)` assignments."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and getattr(node.value.func, "id", None) == "APIRouter"
        ):
            prefix = None
            for kw in node.value.keywords:
                if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                    prefix = kw.value.value
            out[node.targets[0].id] = prefix
    return out


def endpoint_paths(tree) -> set:
    """{(method, path)} from `@router.<method>("<path>")` decorators."""
    out = set()
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in {"get", "post", "patch", "put", "delete"}
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                out.add((dec.func.attr, dec.args[0].value))
    return out


def fns(tree) -> dict:
    """{name: node} for every function in a module AST."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def router_endpoints(tree) -> dict:
    """{func_name: [methods]} for endpoints decorated with @router.<method>."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and getattr(dec.func.value, "id", None) == "router"
                and dec.func.attr in {"get", "post", "patch", "put", "delete"}
            ):
                out.setdefault(node.name, []).append(dec.func.attr)
    return out


def fn_block(text: str, name: str) -> str:
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
    """True if the function's parameter list carries Depends(require_roles...)."""
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
            if "Depends(require_roles" in src:
                return True
    return False


def module_constant_tuples(tree) -> dict:
    """{UPPER_NAME: (values)} for module-level tuple assignments of strings."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Tuple)
        ):
            vals = tuple(
                v.value
                for v in node.value.elts
                if isinstance(v, ast.Constant) and isinstance(v.value, str)
            )
            if vals:
                out[node.targets[0].id] = vals
    return out


def module_constant_dicts(tree) -> dict:
    """{UPPER_NAME: {key: value}} for module-level str-keyed dict assignments."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Dict)
        ):
            items = {}
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    items[k.value] = v
            if items:
                out[node.targets[0].id] = items
    return out


def included_router_attrs(tree) -> set:
    """module names referenced by app.include_router(<mod>.router) in main.py."""
    out = set()
    if tree is None:
        return out
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == "include_router"
            and node.value.args
            and isinstance(node.value.args[0], ast.Attribute)
            and isinstance(node.value.args[0].value, ast.Name)
        ):
            out.add(node.value.args[0].value.id)
    return out


def async_defined(tree) -> set:
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)} if tree else set()


# ─── /api/admin router (eleventh router) ────────────────────────────────────

class TestAdminRouter(unittest.TestCase):
    def test_admin_router_registered_eleventh(self):
        """main.py must include_router all 11 (voice/auth/clinics/calls/
        appointments/prescriptions/payments/notifications/compliance/analytics/admin)."""
        included = included_router_attrs(py_tree(MAIN))
        self.assertEqual(
            KNOWN_ROUTERS | {"admin"},
            included,
            f"main.py must include_router all 11; got {sorted(included)}",
        )

    def test_admin_router_file_with_prefix(self):
        self.assertTrue(ADMIN_ROUTER.exists(), "app/api/admin.py missing")
        routers = router_objects(py_tree(ADMIN_ROUTER))
        self.assertEqual("/api/admin", routers.get("router"), "admin router prefix wrong")

    def test_admin_exact_endpoint_set(self):
        self.assertEqual(
            ADMIN_ENDPOINTS,
            endpoint_paths(py_tree(ADMIN_ROUTER)),
            "admin.py endpoint set differs from contract (5 GETs: '', /clinics, /patients, /revenue, /calls)",
        )

    def test_every_admin_endpoint_role_gated(self):
        """All 5 admin endpoints MUST carry Depends(require_roles('platform_admin'))."""
        text = read(ADMIN_ROUTER)
        tree = ast.parse(text) if text else None
        eps = router_endpoints(tree)
        self.assertGreater(len(eps), 0, "admin.py: no endpoints found")
        for name in eps:
            self.assertTrue(
                args_reference_guard(fns(tree).get(name)),
                f"admin.{name}: missing Depends(require_roles(...)) guard",
            )
            self.assertIn(
                "platform_admin",
                fn_block(text, name),
                f"admin.{name}: gate must require the platform_admin role",
            )


# ─── Platform aggregates in postgres.py ─────────────────────────────────────

class TestPlatformAggregates(unittest.TestCase):
    def test_platform_functions_exist(self):
        defined = async_defined(py_tree(POSTGRES))
        for name in PLATFORM_FNS:
            self.assertIn(name, defined, f"postgres.py: async {name}() missing")

    def test_each_platform_fn_arms_service_bypass(self):
        """Platform aggregates ride app.service_request internally (auth-CRUD
        pattern) so the admin views read across tenants under RLS FORCE."""
        text = read(POSTGRES)
        for name in PLATFORM_FNS:
            self.assertIn(
                "service_request",
                fn_block(text, name),
                f"postgres.py {name}: must arm service_request_ctx() internally",
            )


# ─── Role matrix + schema (platform_admin, clinic read bypass, seed) ────────

class TestRoleAndSchema(unittest.TestCase):
    def test_platform_admin_role_added_above_owner(self):
        tree = py_tree(AUTH_SVC)
        roles = module_constant_tuples(tree).get("ROLES", ())
        self.assertIn("platform_admin", roles, "ROLES must add platform_admin")
        weights = module_constant_dicts(tree).get("ROLE_WEIGHTS", {})
        self.assertIn("platform_admin", weights, "ROLE_WEIGHTS must weight platform_admin")
        self.assertGreaterEqual(
            weights["platform_admin"].value if hasattr(weights["platform_admin"], "value") else -1,
            weights.get("owner", ast.Constant(value=-1)).value if hasattr(weights.get("owner", ast.Constant(value=-1)), "value") else -1,
            "platform_admin must sit above owner",
        )

    def test_clinics_read_policy_service_bypass(self):
        """clinic_staff_read FOR SELECT must admit app.service_request so the
        platform clinics aggregate can read across tenants (no suite pins this
        policy's exact text — verified)."""
        text = read(SCHEMA)
        block = text.split("CREATE POLICY clinic_staff_read", 1)[1].split("CREATE POLICY", 1)[0]
        self.assertIn("app.service_request", block)

    def test_platform_admin_demo_seed(self):
        text = read(SCHEMA)
        self.assertIn("platform@medicall.in", text)
        self.assertIn("platform_admin", text)


# ─── Frontend client (src/lib/api.ts) ───────────────────────────────────────

class TestFrontendClient(unittest.TestCase):
    def test_api_client_exports_new_hooks(self):
        text = read(API_TS)
        for hook in CLINIC_NEW_HOOKS + ADMIN_NEW_HOOKS:
            self.assertIn(f"export function {hook}", text, f"api.ts: export {hook} missing")

    def test_api_client_has_endpoint_paths(self):
        text = read(API_TS)
        for path in CLINIC_NEW_ENDPOINTS + ADMIN_ENDPOINT_PATHS:
            self.assertIn(path, text, f"api.ts: {path} not referenced")

    def test_api_client_clinic_id_pattern(self):
        """Clinic hooks derive clinic_id from NEXT_PUBLIC_CLINIC_ID (single source)."""
        self.assertIn("NEXT_PUBLIC_CLINIC_ID", read(API_TS))

    def test_api_client_terminal_states(self):
        """Triage queue derives from /api/calls filtered by the shared terminal set."""
        self.assertIn("TERMINAL_STATES", read(API_TS))

    def test_admin_endpoints_platform_scoped(self):
        """Admin hooks are platform-wide: no clinic_id query param on /api/admin paths."""
        text = read(API_TS)
        for path in ADMIN_ENDPOINT_PATHS:
            self.assertNotIn(
                f"{path}?clinic_id=", text, f"admin hook must not carry clinic_id: {path}"
            )


# ─── Page wiring (10 wired / 4 entity-less stay mock) ───────────────────────

class TestPageWiring(unittest.TestCase):
    def test_clinic_pages_wired(self):
        for name in CLINIC_WIRED:
            text = read(CLINIC_APP / name / "page.tsx")
            self.assertIn("@/lib/api", text, f"(clinic)/{name}: must use the api client")
            self.assertNotIn("@/components/mock", text, f"(clinic)/{name}: still on mock")

    def test_admin_pages_wired(self):
        for name in ADMIN_WIRED:
            text = read(ADMIN_APP / name / "page.tsx") if name else read(ADMIN_APP / "page.tsx")
            self.assertIn("@/lib/api", text, f"admin/{name or 'index'}: must use the api client")
            self.assertNotIn("@/components/mock", text, f"admin/{name or 'index'}: still on mock")

    def test_unwired_admin_pages_documented_mock(self):
        """Doctors/billing/infrastructure/audit have no backend entity this phase:
        they stay on mock WITH an explicit 'no backend entity' note."""
        for name in ADMIN_UNWIRED:
            text = read(ADMIN_APP / name / "page.tsx")
            self.assertIn("@/components/mock", text, f"admin/{name}: fixture import gone")
            self.assertNotIn("@/lib/api", text, f"admin/{name}: wired but no entity behind it")
            self.assertIn("no backend entity", text, f"admin/{name}: missing the no-entity note")

    def test_mock_fixtures_intact_india_flavour(self):
        """Unwired pages still render mock fixtures; +91/₹ flavour must survive."""
        text = read(MOCK_TS)
        self.assertIn("+91", text)
        self.assertIn("₹", text)

    def test_no_dollar_amounts_in_wired_client(self):
        """Existing suite rule: no $[0-9] money literals anywhere in frontend src."""
        targets = [API_TS]
        for name in CLINIC_WIRED:
            targets.append(CLINIC_APP / name / "page.tsx")
        for name in ADMIN_WIRED:
            targets.append((ADMIN_APP / name / "page.tsx") if name else (ADMIN_APP / "page.tsx"))
        for path in targets:
            self.assertIsNone(
                re.search(r"\$[0-9]", read(path)),
                f"{path}: dollar amounts are banned (use ₹ + formatINR)",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)