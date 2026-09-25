"""Medical LiveKit agent logic — stdlib-only, unit-testable without livekit.

Single source of truth for the conversation brain used by app/services/llm.py
(LLM function schema) and app/services/livekit_agent.py (agent loop): medical
system prompt, intent -> G3 state-machine application, transcript append, and
5-language helpers (hi/en/ta/te/bn). Pure functions only: no network, no DB
(G4 spec §4/§6).
"""
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