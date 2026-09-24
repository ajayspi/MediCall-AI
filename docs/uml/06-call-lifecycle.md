# 06 — Inbound Call Lifecycle (Sequence)

```mermaid
sequenceDiagram
    autonumber
    participant P as Caller (patient phone)
    participant TP as Telephony provider (Exotel / Knowlarity / Twilio)
    participant V as voice.py webhooks
    participant A as LiveKit medical agent
    participant DG as Deepgram STT
    participant EL as ElevenLabs TTS
    participant DB as PostgreSQL

    P->>TP: dials clinic number
    TP->>V: webhook (initiated / answered)
    V->>V: ProviderEvent -> state GREETING
    V->>A: dispatch to LiveKit room call-{sid} in caller language
    loop conversation turns (hi / en / ta / te / bn)
        P->>DG: speech
        DG->>A: transcript turn
        A->>A: advance CallState: GREETING -> TRIAGE -> APPOINTMENT / PRESCRIPTION
        A->>EL: agent reply text
        EL-->>P: spoken voice
    end
    alt triage / fulfillment outcome
        A->>A: APPOINTMENT path: schedule appointment (+ optional payment intent)
        A->>A: PRESCRIPTION path: PAYMENT_SENT -> PAYMENT_EXPIRED loop or COMPLETE
        A->>A: ESCALATED: hand off to human
    end
    A->>V: POST /api/voice/call-completed (transcript JSONB, state, duration)
    V->>DB: update_call_transcript (write owned by Docker/CI stage)
    Note over DB: transcript persisted - Phase 1 EHR (transcript-only) feeds pgvector
```

## Notes

- Lifecycle corresponds to the state machine in 02: GREETING → TRIAGE →
  APPOINTMENT / PRESCRIPTION, with ESCALATED / DROPPED exits and the
  PAYMENT_SENT → PAYMENT_EXPIRED loop.
- The payment leg shows the designed loop; real gateway SDK calls remain gated on
  the G6-Q5 decision — the API currently records payment intents only.
- The `/call-completed` → `update_call_transcript` DB write is a Docker/CI-stage
  TODO (idempotent, keyed by `call_id`), matching 04-data-flow.