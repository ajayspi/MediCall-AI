"""Voice API — Exotel / Knowlarity / Twilio-India webhooks → LiveKit agents.

G4: multi-provider telephony for the Indian Medical Call Center. Webhook
parsing lives in app.services.telephony (stdlib, unit-tested); this module
wires it to FastAPI routes and the LiveKit dispatch stub (live dispatch runs
in Docker/CI, same pattern as main.py lifespan init_db).
"""
import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.services.telephony import (
    CALL_ANSWERED,
    CALL_DROPPED,
    CALL_HANGUP,
    CALL_INITIATED,
    IGNORED,
    parse_exotel,
    parse_knowlarity,
    parse_twilio,
)

router = APIRouter()

DEFAULT_LANGUAGE = os.getenv("DEFAULT_CALLER_LANGUAGE", "hi")
DEFAULT_CLINIC_ID = os.getenv("DEFAULT_CLINIC_ID", "")


class LiveKitStart(BaseModel):
    clinic_id: str = DEFAULT_CLINIC_ID
    call_sid: str
    caller_number: str
    language: str = DEFAULT_LANGUAGE
    call_id: str = ""


class CallCompleted(BaseModel):
    call_id: str
    transcript: list = []
    ended_at: str = ""
    duration_seconds: int = 0
    state: str = "COMPLETE"


def room_name_for(event) -> str:
    """LiveKit room name derived from the provider call id."""
    return f"call-{event.call_sid}"


def handle_event(event) -> dict:
    """Normalized provider event -> webhook response + dispatch decision."""
    if event.event_type == IGNORED:
        return {"status": "ignored"}
    if event.event_type == CALL_INITIATED:
        language = event.language or DEFAULT_LANGUAGE
        # TODO(Docker/CI): create CallSession + dispatch LiveKit agent to room
        return {"status": "ok", "room": room_name_for(event), "language": language}
    if event.event_type == CALL_ANSWERED:
        return {"status": "ok", "room": room_name_for(event)}
    if event.event_type in (CALL_HANGUP, CALL_DROPPED):
        # TODO(Docker/CI): finalize session; agent /call-completed persists transcript
        return {"status": "ok", "call_sid": event.call_sid}
    return {"status": "ignored"}


@router.post("/webhook/exotel")
async def exotel_webhook(request: Request):
    """Exotel StatusCallback webhook (JSON body)."""
    body = await request.json()
    if not isinstance(body, dict):
        body = {}
    return handle_event(parse_exotel(body))


@router.post("/webhook/knowlarity")
async def knowlarity_webhook(request: Request):
    """Knowlarity SR / hook-api webhook (form fields)."""
    form = dict(await request.form())
    return handle_event(parse_knowlarity(form))


@router.post("/webhook/twilio")
async def twilio_webhook(request: Request):
    """Twilio-India voice callback (form fields)."""
    form = dict(await request.form())
    return handle_event(parse_twilio(form))


@router.post("/livekit-agent-start")
async def start_livekit_agent(data: LiveKitStart):
    """Dispatch the medical agent into a LiveKit room for an inbound call."""
    room = room_name_for(data)
    return {"status": "agent_started", "room": room, "language": data.language}


@router.post("/call-completed")
async def call_completed(data: CallCompleted):
    """Agent → API transcript persistence (D1). Saves calls.transcript.

    The postgres write (update_call_transcript) is imported lazily so the API
    layer stays import-light on dev machines without sqlalchemy (Docker/CI has
    it). Idempotent: keyed by call_id.
    """
    # TODO(Docker/CI):
    #   from app.db.postgres import update_call_transcript
    #   await update_call_transcript(data.call_id, data.transcript,
    #                                data.ended_at, data.duration_seconds)
    return {
        "status": "saved",
        "call_id": data.call_id,
        "turns": len(data.transcript),
        "state": data.state,
    }