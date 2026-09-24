# spec-payments.md — Payment Flows & Gateway Wiring (g-payments)

| | |
|---|---|
| **Phase** | G6-Q5: decide the payment flows + gateway wiring (which flow pays / which gateway per flow) |
| **Branch** | `g-payments` (worktree `.worktrees\g-payments`, off g-enforce tip `0e1cb87`) |
| **Rule** | Test-first (RED → GREEN). Stdlib-only local verification; live gateway SDK calls gated behind env keys (501 without — same pattern as SSO/telephony) and proven by CI secrets. |
| **Status** | DRAFT — awaiting sign-off. No implementation before approval. |

## 1. Why this phase exists

G6-Q5 ("payment flows") has been **open since the G6 fix list** (2026-09-22). The
API-routes phase shipped a scaffold that records payment **intent only** (`POST
/api/payments` never calls a gateway SDK); every UML doc marks the payment leg as
"G6-Q5 gated". This phase answers the question and wires the integration layer
behind the established env-gating pattern, so the payments path is real on the
contract surface and only the live SDK round-trips stay behind CI secrets.

## 2. Current state (research, confirmed on-disk 2026-09-25)

| Surface | Truth today |
|---|---|
| Table `payments` | `id`, `clinic_id` FK CASCADE, `call_id` FK SET NULL, `appointment_id` FK SET NULL, `amount NUMERIC(10,2)`, `currency` DEFAULT INR, `gateway` (razorpay/phonepe/cashfree/manual), `gateway_ref`, `status` (pending/captured/failed/refunded), timestamps. Index `idx_payments_clinic_status`. |
| ORM | `class Payment(Base)` inline in `app/db/postgres.py` (line 482) — mirrors the table exactly. |
| CRUD | `create_payment` (intent: clinic/call/appointment/amount/currency/gateway/ref/status), `list_payments(clinic_id, status)`, `get_payment(id)`, `update_payment_status(id, status)`. |
| Router | `app/api/payments.py` — `GET /api/payments?clinic_id=`, `POST /api/payments` (intent, 201), `GET /{payment_id}`, `PATCH /{payment_id}/status` — all `Depends(get_current_user)` (enforcement phase), statuses validated against `PAYMENT_STATUSES`. |
| Call state machine | Loop already designed: `APPOINTMENT → PAYMENT_SENT`, `PRESCRIPTION → PAYMENT_SENT`, `PAYMENT_SENT → COMPLETE | PAYMENT_EXPIRED | DROPPED`, `PAYMENT_EXPIRED → APPOINTMENT | ESCALATED | DROPPED` (verified in `app/models/call.py` — NO model change needed). |
| Gateways (G5) | Pinned in `requirements.txt`: `razorpay==2.0.1`, `phonepe-pg-sdk-python==2.3.0`, `cashfree-pg==6.0.1`. **NOT installed** — this PC is stdlib-only (no pip); SDK imports must stay lazy/env-gated. |
| Locked acceptance (spec-micc-india) | Razorpay = payment links · PhonePe = UPI · Cashfree = subscriptions · webhook handlers for all three · reconciliation via idempotency keys + unified webhook handler. |
| RLS (enforcement) | `payments_manage` policy = `FOR ALL USING (clinic_id IN memberships)`; ALL tenant tables FORCE RLS; API connects as non-owner `medicall_app`. A **userless webhook update** to `payments` is thus deny-all right now. |
| Webhook trust pattern | `_verify_service_token` (`X-Service-Token` == `WEBHOOK_SERVICE_TOKEN`) + `service_request_ctx()` from the enforcement phase — reusable for payments webhooks. |

### Ripple findings to decide here

1. **Webhook writes need a service bypass on `payments`.** `update_payment_status`
   (and any refund/expiry write) from the verified webhook runs with `auth.uid() =
   NULL` → `payments_manage FOR ALL USING (clinic_id IN memberships)` blocks it
   (same class of gap as `calls_update` in the enforcement phase). Add
   `OR current_setting('app.service_request', true) = 'on'` to `payments_manage`
   + extend the enforcement RED test's service-clause contract to cover it.
2. **Webhooks are identity-less by nature** — the webhook route must NOT take
   `get_current_user`; it authenticates via per-gateway signature verification
   (see Q4) + the shared service token, then arms `service_request_ctx()`.
3. **No expiry mechanism exists.** `PAYMENT_SENT → PAYMENT_EXPIRED` is agent/API
   triggered today; gateways do not send expiry events. Add `expires_at` to the
   intent so the callee can decide/transition; an automated expiry sweep is a
   follow-up (needs a scheduler — Docker/CI territory).
4. **Idempotency needs a unique key.** Reconciliation (locked) requires gateway
   webhooks to be replay-safe: add a UNIQUE partial index on `gateway_ref` so a
   duplicate webhook updates the same row instead of creating a second one.
5. **`manual` gateway must keep working keyless** (offline/dev + Phase-1
   invoices) — the 501 env-gate applies to razorpay/phonepe/cashfree only.

## 3. Question to answer (G6-Q5) + options

Q5 asks **which flows pay and which gateway handles each flow**. Sign-off via the
question tool (questions mirror the options below; recommended = first option).

### Q1 — Which flows pay?
- **A1a (recommended)** — Consultations AND prescription refills can bill: on the
  `APPOINTMENT` and `PRESCRIPTION` paths the agent offers payment, the API creates
  the intent, and the payment link/UPI request goes to the caller's phone
  (voice-first — no card entry during the call). Matches the locked acceptance
  criteria + the `PAYMENT_SENT` edges already in the state machine.
- A1b — Consultations only (appointment bills; refills free in Phase 1).
- A1c — Nothing bills yet (status quo: intent records + manual invoices).
- A1d — Refills only (unusual; consult free).

### Q2 — Which gateway per flow?
- **A2a (recommended)** — As locked: **Razorpay = payment links** (consult +
  refill, delivered via SMS), **PhonePe = UPI** (instant in-call collect/intent),
  **Cashfree = subscriptions** (care plans / recurring). A `kind →
  gateway` dispatch + per-gateway fallback — mirrors the telephony decision
  (G6-Q6: all three wired, no single primary).
- A2b — Razorpay primary for everything; PhonePe/Cashfree env-gated follow-up.
- A2c — Per-clinic gateway choice (clinic setting picks the gateway).

### Q3 — When is payment triggered on a call?
- **A3a (recommended)** — In-call: agent asks consent, API creates intent +
  gateway request, call → `PAYMENT_SENT` while the caller pays on their phone;
  `captured` → call → `COMPLETE`; expiry → `PAYMENT_EXPIRED` → back to
  `APPOINTMENT` (the designed loop, verbatim).
- A3b — Post-call only: call completes first; the summary SMS carries the link
  (call never waits in `PAYMENT_SENT`).
- A3c — Both: in-call link for appointments, post-call link for refills.

### Q4 — Webhook trust + reconciliation?
- **A4a (recommended)** — Per-gateway verification in **stdlib** (Razorpay
  `X-Razorpay-Signature` HMAC-SHA256 of the body; PhonePe `X-VERIFY`
  base64(SHA256(...)); Cashfree HMAC-SHA256 signature header) **+** the shared
  `X-Service-Token`; a **unified** `POST /api/payments/webhook` dispatching on the
  payment's `gateway`; **idempotent by `gateway_ref`** (unique partial index);
  status transitions `pending → captured | failed`, `captured → refunded`; on
  `captured`, transition the linked call `PAYMENT_SENT → COMPLETE`.
- A4b — Shared `X-Service-Token` only for all three (per-gateway HMAC =
  follow-up, consistent with enforcement Q2's stance).
- A4c — Webhooks out of scope (status stays manual PATCH only).

### Q5 — Phase scope (live SDK calls now or gated)?
- **A5a (recommended)** — Build the stdlib gateway layer + endpoints + webhook
  verification NOW; live SDK requests fire only when the gateway's env keys are
  present (else 501, mirroring SSO/telephony); live round-trips behind CI
  secrets. Tests structural stdlib-only (HMAC vectors, builders, transitions).
- A5b — Full SDK integration now (requires pip on this PC — not possible;
  everything defers to Docker/CI).

## 4. Deliverables (A–H)

- **A. Sign-off** — Q1–Q5 locked in this spec (approved commit).
- **B. `app/services/payments.py`** (stdlib, unit-tested like telephony) —
  `PAYMENT_KINDS` (consultation/refill/subscription) + `kind → gateway` map;
  per-gateway request/link builders (razorpay link payload, phonepe UPI
  collect, cashfree order + subscription) returning the payload shape only
  (SDK calls lazy + env-gated); per-gateway webhook **signature verifiers** with
  test vectors; unified `reconcile_webhook` (gateway dispatch, idempotency key,
  status transition rules `pending→captured/failed`, `captured→refunded`).
- **C. Router (`app/api/payments.py`)** — keep the 4 guarded endpoints; `POST
  /api/payments` gains `kind`→gateway resolution + env-gated dispatch (501 when
  the gateway's keys are absent, except `manual`); new **`POST
  /api/payments/webhook`** (no `get_current_user`; verifies per-gateway
  signature + `X-Service-Token`; arms `service_request_ctx()`; idempotent
  upsert by `gateway_ref`; on `captured` transitions the linked call
  `PAYMENT_SENT → COMPLETE` via the existing state machine).
- **D. Schema + ORM** — `payments` += `kind` (consultation/refill/subscription),
  `expires_at` (intent TTL for the PAYMENT_EXPIRED leg), UNIQUE partial index on
  `gateway_ref`; `payments_manage` policy gains the `service_request` OR-clause
  (ripple 1); `Payment` model mirrors the columns. `STATE_TRANSITIONS` untouched
  (loop already correct).
- **E. Env** — `.env.example` + compose: `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET`,
  `PHONEPE_MERCHANT_ID`/`PHONEPE_KEY`/`PHONEPE_IV`,
  `CASHFREE_APP_ID`/`CASHFREE_SECRET`, `PAYMENT_LINK_BASE_URL`; keep
  `WEBHOOK_SERVICE_TOKEN`.
- **F. `smoke_api.py`** — payments: `manual` intent create (keyless) → list →
  detail → invalid status 422; webhook POST with `X-Service-Token` (and a
  signed Razorpay-style body) → status updated idempotently; razorpay intent
  without keys → 501.
- **G. `tests/test_payments_q5.py`** (RED → GREEN, stdlib) — service-layer
  contracts (kind→gateway map, builder shapes, HMAC verify vectors per gateway,
  transition rules), router contracts (webhook route + no-auth dependency +
  guards on the 4, 501 env-gating, manual keyless), schema (kind/expires_at/
  unique-partial gateway_ref/service clause on payments_manage in
  `postgres_schema.sql`), smoke flow markers ("webhook", "X-Service-Token",
  "gateway_ref", "501").
- **H. Docs** — `03-api-contracts.md` (+`POST /api/payments/webhook`,
  payments-billable note), `01-er.md` payments columns, `02-state-machine.md`
  payment loop note flips from "G6-Q5 open" to "wired", tracker + HANDOVER.

## 5. Verification plan

1. RED: `tests/test_payments_q5.py` — every assertion fails on g-enforce code
   (no service module, no webhook route, no kind/expires_at/unique-ref, no env
   vars, smoke lacks the new flow); baseline exit 1.
2. GREEN: new suite + **full regression (246 existing + N)** all PASS +
   `compileall` exit 0; frontend untouched (skip npm).
3. RLS/service-bypass structural proof via the extended enforcement suite
   (payments_manage clause); runtime = ci.yml stack job on a Docker host.
4. Live gateway round-trips stay gated on CI secrets (env keys on a Docker
   runner) — same as prior phases.

## 6. Commit sequence

spec → (sign-off) → RED → feat (A–H) → docs (DONE record, tracker, HANDOVER,
03-api-contracts). Branch `g-payments`; main tree stays clean.

---
### Status
- **2026-09-25 DRAFT** — research done (current surface, state-machine loop,
  RLS interplay, gateways pinned); awaiting Q1–Q5 sign-off. No implementation
  before approval.
- **2026-09-25 APPROVED** — sign-off via question tool: **Q1=A1a** consultations
  AND prescription refills bill (agent offers payment on APPOINTMENT +
  PRESCRIPTION; link/UPI request goes to the caller's phone), **Q2=A2a** locked
  kind→gateway map + fallback (razorpay=links for consultation+refill,
  phonepe=UPI instant, cashfree=subscriptions), **Q3=A3a** in-call trigger that
  waits in PAYMENT_SENT (captured → COMPLETE; expiry → PAYMENT_EXPIRED →
  APPOINTMENT), **Q4=A4a** per-gateway HMAC verification (Razorpay
  X-Razorpay-Signature, PhonePe X-VERIFY, Cashfree HMAC header) + shared
  X-Service-Token + unified `/api/payments/webhook` idempotent by gateway_ref,
  **Q5=A5a** stdlib gateway layer now, live SDK requests env-gated (501 without
  keys, manual stays keyless); live round-trips behind CI secrets. Test-first
  (RED → GREEN); runtime = ci.yml stack job on a Docker host.