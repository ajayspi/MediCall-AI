# G6-Q8 Notifications — spec (DRAFT)

| | |
|---|---|
| **Phase** | G6-Q8: SMS/WhatsApp/email messaging layer for the voice call center |
| **Tracker question** | "Notifications: SMS/WhatsApp/email/push provider per language; appointment reminders + no-show flow?" |
| **Branch** | `g-notify` off `g-guardrails` tip `c01bbac` |
| **Status** | DRAFT — pending sign-off (Q1–Q4 below) |
| **Date** | 2026-09-25 |

## 1. Why now (evidence from the current surface)

The payments phase (G6-Q5) **decided** that payment links "go to the caller's
phone via SMS" (`backend/.env.example` line 79–82: `PAYMENT_LINK_BASE_URL` —
"links go to the caller's phone via SMS") — but **no messaging layer exists to
deliver them**. Verified by reading the tree:

| Piece | Current state | Q8 gap |
|---|---|---|
| SMS provider | None — no `notifications.py`/`sms.py` in `app/services/` | The whole messaging layer is missing |
| Payment link delivery | `create_payment_ep` builds + 501-gates the gateway dispatch; nothing sends the URL to the phone | The Q5 required leg — link/UPI intent has no delivery channel |
| Appointment reminders / no-show | No reminder or follow-up flow anywhere | Q8's named triggers don't exist |
| OTP delivery | `auth.py otp_request` is "SMS provider gated — dev mode logs the code" | The layer auth will use (rewiring deferred, auth suite untouched this phase) |
| Records / audit | No notifications table; DPDP audit (G6-Q2) has nothing to read | Notification rows with delivery status, kept for the later consent/retention phase |
| Provider keys | `KNOWLARITY_*` env vars exist but are **telephony-call** config (call API) | SMS needs its own canonical env namespace |

Q8 answers the tracker question with an env-gated stdlib layer that mirrors the
proven `payments.py`/`telephony.py` pattern, so it is fully verifiable on this
PC (no live SMS, no SDK installs).

## 2. Non-goals (hold the line)
- NO WhatsApp / email / push in this phase — WhatsApp Business API verification,
  SMTP creds, and push infra are out of MVP (deferred; catalog stays SMS-shaped).
- NO scheduled sweeps (T-24h reminder cron, expiry sweep) — they need a
  scheduler/Docker (same deferral as the payment-expiry sweep). The messages are
  authored + endpoint-triggerable; auto-scheduling lands with the ci.yml stack.
- NO change to `app/api/auth.py` — the OTP template exists in the catalog but
  auth rewiring is a stated follow-on (auth's 42-test suite stays untouched).
- NO new identity-free endpoints — no delivery-receipt webhook this phase, so
  `IDENTITY_FREE_ENDPOINTS` is NOT extended. `POST /api/notifications/send` is
  identity-gated like every domain endpoint.

## 3. Question to answer (G6-Q8) + options

### Q1 — Channel + provider set at MVP
- **A1a (recommended)** — **SMS-first, dual-provider fallback chain**:
  Knowlarity SMS primary + MSG91 SMS fallback (both India gateways; Knowlarity
  endpoints already verified 2026-09-24 in `knowlarity.py`; MSG91 is the classic
  India OTP/transactional SMS gateway). Mirrors the 3-telephony fallback chain
  (spec-micc-india). **Per-language message templates** for all 5 languages
  (hi/en/ta/te/bn) per kind. WhatsApp/email/push explicitly OUT.
- A1b — Single provider, no fallback. Accepted risk: one provider outage = silent
  missed payment links / reminders.
- A1c — WhatsApp-first. Needs Business API verification + Meta creds — blocks on
  external onboarding.

### Q2 — Which message kinds ship at MVP (the catalog)
- **A2a (recommended)** — **four kinds in the catalog**:
  1. `payment_link` — fires when a payment intent is created with kind
     `link`/`upi` (the Q5 REQUIRED leg; built from the payment record + URL at
     `PAYMENT_LINK_BASE_URL`);
  2. `appointment_reminder` — T-24h reminder text (authored now; the scheduled
     sweep is Docker/CI);
  3. `no_show_followup` — post-window "we missed you" text (authored; trigger
     endpoint + sweep deferred);
  4. `otp` — verification-code template (catalog-complete for auth to use as a
     stated follow-on; auth.py NOT rewired this phase).
- A2b — payment_link + reminders only (no otp template).
- A2c — full catalog incl. WhatsApp/email/push kinds. Larger, blocked on
  providers.

### Q3 — Delivery architecture (mirror payments Q5/A5a)
- **A3a (recommended)** — **env-gated stdlib request builders + 501 gate + lazy
  SDK dispatch**, exactly like `dispatch_gateway_request`: `notifications.py`
  holds templates + per-provider request SHAPES + `sms_env_ready(provider)` +
  lazy `dispatch_sms(provider, ...)` that only imports a provider client when
  that provider's keys are set (never runs on this stdlib PC). `send_notification`
  picks the first ready provider (fallback chain), non-fatal when no keys are
  set (returns a `no_provider` result — the row is still recorded as `queued`).
  The manual `POST /api/notifications/send` endpoint 501s without keys;
  **upstream hooks (payment create) never 501** — delivery is a recorded
  side-effect that can't break the payment response.
- A3b — eager SDK imports. Breaks this PC (no packages), violates stdlib-only.

### Q4 — Records, idempotency, failure
- **A4a (recommended)** — **notifications table + delivery status +
  service-write policy**: new tenant table `notifications` (id, clinic_id,
  kind, recipient_phone, language, params JSONB, channel, provider,
  provider_ref, status ∈ {queued, sent, failed}, template, created_at,
  sent_at) with UNIQUE partial index on `provider_ref` and a
  `notifications_send` RLS policy carrying the `app.service_request` bypass
  OR-clause (mirrors `payments_manage`; writes happen under
  `service_request_ctx()`). Rows feed the G6-Q2 DPDP audit later. Fallback:
  first provider fail → next provider; final status recorded.
- A4b — fire-and-forget, no table. No audit trail, no retryability, fails the
  DPDP story.

## 4. Deliverables
- **A. `backend/app/services/notifications.py`** (new, stdlib-only):
  `MESSAGE_TEMPLATES` (4 kinds × 5 languages), `SMS_PROVIDER_KEYS` (canonical
  env names — single source for the 501 gate + tests/compose),
  `build_sms_request(provider, message, phone)` request shapes,
  `sms_env_ready(provider, env=None)`, lazy `dispatch_sms(provider, ...)`,
  `send_notification(kind, recipient_phone, language, params, ...)` orchestration
  (template render → fallback chain → result dict incl. `no_provider`). Docstring
  keeps the literal "G6-Q8".
- **B. `backend/app/api/notifications.py`** — router: `POST /send` (identity-gated
  `Depends(get_current_user)`, 501 without provider keys, records under
  `service_request_ctx()`) + `GET /` list (identity-gated); registered in
  `main.py` (8th router).
- **C. `postgres_schema.sql`** — `notifications` table + `uq_notifications_provider_ref`
  partial unique index + `notifications_send` policy with service OR-clause
  (mirror `payments_manage`). FORCE RLS for the new table rides with the ci.yml
  RLS/GUC runtime step (payments-not-FORCED precedent).
- **D. `backend/app/db/postgres.py`** — Notification ORM row + `create_notification`
  + `list_notifications` (mirror payment CRUD shape).
- **E. Payments hook** — `create_payment_ep`: for kind `link`/`upi`, after the
  payment row is written, call `send_notification("payment_link", ...)` wrapped
  non-fatally (never breaks the payment response / 501).
- **F. `.env.example` + compose backend env** — canonical SMS keys
  (`KNOWLARITY_SMS_TOKEN`, `KNOWLARITY_SMS_SENDER_ID`, `MSG91_AUTH_KEY`,
  `MSG91_SENDER_ID`, `MSG91_ROUTE`).
- **G. `backend/tests/test_notifications_q8.py`** — RED first (~40 tests):
  structure + templates (4×5) + env gate + lazy dispatch + send orchestration +
  table/policy/ORM + router/enforcement + payments hook + auth-untouched +
  smoke/docs refs. Also: `test_api_routes.py` EXPECTED_ENDPOINTS += notifications
  routes; enforcement suite picks up the identity-gated router automatically.
- **H. Docs** — 03-api-contracts (`/api/notifications`), 01-er (11th table),
  00-index, HANDOVER DONE, tracker record, spec status GREEN.

## 5. Verification plan
1. **RED**: commit `test_notifications_q8.py` + test_api_routes/enforcement
   edits on the scaffold; run `discover -s tests -p "test_notifications_q8.py"`
   → expected failures (no module/table/router/hook), exit 1.
2. **GREEN**: implement A–F; new suite OK; full regression → **319 + new** ALL
   PASS; `compileall -q app scripts tests` exit 0.
3. **Docs**: commit H; re-run full suite — docs-only commit must not move the
   count.

## 6. Ripple / constraints (do-not-break)
- `auth.py` untouched (42 auth tests pinned); `payment_link` delivery can never
  501 or fail a payment create.
- Env names are canonical-first (payments gotcha): SMS keys are new, distinct
  from the telephony `KNOWLARITY_API_KEY/AUTHORIZATION/SIP_URI`.
- Only stdlib (`re`, `urllib`/`httpx` deferred to lazy dispatch); `compileall`
  lint gate; `py -3.14`.
- Identity-gated endpoints only — **no** `IDENTITY_FREE_ENDPOINTS` extension.
- Full regression baseline 319 must hold + new tests.