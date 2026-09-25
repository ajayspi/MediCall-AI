# G6-Q4 Languages — spec (APPROVED)

| | |
|---|---|
| **Phase** | G6-Q4: language layer hardening — confidence-low STT fallback chain + per-language TTS voice map + single-source 5-language catalog |
| **Tracker question** | "Languages: exact 5 (hi/en/ta/te/bn) for MVP; fallback chain when STT confidence low; per-language TTS voice map?" |
| **Branch** | `g-languages` off `g-notify` tip `394192c` |
| **Status** | **APPROVED** (signed off 2026-09-25, question tool: Q1=A1 Q2=A1 Q3=A1 Q4=A1) |
| **Date** | 2026-09-25 |

## 0. Sign-off record (2026-09-25, question tool)

- **Q1=A1** — **confidence-low STT fallback chain**: stdlib
  `resolve_stt_language(language, confidence, threshold, fallback="en")` —
  confirmed (confidence ≥ threshold) or unknown (None) confidence keeps the
  call language; low confidence (< threshold) falls the *operative* language to
  English for that turn and flags the transcript `low_confidence`.
  `STT_CONFIDENCE_THRESHOLD` env (default `0.6`). `stt.py` gains an additive
  `stt_stream_with_scores` (yields `(transcript, confidence, language)`); the
  G4 `stt_stream` (yields `str`) is untouched. Chain = `[detected] → en`.
  (User skipped the Q1 pick; all other answers were A1 recommendations, so the
  recommended A1 was recorded.)
- **Q2=A1** — **single-source catalog**: new stdlib `app/services/languages.py`
  owns `SUPPORTED_LANGUAGES`, `STT_TAGS`, `IVR_DIGIT_LANGUAGES`,
  `TTS_VOICE_ENV_KEYS`, `LANGUAGE_FALLBACK_CHAIN`, `is_supported_language()`,
  `resolve_stt_language()`. `agent_logic.py` re-imports/re-exports the G4-pinned
  helpers unchanged; `postgres.py` + `services/notifications.py` import the
  tuple from `languages` (import-level dedupe).
- **Q3=A1** — **5-language greeting templates**: `GREETING_TEMPLATES`
  (hi/en/ta/te/bn, mirrors `guardrails.SAFE_REFUSALS`) +
  `greeting_for_language(language, clinic_name)` in `agent_logic.py`;
  `livekit_agent.py` greeting wired to it; unknown code → English template.
  (No test pins the current "Namaste" text — verified.)
- **Q4=A1** — **canonical TTS voice env keys**: key form =
  `ELEVENLABS_VOICE_ID_{CODE}` for all 5 (`_HI/_EN/_TA/_TE/_BN`); `.env.example`
  corrected from the `_HINDI/_TAMIL/…` names; `TTS_VOICE_ENV_KEYS` catalog +
  coverage test (all 5 in the map AND documented in `.env.example`).
- Test-first (RED → GREEN); stdlib-only; full regression must stay 371 baseline
  + new.

## 1. Why now (evidence from the current surface)

The 5-language machinery exists and is G4-contract-pinned, but three gaps in
the tracker question are unbuilt, verified by reading the tree:

1. **STT confidence is ignored.** `app/services/stt.py` `receiver()` reads only
   `data["channel"]["alternatives"][0]["transcript"]` — Deepgram's per-utterance
   `confidence` score is dropped. There is no "fallback chain when STT confidence
   low" anywhere: the language is fixed per connection (`stt_language_tag`), and
   a low-confidence turn gets no treatment (no flag, no English fallback for the
   operative language).
2. **The greeting is hardcoded English.** `livekit_agent.py:57-58` =
   `f"Namaste, welcome to {clinic_name}. "` — the TTS voice IS localized
   (`tts_stream(greeting, language=call.caller_language)`), but the *text* is
   always English. A Tamil/Telugu/Bengali caller hears English words in their
   language's voice. No test pins the current "Namaste" text (grep across
   `tests/` = 0 matches) — safe to localize.
3. **Per-language voice env keys mismatch the docs.** Code builds the key as
   `ELEVENLABS_VOICE_ID_{str(language).upper()}` (`agent_logic.tts_voice_id`,
   `tts.voice_for_language`) → `_HI/_EN/_TA/_TE/_BN`, but `.env.example` line
   51-55 documents `_HINDI/_TAMIL/_TELUGU/_BENGALI/_ENGLISH` — the documented
   per-language overrides never fire as configured. `language_codes` table
   already models the per-language voice (column `elevenlabs_voice_id`) but has
   no endpoint and nothing consumes it.

Also: the 5-language tuple is duplicated across 3 app modules — `agent_logic.py:13`,
`postgres.py:156`, `services/notifications.py:31` (plus local copies inside
`test_notifications_q8.py` / `test_guardrails_q3.py`, which are contract-pinned).
Future phases import from wherever they like and drift.

Q4 answers the tracker question with a stdlib service layer + env/dotenv
canonicalization — fully verifiable on this PC (no Docker, no live Deepgram/
ElevenLabs calls), mirroring the Q3/Q8 discipline.

## 2. Non-goals (hold the line)

- NO live STT/TTS/Deepgram/ElevenLabs calls on this PC — the confidence wiring
  is a pure function + an additive yield shape for the Docker/CI host; the G4
  `stt_stream` (yields `str`) stays untouched.
- NO `language_codes` runtime seeding (per-language `elevenlabs_voice_id` rows)
  and NO new `/api/languages` endpoint — the DB table is already modeled; wiring
  it as a runtime store is a Docker/CI follow-on. This phase keeps the voice map
  in code + env (same pattern as the channel keys in Q8).
- NO change to the LLM system prompt / agent loop language plumbing — the
  per-language system prompt, escalation phrases (Q3 guardrails), and template
  validation (Q8) keep their exact behavior; the dedupe is import-level only.
- NO change to `voice.py` webhook semantics (`language = event.language or
  DEFAULT_LANGUAGE` unchanged).
- NO auth/enforcement changes; no table/policy/endpoint additions.

## 3. Question to answer (G6-Q4) — signed off 2026-09-25

- **Q1=A1 (confidence-low STT fallback chain)**: stdlib
  `resolve_stt_language(language, confidence, threshold, fallback="en")` — a
  confirmed utterance (confidence ≥ threshold, or confidence is None) keeps the
  call language; a low-confidence utterance (confidence < threshold) falls the
  *operative* language back to English for that turn and marks the transcript
  `low_confidence`. `STT_CONFIDENCE_THRESHOLD` env (default `0.6`) follows the
  Q8 env-gate pattern. `stt.py` gains an additive `stt_stream_with_scores`
  (yields `(transcript, confidence, language)`) for the livekit loop on the
  Docker host; `stt_stream` is unchanged (G4 pins). Chain = `[detected] → en`
  (safest default).
- **Q2=A1 (single-source catalog)**: new `app/services/languages.py` owns
  `SUPPORTED_LANGUAGES`, `STT_TAGS`, `IVR_DIGIT_LANGUAGES`, `TTS_VOICE_ENV_KEYS`,
  `LANGUAGE_FALLBACK_CHAIN`, `is_supported_language()`, plus
  `resolve_stt_language()`. `agent_logic.py` re-imports + re-exports the
  G4-pinned helpers unchanged (behavior pins keep passing); `postgres.py` +
  `services/notifications.py` import the tuple from `languages` (import-level
  dedupe, values identical).
- **Q3=A1 (greeting localization)**: `GREETING_TEMPLATES` 5-language map in
  `agent_logic.py` (mirrors `guardrails.SAFE_REFUSALS` shape) +
  `greeting_for_language(language, clinic_name)` → `livekit_agent.py` greeting
  replaced with the localized text (unknown code falls back to the English
  template). No test pins the current text (verified).
- **Q4=A1 (TTS voice env-key reconciliation)**: canonical key form = the
  code-built `ELEVENLABS_VOICE_ID_{CODE}` for all 5 (`_HI/_EN/_TA/_TE/_BN`);
  `.env.example` corrected from the `_HINDI/_TAMIL/…` names;
  `TTS_VOICE_ENV_KEYS` catalog + a coverage test asserting all 5 keys exist in
  the map AND are documented in `.env.example` (mirrors Q8's channel-key
  coverage test).

## 4. Deliverables

- **A. `backend/app/services/languages.py`** (new, stdlib-only): the single
  source catalog (SUPPORTED_LANGUAGES 5-tuple, STT_TAGS incl. Deepgram `-IN`
  tags, IVR_DIGIT_LANGUAGES 1–5, TTS_VOICE_ENV_KEYS for all 5, LANGUAGE_FALLBACK_CHAIN),
  `is_supported_language()`, `resolve_stt_language(language, confidence,
  threshold=None, fallback="en", env=None)` (threshold env-param injectable for
  tests, `STT_CONFIDENCE_THRESHOLD` default 0.6). Docstring keeps the literal
  "G6-Q4".
- **B. `agent_logic.py`** — re-import/re-export the G4-pinned helpers
  (`stt_language_tag`, `tts_voice_id`, `language_for_room` behavior unchanged)
  consuming `languages` constants; add `GREETING_TEMPLATES` (5 languages) +
  `greeting_for_language(language, clinic_name)`. `livekit_agent.py` wires the
  localized greeting (English template fallback).
- **C. `stt.py` + `tts.py`** — `STT_CONFIDENCE_THRESHOLD` env read; additive
  `stt_stream_with_scores` (yields `(transcript, confidence, language)` applying
  `resolve_stt_language`); `stt_stream` untouched. `tts.py` `voice_for_language`
  keyed off `languages.TTS_VOICE_ENV_KEYS`.
- **D. Dedupe** — `postgres.py:156` + `services/notifications.py:31` import
  `SUPPORTED_LANGUAGES` from `app.services.languages` (values identical; the
  Q8 422 language validation behavior preserved).
- **E. `.env.example`** — canonical `ELEVENLABS_VOICE_ID_HI/_EN/_TA/_TE/_BN`
  (+ generic `ELEVENLABS_VOICE_ID` documented) + `STT_CONFIDENCE_THRESHOLD=0.6`.
- **F. `backend/tests/test_languages_q4.py`** (RED first, ~40 tests): catalog
  structure + 5-tuple single source (agent_logic/postgres/notifications all read
  the same tuple object), G4 helper behavior pins preserved, confidence fallback
  chain (None / high / low / threshold edge / env override), greeting 5-lang
  coverage + fixed EN vector + unknown → EN template, stt/tts source seam
  checks (`stt_language_tag`, `voice_for_language`, `ELEVENLABS_VOICE_ID_`
  preserved), TTS voice env-key catalog vs `.env.example` coverage, livekit
  greeting wiring, dedupe imports, no en-AU, smoke/docs refs.
- **G. Docs** — tracker record + gotchas, HANDOVER open-list refresh + spec
  index, spec status flip to APPROVED/GREEN. Service-layer only: 01-er, 03-api,
  00-index untouched (no tables/endpoints).

## 5. Verification plan

1. **RED**: commit `test_languages_q4.py` on the scaffold; run
   `py -3.14 -m unittest discover -s tests -p "test_languages_q4.py"` → expected
   failures (no `languages` module / helpers / greeting), exit 1.
2. **GREEN**: implement A–E; new suite OK; full regression → **371 + new** ALL
   PASS; `py -3.14 -m compileall -q app scripts tests main.py` exit 0.
3. **Docs**: commit G; re-run full suite — docs-only commit must not move the
   count.

## 6. Ripple / constraints (do-not-break)

- G4 contract pins (must keep passing unchanged): `stt_language_tag("xx") ==
  "en-IN"`; `tts_voice_id` hi/ta/fallback cases; `language_for_room` tag/IVR/
  default cases; `tts.py` contains `voice_for_language` + `ELEVENLABS_VOICE_ID_`;
  `stt.py` contains `language` + `stt_language_tag`; no `en-AU` anywhere.
- `stt_stream` (yields `str`) yield shape unchanged — scores are additive only.
- Q8 (notifications) 422 on unsupported language + 5-language template coverage
  behavior unchanged after the import dedupe.
- `language_codes` table + `elevenlabs_voice_id` column already exist — this
  phase does NOT seed or expose them (Docker/CI follow-on, noted in tracker).
- Stdlib-only at module level (`py -3.14`); `compileall` lint gate; full
  regression baseline 371 must hold + new tests.

## 7. Implementation record (pending)

- RED commit: —
- feat commit: —
- docs commit: —