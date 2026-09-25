"""G6-Q4 languages RED contract: language layer hardening.

Contract (sign-off 2026-09-25, Q1=A1 Q2=A1 Q3=A1 Q4=A1):
- Q1=A1: confidence-low STT fallback chain — resolve_stt_language(language,
  confidence, threshold, fallback="en"): confirmed (>= threshold) or None
  confidence keeps the call language; low confidence (< threshold) falls the
  operative language to English. STT_CONFIDENCE_THRESHOLD env (default 0.6);
  stt.py gains additive stt_stream_with_scores (yields transcript+confidence+
  language); the G4 stt_stream (yields str) is untouched.
- Q2=A1: new stdlib app/services/languages.py is the single source for
  SUPPORTED_LANGUAGES / STT_TAGS / IVR_DIGIT_LANGUAGES / TTS_VOICE_ENV_KEYS /
  LANGUAGE_FALLBACK_CHAIN + is_supported_language() + resolve_stt_language();
  agent_logic re-imports+re-exports the G4-pinned helpers unchanged;
  postgres.py + services/notifications.py import the tuple from there.
- Q3=A1: GREETING_TEMPLATES (5 langs) + greeting_for_language() in
  agent_logic; livekit_agent greeting wired to it; unknown code -> EN template.
- Q4=A1: canonical voice env keys ELEVENLABS_VOICE_ID_{CODE} for all 5;
  .env.example corrected from the _HINDI/_TAMIL/... names; catalog + coverage
  test (all 5 keys in the map AND documented in .env.example).
"""

import ast
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
TESTS = BACKEND / "tests"
APP = BACKEND / "app"
ENV_EXAMPLE = BACKEND / ".env.example"

SUPPORTED_LANGUAGES = ("hi", "en", "ta", "te", "bn")
STT_TAGS_EXPECTED = {"hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN"}
IVR_EXPECTED = {"1": "hi", "2": "en", "3": "ta", "4": "te", "5": "bn"}
LEGACY_VOICE_NAMES = (
    "ELEVENLABS_VOICE_ID_HINDI",
    "ELEVENLABS_VOICE_ID_TAMIL",
    "ELEVENLABS_VOICE_ID_TELUGU",
    "ELEVENLABS_VOICE_ID_BENGALI",
    "ELEVENLABS_VOICE_ID_ENGLISH",
)
THIRD_PARTY_MODULES = {"httpx", "requests", "websockets", "livekit", "sqlalchemy", "fastapi", "pydantic", "openai"}

try:
    from app.services import languages as langs  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    langs = None


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

    Slices by LINE, not by character offset: splitlines(keepends=True) keeps
    each line intact so text[node.lineno-1:node.end_lineno] spans the def line
    down to the function's last line (same helper as test_auth_enforcement).
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(("import", alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(("from", node.module.split(".")[0]))
    return out


def catalog_keys(lang_mod, codes=SUPPORTED_LANGUAGES) -> set:
    """TTS voice env keys derived the way the catalog must derive them."""
    return {f"ELEVENLABS_VOICE_ID_{code.upper()}" for code in codes}


class TestLanguagesModuleStructure(unittest.TestCase):
    """languages.py: the single-source catalog module (Q2=A1)."""

    def test_module_exists(self):
        self.assertIsNotNone(langs, "app/services/languages.py missing (RED)")

    def test_module_parses(self):
        self.assertIsNotNone(py_tree(APP / "services" / "languages.py"))

    def test_docstring_marks_phase(self):
        self.assertIn("G6-Q4", read(APP / "services" / "languages.py")[:600])

    def test_no_third_party_imports_at_module_level(self):
        tree = py_tree(APP / "services" / "languages.py")
        self.assertIsNotNone(tree)
        for kind, name in imports_at_module_level(tree):
            self.assertNotIn(name, THIRD_PARTY_MODULES, f"{kind} {name} must not load a third-party module")

    def test_supported_languages_exact_5(self):
        self.assertEqual(langs.SUPPORTED_LANGUAGES, SUPPORTED_LANGUAGES)

    def test_stt_tags_all_5(self):
        self.assertEqual(dict(langs.STT_TAGS), STT_TAGS_EXPECTED)

    def test_ivr_digit_languages(self):
        self.assertEqual(dict(langs.IVR_DIGIT_LANGUAGES), IVR_EXPECTED)

    def test_tts_voice_env_keys_catalog(self):
        self.assertEqual(set(langs.TTS_VOICE_ENV_KEYS.values()), catalog_keys(langs))

    def test_tts_voice_env_keys_keyed_by_language(self):
        for code in SUPPORTED_LANGUAGES:
            self.assertEqual(
                langs.TTS_VOICE_ENV_KEYS[code],
                f"ELEVENLABS_VOICE_ID_{code.upper()}",
                f"{code} must map to ELEVENLABS_VOICE_ID_{code.upper()}",
            )

    def test_language_fallback_chain(self):
        self.assertIsInstance(langs.LANGUAGE_FALLBACK_CHAIN, tuple)
        self.assertIn("en", langs.LANGUAGE_FALLBACK_CHAIN)
        self.assertEqual(langs.LANGUAGE_FALLBACK_CHAIN[-1], "en")

    def test_confidence_threshold_constant(self):
        self.assertAlmostEqual(langs.STT_CONFIDENCE_THRESHOLD, 0.6, places=6)


class TestIsSupportedLanguage(unittest.TestCase):
    def test_all_5_supported(self):
        for code in SUPPORTED_LANGUAGES:
            self.assertTrue(langs.is_supported_language(code), f"{code} must be supported")

    def test_unknown_codes_rejected(self):
        for bad in ("xx", "hindi", "en-IN", "", "HI", None):
            self.assertFalse(langs.is_supported_language(bad), f"{bad!r} must not be supported")


class TestResolveSttLanguage(unittest.TestCase):
    """Q1=A1: confidence-low fallback chain (pure stdlib logic)."""

    def test_high_confidence_keeps_language(self):
        self.assertEqual(langs.resolve_stt_language("hi", 0.9), "hi")

    def test_none_confidence_keeps_language(self):
        self.assertEqual(langs.resolve_stt_language("ta", None), "ta")

    def test_low_confidence_falls_back_to_en(self):
        self.assertEqual(langs.resolve_stt_language("bn", 0.3), "en")

    def test_at_threshold_keeps_language(self):
        self.assertEqual(langs.resolve_stt_language("te", 0.6), "te")

    def test_just_below_threshold_falls_back(self):
        self.assertEqual(langs.resolve_stt_language("hi", 0.59), "en")

    def test_custom_threshold_param(self):
        self.assertEqual(langs.resolve_stt_language("hi", 0.7, threshold=0.8), "en")
        self.assertEqual(langs.resolve_stt_language("hi", 0.9, threshold=0.8), "hi")

    def test_env_threshold_override(self):
        env = {"STT_CONFIDENCE_THRESHOLD": "0.9"}
        self.assertEqual(langs.resolve_stt_language("hi", 0.8, env=env), "en")
        self.assertEqual(langs.resolve_stt_language("hi", 0.95, env=env), "hi")

    def test_custom_fallback_param(self):
        self.assertEqual(langs.resolve_stt_language("hi", 0.1, fallback="bn"), "bn")

    def test_no_env_var_uses_constant(self):
        self.assertEqual(langs.resolve_stt_language("hi", 0.6, env={}), "hi")
        self.assertEqual(langs.resolve_stt_language("hi", 0.59, env={}), "en")


class TestAgentLogicSingleSource(unittest.TestCase):
    """Q2=A1: agent_logic re-imports + re-exports the catalog; G4 pins hold."""

    @classmethod
    def setUpClass(cls):
        import app.services.agent_logic as al
        cls.al = al

    def test_imports_catalog_constants(self):
        tree = py_tree(APP / "services" / "agent_logic.py")
        names = module_imported_names(tree, "app.services.languages")
        self.assertTrue({"SUPPORTED_LANGUAGES", "STT_TAGS", "IVR_DIGIT_LANGUAGES"} <= names)

    def test_no_own_tuple_assignment(self):
        self.assertNotIn('SUPPORTED_LANGUAGES = ("hi"', read(APP / "services" / "agent_logic.py"))

    def test_reexports_same_tuple_object(self):
        self.assertIs(self.al.SUPPORTED_LANGUAGES, langs.SUPPORTED_LANGUAGES)

    def test_stt_language_tag_pins(self):
        self.assertEqual(self.al.stt_language_tag("hi"), "hi-IN")
        self.assertEqual(self.al.stt_language_tag("ta"), "ta-IN")
        self.assertEqual(self.al.stt_language_tag("xx"), "en-IN")

    def test_tts_voice_id_pins(self):
        env = {"ELEVENLABS_VOICE_ID_HI": "v_hi", "ELEVENLABS_VOICE_ID": "v_plain"}
        self.assertEqual(self.al.tts_voice_id("hi", env, "v_default"), "v_hi")
        self.assertEqual(self.al.tts_voice_id("ta", env, "v_default"), "v_plain")
        self.assertEqual(self.al.tts_voice_id("ta", {"X": "1"}, "v_default"), "v_default")

    def test_language_for_room_pins(self):
        self.assertEqual(self.al.language_for_room({"language": "te"}, "hi"), "te")
        self.assertEqual(self.al.language_for_room({"ivr_digit": "1"}, "hi"), "hi")
        self.assertEqual(self.al.language_for_room({"ivr_digit": "7"}, "hi"), "hi")
        self.assertEqual(self.al.language_for_room({}, "en"), "en")
        self.assertEqual(self.al.language_for_room(None, "hi"), "hi")


class TestGreeting(unittest.TestCase):
    """Q3=A1: 5-language greeting templates + fallback."""

    @classmethod
    def setUpClass(cls):
        import app.services.agent_logic as al
        cls.al = al

    EN_VECTOR = "Namaste, welcome to MediCall Health."

    def test_greeting_templates_cover_5_langs(self):
        self.assertEqual(set(self.al.GREETING_TEMPLATES), set(SUPPORTED_LANGUAGES))

    def test_greeting_en_fixed_vector(self):
        self.assertEqual(self.al.greeting_for_language("en", "MediCall Health"), self.EN_VECTOR)

    def test_greeting_hi_localized_and_distinct(self):
        hi = self.al.greeting_for_language("hi", "MediCall Health")
        self.assertTrue(hi.strip())
        self.assertIn("MediCall Health", hi)
        self.assertNotEqual(hi, self.EN_VECTOR)

    def test_all_greetings_contain_clinic(self):
        for code in SUPPORTED_LANGUAGES:
            out = self.al.greeting_for_language(code, "Sunrise Clinic")
            self.assertIn("Sunrise Clinic", out, f"{code} greeting must embed the clinic name")

    def test_greeting_unknown_falls_back_en(self):
        self.assertEqual(self.al.greeting_for_language("xx", "MediCall Health"), self.EN_VECTOR)
        self.assertEqual(self.al.greeting_for_language(None, "MediCall Health"), self.EN_VECTOR)

    def test_livekit_greeting_wired(self):
        self.assertIn("greeting_for_language", read(APP / "services" / "livekit_agent.py"))

    def test_livekit_no_hardcoded_greeting(self):
        self.assertNotIn("Namaste, welcome to {clinic_name}", read(APP / "services" / "livekit_agent.py"))


class TestSttSeam(unittest.TestCase):
    """Q1=A1: stt.py gains scores; G4 pins hold; stt_stream kept."""

    def test_stt_parses(self):
        self.assertIsNotNone(py_tree(APP / "services" / "stt.py"))

    def test_stt_pins_preserved(self):
        src = read(APP / "services" / "stt.py")
        self.assertIn("language", src)
        self.assertIn("stt_language_tag", src)
        self.assertNotIn("en-AU", src)

    def test_stt_imports_resolve(self):
        tree = py_tree(APP / "services" / "stt.py")
        self.assertIn("resolve_stt_language", module_imported_names(tree, "app.services.languages"))

    def test_stt_reads_threshold_env(self):
        self.assertIn("STT_CONFIDENCE_THRESHOLD", read(APP / "services" / "stt.py"))

    def test_stt_stream_with_scores_exists(self):
        self.assertTrue(fn_block(read(APP / "services" / "stt.py"), "stt_stream_with_scores"))

    def test_stt_stream_with_scores_uses_resolve(self):
        self.assertIn("resolve_stt_language", fn_block(read(APP / "services" / "stt.py"), "stt_stream_with_scores"))

    def test_stt_stream_preserved(self):
        self.assertTrue(fn_block(read(APP / "services" / "stt.py"), "stt_stream"))


class TestTtsEnvKeys(unittest.TestCase):
    """Q4=A1: canonical ELEVENLABS_VOICE_ID_{CODE} keys; G4 pins hold."""

    def test_tts_parses(self):
        self.assertIsNotNone(py_tree(APP / "services" / "tts.py"))

    def test_tts_pins_preserved(self):
        src = read(APP / "services" / "tts.py")
        self.assertIn("voice_for_language", src)
        self.assertIn("ELEVENLABS_VOICE_ID_", src)

    def test_tts_keyed_off_catalog(self):
        tree = py_tree(APP / "services" / "tts.py")
        self.assertIn("TTS_VOICE_ENV_KEYS", module_imported_names(tree, "app.services.languages"))
        self.assertIn("TTS_VOICE_ENV_KEYS", fn_block(read(APP / "services" / "tts.py"), "voice_for_language"))

    def test_env_example_has_all_5_keys(self):
        text = read(ENV_EXAMPLE)
        for key in sorted(catalog_keys(langs)):
            self.assertIn(key, text, f"{key} must be documented in .env.example")

    def test_env_example_no_legacy_voice_names(self):
        text = read(ENV_EXAMPLE)
        for legacy in LEGACY_VOICE_NAMES:
            self.assertNotIn(legacy, text, f"{legacy} must be replaced by the {legacy[-2:]} form")

    def test_env_example_threshold_documented(self):
        self.assertIn("STT_CONFIDENCE_THRESHOLD", read(ENV_EXAMPLE))


class TestDedupe(unittest.TestCase):
    """Q2=A1: postgres + notifications import the tuple from languages."""

    def test_postgres_imports_catalog(self):
        tree = py_tree(APP / "db" / "postgres.py")
        self.assertIn("SUPPORTED_LANGUAGES", module_imported_names(tree, "app.services.languages"))

    def test_postgres_no_own_tuple(self):
        self.assertNotIn('SUPPORTED_LANGUAGES = ("hi"', read(APP / "db" / "postgres.py"))

    def test_notifications_service_reuses_tuple(self):
        import app.services.notifications as ntf
        self.assertEqual(ntf.SUPPORTED_LANGUAGES, SUPPORTED_LANGUAGES)
        self.assertIs(ntf.SUPPORTED_LANGUAGES, langs.SUPPORTED_LANGUAGES)

    def test_notifications_service_no_own_tuple(self):
        self.assertNotIn('SUPPORTED_LANGUAGES = ("hi"', read(APP / "services" / "notifications.py"))

    def test_notifications_api_import_chain_survives(self):
        tree = py_tree(APP / "api" / "notifications.py")
        self.assertIn("SUPPORTED_LANGUAGES", module_imported_names(tree, "app.services.notifications"))


class TestSmokeRefs(unittest.TestCase):
    """The Q4 suite itself carries the canonical tuples (self-contained)."""

    def test_suite_self_consistent(self):
        self.assertEqual(len(SUPPORTED_LANGUAGES), 5)
        self.assertEqual(set(STT_TAGS_EXPECTED), set(SUPPORTED_LANGUAGES))
        self.assertEqual(set(langs.TTS_VOICE_ENV_KEYS), set(SUPPORTED_LANGUAGES) if langs else set())

    def test_uml_caller_language_spot_column_untouched(self):
        # Presence-only: the calls ER spot columns still list caller_language.
        self.assertIn("caller_language", read(TESTS / "test_uml_diagrams.py"))


if __name__ == "__main__":
    unittest.main(verbosity=2)