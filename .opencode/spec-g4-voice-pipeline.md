# SPEC: G4 — Voice Pipeline (Exotel/Knowlarity/Twilio-India + medical LiveKit agent)

Status: **PENDING SIGN-OFF** (drafted 2026-09-24). Approval unlocks implementation
on branch `g4-voice` (worktree `.worktrees\g4-voice`, startup verified GREEN on
2026-09-24: G1+G2 11/11, G3 9/9, py_compile clean).

## 1. Goal

Replace the last restaurant-flavored code in the voice path with the approved
Indian Medical Call Center pipeline (locked decisions in
`spec-idea-refinement-gaps.md` §3/§4):

- `app/api/voice.py`: Telnyx-US webhook (`call_control_id`, `restaurant_id`,
  "finalize order") → **Exotel + Knowlarity + Twilio-India** webhooks → LiveKit
  SIP room dispatch, `clinic_id`, 5-language tag (`hi/en/ta/te/bn`), transcript
  save to `calls.transcript`, escalation path.
- `app/services/livekit_agent.py`: "Mama's Pizzeria" / `order_items` /
  `TAKING_ORDER` / `rag_menu` → **medical agent** driven by the canonical state
  machine (`app/models/call.py`, G3), triage severity, appointment / prescription
  refill intents, escalation, 5-language STT/TTS selection.

Everything stays **stdlib-testable on this PC** (no fastapi/sqlalchemy/livekit/
openai/websockets on PATH — see §6 test strategy). Live provider/LiveKit calls
and WebSocket audio are wired but exercised only in Docker/CI (same pattern as
`main.py` lifespan `init_db`).

## 2. Non-Goals (this task)

- Outbound dialing / provider REST call-out APIs, recording egress
  (LiveKit → MinIO/S3, G6-Q6 open), SMS/WhatsApp follow-ups (G6-Q8 open),
  payment links (G6-Q5 open), consent/DPDP flags (G6-Q2 open), TEN/Bolna
  fallback stacks, frontend live-call views, RAG/pgvector transcript embeddings.
- No `.git` in Talkbyte / Talkbyte_clone (never touches them — rule 5).

## 3. Webhook contract (evidence-backed 2026-09-24)

Vendor payload shapes verified from public docs (Exotel developer docs
"Webhooks & Callbacks" + StatusCallback reference; Knowlarity SR / hook-api
guide + audio-streaming docs; Twilio standard callback params). Parsers are
written **defensively** (multi-alias field resolution) because provider payloads
vary by product line (Exotel Voice v1 vs v2/CCM, Knowlarity SR vs Knowlus).

All three providers normalize to one internal shape:

```python
@dataclass
class ProviderEvent:
    provider: str            # "exotel" | "knowlarity" | "twilio"
    event_type: str          # "call.initiated" | "call.answered" | "call.hangup" | "call.dropped" | "ignored"
    call_sid: str
    caller_number: str       # E.164-normalized (leading +91 etc.)
    inbound_number: str      # clinic/IVR number the caller dialed ("" if absent)
    language: str = ""       # from provider DTMF digit (Knowlarity `extension`, Twilio `Digits`) — "" = agent decides
    started_at: str = ""     # ISO/raw provider timestamp
    duration_seconds: int = 0
    recording_url: str = ""
    raw: dict                # full provider body for debug/forwarding
```

| Provider | Endpoint (prefix `/api/voice`) | Content type | Key fields | Normalized mapping |
|---|---|---|---|---|
| Exotel | `POST /webhook/exotel` | JSON | `CallSid`, `EventType` (`ringing`/`answered`/`terminal`), `Status` (`completed`/`failed`/`busy`/`no-answer`), `From`, `To`, `ConversationDuration`, `Direction`, `RecordingUrl` | `ringing`→initiated, `answered`→answered, `terminal`+`completed`→hangup, `terminal`+`no-answer`/`busy`/`failed`→dropped |
| Knowlarity | `POST /webhook/knowlarity` | form | `callid`, `caller_id`, `dispnumber`, `extension`, `action`, `start_time`/`end_time`, `resource_url`, `call_duration` | `action=phone` with start→initiated, end-of-call post→hangup/dropped |
| Twilio | `POST /webhook/twilio` | form | `CallSid`, `CallStatus` (`ringing`/`in-progress`/`completed`/`busy`/`no-answer`/`failed`/`canceled`), `From`, `To`, `Digits`, `CallDuration` | `ringing`→initiated, `in-progress`→answered, `completed`→hangup, `busy`/`no-answer`/`failed`/`canceled`→dropped |

Language decision order: provider DTMF digit (`extension`/`Digits`: 1=hi, 2=en,
3=ta, 4=te, 5=bn) → caller-ID heuristic (weak; see D3) → `DEFAULT_CALLER_LANGUAGE`
env (recommend `hi`, spec-micc-india lists Hindi as primary).

## 4. Files

| File | Change |
|---|---|
| `app/services/telephony.py` | **NEW, stdlib-only.** `ProviderEvent` dataclass + `parse_exotel(body)`, `parse_knowlarity(form)`, `parse_twilio(form)`, `normalize_phone(num)`, `language_from_digit(digit)`. Defensive aliases (e.g. sid := `CallSid`/`callid`/`call_id`; caller := `From`/`caller_id`/`caller_number`). |
| `app/services/agent_logic.py` | **NEW, stdlib-only.** Medical conversation brain: `system_prompt(...)`, `MEDICAL_FUNCTIONS` (single source of truth for LLM function schema), `apply_intent(call, fn_name, args)` (validates via `models/call.py` transitions), `append_transcript(...)`, `should_escalate(severity)`, `stt_language_tag(lang)` (`hi→hi-IN` …), `tts_voice_id(lang, env_voices)`, `language_for_room(metadata, default)`. |
| `app/api/voice.py` | Rewrite: 3 provider webhook routes + `POST /livekit-agent-start` (`clinic_id`, `call_sid`, `caller_number`, `language`) + `POST /call-completed` (agent→API transcript persist). Removes Telnyx payload, `restaurant_id`, dead `/stt` stub. Dispatch + LiveKit REST calls isolated behind small async functions (Docker/CI-exercised). |
| `app/services/livekit_agent.py` | Rewrite: connect → read room metadata (`clinic_id`, `call_sid`, `caller_number`, `language`, `call_id`) → greet in language → loop STT/LLM/TTS using `agent_logic` → apply intents to `CallState` → hangup → post `/call-completed` with transcript. No restaurant strings. |
| `app/services/llm.py` | Medical system prompt template + `FUNCTIONS = agent_logic.MEDICAL_FUNCTIONS`; `generate_response` takes medical params. (Imports stay third-party; tested via ast/source checks.) |
| `app/services/stt.py` | `language` param: URL uses `language=<tag>` (default `hi-IN`), drop hardcoded `en-AU`. |
| `app/services/tts.py` | `voice_for(lang)` map from `ELEVENLABS_VOICE_ID_{HI/EN/TA/TE/BN}` envs (already in `.env.example`), fallback to `ELEVENLABS_VOICE_ID`. |
| `app/db/postgres.py` | Add `update_call_transcript(call_id, transcript, ended_at=None, duration_seconds=0) -> bool` (transcript save path for `calls.transcript`). |
| `tests/test_g4_voice.py` | **NEW** — see §6. |
| `.env.example` | Add `DEFAULT_CALLER_LANGUAGE=hi` (+ doc comment). No other new vars needed. |

`backend/main.py` unchanged (voice router already mounted at `/api/voice`).

## 5. Behavior (expected after GREEN)

1. `POST /api/voice/webhook/{exotel|knowlarity|twilio}` parses provider payload →
   normalized `ProviderEvent`; `call.initiated`/`answered` create/open the call
   session + respond 200 with LiveKit room name; terminal events finalize
   (`ended_at`, `duration_seconds`).
2. Agent joins room, plays language IVR when no provider digit, runs
   GREETING→TRIAGE→APPOINTMENT/PRESCRIPTION→(PAYMENT_SENT later)/COMPLETE with
   ESCALATED/DROPPED exits via the G3 state machine; transcript accumulates
   `{"role","text","language"}` entries; hangup → `/call-completed` persists.
3. Triage RED/CRITICAL or explicit caller ask → `ESCALATED`,
   `escalated_to_human=True`, "connecting you to a specialist" message (PSTN
   warm-transfer stubbed, see D2).

## 6. Test plan (RED first — `backend/tests/test_g4_voice.py`, stdlib-only)

Pre-fix RED expectations (each maps to a current gap, like G1–G3 records):

1. Source checks (`ast.parse` + string): `voice.py` contains no `Telnyx`/
   `telnyx`/`call_control_id`/`restaurant_id`/`finalize order`; contains the 3
   provider route strings + `livekit-agent-start` + `call-completed`.
2. `livekit_agent.py`: no `Mama's Pizzeria`/`order_items`/`rag_menu`/
   `TAKING_ORDER`/`restaurant`; imports from `app.services.agent_logic`.
3. `llm.py`: no `{restaurant_name}`; has `set_triage_severity`,
   `book_appointment`, `prescription_refill`, `escalate`, `end_call`.
4. `stt.py`: no `en-AU`; accepts language tag. `tts.py`: voice map by language.
5. `postgres.py` (ast): has `update_call_transcript` touching `transcript`,
   `ended_at`, `duration_seconds`.
6. Behavioral (import `telephony.py` + `agent_logic.py` + `models/call.py`
   directly — all stdlib): parser fixtures for each provider → correct
   `ProviderEvent` incl. E.164 normalization + event mapping + ignored-unknown;
   `language_from_digit` 1..5 → hi/en/ta/te/bn, 0/9 → default; `agent_logic`
   prompt is medical (no restaurant words, contains clinic name + state);
   `apply_intent` respects `CallState` transitions (invalid rejected, escalate→
   ESCALATED, book_appointment→APPOINTMENT, prescription_refill→PRESCRIPTION);
   `append_transcript` shape; `should_escalate` RED/CRITICAL True, GREEN/AMBER
   False; `stt_language_tag` map; `tts_voice_id` env map + fallback;
   `language_for_room` metadata/IVR override + default.

Verify commands after implementation (run from `backend\`):
`python3 tests/test_g1_g2.py`, `python3 tests/test_g3_state_machine.py`,
`python3 tests/test_g4_voice.py` (all exit 0), then
`python3 -m py_compile main.py app/api/voice.py app/services/livekit_agent.py
app/services/telephony.py app/services/agent_logic.py app/services/stt.py
app/services/tts.py app/services/llm.py app/db/postgres.py app/models/call.py`.
Docker/CI stage (deferred): real HTTP webhook round-trips per provider, live
Deepgram/ElevenLabs/OpenAI calls, LiveKit room lifecycle.

## 7. Decisions needed before/at sign-off

- **D1 — transcript write path** (recommended): agent POSTs `/call-completed`
  (JSON transcript + call_id) → `voice.py` persists via `update_call_transcript`.
  Keeps DB access in the API layer and the handler stdlib-testable. Alternative
  (rejected): agent imports `postgres.py` directly — couples worker to DB
  sessions and can't be run on this PC.
- **D2 — escalation MVP** (recommended): agent marks `ESCALATED` +
  `escalated_to_human=True`, speaks "connecting you to a specialist", emits a
  room event for the operator UI. Real PSTN warm-transfer (provider transfer API
  call) is stubbed + deferred to integration. OK?
- **D3 — default language** (recommended): `hi` (spec-micc-india: Hindi primary),
  env-overridable `DEFAULT_CALLER_LANGUAGE`. OK?

## 8. Risks

| Risk | Mitigation |
|---|---|
| Vendor payload drift (Exotel v1 vs v2/CCM, Knowlarity SR vs Knowlus) | Defensive multi-alias parsers + `raw` passthrough; per-provider fixtures documented in §6; live payload sampling at integration stage |
| G3 state machine too strict for agent turns | `apply_intent` returns (allowed, new_state) and agent LLM stays within machine; ESCALATED/DROPPED are exits — agent ends call |
| Transcript loss on agent crash | `/call-completed` idempotent (keyed by call_id); hangup webhook also persists any session transcript as fallback |
| Agent/stdlib boundary leaks (agent imports livekit in untested path) | All logic in `agent_logic.py` (stdlib); `livekit_agent.py` is thin glue, source-checked only |

## 9. Sign-off

- **Status**: ☐ APPROVED / ☐ CHANGES REQUESTED (D1/D2/D3 answers)
- **Approver / date**:
- **Next after approval**: write `tests/test_g4_voice.py` RED → implement files
  → GREEN + py_compile → commit on `g4-voice`.