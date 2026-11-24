# MediCall AI — UML Diagrams

Architecture diagrams for the Indian voice-first medical call center. All diagrams
are Mermaid source rendered natively by GitHub / VS Code / typora (no toolchain).
Verified by `backend/tests/test_uml_diagrams.py` (stdlib, source-level).

| # | Diagram | File | Single source of truth |
|---|---------|------|------------------------|
| 01 | Entity–Relationship (9 tables, FK edges) | [01-er.md](01-er.md) | `backend/postgres_schema.sql` |
| 02 | Call state machine (9 states, 22 transitions) | [02-state-machine.md](02-state-machine.md) | `backend/app/models/call.py` (`CallState` + `STATE_TRANSITIONS`) |
| 03 | API contracts (11 routers, 53 endpoints) | [03-api-contracts.md](03-api-contracts.md) | `backend/app/api/*.py` + `backend/tests/test_api_routes.py` |
| 04 | Voice pipeline data flow | [04-data-flow.md](04-data-flow.md) | `backend/app/api/voice.py` + `backend/app/services/` |
| 05 | Deployment (Docker Compose stack + SaaS) | [05-deployment.md](05-deployment.md) | `docker-compose.yml` |
| 06 | Inbound call lifecycle (sequence) | [06-call-lifecycle.md](06-call-lifecycle.md) | `backend/app/api/voice.py` + `backend/app/models/call.py` |
| 07 | Use cases (actors + goals) | [07-use-cases.md](07-use-cases.md) | `backend/postgres_schema.sql` roles + `backend/app/services/guardrails.py` |
| 08 | Class diagram (domain + DTOs) | [08-class-diagram.md](08-class-diagram.md) | `backend/app/models/call.py` + `backend/app/schemas/` |

## Why these six

- **01 ER** — multi-tenant `clinic_id` spine (the locked tenancy model), the Phase-1
  transcript-only EHR shape, and the API-phase `payments` + `notifications` tables.
- **02 state machine** — the product's core differentiator; the test asserts the
  mermaid edge set **equals** `STATE_TRANSITIONS` parsed from `models/call.py`, so
  the diagram cannot drift from the code.
- **03 API contracts** — executable contract for the Docker/CI smoke tests.
- **04 data flow** — telephony → webhook → LiveKit agent → STT/TTS → postgres,
  with the `/call-completed` DB write marked as Docker/CI-owned.
- **05 deployment** — the Docker Compose stack the next phase actually runs.
- **06 call lifecycle** — one inbound call end-to-end, including the
  `PAYMENT_SENT` / `PAYMENT_EXPIRED` loop (G6-Q5 payments wired
  spec-payments.md: env-gated gateway dispatch + verified webhooks).