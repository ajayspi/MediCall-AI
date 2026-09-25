"""G6-Q2 DPDP RED contract: consent flag + retention + 72-hr breach + posture.

Contract (sign-off 2026-09-25, Q1=A1 Q2=A1 Q3=A1 Q4=A1):
- Q1=A1: calls.recording_consent TEXT (unknown/granted/denied, default unknown)
  + stdlib app/services/consent.py — 5-language yes/no in-call parse
  (parse_consent_response -> granted/denied/None) + recording_allowed() egress
  gate + identity-gated POST /api/calls/{id}/consent. Rides existing calls RLS.
- Q2=A1: stdlib app/services/retention.py — RETENTION_DAYS (calls 365,
  recordings 365, notifications 180, audit 2190) + per-kind env overrides +
  tz-aware retention_deadline() + purge_expired() DELETE service (Docker/CI
  cron wiring deferred; recordings = MinIO objects -> posture + env only).
- Q3=A1: compliance_events tenant table (type/severity/status/detected_at/
  notification_deadline/reported_at) + compliance_manage policy (mirrors
  notifications_send) + identity-gated app/api/compliance.py
  (POST /events, GET "", PATCH /events/{id}) + stdlib app/services/compliance.py
  (DPDP_BREACH_NOTIFICATION_HOURS default 72, breach_notification_deadline(),
  data_residency(), dpo_contact()). DPB dispatch is an operational follow-on.
- Q4=A1: DATA_RESIDENCY_REGION (default "in") + DPO_NAME/DPO_EMAIL env surfaced
  by compliance.py; region pin owned by Q10.
- Pins: G4 voice + Q8 catalog + Q4 languages single-source hold; auth.py /
  IDENTITY_FREE_ENDPOINTS untouched; new service modules are stdlib leaves.
"""

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS = BACKEND / "tests"
APP = BACKEND / "app"

try:
    from app.services import consent as cons  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    cons = None

try:
    from app.services import retention as retn  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    retn = None

try:
    from app.services import compliance as comp  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    comp = None

LANGUAGES = ("hi", "en", "ta", "te", "bn")
CONSENT_STATES = ("unknown", "granted", "denied")
RETENTION_DAYS = {"calls": 365, "recordings": 365, "notifications": 180, "audit": 2190}
EVENT_TYPES = ("data_breach", "consent_withdrawal", "gdpr_request")
SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("open", "reported", "closed")
ENV_KEYS = (
    "RETENTION_CALLS_DAYS",
    "RETENTION_RECORDINGS_DAYS",
    "RETENTION_NOTIFICATIONS_DAYS",
    "RETENTION_AUDIT_DAYS",
    "DPDP_BREACH_NOTIFICATION_HOURS",
    "DATA_RESIDENCY_REGION",
    "DPO_NAME",
    "DPO_EMAIL",
)
BANNED_ROOTS = {"httpx", "requests", "twilio", "whatsapp", "msg91", "firebase_admin",
                "fastapi", "sqlalchemy", "pydantic", "websockets", "openai", "elevenlabs"}


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


def fn_block(text: str, name: str) -> str:
    """The source text of one function (via AST line offsets), or ''.

    Slices by LINE via splitlines(keepends=True) so each line stays intact
    (same helper as test_notifications_q8 / test_languages_q4).
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = text.splitlines(keepends=True)
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


def module_imported_names(tree, module: str) -> set:
    out = set()
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def imports_at_module_level(tree) -> list:
    """[(kind, name)] where kind in {"import", "from"} — module-level only."""
    out = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(("import", alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(("from", node.module.split(".")[0]))
    return out


def endpoint_set(router_path: Path) -> set:
    """{(method, path)} from the router's route decorators (Q8 convention)."""
    tree = py_tree(router_path)
    found = set()
    if tree is None:
        return found
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
                found.add((dec.func.attr, dec.args[0].value))
    return found


# ─── Consent module (Q1=A1) ────────────────────────────────────────────────
class TestConsentModule(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(cons, "app/services/consent.py missing (RED)")

    def test_consent_states_exact(self):
        self.assertEqual(CONSENT_STATES, tuple(cons.RECORDING_CONSENT_STATES))

    def test_parse_yes_english(self):
        for raw in ("yes", "Yes", "  YES  ", "yEs!"):
            self.assertEqual(cons.parse_consent_response(raw, "en"), "granted", raw)

    def test_parse_no_english(self):
        for raw in ("no", "No", "  NO ", "nO!"):
            self.assertEqual(cons.parse_consent_response(raw, "en"), "denied", raw)

    def test_parse_all_five_languages_yes(self):
        words = {"hi": "haan", "en": "yes", "ta": "aamam", "te": "avunu", "bn": "ha"}
        for lang in LANGUAGES:
            self.assertEqual(cons.parse_consent_response(words[lang], lang), "granted", lang)

    def test_parse_all_five_languages_no(self):
        words = {"hi": "nahin", "en": "no", "ta": "illai", "te": "kadu", "bn": "na"}
        for lang in LANGUAGES:
            self.assertEqual(cons.parse_consent_response(words[lang], lang), "denied", lang)

    def test_english_words_work_in_every_language(self):
        # Callers code-switch; "yes"/"no" must catch in any of the 5 languages.
        for lang in LANGUAGES:
            self.assertEqual(cons.parse_consent_response("yes", lang), "granted", lang)
            self.assertEqual(cons.parse_consent_response("no", lang), "denied", lang)

    def test_unknown_or_empty_text_is_none(self):
        self.assertIsNone(cons.parse_consent_response("", "en"))
        self.assertIsNone(cons.parse_consent_response("maybe", "en"))
        self.assertIsNone(cons.parse_consent_response("haan bahut", "hi"))
        self.assertIsNone(cons.parse_consent_response("yes", "xx"), "unknown language -> None")

    def test_recording_allowed_gate(self):
        self.assertTrue(cons.recording_allowed("granted"))
        for value in ("denied", "unknown", None, ""):
            self.assertFalse(cons.recording_allowed(value), value)


class TestConsentCatalog(unittest.TestCase):
    def test_docstring_marks_phase(self):
        text = read(APP / "services" / "consent.py")
        self.assertIn("G6-Q2", text[:600])

    def test_stdlib_only_leaf(self):
        tree = py_tree(APP / "services" / "consent.py")
        banned = [m for _, m in imports_at_module_level(tree) if m in BANNED_ROOTS]
        self.assertEqual([], banned, "consent.py must be a stdlib leaf")

    def test_imports_languages_catalog(self):
        tree = py_tree(APP / "services" / "consent.py")
        names = module_imported_names(tree, "app.services.languages")
        self.assertIn("SUPPORTED_LANGUAGES", names, "consent.py must use the Q4 catalog")

    def test_yes_no_maps_cover_all_five(self):
        self.assertTrue(set(cons.CONSENT_YES) >= set(LANGUAGES))
        self.assertTrue(set(cons.CONSENT_NO) >= set(LANGUAGES))


# ─── Retention module (Q2=A1) ──────────────────────────────────────────────
class TestRetentionModule(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(retn, "app/services/retention.py missing (RED)")

    def test_retention_days_map_exact(self):
        self.assertEqual(RETENTION_DAYS, dict(retn.RETENTION_DAYS))

    def test_retention_days_defaults(self):
        for kind, days in RETENTION_DAYS.items():
            self.assertEqual(retn.retention_days(kind, env={}), days, kind)

    def test_retention_days_env_override(self):
        env = {"RETENTION_CALLS_DAYS": "90", "RETENTION_AUDIT_DAYS": "3650"}
        self.assertEqual(retn.retention_days("calls", env=env), 90)
        self.assertEqual(retn.retention_days("audit", env=env), 3650)
        self.assertEqual(retn.retention_days("notifications", env=env), 180)

    def test_retention_days_invalid_env_falls_back(self):
        env = {"RETENTION_CALLS_DAYS": "bogus", "RETENTION_NOTIFICATIONS_DAYS": ""}
        self.assertEqual(retn.retention_days("calls", env=env), 365)
        self.assertEqual(retn.retention_days("notifications", env=env), 180)

    def test_retention_categories_exact(self):
        self.assertEqual(tuple(RETENTION_DAYS.keys()), tuple(retn.retention_categories()))

    def test_deadline_aware_math(self):
        created = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        deadline = retn.retention_deadline(created, "calls", env={})
        self.assertEqual(deadline, created + timedelta(days=365))
        self.assertIsNotNone(deadline.tzinfo, "deadline must be timezone-aware")

    def test_deadline_naive_input_is_utc(self):
        naive = datetime(2026, 1, 1, 12, 0)
        deadline = retn.retention_deadline(naive, "notifications", env={})
        self.assertEqual(deadline.utcoffset(), timedelta(0), "naive input assumed UTC")
        self.assertEqual(deadline, datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc))

    def test_deadline_respects_env_override(self):
        created = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        env = {"RETENTION_CALLS_DAYS": "30"}
        self.assertEqual(
            retn.retention_deadline(created, "calls", env=env),
            created + timedelta(days=30),
        )

    def test_kinds_have_distinct_deadlines(self):
        created = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        calls = retn.retention_deadline(created, "calls", env={})
        audit = retn.retention_deadline(created, "audit", env={})
        self.assertGreater(audit - calls, timedelta(days=1000), "audit 6yr must outlive calls 1yr")

    def test_stdlib_only_leaf(self):
        tree = py_tree(APP / "services" / "retention.py")
        roots = {m for _, m in imports_at_module_level(tree)}
        self.assertTrue(roots <= {"os", "datetime", "typing"}, f"retention.py roots: {roots}")


# ─── Compliance module (Q3=A1 / Q4=A1) ─────────────────────────────────────
class TestComplianceModule(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(comp, "app/services/compliance.py missing (RED)")

    def test_event_types_exact(self):
        self.assertEqual(EVENT_TYPES, tuple(comp.COMPLIANCE_EVENT_TYPES))

    def test_severities_exact(self):
        self.assertEqual(SEVERITIES, tuple(comp.SEVERITIES))

    def test_statuses_exact(self):
        self.assertEqual(STATUSES, tuple(comp.STATUSES))

    def test_breach_hours_default_72(self):
        self.assertEqual(comp.DPDP_BREACH_NOTIFICATION_HOURS, 72)

    def test_breach_deadline_default_72h(self):
        detected = datetime(2026, 1, 31, 23, 0, tzinfo=timezone.utc)
        deadline = comp.breach_notification_deadline(detected, env={})
        self.assertEqual(deadline, datetime(2026, 2, 3, 23, 0, tzinfo=timezone.utc))
        self.assertIsNotNone(deadline.tzinfo)

    def test_breach_deadline_env_override(self):
        detected = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            comp.breach_notification_deadline(detected, env={"DPDP_BREACH_NOTIFICATION_HOURS": "48"}),
            detected + timedelta(hours=48),
        )
        # invalid env -> default 72
        bad = comp.breach_notification_deadline(detected, env={"DPDP_BREACH_NOTIFICATION_HOURS": "soon"})
        self.assertEqual(bad, detected + timedelta(hours=72))

    def test_breach_deadline_naive_input_is_utc(self):
        detected = datetime(2026, 1, 1, 0, 0)
        deadline = comp.breach_notification_deadline(detected, env={})
        self.assertEqual(deadline.utcoffset(), timedelta(0))
        self.assertEqual(deadline, datetime(2026, 1, 4, 0, 0, tzinfo=timezone.utc))

    def test_data_residency_default_in(self):
        self.assertEqual(comp.data_residency(env={}), "in")

    def test_data_residency_env_override(self):
        self.assertEqual(comp.data_residency(env={"DATA_RESIDENCY_REGION": "ap-south-1"}), "ap-south-1")

    def test_dpo_contact_env_pair(self):
        env = {"DPO_NAME": "A. Sharma", "DPO_EMAIL": "dpo@medicall.in"}
        self.assertEqual(comp.dpo_contact(env=env), ("A. Sharma", "dpo@medicall.in"))
        self.assertEqual(comp.dpo_contact(env={}), ("", ""))

    def test_stdlib_only_leaf(self):
        tree = py_tree(APP / "services" / "compliance.py")
        roots = {m for _, m in imports_at_module_level(tree)}
        self.assertTrue(roots <= {"os", "datetime", "typing"}, f"compliance.py roots: {roots}")


# ─── Schema (Q1=A1 calls column, Q3=A1 compliance_events) ──────────────────
class TestSchemaTable(unittest.TestCase):
    SCHEMA = BACKEND / "postgres_schema.sql"

    def test_calls_has_recording_consent(self):
        sql = read(self.SCHEMA)
        block = sql.split("CREATE TABLE calls", 1)[1].split(");", 1)[0] if "CREATE TABLE calls" in sql else ""
        self.assertIn("recording_consent", block, "calls table missing recording_consent")
        self.assertIn("unknown", block, "recording_consent must default to 'unknown'")

    def test_compliance_events_table_exists(self):
        self.assertIn("CREATE TABLE compliance_events", read(self.SCHEMA))

    def test_compliance_events_core_columns(self):
        sql = read(self.SCHEMA)
        block = sql.split("CREATE TABLE compliance_events", 1)[1].split(");", 1)[0] if "CREATE TABLE compliance_events" in sql else ""
        for col in ("clinic_id", "event_type", "severity", "status", "detected_at",
                    "notification_deadline", "reported_at", "description", "created_at", "updated_at"):
            self.assertIn(col, block, f"compliance_events missing column {col}")

    def test_compliance_index(self):
        self.assertIn("idx_compliance_clinic_status", read(self.SCHEMA))

    def test_compliance_policy_mirrors_notifications(self):
        sql = read(self.SCHEMA)
        self.assertIn("CREATE POLICY compliance_manage", sql)
        self.assertIn("app.service_request", sql)
        self.assertIn("clinic_users", sql, "policy must scope by clinic membership")

    def test_grants_cover_both_roles(self):
        sql = read(self.SCHEMA)
        self.assertIn("GRANT ALL ON compliance_events TO authenticated", sql)
        self.assertIn("GRANT ALL ON compliance_events TO medicall_app", sql)


# ─── Postgres ORM (postgres.py) ────────────────────────────────────────────
class TestPostgresOrm(unittest.TestCase):
    def test_call_orm_recording_consent(self):
        text = read(APP / "db" / "postgres.py")
        self.assertIn("recording_consent", text, "Call ORM must carry recording_consent")

    def test_update_call_consent_helper(self):
        text = read(APP / "db" / "postgres.py")
        self.assertIn("update_call_consent", text)

    def test_compliance_event_orm(self):
        text = read(APP / "db" / "postgres.py")
        self.assertIn('__tablename__ = "compliance_events"', text)

    def test_compliance_helpers(self):
        text = read(APP / "db" / "postgres.py")
        for fn in ("create_compliance_event", "list_compliance_events", "update_compliance_event"):
            self.assertIn(fn, text, f"postgres.py missing {fn}")

    def test_purge_expired_helper(self):
        text = read(APP / "db" / "postgres.py")
        self.assertIn("purge_expired", text)

    def test_create_compliance_event_computes_deadline(self):
        text = read(APP / "db" / "postgres.py")
        block = fn_block(text, "create_compliance_event")
        self.assertIn("notification_deadline", block, "create must compute the 72-hr deadline")
        self.assertIn("breach_notification_deadline", block)


# ─── Calls router (Q1=A1 consent endpoint) ─────────────────────────────────
class TestCallsRouter(unittest.TestCase):
    ROUTER = APP / "api" / "calls.py"

    def test_call_row_serializes_consent(self):
        block = fn_block(read(self.ROUTER), "call_row")
        self.assertIn("recording_consent", block, "call_row must expose recording_consent")

    def test_consent_endpoint_exists(self):
        text = read(self.ROUTER)
        self.assertIn("/consent", text)
        self.assertIn("update_call_consent", text)

    def test_consent_endpoint_identity_gated(self):
        block = fn_block(read(self.ROUTER), "update_call_consent_ep")
        self.assertGreater(len(block), 0, "update_call_consent_ep must exist")
        self.assertIn("Depends(get_current_user)", block)


# ─── Compliance router (Q3=A1) ─────────────────────────────────────────────
class TestComplianceRouter(unittest.TestCase):
    ROUTER = APP / "api" / "compliance.py"
    MAIN = BACKEND / "main.py"

    def test_router_file_exists_and_parses(self):
        self.assertTrue(self.ROUTER.exists(), "app/api/compliance.py missing")
        self.assertIsNotNone(py_tree(self.ROUTER))

    def test_router_prefix(self):
        self.assertIn('prefix="/api/compliance"', read(self.ROUTER))

    def test_endpoints_create_list_patch(self):
        self.assertEqual(
            {("get", ""), ("post", "/events"), ("patch", "/events/{event_id}")},
            endpoint_set(self.ROUTER),
        )

    def test_create_endpoint_identity_gated(self):
        block = fn_block(read(self.ROUTER), "create_compliance_event_ep")
        self.assertGreater(len(block), 0)
        self.assertIn("Depends(get_current_user)", block)

    def test_patch_sets_reported_at(self):
        block = fn_block(read(self.ROUTER), "update_compliance_event_ep")
        self.assertGreater(len(block), 0)
        self.assertIn("reported_at", block, "status -> reported must stamp reported_at")

    def test_registered_in_main(self):
        tree = py_tree(self.MAIN)
        names = module_imported_names(tree, "app.api")
        self.assertIn("compliance", names, "main.py must import app.api.compliance")
        self.assertIn("compliance", read(self.MAIN))


# ─── Env surface (Q2=A1 / Q3=A1 / Q4=A1) ───────────────────────────────────
class TestEnvExample(unittest.TestCase):
    ENV = BACKEND / ".env.example"

    def test_all_dpdp_keys_documented(self):
        text = read(self.ENV)
        for key in ENV_KEYS:
            self.assertIn(key, text, f".env.example missing {key}")

    def test_keys_are_assignments(self):
        text = read(self.ENV)
        for key in ENV_KEYS:
            self.assertIn(f"{key}=", text, f"{key} must be an assignment")


# ─── Docs/surface refs (deliverable J surface, updated in feat) ────────────
class TestDocsRefs(unittest.TestCase):
    def test_api_contracts_doc_covers_dpdp(self):
        doc = read(BACKEND / ".." / "docs" / "uml" / "03-api-contracts.md")
        self.assertIn("/api/compliance", doc)
        self.assertIn("/consent", doc)

    def test_smoke_drives_compliance(self):
        self.assertIn("/api/compliance", read(BACKEND / "scripts" / "smoke_api.py"))


# ─── Auth untouched (pin) ──────────────────────────────────────────────────
class TestAuthUntouched(unittest.TestCase):
    def test_auth_not_rewired(self):
        text = read(APP / "api" / "auth.py")
        self.assertNotIn("recording_consent", text, "consent wiring is not an auth change")
        self.assertNotIn("compliance_events", text)
        self.assertNotIn("app.services.compliance", text)


if __name__ == "__main__":
    unittest.main()