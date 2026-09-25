"""G6-Q4 language catalog — single source for the 5-language voice pipeline.

Q2=A1: the exact-5 language set (hi/en/ta/te/bn) plus its STT/TTS/IVR mappings
live here and nowhere else. Consumers import from this module:

* `SUPPORTED_LANGUAGES` — the 5-tuple (previously duplicated in agent_logic,
  postgres.py, services/notifications.py).
* `STT_TAGS` — Deepgram `-IN` tags per language (checked by stt_language_tag).
* `IVR_DIGIT_LANGUAGES` — IVR DTMF digit -> language (mirrors telephony).
* `TTS_VOICE_ENV_KEYS` — canonical per-language ElevenLabs env keys
  (ELEVENLABS_VOICE_ID_{CODE}, Q4=A1; the legacy _HINDI/_TAMIL/... names are
  gone from .env.example).
* `LANGUAGE_FALLBACK_CHAIN` — the confidence-low fallback chain (Q1=A1):
  [detected] -> en (English is the safe default).

Q1=A1: `resolve_stt_language(language, confidence, threshold, fallback, env)` —
a confirmed utterance (confidence >= threshold, or confidence is None) keeps the
call language; a low-confidence utterance (< threshold) falls the *operative*
language back to English for that turn. `STT_CONFIDENCE_THRESHOLD` env overrides
the 0.6 default.

Stdlib-only (leaf module: nothing in `app` imports this at import time except
leaf-safe consumers, so there is no circular-import risk for postgres.py).
"""
import os
from typing import Optional, Tuple

# Exact 5 languages for MVP (hi/en/ta/te/bn) — single source of truth.
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("hi", "en", "ta", "te", "bn")

# Deepgram STT tags per language (spec-micc-india).
STT_TAGS = {"hi": "hi-IN", "en": "en-IN", "ta": "ta-IN", "te": "te-IN", "bn": "bn-IN"}

# IVR DTMF digit -> language code (mirrors app.services.telephony).
IVR_DIGIT_LANGUAGES = {"1": "hi", "2": "en", "3": "ta", "4": "te", "5": "bn"}

# Canonical per-language ElevenLabs voice env keys (Q4=A1): the code-built form
# ELEVENLABS_VOICE_ID_{CODE}. .env.example documents exactly these five.
TTS_VOICE_ENV_KEYS = {
    code: f"ELEVENLABS_VOICE_ID_{code.upper()}" for code in SUPPORTED_LANGUAGES
}

# Confidence-low fallback chain (Q1=A1): [detected] -> en (English is the safe
# default when STT confidence is below the floor).
LANGUAGE_FALLBACK_CHAIN: Tuple[str, ...] = ("en",)

# Default STT confidence floor; STT_CONFIDENCE_THRESHOLD env overrides it.
STT_CONFIDENCE_THRESHOLD = 0.6


def is_supported_language(language) -> bool:
    """True for exactly the 5 supported codes (case-sensitive)."""
    return isinstance(language, str) and language in SUPPORTED_LANGUAGES


def resolve_stt_language(
    language: str,
    confidence: Optional[float] = None,
    threshold: Optional[float] = None,
    fallback: str = "en",
    env: Optional[dict] = None,
) -> str:
    """Q1=A1 confidence-low fallback chain: which language a turn operates in.

    A confirmed utterance (confidence >= threshold, or confidence is None —
    Deepgram may not score every alternative) keeps the call language. A
    low-confidence utterance (< threshold) falls the operative language back to
    English for that turn (the caller can still be re-prompted in en).

    `threshold` defaults to the STT_CONFIDENCE_THRESHOLD env value, then to the
    0.6 module constant; pass `env` explicitly in tests to isolate the process
    environment. `fallback` is the chain head — LANGUAGE_FALLBACK_CHAIN[0] ("en")
    by default.
    """
    if threshold is None:
        threshold = _threshold_from_env(env)
    if confidence is None:
        return language
    if confidence >= threshold:
        return language
    return fallback or LANGUAGE_FALLBACK_CHAIN[0]


def _threshold_from_env(env: Optional[dict]) -> float:
    source = os.environ if env is None else env
    raw = (source.get("STT_CONFIDENCE_THRESHOLD") or "").strip()
    try:
        return float(raw) if raw else STT_CONFIDENCE_THRESHOLD
    except (TypeError, ValueError):
        return STT_CONFIDENCE_THRESHOLD