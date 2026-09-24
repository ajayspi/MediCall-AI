"""Dashboards acceptance tests: clinic (7-tab) + admin (9-view) shells (stdlib only).

RED before implementation (2026-09-24): frontend/ is restaurant + broken toolchain —
the `(restaurant)` route group exists with a dashboard page importing
`@supabase/supabase-js` (a package NOT in package.json); `(admin)` has a layout with
9 restaurant-era links but ZERO page files; root page.tsx is the 579-line TalkByte
landing; root layout metadata says "TalkByte AI"; globals.css uses Tailwind v3
`@tailwind` directives against a `tailwindcss ^4` dep with no postcss.config.* at all
(cannot build); tailwind.config.js is a v3 JS config with a sky-blue primary (spec
mandates medical teal); next.config.js whitelists a Supabase image domain; there is
no `(clinic)` group, no src/components/, no src/components/nav.ts.

GREEN after implementation (spec-dashboards-clinic-admin.md, D1/D2/D3 approved
2026-09-24): restaurant + Supabase + TalkByte leftovers gone; Tailwind v4 CSS-first
toolchain (@import "tailwindcss" + @theme tokens incl. teal primary + severity,
postcss.config.mjs with @tailwindcss/postcss, no JS tailwind config, no autoprefixer);
clinic route group `(clinic)` with exactly 7 nav tabs (D1 — Settings lives in the
header, not the sidebar) and 7 pages; admin real segment `admin/` (a `(admin)`
route group would resolve to bare `/...` paths and collide with the clinic
pages — fixed in g-ci) with exactly 9 views and 9 pages; shared components with nav.ts as single nav source, language
badge for hi/en/ta/te/bn, severity badge for green/amber/red/critical, call-state
badge for the 9 G3 states, medical mock data (+91, rupee); root page + layout
rebranded "MediCall AI".

Run: python3 tests/test_dashboards.py  (exit 0 = green)
"""
import json
import re
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
APP = SRC / "app"
COMPONENTS = SRC / "components"

GLOBALS_CSS = APP / "globals.css"
POSTCSS = FRONTEND / "postcss.config.mjs"
TAILWIND_JS = FRONTEND / "tailwind.config.js"
PACKAGE_JSON = FRONTEND / "package.json"
NEXT_CONFIG = FRONTEND / "next.config.js"

CLINIC = APP / "(clinic)"
ADMIN = APP / "admin"  # real URL segment: (admin) as a route group adds no
# path segment and would resolve to bare /... paths that collide with the
# clinic pages (caught by the first real `next build`, g-ci).
RESTAURANT_GROUP = APP / "(restaurant)"

CLINIC_TABS = [
    "/dashboard",
    "/live-calls",
    "/triage-queue",
    "/appointments",
    "/prescriptions",
    "/patients",
    "/analytics",
]
CLINIC_TAB_FILES = [
    ("dashboard", "page"),
    ("live-calls", "page"),
    ("triage-queue", "page"),
    ("appointments", "page"),
    ("prescriptions", "page"),
    ("patients", "page"),
    ("analytics", "page"),
]
ADMIN_VIEWS = [
    "/admin",
    "/admin/live-monitor",
    "/admin/clinics",
    "/admin/doctors",
    "/admin/patients",
    "/admin/revenue",
    "/admin/billing",
    "/admin/infrastructure",
    "/admin/audit",
]
ADMIN_VIEW_FILES = [
    ("", "page"),  # /admin overview -> admin/page.tsx (real segment)
    ("live-monitor", "page"),
    ("clinics", "page"),
    ("doctors", "page"),
    ("patients", "page"),
    ("revenue", "page"),
    ("billing", "page"),
    ("infrastructure", "page"),
    ("audit", "page"),
]

RESTAURANT_LEFTOVERS = (
    "talkbyte",
    "mama's",
    "margherita",
    "ord-0",
    "australia",
    "telnyx",
    "square",
    "stripe",
    "restaurant",
    "+61",
    "/admin/restaurants",
    "/admin/users",
)

G3_STATES = (
    "GREETING",
    "TRIAGE",
    "APPOINTMENT",
    "PRESCRIPTION",
    "COMPLETE",
    "ESCALATED",
    "DROPPED",
    "PAYMENT_SENT",
    "PAYMENT_EXPIRED",
)

LANGUAGES = ("hi", "en", "ta", "te", "bn")
SEVERITIES = ("green", "amber", "red", "critical")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def src_files() -> list:
    out = []
    for p in SRC.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".ts", ".tsx", ".css", ".js", ".mjs", ".json"}:
            out.append(p)
    return out


def nav_hrefs(const_name: str):
    """Extract { href: '...' } list from a `export const NAME: NavItem[] = [...]` block."""
    text = read(COMPONENTS / "nav.ts")
    m = re.search(rf"export const {const_name}.*?=\s*\[(.*?)\];", text, re.S)
    if not m:
        return None
    return re.findall(r'href:\s*"([^"]+)"', m.group(1))


class TestToolchain(unittest.TestCase):
    def test_globals_css_tailwind_v4_import(self):
        self.assertIn('@import "tailwindcss"', read(GLOBALS_CSS))

    def test_globals_css_no_v3_directives(self):
        self.assertNotRegex(read(GLOBALS_CSS), r"@tailwind\s+(base|components|utilities)")

    def test_teal_primary_tokens(self):
        css = read(GLOBALS_CSS)
        self.assertIn("--color-primary-400: #2dd4bf", css)
        self.assertIn("--color-primary-500: #14b8a6", css)
        self.assertIn("--color-primary-700: #0f766e", css)

    def test_severity_tokens(self):
        css = read(GLOBALS_CSS)
        for tone in ("green", "amber", "red", "critical"):
            self.assertIn(f"--color-severity-{tone}", css)

    def test_postcss_config_present_and_v4(self):
        self.assertTrue(POSTCSS.exists(), "postcss.config.mjs missing")
        self.assertIn("@tailwindcss/postcss", read(POSTCSS))

    def test_tailwind_js_config_removed(self):
        self.assertFalse(TAILWIND_JS.exists(), "tailwind.config.js should be deleted (v4 CSS-first)")

    def test_package_json_devdeps(self):
        data = json.loads(read(PACKAGE_JSON))
        dev = data.get("devDependencies", {})
        self.assertIn("@tailwindcss/postcss", dev)
        self.assertNotIn("autoprefixer", dev)

    def test_package_json_no_supabase(self):
        self.assertNotIn("supabase", json.dumps(json.loads(read(PACKAGE_JSON))).lower())

    def test_next_config_no_supabase_and_keeps_proxy(self):
        cfg = read(NEXT_CONFIG)
        self.assertNotIn("supabase", cfg.lower())
        self.assertIn("'standalone'", cfg)  # deploy shape intact
        self.assertIn("/api", cfg)  # backend proxy rewrite intact


class TestRestaurantCleanup(unittest.TestCase):
    def test_restaurant_group_deleted(self):
        self.assertFalse(RESTAURANT_GROUP.exists(), "(restaurant) route group must be deleted")

    def test_no_restaurant_strings_in_src(self):
        found = []
        for p in src_files():
            low = read(p).lower()
            for token in RESTAURANT_LEFTOVERS:
                if token in low:
                    found.append(f"{p.relative_to(ROOT)}: {token}")
        self.assertEqual([], found, "restaurant/TalkByte leftovers found:\n" + "\n".join(found))

    def test_no_dollar_money_amounts(self):
        found = []
        for p in src_files():
            money = re.findall(r"\$[0-9]", read(p))
            if money:
                found.append(f"{p.relative_to(ROOT)}: {money}")
        self.assertEqual([], found, "dollar money amounts found:\n" + "\n".join(found))

    def test_supabase_gone_from_frontend(self):
        haystacks = [read(p).lower() for p in src_files()] + [
            read(NEXT_CONFIG).lower(),
            read(PACKAGE_JSON).lower(),
        ]
        self.assertFalse([h for h in haystacks if "supabase" in h])


class TestClinicDashboard(unittest.TestCase):
    def test_clinic_layout_exists(self):
        self.assertTrue((CLINIC / "layout.tsx").exists(), "(clinic)/layout.tsx missing")

    def test_clinic_nav_exactly_seven(self):
        self.assertEqual(nav_hrefs("CLINIC_NAV"), CLINIC_TABS)

    def test_settings_not_a_clinic_tab(self):
        hrefs = nav_hrefs("CLINIC_NAV") or []
        self.assertNotIn("/settings", hrefs, "Settings must be in the header, not the sidebar (D1)")

    def test_clinic_seven_pages_exist(self):
        for cluster, name in CLINIC_TAB_FILES:
            self.assertTrue(
                (CLINIC / cluster / f"{name}.tsx").exists(),
                f"(clinic)/{cluster}/{name}.tsx missing",
            )

    def test_clinic_layout_uses_nav_single_source(self):
        text = read(CLINIC / "layout.tsx")
        self.assertIn("CLINIC_NAV", text)
        self.assertIn("@/components/nav", text)
        self.assertNotIn("href: \"/", text.replace('href="/dashboard"', ""))

    def test_clinic_header_settings_entry(self):
        text = read(CLINIC / "layout.tsx")
        self.assertIn('settingsHref="/settings"', text)

    def test_clinic_identity(self):
        text = read(CLINIC / "layout.tsx")
        self.assertIn("City Care Clinic", text)


class TestAdminDashboard(unittest.TestCase):
    def test_admin_layout_exists(self):
        self.assertTrue((ADMIN / "layout.tsx").exists(), "admin/layout.tsx missing (real /admin segment)")

    def test_admin_nav_exactly_nine(self):
        self.assertEqual(nav_hrefs("ADMIN_NAV"), ADMIN_VIEWS)

    def test_admin_nine_pages_exist(self):
        for cluster, name in ADMIN_VIEW_FILES:
            target = ADMIN / cluster / f"{name}.tsx"
            self.assertTrue(target.exists(), f"admin/{cluster}/{name}.tsx missing")

    def test_admin_layout_uses_nav_single_source(self):
        text = read(ADMIN / "layout.tsx")
        self.assertIn("ADMIN_NAV", text)
        self.assertIn("@/components/nav", text)

    def test_admin_identity(self):
        text = read(ADMIN / "layout.tsx")
        self.assertIn("Platform Admin", text)


class TestSharedComponents(unittest.TestCase):
    def test_nav_single_source_exists(self):
        self.assertTrue((COMPONENTS / "nav.ts").exists(), "src/components/nav.ts missing")
        self.assertIn("export const CLINIC_NAV", read(COMPONENTS / "nav.ts"))
        self.assertIn("export const ADMIN_NAV", read(COMPONENTS / "nav.ts"))

    def test_required_components_exist(self):
        required = (
            "sidebar.tsx",
            "header.tsx",
            "card.tsx",
            "stat-card.tsx",
            "badge.tsx",
            "language-badge.tsx",
            "severity-badge.tsx",
            "call-state-badge.tsx",
            "mock.ts",
        )
        for name in required:
            self.assertTrue((COMPONENTS / name).exists(), f"src/components/{name} missing")

    def test_language_badge_covers_five_languages(self):
        text = read(COMPONENTS / "language-badge.tsx")
        for code in LANGUAGES:
            self.assertRegex(text, rf"\b{code}\s*:", f"language '{code}' not keyed in language-badge")

    def test_severity_badge_covers_four_levels(self):
        text = read(COMPONENTS / "severity-badge.tsx")
        for tone in SEVERITIES:
            self.assertRegex(text, rf"\b{tone}\s*:", f"severity '{tone}' not keyed in severity-badge")

    def test_call_state_badge_covers_nine_g3_states(self):
        text = read(COMPONENTS / "call-state-badge.tsx")
        for state in G3_STATES:
            self.assertIn(state, text, f"G3 state {state} missing from call-state-badge")

    def test_mock_has_medical_india_flavour(self):
        text = read(COMPONENTS / "mock.ts")
        self.assertIn("+91", text)
        self.assertIn("₹", text)


class TestBranding(unittest.TestCase):
    def test_root_page_rebranded(self):
        text = read(APP / "page.tsx")
        self.assertIn("MediCall AI", text)
        self.assertNotIn("TalkByte", text)

    def test_root_layout_rebranded(self):
        text = read(APP / "layout.tsx")
        self.assertIn("MediCall AI", text)
        self.assertNotIn("TalkByte", text)

    def test_root_layout_supports_medical_font_meta(self):
        text = read(APP / "layout.tsx")
        self.assertIn("lang=\"en\"", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)