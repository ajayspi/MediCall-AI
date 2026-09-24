"""API routes acceptance tests: clinics / calls / appointments / prescriptions / payments (stdlib only).

RED before implementation (2026-09-24, spec-api-routes.md D1/D2/D3 approved): backend/main.py
registers ONLY voice.router with a stale comment ("calls/appointments/prescriptions/payments land
in G4+"); backend/app/api/ contains only voice.py; there is NO app/schemas/ package; postgres.py
has no Payment model, no Numeric import, and no clinic list/update, call get/list (with severity/
date/pagination), appointment or prescription get/list/status-update, or any payment CRUD;
postgres_schema.sql has no payments table; postgres.py has no payments CRUD.

GREEN after implementation:
- main.py includes 6 routers (voice + clinics/calls/appointments/prescriptions/payments).
- 5 new router modules under app/api/, each declaring its own APIRouter prefix (self-contained
  full paths), endpoints per the contract table in spec-api-routes.md.
- app/schemas/ package: clinic/call/appointment/prescription/payment request models (pydantic
  BaseModel) + status/gateway constants as the single source for router validation.
- postgres.py: Payment ORM + the new CRUD helpers; list_clinic_calls remains as a thin wrapper.
- postgres_schema.sql: payments table (amount NUMERIC(10,2), currency INR default, gateway,
  gateway_ref, status pending|captured|failed|refunded) + index + trigger + RLS + grant.
- voice.py endpoint set unchanged (no regression).

Run: python3 tests/test_api_routes.py  (exit 0 = green)
"""
import ast
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
API_DIR = BACKEND / "app" / "api"
SCHEMAS_DIR = BACKEND / "app" / "schemas"
DB_DIR = BACKEND / "app" / "db"
MODELS_DIR = BACKEND / "app" / "models"
MAIN = BACKEND / "main.py"
SCHEMA_SQL = BACKEND / "postgres_schema.sql"
VOICE = API_DIR / "voice.py"

G3_STATES = (
    "GREETING",
    "TRIAGE",
    "APPOINTMENT",
    "PRESCRIPTION",
    "COMPLETE",
    "ESCALATED",
    "DROPPED",
    "PAYMENT_SENT",
    "PAYMENT_EXPIRED",
)
LANGUAGES = ("hi", "en", "ta", "te", "bn")
SEVERITIES = ("green", "amber", "red", "critical")

APPOINTMENT_STATUSES = ("pending", "confirmed", "completed", "cancelled", "no_show")
PRESCRIPTION_STATUSES = ("pending", "approved", "sent_pharmacy", "dispensed")
PAYMENT_STATUSES = ("pending", "captured", "failed", "refunded")
PAYMENT_GATEWAYS = ("razorpay", "phonepe", "cashfree", "manual")

NEW_CRUD_HELPERS = (
    "list_clinics",
    "update_clinic",
    "get_call",
    "list_calls",
    "get_appointment",
    "list_appointments",
    "update_appointment_status",
    "get_prescription",
    "list_prescriptions",
    "update_prescription_status",
    "create_payment",
    "list_payments",
    "get_payment",
    "update_payment_status",
)

ROUTER_MODULES = ("clinics", "calls", "appointments", "prescriptions", "payments")
SCHEMA_MODULES = ("clinic", "call", "appointment", "prescription", "payment")

EXPECTED_ENDPOINTS = {
    "clinics": {
        ("get", ""),
        ("post", ""),
        ("get", "/{clinic_id}"),
        ("patch", "/{clinic_id}"),
    },
    "calls": {
        ("get", ""),
        ("get", "/{call_id}"),
        ("patch", "/{call_id}/state"),
        ("get", "/{call_id}/transcript"),
    },
    "appointments": {
        ("get", ""),
        ("post", ""),
        ("get", "/{appointment_id}"),
        ("patch", "/{appointment_id}/status"),
    },
    "prescriptions": {
        ("get", ""),
        ("post", ""),
        ("get", "/{prescription_id}"),
        ("patch", "/{prescription_id}/status"),
    },
    "payments": {
        ("get", ""),
        ("post", ""),
        ("get", "/{payment_id}"),
        ("patch", "/{payment_id}/status"),
    },
}

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
    "+61",
)


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


def router_objects(tree):
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


def module_imported_names(tree, module: str) -> set:
    """Names imported via `from <module> import ...`."""
    out = set()
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            out |= {a.name for a in node.names}
    return out


def schema_classes(tree) -> dict:
    """{class_name: {"bases": set, "fields": [annotated names]}} for ClassDef nodes."""
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(b, "id", None) for b in node.bases} - {None}
        fields = [
            stmt.target.id
            for stmt in node.body
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
        ]
        out[node.name] = {"bases": bases, "fields": fields}
    return out


def module_constant_tuples(tree) -> dict:
    """{UPPER_NAME: (values)} for module-level tuple assignments of string constants."""
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


def async_defined(tree) -> set:
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)} if tree else set()


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


class TestMainApp(unittest.TestCase):
    def test_main_registers_all_six_routers(self):
        tree = py_tree(MAIN)
        included = included_router_attrs(tree)
        self.assertEqual(
            {"voice", "clinics", "calls", "appointments", "prescriptions", "payments"},
            included,
            f"main.py must include_router all 6; got {sorted(included)}",
        )

    def test_main_voice_keeps_api_voice_prefix(self):
        tree = py_tree(MAIN)
        found = False
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Call)
                and isinstance(node.value.func, ast.Attribute)
                and node.value.func.attr == "include_router"
                and node.value.args
                and isinstance(node.value.args[0], ast.Attribute)
                and isinstance(node.value.args[0].value, ast.Name)
                and node.value.args[0].value.id == "voice"
            ):
                prefixes = [
                    kw.value.value
                    for kw in node.value.keywords
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant)
                ]
                self.assertIn("/api/voice", prefixes)
                found = True
        self.assertTrue(found, "voice include_router call not found in main.py")

    def test_main_stale_comment_gone(self):
        self.assertNotIn("land in G4+", read(MAIN))

    def test_main_title_health_unchanged(self):
        text = read(MAIN)
        self.assertIn('title="MediCall AI"', text)
        self.assertIn('"/health"', text)
        self.assertIn("medicall-api", text)

    def test_main_imports_all_six_router_modules(self):
        tree = py_tree(MAIN)
        names = module_imported_names(tree, "app.api")
        self.assertIn("voice", names)
        for mod in ROUTER_MODULES:
            self.assertIn(mod, names, f"main.py must import app.api.{mod}")


class TestRouterPresence(unittest.TestCase):
    def test_each_router_file_exists_with_prefix(self):
        for mod in ROUTER_MODULES:
            path = API_DIR / f"{mod}.py"
            self.assertTrue(path.exists(), f"app/api/{mod}.py missing")
            routers = router_objects(py_tree(path))
            self.assertEqual(f"/api/{mod}", routers.get("router"), f"{mod} router prefix wrong")

    def test_each_router_exact_endpoint_set(self):
        for mod in ROUTER_MODULES:
            path = API_DIR / f"{mod}.py"
            self.assertEqual(
                EXPECTED_ENDPOINTS[mod],
                endpoint_paths(py_tree(path)),
                f"{mod}.py endpoint set differs from contract",
            )


class TestClinicsRouter(unittest.TestCase):
    def test_uses_clinic_schemas(self):
        names = module_imported_names(py_tree(API_DIR / "clinics.py"), "app.schemas.clinic")
        self.assertIn("ClinicCreate", names)
        self.assertIn("ClinicUpdate", names)

    def test_uses_postgres_crud(self):
        names = module_imported_names(py_tree(API_DIR / "clinics.py"), "app.db.postgres")
        for fn in ("list_clinics", "get_clinic", "create_clinic", "update_clinic"):
            self.assertIn(fn, names)

    def test_handles_not_found(self):
        text = read(API_DIR / "clinics.py")
        self.assertIn("HTTPException", text)
        self.assertIn("404", text)


class TestCallsRouter(unittest.TestCase):
    def test_uses_call_state_machine(self):
        names = module_imported_names(py_tree(API_DIR / "calls.py"), "app.models.call")
        self.assertIn("CallState", names)
        self.assertIn("STATE_TRANSITIONS", names)
        self.assertIn("TriageSeverity", names)

    def test_uses_call_schema(self):
        names = module_imported_names(py_tree(API_DIR / "calls.py"), "app.schemas.call")
        self.assertIn("CallStateUpdate", names)

    def test_filters_cover_language_and_severity(self):
        text = read(API_DIR / "calls.py")
        for code in LANGUAGES:
            self.assertRegex(text, rf"\b{code}\b", f"language {code} missing from calls filters")
        for tone in SEVERITIES:
            self.assertRegex(text, rf"\b{tone}\b", f"severity {tone} missing from calls filters")

    def test_pagination_capped(self):
        text = read(API_DIR / "calls.py")
        self.assertIn("limit", text)
        self.assertIn("offset", text)
        self.assertIn("200", text)

    def test_invalid_transition_rejected(self):
        text = read(API_DIR / "calls.py")
        self.assertIn("409", text)
        self.assertIn("STATE_TRANSITIONS", text)


class TestAppointmentsRouter(unittest.TestCase):
    def test_uses_appointment_schemas_and_statuses(self):
        names = module_imported_names(py_tree(API_DIR / "appointments.py"), "app.schemas.appointment")
        self.assertIn("AppointmentCreate", names)
        self.assertIn("AppointmentStatusUpdate", names)

    def test_status_set_validated(self):
        text = read(API_DIR / "appointments.py")
        for status in APPOINTMENT_STATUSES:
            self.assertIn(status, text, f"appointment status {status} missing")
        self.assertIn("422", text)
        self.assertIn("404", text)


class TestPrescriptionsRouter(unittest.TestCase):
    def test_uses_prescription_schemas_and_statuses(self):
        names = module_imported_names(py_tree(API_DIR / "prescriptions.py"), "app.schemas.prescription")
        self.assertIn("PrescriptionCreate", names)
        self.assertIn("PrescriptionStatusUpdate", names)

    def test_status_set_validated(self):
        text = read(API_DIR / "prescriptions.py")
        for status in PRESCRIPTION_STATUSES:
            self.assertIn(status, text, f"prescription status {status} missing")
        self.assertIn("422", text)
        self.assertIn("404", text)


class TestPaymentsRouter(unittest.TestCase):
    def test_uses_payment_schemas_gateways_statuses(self):
        names = module_imported_names(py_tree(API_DIR / "payments.py"), "app.schemas.payment")
        self.assertIn("PaymentCreate", names)
        self.assertIn("PaymentStatusUpdate", names)
        self.assertIn("PAYMENT_GATEWAYS", names)
        self.assertIn("PAYMENT_STATUSES", names)
        text = read(API_DIR / "payments.py")
        for gateway in PAYMENT_GATEWAYS:
            self.assertIn(gateway, text)
        for status in PAYMENT_STATUSES:
            self.assertIn(status, text)

    def test_scaffold_never_calls_gateway_sdks(self):
        low = read(API_DIR / "payments.py").lower()
        for banned in ("from razorpay", "from phonepe_sdk", "from cashfree_pg", "import razorpay"):
            self.assertNotIn(banned, low, f"payments.py must stay SDK-free (G6-Q5), found {banned}")

    def test_scaffold_documented(self):
        text = read(API_DIR / "payments.py")
        self.assertIn("G6-Q5", text, "payments scaffold must document the gating decision")


class TestSchemasPackage(unittest.TestCase):
    def test_package_init_exists(self):
        self.assertTrue((SCHEMAS_DIR / "__init__.py").exists(), "app/schemas/__init__.py missing")

    def test_each_module_exports_expected_models(self):
        expected = {
            "clinic": {"ClinicCreate", "ClinicUpdate"},
            "call": {"CallStateUpdate"},
            "appointment": {"AppointmentCreate", "AppointmentStatusUpdate"},
            "prescription": {"PrescriptionCreate", "PrescriptionStatusUpdate"},
            "payment": {"PaymentCreate", "PaymentStatusUpdate"},
        }
        for mod, wanted in expected.items():
            classes = schema_classes(py_tree(SCHEMAS_DIR / f"{mod}.py"))
            self.assertTrue(wanted <= set(classes), f"{mod}.py missing classes {wanted - set(classes)}")
            for name in wanted:
                self.assertIn("BaseModel", classes[name]["bases"], f"{mod}.{name} must subclass BaseModel")

    def test_required_fields_present(self):
        required = {
            "clinic": {"ClinicCreate": ["name", "phone_number", "city", "state"],
                       "ClinicUpdate": ["ai_instructions", "plan", "is_active"]},
            "call": {"CallStateUpdate": ["state"]},
            "appointment": {"AppointmentCreate": ["clinic_id", "patient_name", "patient_phone", "scheduled_at"],
                            "AppointmentStatusUpdate": ["status"]},
            "prescription": {"PrescriptionCreate": ["clinic_id", "patient_name", "medication"],
                             "PrescriptionStatusUpdate": ["status"]},
            "payment": {"PaymentCreate": ["clinic_id", "amount", "currency", "gateway"],
                        "PaymentStatusUpdate": ["status"]},
        }
        for mod, classmap in required.items():
            classes = schema_classes(py_tree(SCHEMAS_DIR / f"{mod}.py"))
            for name, fields in classmap.items():
                present = classes.get(name, {}).get("fields", [])
                for f in fields:
                    self.assertIn(f, present, f"{mod}.{name} missing field {f}")

    def test_status_gateway_constants_single_source(self):
        consts = module_constant_tuples(py_tree(SCHEMAS_DIR / "appointment.py"))
        self.assertEqual(APPOINTMENT_STATUSES, consts.get("APPOINTMENT_STATUSES"))
        consts = module_constant_tuples(py_tree(SCHEMAS_DIR / "prescription.py"))
        self.assertEqual(PRESCRIPTION_STATUSES, consts.get("PRESCRIPTION_STATUSES"))
        consts = module_constant_tuples(py_tree(SCHEMAS_DIR / "payment.py"))
        self.assertEqual(PAYMENT_STATUSES, consts.get("PAYMENT_STATUSES"))
        self.assertEqual(PAYMENT_GATEWAYS, consts.get("PAYMENT_GATEWAYS"))


class TestPostgresLayer(unittest.TestCase):
    def test_payment_model_present(self):
        tree = py_tree(DB_DIR / "postgres.py")
        self.assertIn("Payment", schema_classes(tree))
        self.assertIn('__tablename__ = "payments"', read(DB_DIR / "postgres.py"))

    def test_numeric_imported(self):
        names = module_imported_names(py_tree(DB_DIR / "postgres.py"), "sqlalchemy")
        self.assertIn("Numeric", names)

    def test_new_crud_helpers_async(self):
        defined = async_defined(py_tree(DB_DIR / "postgres.py"))
        for fn in NEW_CRUD_HELPERS:
            self.assertIn(fn, defined, f"postgres.py missing async def {fn}")

    def test_list_clinic_calls_kept_as_wrapper(self):
        defined = async_defined(py_tree(DB_DIR / "postgres.py"))
        self.assertIn("list_clinic_calls", defined)


class TestPaymentsSQL(unittest.TestCase):
    def test_payments_table_exists(self):
        self.assertIn("CREATE TABLE payments", read(SCHEMA_SQL))

    def test_payments_columns(self):
        text = read(SCHEMA_SQL)
        for col in (
            "amount NUMERIC(10,2) NOT NULL",
            "currency TEXT DEFAULT 'INR'",
            "gateway TEXT",
            "gateway_ref TEXT",
            "status TEXT DEFAULT 'pending'",
            "clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE",
            "call_id UUID REFERENCES calls(id) ON DELETE SET NULL",
            "appointment_id UUID REFERENCES appointments(id) ON DELETE SET NULL",
        ):
            self.assertIn(col, text, f"payments table missing column: {col}")

    def test_payments_statuses_and_gateways(self):
        text = read(SCHEMA_SQL)
        for status in PAYMENT_STATUSES:
            self.assertIn(status, text)
        for gateway in PAYMENT_GATEWAYS:
            self.assertIn(gateway, text)

    def test_payments_index_trigger_rls_grant(self):
        text = read(SCHEMA_SQL)
        self.assertIn("idx_payments_clinic_status", text)
        self.assertIn("update_payments_updated_at", text)
        self.assertIn("ALTER TABLE payments ENABLE ROW LEVEL SECURITY", text)
        self.assertIn("CREATE POLICY payments_manage", text)
        self.assertIn("GRANT ALL ON payments TO authenticated", text)


class TestNoRegression(unittest.TestCase):
    def test_voice_endpoint_set_unchanged(self):
        self.assertEqual(
            {
                ("post", "/webhook/exotel"),
                ("post", "/webhook/knowlarity"),
                ("post", "/webhook/twilio"),
                ("post", "/livekit-agent-start"),
                ("post", "/call-completed"),
            },
            endpoint_paths(py_tree(VOICE)),
            "voice.py must stay exactly as G4 delivered it",
        )

    def test_no_restaurant_leftovers_in_new_backend_files(self):
        targets = [MAIN, SCHEMA_SQL, DB_DIR / "postgres.py"]
        targets += [API_DIR / f"{mod}.py" for mod in ROUTER_MODULES]
        targets += [SCHEMAS_DIR / f"{mod}.py" for mod in SCHEMA_MODULES]
        found = []
        for path in targets:
            low = read(path).lower()
            for token in RESTAURANT_LEFTOVERS:
                if token in low:
                    found.append(f"{path.relative_to(BACKEND)}: {token}")
        self.assertEqual([], found, "restaurant/TalkByte leftovers in new backend files:\n" + "\n".join(found))


if __name__ == "__main__":
    unittest.main(verbosity=2)