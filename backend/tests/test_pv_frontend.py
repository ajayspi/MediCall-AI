"""PVOIC console acceptance tests: the /pv third shell (stdlib only).

RED before implementation (2026-09-26, spec-micc-pv-phase25.md, approved):
there is NO `src/app/pv` segment at all - the PVOIC (PV / Medical Information
Call Centre) officer has nowhere to work. `components/nav.ts` exports only
CLINIC_NAV and ADMIN_NAV, `src/lib/api.ts` has no /api/pv hook, and
`components/mock.ts` has no PV fixture, so the read-only 2E surface
(GET /api/pv/dashboard, /dashboard/psur, /audit, /cases) has no UI.

GREEN after implementation (same spec):
- `src/app/pv/` is a REAL segment (not a `(pv)` route group, whose bare paths
  would collide with the pinned clinic/admin arrays) with its own layout.tsx:
  RequireAuth + Sidebar + Header, hardcoded identity "PVOIC Officer" /
  "MediCall PV & Medical Information", exactly like the other two shells.
- `components/nav.ts` gains a THIRD export PVOIC_NAV with exactly 4 hrefs
  (/pv, /pv/cases, /pv/psur, /pv/audit). CLINIC_NAV (7) and ADMIN_NAV (9) are
  untouched and re-pinned HERE as well, so this slice cannot silently break the
  arrays test_dashboards.py owns.
- 4 client pages, all off the approved 2E API: overview (KPI tiles + the India
  clock countdown + PQC pipeline + PSUR summary + audit digest), case queue
  (status chips + serious-only), PSUR schedule, audit trail.
- `src/lib/api.ts` gains 4 hooks - usePvDashboard / usePvPsur / usePvAudit /
  usePvCases - on the house authFetch + react-query + useFallback pattern, with
  the dashboard snapshot refetching every 60s so the clock caption stays true.
  NO setInterval anywhere (spec non-goal: clocks are server-computed).
- `components/mock.ts` gains the 4 PV fixtures so the default USE_MOCK=auto
  renders a full page offline; the existing +91 / rupee fixtures survive.

WHY THE TOKEN GUARD EXISTS: Tailwind v4 is CSS-first here, so a class name is
a CONTRACT with globals.css. A utility whose colour is not declared in the
@theme block silently renders as no colour at all - which is the live
`login/page.tsx` bug (bg-card / text-foreground / bg-muted / ... never
existed). This file derives the allowed colour tokens FROM globals.css rather
than from a hand-copied list, so the guard cannot drift from the design system.

Run: python3 tests/test_pv_frontend.py  (exit 0 = green)
"""
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
APP = SRC / "app"
COMPONENTS = SRC / "components"
LIB = SRC / "lib"

PV_APP = APP / "pv"  # real URL segment: a `(pv)` group would collide
NAV_TS = COMPONENTS / "nav.ts"
API_TS = LIB / "api.ts"
MOCK_TS = COMPONENTS / "mock.ts"
GLOBALS_CSS = APP / "globals.css"

PVOIC_TABS = ["/pv", "/pv/cases", "/pv/psur", "/pv/audit"]
PVOIC_TAB_FILES = [("", "page"), ("cases", "page"), ("psur", "page"), ("audit", "page")]

# Re-pinned here (not owned by this slice) so a PVOIC nav edit that collides
# with a clinic/admin tab fails in THIS file too.
CLINIC_TABS = [
    "/dashboard", "/live-calls", "/triage-queue", "/appointments",
    "/prescriptions", "/patients", "/analytics",
]
ADMIN_VIEWS = [
    "/admin", "/admin/live-monitor", "/admin/clinics", "/admin/doctors",
    "/admin/patients", "/admin/revenue", "/admin/billing",
    "/admin/infrastructure", "/admin/audit",
]

# hook -> the exact endpoint string the hook must hit (2E surface)
PV_HOOKS = (
    ("usePvDashboard", "/api/pv/dashboard"),
    ("usePvPsur", "/api/pv/dashboard/psur"),
    ("usePvAudit", "/api/pv/audit"),
    ("usePvCases", "/api/pv/cases"),
)
PV_MOCK_KEYS = ("pvDashboard", "pvPsur", "pvAudit", "pvCases")

PVOIC_IDENTITY = ("PVOIC Officer", "MediCall PV & Medical Information")

# ─── Tailwind v4 token namespaces (read from globals.css @theme) ────────────
COLOR_PREFIXES = (
    "bg", "text", "border", "ring", "from", "via", "to", "fill", "stroke",
    "outline", "divide", "accent", "caret", "decoration", "placeholder",
)
# `shadow-<x>` is a COLOUR utility too, but it resolves against --shadow-*.
SHADOW_PREFIXES = ("shadow",)
# Tailwind's default palette ships every family x every shade, so a class like
# `bg-slate-700/50` is real even though no --color-slate-* is declared here.
DEFAULT_FAMILIES = (
    "slate", "gray", "zinc", "neutral", "stone", "red", "orange", "amber",
    "yellow", "lime", "green", "emerald", "teal", "cyan", "sky", "blue",
    "indigo", "violet", "purple", "fuchsia", "pink", "rose",
)
DEFAULT_BARE = ("white", "black", "transparent", "current", "inherit")
DEFAULT_SHADES = ("50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950")
# Words that READ as a colour but are not one in Tailwind (typography, grid,
# flex, border sides, icons, ...). A first segment in this set means the
# token is not a colour utility at all and is skipped, not flagged.
NOT_COLOUR_WORDS = {
    "50", "100", "200", "300", "400", "500", "600", "700", "800", "900", "950",
    "xs", "sm", "base", "md", "lg", "xl", "2xl", "3xl", "4xl", "5xl", "6xl",
    "7xl", "8xl", "9xl", "left", "center", "right", "justify", "start", "end",
    "ellipsis", "wrap", "nowrap", "balance", "pretty", "uppercase", "lowercase",
    "capitalize", "normal", "clip", "b", "t", "l", "r", "s", "e", "x", "y",
    "solid", "dashed", "dotted", "double", "hidden", "none", "auto", "full",
    "screen", "min", "max", "fit", "px", "1", "2", "3", "4", "5", "6", "8", "10",
    "12", "16", "20", "24", "0", "inner", "tl", "tr", "bl", "br",
}
# `bg-gradient-to-r` / `bg-linear-to-br` / `bg-radial` are background-IMAGE
# utilities that happen to start with a colour prefix. Their first segment
# names an image function, not a colour.
IMAGE_WORDS = {"gradient", "linear", "radial", "conic"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def theme_tokens() -> dict:
    """{namespace: {names}} for every `--<namespace>-<name>:` in @theme."""
    css = read(GLOBALS_CSS)
    m = re.search(r"@theme\s*\{(.*?)\n\}", css, re.S)
    block = m.group(1) if m else ""
    out: dict = {}
    for namespace, name in re.findall(r"--([a-z]+)-([a-z0-9-]+)\s*:", block):
        out.setdefault(namespace, set()).add(name)
    return out


def nav_hrefs(const_name: str):
    """hrefs from an `export const NAME: NavItem[] = [...]` block, or None."""
    text = read(NAV_TS)
    m = re.search(rf"export const {const_name}.*?=\s*\[(.*?)\];", text, re.S)
    if not m:
        return None
    return re.findall(r'href:\s*"([^"]+)"', m.group(1))


def export_block(text: str, name: str) -> str:
    """The source of `export function <name>` up to the next `export function`."""
    start = text.find(f"export function {name}")
    if start < 0:
        return ""
    rest = text.find("export function", start + 1)
    return text[start:] if rest < 0 else text[start:rest]


def const_block(text: str, name: str) -> str:
    """The source of `export const <name> = [...]` up to the next `export`."""
    start = text.find(f"export const {name}")
    if start < 0:
        return ""
    rest = text.find("\nexport ", start + 1)
    return text[start:] if rest < 0 else text[start:rest]


def class_tokens(text: str) -> set:
    """Every whitespace-separated className token in a TSX file."""
    out = set()
    for blob in re.findall(r'className\s*=\s*"([^"]*)"', text):
        out.update(blob.split())
    for blob in re.findall(r'className=\{`([^`]*)`\}', text, re.S):
        # template literals carry interpolations; the static chunks are enough
        for chunk in re.split(r"\$\{[^}]*\}", blob):
            out.update(chunk.split())
    for blob in re.findall(r"`([^`]*)`", text, re.S):
        for chunk in re.split(r"\$\{[^}]*\}", blob):
            out.update(
                t for t in chunk.split()
                if re.fullmatch(r"[A-Za-z0-9:/\[\]._-]+", t) and not t.endswith("(")
            )
    return out


def resolves(token: str, tokens: dict) -> bool:
    """True when `token` names a colour that actually exists in this theme."""
    base = token.split("/")[0]  # drop the /20 opacity modifier
    if not base or "[" in base:
        return True  # arbitrary value (text-[10px], bg-white/[0.02]) - not a token ref
    base = base.rsplit(":", 1)[-1]  # drop the variant prefix (hover:, lg:, ...)
    prefix, _, rest = base.partition("-")
    if not rest:
        return True
    if prefix in COLOR_PREFIXES:
        namespaces = ("color",)
    elif prefix in SHADOW_PREFIXES:
        # Tailwind v4: `shadow-card` resolves against --shadow-*, but
        # `shadow-primary-500/20` is a shadow COLOUR and resolves against
        # --color-*. A shadow is therefore valid if EITHER reading matches.
        namespaces = ("color", "shadow")
    else:
        return True
    first = rest.split("-", 1)[0]
    if first in NOT_COLOUR_WORDS or first in IMAGE_WORDS:
        return True  # text-sm / border-b / shadow-xl / bg-gradient-to-r
    if any(rest in tokens.get(ns, ()) for ns in namespaces):
        return True
    if rest in DEFAULT_BARE:
        return True
    family, _, shade = rest.rpartition("-")
    return family in DEFAULT_FAMILIES and shade in DEFAULT_SHADES


def nonexistent_tokens(text: str) -> list:
    tokens = theme_tokens()
    return sorted(t for t in class_tokens(text) if not resolves(t, tokens))


def pv_page_files() -> list:
    if not PV_APP.exists():
        return []
    return sorted(p for p in PV_APP.rglob("*.tsx"))


# ─── The shell ─────────────────────────────────────────────────────────────

class TestPvShell(unittest.TestCase):
    def test_pv_layout_exists(self):
        self.assertTrue((PV_APP / "layout.tsx").exists(), "app/pv/layout.tsx missing")

    def test_pv_layout_is_client_component(self):
        text = read(PV_APP / "layout.tsx")
        self.assertTrue(text.startswith('"use client"'), "pv/layout.tsx must be a client component")

    def test_pv_layout_uses_nav_single_source(self):
        text = read(PV_APP / "layout.tsx")
        self.assertIn("PVOIC_NAV", text)
        self.assertIn("@/components/nav", text, "the nav array must come from components/nav")

    def test_pv_layout_guards_with_require_auth(self):
        text = read(PV_APP / "layout.tsx")
        self.assertIn("RequireAuth", text, "every shell is identity-gated")
        self.assertIn("@/lib/auth", text)

    def test_pv_layout_mirrors_other_shells(self):
        text = read(PV_APP / "layout.tsx")
        for needed in ("Sidebar", "Header", "@/components/sidebar", "@/components/header"):
            self.assertIn(needed, text, f"pv/layout.tsx must use {needed} like the other shells")

    def test_pv_identity(self):
        text = read(PV_APP / "layout.tsx")
        for value in PVOIC_IDENTITY:
            self.assertIn(value, text, f"pv/layout.tsx must hardcode {value!r}")


# ─── Navigation ────────────────────────────────────────────────────────────

class TestPvNav(unittest.TestCase):
    def test_pvoic_nav_exactly_four(self):
        self.assertEqual(
            nav_hrefs("PVOIC_NAV"), PVOIC_TABS,
            "PVOIC_NAV must be exactly /pv, /pv/cases, /pv/psur, /pv/audit",
        )

    def test_three_distinct_nav_exports(self):
        for name in ("CLINIC_NAV", "ADMIN_NAV", "PVOIC_NAV"):
            self.assertIn(f"export const {name}", read(NAV_TS), f"nav.ts: {name} missing")
        clinic, admin, pvoic = (nav_hrefs(n) for n in ("CLINIC_NAV", "ADMIN_NAV", "PVOIC_NAV"))
        for pair in ((clinic, admin), (clinic, pvoic), (admin, pvoic)):
            self.assertFalse(set(pair[0]) & set(pair[1]), f"nav arrays overlap: {pair}")
        self.assertEqual(len(pvoic), len(set(pvoic)), "PVOIC_NAV hrefs must be unique")

    def test_clinic_and_admin_navs_untouched(self):
        """The pinned 7/9 arrays must survive this slice verbatim."""
        self.assertEqual(nav_hrefs("CLINIC_NAV"), CLINIC_TABS)
        self.assertEqual(nav_hrefs("ADMIN_NAV"), ADMIN_VIEWS)

    def test_pvoic_nav_items_are_shaped_like_the_others(self):
        text = read(NAV_TS)
        block = const_block(text, "PVOIC_NAV")
        self.assertTrue(block, "PVOIC_NAV block not found in nav.ts")
        items = re.findall(r"\{(.*?)\}", block, re.S)
        self.assertEqual(len(items), len(PVOIC_TABS), "one object per PVOIC tab")
        for item in items:
            for key in ("href", "label", "icon"):
                self.assertIn(f"{key}:", item, f"PVOIC_NAV item missing {key}: {item[:60]}")


# ─── Pages ─────────────────────────────────────────────────────────────────

class TestPvPages(unittest.TestCase):
    def test_four_pages_exist(self):
        for cluster, name in PVOIC_TAB_FILES:
            self.assertTrue(
                (PV_APP / cluster / f"{name}.tsx").exists(),
                f"app/pv/{cluster}/{name}.tsx missing",
            )

    def test_every_page_is_a_client_component(self):
        for cluster, name in PVOIC_TAB_FILES:
            path = PV_APP / cluster / f"{name}.tsx"
            self.assertTrue(
                read(path).startswith('"use client"'),
                f"pv/{cluster}/{name}.tsx must start with \"use client\"",
            )

    def test_pages_read_the_api_client_not_the_fixtures(self):
        for cluster, name in PVOIC_TAB_FILES:
            text = read(PV_APP / cluster / f"{name}.tsx")
            self.assertIn("@/lib/api", text, f"pv/{cluster}: must use the api client")
            self.assertNotIn(
                "@/components/mock", text,
                f"pv/{cluster}: mock fallback belongs in the hook, not the page",
            )

    def test_no_live_countdown_machinery(self):
        """Clocks are server-computed; react-query refetchInterval is the refresh."""
        for path in pv_page_files():
            self.assertNotIn(
                "setInterval", read(path),
                f"{path.name}: the spec forbids a ticking countdown in the page",
            )

    def test_no_dollar_amounts(self):
        for path in pv_page_files():
            self.assertIsNone(
                re.search(r"\$[0-9]", read(path)),
                f"{path}: dollar amounts are banned (India context only)",
            )

    def test_case_queue_has_filters(self):
        text = read(PV_APP / "cases" / "page.tsx")
        self.assertIn("serious", text.lower(), "the queue must expose the serious-only filter")
        self.assertIn("status", text.lower(), "the queue must expose status filters")

    def test_overview_renders_the_india_clock(self):
        text = read(PV_APP / "page.tsx")
        for needed in ("overdue", "upcoming", "hoursRemaining", "daysOverdue"):
            self.assertIn(needed, text, f"pv overview must render the clock field {needed}")
        self.assertIn(
            "formatRelativeDate", text,
            "the snapshot must carry a 'last updated' caption",
        )

    def test_psur_page_renders_window_and_due_now(self):
        text = read(PV_APP / "psur" / "page.tsx")
        self.assertIn("nextWindow", text, "PSUR cards must name the reporting window")
        self.assertIn("dueNow", text, "PSUR cards must flag a window that is open now")


# ─── The client hooks (src/lib/api.ts) ─────────────────────────────────────

class TestPvHooks(unittest.TestCase):
    def test_hooks_exported(self):
        text = read(API_TS)
        for hook, _path in PV_HOOKS:
            self.assertIn(f"export function {hook}", text, f"api.ts: {hook} not exported")

    def test_hooks_hit_the_approved_2e_endpoints(self):
        text = read(API_TS)
        for hook, path in PV_HOOKS:
            block = export_block(text, hook)
            self.assertRegex(
                block, rf"['\"`]{re.escape(path)}\?",
                f"{hook} must call {path} with ?clinic_id= (and its filters)",
            )

    def test_hooks_carry_clinic_id(self):
        text = read(API_TS)
        for hook, _path in PV_HOOKS:
            block = export_block(text, hook)
            self.assertIn(
                "clinic_id=", block, f"{hook} must scope the read to the clinic id",
            )

    def test_case_queue_filters_are_server_side_params(self):
        block = export_block(read(API_TS), "usePvCases")
        for param in ("status", "serious_only"):
            self.assertIn(param, block, f"usePvCases must pass {param} to the API")

    def test_audit_window_is_a_parameter(self):
        block = export_block(read(API_TS), "usePvAudit")
        self.assertIn("days", block, "usePvAudit must pass the window in days")

    def test_dashboard_snapshot_refetches_for_clock_freshness(self):
        block = export_block(read(API_TS), "usePvDashboard")
        self.assertIn("refetchInterval", block, "the clock must refresh (60s)")
        self.assertRegex(block, r"refetchInterval:\s*60_000")

    def test_hooks_use_the_house_fallback_pattern(self):
        text = read(API_TS)
        for hook, _path in PV_HOOKS:
            block = export_block(text, hook)
            self.assertIn("useQuery", block, f"{hook} must be a react-query hook")
            self.assertIn("authFetch", block, f"{hook} must read through authFetch")
            self.assertIn("USE_MOCK", block, f"{hook} must honour the USE_MOCK policy")

    def test_pv_fixtures_imported(self):
        text = read(API_TS)
        for key in PV_MOCK_KEYS:
            self.assertRegex(
                text, rf"\b{key}\s+as\s+mock{key[0].upper()}{key[1:]}",
                f"api.ts: {key} must be imported aliased mock{key[0].upper()}{key[1:]}",
            )


# ─── Mock parity (components/mock.ts) ──────────────────────────────────────

class TestPvMockParity(unittest.TestCase):
    def test_four_pv_fixtures_exist(self):
        text = read(MOCK_TS)
        for key in PV_MOCK_KEYS:
            self.assertIn(f"export const {key}", text, f"mock.ts: {key} fixture missing")

    def test_existing_india_flavour_survives(self):
        text = read(MOCK_TS)
        self.assertIn("+91", text)
        self.assertIn("\u20b9", text)

    def test_no_dollar_amounts(self):
        self.assertIsNone(re.search(r"\$[0-9]", read(MOCK_TS)))


# ─── Design-system guard (derived from globals.css, not hand-copied) ──────

class TestPvDesignTokens(unittest.TestCase):
    def test_globals_css_theme_parsed(self):
        tokens = theme_tokens()
        self.assertIn("color", tokens, "@theme block not found in globals.css")
        self.assertIn("primary-500", tokens["color"])
        self.assertIn("background", tokens["color"])
        self.assertIn("severity-red", tokens["color"])

    def test_pv_pages_use_no_nonexistent_tokens(self):
        pages = pv_page_files()
        self.assertTrue(pages, "no pv/**/*.tsx files found - nothing was checked")
        found = []
        for path in pages:
            for token in nonexistent_tokens(read(path)):
                found.append(f"{path.relative_to(ROOT)}: {token}")
        self.assertEqual(
            [], found,
            "Tailwind tokens that do not exist in globals.css @theme (a class that "
            "resolves to no colour at all):\n" + "\n".join(found),
        )

    def test_the_guard_actually_catches_the_login_bug_class(self):
        """A shadcn token this theme never declared must FAIL the resolver."""
        for bogus in ("bg-card", "text-foreground", "bg-muted", "text-muted-foreground",
                      "text-destructive", "bg-primary", "text-primary-foreground"):
            self.assertFalse(
                resolves(bogus, theme_tokens()),
                f"{bogus} does not exist in this theme - the guard must reject it",
            )

    def test_the_guard_accepts_the_real_tokens(self):
        for real in ("bg-background", "text-slate-400", "bg-primary-500/20",
                     "text-severity-amber", "text-white", "bg-slate-700/50",
                     "border-white/10", "ring-red-500/40", "shadow-primary-500/20",
                     "divide-white/5", "text-sm", "border-b", "shadow-xl",
                     "shadow-card", "shadow-md", "shadow-inner",
                     "bg-gradient-to-r", "from-primary-500", "to-primary-400"):
            self.assertTrue(
                resolves(real, theme_tokens()), f"{real} must resolve (false positive)",
            )

    def test_the_guard_accepts_shadow_colour_but_not_shadow_typo(self):
        """`shadow-primary-500` is a colour shadow; `shadow-primry-500` is nothing."""
        self.assertTrue(resolves("shadow-primary-500/20", theme_tokens()))
        self.assertFalse(resolves("shadow-primry-500/20", theme_tokens()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
