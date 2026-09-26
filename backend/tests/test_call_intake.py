"""Phase-2 slice 2B — in-call voice capture (spec-micc-pv-phase2.md §2B).

RED before implementation (2026-09-26): no app/services/call_intake.py, no PV
intents in app/services/agent_logic.py, no hangup payload builder in
app/services/livekit_agent.py.

GREEN after implementation: the pure stdlib call-intake module (intent routing
over the 5 languages, minimum-criteria field extraction, the in-language
follow-up script, special-situation flags, and the exact POST /api/pv/cases
body), the agent_logic handler that runs the whole pipeline, and the
livekit_agent hangup seam that hands that body to the D1 persistence point.
NO network, NO livekit import, NO process, NO render in any test.

Run: py -3.14 -m unittest discover -s tests -p "test_call_intake.py"   (from backend/)
"""
import ast
import sys
import unittest
from datetime import date
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

SERVICES = BACKEND / "app" / "services"
API_DIR = BACKEND / "app" / "api"
CALL_INTAKE_PY = SERVICES / "call_intake.py"
AGENT_LOGIC_PY = SERVICES / "agent_logic.py"
AGENT_PY = SERVICES / "livekit_agent.py"
PV_ROUTER = API_DIR / "pv.py"

# Same whitelist the Phase-1 PV gate uses, plus the stdlib roots this module
# legitimately needs. `app` = repo modules.
STDLIB_ROOTS = {
    "csv",
    "datetime",
    "functools",
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

# A network client in a PV collector would be a reportable smell, not a feature:
# the collector records, the gateway sends. urllib/http/socket are stdlib but
# banned here on purpose.
FORBIDDEN_ROOTS = {
    "requests",
    "httpx",
    "urllib",
    "http",
    "socket",
    "aiohttp",
    "asyncio",
    "subprocess",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def py_tree_text(text: str):
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


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


def fns(tree) -> dict:
    out = {}
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def pydantic_fields(text: str, cls: str) -> set:
    """Field names of a pydantic BaseModel, read from source (no pydantic import)."""
    tree = py_tree_text(text)
    if tree is None:
        return set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or node.name != cls:
            continue
        names = set()
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                names.add(item.target.id)
            elif isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Name):
                names.add(item.targets[0].id)
        return names
    return set()


def router_prefix(text: str) -> str:
    tree = py_tree_text(text)
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            call = node.value
            is_router = getattr(call.func, "id", None) == "APIRouter" or (
                isinstance(call.func, ast.Attribute) and call.func.attr == "APIRouter"
            )
            if is_router:
                for kw in call.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        return kw.value.value
    return ""


def router_paths(text: str) -> set:
    tree = py_tree_text(text)
    out = set()
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
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
                out.add((deco.func.attr.lower(), deco.args[0].value))
    return out


try:  # behavioural suites import the stdlib-only modules normally
    from app.services import pharmacovigilance as pv  # noqa: E402
    from app.services import call_intake  # noqa: E402
    from app.services import agent_logic  # noqa: E402

    HAVE_INTAKE = True
except ImportError:  # pragma: no cover - RED state
    pv = call_intake = agent_logic = None
    HAVE_INTAKE = False


# ─── A. Module shape, purity, reuse ─────────────────────────────────────────

PIPELINE_FUNCTIONS = (
    "detect_intent",
    "extract_case_fields",
    "question_script",
    "special_situation_flags",
    "build_case_payload",
)


class TestModuleShape(unittest.TestCase):
    def test_module_exists(self):
        self.assertTrue(CALL_INTAKE_PY.exists(), "app/services/call_intake.py missing")

    def test_module_is_stdlib_only(self):
        roots = module_import_roots(read(CALL_INTAKE_PY))
        self.assertTrue(roots, "no imports parsed")
        self.assertEqual(
            set(), roots - (STDLIB_ROOTS | {"app"}), f"non-stdlib: {sorted(roots - STDLIB_ROOTS)}"
        )

    def test_module_makes_no_network_or_process_call(self):
        roots = module_import_roots(read(CALL_INTAKE_PY))
        self.assertEqual(
            set(), roots & FORBIDDEN_ROOTS, f"collector must not reach out: {sorted(roots)}"
        )

    def test_module_is_class_free(self):
        tree = py_tree_text(read(CALL_INTAKE_PY))
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)] if tree else []
        self.assertEqual([], classes, "call_intake.py must stay class-free (house rule)")

    def test_pipeline_functions_present(self):
        names = set(fns(py_tree_text(read(CALL_INTAKE_PY))))
        for fn in PIPELINE_FUNCTIONS:
            self.assertIn(fn, names, f"call_intake.py missing {fn}")

    def test_reuses_phase1_classifier_and_criteria(self):
        """No reimplementation: the Phase-1 primitives are the only source."""
        src = read(CALL_INTAKE_PY)
        tree = py_tree_text(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported |= {alias.name for alias in node.names}
        self.assertIn("classify_contact_type", imported)
        self.assertIn("validate_minimum_criteria", imported)
        self.assertIn("classify_seriousness", imported)
        self.assertIn("MINIMUM_CRITERIA_ELEMENTS", src)

    def test_agent_logic_imports_the_intake_module(self):
        self.assertIn("call_intake", read(AGENT_LOGIC_PY))

    def test_nothing_tests_import_brings_in_livekit(self):
        """agent_logic + call_intake must be importable with livekit absent."""
        self.assertNotIn("livekit", sys.modules)
        self.assertNotIn("livekit.agents", sys.modules)
        self.assertNotIn("app.services.livekit_agent", sys.modules)

    def test_agent_logic_source_has_no_livekit_import(self):
        """Import roots, not the word: both docstrings name the voice worker.

        What must not happen is agent_logic IMPORTING it - the wording that
        explains where the logic runs is documentation, not a dependency.
        """
        roots = module_import_roots(read(AGENT_LOGIC_PY))
        self.assertNotIn("livekit", roots, "agent_logic must import no voice SDK")
        self.assertNotIn("livekit.agents", roots)

    def test_call_intake_source_has_no_livekit_import(self):
        roots = module_import_roots(read(CALL_INTAKE_PY))
        self.assertNotIn("livekit", roots, "the collector must import no voice SDK")
        self.assertNotIn("livekit.agents", roots)


# ─── B. detect_intent — 5 languages x ae/pqc/mi/none ────────────────────────

HI_AE = (
    "मैं डॉक्टर हूँ। मेरे मरीज की उम्र 45 साल है और वह महिला हैं, "
    "प्रथमाक्षर ए.के.। उसने कल से दवा Dolo 650 ली और बुखार तथा उल्टी हो गई। "
    "अभी हाल में ठीक नहीं हुई। इस दवा की वजह से ऐसा हुआ।"
)
# The same call, truncated: a safety signal with no case detail captured yet.
HI_PARTIAL = "मुझे इस दवा से बुखार हो रहा है।"
# A wrong medicine AND too many tablets in one call: two reportable special
# situations, neither of which is an ICH E2A seriousness criterion.
TA_AE = (
    "நான் மருத்துவர். நோயாளி வயது 30 வயது ஆண், முதல் எழுத்து ஆர்.கே. "
    "நேற்று தவறான மருந்து Telma 40 எடுத்து அதிகமாக மாத்திரை எடுத்தேன். "
    "இப்போது இன்னும் சரியாக இல்லை. இதனால் தான் நினைக்கிறேன்."
)
TE_PQC = (
    "ప్యాకెట్ పగిలి ఉంది, బ్యాచ్ నంబర్ AB1234, ముగుదురు తేదీ 05/2027. "
    "ఇది మరియు గుర్తు లేదు."
)
BN_MI = (
    "আমি রোগীর ছেলে। রোগীর বয়স 32 বছর। "
    "ওষুধটি Dolo 650 প্রতিদিন কতবার খাব? দুধের সাথে খাওয়া যাবে কি?"
)
EN_SERIOUS = (
    "My mother is 78, female, initials A.K. She took too many tablets of Dolo 650 "
    "two days ago and now she is unconscious. She died this morning."
)
EN_NONE = "I would like to book an appointment with the doctor for next Tuesday."

INTENT_CASES = (
    ("hi", HI_AE, "ae"),
    ("ta", TA_AE, "ae"),
    ("bn", BN_MI, "mi"),
    ("en", EN_SERIOUS, "ae"),
    ("en", "the strip arrived broken and the tablets are loose", "pqc"),
    ("hi", "पैकेट फटा हुआ है और गोलियाँ रंग बदली हुई हैं", "pqc"),
    ("ta", "மருந்து எடுக்க எவ்வளவு வேண்டும் என்று கேள்கிறேன்", "mi"),
    ("te", "ఎంత మోతాదు తీసుకోవాలి అని అడుగుతున్నాను", "mi"),
    ("bn", "এটি কীভাবে খাব বলুন, কতটুকু লাগবে", "mi"),
    ("en", EN_NONE, "none"),
    ("hi", "मुझे अगले मंगलवार को डॉक्टर से मिलना है", "none"),
    ("ta", "நேரம் வரண்டும், அப்பாய்ண்ட்மென்ட் வேணும்", "none"),
    ("te", "ఇప్పుడు వచ్చేటప్పటికే నిధి కావాలి", "none"),
    ("bn", "আগামী মঙ্গলবার ডাক্তারের সাথে দেখা করতে চাই", "none"),
)


class TestDetectIntent(unittest.TestCase):
    def test_intent_routing_all_languages(self):
        for language, text, expected in INTENT_CASES:
            with self.subTest(lang=language, expected=expected):
                result = call_intake.detect_intent(text, language)
                self.assertIsInstance(result, dict)
                self.assertEqual(expected, result["intent"])

    def test_intent_is_derived_from_the_phase1_classifier(self):
        """Same words -> same bucket as the endpoint's own classifier."""
        for language, text, _expected in INTENT_CASES:
            with self.subTest(lang=language):
                result = call_intake.detect_intent(text, language)
                self.assertEqual(
                    pv.classify_contact_type(text, language), result["contact_type"]
                )

    def test_detect_returns_auditable_evidence(self):
        result = call_intake.detect_intent(HI_AE, "hi")
        self.assertEqual("AE", result["contact_type"])
        self.assertTrue(result["matched_phrases"], "no phrase evidence for the routing")
        self.assertEqual("hi", result["language"])
        self.assertTrue(result["is_pv_intent"])

    def test_intent_none_is_not_a_pv_intent(self):
        result = call_intake.detect_intent(EN_NONE, "en")
        self.assertEqual("none", result["intent"])
        self.assertEqual("OTHER", result["contact_type"])
        self.assertFalse(result["is_pv_intent"])
        self.assertEqual([], result["matched_phrases"])
        self.assertEqual("", result["function"])

    def test_empty_transcript_is_none(self):
        self.assertEqual("none", call_intake.detect_intent("", "en")["intent"])
        self.assertEqual("none", call_intake.detect_intent("   ", "hi")["intent"])

    def test_unknown_language_still_routes(self):
        """A mislabelled call must not be dropped from safety triage."""
        result = call_intake.detect_intent(HI_AE, "zz")
        self.assertEqual("ae", result["intent"])
        self.assertEqual("en", result["language"], "unknown code normalizes to en")

    def test_special_situation_routes_to_ae(self):
        result = call_intake.detect_intent("the syrup is not working at all", "en")
        self.assertEqual("ae", result["intent"])
        self.assertEqual("AE", pv.classify_contact_type("the syrup is not working at all", "en"))

    def test_function_names_match_the_llm_schema_one_to_one(self):
        names = {f["name"] for f in call_intake.PV_FUNCTIONS}
        routed = {
            call_intake.detect_intent(text, lang)["function"]
            for lang, text, _ in INTENT_CASES
        }
        routed.discard("")
        self.assertEqual(names, routed, "PV_FUNCTIONS must cover every routed intent")

    def test_pv_functions_follow_the_medical_functions_shape(self):
        for entry in call_intake.PV_FUNCTIONS:
            with self.subTest(fn=entry["name"]):
                self.assertEqual({"name", "description", "parameters"}, set(entry))
                self.assertEqual("object", entry["parameters"]["type"])
                self.assertIn("properties", entry["parameters"])


# ─── C. extract_case_fields — exact fields + determinism ─────────────────────

TODAY = date(2026, 9, 26)


class TestExtractCaseFields(unittest.TestCase):
    def test_hindi_ae_fields(self):
        fields = call_intake.extract_case_fields(HI_AE, "ae", "hi", today=TODAY)
        self.assertEqual({"age": "45", "sex": "female", "initials": "ए.के."}, fields["patient"])
        self.assertEqual("Dolo", fields["product_name"])
        self.assertEqual("hcp", fields["reporter_type"])
        self.assertEqual("not_recovered", fields["outcome"])
        self.assertEqual("2026-09-25", fields["event_onset_date"], "कल = yesterday")
        self.assertEqual("इस दवा की वजह से ऐसा हुआ।", fields["causality_reporter"])
        self.assertEqual(HI_AE.strip(), fields["event_text"], "event text stays verbatim")

    def test_the_intent_shows_only_in_the_filled_verbatim_column(self):
        """No `intent` key: the intake schema declares 20 fields and this is all of them.

        The single verbatim column the intent routes to IS the record of intent,
        so adding a 21st key would only risk a field the endpoint would drop.
        """
        for intent in ("ae", "pqc", "mi"):
            with self.subTest(intent=intent):
                fields = call_intake.extract_case_fields(HI_AE, intent, "hi", today=TODAY)
                self.assertNotIn("intent", fields)
                filled = [
                    column
                    for column in ("event_text", "question_text", "defect_description")
                    if fields[column]
                ]
                self.assertEqual([call_intake.INTENT_TEXT_COLUMNS[intent]], filled)

    def test_tamil_ae_fields(self):
        fields = call_intake.extract_case_fields(TA_AE, "ae", "ta", today=TODAY)
        self.assertEqual({"age": "30", "sex": "male", "initials": "ஆர்.கே."}, fields["patient"])
        self.assertEqual("Telma", fields["product_name"], "label-phrase capture, not the seed list")
        self.assertEqual("hcp", fields["reporter_type"])
        self.assertEqual("2026-09-25", fields["event_onset_date"], "நேற்று = yesterday")
        self.assertEqual("not_recovered", fields["outcome"])
        self.assertEqual("இதனால் தான் நினைக்கிறேன்.", fields["causality_reporter"])

    def test_telugu_pqc_fields(self):
        fields = call_intake.extract_case_fields(TE_PQC, "pqc", "te", today=TODAY)
        self.assertEqual("AB1234", fields["batch_no"], "batch case is preserved verbatim")
        self.assertEqual("2027-05-01", fields["expiry"], "05/2027 normalizes to ISO")
        self.assertEqual(TE_PQC.strip(), fields["defect_description"])
        self.assertEqual("", fields["product_name"], "no product name on the pack -> blank")
        self.assertEqual("", fields["event_onset_date"])

    def test_bengali_mi_fields(self):
        fields = call_intake.extract_case_fields(BN_MI, "mi", "bn", today=TODAY)
        self.assertEqual("Dolo", fields["product_name"])
        self.assertEqual("32", fields["patient"]["age"])
        self.assertEqual("patient", fields["reporter_type"], "a family member reporting")
        self.assertEqual(BN_MI.strip(), fields["question_text"])
        self.assertEqual("", fields["event_text"], "MI does not fill the AE event column")

    def test_english_serious_fields(self):
        fields = call_intake.extract_case_fields(EN_SERIOUS, "ae", "en", today=TODAY)
        self.assertEqual({"age": "78", "sex": "female", "initials": "A.K."}, fields["patient"])
        self.assertEqual("fatal", fields["outcome"])
        self.assertEqual("2026-09-24", fields["event_onset_date"], "two days ago")
        self.assertEqual("patient", fields["reporter_type"])

    def test_strength_extraction(self):
        fields = call_intake.extract_case_fields(
            "After taking Azithral 500 mg twice I felt dizzy", "ae", "en"
        )
        self.assertEqual("500 mg", fields["product_strength"])

    def test_months_are_kept_with_their_unit(self):
        fields = call_intake.extract_case_fields(
            "my baby is 6 months old and developed rash", "ae", "en"
        )
        self.assertEqual("6 months", fields["patient"]["age"])

    def test_native_digits_are_normalized(self):
        fields = call_intake.extract_case_fields(
            "उम्र ४५ साल है और दवा से बुखार आया", "ae", "hi", today=TODAY
        )
        self.assertEqual("45", fields["patient"]["age"], "devanagari digits -> ascii")

    def test_a_title_is_not_a_patient_initial(self):
        """"Mr. R." is a doctor being addressed, not a patient's initials."""
        fields = call_intake.extract_case_fields(
            "I am Dr. Rao's nurse, the patient A.K. developed a rash", "ae", "en"
        )
        self.assertEqual("A.K.", fields["patient"]["initials"])

    def test_a_sex_word_inside_another_word_is_not_a_sex(self):
        """"too many" contains "man"; a substring match would invent a sex."""
        fields = call_intake.extract_case_fields(
            "She took too many tablets of Dolo 650 this morning", "ae", "en"
        )
        self.assertEqual("", fields["patient"]["sex"], "never inferred from a substring")

    def test_expectedness_is_never_inferred(self):
        """Expectedness is a PV-officer judgement against the approved label."""
        for language, text, intent in INTENT_CASES:
            with self.subTest(lang=language):
                fields = call_intake.extract_case_fields(text, intent, language, today=TODAY)
                self.assertEqual("", fields["expectedness"])

    def test_extraction_is_deterministic(self):
        for language, text, intent in INTENT_CASES:
            with self.subTest(lang=language):
                first = call_intake.extract_case_fields(text, intent, language, today=TODAY)
                second = call_intake.extract_case_fields(text, intent, language, today=TODAY)
                self.assertEqual(first, second)
                self.assertEqual(sorted(first), sorted(second), "key set is stable too")

    def test_field_set_is_stable_across_intents(self):
        reference = sorted(call_intake.extract_case_fields(HI_AE, "ae", "hi"))
        for language, text, intent in INTENT_CASES:
            with self.subTest(lang=language, intent=intent):
                self.assertEqual(
                    reference, sorted(call_intake.extract_case_fields(text, intent, language))
                )

    def test_onset_needs_a_reference_date(self):
        """No `today` -> no invented date (the API would 422 on a guess)."""
        self.assertEqual("", call_intake.extract_case_fields(HI_AE, "ae", "hi")["event_onset_date"])

    def test_no_transcript_means_no_fields(self):
        fields = call_intake.extract_case_fields("", "ae", "en", today=TODAY)
        self.assertEqual("", fields["product_name"])
        self.assertEqual({}, fields["patient"])
        self.assertEqual([], fields["seriousness_flags"])


# ─── D. question_script — exactly the missing minimum-criteria elements ─────

COMPLETE_AE = {
    "event_text": "fever and vomiting after the tablet",
    "product_name": "Dolo",
    "patient": {"age": "45"},
    "reporter_contact": {"phone_suffix": "1234"},
}
PARTIAL_AE = {"event_text": "fever after the tablet", "patient": {"age": "45"}}


class TestQuestionScript(unittest.TestCase):
    def test_complete_ae_case_asks_nothing(self):
        script = call_intake.question_script("ae", "hi", fields=COMPLETE_AE)
        self.assertEqual([], script)

    def test_script_is_exactly_the_missing_elements(self):
        script = call_intake.question_script("ae", "en", fields=PARTIAL_AE)
        met, missing = call_intake.intake_minimum_criteria(PARTIAL_AE)
        self.assertFalse(met)
        self.assertEqual(["reporter", "product"], missing)
        self.assertEqual(len(missing), len(script))
        self.assertEqual(
            [call_intake.QUESTION_BANK[("ae", element, "en")] for element in missing],
            script,
            "one question per missing element, in canonical order",
        )

    def test_canonical_order_is_preserved(self):
        script = call_intake.question_script("ae", "en", fields={})
        self.assertEqual(
            [
                call_intake.QUESTION_BANK[("ae", element, "en")]
                for element in pv.MINIMUM_CRITERIA_ELEMENTS
            ],
            script,
        )

    def test_script_never_reasks_a_captured_field(self):
        for element in pv.MINIMUM_CRITERIA_ELEMENTS:
            with self.subTest(element=element):
                fields = dict(COMPLETE_AE)
                if element == "reporter":
                    fields.pop("reporter_contact")
                elif element == "product":
                    fields["product_name"] = ""
                elif element == "event":
                    fields["event_text"] = ""
                else:
                    fields["patient"] = {}
                script = call_intake.question_script("ae", "en", fields=fields)
                self.assertEqual(1, len(script))
                self.assertEqual(call_intake.QUESTION_BANK[("ae", element, "en")], script[0])

    def test_pqc_always_asks_the_batch_number(self):
        """Batch/lot is mandatory for a complaint even when the E2B minimum is met.

        The complaint has no patient - the complainant IS the reporter - so the
        endpoint's E2B check still reports `patient` as missing while the
        script must NOT ask a complaint caller for a patient's age. Batch is the
        one element asked from EXTRA_REQUIRED_ELEMENTS, outside the E2B four.
        """
        fields = {
            "defect_description": "the strip was torn",
            "product_name": "Crocin",
            "reporter_contact": {"phone_suffix": "99"},
        }
        met, missing = call_intake.intake_minimum_criteria(fields)
        self.assertEqual(["patient"], missing, "a complaint has no patient to identify")
        script = call_intake.question_script("pqc", "en", fields=fields)
        self.assertEqual([call_intake.QUESTION_BANK[("pqc", "batch", "en")]], script)
        self.assertNotIn("patient", call_intake.INTENT_REQUIRED_ELEMENTS["pqc"])

    def test_pqc_script_keeps_the_complaint_order(self):
        script = call_intake.question_script("pqc", "en", fields={})
        self.assertEqual(
            [
                call_intake.QUESTION_BANK[("pqc", element, "en")]
                for element in call_intake.INTENT_REQUIRED_ELEMENTS["pqc"]
            ],
            script,
        )

    def test_mi_never_asks_for_patient_details(self):
        """A medical-information call is a question, not a patient case."""
        script = call_intake.question_script("mi", "en", fields={})
        self.assertNotIn("patient", call_intake.INTENT_REQUIRED_ELEMENTS["mi"])
        self.assertEqual(
            [
                call_intake.QUESTION_BANK[("mi", element, "en")]
                for element in call_intake.INTENT_REQUIRED_ELEMENTS["mi"]
            ],
            script,
        )
        self.assertIn(call_intake.QUESTION_BANK[("mi", "event", "en")], script)

    def test_intent_none_asks_nothing(self):
        self.assertEqual([], call_intake.question_script("none", "hi"))

    def test_every_language_has_a_question_for_every_element(self):
        for language in pv.PV_LANGUAGES:
            for intent, elements in call_intake.INTENT_REQUIRED_ELEMENTS.items():
                for element in elements:
                    with self.subTest(lang=language, intent=intent, element=element):
                        self.assertTrue(
                            call_intake.QUESTION_BANK[(intent, element, language)].strip()
                        )

    def test_unknown_language_falls_back_to_english(self):
        script = call_intake.question_script("ae", "zz", fields={})
        self.assertEqual(call_intake.question_script("ae", "en", fields={}), script)

    def test_non_english_scripts_are_not_english(self):
        for language in ("hi", "ta", "te", "bn"):
            with self.subTest(lang=language):
                script = call_intake.question_script("ae", language, fields={})
                self.assertEqual(4, len(script))
                self.assertTrue(any(any(ord(ch) > 0x900 for ch in line) for line in script))

    def test_questions_ask_and_never_assess(self):
        """A prompt that diagnoses or advises would break the collector rule."""
        banned = ("diagnos", "you should take", "we recommend", "i advise", "it is safe to")
        for (intent, element, language), question in call_intake.QUESTION_BANK.items():
            with self.subTest(intent=intent, element=element, lang=language):
                self.assertIn("?", question, "a follow-up has to be a question")
                low = question.lower()
                for phrase in banned:
                    self.assertNotIn(phrase, low, f"{intent}/{element}/{language}")


# ─── E. special_situation_flags — 6 reportable situations ───────────────────

SPECIAL_VECTORS = (
    ("pregnancy", "en", "she took the tablet and later found out she is pregnant"),
    ("pregnancy", "hi", "वह गर्भवती हैं और यह दवा ले रही हैं"),
    ("pregnancy", "bn", "সে গর্ভবতী এবং ওষুধটি খেয়েছেন"),
    ("overdose", "en", "she took too many tablets of the syrup"),
    ("overdose", "ta", "நான் அதிகமாக மாத்திரை எடுத்தேன்"),
    ("medication_error", "en", "I took the wrong tablet by mistake"),
    ("medication_error", "te", "తప్పు మందు తీసుకున్నాను"),
    ("off_label", "bn", "প্রেসক্রিপশন ছাড়া ওষুধ খেয়েছি"),
    ("off_label", "hi", "बिना डॉक्टर की सलाह के दवा ली"),
    ("no_effect", "en", "the medicine is not working at all"),
    ("no_effect", "ta", "மருந்து வேலை செய்யவில்லை"),
    ("death", "en", "my father died after the injection"),
    ("death", "hi", "उसकी मृत्यु हो गई"),
    ("death", "te", "ఆమే గుర్తు చనిపోయారు"),
)

NO_SPECIAL = "I ate a sandwich for breakfast and the office meeting is at three."


class TestSpecialSituationFlags(unittest.TestCase):
    def test_each_situation_is_detected(self):
        for flag, language, text in SPECIAL_VECTORS:
            with self.subTest(flag=flag, lang=language):
                flags = call_intake.special_situation_flags({}, text, language)
                self.assertIn(flag, flags)

    def test_plain_transcript_has_no_flags(self):
        self.assertEqual([], call_intake.special_situation_flags({}, NO_SPECIAL, "en"))
        self.assertEqual([], call_intake.special_situation_flags({}, "", "hi"))

    def test_flags_come_back_in_canonical_order(self):
        flags = call_intake.special_situation_flags(
            {}, "she is pregnant, took too many tablets, and the doctor said it caused it", "en"
        )
        self.assertIn("pregnancy", flags)
        self.assertIn("overdose", flags)
        self.assertEqual(sorted(flags, key=call_intake.SPECIAL_SITUATION_FLAGS.index), flags)

    def test_death_from_a_captured_outcome(self):
        fields = {"outcome": "fatal"}
        self.assertEqual(["death"], call_intake.special_situation_flags(fields, "", "en"))

    def test_flags_are_closed_vocabulary_tokens(self):
        for flag, language, text in SPECIAL_VECTORS:
            with self.subTest(flag=flag):
                for token in call_intake.special_situation_flags({}, text, language):
                    self.assertIn(token, call_intake.SPECIAL_SITUATION_FLAGS)

    def test_multiple_situations_in_one_sentence(self):
        flags = call_intake.special_situation_flags(
            {}, "she took too many tablets by mistake and now she has died", "en"
        )
        self.assertEqual(["overdose", "medication_error", "death"], flags)

    def test_every_flag_has_a_prompt_in_every_language(self):
        for flag in call_intake.SPECIAL_SITUATION_FLAGS:
            for language in pv.PV_LANGUAGES:
                with self.subTest(flag=flag, lang=language):
                    self.assertTrue(
                        call_intake.SPECIAL_SITUATION_PROMPTS[(flag, language)].strip()
                    )
        for language in pv.PV_LANGUAGES:
            self.assertEqual([], call_intake.special_situation_prompts([], language))

    def test_prompts_are_questions_and_never_advice(self):
        banned = ("you should take", "stop the medicine", "we recommend", "diagnos")
        for (flag, language), prompt in call_intake.SPECIAL_SITUATION_PROMPTS.items():
            with self.subTest(flag=flag, lang=language):
                self.assertIn("?", prompt)
                for phrase in banned:
                    self.assertNotIn(phrase, prompt.lower())


# ─── F. build_case_payload — the exact POST /api/pv/cases body ──────────────

SCHEMA_FIELDS = pydantic_fields(read(PV_ROUTER), "PvCaseCreate")


class TestBuildCasePayload(unittest.TestCase):
    def _payload(self, language="en", transcript=EN_SERIOUS, intent="ae", **metadata):
        fields = call_intake.extract_case_fields(transcript, intent, language, today=TODAY)
        flags = call_intake.special_situation_flags(fields, transcript, language)
        meta = {"clinic_id": "c1", "call_id": "call-1", "language": language}
        meta.update(metadata)
        return call_intake.build_case_payload(intent, fields, flags, metadata=meta), fields, flags

    def test_schema_fields_were_actually_read(self):
        self.assertIn("clinic_id", SCHEMA_FIELDS, "PvCaseCreate not found in app/api/pv.py")
        self.assertIn("seriousness_flags", SCHEMA_FIELDS)

    def test_payload_keys_match_the_intake_schema_one_to_one(self):
        payload, _fields, _flags = self._payload()
        self.assertEqual(SCHEMA_FIELDS, set(payload), "payload is not the endpoint body")
        self.assertEqual(len(SCHEMA_FIELDS), len(payload), "no extra / no missing keys")

    def test_extracted_field_set_is_the_schema_set(self):
        fields = call_intake.extract_case_fields(EN_SERIOUS, "ae", "en", today=TODAY)
        self.assertEqual(SCHEMA_FIELDS, set(fields))

    def test_complete_payload_passes_minimum_criteria(self):
        payload, _fields, _flags = self._payload(phone_suffix="1234")
        met, missing = call_intake.intake_minimum_criteria(payload)
        self.assertEqual([], missing)
        self.assertTrue(met)

    def test_incomplete_payload_reports_the_missing_elements(self):
        payload = call_intake.build_case_payload(
            "ae",
            call_intake.extract_case_fields("I feel unwell", "ae", "en", today=TODAY),
            [],
            metadata={"clinic_id": "c1", "language": "en"},
        )
        met, missing = call_intake.intake_minimum_criteria(payload)
        self.assertFalse(met)
        self.assertEqual(["reporter", "patient", "product"], missing)

    def test_intake_contract_matches_the_endpoint_call(self):
        """Mirror of api/pv.py: text = first non-blank of the three columns."""
        for transcript, intent, language in (
            (HI_AE, "ae", "hi"),
            (TE_PQC, "pqc", "te"),
            (BN_MI, "mi", "bn"),
        ):
            with self.subTest(lang=language):
                payload, _f, _fl = self._payload(language, transcript, intent)
                text = ""
                for field in ("event_text", "question_text", "defect_description"):
                    if payload.get(field):
                        text = payload[field]
                        break
                self.assertEqual(
                    pv.validate_minimum_criteria(
                        payload["event_text"] or text,
                        payload["reporter_contact"] or payload["reporter_type"],
                        payload["patient"],
                        payload["product_name"] or payload["product_id"],
                    ),
                    call_intake.intake_minimum_criteria(payload),
                )

    def test_seriousness_flags_are_the_e2a_overlap_only(self):
        """A pregnancy flag is reportable, but it is not an ICH E2A criterion."""
        payload, _fields, _flags = self._payload()
        self.assertEqual(["death"], payload["seriousness_flags"])
        is_serious, criteria = pv.classify_seriousness(payload["seriousness_flags"])
        self.assertTrue(is_serious)
        self.assertEqual(["death"], criteria)

    def test_non_e2a_special_situations_do_not_inflate_seriousness(self):
        fields = call_intake.extract_case_fields(TA_AE, "ae", "ta", today=TODAY)
        flags = call_intake.special_situation_flags(fields, TA_AE, "ta")
        self.assertEqual(["overdose", "medication_error"], flags)
        payload = call_intake.build_case_payload(
            "ae", fields, flags, metadata={"clinic_id": "c1", "language": "ta"}
        )
        self.assertEqual([], payload["seriousness_flags"])
        self.assertFalse(pv.classify_seriousness(payload["seriousness_flags"])[0])

    def test_each_intent_fills_its_own_text_column(self):
        for transcript, intent, column, language in (
            (HI_AE, "ae", "event_text", "hi"),
            (TE_PQC, "pqc", "defect_description", "te"),
            (BN_MI, "mi", "question_text", "bn"),
        ):
            with self.subTest(intent=intent):
                payload, _f, _fl = self._payload(language, transcript, intent)
                self.assertEqual(transcript.strip(), payload[column])
                others = {"event_text", "question_text", "defect_description"} - {column}
                for other in others:
                    self.assertEqual("", payload[other], f"{intent} must not fill {other}")

    def test_voice_metadata(self):
        payload, _f, _fl = self._payload(phone_suffix="4321", call_id="call-9")
        self.assertEqual("c1", payload["clinic_id"])
        self.assertEqual("call-9", payload["call_id"])
        self.assertEqual("en", payload["language"])
        self.assertEqual({"phone_suffix": "4321"}, payload["reporter_contact"])
        self.assertEqual([], payload["photos_url"], "a phone call carries no photos")

    def test_payload_is_pure_and_deterministic(self):
        first, _f, _fl = self._payload()
        second, _f2, _fl2 = self._payload()
        self.assertEqual(first, second)

    def test_builder_reports_no_completeness_claim(self):
        """The builder must not pre-judge validity — the endpoint does that."""
        payload, _f, _fl = self._payload()
        self.assertNotIn("e2b_minimum_met", payload)
        self.assertNotIn("is_serious", payload)
        self.assertNotIn("notification_deadline", payload)

    def test_intake_path_is_the_router_endpoint(self):
        prefix = router_prefix(read(PV_ROUTER))
        self.assertIn(("post", "/cases"), router_paths(read(PV_ROUTER)))
        self.assertEqual(
            f"{prefix}/cases", call_intake.PV_INTAKE_PATH, "path drifted from the router"
        )

    def test_builder_does_not_dial_the_endpoint(self):
        src = read(CALL_INTAKE_PY).lower()
        for needle in ("urllib", "requests", "httpx", "socket", "urlopen", "post("):
            self.assertNotIn(needle, src, f"builder must stay pure ({needle})")


# ─── G. agent_logic wiring + the livekit hangup seam ────────────────────────


class TestAgentLogicWiring(unittest.TestCase):
    def test_handler_runs_the_whole_pipeline(self):
        result = agent_logic.run_pv_intake(
            EN_SERIOUS, language="en", clinic_id="c1", call_id="call-1", phone_suffix="7788"
        )
        self.assertEqual("ae", result["intent"])
        self.assertEqual(SCHEMA_FIELDS, set(result["payload"]))
        self.assertTrue(result["should_submit"])
        met, missing = result["e2b_minimum_met"], result["missing"]
        self.assertTrue(met, missing)
        self.assertEqual([], missing)
        self.assertEqual(["death"], result["seriousness_criteria"])
        self.assertTrue(result["is_serious"])

    def test_handler_returns_the_in_call_prompts(self):
        # HI_AE is a COMPLETE case, so it must be asked nothing; a partial one
        # is what produces a script.
        result = agent_logic.run_pv_intake(HI_PARTIAL, language="hi", clinic_id="c1")
        self.assertIsInstance(result["script"], list)
        self.assertTrue(result["script"], "a partial case must get follow-up questions")
        self.assertEqual(
            len(result["script"]) + len(result["special_prompts"]), len(result["prompts"])
        )
        self.assertEqual(result["prompts"], result["script"] + result["special_prompts"])

    def test_complete_case_asks_nothing_through_the_handler(self):
        result = agent_logic.run_pv_intake(HI_AE, language="hi", clinic_id="c1")
        self.assertEqual([], result["script"])
        self.assertEqual([], result["missing"])

    def test_handler_prompts_for_special_situations(self):
        result = agent_logic.run_pv_intake(TA_AE, language="ta", clinic_id="c1")
        self.assertEqual(["overdose", "medication_error"], result["special_situations"])
        self.assertEqual(2, len(result["special_prompts"]))
        self.assertEqual(
            [call_intake.SPECIAL_SITUATION_PROMPTS[(flag, "ta")] for flag in result["special_situations"]],
            result["special_prompts"],
        )

    def test_handler_asks_exactly_what_is_missing(self):
        result = agent_logic.run_pv_intake(
            "the strip arrived broken and the tablets are loose", language="en", clinic_id="c1"
        )
        self.assertEqual("pqc", result["intent"])
        # `missing` is the endpoint's E2B report (it includes `patient`, which a
        # complaint has no element for); the script covers only the complaint's
        # own elements, plus the batch number the E2B four do not list.
        pending = [
            element
            for element in call_intake.INTENT_REQUIRED_ELEMENTS["pqc"]
            if element in set(result["missing"])
            or element in call_intake.EXTRA_REQUIRED_ELEMENTS["pqc"]
        ]
        self.assertEqual(
            [call_intake.QUESTION_BANK[("pqc", element, "en")] for element in pending],
            result["script"],
        )
        self.assertIn(call_intake.QUESTION_BANK[("pqc", "batch", "en")], result["script"])
        self.assertIn("patient", result["missing"], "reported, but never asked of a complaint")

    def test_non_pv_call_submits_nothing(self):
        result = agent_logic.run_pv_intake(EN_NONE, language="en", clinic_id="c1")
        self.assertEqual("none", result["intent"])
        self.assertFalse(result["should_submit"])
        self.assertIsNone(result["payload"])
        self.assertEqual([], result["script"])
        self.assertEqual([], result["special_prompts"])

    def test_handler_is_deterministic(self):
        args = (EN_SERIOUS,)
        first = agent_logic.run_pv_intake(*args, language="en", clinic_id="c1")
        second = agent_logic.run_pv_intake(*args, language="en", clinic_id="c1")
        self.assertEqual(first, second)

    def test_handler_reports_the_llm_function_for_the_intent(self):
        self.assertEqual(
            call_intake.detect_intent(HI_AE, "hi")["function"],
            agent_logic.run_pv_intake(HI_AE, language="hi", clinic_id="c1")["function"],
        )

    def test_caller_speech_joins_only_the_caller(self):
        transcript = [
            {"role": "caller", "text": "fever after the tablet", "language": "en"},
            {"role": "system", "text": "escalated", "language": "en"},
            {"role": "caller", "text": "it started yesterday", "language": "en"},
        ]
        self.assertEqual(
            "fever after the tablet\nit started yesterday", agent_logic.caller_speech(transcript)
        )
        self.assertEqual("", agent_logic.caller_speech([]))
        self.assertEqual("", agent_logic.caller_speech(None))

    def test_handler_never_touches_the_network(self):
        """Import roots, not substrings.

        `agent_logic.system_prompt` legitimately contains the words "prescription
        refill requests" - a substring scan would flag the collector for its own
        prompt text. What actually matters is whether the module IMPORTS a
        network client, so that is what is asserted.
        """
        roots = module_import_roots(read(AGENT_LOGIC_PY))
        self.assertEqual(
            set(), roots & FORBIDDEN_ROOTS, f"collector must not reach out: {sorted(roots)}"
        )

    def test_livekit_agent_parses(self):
        self.assertIsNotNone(py_tree_text(read(AGENT_PY)), "livekit_agent.py must parse")

    def test_livekit_hangup_seam_delegates_to_agent_logic(self):
        src = read(AGENT_PY)
        self.assertIn("run_pv_intake", src)
        self.assertIn("agent_logic", src)
        roots = module_import_roots(src)
        self.assertEqual(
            set(), roots & FORBIDDEN_ROOTS, "no network client from the agent worker"
        )

    def test_livekit_agent_keeps_its_top_level_livekit_import(self):
        """The worker still needs livekit; the tests just must not import it."""
        tree = py_tree_text(read(AGENT_PY))
        roots = module_import_roots(read(AGENT_PY))
        self.assertIn("livekit", roots)
        self.assertIsNotNone(tree)


if __name__ == "__main__":
    unittest.main()
