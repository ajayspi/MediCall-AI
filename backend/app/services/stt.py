"""Deepgram WebSocket STT — multi-language (hi/en/ta/te/bn)."""
import asyncio
import json
import os
from typing import AsyncGenerator

import websockets

from app.services.agent_logic import stt_language_tag

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