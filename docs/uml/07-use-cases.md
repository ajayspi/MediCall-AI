# 07 — Use Cases

```mermaid
flowchart LR
    Caller((Caller /<br/>Patient)) --> UC_Triage[Get triage]
    Caller --> UC_Book[Book appointment]
    Caller --> UC_Refill[Request prescription refill]
    Caller --> UC_Pay[Process payment]
    Caller --> UC_Escalate[Escalate to human]

    Staff((Clinic staff)) --> UC_View[View call / queue]
    Staff --> UC_Confirm[Confirm appointment]

    Doctor((Doctor)) --> UC_Review[Review triage]
    Doctor --> UC_Approve[Approve prescription]

    Admin((Admin)) --> UC_Manage[Manage clinics / users]
    Admin --> UC_Compliance[Compliance & audit]

    UC_Triage --> UC_Escalate
    UC_Book --> UC_Pay
    UC_Refill --> UC_Pay
    UC_Pay --> UC_Confirm
    UC_Refill --> UC_Approve
```

## Notes

- **Actors** map to the RLS roles in `backend/postgres_schema.sql` (`clinic_users.role`:
  `owner / staff / triage_agent / doctor / readonly`) plus the anonymous
  `Caller/Patient` who reaches the system over the phone.
- **Primary actor** is the caller: `get triage` is the entry use case, `escalate`
  is included by it (guardrails in `app/services/guardrails.py` escalate on a
  red-flag keyword independent of the LLM).
- **`process payment`** is included by both `book appointment` and
  `request prescription refill` (G6-Q5 payments; the `PAYMENT_SENT` /
  `PAYMENT_EXPIRED` loop lives in the state machine, see 02-state-machine.md).
- **Doctor/Staff** use cases are the human-in-the-loop halves (confirm /
  approve) that resolve the state machine out of `APPOINTMENT` / `PRESCRIPTION`.
- **Admin** use cases (`manage clinics/users`, `compliance & audit`) are the
  multi-tenant operations over `/api/admin` and `/api/compliance`.
