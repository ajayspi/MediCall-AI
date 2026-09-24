# HANDOVER — MediCall AI → next OpenCode session

Read this file first. It is the full state of the project. The spec tracker
`.opencode/spec-idea-refinement-gaps.md` holds the detailed records; this file
is the launchpad.

## 1. What this is
- **MediCall AI**: a NEW, separate healthcare company (voice-first Indian
  Medical Call Center). It is NOT Talkbyte.
- **Project home (work here ONLY)**:
  `C:\Users\vigilare\OneDrive - Vigilare BP PVT LTD\Documents\MediCall-AI\`
- **NEVER touch**: `C:\Users\vigilare\Talkbyte\` (original Talkbyte: 3 versions
  + docs + .git — verbatim intact). `Documents\Talkbyte_clone\` is the frozen
  archive of earlier work; do not edit it either.

## 2. Where development stands
- ✅ **G1+G2 DONE** — `backend/main.py` imports clean + "MediCall AI" branding;
  `backend/app/db/postgres.py` rewritten (parses, pgvector-correct).
  Proof: `backend/tests/test_g1_g2.py` 11/11 GREEN.
- ✅ **G3 DONE** — single medical state machine; `app/models/call.py` is the
  canonical owner (`CallState`, `TriageSeverity`, `STATE_TRANSITIONS`, 9 states,
  terminal COMPLETE/ESCALATED/DROPPED); `postgres.py` imports from it;
  schema comment fixed. Proof: `backend/tests/test_g3_state_machine.py` 9/9 GREEN.
- ▶️ **NEXT: G4** — voice pipeline: rewrite `services/livekit_agent.py`
  (still restaurant-flavored: "Mama's Pizzeria", `order_items`, `TAKING_ORDER`)
  + Exotel/Knowlarity/Twilio-India webhooks in `app/api/voice.py`
  (still Telnyx-US + `restaurant_id`).
- ⏳ **After G4**: G5 (requirements: drop stripe/celery, add pytest/ruff,
  Knowlarity client) → clinic (7-tab) + admin (9-view) dashboards → API routes
  → UML diagrams → Interactly-parity build (benchmarks + integration catalog
  are specced in `spec-multifit-healthcare.md`, NOT built).

## 3. Decisions already locked (do not relitigate)
- G1–G7 = the complete fix list (approved 2026-09-22).
- Auth MVP: full incl. ABHA login (OTP + password + Google/Microsoft SSO + ABHA).
- Telephony: ALL THREE providers wired with fallback chain (Exotel +
  Knowlarity + Twilio India), no single primary.
- EHR/ABDM Phase 1: transcript-only, no EHR writes.
- Stack: LiveKit Agents (primary) / TEN (multimodal fallback) / Bolna (OSS
  fallback); Deepgram STT + ElevenLabs TTS, 5 languages (hi/en/ta/te/bn);
  Razorpay/PhonePe/Cashfree; PostgreSQL + pgvector local (no Supabase).

## 4. Still open (answer before the session that needs them)
G6-Q2 consent/retention (DPDP), Q3 clinical guardrails, Q4 language fallback,
Q5 payment flows, Q8 notifications, Q9 MVP KPIs, Q10 deploy topology.

## 5. Verify first (before any edit)
```
powershell -ExecutionPolicy Bypass -File start-worktree.ps1
```
Must print STARTUP GREEN (runs both suites + py_compile). Full runs:
`python3 tests/test_g1_g2.py` and `python3 tests/test_g3_state_machine.py`
from `backend\`. This PC has NO third-party packages (no fastapi/sqlalchemy/
pytest/ruff) — tests are stdlib-only by design; live DB/runtime checks belong
in Docker/CI. There is no `.git` in MediCall-AI yet; the startup script can
init it (`-Branch <name>` creates an isolated `.worktrees\<name>` tree).

## 6. Spec index (`.opencode/`)
- `spec-idea-refinement-gaps.md` — master tracker: gaps, sign-off, G-records ← START HERE
- `spec-micc-india.md` — India-market requirements (approved)
- `spec-multifit-healthcare.md` — platform vision + Interactly research
- `spec-micc-database-dashboards-routes-uml.md` — DB/dashboards/routes/UML plan
- `spec-design-system.md` — design tokens/components (pending build)

## 7. Session rules (non-negotiable)
1. Spec-first: clarify → research on-disk (don't assume) → update spec →
   STOP for sign-off → implement only on approval.
2. One task per session (next = G4 only).
3. Tests first (RED), implement to GREEN, refactor, lint-equivalent
   (`py_compile`; ruff lands with G5).
4. PowerShell only: no `&&`, no `tail/head/grep`, quote spaced paths.
5. Never write code into `C:\Users\vigilare\Talkbyte\` or `Talkbyte_clone\`.
