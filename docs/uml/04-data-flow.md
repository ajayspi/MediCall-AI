# 04 — Voice Pipeline Data Flow

```mermaid
flowchart LR
    EX["Exotel<br/>StatusCallback (JSON)"] -->|initiated / answered| WH["voice.py webhooks"]
    KL["Knowlarity<br/>SR / hook-api (form)"] -->|initiated / answered| WH
    TW["Twilio-India<br/>voice callback (form)"] -->|initiated / answered| WH
    WH -->|ProviderEvent| HA["handle_event -> state machine"]
    HA -->|CALL_INITIATED| ROOM["room: call-{sid}"]
    ROOM --> LK["LiveKit room"]
    LK --> AG["LiveKit medical agent"]
    AG --> STT["Deepgram STT (nova-3): hi / en / ta / te / bn"]
    AG --> LLM["LLM triage (OpenAI GPT)"]
    AG --> TTS["ElevenLabs TTS (per-language voices)"]
    STT --> AG
    TTS --> AG
    AG -->|hangup / dropped| CC["POST /api/voice/call-completed"]
    CC -.->|postgres write| DB[("PostgreSQL<br/>update_call_transcript (Docker/CI TODO)")]
```

## Notes

- **3-provider fallback chain** (locked): Exotel → Knowlarity → Twilio-India.
  Parsers in `backend/app/services/telephony.py` normalize to `ProviderEvent`
  (stdlib, unit-tested in G4); `voice.py` maps events to responses + dispatch.
- **Dispatch** (`POST /livekit-agent-start`) targets room `call-{sid}` in the
  caller's language; the LiveKit agent runs the `CallState` machine.
- **STT/TTS**: Deepgram `nova-3` and ElevenLabs across hi/en/ta/te/bn (the
  five locked languages; `language_codes` seed row in `postgres_schema.sql`).
- **Transcript persistence** (`update_call_transcript`) is a TODO owned by the
  Docker/CI stage — `voice.py` returns `saved` but the postgres write lands once
  sqlalchemy is in the runtime image (idempotent, keyed by `call_id`).
- Grey dashed edge = Docker/CI-stage work, not yet live.