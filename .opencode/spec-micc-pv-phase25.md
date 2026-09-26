# SPEC: MICC/PV Module — Phase 2.5 (PVOIC frontend, DRAFT)

**Base**: `.opencode/spec-micc-pv-phase2.md` (Phase 2 IMPLEMENTED & VERIFIED). This slice turns the
approved 2E read-only API surface (dashboard snapshot, PSUR schedule, audit trail, case queue) into
a PVOIC (PV/Medical Information Call Centre) console in the frontend. **Pure frontend: zero backend,
schema, or contract-suite changes** (see Non-Goals). Follows the house RED-first ritual: pinning
tests live in `backend/tests/` (there is no JS test framework by design).

## Goal

A read-only PVOIC console at `/pv` — case-clocks overview, compliance case queue, PSUR schedule, and
PV audit trail — for the Indian MAH / licensed clinic staff role, rendered with the existing design
system (`.card`, `StatCard`, `Badge`/`SeverityBadge`, hand-rolled tables, Tailwind v4 tokens).

## Non-Goals (slice 2.5)

- **No backend changes.** No new routes, no schema, no edits to `test_api_routes.py` /
  `test_uml_diagrams.py` (`API_PATHS` static tuple untouched), no `requirements.txt`.
- **No case writing / export actions.** Case intake stays API/voice-only; the `.e2b.xml` route is
  service-token-guarded, so a download button is a follow-up slice that first makes the GET
  identity-gated for staff. Queue is read-only here.
- **No clinic-selector UX.** Reuse the existing `clinicId()` env helper (`NEXT_PUBLIC_CLINIC_ID`),
  exactly like every other wired page; a membership picker is a follow-up.
- **No live ticking countdown.** Clocks come from the server-computed snapshot
  (`days_remaining` / `hours_remaining` / `days_overdue`), refreshed via react-query
  `refetchInterval` (60 s) + a "last updated {generated_at}" caption. No `setInterval` machinery
  (none exists anywhere in the app today).
- **No new PyPI/npm deps.** recharts/zustand/lucide stay unused; hand-rolled bars like `analytics`.

## Decisions (from frontend exploration 2026-09-26)

1. **Third shell, not an extra tab.** `backend/tests/test_dashboards.py` pins `CLINIC_NAV` to exactly
   7 hrefs and `ADMIN_NAV` to exactly 9 — an 8th clinic tab would break the suite. The PVOIC console
   is a real segment `app/pv/` with its own `layout.tsx` + sidebar (NOT a `(pv)` route group — bare
   paths would collide with the pinned arrays) and a new `PVOIC_NAV` export in `components/nav.ts`
   (Comment in nav.ts: "Do not inline nav arrays in layouts"). `PVOIC_NAV` is a NEW array; the
   clinic/admin arrays are untouched.
2. **Identity**: `PVOIC_USER = {name: "PVOIC Officer", org: "MediCall PV & Medical Information"}` in
   `pv/layout.tsx`, mirroring the hardcoded identities of the other two shells. `RequireAuth` +
   Bearer from `localStorage` (`medicall_token`) via `authFetch` / the `lib/api.ts` pattern.
3. **Mock parity**: `USE_MOCK=auto` (default) means empty API → fallback fixtures from
   `components/mock.ts`. The PV hooks get their own fixture set there (keeping `+91` / `₹`, never
   adding `$<digit>` — `test_dashboards.py` pins both).
4. **Tokens**: new pages use ONLY tokens that exist in `globals.css` (`primary-50..950`,
   `background`, `surface`, `severity-*`, component classes). Do NOT copy the pre-existing
   `login/page.tsx` styling bug (`bg-card`/`text-foreground`/`bg-muted`/… — those tokens don't
   exist); that page is out of scope, not a pattern to inherit.

## Pages + API mapping (all identity-gated, `?clinic_id=` from env helper)

| Page | Route | API | Renders |
|---|---|---|---|
| Overview | `app/pv/page.tsx` | `GET /api/pv/dashboard?clinic_id=` | KPI tiles (total + by_type ae/pqc/mi, overdue count); **clocks block**: overdue list (days_overdue red badge) + upcoming-48h (hours_remaining + status); PQC pipeline by investigation status + disposition; PSUR "due now" summary; audit by_event_type digest |
| Case queue | `app/pv/cases/page.tsx` | `GET /api/pv/cases?clinic_id=&status=&serious_only=` | Status filter chips + serious-only toggle; table: case type badge, product/patient, event/verbatim summary, seriousness, deadline cell (days_remaining + overdue red), status badge |
| PSUR schedule | `app/pv/psur/page.tsx` | `GET /api/pv/dashboard/psur?clinic_id=` | Per-product cards: window label ("6-monthly #3" / "annual #5"), next-due date, due-now badge |
| Audit trail | `app/pv/audit/page.tsx` | `GET /api/pv/audit?clinic_id=&days=30` | Event table: event_type → severity tone, timestamp, clinic/entity, detail — read-only |

**Hooks** (in `lib/api.ts`, house style): `usePvDashboard(clinicId)`, `usePvPsur(clinicId)`,
`usePvAudit(clinicId, days)`, `usePvCases(clinicId, status?, seriousOnly?)` — each the
`authFetch` + react-query + `useFallback` (auto-mode) pattern used by every wired page; snake_case
API type → view type → `Kpi[]` mapping as in `admin/page.tsx` / `(clinic)/analytics/page.tsx`.
`PVOIC_NAV` = `[{href:"/pv",...}, {href:"/pv/cases",...}, {href:"/pv/psur",...}, {href:"/pv/audit",...}]`
(exactly 4), mirroring the approved 2E endpoints.

## Acceptance criteria

- [ ] `backend/tests/test_pv_frontend.py` (NEW, RED first, house style): pins `PVOIC_NAV` hrefs =
      the exact 4-list above; each `/pv/*` page file exists and is `"use client"`; each hook name +
      its exact endpoint string exists in `lib/api.ts`; the 4 mock fixture keys exist in `mock.ts`;
      new `pv/**/*.tsx` pages contain zero nonexistent Tailwind tokens (structural check against the
      `@theme` token list — the same class of guard `login/page.tsx` currently fails) and no
      `$<digit>`.
- [ ] `CLINIC_NAV` / `ADMIN_NAV` arrays and `test_dashboards.py` untouched & green (7/9 pins hold).
- [ ] All existing Python suites green: `py -3.14 -m unittest discover -s tests -p "test_*.py"`
      from `backend` (1038 baseline + new pins), then `py -3.14 -m compileall .`.
- [ ] Frontend gates green: `cd frontend && npm ci && npm run lint && npm run build` (exit 0, no
      TS errors) — the house CI commands.
- [ ] Determinism: pages render from fixtures in default `auto` mode (no empty shells).
- [ ] No new npm/PyPI deps; recharts/zustand/lucide still unused; `requirements.txt` untouched.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| `test_dashboards.py`'s page-exists assertions assume only clinic/admin pages (e.g. counts `src/app` page files) | New `/pv` pages break a count | Implementation reads the exact assertions FIRST (RED run before writing any page); the pinning test file and any deliberate count updates ship with the slice and are reviewed in the commit |
| `npm run build` (Next 16 standalone) is slow / exposes TS strictness | Gate friction | Accept the house CI gate as the verify; fix TS errors at root; report exact output |
| `USE_MOCK=auto` empty-shell regression in default dev | Overview looks broken | Fixtures mandatory for all 4 hooks; pinned by test |
| Scope creep into exports / writing | Slice grows | Queue and page surfaces are read-only by Non-Goals; export + detail + clinic-selector are named follow-ups, not built |

## Spec Status

**Status**: **IMPLEMENTED & VERIFIED — 2026-09-26** (approved via "continue"; fresh-session
implementation, scheduler re-verified). Commit `7cb3c2a` (9 files):

- `frontend/src/app/pv/` — real-segment shell (`layout.tsx`, `PVOIC_USER` identity) + 4 pages
  (`page.tsx` overview, `cases/page.tsx`, `psur/page.tsx`, `audit/page.tsx`), all `"use client"`
- `frontend/src/components/nav.ts` — new `PVOIC_NAV` = `[/pv, /pv/cases, /pv/psur, /pv/audit]`
  (CLINIC_NAV/ADMIN_NAV untouched; test_dashboards.py 7/9 pins hold)
- `frontend/src/lib/api.ts` — `usePvDashboard` (refetchInterval 60 s), `usePvPsur`, `usePvAudit`,
  `usePvCases` — authFetch + react-query + USE_MOCK auto-fallback + FixtureData shape
- `frontend/src/components/mock.ts` — 4 PV fixture sets (`pvDashboard/pvPsur/pvAudit/pvCases`);
  also repaired pre-existing `mock.ts` BOM/mojibake corruption (PowerShell round-trip artefact)
- `backend/tests/test_pv_frontend.py` — 34 pinning tests (RED first): nav list, page files +
  `"use client"`, hook→endpoint strings, mock keys, token allowlist vs `globals.css @theme`,
  no `$<digit>`, nav-array distinctness

**Gates (scheduler re-verified)**: backend `unittest` **1072/1072 exit 0**, `compileall` exit 0;
frontend `npm run lint` + `npm run build` exit 0 (24 static pages incl. the 4 `/pv` pages).
Zero backend changes; zero new deps.

**Deviations recorded**: case queue shows `product_id` (not an invented name); audit table shows
`description` verbatim (no fabricated entity column); `/pv/cases` returns AE-only today (PQC/MI
tones present but defensive); `clinicId()` exported (needed for filtered queue); hand-built query
string so `clinic_id=` is literal on the wire.

**Follow-ups (NOT in this slice)**: case-detail page + identity-gated E2B download (needs one
backend tweak: make the `.e2b.xml` GET staff-identity-accessible), clinic-selector UX, live
countdown polish.