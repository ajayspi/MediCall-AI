# 02 — Call State Machine

```mermaid
stateDiagram-v2
    [*] --> GREETING
    GREETING --> TRIAGE
    GREETING --> ESCALATED
    GREETING --> DROPPED
    TRIAGE --> APPOINTMENT
    TRIAGE --> PRESCRIPTION
    TRIAGE --> ESCALATED
    TRIAGE --> DROPPED
    APPOINTMENT --> PRESCRIPTION
    APPOINTMENT --> PAYMENT_SENT
    APPOINTMENT --> COMPLETE
    APPOINTMENT --> ESCALATED
    APPOINTMENT --> DROPPED
    PRESCRIPTION --> PAYMENT_SENT
    PRESCRIPTION --> COMPLETE
    PRESCRIPTION --> ESCALATED
    PRESCRIPTION --> DROPPED
    PAYMENT_SENT --> COMPLETE
    PAYMENT_SENT --> PAYMENT_EXPIRED
    PAYMENT_SENT --> DROPPED
    PAYMENT_EXPIRED --> APPOINTMENT
    PAYMENT_EXPIRED --> ESCALATED
    PAYMENT_EXPIRED --> DROPPED
    COMPLETE --> [*]
    ESCALATED --> [*]
    DROPPED --> [*]
    note right of APPOINTMENT
        PATCH /api/calls/{call_id}/state returns 409 on invalid transition
        (calls router validates against STATE_TRANSITIONS - model is single source)
    end note
```

## Notes

- **Single source**: `backend/app/models/call.py` — `CallState` enum (9 states) +
  `STATE_TRANSITIONS` dict. `backend/tests/test_uml_diagrams.py` parses the dict
  via `ast` and asserts the mermaid edge set **equals** it, so this diagram cannot
  drift from the code.
- **Terminal states**: `COMPLETE`, `ESCALATED`, `DROPPED` have no outgoing
  transitions.
- **Payment loop (G6-Q5 wired)**: `PRESCRIPTION` and `APPOINTMENT` → `PAYMENT_SENT`
  → `PAYMENT_EXPIRED` → back to `APPOINTMENT`. Live gateway SDK calls are
  env-gated (501 without keys, spec-payments.md Q5/A5a); the unified webhook
  (`POST /api/payments/webhook`, per-gateway HMAC + service token, idempotent
  by `gateway_ref`) advances captured intents and moves the linked call
  `PAYMENT_SENT → COMPLETE`.
- **Escalation guardrails (G6-Q3 wired)**: independent of the LLM — a red-flag
  keyword in the caller's words (12-category catalog in
  `app/services/guardrails.py`) escalates deterministically (temperature≈0
  path, per-language handoff phrase), and every agent reply is scanned for
  diagnosis/dosage claims before TTS (fixed per-language refusal phrase).
- **API enforcement**: the calls router's `PATCH /{call_id}/state` rejects invalid
  transitions with 409 (covered by `test_api_routes.py`).