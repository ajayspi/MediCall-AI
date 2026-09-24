# SPEC: Dashboards — Clinic (7-tab) + Admin (9-view)

Status: **APPROVED 2026-09-24** — user sign-off via question tool:
**D1** = clinic nav exactly 7 tabs, Settings in header;
**D2** = scope = dashboards + tokens + minimal toolchain fix;
**D3** = Tailwind v4 CSS-first migration. Implementation authorized on this
branch (worktree `.worktrees\gd-dashboards`, branch `gd-dashboards` off
`g4-voice` tip `503fad6`).

## 1. Goal

Deliver the two dashboard fronts of MediCall AI — the clinic operator
dashboard (7 tabs) and the platform admin panel (9 views) — as working Next.js
shells with medical mock data, plus the base design tokens and the minimum
shared components both shells need. This is the "clinic (7-tab) + admin
(9-view) dashboards" step in the tracker queue (after G5 DONE).

While researching, the phase surfaced a **broken frontend toolchain** that must
be fixed in the same change or the dashboards cannot build at all (see §3).

## 2. Frontend state found (evidence, 2026-09-24, branch head)

| Finding | Evidence |
|---|---|
| Stack | Next 16.0.0, React 19, TS 5.3 strict, `@/*`→`./src/*`, Tailwind **^4.0.0** devDep |
| `globals.css` | Tailwind **v3** syntax (`@tailwind base/components/utilities`) against tailwindcss ^4 — v4 removed those directives → build broken |
| PostCSS | **No** `postcss.config.*` at all — Tailwind v4 needs `@tailwindcss/postcss` plugin → nothing processes CSS |
| `tailwind.config.js` | v3-style JS config, `primary` = sky-blue (`#0ea5e9`), only 5 shades (no 400, which code uses `text-primary-400`) — design spec mandates **medical teal** |
| Root `page.tsx` | 579-line TalkByte restaurant landing (Telnyx/Square/Stripe, $, "Australian kitchens", Mama's Pizzeria demo) |
| `(restaurant)/` | layout with 7 tabs (Orders/Menu/Billing = restaurant), branding "TalkByte"/"Mama's Pizzeria" |
| `(restaurant)/dashboard/page.tsx` | imports `@supabase/supabase-js` — **package not in package.json** (already broken); restaurant KPIs $/orders |
| `(admin)/` | layout with 9 links (Restaurants/Users/Analytics leftovers) but **zero page files** — every admin link 404s |
| `next.config.js` | `images.domains: ['your-supabase-project.supabase.co']` leftover |
| package.json | has @tanstack/react-query, zustand, recharts, date-fns, lucide-react, clsx, tailwind-merge (fine, some used by later phases); NO supabase pkg; tailwind ^4 + postcss + autoprefixer (v2-era combo) |

Conclusion: the frontend as shipped cannot build. This phase fixes the
toolchain minimally (Tailwind v4 CSS-first) and rebuilds the dashboard area on
medical branding — no marketing site (separate later phase).

## 3. Scope

### 3.1 Toolchain fix (minimal, D3)
- `globals.css` → Tailwind v4: `@import "tailwindcss";` + `@theme` tokens
  (teal primary scale, semantic red/amber/green, radius/spacing/motion, dark
  `color-scheme` default), keep `.card`/`.btn-*` as `@layer components` with
  new tokens.
- New `postcss.config.mjs` with `@tailwindcss/postcss`.
- Delete `tailwind.config.js` (v4 is CSS-first).
- `package.json` devDeps: +`@tailwindcss/postcss`, −`autoprefixer` (v4 vendor-
  prefixes natively). Runtime deps untouched.
- `next.config.js`: remove `images.domains` Supabase entry (keeps `/api` proxy
  rewrite — backend routes phase consumes it).

### 3.2 Clinic dashboard — exactly 7 tabs (D1)
Route group `(clinic)/` (URLs at root): Dashboard `/dashboard`, Live Calls
`/live-calls`, Triage Queue `/triage-queue`, Appointments `/appointments`,
Prescriptions `/prescriptions`, Patients `/patients`, Analytics `/analytics`.
Settings moves to the header user menu (not a sidebar tab) — this is what makes
the count 7; the design-system spec lists 8 items but titles it "7 tabs", so
the discrepancy is resolved here rather than guessed (D1).

### 3.3 Admin panel — exactly 9 views (design-spec list, unchanged)
Route group `(admin)/` under `/admin`: Overview `/admin`, Live Monitor
`/admin/live-monitor`, Clinics `/admin/clinics`, Doctors `/admin/doctors`,
Patients `/admin/patients`, Revenue `/admin/revenue`, Billing `/admin/billing`,
Infrastructure `/admin/infrastructure`, Audit `/admin/audit`.

### 3.4 Shared components (minimum set both shells need)
`frontend/src/components/`:
- `nav.ts` — single source for the 7 clinic + 9 admin nav items (labels, hrefs,
  lucide icon names) — tested
- `sidebar.tsx`, `header.tsx` — drive both layouts from `nav.ts`
- `card.tsx`, `stat-card.tsx`, `badge.tsx`
- `language-badge.tsx` (hi/en/ta/te/bn), `severity-badge.tsx`
  (green/amber/red/critical), `call-state-badge.tsx` (the 9 G3 states)
- `mock.ts` — mock medical data (Indian numbers +91, Indian names, clinics,
  complaints, ₹ revenue, provider statuses)

### 3.5 Pages (16 files, all "use client" where interactive or plain)
- `(clinic)/layout.tsx` + 7 pages; `(admin)/layout.tsx` + 9 pages
- Each page: stat cards + tables/badges/cards from mock data — **no API calls,
  no data fetching** (wiring is the API-routes phase), **no Supabase**
- Branding: "MediCall AI"; clinic shell user = "Clinic Admin · City Care
  Clinic" (single-clinic MVP, mirrors `DEFAULT_CLINIC_ID`); admin shell =
  "Platform Admin"

### 3.6 Root landing + leftovers
- `page.tsx` → minimal branded placeholder ("MediCall AI — coming soon", links
  to `/dashboard` and `/admin`). Marketing site is a later design-system phase.
- Delete `(restaurant)/`, `(admin)/` old group + old dashboard page.

## 4. Non-Goals (this phase)

- Marketing site (`/features`, `/pricing`, `/docs`, `/login`, `/signup`,
  `/demo`), full `src/design-system/` directory + 15+ components, RTL, light
  theme toggle — all later design-system phase(s).
- Real charts wiring (recharts stays in package.json for the analytics phase).
- Data layer / API calls (routes phase).
- Runtime build verification (no node_modules on this PC — OneDrive + MAX_PATH;
  `next build` runs in Docker/CI; frontend Dockerfile exists).

## 5. Test plan (RED first — `backend/tests/test_dashboards.py`, stdlib)

Background: same pattern as G1–G5 — this PC cannot `npm install`, so the
acceptance tests are Python source/state checks over `frontend/` files
(`FRONTEND = BACKEND.parent / "frontend"`).

RED pre-fix (each maps to a current gap): `(restaurant)` + old `(admin)` exist;
no `(clinic)` group; 0 admin pages; TalkByte strings everywhere; root landing
restaurant; `@tailwind` v3 directives; no postcss config; supabase image domain.

GREEN checks:
1. `(restaurant)` and old `(admin)` route groups **deleted**
2. `(clinic)/layout.tsx` exists; clinic nav = exactly **7** hrefs
   {dashboard, live-calls, triage-queue, appointments, prescriptions,
   patients, analytics}; Settings **not** among them
3. `(admin)/layout.tsx` exists; admin nav = exactly **9** hrefs
   {admin, admin/live-monitor, admin/clinics, admin/doctors, admin/patients,
   admin/revenue, admin/billing, admin/infrastructure, admin/audit}
4. All **16** page files exist (7 clinic + 9 admin)
5. No restaurant leftovers across `frontend/src`: TalkByte, Mama's, Margherita,
   ORD-, Aussie/Australian, Telnyx, Square, Stripe, "Restaurant", `+61`, `$`
   (revenue must be ₹)
6. Root `page.tsx`: branded "MediCall AI", no Supabase, no TalkByte
7. `globals.css`: `@import "tailwindcss"` + `--color-primary-*` teal tokens +
   severity tokens; **no** `@tailwind` v3 directives
8. `postcss.config.mjs` exists and names `@tailwindcss/postcss`;
   `tailwind.config.js` deleted
9. `package.json`: has `@tailwindcss/postcss`, no `autoprefixer`, no supabase
10. `next.config.js`: no `supabase` string
11. `language-badge.tsx` covers hi/en/ta/te/bn; `severity-badge.tsx` covers
    green/amber/red/critical; `call-state-badge.tsx` covers the 9 G3 states
12. `nav.ts` is the single source (layouts reference it, not inline arrays)

Verify after implementation:
- `python3 tests/test_dashboards.py` GREEN
- Full backend regression (G1+G2 11/11, G3 9/9, G4 33/33, G5 18/18) + 
  `py_compile` clean (backend untouched, but confirm no regression)
- Manual: frontend files parse readable; real `next build` → Docker/CI stage

## 6. Decisions (signed off 2026-09-24)

- **D1 — Clinic nav count**: ✅ **7 tabs, Settings → header menu** (resolves
  the design-spec "7 tabs" vs 8 listed items).
- **D2 — Scope**: ✅ **dashboards + tokens + shared components + minimal
  toolchain fix** (this spec). Full design-system spec (marketing site, RTL,
  light theme) stays queued.
- **D3 — Toolchain**: ✅ **Tailwind v4 CSS-first migration** (globals.css
  `@theme`, `@tailwindcss/postcss`, delete JS config).

## 7. Risks

| Risk | Mitigation |
|---|---|
| Can't `npm install`/build locally (OneDrive, no node_modules) | Source-level tests via Python; build verification explicitly in Docker/CI next stage; all Token/Tailwind patterns are standard v4 |
| Tailwind v4 API churn breaks a class silently | Tokens + components confined to a small, pinned surface; CI build is the gate |
| Scope creep toward marketing site | Non-goals §4 + D2 |

## 8. Sign-off

- **Status**: ☑ **APPROVED** (D1/D2/D3 as chosen — all recommended options)
- **Approver / date**: user, 2026-09-24 (question-tool sign-off)
- **Next after approval**: write `tests/test_dashboards.py` RED → implement
  (toolchain + tokens + components + 16 pages + deletions) → GREEN → commit on
  `gd-dashboards` → then API routes phase.