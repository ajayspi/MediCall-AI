# 08 — Class Diagram

```mermaid
classDiagram
    class CallState {
        <<enumeration>>
        GREETING
        TRIAGE
        APPOINTMENT
        PRESCRIPTION
        COMPLETE
        ESCALATED
        DROPPED
        PAYMENT_SENT
        PAYMENT_EXPIRED
    }

    class TriageSeverity {
        <<enumeration>>
        GREEN
        AMBER
        RED
        CRITICAL
    }

    class Call {
        +str id
        +str clinic_id
        +str caller_number
        +CallState state
        +datetime started_at
        +str caller_language
        +datetime ended_at
        +List transcript
        +float stt_confidence
        +str triage_severity
        +bool escalated_to_human
        +can_transition(new_state) bool
        +transition(new_state) bool
    }

    class CallStateUpdate {
        +str state
    }

    class ConsentUpdate {
        +str consent
    }

    class ClinicCreate {
        +str name
        +str phone_number
        +str city
        +str state
        +str address
        +str plan
        +bool is_active
    }

    class PaymentCreate {
        +str clinic_id
        +str call_id
        +str appointment_id
        +float amount
        +str currency
        +str gateway
        +str kind
    }

    Call --> CallState : state
    Call --> TriageSeverity : triage_severity
    CallStateUpdate --> CallState : validates against
    PaymentCreate ..> Call : call_id
```

## Notes

- **Single source**: `backend/app/models/call.py` holds `CallState`, `TriageSeverity`,
  `STATE_TRANSITIONS`, and the `Call` dataclass. Request models live in
  `backend/app/schemas/` (Pydantic `BaseModel`); the router validates membership
  in `CallState` and `STATE_TRANSITIONS` (409 on invalid transition, see
  02-state-machine.md).
- **`Call` is a plain `@dataclass`** (stdlib, importable anywhere incl. the DB
  layer and agent workers), not an ORM model — persistence is SQLAlchemy in
  `backend/app/db/postgres.py`.
- **Enums are `str, Enum`**: `CallState` values are the uppercase wire names;
  `TriageSeverity` values are lowercase (`green / amber / red / critical`).
- **Request schemas are anemic DTOs** — they carry only what the client sends;
  the full row shape lives in `backend/postgres_schema.sql` (see 01-er.md).
