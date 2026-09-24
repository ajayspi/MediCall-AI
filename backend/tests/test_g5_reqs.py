"""G5 acceptance tests: requirements cleanup + Knowlarity client (stdlib only).

RED before fix (2026-09-24): backend/requirements.txt still pins
stripe/celery/gunicorn/psycopg2-binary/sqlalchemy-asyncio (sqlalchemy-asyncio
is NOT a real PyPI package — async ships inside SQLAlchemy 2.0); no
pytest/pytest-asyncio/ruff; payment pins stale or wrong (razorpay==1.4.1 old,
'phonepe' is not the official package name, cashfree-pg==1.0.0 unverifiable);
backend/app/services/knowlarity.py does not exist.

GREEN after fix: requirements.txt drops the stale pins, pins the verified
payment SDKs (razorpay==2.0.1, phonepe-pg-sdk-python==2.3.0, cashfree-pg==6.0.1),
adds an uncommented dev/test section (pytest/pytest-asyncio/ruff);
.env.example documents KNOWLARITY_AUTHORIZATION; services/knowlarity.py provides
the stdlib-importable Knowlarity SR API client (config, headers, URL + payload
builders, id extractor) with lazy httpx transport.

Run: python3 tests/test_g5_reqs.py  (exit 0 = green)
"""
import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

REQUIREMENTS = BACKEND / "requirements.txt"
ENV_EXAMPLE = BACKEND / ".env.example"

BANNED_PACKAGES = (
    "stripe",
    "celery",
    "gunicorn",
    "psycopg2-binary",
    "sqlalchemy-asyncio",
)

CORE_STACK = (
    "fastapi",
    "httpx",
    "sqlalchemy",
    "pgvector",
    "openai",
    "deepgram-sdk",
    "livekit-agents",
    "elevenlabs",
    "exotel",
    "twilio",
)


def package_name(token: str) -> str:
    """'uvicorn[standard]==0.29.0' -> 'uvicorn'; 'python-jose[c]' -> 'python-jose'."""
    name = token.split("==")[0].strip().lower()
    if "[" in name:
        name = name[: name.index("[")]
    return name


def pinned_packages() -> dict:
    """{name: version} for every active (non-comment, '==') dependency."""
    pins = {}
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "==" not in line:
            continue
        name, version = line.split("==", 1)
        pins[package_name(name)] = version.strip()
    return pins


class TestRequirementsSource(unittest.TestCase):
    def setUp(self):
        self.pins = pinned_packages()

    def test_stale_packages_removed(self):
        for banned in BANNED_PACKAGES:
            self.assertNotIn(banned, self.pins, f"{banned} still pinned")

    def test_dev_lint_deps_present_and_uncommented(self):
        for dep in ("pytest", "pytest-asyncio", "ruff"):
            self.assertIn(dep, self.pins, f"{dep} missing/uncommented")

    def test_dev_deps_are_pinned(self):
        for dep in ("pytest", "pytest-asyncio", "ruff"):
            self.assertTrue(
                self.pins.get(dep, ""), f"{dep} must have a == version pin"
            )

    def test_payment_pins_verified(self):
        self.assertEqual(self.pins.get("razorpay"), "2.0.1")
        self.assertIn("phonepe-pg-sdk-python", self.pins)
        self.assertNotIn("phonepe", self.pins, "'phonepe' is not the official SDK")
        self.assertEqual(self.pins.get("cashfree-pg"), "6.0.1")

    def test_async_driver_kept(self):
        self.assertIn("asyncpg", self.pins)

    def test_core_stack_kept(self):
        for dep in CORE_STACK:
            self.assertIn(dep, self.pins, f"core dep {dep} dropped")


class TestEnvExample(unittest.TestCase):
    def test_knowlarity_authorization_documented(self):
        text = ENV_EXAMPLE.read_text(encoding="utf-8")
        self.assertIn("KNOWLARITY_AUTHORIZATION", text)


class TestKnowlarityClient(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # RED pre-import: services/knowlarity.py does not exist yet
        from app.services import knowlarity

        cls.K = knowlarity

    def test_from_env_reads_keys(self):
        saved = dict(os.environ)
        try:
            os.environ["KNOWLARITY_API_KEY"] = "k-api-1"
            os.environ["KNOWLARITY_AUTHORIZATION"] = "k-auth-1"
            os.environ["KNOWLARITY_SIP_URI"] = "sip:medicall@knowlarity.com"
            cfg = self.K.from_env()
            self.assertEqual(cfg.api_key, "k-api-1")
            self.assertEqual(cfg.authorization, "k-auth-1")
            self.assertEqual(cfg.k_number, "sip:medicall@knowlarity.com")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_from_env_missing_keys_empty(self):
        saved = dict(os.environ)
        try:
            for key in (
                "KNOWLARITY_API_KEY",
                "KNOWLARITY_AUTHORIZATION",
                "KNOWLARITY_SIP_URI",
            ):
                os.environ.pop(key, None)
            cfg = self.K.from_env()
            self.assertEqual(cfg.api_key, "")
            self.assertEqual(cfg.authorization, "")
            self.assertEqual(cfg.k_number, "")
        finally:
            os.environ.clear()
            os.environ.update(saved)

    def test_defaults_verified_from_docs(self):
        self.assertEqual(
            self.K.DEFAULT_BASE_URL,
            "https://kpi.knowlarity.com/Basic/v1/account",
        )
        self.assertEqual(self.K.DEFAULT_TIMEZONE, "Asia/Kolkata")

    def test_default_base_url_endpoints(self):
        cfg = self.K.KnowlarityConfig()
        self.assertEqual(
            self.K.makecall_url(cfg),
            f"{self.K.DEFAULT_BASE_URL}/call/makecall",
        )
        self.assertEqual(
            self.K.campaign_url(cfg),
            f"{self.K.DEFAULT_BASE_URL}/call/campaign",
        )
        self.assertEqual(
            self.K.order_status_url(cfg, "ord-9"),
            f"{self.K.DEFAULT_BASE_URL}/call/campaign/order-status/?order_id=ord-9",
        )

    def test_headers_include_sr_auth(self):
        cfg = self.K.KnowlarityConfig(api_key="x1", authorization="a1")
        h = self.K.headers(cfg)
        self.assertEqual(h["x-api-key"], "x1")
        self.assertEqual(h["authorization"], "a1")
        self.assertEqual(h["accept"], "application/json")
        self.assertEqual(h["content-type"], "application/json")

    def test_makecall_payload(self):
        cfg = self.K.KnowlarityConfig(k_number="sip:k@knowlarity.com")
        p = self.K.makecall_payload(
            cfg, agent_number="99100", customer_number="9876543210"
        )
        self.assertEqual(p["k_number"], "sip:k@knowlarity.com")
        self.assertEqual(p["agent_number"], "99100")
        self.assertEqual(p["customer_number"], "9876543210")
        self.assertEqual(p["caller_id"], "sip:k@knowlarity.com")
        self.assertIn("uniqueid", p["additional_params"])

    def test_makecall_payload_explicit_caller_id(self):
        cfg = self.K.KnowlarityConfig(k_number="sip:k@knowlarity.com")
        p = self.K.makecall_payload(
            cfg, customer_number="+919876543210", agent_number="99100", caller_id="99220"
        )
        self.assertEqual(p["caller_id"], "99220")

    def test_campaign_payload_defaults(self):
        cfg = self.K.KnowlarityConfig(k_number="1209876")
        p = self.K.campaign_payload(cfg, sound_id=42, additional_number="9876543210")
        self.assertEqual(p["sound_id"], "42")
        self.assertEqual(p["additional_number"], "9876543210")
        self.assertEqual(p["k_number"], "1209876")
        self.assertEqual(p["timezone"], "Asia/Kolkata")
        self.assertIn(" ", p["start_time"])  # 'yyyy-MM-dd HH:mm'

    def test_campaign_payload_explicit_start_and_priority(self):
        cfg = self.K.KnowlarityConfig(k_number="1209876")
        p = self.K.campaign_payload(
            cfg,
            sound_id=7,
            additional_number="111",
            start_time="2026-09-25 10:30",
            priority=3,
        )
        self.assertEqual(p["start_time"], "2026-09-25 10:30")
        self.assertEqual(p["priority"], "3")

    def test_id_extractor_defensive(self):
        self.assertEqual(self.K._id_of({"request_id": "r1"}), "r1")
        self.assertEqual(self.K._id_of({"order_id": "o1"}), "o1")
        self.assertEqual(self.K._id_of({"id": 5}), "5")
        self.assertEqual(self.K._id_of({"ack": True}), "")

    def test_empty_config_constructs(self):
        cfg = self.K.KnowlarityConfig()
        self.assertEqual(cfg.api_key, "")
        self.assertGreater(cfg.timeout_seconds, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)