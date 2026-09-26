"""Coding layer: dictionary seam + WHO-UMC capture + expedited export gate (2C).

spec-micc-pv-phase2.md slice 2C. The slice brief and the spec agree on the scope
this suite holds: MedDRA and WHODrug are LICENSED dictionaries (subscription),
so what ships here is the SEAM plus the parts that do not need the licence —

  * a pluggable DictionaryBackend interface and a tiny built-in fixture lexicon
    (so coding is unit-testable today and a licensed backend can be injected
    later without touching a single call site),
  * WHO-UMC causality CAPTURE — the reporter's and the reviewer's own
    assessments, validated against the scale, stored verbatim, never computed,
  * the human-in-the-loop gate: an EXPEDITED case (serious, and not expected per
    the approved label) cannot reach export without a reviewer stamp.

Same house pattern as test_pv_module.py / test_e2b.py / test_medical_info.py: the
pure stdlib service (app/services/coding.py) is imported and BEHAVIOUR-tested
with no database, no FastAPI, no network and no dictionary licence; the schema /
ORM / router contracts are structural AST + text assertions; and the live
postgres_schema.sql well-formedness guard is executed as a test.

RED before implementation (2026-09-26): no app/services/coding.py, no
adverse_events reviewer-causality columns, no /cases/{case_id}/coding or
/cases/{case_id}/causality route, and no reviewer gate on the E2B export.

Run: py -3.14 -m unittest discover -s tests -p "test_coding.py"   (from backend/)
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
SCHEMA_GUARD = BACKEND / "tests" / "test_schema_wellformed.py"
POSTGRES = DB_DIR / "postgres.py"
PV_ROUTER = API_DIR / "pv.py"
CODING_SVC = SERVICES / "coding.py"
E2B_SVC = SERVICES / "e2b.py"
PV_SVC = SERVICES / "pharmacovigilance.py"

CODING_ROUTES = {
    ("post", "/cases/{case_id}/coding"),
    ("post", "/cases/{case_id}/causality"),
}
CODING_IDENTITY_GATED = ("code_pv_case_ep", "capture_pv_case_causality_ep")
PV_CODED_EVENT = "pv_case_coded"
PV_CAUSALITY_EVENT = "pv_causality_captured"

# The columns slice 2C adds to adverse_events (ALTER TABLE, not a new table).
AE_CODING_COLUMNS = (
    "coding_json",
    "reporter_causality",
    "reviewer_causality",
    "reviewed_by",
    "reviewed_at",
)
AE_REPO_FNS = ("update_adverse_event_coding", "update_adverse_event_causality")

# Every code the fixture lexicon may carry. A real MedDRA code is 8 digits and a
# real WHODrug code is an ATC-ish number, so a FIX prefix makes it impossible to
# ship licensed content by accident — asserted below, over every fixture entry.
FIXTURE_CODE_PREFIX = "FIX"


# ─── AST / text helpers (mirrors test_e2b.py + test_medical_info.py) ────────
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
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
    return out


def fn_block(text: str, name: str) -> str:
    node = fns(py_tree_text(text)).get(name)
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


def module_literal_consts(text: str) -> dict:
    """{Name: literal value} for module-level literal assignments."""
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


def model_block(text: str, cls: str) -> str:
    parts = text.split(f"class {cls}(Base):", 1)
    if len(parts) < 2:
        return ""
    return parts[1].split("\n    def __repr__", 1)[0]


def ddl_statements(text: str) -> list:
    """Every top-level statement, joined across continuation lines.

    The schema file writes multi-line CREATE INDEX statements, so a naive
    one-line scan would miss them; this folds a statement into the next one
    until its ';' appears.
    """
    out = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.split("--", 1)[0].rstrip()
        if not line.strip():
            continue
        buffer = f"{buffer} {line.strip()}".strip() if buffer else line.strip()
        if buffer.endswith(";"):
            out.append(buffer)
            buffer = ""
    return out


# ─── The pure service — behaviour-tested. Absent at RED. ────────────────────
try:
    from app.services import coding  # noqa: E402
    from app.services import e2b as e2b_mod  # noqa: E402
    from app.services import pharmacovigilance as pv  # noqa: E402

    HAVE_SVC = True
except ImportError:  # pragma: no cover - RED state
    coding = None
    e2b_mod = None
    pv = None
    HAVE_SVC = False


def require_coding():
    """RED-state guard: the behaviour classes ERROR (never skip) without the module."""
    if not HAVE_SVC:
        raise AssertionError("app/services/coding.py is missing (RED state)")


class StubDictionary(coding.DictionaryBackend if HAVE_SVC else object):
    """A second backend, to prove the seam swaps without touching call sites.

    Stands in for a licensed MedDRA/WHODrug client: it answers from its own
    tables and is otherwise identical from the caller's point of view.
    """

    PTS = {
        "fixture rash": {
            "code": "LIC-9001",
            "pt": "Licensed rash term",
            "soc": "LICSOC-1",
            "hlt": "LICHLT-1",
        },
    }
    DRUGS = {"licensed product": {"code": "LIC-8001", "name": "Licensed product"}}

    def name(self):
        return "stub-licensed"

    def lookup_pt(self, term):
        return self.PTS.get(str(term or "").strip().lower())

    def lookup_drug(self, term):
        return self.DRUGS.get(str(term or "").strip().lower())


class EmptyDictionary(coding.DictionaryBackend if HAVE_SVC else object):
    """A backend that knows nothing: every lookup is a miss."""

    def name(self):
        return "empty"

    def lookup_pt(self, term):
        return None

    def lookup_drug(self, term):
        return None


class MalformedDictionary(coding.DictionaryBackend if HAVE_SVC else object):
    """A backend that returns an incomplete entry — must fail CLOSED."""

    def name(self):
        return "malformed"

    def lookup_pt(self, term):
        return {"code": "LIC-9002", "pt": "no hierarchy at all"}

    def lookup_drug(self, term):
        return {"code": "", "name": ""}


class DictionaryRegistryMixin(unittest.TestCase):
    """Restores the module registry so a swap can never leak into another test.

    The RED-state guard matches test_e2b.py: behaviour classes ERROR, never skip.
    """

    def setUp(self):
        require_coding()
        self._saved = coding.get_dictionary()
        self.addCleanup(coding.register_dictionary, self._saved)


# ─── Fixtures ───────────────────────────────────────────────────────────────
def case(**overrides) -> dict:
    """One complete AE case row, shaped exactly like api/pv.py's _case_row.

    Defaults to an EXPEDITED case that already carries a reviewer stamp, so a
    test only has to state the field it is exercising.
    """
    row = {
        "id": "11111111-1111-4111-8111-111111111111",
        "case_type": "AE",
        "clinic_id": "22222222-2222-4222-8222-222222222222",
        "product_id": "44444444-4444-4444-8444-444444444444",
        "product_name": "fixamet 500 mg",
        "event_text": "itching",
        "seriousness_flags": ["hospitalisation", "medically_important"],
        "expectedness": "unexpected",
        "e2b_minimum_met": True,
        "status": "new",
        "reviewer_causality": "possible",
        "reviewed_by": "safety.physician@medicall.in",
        "reviewed_at": "2026-09-23T09:30:00+00:00",
    }
    row.update(overrides)
    return row


def unstamped(**overrides) -> dict:
    """An expedited case with NO reviewer stamp (the refused case).

    Overrides land AFTER the blanks, so a test can also blank one field it did
    not otherwise name — passing the same field twice would otherwise be a
    TypeError, not a test.
    """
    row = case(reviewer_causality="", reviewed_by="", reviewed_at="")
    row.update(overrides)
    return row


# ─── A. Module shape + import purity ────────────────────────────────────────
STDLIB_ROOTS = {
    "datetime",
    "sys",
    "typing",
}

# Nothing in the coding layer may open a socket: a licensed dictionary client is
# deployment configuration, and the module that decides a case is exportable must
# be provably offline.
NETWORK_ROOTS = {
    "asyncio",
    "ftplib",
    "http",
    "httpx",
    "httplib",
    "requests",
    "smtplib",
    "socket",
    "ssl",
    "telnetlib",
    "urllib",
    "urllib3",
    "webbrowser",
    "xmlrpc",
}


class TestModuleShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(CODING_SVC)

    def test_service_module_exists(self):
        self.assertTrue(CODING_SVC.exists(), "app/services/coding.py missing")

    def test_service_module_is_stdlib_only(self):
        roots = module_import_roots(self.text)
        allowed = STDLIB_ROOTS | {"app"}
        self.assertTrue(roots, "no imports parsed")
        self.assertEqual(
            set(),
            roots - allowed,
            f"coding.py must be stdlib-only + repo modules; got {sorted(roots - allowed)}",
        )

    def test_no_network_imports(self):
        roots = module_import_roots(self.text)
        for banned in sorted(roots & NETWORK_ROOTS):
            self.fail(f"coding.py must not import {banned}: no vendor SDK, no socket")

    def test_only_the_phase1_pv_service_is_imported(self):
        """Seriality + expectedness are the Phase-1 rules; 2C reuses, never copies."""
        tree = py_tree_text(self.text)
        app_modules = {
            node.module
            for node in ast.walk(tree or ast.Module(body=[], type_ignores=[]))
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "app"
        }
        self.assertTrue(app_modules, "coding.py must import the Phase-1 service")
        for module in app_modules:
            with self.subTest(module):
                self.assertEqual({"app.services.pharmacovigilance"}, app_modules)

    def test_public_surface(self):
        names = set(fns(py_tree_text(self.text)))
        for name in (
            "DictionaryBackend",
            "FixtureDictionary",
            "register_dictionary",
            "get_dictionary",
            "code_case",
            "causality_capture",
            "is_expedited",
            "reviewer_stamp",
            "missing_review_stamp",
        ):
            with self.subTest(name):
                self.assertIn(name, names, f"coding.py missing {name}")

    def test_module_states_the_licensed_content_position(self):
        """The one thing a reader must not have to guess: what is NOT in here."""
        doc = (ast.get_docstring(py_tree_text(self.text)) or "").lower()
        for token in ("licensed", "meddra", "whodrug", "register_dictionary"):
            with self.subTest(token):
                self.assertIn(token, doc)


# ─── B. The dictionary interface ────────────────────────────────────────────
class TestDictionaryBackend(DictionaryRegistryMixin):
    def test_base_class_is_an_interface(self):
        base = coding.DictionaryBackend()
        for call in (
            lambda: base.lookup_pt("itching"),
            lambda: base.lookup_drug("fixamet"),
            lambda: base.name(),
        ):
            with self.subTest(call):
                with self.assertRaises(NotImplementedError):
                    call()

    def test_fixture_declares_the_interface(self):
        self.assertTrue(issubclass(coding.FixtureDictionary, coding.DictionaryBackend))
        for name in ("lookup_pt", "lookup_drug"):
            self.assertTrue(callable(getattr(coding.FixtureDictionary, name, None)))

    def test_every_returned_entry_has_exactly_the_contract_fields(self):
        entry = coding.FixtureDictionary().lookup_pt("itching")
        self.assertEqual(set(coding.PT_ENTRY_FIELDS), set(entry))
        self.assertTrue(all(isinstance(v, str) and v for v in entry.values()))
        drug = coding.FixtureDictionary().lookup_drug("fixamet")
        self.assertEqual(set(coding.DRUG_ENTRY_FIELDS), set(drug))

    def test_lookup_is_case_and_whitespace_insensitive(self):
        lexicon = coding.FixtureDictionary()
        for term in ("ITCHING", "  Itching  ", "itching"):
            with self.subTest(term):
                self.assertIsNotNone(lexicon.lookup_pt(term))

    def test_fixture_misses_are_none_not_guesses(self):
        lexicon = coding.FixtureDictionary()
        for term in ("", "   ", "a term nobody licensed", "itchingly"):
            with self.subTest(repr(term)):
                self.assertIsNone(lexicon.lookup_pt(term))
                self.assertIsNone(lexicon.lookup_drug(term))

    def test_no_licensed_dictionary_content_ships(self):
        """Fixture codes are synthetic: no 8-digit MedDRA, no WHODrug number."""
        for term, entry in coding.FIXTURE_PT_TERMS.items():
            with self.subTest(term):
                self.assertTrue(
                    entry["code"].startswith(FIXTURE_CODE_PREFIX),
                    f"fixture PT code {entry['code']} is not fixture content",
                )
        for term, entry in coding.FIXTURE_DRUG_TERMS.items():
            with self.subTest(term):
                self.assertTrue(entry["code"].startswith(FIXTURE_CODE_PREFIX))
                self.assertFalse(
                    entry["code"].isdigit(), "a licensed drug code is a number"
                )


# ─── C. The registry — how the licensed dictionary is swapped ──────────────
class TestDictionaryRegistry(DictionaryRegistryMixin):
    def test_default_is_the_fixture(self):
        self.assertIsInstance(coding.get_dictionary(), coding.FixtureDictionary)

    def test_get_dictionary_is_stable(self):
        self.assertIs(coding.get_dictionary(), coding.get_dictionary())

    def test_register_swaps_the_backend_for_every_call_site(self):
        coding.register_dictionary(StubDictionary())
        self.assertIsInstance(coding.get_dictionary(), StubDictionary)
        result = coding.code_case(case(event_text="fixture rash"))
        self.assertTrue(result["coded"])
        self.assertEqual("Licensed rash term", result["event"]["pt"])
        self.assertEqual("stub-licensed", result["dictionary"])
        # ... and the fixture lexicon is unreachable until it is registered back.
        self.assertFalse(coding.code_case(case())["coded"])

    def test_register_none_restores_the_default_fixture(self):
        coding.register_dictionary(StubDictionary())
        coding.register_dictionary(None)
        self.assertIsInstance(coding.get_dictionary(), coding.FixtureDictionary)

    def test_register_rejects_anything_that_is_not_a_backend(self):
        for bad in (object(), "meddra", 42, {"lookup_pt": "x"}):
            with self.subTest(repr(bad)):
                with self.assertRaises(TypeError):
                    coding.register_dictionary(bad)

    def test_register_returns_the_backend(self):
        stub = StubDictionary()
        self.assertIs(stub, coding.register_dictionary(stub))


# ─── D. code_case — mapping, never guessing ─────────────────────────────────
class TestCodeCase(DictionaryRegistryMixin):
    def test_dictionary_hit_maps_the_event_term(self):
        result = coding.code_case(case(event_text="itching"))
        self.assertTrue(result["coded"])
        self.assertEqual("", result["reason"])
        self.assertEqual("FIXPT-1001", result["event"]["code"])
        self.assertEqual("Itching (fixture term)", result["event"]["pt"])
        self.assertTrue(result["event"]["soc"].startswith(FIXTURE_CODE_PREFIX))
        self.assertTrue(result["event"]["hlt"].startswith(FIXTURE_CODE_PREFIX))
        self.assertEqual(coding.FIXTURE_DICTIONARY_NAME, result["dictionary"])

    def test_hit_maps_the_suspect_drug(self):
        result = coding.code_case(case(product_name="fixamet 500 mg"))
        self.assertTrue(result["coded"])
        self.assertTrue(result["drug_coded"])
        self.assertTrue(result["drug"]["code"].startswith(FIXTURE_CODE_PREFIX))
        self.assertTrue(result["drug"]["name"])

    def test_miss_is_not_in_dictionary_and_never_a_guess(self):
        result = coding.code_case(case(event_text="a term nobody licensed"))
        self.assertFalse(result["coded"])
        self.assertEqual(coding.CODING_NOT_IN_DICTIONARY, result["reason"])
        self.assertIsNone(result["event"])
        self.assertIsNone(result["drug"])
        self.assertFalse(result["drug_coded"])
        self.assertNotIn("code", result)

    def test_miss_carries_no_code_at_all(self):
        """A refusal must not smuggle a plausible-looking code out."""
        result = coding.code_case(case(event_text="", product_name=""))
        self.assertFalse(result["coded"])
        self.assertEqual(coding.CODING_NOT_IN_DICTIONARY, result["reason"])
        self.assertIsNone(result["event"])
        self.assertIsNone(result["drug"])

    def test_drug_hit_alone_does_not_code_the_case(self):
        """A coded drug with an uncoded event is not a coded case."""
        result = coding.code_case(case(event_text="not in the lexicon"))
        self.assertFalse(result["coded"])
        self.assertFalse(result["drug_coded"])

    def test_malformed_backend_entry_fails_closed(self):
        coding.register_dictionary(MalformedDictionary())
        result = coding.code_case(case())
        self.assertFalse(result["coded"])
        self.assertIsNone(result["event"])
        self.assertFalse(result["drug_coded"])

    def test_empty_backend_is_all_misses(self):
        coding.register_dictionary(EmptyDictionary())
        result = coding.code_case(case())
        self.assertFalse(result["coded"])
        self.assertEqual(coding.CODING_NOT_IN_DICTIONARY, result["reason"])

    def test_is_pure_and_deterministic(self):
        row = case()
        before = dict(row)
        first = coding.code_case(row)
        second = coding.code_case(row)
        self.assertEqual(first, second)
        self.assertEqual(before, row, "code_case must not mutate the case row")
        self.assertEqual(coding.code_case(case()), first)

    def test_blank_case_never_raises(self):
        for blank in ({}, {"event_text": None}, {"event_text": 5}):
            with self.subTest(repr(blank)):
                result = coding.code_case(blank)
                self.assertFalse(result["coded"])


# ─── E. causality_capture — WHO-UMC, captured never assigned ────────────────
class TestCausalityCapture(DictionaryRegistryMixin):
    def test_who_umc_scale_constant(self):
        self.assertEqual(
            (
                "certain",
                "probable",
                "possible",
                "unlikely",
                "conditional",
                "unassessable",
                "not_related",
            ),
            tuple(coding.WHO_UMC_CAUSALITY_CATEGORIES),
        )

    def test_reporter_and_reviewer_both_captured(self):
        captured = coding.causality_capture(
            reporters_assessment="Probable",
            reviewer_assessment="possible",
            reviewer="dr.iyer@medicall.in",
            reviewed_at="2026-09-26T09:30:00+00:00",
        )
        self.assertTrue(captured["valid"])
        self.assertTrue(captured["captured"])
        self.assertEqual("", captured["error"])
        self.assertEqual("probable", captured["reporters_assessment"])
        self.assertEqual("possible", captured["reviewer_assessment"])
        self.assertEqual("Probable", captured["reporters_assessment_verbatim"])
        self.assertEqual("dr.iyer@medicall.in", captured["reviewed_by"])
        self.assertEqual("2026-09-26T09:30:00+00:00", captured["reviewed_at"])
        self.assertEqual(coding.WHO_UMC_SCALE_NAME, captured["scale"])

    def test_the_system_never_assigns_a_category(self):
        captured = coding.causality_capture(
            reporters_assessment="probable", reviewer="dr.iyer@medicall.in"
        )
        self.assertTrue(captured["valid"])
        self.assertEqual("", captured["reviewer_assessment"])
        self.assertFalse(
            captured["system_assigned"],
            "no code path may fill a causality slot the human did not fill",
        )

    def test_reporter_only_is_a_valid_capture(self):
        captured = coding.causality_capture(reporters_assessment="unlikely")
        self.assertTrue(captured["valid"])
        self.assertEqual("unlikely", captured["reporters_assessment"])
        self.assertEqual("", captured["reviewer_assessment"])
        self.assertEqual("", captured["reviewed_by"])

    def test_assessment_must_be_on_the_scale(self):
        for bad in ("probably", "definitely", "1", "true", "caused by it", "आश्रय"):
            with self.subTest(bad):
                captured = coding.causality_capture(
                    reviewer_assessment=bad,
                    reviewer="dr.iyer@medicall.in",
                    reviewed_at="2026-09-26T09:30:00+00:00",
                )
                self.assertFalse(captured["valid"])
                self.assertFalse(captured["captured"])
                self.assertEqual(
                    coding.CAUSALITY_REVIEWER_NOT_ON_SCALE, captured["error"]
                )
                self.assertIn(coding.WHO_UMC_SCALE_NAME, captured["detail"])
                self.assertEqual("", captured["reviewer_assessment"])

    def test_invalid_reporter_assessment_is_rejected(self):
        captured = coding.causality_capture(reporters_assessment="somewhat likely")
        self.assertFalse(captured["valid"])
        self.assertEqual(coding.CAUSALITY_REPORTER_NOT_ON_SCALE, captured["error"])
        self.assertEqual("", captured["reporters_assessment"])

    def test_reviewer_assessment_without_identity_is_rejected(self):
        captured = coding.causality_capture(reviewer_assessment="possible")
        self.assertFalse(captured["valid"])
        self.assertEqual(coding.CAUSALITY_REVIEWER_UNATTRIBUTED, captured["error"])
        self.assertIn("reviewer", captured["detail"].lower())
        self.assertEqual(
            "", captured["reviewer_assessment"], "an unattributed review is never stored"
        )
        self.assertEqual("", captured["reviewed_by"])

    def test_reviewer_assessment_without_date_is_rejected(self):
        captured = coding.causality_capture(
            reviewer_assessment="possible", reviewer="dr.iyer@medicall.in"
        )
        self.assertFalse(captured["valid"])
        self.assertEqual(coding.CAUSALITY_REVIEWER_UNATTRIBUTED, captured["error"])
        self.assertIn("reviewed_at", captured["detail"])
        self.assertEqual("", captured["reviewer_assessment"])

    def test_blank_reviewer_identity_does_not_count(self):
        for blank in ("", "   "):
            with self.subTest(repr(blank)):
                captured = coding.causality_capture(
                    reviewer_assessment="possible",
                    reviewer=blank,
                    reviewed_at="2026-09-26T09:30:00+00:00",
                )
                self.assertFalse(captured["valid"])
                self.assertEqual(coding.CAUSALITY_REVIEWER_UNATTRIBUTED, captured["error"])

    def test_reviewed_at_must_be_iso8601(self):
        """No clock in this module: an unreadable date is refused, not replaced."""
        captured = coding.causality_capture(
            reviewer_assessment="possible",
            reviewer="dr.iyer@medicall.in",
            reviewed_at="yesterday",
        )
        self.assertFalse(captured["valid"])
        self.assertEqual(coding.CAUSALITY_REVIEWED_AT_NOT_ISO, captured["error"])

    def test_a_rejected_reviewer_never_leaks_the_reporter_part(self):
        """The capture is atomic: a refused review stores nothing at all."""
        captured = coding.causality_capture(
            reporters_assessment="probable",
            reviewer_assessment="maybe",
            reviewer="dr.iyer@medicall.in",
            reviewed_at="2026-09-26T09:30:00+00:00",
        )
        self.assertFalse(captured["valid"])
        for key in ("reporters_assessment", "reporters_assessment_verbatim"):
            self.assertEqual("", captured[key], f"{key} must not survive a refusal")
        self.assertEqual(
            set(captured.keys()),
            set(coding.causality_capture(reporters_assessment="probable").keys()),
            "the valid and refused shapes must be identical",
        )

    def test_nothing_to_capture_is_refused(self):
        captured = coding.causality_capture()
        self.assertFalse(captured["valid"])
        self.assertEqual(coding.CAUSALITY_NO_ASSESSMENT, captured["error"])

    def test_who_umc_aliases_normalise_to_the_scale(self):
        for raw, canonical in (("Likely", "probable"), ("not related", "not_related")):
            with self.subTest(raw):
                captured = coding.causality_capture(reporters_assessment=raw)
                self.assertTrue(captured["valid"])
                self.assertEqual(canonical, captured["reporters_assessment"])
                self.assertEqual(raw, captured["reporters_assessment_verbatim"])

    def test_is_pure_and_deterministic(self):
        kwargs = dict(
            reporters_assessment="probable",
            reviewer_assessment="possible",
            reviewer="dr.iyer@medicall.in",
            reviewed_at="2026-09-26T09:30:00+00:00",
        )
        first = coding.causality_capture(**kwargs)
        self.assertEqual(first, coding.causality_capture(**kwargs))
        self.assertEqual(
            {"reporters_assessment", "reviewer_assessment", "reviewer", "reviewed_at"},
            set(kwargs),
        )


# ─── F. The expedited gate — the rule, in the module that owns it ───────────
class TestReviewerStamp(DictionaryRegistryMixin):
    def test_serious_and_unexpected_is_expedited(self):
        self.assertTrue(coding.is_expedited(case()))

    def test_non_serious_is_never_expedited(self):
        # An unrecognised flag is not an ICH E2A criterion: Phase 1 ignores it,
        # so a case nobody marked serious is never gated. (A single RECOGNISED
        # criterion, e.g. ["hospitalisation"], IS serious — that row is the
        # expedited one asserted by GATE_TABLE below.)
        for flags in ([], ["patient called back about the itch"]):
            with self.subTest(flags):
                self.assertFalse(coding.is_expedited(case(seriousness_flags=flags)))

    def test_serious_but_expected_is_not_expedited(self):
        self.assertFalse(coding.is_expedited(case(expectedness="expected")))

    def test_expectedness_spelling_is_normalised(self):
        for raw in ("Expected", "expected per label"):
            with self.subTest(raw):
                self.assertFalse(coding.is_expedited(case(expectedness=raw)))

    def test_unassessed_expectedness_fails_closed(self):
        """A serious case nobody compared with the label is gated, not waved through."""
        for raw in ("", "unknown", "  "):
            with self.subTest(repr(raw)):
                self.assertTrue(coding.is_expedited(case(expectedness=raw)))
        # And an unstamped one names the WHOLE stamp — the category, the identity
        # AND the moment — so the desk is told the full price of the gate, not
        # one field at a time.
        self.assertEqual(
            ["reviewer_causality", "reviewed_by", "reviewed_at"],
            coding.missing_review_stamp(unstamped(expectedness="")),
        )

    def test_stamp_is_complete_when_all_three_fields_are_present(self):
        stamp = coding.reviewer_stamp(case())
        self.assertTrue(stamp["expedited"])
        self.assertTrue(stamp["stamped"])
        self.assertEqual([], stamp["missing"])
        self.assertEqual([], coding.missing_review_stamp(case()))

    def test_each_missing_field_is_named_in_canonical_order(self):
        for field in ("reviewer_causality", "reviewed_by", "reviewed_at"):
            with self.subTest(field):
                # Exactly ONE field cleared, so the refusal names exactly it.
                missing = coding.missing_review_stamp(case(**{field: ""}))
                self.assertEqual([field], missing)
        # Two cleared: they come back in the canonical stamp order, not in the
        # order the caller happened to clear them in.
        self.assertEqual(
            ["reviewed_by", "reviewed_at"],
            coding.missing_review_stamp(case(reviewed_at="", reviewed_by="")),
        )

    def test_an_off_scale_stored_category_is_not_a_stamp(self):
        """A hand-edited row cannot unlock the gate with a free-text value."""
        missing = coding.missing_review_stamp(case(reviewer_causality="probably"))
        self.assertEqual(["reviewer_causality"], missing)

    def test_a_non_expedited_case_needs_no_stamp(self):
        row = unstamped(seriousness_flags=[], expectedness="unexpected")
        self.assertEqual([], coding.missing_review_stamp(row))
        self.assertFalse(coding.reviewer_stamp(row)["expedited"])
        row = unstamped(expectedness="expected")
        self.assertEqual([], coding.missing_review_stamp(row))

    def test_review_stamp_canonicalises_the_stored_category(self):
        stamp = coding.reviewer_stamp(case(reviewer_causality="Possible"))
        self.assertEqual("possible", stamp["reviewer_causality"])

    def test_gate_status_is_a_4xx_conflict(self):
        self.assertGreaterEqual(coding.REVIEW_GATE_STATUS, 400)
        self.assertLess(coding.REVIEW_GATE_STATUS, 500)
        self.assertEqual(409, coding.REVIEW_GATE_STATUS)


# ─── G. The gate as the export route sees it (app/services/e2b.py) ─────────
# The decision table, over the ONE function both e2b routes already call.
# serious | expectedness | causality | by | at | e2b_min | expected status
GATE_TABLE = (
    # expedited, unstamped -> refused
    (True, "unexpected", "", "", "", True, 409),
    (True, "unexpected", "possible", "", "", True, 409),
    (True, "unexpected", "possible", "safety.physician@medicall.in", "", True, 409),
    (True, "unexpected", "probably", "safety.physician@medicall.in",
     "2026-09-23T09:30:00+00:00", True, 409),
    (True, "", "", "", "", True, 409),
    (True, "unknown", "", "", "", True, 409),
    # expedited, stamped -> allowed
    (True, "unexpected", "possible", "safety.physician@medicall.in",
     "2026-09-23T09:30:00+00:00", True, 0),
    (True, "", "not_related", "safety.physician@medicall.in",
     "2026-09-23T09:30:00+00:00", True, 0),
    # not expedited -> allowed unstamped
    (True, "expected", "", "", "", True, 0),
    (False, "unexpected", "", "", "", True, 0),
    (False, "", "", "", "", True, 0),
)


class TestExportGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_SVC:
            require_coding()
        cls.text = read(E2B_SVC)

    def test_e2b_service_uses_the_shared_review_gate(self):
        self.assertIn("from app.services.coding import", self.text)
        block = fn_block(self.text, "e2b_export_block")
        self.assertIn("missing_review_stamp", block, "one decision, not a copy")
        self.assertIn("REVIEW_GATE_STATUS", block)

    def test_the_e2b_minimum_is_still_checked_first(self):
        """An incomplete case cannot be an ICSR at all, whatever the stamp says."""
        row = unstamped(e2b_minimum_met=False)
        status, detail = e2b_mod.e2b_export_block(row)
        self.assertEqual(422, status)
        self.assertIn("e2b_minimum_met", detail)

    def test_missing_case_is_still_404(self):
        for empty in ({}, None, {"id": ""}):
            with self.subTest(repr(empty)):
                self.assertEqual(
                    (404, e2b_mod.CASE_NOT_FOUND_DETAIL), e2b_mod.e2b_export_block(empty)
                )

    def test_gate_decision_table(self):
        for serious, expectedness, causality, by, at, minimum, expected in GATE_TABLE:
            row = case(
                seriousness_flags=["hospitalisation"] if serious else [],
                expectedness=expectedness,
                reviewer_causality=causality,
                reviewed_by=by,
                reviewed_at=at,
                e2b_minimum_met=minimum,
            )
            with self.subTest(
                serious=serious,
                expectedness=expectedness,
                reviewer_causality=causality,
            ):
                status, detail = e2b_mod.e2b_export_block(row)
                self.assertEqual(expected, status, detail)
                if expected == coding.REVIEW_GATE_STATUS:
                    self.assertIn(coding.REVIEW_GATE_DETAIL, detail)
                    self.assertIn("missing:", detail)
                else:
                    self.assertEqual(e2b_mod.E2B_EXPORTABLE, (status, detail))

    def test_refusal_names_every_missing_field(self):
        status, detail = e2b_mod.e2b_export_block(unstamped())
        self.assertEqual(coding.REVIEW_GATE_STATUS, status)
        for field in coding.REVIEWER_STAMP_FIELDS:
            self.assertIn(field, detail)
        self.assertIn("expedited", detail.lower())

    def test_refusal_never_names_a_missing_category_as_if_it_had_one(self):
        _status, detail = e2b_mod.e2b_export_block(case(reviewer_causality=""))
        self.assertIn("reviewer_causality", detail)
        self.assertNotIn("reviewed_at=T", detail)


# ─── H. Schema: the reviewer-causality columns ─────────────────────────────
class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCHEMA_SQL)
        cls.statements = ddl_statements(cls.text)

    def test_alter_statements_are_top_level_and_idempotent(self):
        for column in AE_CODING_COLUMNS:
            with self.subTest(column):
                matches = [
                    s
                    for s in self.statements
                    if s.startswith("ALTER TABLE adverse_events")
                    and f"ADD COLUMN IF NOT EXISTS {column} " in s
                ]
                self.assertEqual(
                    1, len(matches), f"one idempotent ALTER for {column}"
                )
                self.assertTrue(
                    matches[0].startswith("ALTER TABLE adverse_events "),
                    "the ALTER must name the table at statement start",
                )

    def test_no_duplicate_column_adds(self):
        for column in AE_CODING_COLUMNS:
            hits = [
                s for s in self.statements if f"ADD COLUMN IF NOT EXISTS {column} " in s
            ]
            self.assertEqual(1, len(hits), f"{column} is added more than once")

    def test_reviewed_at_is_a_timestamp_column(self):
        match = [
            s
            for s in self.statements
            if "ADD COLUMN IF NOT EXISTS reviewed_at " in s
        ][0]
        self.assertIn("TIMESTAMPTZ", match)

    def test_alter_statements_are_comma_clean_and_paren_balanced(self):
        for statement in self.statements:
            if not statement.startswith("ALTER TABLE adverse_events"):
                continue
            with self.subTest(statement[:60]):
                self.assertTrue(statement.endswith(";"))
                self.assertEqual(
                    0,
                    statement.count("(") - statement.count(")"),
                    "unbalanced parens in a DDL statement",
                )
                self.assertFalse(
                    statement[:-1].rstrip().endswith(","), "trailing comma"
                )

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


# ─── I. ORM: columns + the two writers ─────────────────────────────────────
class TestOrm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(POSTGRES)

    def test_ae_model_has_the_coding_and_causality_columns(self):
        block = model_block(self.text, "AdverseEvent")
        self.assertTrue(block, "class AdverseEvent(Base): not found")
        for column in AE_CODING_COLUMNS:
            with self.subTest(column):
                self.assertIn(f"{column}:", block)

    def test_typed_columns(self):
        block = model_block(self.text, "AdverseEvent")
        self.assertIn("coding_json: Mapped[Optional[dict]]", block)
        self.assertIn("reviewer_causality: Mapped[Optional[str]]", block)
        self.assertIn("reporter_causality: Mapped[Optional[str]]", block)
        self.assertIn("reviewed_by: Mapped[Optional[str]]", block)
        self.assertIn("reviewed_at: Mapped[Optional[datetime]]", block)

    def test_causality_reporter_verbatim_column_is_untouched(self):
        """Phase 1's verbatim free text stays; 2C adds a CATEGORY beside it."""
        block = model_block(self.text, "AdverseEvent")
        self.assertIn("causality_reporter: Mapped[Optional[str]]", block)

    def test_repository_helpers_exist(self):
        names = set(fns(py_tree_text(self.text)))
        for fn in AE_REPO_FNS:
            self.assertIn(fn, names, f"postgres.py missing repository helper {fn}")

    def test_coding_writer_writes_only_what_is_passed(self):
        block = fn_block(self.text, "update_adverse_event_coding")
        self.assertIn("coding", block)
        self.assertIn("update(AdverseEvent)", block)
        self.assertIn("updated_at", block)

    def test_causality_writer_writes_only_what_is_passed(self):
        block = fn_block(self.text, "update_adverse_event_causality")
        for field in ("reporter_causality", "reviewer_causality", "reviewed_by", "reviewed_at"):
            self.assertIn(field, block)
        self.assertIn("update(AdverseEvent)", block)


# ─── J. Router: the two staff routes ───────────────────────────────────────
class TestRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PV_ROUTER)
        cls.tree = py_tree_text(cls.text)

    def test_routes_present(self):
        found = {(verb, path) for verb, path, _ in endpoints(self.tree)}
        for route in CODING_ROUTES:
            self.assertIn(route, found, f"missing pv route {route}")

    def test_routes_identity_gated(self):
        for name in CODING_IDENTITY_GATED:
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertTrue(block, f"{name} missing from app/api/pv.py")
                self.assertIn("get_current_user", block, f"{name} must be identity-gated")
                self.assertNotIn("WEBHOOK_SERVICE_TOKEN", block)

    def test_case_row_carries_the_stamp_to_the_gate(self):
        block = fn_block(self.text, "_case_row")
        for field in ("reviewer_causality", "reviewed_by", "reviewed_at"):
            self.assertIn(field, block, f"_case_row must carry {field} to the gate")

    def test_coding_route_runs_the_pure_service_and_stores_on_hit_only(self):
        block = fn_block(self.text, "code_pv_case_ep")
        self.assertIn("code_case", block, "coding runs in the pure service")
        self.assertIn("get_adverse_event", block)
        self.assertIn("update_adverse_event_coding", block)
        self.assertIn("create_compliance_event", block)
        self.assertIn(PV_CODED_EVENT, block)
        self.assertIn("coded", block, "a miss must be reported, not stored")

    def test_coding_route_never_fabricates_a_code(self):
        block = fn_block(self.text, "code_pv_case_ep")
        for banned in ("FIXPT", "FIXDRUG", "lookup_pt(", "lookup_drug("):
            self.assertNotIn(banned, block, f"the router must not code itself: {banned}")

    def test_causality_route_captures_and_never_computes(self):
        block = fn_block(self.text, "capture_pv_case_causality_ep")
        self.assertIn("causality_capture", block)
        self.assertIn("update_adverse_event_causality", block)
        self.assertIn("create_compliance_event", block)
        self.assertIn(PV_CAUSALITY_EVENT, block)
        self.assertIn("422", block, "a refused capture is a validation error")
        for banned in ("classify_seriousness", "classify_contact_type", "_now()"):
            self.assertNotIn(
                banned, block, f"the capture path must never judge: {banned}"
            )

    def test_causality_route_stores_only_what_the_capture_validated(self):
        """A refused capture raises before the write, and only the capture's own
        values are written — the route never supplies a category of its own."""
        block = fn_block(self.text, "capture_pv_case_causality_ep")
        self.assertIn("if not captured", block, "a refusal must raise before any write")
        guard = block.index("if not captured")
        write = block.index("update_adverse_event_causality")
        self.assertLess(guard, write, "the refusal check must precede the write")
        for key in (
            "reporters_assessment",
            "reviewer_assessment",
            "reviewed_by",
            "reviewed_at",
        ):
            with self.subTest(key):
                self.assertIn(f'captured["{key}"]', block)

    def test_both_e2b_routes_refuse_through_the_one_gate(self):
        gate = fn_block(self.text, "_e2b_case")
        self.assertIn("e2b_export_block", gate)
        self.assertIn("REVIEW_GATE_STATUS", gate, "the reviewer gate must surface as 409")
        for name in ("get_pv_case_e2b_xml_ep", "prepare_pv_case_e2b_submission_ep"):
            with self.subTest(name):
                self.assertIn("_e2b_case", fn_block(self.text, name))

    def test_audit_event_names(self):
        self.assertIn(PV_CODED_EVENT, self.text)
        self.assertIn(PV_CAUSALITY_EVENT, self.text)

    def test_router_docstring_lists_the_new_routes(self):
        doc = ast.get_docstring(self.tree) or ""
        self.assertIn("/cases/{case_id}/coding", doc)
        self.assertIn("/cases/{case_id}/causality", doc)

    def test_router_imports_the_coding_service(self):
        self.assertIn("from app.services.coding import", self.text)


# ─── K. The route-set tuples in test_pv_module.py must know these routes ───
class TestPvModuleRouteSets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "t_pv_module", BACKEND / "tests" / "test_pv_module.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.module = module

    def test_pv_module_route_set_includes_the_coding_routes(self):
        for route in CODING_ROUTES:
            with self.subTest(route):
                self.assertIn(route, self.module.PV_ROUTES)

    def test_pv_module_identity_gated_tuple_includes_the_endpoints(self):
        for name in CODING_IDENTITY_GATED:
            with self.subTest(name):
                self.assertIn(name, self.module.IDENTITY_GATED)

    def test_pv_module_has_no_stale_route_assertion(self):
        """The exact-set test must still be an exact set (not silently relaxed)."""
        block = fn_block(read(BACKEND / "tests" / "test_pv_module.py"), "test_route_set")
        self.assertIn("assertEqual(PV_ROUTES, found", block)


# ─── L. The Phase-1 rules are reused, never re-derived ─────────────────────
class TestPhaseOneRulesReused(unittest.TestCase):
    def test_seriousness_comes_from_the_phase1_classifier(self):
        block = fn_block(read(CODING_SVC), "is_expedited")
        self.assertIn("classify_seriousness", block)
        self.assertNotIn("hospitalisation", block, "criteria must not be re-listed")

    def test_expedited_definition_is_the_specified_one(self):
        """serious AND not expected per the label — one definition, used by the gate."""
        source = read(CODING_SVC)
        self.assertIn("EXPECTEDNESS_VALUES", source)
        self.assertIn("classify_seriousness", source)
        for criteria in pv.SERIOUSNESS_CRITERIA:
            with self.subTest(criteria):
                self.assertNotIn(
                    f'"{criteria}"', source, f"{criteria} must not be re-declared"
                )

    def test_causality_scale_is_not_derived_from_seriousness(self):
        source = read(CODING_SVC)
        block = fn_block(source, "causality_capture")
        self.assertNotIn("classify_seriousness", block)
        self.assertNotIn("classify_contact_type", block)


if __name__ == "__main__":
    unittest.main()
