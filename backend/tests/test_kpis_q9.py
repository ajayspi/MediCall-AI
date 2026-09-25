"""G6-Q9 MVP KPIs + analytics RED contract.

Contract (sign-off 2026-09-25, Q1=A3 Q2=A2 Q3=A1 Q4=A1):
- Q1=A3 (7 KPIs): call volume (total/by_state/by_day/avg_duration_seconds) +
  resolution rate + triage mix + language dist + no-show rate + revenue
  (captured/refunded/by_kind/currency) + notification delivery success (per
  kind: sent/failed/total/success_rate) + static market benchmarks context
  dict. Reminder *confirmation* rate deferred (needs campaign state).
- Q2=A2 (per-KPI endpoints): app/api/analytics.py, prefix /api/analytics,
  one GET per KPI: /volume /resolution /triage /language /no-show /revenue
  /delivery, plus /benchmarks for the static market context. Handlers
  get_<kpi>_ep, all identity-gated; KPI handlers take clinic_id + optional
  from/to; benchmarks handler takes clinic_id-free (static) — no period.
- Q3=A1 (pure computed): stdlib app/services/analytics.py leaf (roots subset
  {datetime, collections, typing}); postgres.py per-KPI async aggregates
  (func.count / func.sum + group_by); zero schema writes; rides existing RLS.
- Q4=A1 (period): optional ISO from/to, defaults to=now / from=to-30d, cap
  366 days, 422 on bad order / over-cap / unparseable; naive assumed UTC
  (same rule as retention.retention_deadline).
- Pins: G4 voice + Q8 catalog + Q4 languages + Q2 consent hold; auth.py /
  IDENTITY_FREE_ENDPOINTS untouched; no .env additions (benchmarks are code).
"""

import ast
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS = BACKEND / "tests"
APP = BACKEND / "app"
POSTGRES = APP / "db" / "postgres.py"
ANALYTICS_ROUTER = APP / "api" / "analytics.py"

try:
    from app.services import analytics as anl  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    anl = None

KPI_ENDPOINTS = {
    ("get", "/volume"),
    ("get", "/resolution"),
    ("get", "/triage"),
    ("get", "/language"),
    ("get", "/no-show"),
    ("get", "/revenue"),
    ("get", "/delivery"),
    ("get", "/benchmarks"),
}
KPI_HANDLERS = (
    "get_volume_ep",
    "get_resolution_ep",
    "get_triage_ep",
    "get_language_ep",
    "get_no_show_ep",
    "get_revenue_ep",
    "get_delivery_ep",
    "get_benchmarks_ep",
)
DB_HELPERS = (
    "compute_volume",
    "compute_resolution",
    "compute_triage",
    "compute_language",
    "compute_no_show",
    "compute_revenue",
    "compute_delivery",
)
BANNED_ROOTS = {"httpx", "requests", "twilio", "whatsapp", "msg91", "firebase_admin",
                "fastapi", "sqlalchemy", "pydantic", "websockets", "openai",
                "elevenlabs", "pgvector", "asyncpg"}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def py_tree(path: Path):
    text = read(path)
    if not text:
        return None
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def fn_block(text: str, name: str) -> str:
    """The source text of one function (via AST line offsets), or ''.

    Slices by LINE via splitlines(keepends=True) so each line stays intact
    (same helper as test_notifications_q8 / test_languages_q4 / test_dpdp_q2).
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            lines = text.splitlines(keepends=True)
            return "".join(lines[node.lineno - 1 : node.end_lineno])
    return ""


def imports_at_module_level(tree) -> list:
    """[(kind, name)] where kind in {"import", "from"} — module-level only."""
    out = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(("import", alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(("from", node.module.split(".")[0]))
    return out


def endpoint_set(router_path: Path) -> set:
    """{(method, path)} from the router's route decorators (Q8 convention)."""
    tree = py_tree(router_path)
    found = set()
    if tree is None:
        return found
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in {"get", "post", "patch", "put", "delete"}
                and dec.args
                and isinstance(dec.args[0], ast.Constant)
            ):
                found.add((dec.func.attr, dec.args[0].value))
    return found


UTC = timezone.utc


# ─── Analytics service (Q1=A3, Q3=A1, Q4=A1) ───────────────────────────────
class TestAnalyticsModule(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(anl, "app/services/analytics.py missing (RED)")

    def test_module_is_stdlib_leaf(self):
        tree = py_tree(APP / "services" / "analytics.py")
        self.assertIsNotNone(tree, "analytics.py must parse")
        roots = {name for _, name in imports_at_module_level(tree)}
        self.assertTrue(roots <= {"datetime", "collections", "typing"},
                        f"analytics.py must be stdlib-only roots; got {sorted(roots)}")
        self.assertFalse(roots & BANNED_ROOTS)

    # ── resolution_rate ─────────────────────────────────────────────────────
    def test_resolution_rate_math(self):
        rate = anl.resolution_rate(60, 20, 10, 5)
        # terminal = completed + dropped + escalated + payment_expired
        self.assertAlmostEqual(rate, 60 / 95, places=6)

    def test_resolution_rate_zero_denominator(self):
        self.assertIsNone(anl.resolution_rate(0, 0, 0, 0))

    def test_resolution_rate_excludes_payment_sent(self):
        # PAYMENT_SENT is in-progress; the denominator never includes it.
        self.assertEqual(anl.resolution_rate(1, 0, 0, 0), 1.0)

    # ── no_show_rate ────────────────────────────────────────────────────────
    def test_no_show_rate_math(self):
        rate = anl.no_show_rate(6, 80, 14)  # 6 / (6+80+14)
        self.assertAlmostEqual(rate, 0.06, places=6)

    def test_no_show_rate_zero_denominator(self):
        self.assertIsNone(anl.no_show_rate(0, 0, 0))

    # ── success_rate ────────────────────────────────────────────────────────
    def test_success_rate_math(self):
        self.assertEqual(anl.success_rate(95, 5), 0.95)

    def test_success_rate_zero_denominator(self):
        self.assertIsNone(anl.success_rate(0, 0))

    # ── resolve_period (Q4=A1) ──────────────────────────────────────────────
    def test_period_defaults_30d(self):
        now = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
        from_dt, to_dt = anl.resolve_period(None, None, now=now)
        self.assertEqual(from_dt, datetime(2026, 8, 26, 12, 0, tzinfo=UTC))
        self.assertEqual(to_dt, now)
        self.assertEqual((to_dt - from_dt).days, 30)

    def test_period_naive_assumed_utc(self):
        from_dt, to_dt = anl.resolve_period("2026-09-01T00:00:00", "2026-09-25", now=None)
        self.assertEqual(from_dt.utcoffset(), timedelta(0), "naive input assumed UTC")
        self.assertEqual(to_dt.utcoffset(), timedelta(0))

    def test_period_range_cap_366(self):
        with self.assertRaises(ValueError):
            anl.resolve_period("2024-01-01", "2026-01-01")  # > 366 days

    def test_period_bad_order(self):
        with self.assertRaises(ValueError):
            anl.resolve_period("2026-09-25", "2026-09-01")

    def test_period_bad_format(self):
        with self.assertRaises(ValueError):
            anl.resolve_period("not-a-date", None)

    def test_period_explicit_in_cap_ok(self):
        from_dt, to_dt = anl.resolve_period("2026-09-01", "2026-09-25")
        self.assertEqual(from_dt, datetime(2026, 9, 1, tzinfo=UTC))
        self.assertEqual(to_dt, datetime(2026, 9, 25, tzinfo=UTC))

    # ── shape helpers ───────────────────────────────────────────────────────
    def test_shape_volume_avg_duration(self):
        raw = {
            "total": 3,
            "by_state": {"COMPLETE": 2, "DROPPED": 1},
            "by_day": {"2026-09-01": 3},
            "duration_sum": 300,
            "duration_count": 3,
        }
        out = anl.shape_volume(raw)
        self.assertEqual(out["total"], 3)
        self.assertEqual(out["by_state"]["COMPLETE"], 2)
        self.assertEqual(out["by_day"]["2026-09-01"], 3)
        self.assertEqual(out["avg_duration_seconds"], 100.0)

    def test_shape_volume_no_duration_avg_none(self):
        raw = {"total": 0, "by_state": {}, "by_day": {},
               "duration_sum": 0, "duration_count": 0}
        self.assertIsNone(anl.shape_volume(raw)["avg_duration_seconds"])

    def test_shape_delivery_per_kind(self):
        raw = {"payment_link": {"sent": 90, "failed": 10},
               "otp": {"sent": 5, "failed": 0}}
        out = anl.shape_delivery(raw)
        self.assertEqual(out["payment_link"]["sent"], 90)
        self.assertEqual(out["payment_link"]["failed"], 10)
        self.assertEqual(out["payment_link"]["total"], 100)
        self.assertEqual(out["payment_link"]["success_rate"], 0.9)
        self.assertEqual(out["otp"]["success_rate"], 1.0)

    # ── benchmarks (market context, display-only) ───────────────────────────
    def test_benchmarks_resolution(self):
        b = anl.BENCHMARKS
        self.assertEqual(b["resolution"]["human_fcr_pct"], [70, 79])
        self.assertEqual(b["resolution"]["interactly_virtual_receptionist_pct"], 72)

    def test_benchmarks_no_show(self):
        b = anl.BENCHMARKS
        self.assertEqual(b["no_show"]["india_baseline_pct"], [18, 25])
        self.assertEqual(b["no_show"]["voice_reminder_target_pct"], [8, 12])

    def test_benchmarks_confirmation_and_sources(self):
        b = anl.BENCHMARKS
        self.assertEqual(b["confirmation"]["voice_reminder_confirmation_pct"], [75, 85])
        self.assertTrue(isinstance(b["sources"], list) and b["sources"])
        self.assertTrue(all(isinstance(s, str) and s for s in b["sources"]))


# ─── postgres.py aggregates (Q3=A1) ─────────────────────────────────────────
class TestAnalyticsDb(unittest.TestCase):
    def test_compute_helpers_exist(self):
        text = read(POSTGRES)
        for name in DB_HELPERS:
            self.assertTrue(fn_block(text, name), f"postgres.py missing async {name}()")

    def test_compute_volume_aggregates(self):
        block = fn_block(read(POSTGRES), "compute_volume")
        self.assertIn("func.count", block)
        self.assertIn("group_by", block)

    def test_compute_revenue_aggregates(self):
        block = fn_block(read(POSTGRES), "compute_revenue")
        self.assertIn("func.sum", block)
        self.assertIn("Payment.status", block)
        self.assertIn("captured", block)

    def test_compute_delivery_aggregates(self):
        block = fn_block(read(POSTGRES), "compute_delivery")
        self.assertIn("Notification.status", block)
        self.assertIn("group_by", block)


# ─── Analytics router (Q2=A2, Q3=A1) ────────────────────────────────────────
class TestAnalyticsRouter(unittest.TestCase):
    def test_router_file_exists_and_parses(self):
        self.assertIsNotNone(py_tree(ANALYTICS_ROUTER),
                             "app/api/analytics.py missing or unparseable (RED)")

    def test_router_prefix(self):
        self.assertIn("/api/analytics", read(ANALYTICS_ROUTER))

    def test_endpoint_set_exact(self):
        self.assertEqual(KPI_ENDPOINTS, endpoint_set(ANALYTICS_ROUTER))

    def test_each_kpi_handler_identity_gated(self):
        text = read(ANALYTICS_ROUTER)
        for name in KPI_HANDLERS:
            block = fn_block(text, name)
            self.assertTrue(block, f"{name} missing in analytics router")
            self.assertIn("Depends(get_current_user)", block, name)

    def test_volume_handler_takes_clinic_and_period(self):
        block = fn_block(read(ANALYTICS_ROUTER), "get_volume_ep")
        self.assertIn("clinic_id", block)
        self.assertIn('alias="from"', block)
        self.assertIn('alias="to"', block)

    def test_benchmarks_handler_has_no_period(self):
        block = fn_block(read(ANALYTICS_ROUTER), "get_benchmarks_ep")
        # static market context: no from/to window params
        self.assertNotIn('alias="from"', block)
        self.assertNotIn('alias="to"', block)


if __name__ == "__main__":
    unittest.main()