# G6-Q3 Clinical Guardrails — spec (DRAFT)

| | |
|---|---|
| **Phase** | G6-Q3: clinical safety guardrails for the voice agent |
| **Tracker question** | "Clinical safety: triage guardrails (no diagnosis/dosage from AI), escalation triggers, red-team list, temperature≈0 paths?" |
| **Branch** | `g-guardrails` off `g-payments` tip `4812795` |
| **Status** | DRAFT — pending sign-off (Q1–Q4 below) |
| **Date** | 2026-09-25 |

## 1. Why now (evidence from the current surface)

The G4 voice pipeline shipped an **escalation MVP (D2)** and the G3 state machine carries
`ESCALATED` + `TriageSeverity`. What exists today is deliberately thin:

| Piece | Current state (verified by reading the code) | Gap |
|---|---|---|
| `agent_logic.should_escalate(severity)` | red/critical → True only; **no keyword layer** | LLM can mislabel severity ("chest pain" tagged `amber`) → no escalation |
| `system_prompt` | Prose guardrail (no diagnosis/dosage; lists chest pain / breathing difficulty / severe bleeding) | Prompt-only: nothing enforces it downstream; no structured symptom catalog |
| `livekit_agent` escalation leg | Hardcoded **English-only** phrase, regardless of caller language | 5-language product speaks English at the one moment that matters most |
| `livekit_agent` content branch | LLM output goes **straight to TTS**, no scan | A diagnosis/dosage claim in a response would be spoken verbatim |
| Red-team vectors | Only `test_g4_voice` severity checks | No adversarial acceptance suite for guardrails |

Q3 answers the question and hardens all five.

## 2. Non-goals (hold the line)
- NO clinical decision support: no diagnosis engine, no medication logic, no "is this safe to take" answers.
- NOT replacing human triage: every escalation is a handoff, and the red-flag path is deterministic, never LLM-judged.
- No new env keys, no new tables, no new endpoints — this is a **pure stdlib logic phase** (runs fully on this PC).
- `should_escalate` and `system_prompt` stay untouched (G4's `test_g4_voice.py` pins them).

## 3. Question to answer (G6-Q3) + options

### Q1 — Escalation triggers: what fires an escalation?
- **A1a (recommended)** — **Layered deterministic triggers**: escalate when ANY of
  - (1) triage severity ∈ {red, critical} — existing `should_escalate`, reused not duplicated;
  - (2) caller transcript matches a red-flag symptom keyword — **new `match_red_flag(text)`** (catches LLM severity mislabels);
  - (3) explicit `escalate` intent — existing `apply_intent`.
  Each trigger records its `reason` (e.g. `severity:red`, `red_flag:cardiac`).
- A1b — Severity-only (status quo; no keyword layer). Accepted risk: mislabeled severity slips through.

### Q2 — No-diagnosis / no-dosage enforcement
- **A2a (recommended)** — **Deterministic output guard**: `guard_output(text, language)` scans the agent's
  response for forbidden diagnosis/dosage patterns (`FORBIDDEN_CLAIMS`); on a match it replaces the
  offending content with a **fixed per-language refusal phrase** (the temperature≈0 path) and returns
  `(safe_text, flag, reason)`. Applied in the agent loop **before TTS** so a bad claim is never spoken.
- A2b — Prompt-only (rely on `system_prompt` prose). Accepted risk: nothing catches a prompt-ignoring model.

### Q3 — Red-flag catalog scope
- **A3a (recommended)** — **~12 curated life-threatening categories** with stable keyword phrase tables
  (documented in the module + spec): cardiac, respiratory, severe bleeding, stroke/neuro, seizure,
  poisoning/overdose, anaphylaxis, burns, head injury/unconscious, pregnancy emergency, self-harm/suicide,
  choking. Matching is case/accent-insensitive substring on the caller's words.
- A3b — Only the 3 already in the prompt (chest pain / breathing difficulty / severe bleeding). Smaller
  surface, weaker safety net.

### Q4 — Red-team acceptance suite
- **A4a (recommended)** — **Adversarial vector table (~15 scenarios)** as the RED test suite: each asserts
  the exact guard action (escalate / refuse / safe) + reason. Covers a red flag per category, LLM-mislabeled
  severity, dosage requests ("how much paracetamol for my baby"), diagnosis-style questions, self-harm,
  and benign queries (must NOT false-positive). Doubles as the acceptance gate.
- A4b — Reuse only the existing g4 escalation tests. Weaker gate.

## 4. Deliverables

- **A. `backend/app/services/guardrails.py`** (new, stdlib-only, zero env keys):
  - `RED_FLAG_CATEGORIES: Dict[str, Tuple[str, ...]]` — the A3a catalog (≥12 categories).
  - `match_red_flag(text) -> Optional[Tuple[str, str]]` — (category, matched_phrase) or None.
  - `FORBIDDEN_CLAIMS: Tuple[str, ...]` — diagnosis/dosage patterns ("you have <condition>", "it looks like…",
    "take \d+ mg", "take \d+ tablets", "\d+ ml of", "twice/thrice a day", …).
  - `guard_output(text, language="en") -> Tuple[str, str, str]` — (safe_text, flag, reason), flag ∈ {safe, refused}.
  - `SAFE_REFUSALS: Dict[str, str]` + `ESCALATE_PHRASES: Dict[str, str]` — per-language fixed strings (hi/en/ta/te/bn).
  - `escalation_decision(severity, caller_text="") -> Tuple[bool, str]` — composes `should_escalate` + `match_red_flag`; reason records the trigger source.
- **B. Wire `backend/app/services/livekit_agent.py`** (keeping every string G4 pins: `agent_logic`,
  `CallState`, `MEDICAL_FUNCTIONS`, `specialist`):
  - ESCALATED leg → speak `ESCALATE_PHRASES[caller_language]` (EN value keeps "Connecting you to a specialist…").
  - Content branch → `guard_output(content, language)` first; speak the safe text (refusal phrase on flag).
  - Transcript branch → `match_red_flag(user_text)`; on a hit set `triage_severity = "red"` + escalate
    deterministically (temperature≈0 path) with the category as reason.
- **C. `backend/tests/test_guardrails_q3.py`** — RED first, ~30 tests (structure + behavior + wiring as above).
- **D. Docs** — 02-state-machine escalation leg note, 06-call-lifecycle escalation detail, HANDOVER DONE
  record, tracker record, spec status GREEN.

## 5. Verification plan
1. **RED**: commit `test_guardrails_q3.py` on the scaffold; run `py -3.14 -m unittest discover -s tests -p
   "test_guardrails_q3.py"` → expected failures (no guardrails module, no wiring), exit 1.
2. **GREEN**: implement A+B; run the new suite → OK; full regression `discover -s tests` → **282 + new** ALL
   PASS; `compileall -q app scripts tests` exit 0.
3. **Docs**: commit D; re-run full suite (docs-only changes must not move the count).

## 6. Ripple / constraints (do-not-break)
- `test_g4_voice.py` pins: `livekit_agent.py` contains `agent_logic`, `CallState`, `MEDICAL_FUNCTIONS`,
  and "specialist" (lower) — keep all four in the file.
- `agent_logic.system_prompt` prose is unchanged (pinned by `test_system_prompt_medical`); `should_escalate`
  signature preserved (pinned by `test_should_escalate`).
- Stdlib-only (no pip on this PC); lint gate = `compileall`; Python 3.14.7 via `py -3.14`.
- Keep the literal "G6-Q3" in `guardrails.py` docstring (parity with "G6-Q5" in `payments.py`).
- Full regression must stay at 282 baseline + new tests.