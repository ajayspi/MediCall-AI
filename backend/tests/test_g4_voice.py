"""G4 acceptance tests: medical voice pipeline (stdlib only).

RED before fix (2026-09-24): voice.py is Telnyx-US (`call_control_id`,
`restaurant_id`, /stt stub); livekit_agent.py is restaurant flow ("Mama's
Pizzeria", order_items, TAKING_ORDER, rag_menu); llm.py prompt + FUNCTIONS are
restaurant; stt.py hardcodes en-AU; tts.py has no per-language voice map;
postgres.py has no update_call_transcript; services/telephony.py and
services/agent_logic.py do not exist.

GREEN after fix: Exotel/Knowlarity/Twilio-India webhooks -> normalized
ProviderEvent -> LiveKit room; medical agent on the G3 state machine;
5-language STT/TTS (hi/en/ta/te/bn); transcript persistence path (D1);
escalation MVP (D2); default language hi (D3).

Run: python3 tests/test_g4_voice.py  (exit 0 = green)
"""
import ast
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

VOICE_PY = BACKEND / "app" / "api" / "voice.py"
AGENT_PY = BACKEND / "app" / "services" / "livekit_agent.py"
LLM_PY = BACKEND / "app" / "services" / "llm.py"
STT_PY = BACKEND / "app" / "services" / "stt.py"
TTS_PY = BACKEND / "app" / "services" / "tts.py"
POSTGRES_PY = BACKEND / "app" / "db" / "postgres.py"
TELEPHONY_PY = BACKEND / "app" / "services" / "telephony.py"
AGENT_LOGIC_PY = BACKEND / "app" / "services" / "agent_logic.py"

TELNYX_LEFTOVERS = (
    "telnyx",
    "call_control_id",
    "restaurant_id",
    "finalize order",
)
RESTAURANT_LEFTOVERS = (
    "Mama's Pizzeria",
    "order_items",
    "rag_menu",
    "TAKING_ORDER",
)
MEDICAL_FUNCTIONS = (
    "set_triage_severity",
    "book_appointment",
    "prescription_refill",
    "escalate",
    "end_call",
)


def parse_source(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


# Behavioral suites import the stdlib-only modules normally (single module
# instance so enum identity holds across agent_logic <-> models.call).
import app.models.call as calls_mod  # noqa: E402
import app.services.telephony as telephony_mod  # noqa: E402
import app.services.agent_logic as agent_logic_mod  # noqa: E402


class TestVoiceApiSource(unittest.TestCase):
    """voice.py: no Telnyx-US/restaurant leftovers; 3 provider routes present."""

    def test_voice_parses(self):
        parse_source(VOICE_PY)

    def test_no_telnyx_or_restaurant_leftovers(self):
        src = VOICE_PY.read_text(encoding="utf-8").lower()
        for leftover in (*TELNYX_LEFTOVERS, "restaurant", "pizzeria"):
            self.assertNotIn(leftover, src, f"voice.py leftover: {leftover}")

    def test_provider_routes_present(self):
        src = VOICE_PY.read_text(encoding="utf-8")
        for route in (
            "/webhook/exotel",
            "/webhook/knowlarity",
            "/webhook/twilio",
            "/livekit-agent-start",
            "/call-completed",
        ):
            self.assertIn(route, src, f"missing route {route}")

    def test_no_dead_stt_stub(self):
        self.assertNotIn("/stt", VOICE_PY.read_text(encoding="utf-8"))

    def test_livekit_start_uses_clinic_id(self):
        src = VOICE_PY.read_text(encoding="utf-8")
        self.assertIn("clinic_id", src)
        self.assertIn("caller_number", src)
        self.assertIn("language", src)


class TestAgentSource(unittest.TestCase):
    """livekit_agent.py: medical glue, no restaurant flavor."""

    def test_agent_parses(self):
        parse_source(AGENT_PY)

    def test_no_restaurant_leftovers(self):
        src = AGENT_PY.read_text(encoding="utf-8")
        for leftover in (*RESTAURANT_LEFTOVERS, "restaurant"):
            self.assertNotIn(leftover, src, f"agent leftover: {leftover}")

    def test_uses_agent_logic_and_state_machine(self):
        src = AGENT_PY.read_text(encoding="utf-8")
        self.assertIn("agent_logic", src)
        self.assertIn("CallState", src)
        self.assertIn("MEDICAL_FUNCTIONS", src)

    def test_escalation_message_present(self):
        self.assertIn("specialist", AGENT_PY.read_text(encoding="utf-8").lower())


class TestLlmMedical(unittest.TestCase):
    """llm.py: medical prompt + medical function schema."""

    def test_llm_parses(self):
        parse_source(LLM_PY)

    def test_no_restaurant_prompt(self):
        src = LLM_PY.read_text(encoding="utf-8")
        for leftover in ("{restaurant_name}", "restaurant", "order", "menu"):
            self.assertNotIn(leftover, src.lower(), f"llm leftover: {leftover}")

    def test_medical_functions_from_agent_logic(self):
        # Single source of truth: llm.py consumes agent_logic.MEDICAL_FUNCTIONS;
        # the 5 names themselves are asserted behaviorally on agent_logic.
        self.assertIn("MEDICAL_FUNCTIONS", LLM_PY.read_text(encoding="utf-8"))

    def test_low_temperature(self):
        self.assertIn("temperature", LLM_PY.read_text(encoding="utf-8"))


class TestSttTtsLanguage(unittest.TestCase):
    """stt/tts: 5-language parameterization, no en-AU hardcode."""

    def test_stt_parses(self):
        parse_source(STT_PY)

    def test_stt_no_en_au(self):
        self.assertNotIn("en-AU", STT_PY.read_text(encoding="utf-8"))

    def test_stt_accepts_language(self):
        src = STT_PY.read_text(encoding="utf-8")
        self.assertIn("language", src)
        self.assertIn("stt_language_tag", src)

    def test_tts_parses(self):
        parse_source(TTS_PY)

    def test_tts_voice_map_by_language(self):
        src = TTS_PY.read_text(encoding="utf-8")
        self.assertIn("voice_for_language", src)
        self.assertIn("ELEVENLABS_VOICE_ID_", src)  # per-language env key builder


class TestPostgresTranscriptHelper(unittest.TestCase):
    """postgres.py: update_call_transcript persists transcript + end metadata."""

    def test_postgres_has_transcript_helper(self):
        src = POSTGRES_PY.read_text(encoding="utf-8")
        self.assertIn("def update_call_transcript", src)

    def test_helper_touches_transcript_and_end_fields(self):
        tree = parse_source(POSTGRES_PY)
        sig = set()
        # async def functions are ast.AsyncFunctionDef — a sibling of
        # FunctionDef, so match both (G3-style source checks never hit this).
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "update_call_transcript":
                sig = {a.arg for a in node.args.args}
                break
        self.assertGreaterEqual(
            sig, {"call_id", "transcript", "ended_at", "duration_seconds"}
        )


class TestTelephonyParsers(unittest.TestCase):
    """Exotel/Knowlarity/Twilio payloads -> normalized ProviderEvent."""

    def test_exotel_ringing_answered_terminal(self):
        t = telephony_mod
        ringing = t.parse_exotel(
            {"CallSid": "SID1", "EventType": "ringing", "From": "+919876543210",
             "To": "+918047111111", "Status": "ringing"}
        )
        self.assertEqual(ringing.provider, "exotel")
        self.assertEqual(ringing.event_type, "call.initiated")
        self.assertEqual(ringing.call_sid, "SID1")
        self.assertEqual(ringing.caller_number, "+919876543210")

        answered = t.parse_exotel(
            {"CallSid": "SID1", "EventType": "answered", "Status": "in-progress"}
        )
        self.assertEqual(answered.event_type, "call.answered")

        done = t.parse_exotel(
            {"CallSid": "SID1", "EventType": "terminal", "Status": "completed",
             "ConversationDuration": 120, "RecordingUrl": "https://rec/x.mp3"}
        )
        self.assertEqual(done.event_type, "call.hangup")
        self.assertEqual(done.duration_seconds, 120)
        self.assertEqual(done.recording_url, "https://rec/x.mp3")

    def test_exotel_dropped_and_ignored(self):
        t = telephony_mod
        missed = t.parse_exotel({"CallSid": "S2", "EventType": "terminal", "Status": "no-answer"})
        self.assertEqual(missed.event_type, "call.dropped")
        unknown = t.parse_exotel({"something": "else", "CallSid": "S3"})
        self.assertEqual(unknown.event_type, "ignored")

    def test_knowlarity_inbound_and_cdr(self):
        t = telephony_mod
        inbound = t.parse_knowlarity(
            {"callid": "a0ea5072-a11e-4a8a-8013-512b57c10de7", "caller_id": "9876543210",
             "dispnumber": "0801234567", "extension": "3", "action": "phone"}
        )
        self.assertEqual(inbound.provider, "knowlarity")
        self.assertEqual(inbound.event_type, "call.initiated")
        self.assertEqual(inbound.language, "ta")
        self.assertEqual(inbound.call_sid, "a0ea5072-a11e-4a8a-8013-512b57c10de7")
        self.assertEqual(inbound.inbound_number, "0801234567")

        cdr = t.parse_knowlarity(
            {"callid": "a0ea5072-a11e-4a8a-8013-512b57c10de7", "caller_id": "9876543210",
             "dispnumber": "0801234567", "action": "phone", "start_time": "2026-09-24 10:00:00",
             "end_time": "2026-09-24 10:02:00", "call_duration": "120", "resource_url": "https://rec/k.mp3"}
        )
        self.assertEqual(cdr.event_type, "call.hangup")
        self.assertEqual(cdr.duration_seconds, 120)

        voicemail = t.parse_knowlarity(
            {"callid": "x", "action": "voicemail", "end_time": "2026-09-24 10:00:00"}
        )
        self.assertEqual(voicemail.event_type, "call.dropped")

    def test_twilio_status_map(self):
        t = telephony_mod
        cases = {
            "ringing": "call.initiated",
            "in-progress": "call.answered",
            "completed": "call.hangup",
            "failed": "call.dropped",
            "no-answer": "call.dropped",
            "canceled": "call.dropped",
        }
        for status, expected in cases.items():
            ev = t.parse_twilio({"CallSid": "CA1", "CallStatus": status, "Digits": "1"})
            self.assertEqual(
                ev.event_type, expected, f"twilio {status} -> {ev.event_type}"
            )
        self.assertEqual(
            t.parse_twilio({"CallSid": "CA1", "CallStatus": "ringing", "Digits": "1"}).language,
            "hi",
        )

    def test_normalize_phone_and_language_digit(self):
        t = telephony_mod
        self.assertEqual(t.normalize_phone("+91 98765 43210"), "+919876543210")
        self.assertEqual(t.normalize_phone(None), "")
        self.assertEqual(t.language_from_digit("2"), "en")
        self.assertEqual(t.language_from_digit("9"), "")
        self.assertEqual(t.language_from_digit(None), "")


class TestAgentLogic(unittest.TestCase):
    """Medical conversation brain: prompt, intents, transcripts, languages."""

    def _call(self, state="TRIAGE"):
        return calls_mod.Call(
            id="c1", clinic_id="k1", caller_number="+919876543210",
            state=calls_mod.CallState(state), caller_language="hi",
        )

    def test_system_prompt_medical(self):
        prompt = agent_logic_mod.system_prompt(
            clinic_name="Apollo Clinic", language="hi",
            date="2026-09-24", time="10:00", state="TRIAGE",
        )
        self.assertIn("Apollo Clinic", prompt)
        self.assertIn("triage", prompt.lower())
        lowered = prompt.lower()
        for word in ("restaurant", "pizzeria", "order"):
            self.assertNotIn(word, lowered)

    def test_medical_functions_schema(self):
        names = {f["name"] for f in agent_logic_mod.MEDICAL_FUNCTIONS}
        self.assertEqual(names, set(MEDICAL_FUNCTIONS))
        sev = next(f for f in agent_logic_mod.MEDICAL_FUNCTIONS if f["name"] == "set_triage_severity")
        props = sev["parameters"]["properties"]["severity"]
        self.assertEqual(set(props["enum"]), {"green", "amber", "red", "critical"})

    def test_apply_intent_transitions(self):
        C = calls_mod.CallState
        al = agent_logic_mod
        call = self._call("TRIAGE")
        ok, new = al.apply_intent(call, "book_appointment", {"patient_name": "Ravi"})
        self.assertTrue(ok)
        self.assertEqual(new, C.APPOINTMENT)
        self.assertEqual(call.state, C.APPOINTMENT)

        call2 = self._call("TRIAGE")
        ok2, _ = al.apply_intent(call2, "escalate", {"reason": "chest pain"})
        self.assertTrue(ok2)
        self.assertEqual(call2.state, C.ESCALATED)

        call3 = self._call("TRIAGE")
        ok3, _ = al.apply_intent(call3, "prescription_refill", {"medication": "Metformin"})
        self.assertTrue(ok3)
        self.assertEqual(call3.state, C.PRESCRIPTION)

    def test_apply_intent_stores_severity_without_transition(self):
        call = self._call("TRIAGE")
        ok, new = agent_logic_mod.apply_intent(call, "set_triage_severity", {"severity": "red"})
        self.assertTrue(ok)
        self.assertIsNone(new)
        self.assertEqual(call.triage_severity, "red")
        self.assertEqual(call.state, calls_mod.CallState.TRIAGE)

    def test_apply_intent_rejects_invalid_transition(self):
        call = self._call("COMPLETE")
        ok, new = agent_logic_mod.apply_intent(call, "escalate", {"reason": "late"})
        self.assertFalse(ok)
        self.assertIsNone(new)

    def test_append_transcript(self):
        original = []
        updated = agent_logic_mod.append_transcript(original, "caller", "Hello", "hi")
        self.assertEqual(updated, [{"role": "caller", "text": "Hello", "language": "hi"}])
        self.assertEqual(original, [])

    def test_should_escalate(self):
        self.assertTrue(agent_logic_mod.should_escalate("red"))
        self.assertTrue(agent_logic_mod.should_escalate("CRITICAL"))
        self.assertFalse(agent_logic_mod.should_escalate("green"))
        self.assertFalse(agent_logic_mod.should_escalate("amber"))
        self.assertFalse(agent_logic_mod.should_escalate(None))

    def test_language_helpers(self):
        al = agent_logic_mod
        self.assertEqual(al.stt_language_tag("hi"), "hi-IN")
        self.assertEqual(al.stt_language_tag("ta"), "ta-IN")
        self.assertEqual(al.stt_language_tag("xx"), "en-IN")
        env = {"ELEVENLABS_VOICE_ID_HI": "v_hi", "ELEVENLABS_VOICE_ID": "v_plain"}
        self.assertEqual(al.tts_voice_id("hi", env, "v_default"), "v_hi")
        self.assertEqual(al.tts_voice_id("ta", env, "v_default"), "v_plain")
        self.assertEqual(al.tts_voice_id("ta", {"X": "1"}, "v_default"), "v_default")
        self.assertEqual(al.language_for_room({"language": "te"}, "hi"), "te")
        self.assertEqual(al.language_for_room({"ivr_digit": "1"}, "hi"), "hi")
        self.assertEqual(al.language_for_room({"ivr_digit": "7"}, "hi"), "hi")
        self.assertEqual(al.language_for_room({}, "en"), "en")
        self.assertEqual(al.language_for_room(None, "hi"), "hi")


if __name__ == "__main__":
    unittest.main(verbosity=2)