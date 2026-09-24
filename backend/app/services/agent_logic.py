"""Medical LiveKit agent logic — stdlib-only, unit-testable without livekit.

Single source of truth for the conversation brain used by app/services/llm.py
(LLM function schema) and app/services/livekit_agent.py (agent loop): medical
system prompt, intent -> G3 state-machine application, transcript append, and
5-language helpers (hi/en/ta/te/bn). Pure functions only: no network, no DB
(G4 spec §4/§6).
"""
from typing import Any, Dict, List, Optional, Tuple

from app.models.call import Call, CallState, TriageSeverity

SUPPORTED_LANGUAGES = ("hi", "en", "ta", "te", "bn")

# Deepgram STT tags per language (spec-micc-india)
STT_TAGS = {"hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN"}

# IVR DTMF digit -> language code (mirrors app.services.telephony)
IVR_DIGIT_LANGUAGES = {"1": "hi", "2": "en", "3": "ta", "4": "te", "5": "bn"}

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