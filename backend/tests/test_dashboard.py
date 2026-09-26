"""PVOIC compliance dashboard API (spec-micc-pv-phase2.md slice 2E) — RED contracts.

Read-only, API-first: the numbers are assembled by a PURE stdlib helper
(app/services/pv_dashboard.py) that takes already-fetched rows and computes
every count, so it is unit-testable with no database, no FastAPI and no
network. The /api/pv route contracts are structural AST + text assertions —
the house pattern of test_pv_module.py and test_e2b.py, because FastAPI and
SQLAlchemy are NOT installed in the test environment.

Three things this slice must not get wrong, and therefore tests:
- the India clock is REUSED (compute_reporting_deadline), never duplicated:
  the dashboard's days_remaining must equal the Phase-1 clock exactly;
- overdue is a flag on an OPEN case (status not notified/submitted/closed) —
  a case reported late is a fact, not a violation of the PVOIC's own status;
- the PSUR calendar is 6-monthly x2y then annual x2y from approval
  (research-micc-process.md 3.3), so a 4-year-old product has no further
  window IN THIS MODULE and must say so rather than invent a cadence.

RED before implementation (2026-09-26): no app/services/pv_dashboard.py, no
/dashboard, /dashboard/psur or /audit route.

Run: py -3.14 -m unittest discover -s tests -p "test_dashboard.py"   (from backend/)
"""
import ast
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

SERVICES = BACKEND / "app" / "services"
DASH_SVC = SERVICES / "pv_dashboard.py"
PV_ROUTER = BACKEND / "app" / "api" / "pv.py"

# The dashboard module is a stdlib leaf that may import EXACTLY the Phase-1 PV
# service (the India clock lives there and must be reused, not re-implemented).
ALLOWED_APP_IMPORTS = {"app.services.pharmacovigilance"}
NETWORK_ROOTS = {
    "asyncio",
    "ftplib",
    "http",
    "httpx",
    "httplib",
    "requests",
    "smtplib",
    "socket",
    "ssl",
    "telnetlib",
    "urllib",
    "urllib3",
    "webbrowser",
    "xmlrpc",
}

from app.services import pharmacovigilance as pv  # noqa: E402

try:
    from app.services import pv_dashboard as dash  # noqa: E402

    HAVE_DASH = True
except ImportError:  # pragma: no cover - RED state
    dash = None
    HAVE_DASH = False


# ─── Fixtures + AST helpers ─────────────────────────────────────────────────
NOW = datetime(2026, 3, 15, 9, 30, tzinfo=timezone.utc)


def ae_row(
    case_id: str = "11111111-1111-4111-8111-111111111111",
    days_ago: float = 3,
    serious: bool = False,
    status: str = "new",
    deadline: str = "",
) -> dict:
    """One AdverseEvent row, shaped like api/pv.py's _case_row."""
    received = (NOW - timedelta(days=days_ago)).isoformat()
    return {
        "id": case_id,
        "case_type": "AE",
        "status": status,
        "received_at": received,
        "notification_deadline": deadline,
        "notified_at": "",
        "seriousness_flags": ["hospitalisation"] if serious else [],
    }


def pqc_row(complaint_id: str, status: str, disposition: str = "") -> dict:
    return {
        "id": complaint_id,
        "investigation_status": status,
        "disposition": disposition or None,
    }


def mi_row(inquiry_id: str, status: str) -> dict:
    return {"id": inquiry_id, "status": status}


def product_row(
    product_id: str, name: str, anchor: date, active: bool = True
) -> dict:
    """One Product row; created_at is the PSUR anchor in this slice."""
    return {
        "id": product_id,
        "name": name,
        "generic_name": "",
        "is_active": active,
        "created_at": datetime(anchor.year, anchor.month, anchor.day, tzinfo=timezone.utc),
    }


def audit_row(event_id: str, event_type: str, days_ago: float = 1) -> dict:
    return {
        "id": event_id,
        "event_type": event_type,
        "severity": "medium",
        "status": "open",
        "detected_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "description": "AE captured",
    }


def snapshot(**overrides) -> dict:
    payload = {
        "ae_rows": [],
        "pqc_rows": [],
        "mi_rows": [],
        "product_rows": [],
        "audit_rows": [],
    }
    payload.update(overrides)
    return dash.build_dashboard_snapshot(now=NOW, **payload)


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


def fns(tree) -> dict:
    out = {}
    for node in ast.walk(tree or ast.Module(body=[], type_ignores=[])):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = node
    return out


def fn_block(text: str, name: str) -> str:
    try:
        tree = ast.parse(text) if text else None
    except SyntaxError:
        return ""
    node = fns(tree).get(name)
    if node is None:
        return ""
    lines = text.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def module_import_roots(text: str) -> set:
    roots = set()
    if not text:
        return roots
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return roots
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def endpoints(tree) -> list:
    """[(method, path, endpoint name)] for every @router.<verb> endpoint."""
    out = []
    if tree is None:
        return out
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if (
                isinstance(deco, ast.Call)
                and isinstance(deco.func, ast.Attribute)
                and isinstance(deco.func.value, ast.Name)
                and deco.func.value.id == "router"
                and deco.args
            ):
                out.append((deco.func.attr.lower(), deco.args[0].value, node.name))
    return out


def require_dash():
    """RED-state guard: the behaviour classes ERROR (never skip) without it."""
    if not HAVE_DASH:
        raise AssertionError("app/services/pv_dashboard.py is missing (RED state)")


# ─── A. Module shape: stdlib leaf, no network, no new deps ──────────────────
class TestDashboardServiceShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(DASH_SVC)
        cls.tree = py_tree(DASH_SVC)

    def test_service_module_exists(self):
        self.assertTrue(DASH_SVC.exists(), "app/services/pv_dashboard.py missing")
        self.assertIsNotNone(self.tree, "pv_dashboard.py must parse")

    def test_stdlib_only(self):
        roots = module_import_roots(self.text)
        for root in roots:
            with self.subTest(root):
                self.assertTrue(
                    root == "app" or root in sys.stdlib_module_names,
                    f"pv_dashboard.py imports a non-stdlib root: {root}",
                )
        app_modules = {
            node.module
            for node in ast.walk(self.tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] == "app"
        }
        for module in app_modules:
            with self.subTest(module):
                self.assertIn(
                    module,
                    ALLOWED_APP_IMPORTS,
                    "pv_dashboard.py may only import the Phase-1 PV service (the clock)",
                )

    def test_no_network_imports(self):
        roots = module_import_roots(self.text)
        for banned in sorted(roots & NETWORK_ROOTS):
            self.fail(f"pv_dashboard.py must not import {banned}: slice 2E is read-only")

    def test_no_new_pypi_dependencies(self):
        """The slice adds zero runtime deps: requirements.txt must not change."""
        req = (BACKEND / "requirements.txt").read_text(encoding="utf-8").lower()
        for banned in ("pandas", "numpy", "dateutil", "pytz", "croniter", "arrow"):
            with self.subTest(banned):
                self.assertNotIn(banned, req, f"slice 2E must not add {banned}")

    def test_public_surface(self):
        names = set(fns(self.tree))
        for name in (
            "build_dashboard_snapshot",
            "build_psur_schedule",
            "build_audit_trail",
            "psur_next_window",
        ):
            with self.subTest(name):
                self.assertIn(name, names, f"pv_dashboard.py missing {name}")

    def test_reuses_the_phase1_clock(self):
        self.assertIn("from app.services.pharmacovigilance import", self.text)
        self.assertIn(
            "compute_reporting_deadline",
            self.text,
            "the India clock must be reused from pharmacovigilance, never duplicated",
        )
        for banned in ("REPORTING_CLOCK_DAYS", "DAYS_SERIOUS", "DAYS_NON_SERIOUS"):
            with self.subTest(banned):
                self.assertNotIn(
                    banned, self.text, "a second reporting clock would be a second truth"
                )


# ─── B. Snapshot counts ─────────────────────────────────────────────────────
class TestDashboardCounts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()
        cls.snap = snapshot(
            ae_rows=[
                ae_row("aaaa", days_ago=1, serious=True),
                ae_row("bbbb", days_ago=20, serious=True),  # 15d clock -> overdue
                ae_row("cccc", days_ago=4, serious=False),  # 90d clock
                ae_row("dddd", days_ago=30, serious=False, status="notified"),
                ae_row("eeee", days_ago=30, serious=False, status="submitted"),
                ae_row("ffff", days_ago=30, serious=False, status="closed"),
            ],
            pqc_rows=[
                pqc_row("p1", "captured"),
                pqc_row("p2", "investigating", "batch_confirmed"),
                pqc_row("p3", "disposition", "batch_confirmed"),
                pqc_row("p4", "capa", "recall"),
            ],
            mi_rows=[mi_row("m1", "open"), mi_row("m2", "answered")],
        )

    def test_counts_by_case_type(self):
        by_type = self.snap["cases"]["by_type"]
        self.assertEqual(by_type["ae"], 6)
        self.assertEqual(by_type["pqc"], 4)
        self.assertEqual(by_type["mi"], 2)
        self.assertEqual(by_type["total"], 12)

    def test_counts_by_status(self):
        by_status = self.snap["cases"]["by_status"]
        self.assertEqual(by_status["notified"], 1)
        self.assertEqual(by_status["submitted"], 1)
        self.assertEqual(by_status["closed"], 1)
        # open = every AE that is not notified/submitted/closed
        self.assertEqual(by_status["open"], 3)
        self.assertEqual(by_status["total"], 6)
        self.assertEqual(by_status["unknown"], 0)

    def test_overdue_is_flagged_on_an_open_case(self):
        clocks = self.snap["clocks"]
        self.assertEqual(clocks["overdue_count"], 1)
        entry = clocks["overdue"][0]
        self.assertEqual(entry["case_id"], "bbbb")
        self.assertTrue(entry["is_serious"])
        self.assertEqual(entry["days_overdue"], 5)

    def test_notified_submitted_closed_are_never_overdue(self):
        for case_id in ("dddd", "eeee", "ffff"):
            with self.subTest(case_id):
                self.assertNotIn(
                    case_id, [e["case_id"] for e in self.snap["clocks"]["overdue"]]
                )

    def test_pqc_pipeline_counts(self):
        pqc = self.snap["pqc"]
        self.assertEqual(pqc["total"], 4)
        for stage in ("captured", "investigating", "disposition", "capa"):
            with self.subTest(stage):
                self.assertEqual(pqc["by_investigation_status"][stage], 1)
        self.assertEqual(
            pqc["by_disposition"], {"batch_confirmed": 2, "recall": 1}
        )

    def test_mi_status_counts(self):
        self.assertEqual(self.snap["mi"]["by_status"], {"answered": 1, "open": 1})
        self.assertEqual(self.snap["mi"]["total"], 2)

    def test_empty_clinic_is_all_zeroes_not_a_crash(self):
        empty = snapshot()
        self.assertEqual(empty["cases"]["by_type"]["total"], 0)
        self.assertEqual(empty["cases"]["by_status"]["open"], 0)
        self.assertEqual(empty["clocks"]["overdue_count"], 0)
        self.assertEqual(empty["clocks"]["upcoming_count"], 0)
        self.assertEqual(empty["pqc"]["total"], 0)
        self.assertEqual(empty["psur"]["products"], 0)
        self.assertEqual(empty["audit"]["count"], 0)
        self.assertEqual(empty["generated_at"], NOW.isoformat())

    def test_unknown_status_is_counted_open_and_flagged(self):
        snap = snapshot(ae_rows=[ae_row("zzzz", status="weird_state")])
        self.assertEqual(snap["cases"]["by_status"]["open"], 1)
        self.assertEqual(snap["cases"]["by_status"]["unknown"], 1)


# ─── C. Overdue + the 48h upcoming horizon ──────────────────────────────────
class TestDashboardClocks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()

    def test_horizon_is_48_hours(self):
        self.assertEqual(snapshot()["clocks"]["horizon_hours"], 48)

    def test_upcoming_includes_exactly_48h(self):
        deadline = (NOW + timedelta(hours=48)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", deadline=deadline)])
        self.assertEqual(snap["clocks"]["upcoming_count"], 1)
        self.assertEqual(snap["clocks"]["upcoming"][0]["hours_remaining"], 48.0)

    def test_upcoming_includes_47h(self):
        deadline = (NOW + timedelta(hours=47)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", deadline=deadline)])
        self.assertEqual(snap["clocks"]["upcoming_count"], 1)
        self.assertEqual(snap["clocks"]["upcoming"][0]["hours_remaining"], 47.0)

    def test_upcoming_excludes_49h(self):
        deadline = (NOW + timedelta(hours=49)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", deadline=deadline)])
        self.assertEqual(snap["clocks"]["upcoming_count"], 0)
        self.assertEqual(snap["clocks"]["upcoming"], [])

    def test_a_closed_case_is_never_upcoming(self):
        deadline = (NOW + timedelta(hours=10)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", status="closed", deadline=deadline)])
        self.assertEqual(snap["clocks"]["upcoming_count"], 0)
        self.assertEqual(snap["clocks"]["overdue_count"], 0)

    def test_overdue_case_is_not_also_upcoming(self):
        deadline = (NOW - timedelta(hours=1)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", deadline=deadline)])
        self.assertEqual(snap["clocks"]["overdue_count"], 1)
        self.assertEqual(snap["clocks"]["upcoming_count"], 0)

    def test_upcoming_entries_carry_days_remaining(self):
        deadline = (NOW + timedelta(hours=36)).isoformat()
        snap = snapshot(ae_rows=[ae_row("a", serious=True, deadline=deadline)])
        entry = snap["clocks"]["upcoming"][0]
        self.assertEqual(entry["days_remaining"], 2)
        self.assertEqual(entry["notification_deadline"], deadline)

    def test_upcoming_is_sorted_by_soonest_deadline(self):
        rows = [
            ae_row("late", deadline=(NOW + timedelta(hours=40)).isoformat()),
            ae_row("soon", deadline=(NOW + timedelta(hours=3)).isoformat()),
            ae_row("mid", deadline=(NOW + timedelta(hours=20)).isoformat()),
        ]
        snap = snapshot(ae_rows=rows)
        self.assertEqual(
            [e["case_id"] for e in snap["clocks"]["upcoming"]], ["soon", "mid", "late"]
        )

    def test_case_without_a_deadline_is_neither_overdue_nor_upcoming(self):
        snap = snapshot(ae_rows=[ae_row("a")])  # no stored deadline -> computed
        self.assertEqual(snap["clocks"]["overdue_count"], 0)

    def test_missing_received_at_never_raises(self):
        row = ae_row("a")
        row["received_at"] = None
        snap = snapshot(ae_rows=[row])
        self.assertEqual(snap["clocks"]["overdue_count"], 0)
        self.assertEqual(snap["clocks"]["upcoming_count"], 0)


# ─── D. The India clock is reused, not re-derived ───────────────────────────
class TestDashboardUsesThePhase1Clock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()

    def test_serious_case_deadline_matches_compute_reporting_deadline(self):
        # 14 days into the 15-day serious clock -> due in 24h, i.e. upcoming.
        row = ae_row("a", days_ago=14, serious=True)
        row["notification_deadline"] = ""  # force the computed path
        snap = snapshot(ae_rows=[row])
        deadline, remaining = pv.compute_reporting_deadline(
            True, datetime.fromisoformat(row["received_at"]), now=NOW
        )
        self.assertEqual(remaining, 1)
        entry = snap["clocks"]["upcoming"][0]
        self.assertEqual(entry["notification_deadline"], deadline.isoformat())
        self.assertEqual(entry["days_remaining"], remaining)
        self.assertEqual(entry["hours_remaining"], 24.0)
        self.assertEqual(snap["clocks"]["overdue_count"], 0)

    def test_overdue_days_match_the_clocks_negative_remaining(self):
        row = ae_row("a", days_ago=20, serious=True)
        row["notification_deadline"] = ""
        snap = snapshot(ae_rows=[row])
        _deadline, remaining = pv.compute_reporting_deadline(
            True, datetime.fromisoformat(row["received_at"]), now=NOW
        )
        self.assertLess(remaining, 0)
        entry = snap["clocks"]["overdue"][0]
        self.assertEqual(entry["days_overdue"], -remaining)

    def test_non_serious_case_uses_the_90_day_clock(self):
        # 88 days into the 90-day non-serious clock -> due in exactly 48h.
        row = ae_row("a", days_ago=88, serious=False)
        row["notification_deadline"] = ""
        snap = snapshot(ae_rows=[row])
        deadline, remaining = pv.compute_reporting_deadline(
            False, datetime.fromisoformat(row["received_at"]), now=NOW
        )
        self.assertEqual(remaining, 2)
        entry = snap["clocks"]["upcoming"][0]
        self.assertEqual(entry["notification_deadline"], deadline.isoformat())
        self.assertEqual(entry["days_remaining"], remaining)
        self.assertEqual(entry["hours_remaining"], 48.0)

    def test_a_hours_late_case_is_overdue_with_zero_whole_days(self):
        """The flag is the timestamp; the clock rounds up to 0 whole days."""
        row = ae_row("a", days_ago=1, serious=True)
        row["notification_deadline"] = (NOW - timedelta(hours=1)).isoformat()
        snap = snapshot(ae_rows=[row])
        self.assertEqual(snap["clocks"]["overdue_count"], 1)
        self.assertEqual(snap["clocks"]["overdue"][0]["days_overdue"], 0)

    def test_stored_deadline_is_the_legal_record(self):
        """A stored deadline wins over a recomputed one — it is what was filed."""
        row = ae_row("a", days_ago=1, serious=True)
        row["notification_deadline"] = (NOW - timedelta(hours=2)).isoformat()
        snap = snapshot(ae_rows=[row])
        self.assertEqual(snap["clocks"]["overdue_count"], 1)
        self.assertEqual(snap["clocks"]["upcoming_count"], 0)


# ─── E. PSUR calendar: 6-monthly x2y, then annual x2y ───────────────────────
class TestPsurSchedule(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()

    def window_months_back(self, months: int, day: int = 15):
        """psur_next_window for a product anchored N months before NOW."""
        total = NOW.month - 1 - months
        anchor = date(NOW.year + total // 12, total % 12 + 1, day)
        return dash.psur_next_window(anchor, now=NOW)

    def test_cadence_is_six_monthly_then_annual(self):
        self.assertEqual(
            [(m, c) for m, c in dash.PSUR_WINDOWS],
            [(6, "6-monthly"), (12, "6-monthly"), (18, "6-monthly"), (24, "6-monthly"),
             (36, "annual"), (48, "annual")],
            "research 3.3: 6-monthly for the first 2 years, annual for the next 2",
        )
        self.assertEqual(dash.PSUR_SCHEDULE_LABEL, "6-monthly x2y, then annual x2y")

    def test_full_schedule_is_six_windows(self):
        entries = dash.psur_schedule(date(2024, 1, 1))
        self.assertEqual(len(entries), 6)
        self.assertEqual([e["label"] for e in entries][:2], ["6-monthly #1", "6-monthly #2"])
        self.assertEqual([e["label"] for e in entries][4:], ["annual #5", "annual #6"])

    def test_brand_new_product_next_window_is_6_monthly_1(self):
        found = self.window_months_back(0)  # anchored today
        self.assertFalse(found["due_now"], "the first window has not opened yet")
        self.assertEqual(found["next"]["label"], "6-monthly #1")
        self.assertEqual(found["next"]["due_date"], "2026-09-15")

    def test_half_year_old_product_next_window_is_6_monthly_2(self):
        # anchored 2025-09-15: #1 (2026-03-15) is due today, #2 is next.
        found = self.window_months_back(6)
        self.assertTrue(found["due_now"], "a PSUR window is open")
        self.assertEqual(found["next"]["label"], "6-monthly #2")
        self.assertEqual(found["next"]["due_date"], "2026-09-15")

    def test_two_and_a_half_year_old_product_is_annual(self):
        # anchored 2023-09-15: #4 (2025-09-15) opened, #5 (2026-09-15) is next.
        found = self.window_months_back(30)
        self.assertTrue(found["due_now"], "the year-2 window is still open")
        self.assertEqual(found["next"]["label"], "annual #5")
        self.assertEqual(found["next"]["due_date"], "2026-09-15")

    def test_three_and_a_half_year_old_product_is_annual_6(self):
        # anchored 2022-09-15: #5 (2025-09-15) is open, #6 (2026-09-15) is next.
        found = self.window_months_back(42)
        self.assertTrue(found["due_now"], "the year-3 window is still open")
        self.assertEqual(found["next"]["label"], "annual #6")
        self.assertEqual(found["next"]["due_date"], "2026-09-15")

    def test_four_year_old_product_has_no_further_window(self):
        # anchored 2022-03-15: #6 (the 4-year annual report) is due today.
        found = self.window_months_back(48)
        self.assertTrue(found["due_now"], "the final window is the one due now")
        self.assertIsNone(found["next"])
        self.assertEqual(found["next_label"], "N/A")

    def test_over_four_years_is_not_due_and_says_na(self):
        found = self.window_months_back(60)  # anchored 2021-03-15
        self.assertFalse(found["due_now"], "the schedule ended, nothing is due")
        self.assertIsNone(found["next"])
        self.assertEqual(found["next_label"], "N/A")

    def test_window_dates_are_calendar_months_not_30_day_blocks(self):
        entries = dash.psur_schedule(date(2024, 1, 31))
        self.assertEqual(entries[0]["due_date"], "2024-07-31")
        self.assertEqual(entries[1]["due_date"], "2025-01-31")

    def test_month_end_clamps_rather_than_overflowing(self):
        entries = dash.psur_schedule(date(2024, 8, 31))
        self.assertEqual(entries[0]["due_date"], "2025-02-28")

    def test_age_days_is_reported(self):
        self.assertEqual(
            self.window_months_back(0)["age_days"], (NOW.date() - date(2026, 3, 15)).days
        )

    def test_a_window_opens_on_its_due_date_not_the_day_before(self):
        # #1 is due 2026-03-16 for a 2025-09-16 anchor: tomorrow, so not open.
        self.assertFalse(
            dash.psur_next_window(date(2025, 9, 16), now=NOW)["due_now"],
            "a window must not open a day early",
        )
        # #1 is due 2026-03-15 for a 2025-09-15 anchor: today, so open.
        self.assertTrue(dash.psur_next_window(date(2025, 9, 15), now=NOW)["due_now"])

    def test_psur_schedule_payload_for_products(self):
        payload = dash.build_psur_schedule(
            [
                product_row("p1", "Amox 500", date(2025, 9, 15)),
                product_row("p2", "Beta cream", date(2020, 1, 10)),
                product_row("p3", "Gamma 250", date(2023, 9, 15)),
            ],
            now=NOW,
        )
        self.assertEqual(payload["products"], 3)
        # Amox 500 (window #1 open today) + Gamma 250 (year-2 window open);
        # Beta cream is past the four-year schedule, so nothing is owed.
        self.assertEqual(payload["due_now"], 2)
        self.assertEqual(payload["schedule"], dash.PSUR_SCHEDULE_LABEL)
        names = [e["product_name"] for e in payload["entries"]]
        self.assertEqual(names, sorted(names), "entries are sorted for a stable view")
        by_name = {e["product_name"]: e for e in payload["entries"]}
        self.assertEqual(by_name["Amox 500"]["next_window"], "6-monthly #2")
        self.assertTrue(by_name["Amox 500"]["due_now"])
        self.assertEqual(by_name["Beta cream"]["next_window"], "N/A")
        self.assertFalse(by_name["Beta cream"]["due_now"])
        self.assertEqual(by_name["Gamma 250"]["next_window"], "annual #5")

    def test_inactive_products_are_excluded_from_the_schedule(self):
        payload = dash.build_psur_schedule(
            [product_row("p1", "Live", date(2025, 9, 15), active=True),
             product_row("p2", "Retired", date(2025, 9, 15), active=False)],
            now=NOW,
        )
        self.assertEqual(payload["products"], 1)
        self.assertEqual([e["product_name"] for e in payload["entries"]], ["Live"])

    def test_dashboard_embeds_the_same_psur_payload(self):
        snap = snapshot(product_rows=[product_row("p1", "Amox 500", date(2025, 9, 15))])
        self.assertEqual(snap["psur"]["products"], 1)
        self.assertEqual(snap["psur"]["entries"][0]["next_window"], "6-monthly #2")


# ─── F. Audit trail ─────────────────────────────────────────────────────────
class TestDashboardAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()

    def test_count_is_a_7_day_pv_window(self):
        rows = [
            audit_row("c1", "pv_case_intake", days_ago=0),
            audit_row("c2", "pqc_disposition", days_ago=6.9),
            audit_row("c3", "pv_case_intake", days_ago=7.1),  # outside
            audit_row("c4", "data_breach", days_ago=0),  # not a PV event
        ]
        snap = snapshot(audit_rows=rows)
        self.assertEqual(snap["audit"]["window_days"], 7)
        self.assertEqual(snap["audit"]["count"], 2)
        self.assertEqual(
            snap["audit"]["by_event_type"], {"pqc_disposition": 1, "pv_case_intake": 1}
        )

    def test_only_pv_event_types_count(self):
        for event_type in ("pv_case_intake", "pv_e2b_prepared", "pqc_disposition"):
            with self.subTest(event_type):
                self.assertTrue(dash.is_pv_audit_event(event_type))
        for event_type in ("data_breach", "consent_withdrawal", "", "incident"):
            with self.subTest(event_type):
                self.assertFalse(dash.is_pv_audit_event(event_type))

    def test_audit_trail_lists_events_newest_first(self):
        rows = [
            audit_row("c1", "pv_case_intake", days_ago=3),
            audit_row("c2", "pv_case_intake", days_ago=0),
        ]
        trail = dash.build_audit_trail(rows, days=30, now=NOW)
        self.assertEqual([e["id"] for e in trail["events"]], ["c2", "c1"])
        self.assertEqual(trail["window_days"], 30)
        self.assertEqual(trail["count"], 2)

    def test_audit_window_is_configurable_and_bounded(self):
        rows = [audit_row("c1", "pv_case_intake", days_ago=20)]
        self.assertEqual(dash.build_audit_trail(rows, days=30, now=NOW)["count"], 1)
        self.assertEqual(dash.build_audit_trail(rows, days=7, now=NOW)["count"], 0)

    def test_empty_audit_rows(self):
        self.assertEqual(dash.build_audit_trail([], days=30, now=NOW)["count"], 0)
        self.assertEqual(dash.build_audit_trail(None, days=30, now=NOW)["events"], [])


# ─── G. Determinism ─────────────────────────────────────────────────────────
class TestDashboardDeterminism(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HAVE_DASH:
            require_dash()

    def build_ae(self):
        return [
            ae_row("b1", days_ago=20, serious=True),
            ae_row("a1", deadline=(NOW + timedelta(hours=2)).isoformat()),
            ae_row("a2", deadline=(NOW + timedelta(hours=10)).isoformat()),
            ae_row("a3", days_ago=2, serious=True),
        ]

    def build_pqc(self):
        return [pqc_row("q2", "capa", "recall"), pqc_row("q1", "captured")]

    def build_mi(self):
        return [mi_row("m2", "open"), mi_row("m1", "answered")]

    def build_products(self):
        return [
            product_row("p2", "Beta", date(2023, 9, 15)),
            product_row("p1", "Alpha", date(2025, 9, 15)),
        ]

    def build_audit(self):
        return [
            audit_row("e2", "pv_e2b_prepared", days_ago=1),
            audit_row("e1", "pv_case_intake", days_ago=2),
        ]

    def build(self):
        return snapshot(
            ae_rows=self.build_ae(),
            pqc_rows=self.build_pqc(),
            mi_rows=self.build_mi(),
            product_rows=self.build_products(),
            audit_rows=self.build_audit(),
        )

    def test_same_rows_twice_is_identical(self):
        self.assertEqual(self.build(), self.build())

    def test_input_order_never_changes_the_snapshot(self):
        again = snapshot(
            ae_rows=[
                ae_row("a1", deadline=(NOW + timedelta(hours=2)).isoformat()),
                ae_row("a2", deadline=(NOW + timedelta(hours=10)).isoformat()),
                ae_row("a3", days_ago=2, serious=True),
                ae_row("b1", days_ago=20, serious=True),
            ],
            pqc_rows=[pqc_row("q1", "captured"), pqc_row("q2", "capa", "recall")],
            mi_rows=[mi_row("m1", "answered"), mi_row("m2", "open")],
            product_rows=[
                product_row("p1", "Alpha", date(2025, 9, 15)),
                product_row("p2", "Beta", date(2023, 9, 15)),
            ],
            audit_rows=[
                audit_row("e1", "pv_case_intake", days_ago=2),
                audit_row("e2", "pv_e2b_prepared", days_ago=1),
            ],
        )
        self.assertEqual(again, self.build())

    def test_no_set_or_frozenset_leaks_into_the_payload(self):
        """A set is not JSON-serialisable and has no defined order."""
        def walk(node, path="$"):
            if isinstance(node, (set, frozenset)):
                self.fail(f"unordered set at {path}")
            if isinstance(node, dict):
                for key, value in node.items():
                    self.assertIsInstance(key, str, f"non-string key at {path}")
                    walk(value, f"{path}.{key}")
            elif isinstance(node, (list, tuple)):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(self.build())

    def test_overdue_and_upcoming_lists_are_sorted(self):
        snap = self.build()
        self.assertEqual(
            [e["case_id"] for e in snap["clocks"]["overdue"]], ["b1"]
        )
        self.assertEqual(
            [e["case_id"] for e in snap["clocks"]["upcoming"]], ["a1", "a2"]
        )

    def test_orm_rows_give_the_same_snapshot_as_dicts(self):
        """The route passes SQLAlchemy rows, not dicts: both must work."""
        from types import SimpleNamespace

        def obj(row):
            return SimpleNamespace(**row)

        as_dicts = self.build()
        as_objects = snapshot(
            ae_rows=[obj(r) for r in self.build_ae()],
            pqc_rows=[obj(r) for r in self.build_pqc()],
            mi_rows=[obj(r) for r in self.build_mi()],
            product_rows=[obj(r) for r in self.build_products()],
            audit_rows=[obj(r) for r in self.build_audit()],
        )
        self.assertEqual(as_objects, as_dicts)

    def test_uuid_ids_are_serialised_as_strings(self):
        import uuid as uuid_mod

        case = ae_row("a", deadline=(NOW + timedelta(hours=5)).isoformat())
        case["id"] = uuid_mod.UUID("11111111-1111-4111-8111-111111111111")
        snap = snapshot(ae_rows=[case])
        self.assertIsInstance(snap["clocks"]["upcoming"][0]["case_id"], str)


# ─── H. /api/pv route contracts ─────────────────────────────────────────────
DASHBOARD_ROUTE = ("get", "/dashboard")
PSUR_ROUTE = ("get", "/dashboard/psur")
AUDIT_ROUTE = ("get", "/audit")
DASHBOARD_ENDPOINT = "pv_dashboard_ep"
PSUR_ENDPOINT = "pv_dashboard_psur_ep"
AUDIT_ENDPOINT = "pv_audit_ep"


class TestDashboardRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(PV_ROUTER)
        cls.tree = py_tree(PV_ROUTER)

    def test_all_three_routes_exist(self):
        found = {(verb, path) for verb, path, _ in endpoints(self.tree)}
        for route in (DASHBOARD_ROUTE, PSUR_ROUTE, AUDIT_ROUTE):
            with self.subTest(route):
                self.assertIn(route, found)

    def test_router_imports_the_dashboard_service(self):
        self.assertIn("from app.services.pv_dashboard import", self.text)

    def test_every_new_route_is_identity_gated(self):
        for name in (DASHBOARD_ENDPOINT, PSUR_ENDPOINT, AUDIT_ENDPOINT):
            with self.subTest(name):
                block = fn_block(self.text, name)
                self.assertIn("get_current_user", block, f"{name} must be identity-gated")
                self.assertNotIn("WEBHOOK_SERVICE_TOKEN", block)

    def test_dashboard_is_read_only(self):
        for name in (DASHBOARD_ENDPOINT, PSUR_ENDPOINT, AUDIT_ENDPOINT):
            with self.subTest(name):
                block = fn_block(self.text, name)
                for writer in (
                    "create_adverse_event",
                    "create_quality_complaint",
                    "create_medical_inquiry",
                    "create_compliance_event",
                    "update_quality_complaint",
                ):
                    self.assertNotIn(writer, block, f"{name} is a read-only view")
                self.assertIn("uuid", block, f"{name}: clinic_id must be validated")

    def test_dashboard_reads_every_pv_table_through_a_repo_helper(self):
        block = fn_block(self.text, DASHBOARD_ENDPOINT)
        for helper in (
            "list_adverse_events",
            "list_quality_complaints",
            "list_medical_inquiries",
            "list_products",
            "list_compliance_events",
        ):
            with self.subTest(helper):
                self.assertIn(helper, block, f"dashboard must read via {helper}")
        self.assertIn("build_dashboard_snapshot", block, "no numbers are computed inline")

    def test_psur_route_reads_products_and_reuses_the_helper(self):
        block = fn_block(self.text, PSUR_ENDPOINT)
        self.assertIn("list_products", block)
        self.assertIn("build_psur_schedule", block, "reuse the pure helper")

    def test_audit_route_reads_compliance_events(self):
        block = fn_block(self.text, AUDIT_ENDPOINT)
        self.assertIn("list_compliance_events", block)
        self.assertIn("build_audit_trail", block)
        self.assertIn("days", block, "the audit window is a parameter")

    def test_dashboard_does_not_recompute_the_clock(self):
        """The route must delegate, never re-derive the India clock."""
        block = fn_block(self.text, DASHBOARD_ENDPOINT)
        self.assertNotIn(
            "timedelta",
            block,
            "the dashboard must not re-implement the reporting clock",
        )

    def test_audit_days_are_bounded(self):
        block = fn_block(self.text, AUDIT_ENDPOINT)
        self.assertIn("422", block, "a bad audit window is a 422, not a 500")
