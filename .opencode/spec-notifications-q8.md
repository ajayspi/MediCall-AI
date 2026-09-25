# G6-Q8 Notifications — spec (APPROVED → GREEN)

| | |
|---|---|
| **Phase** | G6-Q8: multi-channel messaging layer (WhatsApp-first) for the voice call center |
| **Tracker question** | "Notifications: SMS/WhatsApp/email/push provider per language; appointment reminders + no-show flow?" |
| **Branch** | `g-notify` off `g-guardrails` tip `c01bbac` |
| **Status** | APPROVED → **GREEN** (implemented 2026-09-25; regression 371/371, compileall 0) |
| **Date** | 2026-09-25 |

## 0. Sign-off record (2026-09-25, question tool)

- **Q1=A1c** — **WhatsApp-first**: Meta Cloud API is the PRIMARY channel
  (payment links, reminders, follow-ups, OTP all prefer WhatsApp), with SMS as
  the fallback chain (Knowlarity primary → MSG91), then email where a kind
  supports it. All channels env-gated: without keys the layer 501/queues, never
  crashes. Live dispatch waits for creds (CI/Docker host) — same discipline as
  the payments SDK gate.
- **Q2=A2c** — **full message catalog** across channels: `payment_link`
  (whatsapp→sms→email), `appointment_reminder` (whatsapp→sms→email),
  `no_show_followup` (whatsapp→sms), `otp` (whatsapp→sms), `payment_receipt`
  (email→whatsapp). Per-language templates (hi/en/ta/te/bn) for every kind that
  has a channel; push (FCM) ships as an env-gated kind stub for
  `appointment_reminder` (dispatch lazy/deferred — no patient app yet).
- **Q3=A3a** — env-gated stdlib request builders + `channel_env_ready` + lazy
  `dispatch_channel` (imports a provider client ONLY when its keys are set —
  never on this stdlib PC); `send_notification` walks the kind's default
  channel order using the first ready channel; non-fatal `no_provider` result
  (row still recorded `queued`). Manual `POST /api/notifications/send` 501s
  without keys; **upstream hooks (payment create) never fail or 501**.
- **Q4=A4a** — new `notifications` tenant table (id, clinic_id, kind,
  recipient, language, params JSONB, channel, provider, provider_ref, status
  ∈ {queued, sent, failed}, template, created_at, sent_at) + UNIQUE partial
  index on provider_ref + `notifications_send` RLS policy with the
  `app.service_request` bypass OR-clause (mirrors `payments_manage`); writes
  under `service_request_ctx()`. Rows feed the G6-Q2 DPDP audit.
- Test-first (RED → GREEN); stdlib-only; full regression must stay 319 baseline
  + new.

## 1. Why now (evidence from the current surface)

The payments phase (G6-Q5) **decided** payment links "go to the caller's phone
via SMS" (`.env.example`: `PAYMENT_LINK_BASE_URL` — "links go to the caller's
phone via SMS") — but **no messaging layer exists**. Verified by reading the
tree: no notifications/sms module in `app/services/`; `auth.py otp_request` is
"SMS provider gated — dev mode logs the code"; no notifications table/router;
`KNOWLARITY_*` env vars are telephony-call config, so SMS/WhatsApp keys need
their own namespace. Q8 answers the tracker question with an env-gated stdlib
layer mirroring the proven `payments.py`/`telephony.py` pattern — fully
verifiable on this PC (no live providers, no SDK installs).

## 2. Non-goals (hold the line)
- NO scheduled sweeps (T-24h reminder cron, no-show sweep) — they need a
  scheduler/Docker (same deferral as the payment-expiry sweep); messages are
  authored + endpoint-triggerable in this phase.
- NO change to `app/api/auth.py` — the `otp` kind + channel chain are
  catalog-complete; auth rewiring is a stated follow-on (auth 42-test suite
  stays untouched).
- NO new identity-free endpoints — no delivery-receipt webhook this phase;
  `IDENTITY_FREE_ENDPOINTS` is NOT extended. `POST /api/notifications/send`
  is identity-gated like every domain endpoint.
- NO live provider calls on this PC — every channel enforces the env gate;
  WhatsApp/Meta, SMS, FCM dispatch stay lazy (import client only on a keyed
  host). Email request-building (MIME) is stdlib and fully tested here; actual
  SMTP sending is env-gated.
- Push (FCM) is a kind stub: template + env keys + lazy dispatch shape only —
  real delivery needs a patient app (later phase).

## 3. Question to answer (G6-Q8) — signed off

- **Q1=A1c (WhatsApp-first)**: primary channel = Meta Cloud API
  (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`); fallback chain = SMS (Knowlarity →
  MSG91) → email (SMTP) per kind. Per-language templates for all 5 languages
  (hi/en/ta/te/bn). Channel env keys are canonical, single-source.
- **Q2=A2c (full catalog)**: kinds = `payment_link`, `appointment_reminder`,
  `no_show_followup`, `otp`, `payment_receipt` (+ push stub kind
  `appointment_reminder` on channel `push`). Each kind has a
  `DEFAULT_CHANNEL_ORDER` (see §0). Email carries a per-kind subject line.
- **Q3=A3a**: env-gated stdlib builders + lazy dispatch + 501 on the manual
  endpoint + non-fatal upstream hooks (exact payments Q5/A5a discipline).
- **Q4=A4a**: records + idempotency-by-provider_ref + service-write policy.

## 4. Deliverables

- **A. `backend/app/services/notifications.py`** (new, stdlib-only):
  `MESSAGE_TEMPLATES[kind][language]` (+ `MESSAGE_SUBJECTS[kind]` for email),
  `DEFAULT_CHANNEL_ORDER[kind]` (WhatsApp-first chains), `CHANNEL_PROVIDER_KEYS`
  (canonical env names: whatsapp/sms-knowlarity/sms-msg91/email/push-fcm),
  per-channel request builders (`build_whatsapp_text`, `build_sms_request`,
  `build_email_mime` — stdlib `email.mime`, `build_push_payload`),
  `channel_env_ready(channel, env=None)`, lazy `dispatch_channel(channel, kind,
  row, env=None)` (imports the provider client only on a keyed host — proves no
  third-party import at module level), `send_notification(kind, recipient,
  language, params, ...)` orchestration (template render → first-ready channel
  → result dict incl. channel/provider/status/reason). Docstring keeps the
  literal "G6-Q8".
- **B. `backend/app/api/notifications.py`** — router: `POST /send`
  (identity-gated `Depends(get_current_user)`, 501 without any channel keys,
  records under `service_request_ctx()`) + `GET /` list (identity-gated);
  registered in `main.py` (8th router).
- **C. `postgres_schema.sql`** — `notifications` table + `uq_notifications_provider_ref`
  partial unique index + `notifications_send` policy with the service
  OR-clause (mirror `payments_manage`). FORCE RLS for the new table rides with
  the ci.yml RLS/GUC runtime step (payments-not-FORCED precedent).
- **D. `backend/app/db/postgres.py`** — Notification ORM row +
  `create_notification` + `list_notifications` (mirror payment CRUD shape).
- **E. Payments hook** — `create_payment_ep`: for kind `link`/`upi`, after the
  payment row is written, call `send_notification("payment_link", ...)` wrapped
  non-fatally (never breaks the payment response / 501).
- **F. `.env.example` + compose backend env** — canonical channel keys:
  `WHATSAPP_TOKEN/PHONE_ID`, `KNOWLARITY_SMS_TOKEN/SENDER_ID`,
  `MSG91_AUTH_KEY/SENDER_ID/ROUTE`, `SMTP_HOST/PORT/USER/PASSWORD/FROM`,
  `FCM_SERVER_KEY/SENDER_ID`.
- **G. `backend/tests/test_notifications_q8.py`** — RED first (~45 tests):
  structure (module/table/policy/router/ORM/hook) + templates (kind × language
  coverage + fixed values) + channel env gates + lazy dispatch + fallback-chain
  orchestration (synthetic env: whatsapp-only → whatsapp; sms-only → sms; none →
  queued) + email MIME build + payments hook + auth-untouched + smoke/docs refs.
  Also `test_api_routes.py` EXPECTED_ENDPOINTS += notifications routes; the
  enforcement suite picks up the identity-gated router automatically.
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
- Env names are canonical-first (payments gotcha): chat/SMS keys are distinct
  from the telephony `KNOWLARITY_API_KEY/AUTHORIZATION/SIP_URI`.
- Only stdlib at module level — any third-party client (httpx/Meta SDK/FCM)
  must live behind `dispatch_channel`'s lazy import; `compileall` lint gate;
  `py -3.14`.
- Identity-gated endpoints only — no `IDENTITY_FREE_ENDPOINTS` extension.
- Full regression baseline 319 must hold + new tests.

## 7. Implementation record (GREEN, 2026-09-25)

- **RED commit `791a942` (52 tests, 21 FAIL + 30 ERROR + exit 1)**: new
  `tests/test_notifications_q8.py` (module structure, 5-kind × 5-language
  templates + fixed EN vectors, WhatsApp-first chains, env gates, lazy
  dispatch, fallback orchestration with injectable dispatch, email MIME,
  schema table + policy, ORM helpers, router structure + identity gate,
  payments hook, auth-untouched, smoke/docs refs) + `test_api_routes`
  ROUTER_MODULES/EXPECTED_ENDPOINTS/8-router set + enforcement ROUTER_MODULES.
  Latent bugs caught before GREEN: `and`-chained asserts short-circuit (None
  is falsy → the second assert never ran); first-pass `fn_block` sliced text
  by line numbers as character offsets (fixed to the established
  splitlines(keepends=True) helper — the RED suite is code too).
- **feat commit `9bfa49c` (371/371 ALL PASS, compileall 0)**: `app/services/
  notifications.py` (catalog + templates + env gates + lazy dispatch +
  orchestration; module-level imports stdlib-only), `app/schemas/
  notification.py`, `app/api/notifications.py` (GET "" + POST /send — 501
  no-channel gate, records rows Q4=A4a), `postgres_schema.sql`
  (`notifications` table + `uq_notifications_provider_ref` partial unique +
  `notifications_send` policy with the `app.service_request` OR-clause +
  grants), `postgres.py` (`Notification` ORM + `create_notification` +
  `list_notifications`), `main.py` 8th router, `.env.example` + compose
  channel keys, `payments.py` `_send_notification_payment_link` hook for
  kind link/upi (non-fatal, never 501s), `smoke_api.py` 501 check,
  `docs/uml/03-api-contracts.md` `/api/notifications`.
- **docs commit (tip; count not moved)**: 03-api-contracts Notes + mermaid node
  (in feat — executable contract), 01-er 11th table, 00-index, HANDOVER Q8
  DONE, tracker record, spec status GREEN.
- **Structure gotcha honored**: notifications router endpoints take
  `user=Depends(get_current_user)` (untyped form); no `IDENTITY_FREE_ENDPOINTS`
  extension; SMS env keys distinct from telephony `KNOWLARITY_*`; G1–G7 locks
  untouched.