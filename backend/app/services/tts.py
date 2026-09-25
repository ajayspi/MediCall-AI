"""ElevenLabs TTS streaming — multi-language voices (hi/en/ta/te/bn)."""
import os
from typing import AsyncGenerator, Optional

import httpx

from app.services.languages import TTS_VOICE_ENV_KEYS

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
BASE_URL = "https://api.elevenlabs.io/v1"


def voice_for_language(language: str, env: Optional[dict] = None) -> str:
    """Select the ElevenLabs voice for a language (env map -> generic -> default).

    Canonical per-language keys come from the languages catalog (G6-Q4 Q4=A1):
    ELEVENLABS_VOICE_ID_HI/_EN/_TA/_TE/_BN, with ELEVENLABS_VOICE_ID as the
    generic fallback. The legacy _HINDI/_TAMIL/... names are gone from
    .env.example (they never fired — the code always built the {CODE} form).
    """
    env = env or os.environ
    key = TTS_VOICE_ENV_KEYS.get(language) or f"ELEVENLABS_VOICE_ID_{str(language).upper()}"
    return env.get(key) or env.get("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID


async def tts_stream(text: str, language: str = "hi") -> AsyncGenerator[bytes, None]:
    """Stream TTS audio from ElevenLabs in the call language."""
    voice_id = voice_for_language(language)
    url = f"{BASE_URL}/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            async for chunk in response.aiter_bytes():
                yield chunk