# SPEC: MICC/PV Module — Phase 2 (DRAFT plan)

**Research base**: `.opencode/research-micc-process.md`. **Phase-1 base**: `.opencode/spec-micc-pv-module.md`
(implemented, verified, `c66fc9b`). Phases are **independently signable slices** — nothing here is
approved yet; pick slices, or adjust scope.

**Where Phase 2 starts from**: Phase 1 is a *collector* — it records AE/PQC/MI facts, computes the
India clocks, and exports E2B-minimum JSON/CSV/print. Phase 2 makes the module *submission-capable*,
*voice-native*, and *analyst-friendly*. The call-centre-is-a-collector rule still holds: coding and
causality remain expert-judgement steps with the system as an assistant, never the decision-maker.

## Goal (overall)

Turn the Phase-1 collector into a workflow an Indian MAH / licensed clinic can actually run daily:
E2B(R3)-shaped submission material for the PVOIC, in-call AE/PQC/MI capture by the voice agent,
regulator-standard coding with human-in-the-loop, an approved-content MI answering layer, and a
PVOIC-facing compliance view.

## Non-Goals (Phase 2 overall)

- **No autonomous submission.** Every regulator-bound artifact (E2B XML, PSUR cover, gateway push) is
  *generated* by the system and *signed off / sent* by the PVOIC. Gateways need MAH credentials +
  a validated environment (GVP Module I QMS / equivalent), which is a deployment concern, not code.
- **No signal detection, no RMP authoring, no AI causality.** WHO-UMC causality is captured from the
  reporter + expert review only; the system never assigns a causality category.
- **No MedDRA content embedded.** Phase-2C integrates a *licensed* dictionary (subscription), API-side;
  no partial dictionary blobs ship in-repo.
- **No clinical-trial SAE path** (still NDCT 14-day out of scope — post-marketing only).
- **No Notion/ops tooling in this plan** (project-docs mirror stays a separate track on the project page).

## Proposed slices

| Slice | Deliverable | Blocked by | Acceptance sketch |
|---|---|---|---|
| **2A — E2B(R3) XML generator + gateway adapter** | stdlib `services/e2b.py`: Phase-1 export JSON → E2B(R3)-shaped XML (message/case wrappers, C.1/D/E groups, sender case id, redirects); `api/pv.py` route `POST /api/pv/cases/{id}/e2b.xml` (+ batch). Adapter interface with a stub gateway; **no live send**. | none | XML parses (xml.etree), mirrors export key-for-key, deterministic, unmasked per data element tests; adapter does not refactor? — adapter is a stub returning the payload for PvPI's E2B-XML spec; no net call in tests |
| **2B — In-call voice capture** | `livekit_agent` + `agent_logic` intents (AE / PQC / MI): agent asks minimum-criteria questions in-language, structured capture → `POST /api/pv/cases` on hangup; special-situation prompts (pregnancy/overdose/medication error) | parked Docker blocker (needed for smoke test; unit-coverable headless) | unit tests for transcript→fields extraction reuse + intent routing; smoke deferred to Docker resume |
| **2C — Coding layer (MedDRA + WHODrug + WHO-UMC)** | `services/coding.py`: dictionary-backed AE/indication coding to MedDRA PTs, company dict/WHODrug mapping; WHO-UMC causality *capture form* (reporter + reviewer, no auto-assign); human-in-loop gate for expedited cases | MedDRA license (subscription) | coding mapping tests with a tiny fixture dictionary; causality stored as verbatim + reviewer fields; expedited path requires a `reviewer` stamp before export |
| **2D — MI approved-content KB** | `medical_inquiries` gains approved-response linkage: `products` label JSON → per-language standard responses; answer path returns approved content or `NO_MEDICAL_ADVICE`; versioned response snapshots (audit) | none | KB load/query tests; versioned response history; no-personal-advice guard enforced in answer endpoint |
| **2E — PVOIC dashboard + compliance view** | read-only dashboard API + (Phase-2.5, frontend) — case queue, clock countdowns (15/90-day), overdue red flags, PQC pipeline, PSUR windows (6-monthly ×2y, annual ×2y), audit trail; exports wired from 2A | none (API first, frontend later) | API contract tests: counts, deadline math matches `compute_reporting_deadline`, overdue detection |

**Sequencing**: 2A and 2E are independent and dependency-free (fastest wins). 2B needs the Docker
unblock for its smoke test (unit work can start now). 2C waits on a MedDRA license; its non-dictionary
parts (capture form, reviewer gate) can proceed. 2D is independent. Suggest order: **2A → 2E → 2B
(unit) → 2D → 2C** — but each slice is standalone.

## Acceptance criteria (per slice, consolidated)

- [ ] Slice adds **zero** new PyPI runtime deps that aren't already licensed/intended (2C is the only
      one that may add a vendor SDK — gated on the license)
- [ ] Every slice keeps the py gate green: `py -3.14 -m unittest discover` + `compileall` from `backend`
- [ ] Every slice keeps 687/687 existing tests green (no regression); new tests written RED first
- [ ] 2A: generated XML round-trips through the Phase-1 exporter fields; no network calls in tests
- [ ] 2B: transcript→fields extraction unit tests over the 5 languages; hangup path creates AE/PQC/MI rows
      exactly like the API path (same validation/deadline/audit)
- [ ] 2C: expedited cases cannot reach export without a `reviewer` stamp; causality fields are never
      system-generated
- [ ] 2D: every answer is versioned; `NO_MEDICAL_ADVICE` cannot be bypassed by a KB gap
- [ ] 2E: deadline math matches Phase-1 clocks exactly; audit events visible; PSUR window calc tested

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| E2B(R3) spec drift / gateway mismatch (PvPI) | Generated XML rejected downstream | 2A generates from the Phase-1 key-group contract, not a fixed vendor draft; PvPI's published E2B-XML example is the acceptance fixture |
| Live submission liability | Wrong report = regulatory exposure | Human PVOIC gate before anything leaves the system; validated-environment deployment note |
| MedDRA license cost/complexity | Slice stalls | 2C designed so the dictionary is pluggable; non-dictionary parts ship first |
| Voice intents without smoke (Docker parked) | In-call capture only unit-tested | Unit coverage now; smoke deferred to Docker resume; no production voice claim until then |
| AI-assisted capture drifts into advice/causality | Collector rule broken | Reuse Phase-1 guardrails + explicit none-advice phrases; 2B extraction is question-scripted, not free-association |

## Spec Status
**Status**: **APPROVED — 2026-09-26** (user sign-off via "continue"). Implementing slices in the
suggested order: **2A → 2E → 2B → 2D → 2C** (each a fresh implementation session, per workflow).
Deferred-by-license: 2C's MedDRA/WHODrug dictionary integration (needs a MedDRA subscription — the
non-dictionary parts: capture form + reviewer gate ship now). Deferred-by-blocker: 2B end-to-end
voice smoke (parked Docker) — 2B unit coverage ships now. This file will be updated with per-slice
final states as they land.