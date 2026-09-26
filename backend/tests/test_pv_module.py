"""Pharmacovigilance / MICC Phase 1 (spec-micc-pv-module.md) — RED contracts.

Stdlib-only, no live Postgres, no gateway keys — the house pattern of
test_payments_q5 / test_g4_voice: the pure service module
(app/services/pharmacovigilance.py) is imported and BEHAVIOUR-tested (contact
classification in 5 languages, E2B minimum criteria, ICH E2A seriousness, the
India 15/90-day clock, the PQC state machine, the E2B-minimum export bundle +
flat CSV + the print view), while the schema / ORM / router / wiring contracts
are structural AST + text assertions.

RED before implementation (2026-09-26): no app/services/pharmacovigilance.py,
no /api/pv router, no products/adverse_events/quality_complaints/medical_
inquiries tables, no pv_alert notification kind.

GREEN after implementation: 4 tables with RLS+FORCE+{table}_manage policies,
4 SQLAlchemy models + repository helpers, the 4 stdlib service functions, 7
routes on the twelfth router, a compliance_events audit row per intake and per
disposition change, and the pv_alert kind (default on, env-gated mailbox).

Run: py -3.14 -m unittest discover -s tests -p "test_pv_module.py"   (from backend/)
"""
import ast
import csv
import io
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))

API_DIR = BACKEND / "app" / "api"
DB_DIR = BACKEND / "app" / "db"
SERVICES = BACKEND / "app" / "services"
SCHEMAS = BACKEND / "app" / "schemas"
SCHEMA_SQL = BACKEND / "postgres_schema.sql"
POSTGRES = DB_DIR / "postgres.py"
MAIN = BACKEND / "main.py"
PV_ROUTER = API_DIR / "pv.py"
PV_SVC = SERVICES / "pharmacovigilance.py"
ENV_EXAMPLE = BACKEND / ".env.example"
DEPLOY_DOC = ROOT / "docs" / "DEPLOYMENT.md"

PV_TABLES = ("products", "adverse_events", "quality_complaints", "medical_inquiries")
PV_MODELS = ("Product", "AdverseEvent", "QualityComplaint", "MedicalInquiry")

# The E2B/R2 keyword classes the print view must never contain. The banner is
# stripped before scanning (it is the NO_MEDICAL_ADVICE disclaimer, not case
# data) and the banner itself is asserted free of these words.
FORBIDDEN_PRINT_KEYWORDS = (
    "causality",
    "caused by",
    "causal judgement",
    "diagnosis",
    "diagnosed",
    "differential",
    "you have",
    "you are suffering",
    "should take",
    "recommended dose",
    "medical advice",
    "we advise",
    "likely",
    "probably",
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


def py_tree_text(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def module_literal_consts(text: str) -> dict:
    """{Name: literal value} for module-level Tuple/Dict/List assignments."""
    out = {}
    tree = py_tree_text(text)
    if tree is None:
        return out
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.Tuple, ast.Dict, ast.List)
        ):
            try:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    out[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


def module_import_roots(text: str) -> set:
    """Root package of every import in a module (for the stdlib-only gate)."""
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


def endpoints(tree) -> list:
    """[(method, path)] for every @router.<verb> decorated endpoint."""
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
                path = deco.args[0].value
                out.append((deco.func.attr.lower(), path, node.name))
    return out


def router_prefix(tree) -> str:
    """Prefix of the `router = APIRouter(...)` assignment.

    House convention (all 10 existing api/*.py) spells it `APIRouter(prefix=...)`
    with a bare name, so the keyword is read first and a positional arg (and a
    `fastapi.APIRouter` attribute form) is only a fallback.
    """
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            is_router = getattr(call.func, "id", None) == "APIRouter" or (
                isinstance(call.func, ast.Attribute)
                and call.func.attr == "APIRouter"
            )
            if is_router:
                for kw in call.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
                if call.args and isinstance(call.args[0], ast.Constant):
                    return call.args[0].value
    return ""


def model_block(text: str, cls: str) -> str:
    return text.split(f"class {cls}(Base):", 1)[1].split("\n    def __repr__", 1)[0]


def sql_table_block(text: str, table: str) -> str:
    marker = f"CREATE TABLE IF NOT EXISTS {table} ("
    if marker not in text:  # tolerate a non-idempotent spelling
        marker = f"CREATE TABLE {table} ("
    if marker not in text:
        return ""
    return text.split(marker, 1)[1].split("\n);", 1)[0]


# The stdlib service — behaviour-tested. Absent at RED.
try:
    from app.services import pharmacovigilance as pv  # noqa: E402

    HAVE_SVC = True
except ImportError:  # pragma: no cover - RED state
    pv = None
    HAVE_SVC = False


# ─── A. Module + import purity ───────────────────────────────────────────────

STDLIB_ROOTS = {
    "csv",
    "datetime",
    "html",
    "io",
    "json",
    "math",
    "os",
    "re",
    "sys",
    "typing",
    "unicodedata",
    "uuid",
}


class TestServiceModuleShape(unittest.TestCase):
    def test_service_module_exists(self):
        self.assertTrue(PV_SVC.exists(), "app/services/pharmacovigilance.py missing")

    def test_service_module_is_stdlib_only(self):
        roots = module_import_roots(read(PV_SVC))
        allowed = STDLIB_ROOTS | {"app"}
        self.assertTrue(roots, "no imports parsed")
        self.assertEqual(
            set(),
            roots - allowed,
            f"pharmacovigilance.py must be stdlib-only + repo modules; got {sorted(roots - allowed)}",
        )

    def test_module_is_class_free(self):
        """House convention (guardrails / telephony / payments): no classes."""
        tree = py_tree(PV_SVC)
        classes = [n.name for n in ast.walk(tree or ast.Module(body=[], type_ignores=[]))
                   if isinstance(n, ast.ClassDef)]
        self.assertEqual([], classes, "pharmacovigilance.py must stay class-free")

    def test_four_service_functions_present(self):
        names = set(fns(py_tree(PV_SVC)))
        for fn in (
            "classify_contact_type",
            "validate_minimum_criteria",
            "classify_seriousness",
            "compute_reporting_deadline",
        ):
            self.assertIn(fn, names, f"services.pharmacovigilance missing {fn}")

    def test_catalog_constants(self):
        consts = module_literal_consts(read(PV_SVC))
        self.assertEqual(("AE", "PQC", "MI", "OTHER"), consts.get("CONTACT_TYPES"))
        self.assertEqual(("hi", "en", "ta", "te", "bn"), consts.get("PV_LANGUAGES"))
        self.assertEqual(
            ("reporter", "patient", "product", "event"),
            consts.get("MINIMUM_CRITERIA_ELEMENTS"),
        )
        self.assertEqual(
            {
                "death",
                "life_threatening",
                "hospitalisation",
                "disability",
                "congenital_anomaly",
                "medically_important",
            },
            set(consts.get("SERIOUSNESS_CRITERIA", ())),
            "ICH E2A needs all six seriousness criteria",
        )
        clocks = consts.get("REPORTING_CLOCK_DAYS", {})
        self.assertEqual(15, clocks.get("india", {}).get("serious"))
        self.assertEqual(90, clocks.get("india", {}).get("non_serious"))
        self.assertEqual(
            ("captured", "investigating", "disposition", "capa"),
            consts.get("PQC_STATUSES"),
        )
        self.assertEqual(
            {
                "captured": ("investigating",),
                "investigating": ("disposition",),
                "disposition": ("capa",),
                "capa": (),
            },
            consts.get("PQC_TRANSITIONS"),
        )


# ─── B. classify_contact_type — 5 languages + special situations ─────────────

# (language, text, expected) — curated phrase-table vectors per language.
CONTACT_CASES = (
    # hi
    ("hi", "मुझे दवा से बुखार और उल्टी हो रही है", "AE"),
    ("hi", "पैकेट टूटा हुआ है और दवा का रंग बदल गया", "PQC"),
    ("hi", "यह दवा कितनी बार लेनी है, दूध के साथ ले सकते हैं क्या", "MI"),
    ("hi", "मुझे डॉक्टर से बात करनी है", "OTHER"),
    # en
    ("en", "I broke out in a rash after taking the tablet", "AE"),
    ("en", "the strip arrived broken and the tablets are loose", "PQC"),
    ("en", "can I take this with milk and how often", "MI"),
    ("en", "I would like to speak to the doctor", "OTHER"),
    # ta
    ("ta", "மருந்து எடுத்த பிறகு வலியும் வாந்தியும் ஏற்பட்டது", "AE"),
    ("ta", "பாக்கெட் உடைந்து இருந்தது, மாத்திரை உடையிருந்தது", "PQC"),
    ("ta", "எவ்வளவு மருந்து எடுக்க வேண்டும்", "MI"),
    ("ta", "நேரம் வரண்டும்", "OTHER"),
    # te
    ("te", "మందులు తీసిన తర్వాత జ్వరం వచ్చింది", "AE"),
    ("te", "ప్యాకెట్ పగిలి ఉంది", "PQC"),
    ("te", "ఎంత మోతాదు తీసుకోవాలి", "MI"),
    ("te", "ఇప్పుడు వచ్చేటప్పటికే నిధి", "OTHER"),
    # bn
    ("bn", "ওষুধ খাওয়ার পরে জ্বর ও বমি হয়েছে", "AE"),
    ("bn", "প্যাকেট ছিঁড়ে গেছে, ট্যাবলেট ভেঙে আছে", "PQC"),
    ("bn", "কতটুকু খাব আর কখন খাব", "MI"),
    ("bn", "ডাক্তারের সাথে কথা বলতে চাই", "OTHER"),
    # Special situations -> AE (ICH E2A / listed situations), in every script.
    ("en", "I took too many pills by mistake", "AE"),
    ("en", "the injection is not working for my father", "AE"),
    ("en", "I used leftover medicine for my knee pain", "AE"),
    ("en", "the medicine changed my periods", "AE"),
    ("hi", "मैंने गलत दवा खा लिया", "AE"),
    ("hi", "दवा अब काम नहीं कर रही", "AE"),
    ("ta", "அதிக மருந்து சாப்பிட்டேன்", "AE"),
    ("ta", "மருந்து வேலை செய்யவில்லை", "AE"),
    ("te", "తప్పు మందులు తీసుకున్నాను", "AE"),
    ("te", "మందులు పనిచేయడం లేదు", "AE"),
    ("bn", "ভুল ওষুধ খেয়েছি", "AE"),
    ("bn", "ওষুধ কাজ করছে না", "AE"),
    ("bn", "অতিরিক্ত ওষুধ খেয়েছি", "AE"),
    # Safety signalling beats a defect mention (EU GMP Ch. 8.7: complaints
    # that indicate a suspected AE are routed to PV).
    ("en", "the bottle is leaking and now my son has a severe rash", "AE"),
    ("en", "my father died after the injection", "AE"),
)


class TestClassifyContactType(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_table_driven_all_languages(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for language, text, expected in CONTACT_CASES:
            with self.subTest(lang=language, text=text):
                self.assertEqual(
                    expected,
                    pv.classify_contact_type(text, language),
                    f"{language}: {text!r}",
                )

    def test_all_five_languages_covered_by_the_table(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual(
            {"hi", "en", "ta", "te", "bn"},
            set(pv.CONTACT_PHRASES),
            "phrase tables must exist for all 5 Indian languages",
        )
        for language in ("hi", "en", "ta", "te", "bn"):
            for kind in ("AE", "PQC", "MI"):
                self.assertTrue(
                    pv.CONTACT_PHRASES[language].get(kind),
                    f"{language}: empty {kind} phrase table",
                )

    def test_special_situation_terms_in_every_language(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual(
            {"hi", "en", "ta", "te", "bn"},
            set(pv.SPECIAL_SITUATION_TERMS),
        )
        for language, terms in pv.SPECIAL_SITUATION_TERMS.items():
            self.assertTrue(terms, f"{language}: no special-situation terms")

    def test_empty_and_none_input_is_other(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for text in ("", "   ", None):
            self.assertEqual("OTHER", pv.classify_contact_type(text, "en"))

    def test_unknown_language_falls_back_not_crashes(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual("AE", pv.classify_contact_type("I broke out in a rash", "xx"))
        self.assertEqual("OTHER", pv.classify_contact_type("", "xx"))

    def test_matching_is_case_insensitive(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual("AE", pv.classify_contact_type("SIDE EFFECT after the pill", "en"))


# ─── C. validate_minimum_criteria — each missing element ─────────────────────

GOOD_REPORTER = {"reporter_type": "hcp", "role": "doctor", "phone_suffix": "43210"}
GOOD_PATIENT = {"age": "54", "sex": "female", "initials": "RS"}


class TestValidateMinimumCriteria(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_complete_case_valid(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria(
            "Rash and fever after the third dose",
            GOOD_REPORTER,
            GOOD_PATIENT,
            {"name": "Azithral 500", "strength": "500mg"},
        )
        self.assertTrue(ok)
        self.assertEqual([], missing)

    def test_missing_reporter(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria("rash", None, GOOD_PATIENT, {"name": "X"})
        self.assertFalse(ok)
        self.assertEqual(["reporter"], missing)

    def test_missing_patient(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria("rash", GOOD_REPORTER, {}, {"name": "X"})
        self.assertFalse(ok)
        self.assertEqual(["patient"], missing)

    def test_missing_product(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria("rash", GOOD_REPORTER, GOOD_PATIENT, None)
        self.assertFalse(ok)
        self.assertEqual(["product"], missing)

    def test_missing_event(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for text in ("", "   ", None):
            ok, missing = pv.validate_minimum_criteria(
                text, GOOD_REPORTER, GOOD_PATIENT, {"name": "X"}
            )
            self.assertFalse(ok)
            self.assertEqual(["event"], missing, f"event text {text!r}")

    def test_all_missing_reported_in_canonical_order(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria("", None, {}, "")
        self.assertFalse(ok)
        self.assertEqual(["reporter", "patient", "product", "event"], missing)

    def test_partial_patient_is_identifiable(self):
        """E2B: age OR sex OR initials alone is an identifiable patient."""
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for patient in (
            {"age": "7"},
            {"sex": "male"},
            {"initials": "A.K."},
            {"patient_initials": "AK"},
        ):
            ok, missing = pv.validate_minimum_criteria(
                "nausea", GOOD_REPORTER, patient, {"name": "X"}
            )
            self.assertTrue(ok, f"{patient} should be identifiable")
            self.assertEqual([], missing)

    def test_bare_reporter_string_counts_as_identifiable(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, _ = pv.validate_minimum_criteria("nausea", "patient's son", GOOD_PATIENT, "Drug X")
        self.assertTrue(ok)

    def test_blank_fields_do_not_count(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ok, missing = pv.validate_minimum_criteria(
            "nausea",
            {"reporter_type": "", "role": "", "phone": ""},
            {"age": "", "sex": "", "initials": ""},
            {"name": "  "},
        )
        self.assertFalse(ok)
        self.assertEqual(["reporter", "patient", "product"], missing)


# ─── D. classify_seriousness — all six ICH E2A criteria ──────────────────────


class TestClassifySeriousness(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_no_flags_is_non_serious(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        serious, criteria = pv.classify_seriousness({})
        self.assertFalse(serious)
        self.assertEqual([], criteria)
        for empty in (None, [], (), set(), {"death": False}):
            self.assertEqual(
                (False, []), pv.classify_seriousness(empty), f"{empty!r}"
            )

    def test_each_of_the_six_criteria_alone_is_serious(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for criterion in pv.SERIOUSNESS_CRITERIA:
            serious, criteria = pv.classify_seriousness({criterion: True})
            self.assertTrue(serious, criterion)
            self.assertEqual([criterion], criteria)

    def test_all_six_reported_in_canonical_order(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        flags = {c: True for c in reversed(pv.SERIOUSNESS_CRITERIA)}
        serious, criteria = pv.classify_seriousness(flags)
        self.assertTrue(serious)
        self.assertEqual(list(pv.SERIOUSNESS_CRITERIA), criteria)

    def test_list_and_set_inputs_accepted(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for payload in (
            ["death"],
            ("death",),
            {"death"},
            {"death": 1},
        ):
            serious, criteria = pv.classify_seriousness(payload)
            self.assertTrue(serious, f"{payload!r}")
            self.assertEqual(["death"], criteria)

    def test_spelling_aliases_normalised(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for alias, canonical in (
            ("life-threatening", "life_threatening"),
            ("life threatening", "life_threatening"),
            ("hospitalization", "hospitalisation"),
            ("hospitalisation", "hospitalisation"),
            ("congenital", "congenital_anomaly"),
            ("congenital-anomaly", "congenital_anomaly"),
            ("medically-important", "medically_important"),
        ):
            serious, criteria = pv.classify_seriousness([alias])
            self.assertTrue(serious, alias)
            self.assertEqual([canonical], criteria, alias)

    def test_unknown_flag_is_not_serious(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual((False, []), pv.classify_seriousness(["mild_rash"]))

    def test_falsy_values_are_not_serious(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        serious, criteria = pv.classify_seriousness(
            {"death": False, "hospitalisation": False, "disability": 0}
        )
        self.assertFalse(serious)
        self.assertEqual([], criteria)


# ─── E. compute_reporting_deadline — India 15/90 calendar days ───────────────

UTC = timezone.utc


class TestComputeReportingDeadline(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_serious_is_fifteen_calendar_days(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        deadline, remaining = pv.compute_reporting_deadline(True, received)
        self.assertEqual(datetime(2026, 1, 20, 10, 0, tzinfo=UTC), deadline)
        self.assertEqual(15, remaining)

    def test_non_serious_is_ninety_calendar_days(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        deadline, remaining = pv.compute_reporting_deadline(False, received)
        self.assertEqual(datetime(2026, 4, 1, 10, 0, tzinfo=UTC), deadline)
        self.assertEqual(90, remaining)

    def test_weekends_count_no_holiday_skipping(self):
        """Friday receipt + 15 days lands on a Saturday (2026-10-10)."""
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 9, 25, 9, 30, tzinfo=UTC)  # Friday
        deadline, _ = pv.compute_reporting_deadline(True, received)
        self.assertEqual(datetime(2026, 10, 10, 9, 30, tzinfo=UTC), deadline)
        self.assertEqual(4, received.weekday())  # Friday
        self.assertEqual(5, deadline.weekday())  # Saturday, not slipped to Monday
        non_serious, _ = pv.compute_reporting_deadline(False, received)
        self.assertEqual(datetime(2026, 12, 24, 9, 30, tzinfo=UTC), non_serious)

    def test_month_end_rollover(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 25, 23, 59, tzinfo=UTC)
        deadline, _ = pv.compute_reporting_deadline(True, received)
        self.assertEqual(datetime(2026, 2, 9, 23, 59, tzinfo=UTC), deadline)

    def test_year_end_rollover_ninety_days(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2025, 12, 20, 0, 0, tzinfo=UTC)
        deadline, _ = pv.compute_reporting_deadline(False, received)
        self.assertEqual(datetime(2026, 3, 20, 0, 0, tzinfo=UTC), deadline)

    def test_exact_ninetieth_day_remaining_zero(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
        deadline_guess = received + timedelta(days=90)
        deadline, remaining = pv.compute_reporting_deadline(
            False, received, now=deadline_guess
        )
        self.assertEqual(deadline_guess, deadline)
        self.assertEqual(0, remaining)

    def test_partial_days_round_up(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        _, remaining = pv.compute_reporting_deadline(
            True, received, now=received + timedelta(days=14, hours=1)
        )
        self.assertEqual(1, remaining)

    def test_overdue_is_negative(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        _, remaining = pv.compute_reporting_deadline(
            True, received, now=received + timedelta(days=18)
        )
        self.assertLess(remaining, 0)

    def test_naive_receipt_treated_as_utc(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        naive = datetime(2026, 1, 5, 10, 0)
        deadline, _ = pv.compute_reporting_deadline(True, naive)
        self.assertEqual(datetime(2026, 1, 20, 10, 0, tzinfo=UTC), deadline)
        self.assertIsNotNone(deadline.tzinfo)

    def test_offset_timezone_preserved(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        ist = timezone(timedelta(hours=5, minutes=30))
        received = datetime(2026, 1, 5, 10, 0, tzinfo=ist)
        deadline, _ = pv.compute_reporting_deadline(True, received)
        self.assertEqual(ist, deadline.tzinfo)
        self.assertEqual(received + timedelta(days=15), deadline)
        self.assertEqual(10, deadline.hour)

    def test_unknown_jurisdiction_falls_back_to_india_clock(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        self.assertEqual(
            pv.compute_reporting_deadline(True, received, "india"),
            pv.compute_reporting_deadline(True, received, "mars"),
            "an unknown jurisdiction must never zero the clock",
        )

    def test_india_explicit_jurisdiction(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        received = datetime(2026, 2, 27, 12, 0, tzinfo=UTC)
        deadline, _ = pv.compute_reporting_deadline(False, received, jurisdiction="india")
        self.assertEqual(datetime(2026, 5, 28, 12, 0, tzinfo=UTC), deadline)


# ─── F. PQC state machine ────────────────────────────────────────────────────

PQC_LEGAL = (
    ("captured", "investigating"),
    ("investigating", "disposition"),
    ("disposition", "capa"),
)
PQC_ILLEGAL = (
    ("captured", "disposition"),
    ("captured", "capa"),
    ("investigating", "capa"),
    ("investigating", "captured"),
    ("disposition", "captured"),
    ("capa", "captured"),
    ("capa", "disposition"),
    ("capa", "investigating"),
)


class TestComplaintStateMachine(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_legal_transitions_accepted(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for current, target in PQC_LEGAL:
            with self.subTest(f"{current}->{target}"):
                self.assertTrue(pv.is_legal_complaint_transition(current, target))
                self.assertEqual(target, pv.next_pqc_status(current, target))

    def test_illegal_transitions_rejected(self):
        """The spec's named case: capa -> captured must be rejected."""
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for current, target in PQC_ILLEGAL:
            with self.subTest(f"{current}->{target}"):
                self.assertFalse(pv.is_legal_complaint_transition(current, target))
                self.assertIsNone(pv.next_pqc_status(current, target))

    def test_self_transition_rejected(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for status in pv.PQC_STATUSES:
            self.assertFalse(pv.is_legal_complaint_transition(status, status), status)

    def test_unknown_states_rejected(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        for current, target in (("bogus", "captured"), ("captured", "bogus"), ("", "")):
            self.assertFalse(pv.is_legal_complaint_transition(current, target))
            self.assertIsNone(pv.next_pqc_status(current, target))

    def test_terminal_capa_has_no_successor(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        self.assertEqual((), pv.PQC_TRANSITIONS["capa"])


# ─── G. E2B-minimum export bundle (JSON key groups) ─────────────────────────

AE_CASE = {
    "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    "case_type": "AE",
    "clinic_id": "22222222-2222-2222-2222-222222222222",
    "call_id": "33333333-3333-3333-3333-333333333333",
    "product_id": "44444444-4444-4444-4444-444444444444",
    "product_name": "Azithral",
    "product_strength": "500mg",
    "reporter_type": "hcp",
    "reporter_contact": {"role": "doctor", "phone_suffix": "43210"},
    "patient_age": "54",
    "patient_sex": "female",
    "patient_initials": "RS",
    "event_text": "Rash and fever after the third dose",
    "event_onset_date": "2026-09-20",
    "outcome": "recovering",
    "seriousness_flags": ["hospitalisation"],
    "expectedness": "unknown",
    "causality_reporter": "suspected by reporter",
    "status": "new",
    "e2b_minimum_met": True,
    "source_channel": "voice",
    "recording_consent": "granted",
    "received_at": "2026-09-26T10:00:00+00:00",
    "notification_deadline": "2026-10-11T10:00:00+00:00",
    "notified_at": None,
}

AE_CASE_2 = dict(AE_CASE, id="bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                 event_text="Mild nausea after one tablet", seriousness_flags=[],
                 notification_deadline="2026-12-25T10:00:00+00:00")


class TestE2BExportBundle(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_bundle_key_groups_exactly_e2b_minimum(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        bundle = pv.build_e2b_case(AE_CASE)
        self.assertEqual(
            set(pv.E2B_CASE_GROUPS),
            set(bundle),
            "export must carry the E2B-minimum key groups and nothing else",
        )
        for group in (
            "sender_case_id",
            "primary_source",
            "reporter",
            "patient",
            "suspect_product",
            "event",
            "seriousness",
            "reporter_causality",
            "dates",
        ):
            self.assertIn(group, pv.E2B_CASE_GROUPS, group)

    def test_bundle_carries_the_captured_facts(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        bundle = pv.build_e2b_case(AE_CASE)
        self.assertEqual(str(AE_CASE["id"]), bundle["sender_case_id"])
        self.assertEqual("RS", bundle["patient"]["patient_initials"])
        self.assertEqual("2026-09-20", bundle["event"]["event_onset_date"])
        self.assertEqual(["hospitalisation"], bundle["seriousness"]["seriousness_flags"])
        self.assertEqual(True, bundle["seriousness"]["is_serious"])
        self.assertEqual(
            "suspected by reporter", bundle["reporter_causality"]["verbatim"]
        )
        self.assertIn("2026-09-26T10:00:00+00:00", bundle["dates"]["values"])
        self.assertIn("2026-10-11T10:00:00+00:00", bundle["dates"]["values"])
        self.assertEqual("2026-09-26", bundle["dates"]["day_zero"][:10])

    def test_bundle_contains_no_free_form_keys(self):
        """Every group is a fixed E2B(R3) data-element group: no ad-hoc keys."""
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        bundle = pv.build_e2b_case(AE_CASE)
        for group, value in bundle.items():
            self.assertIn(group, pv.E2B_CASE_GROUPS, group)
            if isinstance(value, dict):
                for key in value:
                    self.assertNotIn(" ", str(key), f"{group}.{key} looks free-form")
        self.assertEqual(9, len(pv.E2B_CASE_GROUPS))

    def test_flatten_mirrors_the_bundle(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        flat = pv.flatten_case(pv.build_e2b_case(AE_CASE))
        self.assertEqual(set(pv.CSV_COLUMNS), set(flat))
        self.assertEqual(str(AE_CASE["id"]), flat["sender_case_id"])
        self.assertEqual("hospitalisation", flat["seriousness_flags"])

    def test_csv_header_and_row_count(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        text = pv.export_csv_text([pv.build_e2b_case(AE_CASE), pv.build_e2b_case(AE_CASE_2)])
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(list(pv.CSV_COLUMNS), rows[0], "CSV header must be the flat E2B fields")
        self.assertEqual(3, len(rows), "header + one row per case")
        self.assertEqual(str(AE_CASE["id"]), rows[1][rows[0].index("sender_case_id")])

    def test_csv_is_header_only_when_empty(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        text = pv.export_csv_text([])
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual([list(pv.CSV_COLUMNS)], rows)

    def test_csv_mirrors_json_fields(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        bundle = pv.build_e2b_case(AE_CASE)
        flat = pv.flatten_case(bundle)
        rows = list(csv.reader(io.StringIO(pv.export_csv_text([bundle]))))
        for index, column in enumerate(pv.CSV_COLUMNS):
            self.assertEqual(
                str(flat[column]), rows[1][index], f"CSV {column} must mirror the JSON bundle"
            )

    def test_bundle_builder_tolerates_a_bare_minimum_case(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        bundle = pv.build_e2b_case(
            {"id": "cccccccc-cccc-4ccc-8ccc-cccccccccccc", "case_type": "AE"}
        )
        self.assertEqual(set(pv.E2B_CASE_GROUPS), set(bundle))
        self.assertEqual([], bundle["seriousness"]["seriousness_flags"])


# ─── H. Print view — captured facts only ─────────────────────────────────────


class TestPrintView(unittest.TestCase):
    def html(self) -> str:
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        return pv.render_case_html(AE_CASE)

    def test_print_view_is_self_contained_html(self):
        html = self.html()
        self.assertTrue(html.lstrip().lower().startswith("<!doctype html"))
        self.assertIn("<html", html)
        self.assertIn("</html>", html)
        self.assertIn("<style", html, "print view must be self-contained (inline CSS)")
        self.assertNotIn("<script", html.lower())
        self.assertNotIn("http://", html, "no external asset references")
        self.assertNotIn("https://", html)

    def test_print_view_shows_captured_facts(self):
        html = self.html()
        for fact in (
            "RS",
            "54",
            "female",
            "Azithral",
            "500mg",
            "hospitalisation",
            "Rash and fever after the third dose",
        ):
            self.assertIn(fact, html, f"missing captured fact {fact!r}")

    def test_print_view_carries_the_no_medical_advice_banner(self):
        html = self.html()
        self.assertIn(pv.PRINT_BANNER, html)
        self.assertIn("NO_MEDICAL_ADVICE", html)
        self.assertIn("SOURCE DATA ONLY", pv.PRINT_BANNER)

    def test_print_view_has_no_analysis_causality_or_advice(self):
        html = self.html()
        scanned = html.replace(pv.PRINT_BANNER, "").lower()
        for keyword in FORBIDDEN_PRINT_KEYWORDS:
            self.assertNotIn(keyword, scanned, f"print view leaks {keyword!r}")

    def test_banner_itself_stays_inside_the_keyword_ban(self):
        banner = pv.PRINT_BANNER.lower()
        for keyword in FORBIDDEN_PRINT_KEYWORDS:
            self.assertNotIn(keyword, banner, f"banner leaks {keyword!r}")

    def test_print_view_escapes_html(self):
        html = pv.render_case_html(
            dict(AE_CASE, event_text="<script>alert('x')</script>")
        )
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)


# ─── I. Product CSV seed parsing ─────────────────────────────────────────────

PRODUCT_CSV = (
    "name,generic_name,strength,dosage_form,manufacturer\n"
    "Azithral,azithromycin,500mg,tablet,Cipla\n"
    "Pan 40,pancreatinin,40mg,tablet,Abbott\n"
    "\n"
    "Augmentin,amoxicillin+clavulanate,625mg,tablet,GSK\n"
)


class TestProductCsvSeed(unittest.TestCase):
    def test_service_available(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")

    def test_parse_rows_and_errors(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        rows, errors = pv.parse_product_csv(PRODUCT_CSV)
        self.assertEqual(3, len(rows))
        self.assertEqual([], errors)
        self.assertEqual("Azithral", rows[0]["name"])
        self.assertEqual("500mg", rows[0]["strength"])
        self.assertEqual("tablet", rows[0]["dosage_form"])
        self.assertEqual("Cipla", rows[0]["manufacturer"])
        self.assertEqual("Pan 40", rows[1]["name"])

    def test_blank_lines_skipped(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        rows, errors = pv.parse_product_csv("name,strength\n\nA,1mg\n\n")
        self.assertEqual(1, len(rows))
        self.assertEqual([], errors)

    def test_row_without_name_is_an_error(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        rows, errors = pv.parse_product_csv("name,strength\n,10mg\nOk,5mg")
        self.assertEqual(1, len(rows))
        self.assertEqual(1, len(errors))
        self.assertIn("name", errors[0])

    def test_empty_csv_is_empty(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        rows, errors = pv.parse_product_csv("")
        self.assertEqual([], rows)
        self.assertEqual([], errors)

    def test_header_only_csv_is_empty(self):
        self.assertTrue(HAVE_SVC, "app/services/pharmacovigilance.py missing")
        rows, errors = pv.parse_product_csv("name,strength,dosage_form\n")
        self.assertEqual([], rows)
        self.assertEqual([], errors)


# ─── J. Schema: four tables, RLS, FORCE, policies, grants ───────────────────


class TestPvSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCHEMA_SQL)

    def test_four_tables_created_idempotently(self):
        for table in PV_TABLES:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table} ", self.text,
                          f"missing idempotent CREATE TABLE for {table}")

    def test_products_columns(self):
        block = sql_table_block(self.text, "products")
        self.assertTrue(block, "products table missing")
        for column in (
            "id UUID PRIMARY KEY",
            "clinic_id UUID NOT NULL REFERENCES clinics(id)",
            "name TEXT NOT NULL",
            "generic_name TEXT",
            "strength TEXT",
            "dosage_form TEXT",
            "manufacturer TEXT",
            "approved_label_json JSONB",
            "is_active BOOLEAN",
        ):
            self.assertIn(column, block, f"products missing {column}")

    def test_adverse_events_columns(self):
        block = sql_table_block(self.text, "adverse_events")
        self.assertTrue(block, "adverse_events table missing")
        for column in (
            "clinic_id UUID NOT NULL REFERENCES clinics(id)",
            "call_id UUID REFERENCES calls(id) ON DELETE SET NULL",
            "product_id UUID REFERENCES products(id) ON DELETE SET NULL",
            "reporter_type TEXT",
            "reporter_contact JSONB",
            "patient_age TEXT",
            "patient_sex TEXT",
            "patient_initials TEXT",
            "event_text TEXT",
            "event_onset_date DATE",
            "outcome TEXT",
            "seriousness_flags JSONB",
            "expectedness TEXT",
            "causality_reporter TEXT",
            "e2b_minimum_met BOOLEAN",
            "status TEXT",
            "notification_deadline TIMESTAMPTZ",
            "notified_at TIMESTAMPTZ",
            "source_channel TEXT",
            "recording_consent TEXT",
        ):
            self.assertIn(column, block, f"adverse_events missing {column}")

    def test_quality_complaints_columns(self):
        block = sql_table_block(self.text, "quality_complaints")
        self.assertTrue(block, "quality_complaints table missing")
        for column in (
            "clinic_id UUID NOT NULL REFERENCES clinics(id)",
            "call_id UUID REFERENCES calls(id) ON DELETE SET NULL",
            "product_id UUID REFERENCES products(id) ON DELETE SET NULL",
            "batch_no TEXT",
            "expiry DATE",
            "defect_description TEXT",
            "photos_url JSONB",
            "severity TEXT",
            "investigation_status TEXT",
            "disposition TEXT",
            "capa_ref TEXT",
            "recording_consent TEXT",
        ):
            self.assertIn(column, block, f"quality_complaints missing {column}")

    def test_medical_inquiries_columns(self):
        block = sql_table_block(self.text, "medical_inquiries")
        self.assertTrue(block, "medical_inquiries table missing")
        for column in (
            "clinic_id UUID NOT NULL REFERENCES clinics(id)",
            "call_id UUID REFERENCES calls(id) ON DELETE SET NULL",
            "product_id UUID REFERENCES products(id) ON DELETE SET NULL",
            "question_text TEXT",
            "category TEXT",
            "language TEXT",
            "response_text TEXT",
            "status TEXT",
        ):
            self.assertIn(column, block, f"medical_inquiries missing {column}")

    def test_product_dictionary_idempotency_key(self):
        self.assertIn("uq_products_identity", self.text)
        block = sql_table_block(self.text, "products")
        self.assertIn("UNIQUE (clinic_id, name, strength, dosage_form)", block)

    def test_rls_enabled_and_forced_on_all_four(self):
        for table in PV_TABLES:
            self.assertIn(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY", self.text)
            self.assertIn(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY", self.text)

    def test_manage_policies_mirror_payments_manage(self):
        for table in PV_TABLES:
            policy = f"CREATE POLICY {table}_manage"
            self.assertIn(policy, self.text, f"missing {table}_manage policy")
            block = self.text.split(policy, 1)[1].split("CREATE POLICY", 1)[0]
            self.assertIn("clinic_id IN (", block, f"{table}_manage: clinic scope missing")
            self.assertIn(
                "app.service_request", block, f"{table}_manage: service bypass missing"
            )
            self.assertIn("auth.uid()", block, f"{table}_manage: membership scope missing")

    def test_grants_for_the_runtime_roles(self):
        for table in PV_TABLES:
            self.assertIn(f"GRANT ALL ON {table} TO authenticated", self.text)
            self.assertIn(f"GRANT ALL ON {table} TO medicall_app", self.text)

    def test_pv_indexes_present(self):
        for index in (
            "idx_adverse_events_clinic_status",
            "idx_adverse_events_deadline",
            "idx_quality_complaints_clinic_status",
            "idx_medical_inquiries_clinic_status",
            "idx_products_clinic",
        ):
            self.assertIn(index, self.text, f"missing index {index}")

    def test_existing_schema_untouched(self):
        """The nine RLS tables + payments_manage must survive verbatim."""
        for policy in (
            "clinic_own_data",
            "users_own_data",
            "clinic_staff_read",
            "calls_create",
            "calls_read",
            "calls_update",
            "appointments_manage",
            "prescriptions_manage",
            "payments_manage",
            "notifications_send",
            "compliance_manage",
            "clinic_users_own",
            "clinic_users_manage",
            "clinic_users_service_insert",
            "clinics_create",
            "language_codes_read",
        ):
            self.assertIn(f"CREATE POLICY {policy} ON", self.text, f"lost {policy}")


# ─── K. ORM models + repository helpers ─────────────────────────────────────

PV_REPO_FNS = (
    "create_product",
    "find_product",
    "list_products",
    "create_adverse_event",
    "get_adverse_event",
    "list_adverse_events",
    "create_quality_complaint",
    "get_quality_complaint",
    "list_quality_complaints",
    "update_quality_complaint",
    "create_medical_inquiry",
    "list_medical_inquiries",
)


class TestPvOrm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(POSTGRES)

    def test_four_models_typed(self):
        for model in PV_MODELS:
            self.assertIn(f"class {model}(Base):", self.text, f"missing model {model}")
            self.assertIn(f'__tablename__ = "', model_block(self.text, model))

    def test_models_use_mapped_column_and_jsonb(self):
        for model in PV_MODELS:
            block = model_block(self.text, model)
            self.assertIn("mapped_column", block, f"{model}: not a typed model")
        self.assertIn("seriousness_flags: Mapped[list]", model_block(self.text, "AdverseEvent"))
        self.assertIn(
            "approved_label_json: Mapped[Optional[dict]]",
            model_block(self.text, "Product"),
        )

    def test_models_foreign_key_calls_and_products(self):
        for model in ("AdverseEvent", "QualityComplaint", "MedicalInquiry"):
            block = model_block(self.text, model)
            self.assertIn('ForeignKey("calls.id", ondelete="SET NULL")', block)
            self.assertIn('ForeignKey("products.id", ondelete="SET NULL")', block)
            self.assertIn('ForeignKey("clinics.id", ondelete="CASCADE")', block)

    def test_product_uniqueness_constraint_in_orm(self):
        block = model_block(self.text, "Product")
        self.assertIn("__table_args__", block)
        self.assertIn("UniqueConstraint", model_block(self.text, "Product")[:400])

    def test_repository_helpers_exist(self):
        names = set(fns(py_tree(POSTGRES)))
        for fn in PV_REPO_FNS:
            self.assertIn(fn, names, f"postgres.py missing repository helper {fn}")

    def test_deadline_ordered_ae_listing(self):
        """Overdue serious cases float to the top of the dashboard list."""
        block = fn_block(self.text, "list_adverse_events")
        self.assertIn("notification_deadline", block)
        self.assertIn("asc", block.lower())


# ─── L. Router: /api/pv surface, guards, audit ──────────────────────────────

PV_ROUTES = {
    ("post", "/products"),
    ("post", "/products/import"),
    ("post", "/cases"),
    ("get", "/cases"),
    ("post", "/export"),
    ("get", "/cases/{case_id}/print"),
    ("patch", "/complaints/{complaint_id}"),
}

SERVICE_GUARDED = ("create_pv_case_ep",)
IDENTITY_GATED = (
    "create_product_ep",
    "import_products_ep",
    "list_pv_cases_ep",
    "export_pv_ep",
    "print_pv_case_ep",
    "update_complaint_ep",
)


class TestPvRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PV_ROUTER)
        cls.tree = py_tree(PV_ROUTER)

    def test_router_file_with_prefix(self):
        self.assertTrue(PV_ROUTER.exists(), "app/api/pv.py missing")
        self.assertEqual("/api/pv", router_prefix(self.tree), "pv router prefix wrong")

    def test_route_set(self):
        found = {(verb, path) for verb, path, _ in endpoints(self.tree)}
        self.assertEqual(PV_ROUTES, found, f"pv route set differs: {sorted(found)}")

    def test_service_token_guard_on_case_intake(self):
        block = fn_block(self.text, "create_pv_case_ep")
        self.assertIn("WEBHOOK_SERVICE_TOKEN", block, "intake must verify the service token")
        self.assertIn("X-Service-Token", block)
        self.assertIn("hmac", self.text, "token compare must be constant-time")
        self.assertIn("service_request_ctx", block, "intake writes arm the RLS bypass")
        self.assertNotIn("get_current_user", block, "intake is identity-free by design")

    def test_dashboard_and_dictionary_routes_identity_gated(self):
        for name in IDENTITY_GATED:
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertIn("get_current_user", block, f"{name} must be identity-gated")
                self.assertNotIn("WEBHOOK_SERVICE_TOKEN", block)

    def test_intake_runs_classify_validate_and_clock(self):
        block = fn_block(self.text, "create_pv_case_ep")
        for token in (
            "classify_contact_type",
            "validate_minimum_criteria",
            "classify_seriousness",
            "compute_reporting_deadline",
        ):
            self.assertIn(token, block, f"intake must call {token}")
        self.assertIn("create_adverse_event", block)
        self.assertIn("create_quality_complaint", block)
        self.assertIn("create_medical_inquiry", block)
        self.assertIn("e2b_minimum_met", block, "incomplete cases are stored, not dropped")

    def test_recording_consent_flows_from_the_call_row(self):
        block = fn_block(self.text, "create_pv_case_ep")
        self.assertIn("get_call", block, "consent must be read from the parent call")
        self.assertIn("recording_consent", block)

    def test_compliance_audit_row_on_every_write(self):
        self.assertIn("create_compliance_event", self.text)
        for name in ("create_pv_case_ep", "update_complaint_ep"):
            block = fn_block(self.text, name)
            self.assertIn(
                "create_compliance_event", block, f"{name}: missing compliance_events audit"
            )
        text_all = self.text
        self.assertIn("pv_case_intake", text_all)
        self.assertIn("pqc_disposition", text_all)

    def test_complaint_patch_rejects_illegal_transitions(self):
        block = fn_block(self.text, "update_complaint_ep")
        self.assertIn("next_pqc_status", block)
        self.assertIn("409", block, "an illegal transition is a conflict, not a 500")

    def test_export_formats(self):
        block = fn_block(self.text, "export_pv_ep")
        self.assertIn("build_e2b_case", block)
        self.assertIn("export_csv_text", block)
        self.assertIn("format", block)

    def test_print_route_returns_html(self):
        block = fn_block(self.text, "print_pv_case_ep")
        self.assertIn("render_case_html", block)
        self.assertIn("HTMLResponse", block)

    def test_router_imports_pv_service_and_db_layer(self):
        self.assertIn("from app.services.pharmacovigilance import", self.text)
        self.assertIn("from app.db.postgres import", self.text)


class TestMainRegistration(unittest.TestCase):
    def test_main_imports_and_registers_pv(self):
        text = read(MAIN)
        self.assertIn("pv,", text, "main.py must import the pv router module")
        self.assertIn("app.include_router(pv.router", text)
        self.assertEqual("/api/pv", router_prefix(py_tree(PV_ROUTER)))


# ─── M. pv_alert notification kind (optional item, default on) ───────────────


class TestPvAlertNotification(unittest.TestCase):
    def test_kind_registered_in_both_catalogs(self):
        for path, const in (
            (SCHEMAS / "notification.py", "NOTIFICATION_KINDS"),
            (SERVICES / "notifications.py", "KINDS"),
        ):
            consts = module_literal_consts(read(path))
            self.assertIn(
                "pv_alert", consts.get(const, ()), f"{path.name}: {const} missing pv_alert"
            )

    def test_pv_alert_email_first_with_fallback(self):
        consts = module_literal_consts(read(SERVICES / "notifications.py"))
        order = consts.get("DEFAULT_CHANNEL_ORDER", {}).get("pv_alert", ())
        self.assertTrue(order, "pv_alert needs a channel order")
        self.assertEqual("email", order[0], "the PVOIC mailbox is an email recipient")

    def test_pv_alert_templates_in_all_five_languages(self):
        consts = module_literal_consts(read(SERVICES / "notifications.py"))
        templates = consts.get("MESSAGE_TEMPLATES", {}).get("pv_alert", {})
        self.assertEqual(
            {"hi", "en", "ta", "te", "bn"},
            set(templates),
            "every kind carries 5-language templates (Q2/A2c)",
        )
        for language, template in templates.items():
            self.assertIn("{case_id}", template, language)
            self.assertIn("{deadline}", template, language)

    def test_pv_alert_email_subject(self):
        consts = module_literal_consts(read(SERVICES / "notifications.py"))
        self.assertIn("pv_alert", consts.get("MESSAGE_SUBJECTS", {}))

    def test_serious_ae_capture_dispatches_pv_alert_env_gated(self):
        text = read(PV_ROUTER)
        self.assertIn("PV_PVOIC_EMAIL", text, "the alert mailbox is env-gated")
        self.assertIn("pv_alert", text)
        block = fn_block(text, "create_pv_case_ep")
        self.assertIn("send_notification", block)
        self.assertIn("create_notification", block)

    def test_pv_alert_is_non_fatal(self):
        """A missing mailbox or channel key must never fail the intake."""
        text = read(PV_ROUTER)
        block = fn_block(text, "create_pv_case_ep")
        self.assertIn("except Exception", block, "pv_alert must be best-effort")

    def test_env_documented(self):
        self.assertIn("PV_PVOIC_EMAIL", read(ENV_EXAMPLE))
        self.assertIn("PV_PVOIC_EMAIL", read(DEPLOY_DOC))


if __name__ == "__main__":
    unittest.main(verbosity=2)
