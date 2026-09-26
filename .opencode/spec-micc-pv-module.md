# SPEC: Pharmacovigilance / MICC Module (MediCall-AI, Phase 1)

**Supersedes / extends**: nothing. `spec-micc-india.md` covers the *clinical* call center; this is the
new pharmacovigilance layer on top of it.
**Research base**: `.opencode/research-micc-process.md` (global + India, fully sourced).

## Goal

Turn MediCall-AI's voice intake into a compliant **pharmacovigilance (PV) collector** for an Indian
MAH / licensed clinic acting for one. Phase 1 delivers the data model + deterministic compliance
logic so that **adverse events (AE), product quality complaints (PQC) and medical information (MI)
enquiries identified on calls can be recorded, triaged, clocked and exported** — nothing more.
The call centre is a *collector, never an assessor*: no causality judgement, no diagnosis, no
medical advice; source data hands off to PV within the SLA.

Phase 1 ships four stdlib-only service functions + four new data tables (`products`,
`adverse_events`, `quality_complaints`, `medical_inquiries`) + one export surface in three formats
(JSON / CSV / print view), matching the established MediCall pattern (guardrails / telephony /
agent_logic are all class-free, stdlib-only modules). **Zero new PyPI deps** — the parked
livekit/openai resolver is untouched.

## Non-Goals (Phase 1)

- **No regulator submission.** Export only; E2B(R3) XML generation + gateway push (PvPI/NCC,
  EudraVigilance, FDA ESG) is Phase 2 and needs MAH gateway credentials + a validated system.
- **No clinical-trial SAE reporting** (NDCT Rules 2019, 14-day, Third Schedule Table 5) — post-marketing
  ICSR collector only.
- **No causality / expectedness judgement by the system.** WHO-UMC causality + MedDRA coding are
  Phase 2 (MedDRA is a licensed dictionary); Phase 1 captures reporter's causality verbatim only.
- **No MI approved-content knowledge base / standard responses** (Phase 2). Phase 1 logs MI enquiries.
- **No in-call voice-agent intents** (livekit system_prompt changes). Phase 1 is API/service layer,
  unit-testable headless; voice wiring is Phase 2.
- **No requirements.txt / Docker changes** (livekit/openai conflict stays parked; this module adds
  nothing that touches the resolver).
- **No PSUR scheduling, no signal detection, no RMP.**

## Affected Files

### Database Layer — `backend/postgres_schema.sql` (+ matching SQLAlchemy models in `backend/app/db/postgres.py`)

Append four tables (idempotent `CREATE TABLE IF NOT EXISTS` style per house convention), each with
RLS: `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + add to the FORCE list + `{table}_manage` policy
mirroring `payments_manage` (clinic `clinic_users` membership **OR** `app.service_request = 'on'`
for verified-webhook writes).

| Table | Key columns (design) | Purpose |
|---|---|---|
| `products` | `id UUID PK`, `clinic_id FK→clinics`, `name`, `generic_name`, `strength`, `dosage_form`, `manufacturer`, `approved_label_json JSONB` (expectedness reference), `is_active BOOL` | Company product dictionary the PV records hang off |
| `adverse_events` | `id UUID PK`, `call_id FK→calls ON DELETE SET NULL`, `clinic_id FK→clinics`, `product_id FK→products`, `reporter_type TEXT (hcp/patient/other)`, `reporter_contact JSONB` (minimal: role, phone suffix), `patient_age`, `patient_sex`, `patient_initials`, `event_text TEXT`, `event_onset_date DATE`, `outcome TEXT`, `seriousness_flags JSONB` (death / life-threatening / hospitalisation / disability / congenital / medically-important), `expectedness TEXT (expected/unexpected/unknown)` vs label JSON, `causality_reporter TEXT` (verbatim, never system-assessed), `e2b_minimum_met BOOL`, `status TEXT` (`new → validated → triaged → notified → submitted → closed`), `notification_deadline TIMESTAMPTZ` (computed), `notified_at TIMESTAMPTZ`, `source_channel TEXT (voice/email/form/…)`, `recording_consent TEXT` (from the call row) | The ICSR collector record (E2B-minimum fields) |
| `quality_complaints` | `id UUID PK`, `call_id FK→calls`, `clinic_id FK→clinics`, `product_id FK→products`, `batch_no TEXT`, `expiry DATE`, `defect_description TEXT`, `photos_url JSONB`, `severity TEXT (minor/major/critical)`, `investigation_status TEXT` (`captured → investigating → disposition → capa`), `disposition TEXT (released/hold/reject/recall)`, `capa_ref TEXT` | PQC → investigation → CAPA trail (EU GMP Ch. 8 / complaint-file model) |
| `medical_inquiries` | `id UUID PK`, `call_id FK→calls`, `clinic_id FK→clinics`, `product_id FK→products NULL`, `question_text TEXT`, `category TEXT` (dosing/indication/interaction/storage/pregnancy/other), `language TEXT`, `response_text TEXT` (approved-content phrase or `NO_MEDICAL_ADVICE` note), `status TEXT (`received → responded → followed_up`)` | MI enquiry log (approved-content discipline, no-personal-advice rule) |

### Service Layer — `backend/app/services/pharmacovigilance.py` (NEW, stdlib-only)

| Function | Behavior | Test hooks |
|---|---|---|
| `classify_contact_type(text, language)` → `"AE" \| "PQC" \| "MI" \| "OTHER"` | Phrase-table classification per language (`hi/en/ta/te/bn`), mirroring `IVR_DIGIT_LANGUAGES` / `RED_FLAG_CATEGORIES` patterns; special-situation terms (pregnancy, overdose, medication error, off-label, lack of effect) → AE | table-driven cases per language |
| `validate_minimum_criteria(event_text, reporter, patient, product)` → `(valid: bool, missing: list[str])` | E2B/India minimum criteria verbatim: identifiable reporter, identifiable patient (age/sex/initials), suspect product, AE description | explicit missing-each paths |
| `classify_seriousness(seriousness_flags)` → `(is_serious: bool, criteria: list[str])` | ICH E2A/E2D criteria: death, life-threatening, hospitalisation / prolongation, persistent-significant disability / incapacity, congenital anomaly / birth defect, medically important condition | each criterion + none |
| `compute_reporting_deadline(serious, received_at, jurisdiction="india")` → `(deadline: datetime, days_remaining: int)` | India clocks (calendar days, no holiday skipping, day-zero = receipt of minimum criteria): serious **15 days**, non-serious **90 days** | weekend/month-end/last-day-of-90 edge cases |

### API Layer — `backend/app/api/pv.py` (NEW router, registered in `backend/main.py`)

| Route | Behavior |
|---|---|
| `POST /api/pv/products` | Identity-gated (clinic staff) single-product create into the `products` dictionary (name, generic, strength, dosage form, manufacturer, `approved_label_json` for expectedness). |
| `POST /api/pv/products/import` | Bulk **CSV seed** of the product dictionary (mirrors the `language_codes` seed pattern); idempotent by (clinic_id, name, strength, dosage_form). |
| `POST /api/pv/cases` | Webhook-token-guarded (verified `X-Service-Token` path, mirroring `voice.py`; writes under `service_request_ctx()` for RLS). Body: call_id + transcript or structured fields. Runs classify → create the right table → compute deadline → return case id + deadline + missing minimum criteria. Records a `compliance_events` row (PV intake, DPDP audit trail). |
| `GET /api/pv/cases?type=ae\|pqc\|mi&clinic_id=&status=` | Identity-gated list for the dashboard (clinic-staff scope via RLS). |
| `POST /api/pv/export?format=json\|csv` | Phase-1 export: **JSON** = E2B-minimum bundle for validated serious cases (keys mirroring E2B(R3) groups: sender case id, primary source/reporter, patient age/sex/initials, product, event term + onset + outcome, seriousness flags, reporter causality, dates incl. day zero) — the skeleton the Phase-2 E2B(R3) XML generator consumes. **CSV** = same fields, flat, for analysts/BI. |
| `GET /api/pv/cases/{id}/print` | Human-readable, self-contained **HTML per-case summary** (print-friendly) for the PV team — displays only captured facts (no analysis, no causality claim), with the `NO_MEDICAL_ADVICE`/source-data banner. |
| `PATCH /api/pv/complaints/{id}` | PQC disposition updates (`investigating → disposition → capa`, with `capa_ref`). |

### Supporting

| File | Change |
|---|---|
| `backend/app/db/postgres.py` | Four SQLAlchemy 2.0 models mirroring the schema tables (`AdverseEvent`, `QualityComplaint`, `MedicalInquiry`, `Product`) + repository helpers, following the existing typed-model pattern |
| `backend/app/services/notifications.py` / `backend/app/schemas/notification.py` | (Optional, default on) add `pv_alert` to `NOTIFICATION_KINDS` so the env-gated `send_notification` can ping the PVOIC/`sae@cdsco.nic.in` mailbox on serious-AE capture — reuses G6-Q8 with zero new channels |
| `backend/tests/test_pv_module.py` | NEW unit tests (see checklist) |
| `.opencode/research-micc-process.md` | Already written — this spec's source of truth |

## Expected Behavior

1. **Intake & classification**. A call transcript (any of the 5 languages) is classified at the API
   boundary into AE / PQC / MI / OTHER via the phrase tables. Special situations (pregnancy,
   overdose, misuse, off-label, medication error, lack of effect), product + symptom complaint →
   AE.
2. **AE capture**. `POST /api/pv/cases` creates an `adverse_events` row with E2B minimum-criteria
   validation: if anything is missing, the case is still stored (ABPI: store-and-forward regardless)
   but flagged `e2b_minimum_met=false` with the missing elements returned. A `pv_alert` notification
   (if channel keys exist) fires immediately; otherwise the row + `compliance_events` audit entry is
   the record. **No causality statement, no diagnosis, no medical advice** is generated anywhere.
3. **The clock starts at capture**. `compute_reporting_deadline` sets `notification_deadline` = 15
   calendar days (serious) or 90 (non-serious) from day zero, calendar-day arithmetic (weekends and
   Indian holidays count). Dashboard lists show days-remaining; overdue serious cases float to the
   top.
4. **PQC path**. Quality complaints land in `quality_complaints` with batch/expiry/defect; the
   PATCH route drives `investigating → disposition → capa` (initial-assessment-in-24-48h is a
   documented operational target in the research doc, surfaced to the dashboard as a KPI, not
   enforced by a clock in Phase 1).
5. **MI path**. Medical-information questions are logged with category + language + response note;
   any question that can't be answered from approved content records `NO_MEDICAL_ADVICE` and
   flags for human Medical Affairs follow-up.
6. **Product dictionary**. `POST /api/pv/products` + the CSV import keep the `products` reference
   current (idempotent by clinic/name/strength/form); AE/PQC/MI records reference it for
   expectedness-vs-label and batch-level reporting.
7. **Export**. `POST /api/pv/export` emits the **E2B-minimum JSON bundle** (Phase-2 XML-generator
   input) **and a flat CSV** for analysts; `GET /api/pv/cases/{id}/print` renders a self-contained
   HTML per-case summary for the PV team — the deterministic feed a qualified PV team (or Phase 2
   E2B(R3) generator) consumes for `sae@cdsco.nic.in` / PvPI submission. Phase 1 does **not** send.

## Acceptance Criteria Checklist

### Hard gates (unchanged project law)
- [ ] `py -3.14 -m unittest discover` passes from `backend/` (sequential, then `compileall`) — run
      exactly as the agent-work-rules say, report the passing run
- [ ] Existing suite stays green (580+ tests at last count; **no regression**)
- [ ] `backend/requirements.txt` byte-identical to the parked state — no new deps, resolver untouched
- [ ] New module itself is stdlib-only (no `import` outside stdlib + repo modules)

### Database
- [ ] Four tables (`products`, `adverse_events`, `quality_complaints`, `medical_inquiries`) in
      `postgres_schema.sql` + matching SQLAlchemy models; FKs to `calls(id)` validated
- [ ] RLS enabled + FORCE'd for the four, with `{table}_manage` policies (clinic scope + service
      bypass) — mirrors `payments_manage`
- [ ] `recording_consent` flows from the parent `calls` row onto AE/PQC record creation (DPDP)

### Service functions
- [ ] `classify_contact_type` — table-driven tests over hi/en/ta/te/bn incl. special-situation terms
- [ ] `validate_minimum_criteria` — each missing element asserted individually (reporter / patient /
      product / event)
- [ ] `classify_seriousness` — all six E2A criteria incl. the medically-important-condition catch-all
- [ ] `compute_reporting_deadline` — serious 15 / non-serious 90 calendar days; weekend + month-end +
      exact-90th-day edges asserted; timezone-aware UTC

### API
- [ ] `POST /api/pv/products` + `/import` create/seed the dictionary; import idempotent by
      (clinic_id, name, strength, dosage_form) — re-seeding the same CSV adds no duplicates
- [ ] `POST /api/pv/cases` enforces the service token; writes succeed under `service_request_ctx()`
      (RLS bypass tested via service path, denied via plain user path)
- [ ] Incomplete cases stored with `e2b_minimum_met=false` + missing list returned, case not dropped
- [ ] `POST /api/pv/export?format=json` output validates against the E2B-minimum key groups
      (no free-form keys); `format=csv` mirrors the same fields flat (assert header row + row count)
- [ ] `GET /api/pv/cases/{id}/print` renders self-contained HTML with captured facts only — asserted
      to contain **no** causality/diagnosis/advice text
- [ ] `PATCH /api/pv/complaints/{id}` state machine rejects illegal transitions (`capa` → `captured`)
- [ ] `compliance_events` audit row written for every intake + disposition change

### Documentation
- [ ] `.opencode/research-micc-process.md` exists with all sources inline (done — reviewer should skim §2.3/§3.3/§8 for the clock table the module implements)

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| **Not a validated PV system** | A collector module is not a regulatory-submission system; a wrongful implication of compliance | Research doc + spec state it plainly: exports feed a human PV team; Phase-2 submission needs a validated system + gateway creds (GVP Module I QMS / equivalent) |
| **Deadline/criteria edge cases are compliance-critical** | Wrong 15/90-day clock or seriousness mis-triage | Deterministic stdlib functions + table-driven unit tests incl. calendar edges; seriousness is flag-driven (no free-text parsing for the *decision*) |
| **India data protection (DPDP)** | AE records are health data — consent + audit + PII minimization | Reuse G6-Q2 `recording_consent` from the call; E2B-minimum PII (age/sex/initials, phone suffix); `compliance_events` on every write; no diagnosis/causality text stored beyond caller's own words |
| **MedDRA / WHO-UMC / E2B(R3) are Phase 2** | Regulator-strict coding absent in Phase 1 | Explicitly non-goaled; export uses E2B-minimum field *names* so the Phase-2 generator slots in without reshaping data |
| **MI caller asks for personal medical advice** | Agent/dashboard must not answer | Research doc 8.01 rule → MI path returns approved-content or `NO_MEDICAL_ADVICE` + human follow-up; guardrails already forbid diagnosis/dosage claims |
| **Parked Docker blocker (livekit/openai)** | Full-stack smoke blocked end-to-end | Module is stdlib-only + unit-testable headless; does not worsen the resolver; Docker walkthrough resumes independently |

## Final State (post-implementation — workflow step 6, 2026-09-26)

**Implemented and committed**: `c66fc9b` — `feat(pv): MICC pharmacovigilance module - 4 tables, stdlib PV service, /api/pv router (686/686)`.

**Gates (verified by scheduler re-run, not just reported)**:
- `py -3.14 -m unittest discover -s tests -p "test_*.py"` → **686 tests, OK, exit 0** (580 pre-existing + 106 new PV)
- `py -3.14 -m compileall .` → **exit 0**
- `backend/requirements.txt` byte-identical to parked state (only the pre-existing parked edits remain unstaged); docker-compose/livekit untouched

**Delivered**: 4 tables + 5 indexes + RLS ENABLE/FORCE + 4 `_manage` policies + GRANTs (`postgres_schema.sql`); 4 SQLAlchemy 2.0 models + 12 repo helpers (`postgres.py`); `services/pharmacovigilance.py` (stdlib-only: classification 5 languages, minimum criteria, E2A seriousness, 15/90-day clocks, PQC transitions, E2B groups, CSV/HTML export); `api/pv.py` (7 routes incl. service-token intake + `compliance_events` audit); router registered in `main.py` (12th); `pv_alert` notification kind (email-only channel, `PV_PVOIC_EMAIL` env); `.env.example` + `docs/DEPLOYMENT.md` updated.

**Recorded deviations**: (1) `STDLIB_ROOTS` whitelist gained `html` (pre-existing whitelist omission of a genuine stdlib module; gate intent — no third-party imports — preserved); (2) `_verify_service_token` inlined in `create_pv_case_ep` (constant-time guard per test contract; DRY loss accepted); (3) two exact-set router-count tests extended to 12 via `included - {"pv"}`; (4) test-helper bugs fixed before they could falsify RED/GREEN (walrus-in-kwarg SyntaxError, mixed-script Hindi vector, Saturday=5 weekday).

**Pre-existing defect surfaced (was OUT OF SCOPE, now FIXED 2026-09-26)**: `backend/postgres_schema.sql`
had two invalid-SQL defects: (1) `CREATE TABLE call_sessions (` was never terminated — `CREATE TABLE
payments (` was nested inside it; (2) a dangling comma on `last_heartbeat` before the closer. Fixed in
commit `aabcf75` (see `backend/tests/test_schema_wellformed.py`, the permanent regression guard: CREATE TABLE
statements must be top-level, paren-balanced, and comma-clean before `);`). This file had never been
executable by `psql -f`; the fix unblocks the parked Docker walkthrough.

## Spec Status
**Status**: **APPROVED → IMPLEMENTED & VERIFIED — 2026-09-26** (fresh-session implementation per workflow
step 5; scheduler re-ran the gates per verify-before-done; final state above).