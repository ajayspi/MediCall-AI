"""Medical LiveKit agent logic — stdlib-only, unit-testable without livekit.

Single source of truth for the conversation brain used by app/services/llm.py
(LLM function schema) and app/services/livekit_agent.py (agent loop): medical
system prompt, intent -> G3 state-machine application, transcript append, and
5-language helpers (hi/en/ta/te/bn). Pure functions only: no network, no DB
(G4 spec §4/§6).
"""
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.models.call import Call, CallState, TriageSeverity

# G6-Q4 (Q2=A1): the 5-language catalog is single-sourced in
# app/services/languages.py. These names are re-exported so existing consumers
# (telephony mirrors, G4 pins on agent_logic) keep working unchanged.
from app.services.languages import (
    IVR_DIGIT_LANGUAGES,
    STT_TAGS,
    SUPPORTED_LANGUAGES,
)

# The in-call pharmacovigilance collector (spec-micc-pv-phase2.md, slice 2B).
# Imported for its pure functions only, and deliberately NOT folded into
# MEDICAL_FUNCTIONS above: that schema is pinned to 5 names by tests/test_g4_voice.py
# and is the single source app/services/llm.py ships to the model. The PV
# function list lives beside its own pipeline (call_intake.PV_FUNCTIONS) so the
# pin can be lifted deliberately rather than by accident.
from app.services import call_intake

# Valid triage severities (never a diagnosis — flag only)
SEVERITIES = {s.value for s in TriageSeverity}  # green, amber, red, critical

# Intent name -> target CallState (validated against STATE_TRANSITIONS in apply_intent)
INTENT_STATES: Dict[str, CallState] = {
    "book_appointment": CallState.APPOINTMENT,
    "prescription_refill": CallState.PRESCRIPTION,
    "escalate": CallState.ESCALATED,
    "end_call": CallState.COMPLETE,
}

MEDICAL_FUNCTIONS = [
    {
        "name": "set_triage_severity",
        "description": "Record the triage urgency of the caller's situation "
        "(strictly a flag for the care team, never a diagnosis).",
        "parameters": {
            "type": "object",
            "properties": {
                "severity": {
                    "type": "string",
                    "enum": ["green", "amber", "red", "critical"],
                },
                "reason": {"type": "string"},
            },
            "required": ["severity"],
        },
    },
    {
        "name": "book_appointment",
        "description": "Schedule a clinic appointment for the caller.",
        "parameters": {
            "type": "object",
            "properties": {
                "patient_name": {"type": "string"},
                "reason": {"type": "string"},
                "preferred_datetime": {"type": "string"},
            },
            "required": ["patient_name"],
        },
    },
    {
        "name": "prescription_refill",
        "description": "Record a prescription refill request for review by a doctor.",
        "parameters": {
            "type": "object",
            "properties": {
                "medication": {"type": "string"},
                "dosage": {"type": "string"},
                "frequency": {"type": "string"},
            },
            "required": ["medication"],
        },
    },
    {
        "name": "escalate",
        "description": "Transfer the caller to a human specialist immediately.",
        "parameters": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "end_call",
        "description": "End the call with an optional summary.",
        "parameters": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
        },
    },
]


def system_prompt(
    clinic_name: str,
    ai_instructions: str = "",
    language: str = "en",
    date: str = "",
    time: str = "",
    state: str = "GREETING",
    call_summary: str = "",
) -> str:
    """Medical system prompt (safety-guardrailed: no diagnosis, no dosage)."""
    return (
        f"You are the MediCall voice assistant for {clinic_name}, an Indian "
        "medical call center. You help callers with triage, clinic appointment "
        "booking, and prescription refill requests.\n\n"
        "You must NEVER give a diagnosis, prescribe medication, or recommend "
        "dosage — only a licensed doctor may. Never claim to be a doctor. "
        "If the caller reports chest pain, breathing difficulty, severe "
        "bleeding, or any life-threatening symptom, escalate to a human "
        "specialist immediately.\n"
        f"Language: respond in '{language}' (hi/en/ta/te/bn).\n"
        f"Today is {date} at {time}. Current call state: {state}.\n"
        f"Clinic guidance: {ai_instructions}\n"
        f"Conversation so far: {call_summary}\n"
        "Keep answers short, clear, and calm."
    )


def apply_intent(
    call: Call, fn_name: str, args: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[CallState]]:
    """Apply an LLM function call to the G3 state machine.

    Returns (applied, new_state): new_state is None when the intent does not
    change state (set_triage_severity); applied=False when the function is
    unknown or the transition is invalid per models/call.py STATE_TRANSITIONS.
    """
    args = args or {}
    if fn_name == "set_triage_severity":
        severity = str(args.get("severity", "")).lower()
        if severity in SEVERITIES:
            call.triage_severity = severity
            return True, None
        return False, None
    target = INTENT_STATES.get(fn_name)
    if target is None:
        return False, None
    if call.transition(target):
        return True, target
    return False, None


def append_transcript(
    transcript: List[Dict[str, str]], role: str, text: str, language: str
) -> List[Dict[str, str]]:
    """Return a new transcript with one entry appended (no in-place mutation)."""
    return [*transcript, {"role": role, "text": text, "language": language}]


def should_escalate(severity: Optional[str]) -> bool:
    """RED/CRITICAL triage severities escalate immediately (D2)."""
    return (severity or "").lower() in ("red", "critical")


def stt_language_tag(language: str) -> str:
    """Deepgram STT language tag; unknown codes fall back to English-India."""
    return STT_TAGS.get(language, "en-IN")


def tts_voice_id(
    language: str, env_voices: Dict[str, Optional[str]], fallback: str
) -> str:
    """Per-language ElevenLabs voice id: {LANG} env -> generic env -> fallback."""
    key = f"ELEVENLABS_VOICE_ID_{str(language).upper()}"
    for candidate in (env_voices.get(key), env_voices.get("ELEVENLABS_VOICE_ID"), fallback):
        if candidate:
            return candidate
    return fallback


def language_for_room(metadata: Optional[Dict[str, Any]], default: str = "hi") -> str:
    """Language from room metadata: explicit tag -> IVR digit -> default (D3)."""
    if not isinstance(metadata, dict):
        return default
    tag = metadata.get("language")
    if isinstance(tag, str) and tag in SUPPORTED_LANGUAGES:
        return tag
    digit = metadata.get("ivr_digit")
    if digit is not None:
        mapped = IVR_DIGIT_LANGUAGES.get(str(digit).strip(), "")
        if mapped:
            return mapped
    return default


# G6-Q4 (Q3=A1): per-language opening greeting — mirrors the guardrails
# SAFE_REFUSALS shape (fixed text per language, English template as fallback).
GREETING_TEMPLATES = {
    "hi": "नमस्ते, {clinic} में आपका स्वागत है।",
    "en": "Namaste, welcome to {clinic}.",
    "ta": "வணக்கம், {clinic} க்கு வரவேற்கிறோம்।",
    "te": "నమస్కారం, {clinic} కు స్వాగతం।",
    "bn": "নমস্কার, {clinic} এ আপনাকে স্বাগতম।",
}


def greeting_for_language(language: Optional[str], clinic_name: str) -> str:
    """Localized opening greeting; unknown/None language -> English template.

    The TTS voice was already per-language (tts.voice_for_language); this makes
    the *text* per-language too (previously the greeting was always English
    words — livekit_agent emitted "Namaste, welcome to {clinic}." in every
    language).
    """
    template = GREETING_TEMPLATES.get(language) if isinstance(language, str) else None
    return (template or GREETING_TEMPLATES["en"]).format(clinic=clinic_name)


# ─── Pharmacovigilance in-call capture (slice 2B) ───────────────────────────
# The in-call half of PV intake: route the call, capture what the caller said,
# ask for what is still missing, and assemble the exact /api/pv/cases body. It
# lives here - not in the voice worker - so the whole pipeline is unit-testable
# with the voice SDK absent, which is the point: a PV collector that can only be
# exercised with a live voice room is a collector nobody can prove correct.
def caller_speech(transcript: Any) -> str:
    """The caller's own words from a transcript, one utterance per line.

    Only `role == "caller"` turns: the agent's questions and the operator's
    system notes are the call centre's words, and a PV case records what the
    CALLER said. A missing transcript, a non-list, a non-dict turn and a blank
    turn are all skipped rather than raising - a call that dropped before any
    speech is a normal outcome, not an error.
    """
    if not isinstance(transcript, (list, tuple)):
        return ""
    lines: List[str] = []
    for turn in transcript:
        if not isinstance(turn, dict):
            continue
        if str(turn.get("role", "")).strip().lower() != "caller":
            continue
        text = str(turn.get("text") or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def run_pv_intake(
    transcript: Any,
    language: str = "en",
    clinic_id: str = "",
    call_id: str = "",
    phone_suffix: str = "",
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Run the whole in-call PV pipeline and return what the agent should do.

    The five steps, in the order the voice turn needs them:
      1. route the call to ae / pqc / mi - or `none`, which is not a PV case;
      2. capture the ICH E2B minimum from the caller's own words;
      3. ask, in the caller's language, for exactly what is still missing;
      4. name the reportable special situations, each with its own prompt;
      5. assemble the exact POST /api/pv/cases body.

    `transcript` is the live transcript list or a plain string of caller speech.

    NOTHING IS SENT FROM HERE. `payload` is the request body for the D1
    persistence point in the voice worker; this module has no HTTP client, so a
    case cannot be filed by accident from a test.

    `e2b_minimum_met` is the ENDPOINT's own check (app/api/pv.py, via
    app/services/pharmacovigilance.py), REPORTED and not enforced: ABPI
    store-and-forward means an incomplete case is still captured and still
    chased by a follow-up call, so `should_submit` is True for every PV intent
    whether or not the minimum is met. `missing` is what the agent asks about.

    `today` is the reference day for a relative onset ("yesterday"). It is a
    parameter rather than a clock read, so the same call always yields the same
    body and a relative phrase with no reference day yields no date at all.
    """
    spoken = transcript if isinstance(transcript, str) else caller_speech(transcript)
    route = call_intake.detect_intent(spoken, language)
    intent = route["intent"]
    code = route["language"]

    if intent == "none":
        # A booking call is not a PV case. Post one anyway and the compliance
        # audit trail fills with noise, so the pipeline stops here - with no
        # body, no completeness claim and nothing said about a medicine.
        return {
            "intent": intent,
            "contact_type": route["contact_type"],
            "function": route["function"],
            "language": code,
            "should_submit": False,
            "payload": None,
            "script": [],
            "special_situations": [],
            "special_prompts": [],
            "prompts": [],
            "e2b_minimum_met": False,
            "missing": [],
            "is_serious": False,
            "seriousness_criteria": [],
        }

    fields = call_intake.extract_case_fields(spoken, intent, code, today=today)
    situations = call_intake.special_situation_flags(fields, spoken, code)
    payload = call_intake.build_case_payload(
        intent,
        fields,
        situations,
        metadata={
            "clinic_id": clinic_id,
            "call_id": call_id,
            "language": code,
            "phone_suffix": phone_suffix,
        },
    )
    met, missing = call_intake.intake_minimum_criteria(payload)
    # Asked against the assembled body, not the raw fields: the callback number
    # already identifies the reporter (WHO E2B accepts a contact detail), so the
    # agent must not ask a caller for a name it already holds.
    script = call_intake.question_script(intent, code, fields=payload)
    special_prompts = call_intake.special_situation_prompts(situations, code)
    is_serious, criteria = call_intake.is_serious_payload(payload)
    return {
        "intent": intent,
        "contact_type": route["contact_type"],
        "function": route["function"],
        "language": code,
        "should_submit": True,
        "payload": payload,
        "script": script,
        "special_situations": situations,
        "special_prompts": special_prompts,
        "prompts": script + special_prompts,
        "e2b_minimum_met": met,
        "missing": missing,
        "is_serious": is_serious,
        "seriousness_criteria": criteria,
    }