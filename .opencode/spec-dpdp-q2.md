# G6-Q2 Consent + DPDP — spec (DRAFT)

| | |
|---|---|
| **Phase** | G6-Q2: consent & DPDP Act 2023 layer — per-call recording consent flag, retention policy, 72-hr breach flow, data-localization/DPO posture |
| **Tracker question** | "Consent & DPDP Act 2023: per-call recording consent flag, data localization, 72-hr breach flow, retention policy?" |
| **Branch** | `g-dpdp` off `g-languages` tip `af63e3c` |
| **Status** | **DRAFT** — awaiting question-tool sign-off |
| **Date** | 2026-09-25 |

## 0. Sign-off record (pending)

- Q1=—, Q2=—, Q3=—, Q4=— (question tool, 2026-09-25)
- Test-first (RED → GREEN); stdlib-only; full regression must stay 426 baseline + new.

## 1. Why now (evidence from the current surface)

The DPDP hooks are *named* everywhere but *built* nowhere, verified by reading the tree:

1. **There is no per-call recording-consent flag anywhere.** The `calls` table
   (`postgres_schema.sql:59-79`) has no consent column (state/transcript/
   stt_confidence/triage_severity/… only); the `Call` ORM (`postgres.py:260-313`)
   and the `Call` dataclass (`models/call.py:74-86`) have no consent field;
   `call_row` (`api/calls.py:26-45`) serializes no consent. Yet the board
   (`spec-multifit-healthcare.md:79`) commits to "Call Recording: Optional via
   LiveKit egress, stored in MinIO/S3, **with DPDP consent flag per-call**."
   The LiveKit egress gate ("record only when the caller consented") has no
   input to read. Grep across `tests/` for `consent|retention|breach|DPDP` =
   0 contract matches (one unrelated `recording_url`).
2. **The DPDP audit trail exists but has no consumers.** Q8 built
   `notifications` rows explicitly "as the DPDP audit trail (G6-Q2)"
   (`postgres.py:1029` comment, `postgres_schema.sql:172`, `api/notifications.py:8`).
   Nothing reads them for retention/breach/erasure decisions.
3. **No retention policy exists.** Nothing computes or enforces how long calls/
   recordings/notifications/audit rows live. The board says audit logs are
   "retained 6yr per DPDP/HIPAA-equivalent" (`spec-multifit-healthcare.md:195`)
   and breach notification is "72hr" (`:161,:193`) — both are unbuilt.
4. **No breach/compliance event record exists.** There is no table, endpoint,
   or service for recording a data breach, its 72-hr notification deadline, or
   the DPB-report status. The "designated DPO + data localization"
   (`:193`) posture has no config surface either.

Q2 answers the tracker question with a stdlib service layer + one new tenant
table + `.env` config — fully verifiable on this PC (no Docker, no live
provider), mirroring the Q3/Q8/Q4 discipline. Recordings themselves (LiveKit
egress → MinIO/S3) and actual DPB notification dispatch are deferred to
Docker/CI + the Q10 deploy session.

## 2. Non-goals (hold the line)

- **No recordings pipeline**: no LiveKit egress, no MinIO/S3, no recording
  storage/playback. This phase builds the *consent gate + audit record* that
  the egress step will read.
- **No actual 72-hr dispatch**: notifying the Data Protection Board / affected
  users is operational (SLA/email/telecom). The phase builds the *event record +
  computed deadline + status lifecycle*; the Q8 email channel is a noted
  follow-on (no new notification kind, catalog untouched).
- **No GDPR-style erasure requests (data subject rights)**: a `gdpr_request`
  event *type* is recorded, but a full right-to-erasure flow (cascade wipe +
  evidence bundle) is out of scope.
- **No scheduler**: `purge_expired` is built and wired for the Docker/CI cron
  (same deferral as the Q8 sweeps) — nothing auto-runs on this PC.
- **No auth/enforcement changes**: `auth.py`, `IDENTITY_FREE_ENDPOINTS`, RLS
  FORCE + GUC pattern untouched. New table's policy mirrors `notifications_send`.
- **No Q10 work**: the actual data-residency region choice (docker-compose pin,
  provider region, zero-retention BAAs) belongs to the Q10 deploy session; Q2
  only surfaces the documented config constants.

## 3. Pins (must not break)

- The 426-test baseline (incl. G4 voice pins, Q8 notifications catalog,
  Q4 languages single-source). Consent/retention/compliance modules import
  `SUPPORTED_LANGUAGES` from `app.services.languages` (no new tuple copies).
- `calls` RLS policies (`calls_create/read/update`) unchanged; the consent
  write rides `calls_update` (membership OR `app.service_request`).
- The 5-language exact set; TTS voice keys; greeting templates — untouched.
- Notifications `CHANNELS/KINDS/DEFAULT_CHANNEL_ORDER` catalog untouched.
- stdlib-only import gate for the three new service modules (consent.py,
  retention.py, compliance.py — leaf modules, `os`/`datetime`/`typing` only).

## 4. Decision options (question tool, 2026-09-25)

**Q1 — Per-call recording consent (how is consent captured/stored?)**
- **A1 (rec.)**: `calls.recording_consent TEXT NOT NULL DEFAULT 'unknown'`
  (unknown/granted/denied) + stdlib `app/services/consent.py` with 5-language
  yes/no capture (`parse_consent_response(text, language)` → granted/denied/
  None) + `recording_allowed(consent)` egress gate + identity-gated
  `POST /api/calls/{id}/consent` (staff/post-hoc + the in-call service path).
  No new table; consent rides the calls RLS.
- **A2**: dedicated `consents` table (call_id, phone, consent_type, status,
  source, recorded_at, revoked_at) — full lifecycle rows; the egress gate
  reads the latest row.
- **A3**: flag (A1) + a `consent_withdrawal` row in `compliance_events` when
  consent is revoked (audited trail).

**Q2 — Retention policy (how long does data live?)**
- **A1 (rec.)**: stdlib `app/services/retention.py` — `RETENTION_DAYS` map
  (calls 365, recordings 365, notifications 180, audit 2190 = 6 yr) with
  per-kind env overrides (`RETENTION_CALLS_DAYS` etc.), `retention_days(kind)`,
  `retention_deadline(created_at, kind)` (tz-aware) + `purge_expired(kind)`
  DELETE service in `postgres.py`, **wired for the Docker/CI scheduler**
  (execution deferred). Recordings = external MinIO objects → documented
  posture + env constant only (egress gating deferred with Q1/recordings).
  Compliance events = audit (6 yr).
- **A2**: constants + docs only, no purge code.
- **A3**: per-entity purge + FK cascade + compliance_event "closed by purge"
  rows (heavier audit).

**Q3 — 72-hr breach flow (what is recorded?)**
- **A1 (rec.)**: new `compliance_events` tenant table (id, clinic_id, type,
  severity, description, status, detected_at, notification_deadline,
  reported_at, created_at, updated_at) + ORM + RLS policy
  (`compliance_manage`, membership OR service_request — mirrors
  `notifications_send`) + identity-gated `app/api/compliance.py`
  (POST create 201 / GET list / PATCH status; 9th router) + stdlib
  `app/services/compliance.py`: `breach_notification_deadline(detected_at)`
  = detected + `DPDP_BREACH_NOTIFICATION_HOURS` (default 72), statuses
  open/reported/closed (→ reported sets reported_at), types data_breach /
  consent_withdrawal / gdpr_request.
- **A2**: runbook doc only (no table).
- **A3**: incident workflow (assignees/evidence/attachments) — overkill for MVP.

**Q4 — Data localization + DPO (posture surface)**
- **A1 (rec.)**: `DATA_RESIDENCY_REGION` env (default `"in"`) + `DPO_NAME`/
  `DPO_EMAIL` env, surfaced by stdlib `compliance.py` (`data_residency()`,
  `dpo_contact()`); posture documented in spec + HANDOVER. No infra change —
  the region pin is Q10's job.
- **A2**: doc-only note pointing to Q10 (no config surface).
- **A3**: skip entirely this phase.

## 5. Deliverables

- **A. `app/services/consent.py`** (stdlib, leaf): `RECORDING_CONSENT_STATES`,
  5-language `CONSENT_YES`/`CONSENT_NO` word lists (mirrors Q4 catalog pattern;
  imports `SUPPORTED_LANGUAGES` from `app.services.languages`),
  `parse_consent_response(text, language)` → `"granted"|"denied"|None`,
  `recording_allowed(consent)` → bool (granted only).
- **B. Calls consent surface**: `postgres_schema.sql` `calls.recording_consent
  TEXT NOT NULL DEFAULT 'unknown'` (+comment); `Call` ORM column +
  `create_call` default; `call_row` serialization (`api/calls.py`);
  `update_call_consent(call_id, consent)` in `postgres.py`;
  `POST /api/calls/{call_id}/consent` (identity-gated; 422 invalid consent).
- **C. `app/services/retention.py`** (stdlib): `RETENTION_DAYS` map,
  `RETENTION_ENV_KEYS`, `retention_days(kind, env)`, `retention_deadline(
  created_at, kind, env, now=None)` (timezone-aware), `retention_categories()`.
- **D. `purge_expired(kind, env, now=None)`** in `postgres.py`: DELETE from
  `calls` (FK-cascades call_embeddings), `notifications`, `compliance_events`
  where `created_at < deadline`; returns deleted count; documented as the
  Docker/CI cron function (never auto-runs on this PC).
- **E. `compliance_events` table**: schema DDL + `idx_compliance_clinic_status`
  + `compliance_manage` policy + GRANTs (authenticated + medicall_app);
  ORM `ComplianceEvent` + `create_compliance_event` (computes deadline via the
  service helper) / `list_compliance_events(clinic_id, status)` /
  `update_compliance_event(call: status|severity, reported_at on →reported)`.
- **F. `app/services/compliance.py`** (stdlib): `COMPLIANCE_EVENT_TYPES`,
  `SEVERITIES`, `STATUSES`, `DPDP_BREACH_NOTIFICATION_HOURS` (default 72, env
  override), `breach_notification_deadline(detected_at, env)`,
  `data_residency(env)`, `dpo_contact(env)`.
- **G. `app/api/compliance.py`** (9th router, prefix `/api/compliance`,
  identity-gated via `get_current_user`): POST `/events` (201; 422 unknown
  type/severity; stores computed deadline), GET `/events?clinic_id=&status=`,
  PATCH `/events/{id}` (status/severity); wired in `main.py`.
- **H. `.env.example`**: `RETENTION_CALLS_DAYS=365`,
  `RETENTION_RECORDINGS_DAYS=365`, `RETENTION_NOTIFICATIONS_DAYS=180`,
  `RETENTION_AUDIT_DAYS=2190`, `DPDP_BREACH_NOTIFICATION_HOURS=72`,
  `DATA_RESIDENCY_REGION=in`, `DPO_NAME=`, `DPO_EMAIL=` (documented block).
- **I. `tests/test_dpdp_q2.py`** (~50 tests, 8-9 classes, Q8-suite helpers):
  behavioral for consent.py (5-language parse, gate, unknown handling) /
  retention.py (map, env overrides, tz-aware deadline math) / compliance.py
  (72-hr deadline, env override, defaults, validation); stdlib-only import
  gates; schema source checks (calls column + compliance table + policy +
  grants + index); ORM/router source checks (Call.recording_consent,
  ComplianceEvent, calls.py consent route + call_row field, main.py compliance
  import, Depends(get_current_user) identity gate); `.env.example` coverage.
- **J. Docs**: tracker record + gotchas + open-list (Q9/Q10 remain) + Next
  line; HANDOVER Q2 DONE + section-4 refresh + spec index; spec GREEN +
  implementation record; `docs/uml/01-er.md` (calls column +
  `compliance_events`) + `docs/uml/03-api-contracts.md` (consent + compliance
  routes). `02/04/05/06` untouched.

## 6. Verification plan

1. **RED**: write `tests/test_dpdp_q2.py`; run
   `py -3.14 -m unittest discover -s tests -p "test_dpdp_q2.py"` → failures
   (no consent/retention/compliance modules, no column/table, no router) →
   commit RED.
2. **FEAT**: implement A–H; new suite GREEN; full regression
   (`py -3.14 -m unittest discover -s tests`) = **426 + new ALL PASS**;
   `py -3.14 -m compileall -q app scripts tests main.py` exit 0 → commit feat.
3. **DOCS**: J; re-run full suite — count must not move → commit docs.
4. Commits: spec (DRAFT→APPROVED) → RED → feat → docs; worktree `g-dpdp`
   stays clean at tip.

## 7. Implementation record (pending)

- RED commit: —
- feat commit: —
- docs commit: —