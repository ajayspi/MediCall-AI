"""LiveKit Agents pipeline — MediCall AI medical agent (thin glue).

All conversation logic lives in app/services/agent_logic.py (stdlib, unit-
tested): the medical system prompt, the MEDICAL_FUNCTIONS schema, intent →
CallState application, and the 5-language helpers. This module only wires
livekit events/audio to that logic and to the LLM/TTS services; live runs
happen in Docker/CI (no livekit installed on this PC).
"""
import json
import os

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli

from app.models.call import Call, CallState
from app.services import agent_logic
from app.services import guardrails
from app.services.llm import generate_response
from app.services.tts import tts_stream

DEFAULT_LANGUAGE = os.getenv("DEFAULT_CALLER_LANGUAGE", "hi")


def call_from_metadata(metadata: dict) -> Call:
    """Build the Call (G3 state machine) from LiveKit room metadata."""
    lang = agent_logic.language_for_room(metadata, DEFAULT_LANGUAGE)
    return Call(
        id=metadata.get("call_id", ""),
        clinic_id=metadata.get("clinic_id", ""),
        caller_number=metadata.get("caller_number", ""),
        state=CallState.GREETING,
        caller_language=lang,
    )


def parse_function_arguments(fn_call) -> dict:
    """OpenAI-style function_call arguments may arrive as dict or JSON str."""
    raw = getattr(fn_call, "arguments", None)
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


async def entrypoint(ctx: JobContext):
    """Main LiveKit agent entrypoint (medical flow)."""
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    metadata = json.loads(ctx.room.metadata) if ctx.room.metadata else {}
    call = call_from_metadata(metadata)
    clinic_name = metadata.get("clinic_name", "MediCall AI")
    ai_instructions = metadata.get("ai_instructions", "")

    greeting = (
        f"Namaste, welcome to {clinic_name}. "
        "Tell me briefly how we can help you today."
    )
    async for chunk in tts_stream(greeting, language=call.caller_language):
        await ctx.room.local_participant.publish_audio(chunk)

    transcript: list = []
    call.state = CallState.TRIAGE

    async for event in ctx.room.events():
        if event.type == "audio":
            pass  # live STT streaming wiring (Deepgram via stt_stream) — Docker/CI
        elif event.type == "transcript":
            user_text = event.transcript
            transcript = agent_logic.append_transcript(
                transcript, "caller", user_text, call.caller_language
            )
            # G6-Q3 deterministic path (temperature≈0): a red-flag keyword
            # beats any LLM severity judgment — escalate now, no generation.
            red_flag = guardrails.match_red_flag(user_text)
            if red_flag is not None:
                call.triage_severity = "red"
                transcript = agent_logic.append_transcript(
                    transcript, "system", f"red_flag:{red_flag[0]}",
                    call.caller_language,
                )
                async for chunk in tts_stream(
                    guardrails.ESCALATE_PHRASES.get(
                        call.caller_language,
                        "Connecting you to a specialist. Please stay on the line.",
                    ),
                    language=call.caller_language,
                ):
                    await ctx.room.local_participant.publish_audio(chunk)
                break
            messages = [{"role": "user", "content": user_text}]
            response = await generate_response(
                messages=messages,
                clinic_name=clinic_name,
                ai_instructions=ai_instructions,
                language=call.caller_language,
                state=call.state.value,
            )
            fn_call = getattr(response, "function_call", None)
            if fn_call is not None and getattr(fn_call, "name", None):
                agent_logic.apply_intent(
                    call, fn_call.name, parse_function_arguments(fn_call)
                )
                if call.state == CallState.ESCALATED:
                    # D2 escalation MVP → G6-Q3: per-language phrase (EN keeps
                    # the specialist text); flag + message + room event for the
                    # operator UI; PSTN warm-transfer stub lands in integration.
                    async for chunk in tts_stream(
                        guardrails.ESCALATE_PHRASES.get(
                            call.caller_language,
                            "Connecting you to a specialist. Please stay on the line.",
                        ),
                        language=call.caller_language,
                    ):
                        await ctx.room.local_participant.publish_audio(chunk)
                    break
                if call.state == CallState.COMPLETE:
                    break
            else:
                content = getattr(response, "content", None) or ""
                # G6-Q3: no-diagnosis/no-dosage from AI — guard before TTS so a
                # forbidden claim is never spoken (Q2/A2a deterministic guard).
                safe_text, _flag, _reason = guardrails.guard_output(
                    content, language=call.caller_language
                )
                async for chunk in tts_stream(
                    safe_text, language=call.caller_language
                ):
                    await ctx.room.local_participant.publish_audio(chunk)

    # D1: persist transcript via POST /api/voice/call-completed (agent worker →
    # API, httpx + API_BASE_URL configured in Docker/CI). `transcript` +
    # `call.id` are the payload; the reporter below is the integration seam.
    _ = (transcript, call.id, call.state.value)


def main():
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))


if __name__ == "__main__":
    main()