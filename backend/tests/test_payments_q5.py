"""Payments phase (spec-payments.md, G6-Q5) — RED contracts.

Tests the Q5 flip WITHOUT a live Postgres or gateway SDKs (same pattern as
test_g4_voice/test_auth_enforcement): the stdlib gateway service is imported
and behavior-tested (HMAC webhook vectors, builders, status/ref extraction,
transition rules); the router/schema/env/smoke/docs contracts are structural
AST/text assertions.

Approved 2026-09-25: Q1=A1a consult+refill bill, Q2=A2a kind→gateway map +
fallback, Q3=A3a in-call wait in PAYMENT_SENT, Q4=A4a per-gateway HMAC + shared
service token + unified /api/payments/webhook (idempotent by gateway_ref),
Q5=A5a stdlib layer now, live SDK requests env-gated (501 without keys).

RED before implementation (2026-09-25): every assertion here FAILS on
g-enforce's scaffold — no app/services/payments.py, no webhook route, no
kind/expires_at/unique gateway_ref, no payments_manage service clause, no
gateway env vars, smoke has no webhook/501 flow, contracts doc has no
/api/payments/webhook.
"""
import ast
import base64
import hashlib
import hmac
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

API_DIR = BACKEND / "app" / "api"
SERVICES = BACKEND / "app" / "services"
SCHEMA = BACKEND / "postgres_schema.sql"
POSTGRES = BACKEND / "app" / "db" / "postgres.py"
SCHEMAS = BACKEND / "app" / "schemas"
SMOKE = BACKEND / "scripts" / "smoke_api.py"
COMPOSE = BACKEND.parent / "docker-compose.yml"
ENV_EXAMPLE = BACKEND / ".env.example"
CONTRACTS = BACKEND.parent / "docs" / "uml" / "03-api-contracts.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def fns(tree) -> dict:
    """{name: node} for every function in a module AST."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = node
    return out


def fn_block(text: str, name: str) -> str:
    """The source text of one function (via AST line offsets), or ''."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    node = fns(tree).get(name)
    if node is None:
        return ""
    lines = text.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1:node.end_lineno])


def module_literal_consts(text: str) -> dict:
    """{Name: literal value} for module-level Tuple/Dict assignments."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return {}
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.Tuple, ast.Dict)
        ):
            try:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    out[target.id] = ast.literal_eval(node.value)
            except ValueError:
                continue
    return out


# The stdlib gateway service — imported for behavior tests. Absent at RED.
try:
    from app.services import payments as pay_svc  # noqa: E402
    HAVE_SVC = True
except ImportError:  # pragma: no cover - RED state
    pay_svc = None
    HAVE_SVC = False


# Signed webhook test vectors (the ALGO is the contract; expected values are
# computed here with stdlib and the service must accept exactly these).
RZ_SECRET = "rzp_test_secret_001"
RZ_BODY = b'{"event":"payment.captured","payload":{"payment":{"entity":{"id":"pay_ABC123"}}}}'
RZ_SIG = hmac.new(RZ_SECRET.encode(), RZ_BODY, hashlib.sha256).hexdigest()

PP_PAYLOAD = '{"merchantId":"M1","merchantTransactionId":"TXN_789","state":"COMPLETED"}'
PP_SALT = "phonepe-salt-key"
PP_XVERIFY = (
    base64.b64encode(hashlib.sha256((PP_PAYLOAD + PP_SALT).encode()).digest()).decode()
    + "###1"
)

CF_SECRET = "cf_secret_002"
CF_TS = "2026-09-26T10:35:00Z"
CF_BODY = b'{"data":{"order":{"order_id":"order_456","order_status":"PAID"}}}'
CF_SIG = hmac.new(CF_SECRET.encode(), (CF_TS + CF_BODY.decode()).encode(), hashlib.sha256).hexdigest()


# ─── B. app/services/payments.py — stdlib gateway layer ──────────────────────

class TestPaymentService(unittest.TestCase):
    def test_service_module_exists(self):
        self.assertTrue((SERVICES / "payments.py").exists(), "app/services/payments.py missing")

    def test_kind_to_gateway_map(self):
        consts = module_literal_consts(read(SERVICES / "payments.py"))
        self.assertEqual(("consultation", "refill", "subscription"), consts.get("PAYMENT_KINDS"))
        self.assertEqual(
            {
                "consultation": ("razorpay", "phonepe"),
                "refill": ("razorpay",),
                "subscription": ("cashfree",),
            },
            consts.get("KIND_TO_GATEWAYS"),
            "kind→gateway order = fallback chain (Q2/A2a)",
        )

    def test_status_transition_rules(self):
        consts = module_literal_consts(read(SERVICES / "payments.py"))
        self.assertEqual(
            {"pending": ("captured", "failed"), "captured": ("refunded",)},
            consts.get("TRANSITIONS"),
        )

    def test_builders_exist(self):
        names = set(fns(ast.parse(read(SERVICES / "payments.py"))))
        for fn in (
            "build_razorpay_link",
            "build_phonepe_upi",
            "build_cashfree_order",
            "build_cashfree_subscription",
        ):
            self.assertIn(fn, names, f"services.payments missing {fn}")

    def test_razorpay_link_builder_shape(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        link = pay_svc.build_razorpay_link(500.0, "INR", "ref-1")
        self.assertEqual(50000, link["amount"], "razorpay amounts are in paise")
        self.assertEqual("INR", link["currency"])
        self.assertEqual("ref-1", link["reference_id"])
        self.assertIn("description", link)

    def test_phonepe_upi_builder_shape(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        upi = pay_svc.build_phonepe_upi(500.0, "INR", "mtx-1", "user-1")
        self.assertEqual(50000, upi["amount"], "phonepe amounts are in paise")
        self.assertEqual("mtx-1", upi["merchantTransactionId"])
        self.assertEqual("UPI_INTENT", upi["paymentInstrument"]["type"])

    def test_cashfree_order_builder_shape(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        order = pay_svc.build_cashfree_order(
            "Smoke", "c@x.in", "+919000000000", 500.0, "INR", "ord-1"
        )
        self.assertEqual(500.0, order["order_amount"], "cashfree amounts are rupees")
        self.assertEqual("INR", order["order_currency"])
        self.assertEqual("ord-1", order["order_id"])
        self.assertIn("customer_details", order)

    def test_cashfree_subscription_builder_shape(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        sub = pay_svc.build_cashfree_subscription(
            "sub-1", "plan-9", "Smoke", "c@x.in", "+919000000000", 99.0, "INR", "monthly"
        )
        self.assertEqual("sub-1", sub["subscription_id"])
        self.assertEqual("plan-9", sub["plan_id"])
        self.assertIn("customer_details", sub)
        self.assertEqual("monthly", sub["frequency"])

    def test_razorpay_signature_verify(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertTrue(pay_svc.verify_razorpay_signature(RZ_BODY, RZ_SIG, RZ_SECRET))

    def test_razorpay_signature_rejects_tamper(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertFalse(pay_svc.verify_razorpay_signature(b"tampered", RZ_SIG, RZ_SECRET))
        self.assertFalse(pay_svc.verify_razorpay_signature(RZ_BODY, "deadbeef", RZ_SECRET))

    def test_phonepe_xverify_verify(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertTrue(pay_svc.verify_phonepe_xverify(PP_PAYLOAD, PP_XVERIFY, PP_SALT))

    def test_phonepe_xverify_rejects_tamper(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertFalse(pay_svc.verify_phonepe_xverify(PP_PAYLOAD + "x", PP_XVERIFY, PP_SALT))
        self.assertFalse(pay_svc.verify_phonepe_xverify(PP_PAYLOAD, "bogus###1", PP_SALT))

    def test_cashfree_signature_verify(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertTrue(pay_svc.verify_cashfree_signature(CF_BODY, CF_SIG, CF_SECRET, CF_TS))

    def test_cashfree_signature_rejects_tamper(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertFalse(pay_svc.verify_cashfree_signature(b"tampered", CF_SIG, CF_SECRET, CF_TS))
        self.assertFalse(pay_svc.verify_cashfree_signature(CF_BODY, "cafe", CF_SECRET, CF_TS))

    def test_extract_gateway_ref_razorpay(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        payload = {"payload": {"payment": {"entity": {"id": "pay_ABC123"}}}}
        self.assertEqual("pay_ABC123", pay_svc.extract_gateway_ref("razorpay", payload))

    def test_extract_gateway_ref_phonepe(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        payload = {"data": {"merchantTransactionId": "TXN_789"}}
        self.assertEqual("TXN_789", pay_svc.extract_gateway_ref("phonepe", payload))

    def test_extract_gateway_ref_cashfree(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        payload = {"data": {"order": {"order_id": "order_456"}}}
        self.assertEqual("order_456", pay_svc.extract_gateway_ref("cashfree", payload))

    def test_webhook_status_razorpay(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("captured", pay_svc.webhook_status_for("razorpay", {"event": "payment.captured"}))
        self.assertEqual("failed", pay_svc.webhook_status_for("razorpay", {"event": "payment.failed"}))
        self.assertEqual("refunded", pay_svc.webhook_status_for("razorpay", {"event": "refund.processed"}))

    def test_webhook_status_phonepe(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("captured", pay_svc.webhook_status_for("phonepe", {"data": {"state": "COMPLETED"}}))
        self.assertEqual("failed", pay_svc.webhook_status_for("phonepe", {"data": {"state": "FAILED"}}))
        self.assertEqual("refunded", pay_svc.webhook_status_for("phonepe", {"data": {"state": "REVERSED"}}))

    def test_webhook_status_cashfree(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("captured", pay_svc.webhook_status_for("cashfree", {"data": {"order": {"order_status": "PAID"}}}))
        self.assertEqual("failed", pay_svc.webhook_status_for("cashfree", {"data": {"order": {"order_status": "FAILED"}}}))
        self.assertEqual("refunded", pay_svc.webhook_status_for("cashfree", {"data": {"order": {"order_status": "REFUNDED"}}}))

    def test_next_status_from_pending(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("captured", pay_svc.next_status("pending", "captured"))
        self.assertEqual("failed", pay_svc.next_status("pending", "failed"))

    def test_next_status_captured_to_refunded(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("refunded", pay_svc.next_status("captured", "refunded"))

    def test_next_status_invalid_keeps_current(self):
        self.assertTrue(HAVE_SVC, "app/services/payments.py missing")
        self.assertEqual("pending", pay_svc.next_status("pending", "refunded"))
        self.assertEqual("captured", pay_svc.next_status("captured", "failed"))
        self.assertEqual("pending", pay_svc.next_status("pending", "bogus"))


# ─── C. Router: webhook (identity-free, signed) + env-gated create ───────────

class TestPaymentsRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(API_DIR / "payments.py")

    def test_webhook_route_registered(self):
        self.assertIn('"/webhook"', self.text)

    def test_webhook_is_identity_free_signed_service(self):
        block = fn_block(self.text, "payments_webhook")
        self.assertNotIn("get_current_user", block,
                         "webhook is gateway→server: no identity dependency")
        self.assertIn("Request", block, "webhook consumes the raw Request")
        self.assertIn("service_request_ctx", block,
                      "webhook writes arm the RLS service bypass")
        self.assertIn("WEBHOOK_SERVICE_TOKEN", block,
                      "webhook requires the shared service token")
        self.assertIn("gateway_ref", block, "idempotency keyed by gateway_ref")

    def test_create_env_gated_manual_keyless(self):
        block = fn_block(self.text, "create_payment_ep")
        self.assertIn("501", block, "missing gateway keys => 501 (Q5/A5a)")
        self.assertIn("manual", block, "manual gateway stays keyless")

    def test_payment_schema_accepts_kind(self):
        self.assertIn("kind", read(SCHEMAS / "payment.py"))


# ─── D. Schema + ORM: kind, expires_at, unique gateway_ref, service clause ───

class TestPaymentSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read(SCHEMA)

    def test_payments_table_kind_and_expires_at(self):
        block = self.text.split("CREATE TABLE payments", 1)[1].split(");", 1)[0]
        self.assertIn("kind TEXT", block)
        self.assertIn("expires_at TIMESTAMPTZ", block)

    def test_unique_gateway_ref_index(self):
        self.assertIn("uq_payments_gateway_ref", self.text)
        self.assertIn("gateway_ref", self.text)

    def test_payments_manage_service_clause(self):
        block = self.text.split("CREATE POLICY payments_manage", 1)[1].split("CREATE POLICY", 1)[0]
        self.assertIn("app.service_request", block,
                      "userless webhook status updates need the service bypass")

    def test_orm_payment_kind_expires_at(self):
        text = read(POSTGRES)
        block = text.split("class Payment(Base):", 1)[1].split("\n    def __repr__", 1)[0]
        self.assertIn("kind", block)
        self.assertIn("expires_at", block)


# ─── E. Env vars (compose + .env.example) ────────────────────────────────────

class TestPaymentEnv(unittest.TestCase):
    GATEWAY_KEYS = (
        "RAZORPAY_KEY_ID",
        "RAZORPAY_KEY_SECRET",
        "PHONEPE_MERCHANT_ID",
        "PHONEPE_KEY",
        "PHONEPE_IV",
        "CASHFREE_APP_ID",
        "CASHFREE_SECRET",
        "PAYMENT_LINK_BASE_URL",
    )

    def test_env_example_gateway_keys(self):
        text = read(ENV_EXAMPLE)
        for key in self.GATEWAY_KEYS:
            self.assertIn(key, text, f".env.example missing {key}")

    def test_compose_gateway_keys(self):
        text = read(COMPOSE)
        self.assertIn("CASHFREE_APP_ID", text)
        self.assertIn("PAYMENT_LINK_BASE_URL", text)
        self.assertIn("WEBHOOK_SERVICE_TOKEN", text)


# ─── F/G. Smoke flow + docs contract ─────────────────────────────────────────

class TestSmokeAndDocs(unittest.TestCase):
    def test_smoke_payments_webhook_flow(self):
        self.assertIn('"/api/payments/webhook"', read(SMOKE))

    def test_smoke_env_gate_501(self):
        self.assertIn("501", read(SMOKE))

    def test_docs_contracts_list_webhook(self):
        self.assertIn("/api/payments/webhook", read(CONTRACTS))


if __name__ == "__main__":
    unittest.main(verbosity=2)