"""MI approved-content knowledge base (spec-micc-pv-phase2.md slice 2D) — RED contracts.

The Phase-1 MI path only LOGGED a question and told the caller it would be
routed to Medical Affairs. Slice 2D adds the approved-content layer on top: a
versioned per-(product, language, category) response knowledge base, and an
answer path that may speak ONLY from approved content or from the product's own
approved label. Anything else is NO_MEDICAL_ADVICE — a knowledge-base gap can
never be talked round, because the fallback is a refusal phrase, not an
improvisation.

Same house pattern as test_pv_module.py / test_pv_dashboard.py: the pure stdlib
service (app/services/medical_info.py) is imported and BEHAVIOUR-tested with no
database, no FastAPI and no network; the schema / ORM / router contracts are
structural AST + text assertions; and the live postgres_schema.sql well-formedness
guard is executed as a test so a malformed CREATE TABLE cannot ship behind a
green suite.

RED before implementation (2026-09-26): no app/services/medical_info.py, no
product_responses table, no ORM model/repository helpers, no /api/pv/responses
or /api/pv/inquiries/{id}/answer routes.

Run: py -3.14 -m unittest discover -s tests -p "test_medical_info.py"   (from backend/)
"""
import ast
import importlib.util
import io
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

API_DIR = BACKEND / "app" / "api"
DB_DIR = BACKEND / "app" / "db"
SERVICES = BACKEND / "app" / "services"
SCHEMA_SQL = BACKEND / "postgres_schema.sql"
POSTGRES = DB_DIR / "postgres.py"
PV_ROUTER = API_DIR / "pv.py"
MI_SVC = SERVICES / "medical_info.py"
SCHEMA_GUARD = BACKEND / "tests" / "test_schema_wellformed.py"

KB_TABLE = "product_responses"
KB_MODEL = "ProductResponse"
KB_REPO_FNS = (
    "create_response",
    "list_responses",
    "latest_approved_response",
    "update_response_status",
    "delete_response",
)
# Extra repository helpers the answer route needs: the MI row it updates, and
# the writer that persists response_text + status on it.
MI_REPO_FNS = ("get_medical_inquiry", "update_medical_inquiry_answer")

KB_ROUTES = {
    ("post", "/responses"),
    ("get", "/responses"),
    ("post", "/inquiries/{inquiry_id}/answer"),
}
KB_IDENTITY_GATED = (
    "create_response_ep",
    "list_responses_ep",
    "answer_medical_inquiry_ep",
)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def py_tree_text(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def fns(tree) -> dict:
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def fn_block(text: str, name: str) -> str:
    tree = py_tree_text(text)
    node = fns(tree).get(name)
    if node is None:
        return ""
    lines = text.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def endpoints(tree) -> list:
    """[(method, path, endpoint name)] for every @router.<verb> endpoint."""
    out = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and isinstance(deco.func.value, ast.Name)
                and deco.func.value.id == "router"
                and deco.args
            ):
                out.append((deco.func.attr.lower(), deco.args[0].value, node.name))
    return out


def module_literal_consts(text: str) -> dict:
    """{Name: literal value} for module-level literal assignments.

    Containers (Tuple/Dict/List) and scalars both count: the refusal phrase is a
    parenthesised string, so accepting only containers would have made the
    NO_MEDICAL_ADVICE_PHRASE contract untestable.
    """
    out = {}
    tree = py_tree_text(text)
    if tree is None:
        return out
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not isinstance(
            node.value, (ast.Tuple, ast.Dict, ast.List, ast.Constant)
        ):
            continue
        try:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                out[target.id] = ast.literal_eval(node.value)
        except ValueError:
            continue
    return out


def module_import_roots(text: str) -> set:
    roots = set()
    tree = py_tree_text(text)
    if tree is None:
        return roots
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def model_block(text: str, cls: str) -> str:
    return text.split(f"class {cls}(Base):", 1)[1].split("\n    def __repr__", 1)[0]


def sql_table_block(text: str, table: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {table} ("
    if marker not in text:
        marker = f"CREATE TABLE {table} ("
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("\n);", 1)[0]


# The pure service — behaviour-tested. Absent at RED.
try:
    from app.services import medical_info as mi  # noqa: E402

    HAVE_SVC = True
except ImportError:  # pragma: no cover - RED state
    mi = None
    HAVE_SVC = False


def row(
    *,
    product_id="p-1",
    language="en",
    category="dosing",
    version=1,
    body="Take one tablet twice a day after food.",
    active=True,
    response_id="r-1",
):
    """A product_responses row as a plain dict (the service takes rows, not ORM)."""
    return {
        "id": response_id,
        "product_id": product_id,
        "language": language,
        "category": category,
        "response_body": body,
        "version": version,
        "is_active": active,
        "approved_by": "medical.affairs@example.in",
        "approved_at": "2026-09-01T00:00:00+00:00",
    }


LABEL = {
    "indication": "Paracetamol 500 mg is indicated for relief of mild to moderate pain.",
    "dosage": "Adults: 500 mg to 1 g every 4 to 6 hours; maximum 4 g in 24 hours.",
    "adverse_reactions": "Commonly reported: nausea, rash.",
}


# ─── A. Module shape + import purity ────────────────────────────────────────

STDLIB_ROOTS = {
    "re",
    "typing",
}


class TestModuleShape(unittest.TestCase):
    def test_service_module_exists(self):
        self.assertTrue(MI_SVC.exists(), "app/services/medical_info.py missing")

    def test_service_module_is_stdlib_only(self):
        roots = module_import_roots(read(MI_SVC))
        allowed = STDLIB_ROOTS | {"app"}
        self.assertTrue(roots, "no imports parsed")
        self.assertEqual(
            set(),
            roots - allowed,
            f"medical_info.py must be stdlib-only + repo modules; got {sorted(roots - allowed)}",
        )

    def test_module_is_class_free(self):
        tree = py_tree_text(read(MI_SVC))
        classes = [
            n.name
            for n in ast.walk(tree or ast.Module(body=[], type_ignores=[]))
            if isinstance(n, ast.ClassDef)
        ]
        self.assertEqual([], classes, "medical_info.py must stay class-free")

    def test_three_service_functions_present(self):
        names = set(fns(py_tree_text(read(MI_SVC))))
        for fn in (
            "next_version",
            "lookup_approved_response",
            "answer_medical_inquiry",
        ):
            self.assertIn(fn, names, f"services.medical_info missing {fn}")

    def test_answer_source_vocabulary(self):
        consts = module_literal_consts(read(MI_SVC))
        self.assertEqual(
            ("approved_content", "label", "no_medical_advice"),
            consts.get("ANSWER_SOURCES"),
        )

    def test_no_medical_advice_phrase_is_one_constant(self):
        consts = module_literal_consts(read(MI_SVC))
        phrase = consts.get("NO_MEDICAL_ADVICE_PHRASE")
        self.assertTrue(phrase, "NO_MEDICAL_ADVICE_PHRASE constant missing")
        self.assertIn("NO_MEDICAL_ADVICE", phrase)
        self.assertNotIn(
            "advice", phrase.lower().replace("no_medical_advice", ""),
            "the refusal phrase must not read as medical advice",
        )


# ─── B. next_version — version semantics ─────────────────────────────────────


class TestNextVersion(unittest.TestCase):
    def test_table(self):
        cases = (([], 1), ([1], 2), ([1, 2, 3], 4))
        for existing, expected in cases:
            with self.subTest(existing=existing):
                self.assertEqual(expected, mi.next_version(existing))

    def test_gaps_and_dupes_are_ignored(self):
        self.assertEqual(6, mi.next_version([1, 5, 5]))
        self.assertEqual(1, mi.next_version([]))

    def test_junk_entries_never_lower_the_version(self):
        self.assertEqual(3, mi.next_version([1, 2, None, "x"]))


# ─── C. lookup_approved_response — language chain + version supersession ─────


class TestLookupApprovedResponse(unittest.TestCase):
    def test_exact_language_hit(self):
        rows = [row(language="ta", body="தினமும் ஒரு மாத்திரை"), row(language="en")]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "ta")
        self.assertTrue(hit["found"])
        self.assertEqual("தினமும் ஒரு மாத்திரை", hit["response_body"])
        self.assertEqual(1, hit["version"])
        self.assertEqual("ta", hit["language"])
        self.assertEqual("exact", hit["language_match"])

    def test_falls_back_to_english(self):
        rows = [row(language="en", body="English approved text")]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "hi")
        self.assertTrue(hit["found"])
        self.assertEqual("English approved text", hit["response_body"])
        self.assertEqual("fallback", hit["language_match"])

    def test_falls_back_to_another_available_product_language(self):
        """No exact content, no English, but the product IS approved in Tamil."""
        rows = [row(language="ta", body="Tamil approved text")]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "hi")
        self.assertTrue(hit["found"])
        self.assertEqual("ta", hit["language"])
        self.assertEqual("product_available", hit["language_match"])

    def test_nothing_approved_is_found_false(self):
        self.assertFalse(mi.lookup_approved_response([], "p-1", "dosing", "en")["found"])
        self.assertFalse(
            mi.lookup_approved_response(
                [row(category="storage")], "p-1", "dosing", "en"
            )["found"]
        )

    def test_other_product_is_never_answered_from(self):
        rows = [row(product_id="p-2")]
        self.assertFalse(mi.lookup_approved_response(rows, "p-1", "dosing", "en")["found"])

    def test_inactive_rows_are_never_answered_from(self):
        rows = [row(active=False)]
        self.assertFalse(mi.lookup_approved_response(rows, "p-1", "dosing", "en")["found"])

    def test_highest_active_version_wins(self):
        rows = [
            row(version=1, body="v1"),
            row(version=2, body="v2"),
            row(version=3, body="v3"),
        ]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "en")
        self.assertEqual("v3", hit["response_body"])
        self.assertEqual(3, hit["version"])

    def test_new_version_supersedes_the_old_one(self):
        """Pushing v2 deactivates v1: the answer changes, and v1 stays readable."""
        rows = [row(version=1, body="old", active=False), row(version=2, body="new")]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "en")
        self.assertEqual("new", hit["response_body"])
        self.assertEqual(2, hit["version"])

    def test_inactive_newer_version_does_not_bury_an_active_older_one(self):
        """Withdrawn v2 must not blank out a product that still has approved v1."""
        rows = [
            row(version=1, body="still approved"),
            row(version=2, body="withdrawn", active=False),
        ]
        hit = mi.lookup_approved_response(rows, "p-1", "dosing", "en")
        self.assertTrue(hit["found"])
        self.assertEqual("still approved", hit["response_body"])
        self.assertEqual(1, hit["version"])

    def test_blank_body_is_not_approved_content(self):
        rows = [row(body="   ")]
        self.assertFalse(mi.lookup_approved_response(rows, "p-1", "dosing", "en")["found"])

    def test_uuid_products_match_as_strings(self):
        pid = "6f1d2a44-1f2b-4a1e-9d0e-2b3c4d5e6f70"
        rows = [row(product_id=pid)]
        self.assertTrue(mi.lookup_approved_response(rows, pid, "dosing", "en")["found"])

    def test_lookup_is_deterministic(self):
        rows = [row(language="ta"), row(language="en"), row(language="te")]
        first = mi.lookup_approved_response(rows, "p-1", "dosing", "hi")
        second = mi.lookup_approved_response(list(reversed(rows)), "p-1", "dosing", "hi")
        self.assertEqual(first, second, "row order must not change the answer")


# ─── D. answer_medical_inquiry — approved content, label, refusal ────────────


class TestAnswerMedicalInquiry(unittest.TestCase):
    def _inquiry(self, **overrides) -> dict:
        fields = {
            "id": "mi-1",
            "product_id": "p-1",
            "category": "dosing",
            "language": "en",
            "question_text": "How many tablets a day should I take?",
        }
        fields.update(overrides)
        return fields

    def test_approved_content_is_returned_verbatim(self):
        approved = "Take one tablet twice a day after food. Approved response v3."
        out = mi.answer_medical_inquiry(self._inquiry(), [row(version=3, body=approved)], None)
        self.assertEqual("approved_content", out["source"])
        self.assertEqual(approved, out["answer"])
        self.assertEqual(3, out["version"])
        self.assertTrue(out["reasoning"], "every answer carries its reasoning")
        self.assertFalse(out["suggest_report_to_pv"])

    def test_label_answers_when_no_kb_row_exists(self):
        out = mi.answer_medical_inquiry(self._inquiry(category="indication"), [], LABEL)
        self.assertEqual("label", out["source"])
        self.assertEqual(LABEL["indication"], out["answer"])
        self.assertIsNone(out["version"], "label text is not a versioned KB response")

    def test_label_dose_answers_dosing_category(self):
        out = mi.answer_medical_inquiry(self._inquiry(), [], LABEL)
        self.assertEqual("label", out["source"])
        self.assertIn("500 mg", out["answer"])

    def test_kb_gap_is_no_medical_advice(self):
        out = mi.answer_medical_inquiry(
            self._inquiry(category="pregnancy"), [], LABEL
        )
        self.assertEqual("no_medical_advice", out["source"])
        self.assertEqual(mi.NO_MEDICAL_ADVICE_PHRASE, out["answer"])
        self.assertIsNone(out["version"])
        self.assertIn("pregnancy", out["reasoning"])

    def test_no_label_and_no_kb_is_no_medical_advice(self):
        out = mi.answer_medical_inquiry(self._inquiry(), [], None)
        self.assertEqual("no_medical_advice", out["source"])
        self.assertEqual(mi.NO_MEDICAL_ADVICE_PHRASE, out["answer"])

    def test_blank_label_section_cannot_manufacture_an_answer(self):
        out = mi.answer_medical_inquiry(
            self._inquiry(category="storage"), [], {"storage": "  "}
        )
        self.assertEqual("no_medical_advice", out["source"])
        self.assertEqual(mi.NO_MEDICAL_ADVICE_PHRASE, out["answer"])

    def test_kb_beats_label_for_the_same_category(self):
        rows = [row(category="dosing", body="Approved KB dosing text")]
        out = mi.answer_medical_inquiry(self._inquiry(), rows, LABEL)
        self.assertEqual("approved_content", out["source"])
        self.assertEqual("Approved KB dosing text", out["answer"])

    def test_ae_flavoured_inquiry_is_flagged_for_pv_not_answered_from_speculation(self):
        """A question that carries AE content gets the refusal PLUS the net."""
        out = mi.answer_medical_inquiry(
            self._inquiry(
                category="other",
                question_text="I broke out in a rash after taking it",
            ),
            [],
            LABEL,
        )
        self.assertEqual("no_medical_advice", out["source"])
        self.assertTrue(out["suggest_report_to_pv"], "AE content must reach the PV net")
        self.assertIn(mi.NO_MEDICAL_ADVICE_PHRASE, out["answer"])
        self.assertIn(mi.REPORTABLE_HINT, out["answer"])
        self.assertTrue(out["report_reasons"], "the flag must name what it saw")

    def test_ae_flavoured_inquiry_still_answers_from_approved_content_and_flags(self):
        out = mi.answer_medical_inquiry(
            self._inquiry(
                category="side_effect",
                question_text="I got a rash after the tablet, is this known?",
            ),
            [row(category="side_effect", body="Rash is listed in the approved label.")],
            LABEL,
        )
        self.assertEqual("approved_content", out["source"])
        self.assertTrue(out["suggest_report_to_pv"], "an approved answer never hides an AE")

    def test_pqc_flavoured_inquiry_is_flagged(self):
        out = mi.answer_medical_inquiry(
            self._inquiry(question_text="the strip arrived broken and the tablets are loose"),
            [],
            LABEL,
        )
        self.assertTrue(out["suggest_report_to_pv"])

    def test_pure_factual_question_is_not_flagged(self):
        out = mi.answer_medical_inquiry(
            self._inquiry(), [row()], LABEL
        )
        self.assertFalse(out["suggest_report_to_pv"])
        self.assertEqual([], out["report_reasons"])

    def test_answer_never_contains_the_forbidden_advice_phrases(self):
        """The three answers are approved text, label text or the refusal."""
        out = mi.answer_medical_inquiry(self._inquiry(category="other"), [], LABEL)
        self.assertEqual(mi.NO_MEDICAL_ADVICE_PHRASE, out["answer"])

    def test_determinism_same_rows_same_answer(self):
        rows = [row(version=1, body="a"), row(version=2, body="b"), row(language="hi", body="c")]
        fields = self._inquiry(language="hi")
        first = mi.answer_medical_inquiry(fields, rows, LABEL)
        second = mi.answer_medical_inquiry(fields, list(reversed(rows)), LABEL)
        self.assertEqual(first, second)

    def test_no_mutation_of_input_rows(self):
        rows = [row(version=1), row(version=2)]
        snapshot = [dict(r) for r in rows]
        mi.answer_medical_inquiry(self._inquiry(), rows, LABEL)
        self.assertEqual(snapshot, rows, "the service is pure: it never writes to rows")

    def test_missing_product_id_is_not_answered_from_another_product(self):
        out = mi.answer_medical_inquiry(self._inquiry(product_id=None), [row()], LABEL)
        self.assertEqual("no_medical_advice", out["source"])


# ─── E. Schema: the product_responses table ─────────────────────────────────


class TestKbSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCHEMA_SQL)

    def test_table_created_idempotently(self):
        self.assertIn(
            f"CREATE TABLE IF NOT EXISTS {KB_TABLE} ",
            self.text,
            f"missing idempotent CREATE TABLE for {KB_TABLE}",
        )

    def test_columns(self):
        block = sql_table_block(self.text, KB_TABLE)
        self.assertTrue(block, f"{KB_TABLE} table missing")
        for column in (
            "id UUID PRIMARY KEY",
            "clinic_id UUID NOT NULL REFERENCES clinics(id) ON DELETE CASCADE",
            "product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE",
            "language TEXT NOT NULL",
            "category TEXT NOT NULL",
            "response_body TEXT NOT NULL",
            "version INTEGER NOT NULL DEFAULT 1",
            "is_active BOOLEAN DEFAULT TRUE",
            "approved_by TEXT",
            "approved_at TIMESTAMPTZ",
            "created_at TIMESTAMPTZ DEFAULT NOW()",
            "updated_at TIMESTAMPTZ DEFAULT NOW()",
        ):
            self.assertIn(column, block, f"{KB_TABLE} missing {column}")

    def test_version_uniqueness_constraint(self):
        block = sql_table_block(self.text, KB_TABLE)
        self.assertIn("UNIQUE (product_id, language, category, version)", block)

    def test_lookup_index(self):
        self.assertIn("idx_product_responses_lookup", self.text)

    def test_rls_enabled_and_forced(self):
        self.assertIn(f"ALTER TABLE {KB_TABLE} ENABLE ROW LEVEL SECURITY", self.text)
        self.assertIn(f"ALTER TABLE {KB_TABLE} FORCE ROW LEVEL SECURITY", self.text)

    def test_manage_policy_mirrors_payments_manage(self):
        policy = f"CREATE POLICY {KB_TABLE}_manage"
        self.assertIn(policy, self.text, f"missing {KB_TABLE}_manage policy")
        block = self.text.split(policy, 1)[1].split("CREATE POLICY", 1)[0]
        self.assertIn("clinic_id IN (", block, "clinic scope missing")
        self.assertIn("auth.uid()", block, "membership scope missing")
        self.assertIn("app.service_request", block, "service bypass missing")

    def test_grants_for_the_runtime_roles(self):
        self.assertIn(f"GRANT ALL ON {KB_TABLE} TO authenticated", self.text)
        self.assertIn(f"GRANT ALL ON {KB_TABLE} TO medicall_app", self.text)

    def test_live_schema_guard_still_passes(self):
        """Execute test_schema_wellformed's own check over the edited file."""
        spec = importlib.util.spec_from_file_location("t_schema_guard", SCHEMA_GUARD)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = unittest.TextTestRunner(stream=io.StringIO()).run(
            unittest.defaultTestLoader.loadTestsFromModule(module)
        )
        self.assertTrue(
            result.wasSuccessful(),
            "schema well-formedness guard failed:\n"
            + "\n".join(str(t) for t in (result.failures + result.errors)),
        )


# ─── F. ORM model + repository helpers ──────────────────────────────────────


class TestKbOrm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(POSTGRES)

    def test_model_typed(self):
        self.assertIn(f"class {KB_MODEL}(Base):", self.text, f"missing model {KB_MODEL}")
        block = model_block(self.text, KB_MODEL)
        self.assertIn(f'__tablename__ = "{KB_TABLE}"', block)
        self.assertIn("mapped_column", block)

    def test_model_fks_and_columns(self):
        block = model_block(self.text, KB_MODEL)
        self.assertIn('ForeignKey("clinics.id", ondelete="CASCADE")', block)
        self.assertIn('ForeignKey("products.id", ondelete="CASCADE")', block)
        self.assertIn("response_body: Mapped[str]", block)
        self.assertIn("version: Mapped[int]", block)
        self.assertIn("is_active: Mapped[bool]", block)
        self.assertIn("approved_by", block)
        self.assertIn("approved_at", block)

    def test_repository_helpers_exist(self):
        names = set(fns(py_tree_text(self.text)))
        for fn in KB_REPO_FNS + MI_REPO_FNS:
            self.assertIn(fn, names, f"postgres.py missing repository helper {fn}")

    def test_latest_approved_response_filters_active_and_orders_by_version(self):
        block = fn_block(self.text, "latest_approved_response")
        self.assertIn("is_active", block)
        self.assertIn("desc", block.lower(), "the highest active version must win")


# ─── G. Router: KB routes, gating, audit, no auto-case ──────────────────────


class TestKbRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PV_ROUTER)
        cls.tree = py_tree_text(cls.text)

    def test_router_exists(self):
        self.assertTrue(PV_ROUTER.exists(), "app/api/pv.py missing")

    def test_kb_routes_present(self):
        found = {(verb, path) for verb, path, _ in endpoints(self.tree)}
        for route in KB_ROUTES:
            self.assertIn(route, found, f"missing pv route {route}")

    def test_kb_routes_identity_gated(self):
        for name in KB_IDENTITY_GATED:
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertTrue(block, f"{name} missing from app/api/pv.py")
                self.assertIn("get_current_user", block, f"{name} must be identity-gated")
                self.assertNotIn("WEBHOOK_SERVICE_TOKEN", block)

    def test_router_docstring_lists_the_kb_routes(self):
        module_doc = ast.get_docstring(self.tree) or ""
        self.assertIn("/responses", module_doc, "the route table must name /responses")
        self.assertIn(
            "/inquiries/{inquiry_id}/answer",
            module_doc,
            "the route table must name the answer route",
        )

    def test_response_create_is_versioned_and_deactivates_older(self):
        block = fn_block(self.text, "create_response_ep")
        self.assertIn("next_version", block, "a new response is the next version")
        self.assertIn("update_response_status", block, "the old version is superseded")
        self.assertIn("create_response", block)
        self.assertIn("is_active", block)

    def test_answer_route_runs_the_pure_service_and_persists(self):
        block = fn_block(self.text, "answer_medical_inquiry_ep")
        self.assertIn("answer_medical_inquiry", block)
        self.assertIn("update_medical_inquiry_answer", block, "the answer is persisted")
        self.assertIn("create_compliance_event", block, "the answer is audited")

    def test_answer_route_audits_the_pv_inquiry_answered_event(self):
        self.assertIn("pv_inquiry_answered", self.text)
        block = fn_block(self.text, "answer_medical_inquiry_ep")
        self.assertIn("PV_INQUIRY_ANSWERED_EVENT", block)

    def test_answer_route_never_creates_a_pv_case(self):
        """The MI answer path flags a reportable item; the intake path owns it."""
        block = fn_block(self.text, "answer_medical_inquiry_ep")
        for fn in ("create_adverse_event", "create_quality_complaint", "create_pv_case"):
            self.assertNotIn(fn, block, f"{fn} must not run on the answer path")

    def test_refusal_is_persisted_too(self):
        """A NO_MEDICAL_ADVICE answer is still the record, and still audited."""
        block = fn_block(self.text, "answer_medical_inquiry_ep")
        self.assertIn("no_medical_advice", block, "the refusal branch is explicit")
        self.assertIn("update_medical_inquiry_answer", block)


if __name__ == "__main__":
    unittest.main()
