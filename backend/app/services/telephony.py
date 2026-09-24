"""Multi-provider telephony webhook parsing (Exotel / Knowlarity / Twilio-India).

Stdlib-only by design: pure dict-in -> ProviderEvent-out so the parsers run on
machines without fastapi/httpx installed (G4 pattern, spec-g4-voice-pipeline.md
§6). Live talk paths are wired in app/api/voice.py and exercised in Docker/CI.

Payload shapes verified against vendor docs 2026-09-24:
- Exotel    (JSON POST): CallSid, EventType (ringing|answered|terminal),
  Status (completed|failed|busy|no-answer), From/To, ConversationDuration,
  RecordingUrl, Direction.
- Knowlarity (form):    callid, caller_id, dispnumber, extension, action,
  start_time/end_time, resource_url, call_duration.
- Twilio    (form):     CallSid, CallStatus, From/To, Digits, CallDuration.

Parsers are defensive (multi-alias field resolution) because provider products
vary (Exotel v1 vs v2/CCM, Knowlarity SR vs Knowlus).
"""
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

CALL_INITIATED = "call.initiated"
CALL_ANSWERED = "call.answered"
CALL_HANGUP = "call.hangup"
CALL_DROPPED = "call.dropped"
IGNORED = "ignored"

# IVR DTMF digit -> language code (spec-micc-india: hi/en/ta/te/bn)
IVR_DIGIT_LANGUAGES = {"1": "hi", "2": "en", "3": "ta", "4": "te", "5": "bn"}

# Provider statuses that mean the caller never got through -> dropped
TERMINAL_DROPPED = {"no-answer", "busy", "failed", "canceled", "missed", "missed-call"}


@dataclass
class ProviderEvent:
    provider: str
    event_type: str = IGNORED
    call_sid: str = ""
    caller_number: str = ""
    inbound_number: str = ""
    language: str = ""
    started_at: str = ""
    duration_seconds: int = 0
    recording_url: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def _first(data: Dict[str, Any], *keys: str, default: str = "") -> str:
    for key in keys:
        value = data.get(key)
        if value is not None and str(value) != "":
            return str(value)
    return default


def normalize_phone(number: Any) -> str:
    """Best-effort E.164-ish normalization (keeps leading +, drops separators)."""
    s = str(number or "").strip()
    return "".join(ch for ch in s if ch.isdigit() or ch == "+")


def language_from_digit(digit: Optional[str]) -> str:
    """Map an IVR DTMF digit to a language code, '' when unknown."""
    if digit is None:
        return ""
    return IVR_DIGIT_LANGUAGES.get(str(digit).strip(), "")


def _duration(seconds: Any) -> int:
    try:
        return int(float(seconds))
    except (TypeError, ValueError):
        return 0


def parse_exotel(body: Dict[str, Any]) -> ProviderEvent:
    """Normalize an Exotel StatusCallback webhook (JSON body)."""
    sid = _first(body, "CallSid", "call_sid")
    status = _first(body, "Status", "CallStatus").lower()
    et = _first(body, "EventType", "event_type").lower()
    if et == "terminal" or (not et and status):
        event_type = (
            CALL_DROPPED
            if status in TERMINAL_DROPPED
            else (CALL_HANGUP if status == "completed" else IGNORED)
        )
    elif et == "answered" or status == "in-progress":
        event_type = CALL_ANSWERED
    elif et == "ringing" or status == "ringing":
        event_type = CALL_INITIATED
    else:
        event_type = IGNORED
    return ProviderEvent(
        provider="exotel",
        event_type=event_type,
        call_sid=sid,
        caller_number=normalize_phone(_first(body, "From", "caller_number")),
        inbound_number=normalize_phone(_first(body, "To", "PhoneNumberSid")),
        started_at=_first(body, "DateCreated", "StartTime"),
        duration_seconds=_duration(_first(body, "ConversationDuration", "Duration")),
        recording_url=_first(body, "RecordingUrl"),
        raw=body,
    )


def parse_knowlarity(form: Dict[str, Any]) -> ProviderEvent:
    """Normalize a Knowlarity SR / hook-api webhook (form fields)."""
    sid = _first(form, "callid", "call_id", "CallSid")
    caller = normalize_phone(_first(form, "caller_id", "From"))
    inbound = normalize_phone(_first(form, "dispnumber", "To"))
    digit = form.get("extension") or form.get("Digits")
    action = _first(form, "action", "Action").lower()
    duration = _duration(_first(form, "call_duration", "ConversationDuration"))
    is_terminal = bool(_first(form, "end_time", "EndTime")) or duration > 0
    if is_terminal:
        event_type = CALL_DROPPED if action in ("fax", "voicemail") else CALL_HANGUP
    elif action == "phone":
        event_type = CALL_INITIATED
    else:
        event_type = IGNORED
    return ProviderEvent(
        provider="knowlarity",
        event_type=event_type,
        call_sid=sid,
        caller_number=caller,
        inbound_number=inbound,
        language=language_from_digit(digit),
        started_at=_first(form, "start_time", "StartTime"),
        duration_seconds=duration,
        recording_url=_first(form, "resource_url"),
        raw=form,
    )


def parse_twilio(form: Dict[str, Any]) -> ProviderEvent:
    """Normalize a Twilio-India voice callback (form fields)."""
    sid = _first(form, "CallSid", "call_sid")
    status = _first(form, "CallStatus", "CallStatus").lower()
    if status == "completed":
        event_type = CALL_HANGUP
    elif status in TERMINAL_DROPPED:
        event_type = CALL_DROPPED
    elif status in ("ringing", "queued", "initiated"):
        event_type = CALL_INITIATED
    elif status in ("in-progress", "answered"):
        event_type = CALL_ANSWERED
    else:
        event_type = IGNORED
    return ProviderEvent(
        provider="twilio",
        event_type=event_type,
        call_sid=sid,
        caller_number=normalize_phone(_first(form, "From", "Caller")),
        inbound_number=normalize_phone(_first(form, "To")),
        language=language_from_digit(form.get("Digits")),
        started_at=_first(form, "Timestamp", "CallTimestamp"),
        duration_seconds=_duration(_first(form, "CallDuration")),
        recording_url=_first(form, "RecordingUrl"),
        raw=form,
    )