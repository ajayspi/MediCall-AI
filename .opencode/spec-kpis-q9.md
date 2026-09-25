# G6-Q9 MVP KPIs + Analytics — spec (DRAFT)

| | |
|---|---|
| **Phase** | G6-Q9: analytics — which KPIs are MVP, computed from existing tables (calls/appointments/payments) behind one identity-gated endpoint |
| **Tracker question** | "Analytics: which KPIs are MVP (call volume, triage mix, language dist, no-show, revenue)?" |
| **Branch** | `g-kpis` off `g-dpdp` tip `684a8ab` |
| **Status** | DRAFT → APPROVED (signed off 2026-09-25, question tool, Q1=A3 Q2=A2 Q3=A1 Q4=A1) → **GREEN** (implemented 2026-09-25; regression 519/519, compileall 0) |
| **Date** | 2026-09-25 |

## 0. Sign-off record (2026-09-25, question tool)

- **Q1=A3** — **7 KPIs**: volume (total / by_state / by_day /
  avg_duration_seconds) + resolution rate + triage mix + language dist +
  no-show rate + revenue (captured / refunded / by_kind / currency) +
  **notification delivery success** (per kind: sent / failed / total /
  success_rate) + the static market `benchmarks` context dict. The reminder
  *confirmation* rate stays out (needs campaign state not recorded yet).
- **Q2=A2** — **per-KPI endpoints**: one hander + path per KPI under
  `/api/analytics` (`/volume`, `/resolution`, `/triage`, `/language`,
  `/no-show`, `/revenue`, `/delivery`, plus `/benchmarks` for the static
  market context) — dashboard does N round-trips, no giant summary payload.
  Pure stdlib `services/analytics.py` shapes; `postgres.py` gets per-KPI
  async aggregates; all data rides existing RLS.
- **Q3=A1** — pure computed, no writes: read-only aggregates over
  calls/appointments/payments/notifications, computed live per request, zero
  schema writes, no materialization/caching; clinic-scoped (explicit
  `clinic_id` filter + RLS membership); identity-gated like every domain
  endpoint.
- **Q4=A1** — optional ISO `from`/`to` with defaults (`to = now`, `from =
  to − 30d`), 366-day cap, 422 on `from > to` / range > cap / unparseable;
  naive assumed UTC (same rule as `retention.retention_deadline`).

## 1. Market grounding (2026)

The tracker already listed the candidate KPIs; 2026 vendor/benchmark data
confirms them and supplies context targets the dashboard can show as
"vs benchmark" cards (display constants, never enforced thresholds):

| KPI | Market signal |
|---|---|
| **Call volume + resolution rate** | Interactly benchmark (Multifit §benchmark): 72% of requests resolved without front-desk; human-agent FCR benchmark is 70–79% (Hyro 2026 Benchmark Report); call containment (share of inbound calls resolved without transfer) is the healthcare-specific AI-agent KPI |
| **Triage mix** | Interactly/guardrail practice: severity distribution is the clinical-safety signal for escalation staffing (Multifit Analytics tab: "triage outcomes") |
| **Language distribution** | Multifit Analytics tab: "language dist" — drives agent/catalog coverage; India voice-AI context: global models 20–30% WER on Indian speech (Caller Digital, Voice of India benchmark 2026) makes per-language tracking material |
| **No-show rate** | India baseline 18–25% OPD (some segments 28–38%); voice-AI reminder programmes reduce to 8–12% (50–60% improvement; Caller Digital/Haptik/Ukti 2026) |
| **Reminder confirmation rate** | Outbound voice reminder confirmation benchmark 75–85% (Haptik) — **not** in MVP (needs reminder campaign state we don't record yet); documented as a Q10+ KPI |
| **Revenue** | Multifit Overview + Analytics tabs: revenue KPI + by-channel; missed-appointment revenue loss is the headline business case |

## 2. Proposed MVP KPI set + benchmark context (recommended A1, subject to Q1 sign-off)

One read-only, clinic-scoped, period-bounded summary — the exact payload the
Multifit Overview/Analytics tabs consume:

```
GET /api/analytics?clinic_id={uuid}&from=2026-08-26&to=2026-09-25   (identity-gated)
→ {
  "period": {"from": …, "to": …, "days": 31},
  "calls": {
    "total": 0, "by_state": {9 states…}, "by_day": {"2026-08-26": n…},
    "avg_duration_seconds": 0.0 | null,
    "resolution_rate": 0.0 | null,          # completed / terminal, see §5
    "triage_mix": {"green": n, "amber": n, "red": n, "critical": n, "untriaged": n},
    "language_dist": {"hi": n, "en": n, "ta": n, "te": n, "bn": n, "unknown": n},
  },
  "appointments": {"no_show": n, "completed": n, "cancelled": n, "terminal": n, "no_show_rate": 0.0 | null},
  "revenue": {"captured": 0.0, "refunded": 0.0, "by_kind": {"consultation": 0.0, "refill": 0.0, "subscription": 0.0}, "currency": "INR"},
  "benchmarks": {…}   # market context cards (see §5), static constants
}
```

## 3. Deliverables

- **A** — branch `g-kpis` off `g-dpdp` tip + this spec APPROVED
- **B** — RED contract `backend/tests/test_kpis_q9.py` (structural + behavioral;
  mirrors the Q2/Q4 suite helpers: fn_block, module_imported_names, endpoint_set)
- **C** — stdlib `backend/app/services/analytics.py` (pure):
  `no_show_rate`, `resolution_rate`, `shape_summary` (raw aggregates → payload),
  period helpers (default window, 366-day cap, naive→UTC), `BENCHMARKS` dict;
  import roots ⊆ {datetime, collections, typing}
- **D** — `backend/app/db/postgres.py`: async `compute_kpis(clinic_id, from_, to)`
  — SQLAlchemy `func.count`/`func.sum` groups over `Call`/`Appointment`/`Payment`
  (window + clinic_id filter; RLS applies because queries run as the app user)
- **E** — `backend/app/api/analytics.py` — **10th router**, prefix
  `/api/analytics`, single `GET ""` handler `get_analytics_summary_ep`
  (clinic_id required; from/to optional; identity-gated via
  `Depends(get_current_user)`; 422 on bad params)
- **F** — `main.py` registers the analytics router
- **G** — baseline `backend/tests/test_api_routes.py` contract grows 9 → 10
  (ROUTER_MODULES, EXPECTED_ENDPOINTS, "all nine routers" → "all ten")
- **H** — docs: `03-api-contracts.md` (Analytics node + note; ConsentGuard-style
  guard line for 422 period rules), `scripts/smoke_api.py` analytics check
  (demo tenant), `01-er.md` note only (no schema change)
- **I** — tracker record + gotchas, HANDOVER (Q9 DONE, open list → Q10),
  spec §7 GREEN
- **J** — verification: Q9 suite GREEN → full regression 488 + N ALL PASS →
  `compileall` exit 0

## 4. Definitions pinned (RED enforces these)

- **Window**: `from`/`to` optional ISO-8601 (date or datetime); defaults
  `to = now`, `from = to − 30d`; cap **366 days**; 422 on `from > to`,
  range > cap, or unparseable; naive datetimes assumed UTC (same rule as
  `retention.retention_deadline`).
- **Resolution rate**: `count(COMPLETE) / count(COMPLETE + DROPPED +
  ESCALATED + PAYMENT_EXPIRED)` over calls whose `started_at` is in-window.
  `PAYMENT_SENT` is in-progress (webhook advances it to COMPLETE), so it is
  excluded from the terminal denominator. `None` when denominator = 0.
- **Triage mix**: counts by `triage_severity` (green/amber/red/critical) +
  `untriaged` (null severity) over in-window calls.
- **Language dist**: counts by `caller_language` over in-window calls, with an
  `unknown` bucket for null.
- **No-show rate**: `count(no_show) / count(completed + cancelled + no_show)`
  over appointments whose `scheduled_at` is in-window and status is terminal
  (pending/confirmed future bookings excluded). `None` when denominator = 0.
- **Revenue**: payments whose `created_at` is in-window — `captured` sum,
  `refunded` sum, `captured` by `kind` (consultation/refill/subscription),
  `currency` surfaced from Payment.currency.
- **Benchmarks** (static, sourced, display-only):
  `resolution: {human_fcr_pct: [70, 79], interactly_virtual_receptionist_pct: 72}`;
  `no_show: {india_baseline_pct: [18, 25], voice_reminder_target_pct: [8, 12]}`;
  `confirmation: {voice_reminder_confirmation_pct: [75, 85]}`;
  `sources: […]` (2026: Hyro benchmark report, Caller Digital, Haptik, Ukti,
  Interactly/Multifit).

## 5. Out of scope (explicit)

- No new tables, no schema writes, no materialized KPI tables, no caching layer
  (computed live per request from the three existing RLS tables).
- No frontend/dashboard implementation (Multifit shells are layout-only, a
  later frontend phase consumes this endpoint).
- No reminder-confirmation KPI (needs campaign state we don't record; Q10+),
  no predictive no-show scoring, no HR/timesheet data, no exported KPIs.

## 6. Verification plan

1. RED: `py -3.14 -m unittest discover -s tests -p "test_kpis_q9.py"` → RED exit 1.
2. FEAT: suite → GREEN; full regression `discover -s tests` → 488 + N ALL PASS;
   `py -3.14 -m compileall -q app scripts tests main.py` → exit 0.
3. Docs: tracker + HANDOVER + spec §7 GREEN; re-run full suite → count unchanged.

## 7. Implementation record (2026-09-25)

- RED commit: `f553df2` — spec DRAFT→APPROVED landed with the suite
  (test_kpis_q9.py; 31 tests: 11 FAIL + 19 ERROR, exit 1).
- feat commit: `763ae22` (8 files, 609+/7−):
  - **services/analytics.py** (stdlib leaf, roots {datetime, collections,
    typing}): `resolve_period` (defaults 30d / cap 366d / naive→UTC /
    ValueError rules), `resolution_rate` (COMPLETE over the 4 terminal
    states; PAYMENT_SENT excluded), `no_show_rate`, `success_rate`,
    `shape_volume`, `shape_delivery`, `BENCHMARKS` (market context cards).
  - **postgres.py**: `func` added to the sqlalchemy import; 7 per-KPI async
    aggregates (compute_volume / resolution / triage / language / no_show /
    revenue / delivery) — read-only rollups filtered clinic_id + window,
    riding the existing RLS (pure computed, zero writes).
  - **app/api/analytics.py** — **10th router**, prefix /api/analytics: one
    GET per KPI (/volume /resolution /triage /language /no-show /revenue
    /delivery) + /benchmarks (static market context, no period params); all
    identity-gated; 422 on bad period. main.py registers it; test_api_routes
    contract grown 9→10 routers.
  - **smoke/docs**: smoke_api.py analytics checks (volume 200, benchmarks
    200, bad range 422); 03-api-contracts.md Analytics node + PeriodGuard +
    note + 10-router note; 01-er.md note (no new entities).
- docs commit: — (this session, next)
- Baseline moved 488 → 519 (31 new). 519/519 ALL PASS, compileall 0.