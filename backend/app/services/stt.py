"""Deepgram WebSocket STT — multi-language (hi/en/ta/te/bn)."""
import asyncio
import json
import os
from typing import AsyncGenerator, Optional

import websockets

from app.services.agent_logic import stt_language_tag
from app.services.languages import resolve_stt_language

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
DEEPGRAM_TEMPLATE = (
    "wss://api.deepgram.com/v1/listen?model=nova-3&language={lang}&"
    "punctuate=true&interim_results=true&encoding=linear16&sample_rate=16000"
)


async def stt_stream(
    audio_queue: asyncio.Queue, language: str = "hi"
) -> AsyncGenerator[str, None]:
    """Stream audio to Deepgram and yield transcripts in the call language."""
    url = DEEPGRAM_TEMPLATE.format(lang=stt_language_tag(language))
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}

    async with websockets.connect(url, extra_headers=headers) as ws:
        async def sender():
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "CloseStream"}))

        async def receiver():
            async for msg in ws:
                data = json.loads(msg)
                if "channel" in data:
                    transcript = data["channel"]["alternatives"][0]["transcript"]
                    if transcript:
                        yield transcript

        sender_task = asyncio.create_task(sender())
        async for transcript in receiver():
            yield transcript
        await sender_task


def _env_threshold() -> Optional[float]:
    """STT_CONFIDENCE_THRESHOLD env (G6-Q4 Q1=A1); empty/invalid -> None.

    None lets resolve_stt_language use its 0.6 default constant, so a bad value
    in the environment can never crash the stream or change the floor
    unexpectedly.
    """
    raw = os.getenv("STT_CONFIDENCE_THRESHOLD", "").strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


async def stt_stream_with_scores(
    audio_queue: asyncio.Queue, language: str = "hi"
) -> AsyncGenerator[tuple, None]:
    """stt_stream + per-utterance Deepgram confidence (G6-Q4 Q1=A1).

    Yields (transcript, confidence, language): `language` applies the
    confidence-low fallback chain (resolve_stt_language — a low-confidence turn
    falls the *operative* language back to English so the agent can re-prompt,
    and the transcript is flagged low_confidence by the caller). The G4
    stt_stream (transcript-only) is unchanged. Live wiring happens in
    Docker/CI (livekit not installed on this PC).
    """
    url = DEEPGRAM_TEMPLATE.format(lang=stt_language_tag(language))
    headers = {"Authorization": f"Token {DEEPGRAM_API_KEY}"}
    threshold = _env_threshold()

    async with websockets.connect(url, extra_headers=headers) as ws:
        async def sender():
            while True:
                chunk = await audio_queue.get()
                if chunk is None:
                    break
                await ws.send(chunk)
            await ws.send(json.dumps({"type": "CloseStream"}))

        async def receiver():
            async for msg in ws:
                data = json.loads(msg)
                if "channel" in data:
                    alt = data["channel"]["alternatives"][0]
                    transcript = alt.get("transcript", "")
                    if transcript:
                        yield (
                            transcript,
                            alt.get("confidence"),
                            resolve_stt_language(language, alt.get("confidence"), threshold=threshold),
                        )

        sender_task = asyncio.create_task(sender())
        async for item in receiver():
            yield item
        await sender_task