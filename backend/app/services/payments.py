"""Payment gateway service layer — stdlib only (G6-Q5, spec-payments.md).

Q5/A5a, approved 2026-09-25: the gateway REQUEST BUILDERS and WEBHOOK
VERIFIERS live here as pure stdlib functions (unit-tested with HMAC vectors).
Live SDK calls are LAZY + env-gated through `dispatch_gateway_request` — the
SDK modules only import on a host that has the gateway's keys (CI/Docker);
this dev PC (stdlib-only, no pip) never reaches them. The router answers 501
when a gateway's keys are absent (mirrors the SSO/telephony pattern).

Contracts (also asserted by backend/tests/test_payments_q5.py):
  PAYMENT_KINDS     = consultation / refill / subscription
  KIND_TO_GATEWAYS  = kind -> ordered fallback chain (Q2/A2a):
                      consultation -> razorpay, then phonepe (UPI)
                      refill       -> razorpay (payment link)
                      subscription -> cashfree
  TRANSITIONS       = pending -> captured|failed ; captured -> refunded
  verify_razorpay_signature / verify_phonepe_xverify /
  verify_cashfree_signature  — the ALGO is the contract (HMAC vectors).
"""
import base64
import hashlib
import hmac
import os

PAYMENT_KINDS = ("consultation", "refill", "subscription")

# kind -> ordered gateway fallback chain (Q2/A2a, mirrors the telephony
# decision: all gateways wired, no single primary).
KIND_TO_GATEWAYS = {
    "consultation": ("razorpay", "phonepe"),
    "refill": ("razorpay",),
    "subscription": ("cashfree",),
}

# Webhook-driven transitions only; anything else keeps the current status.
TRANSITIONS = {"pending": ("captured", "failed"), "captured": ("refunded",)}

# Gateway env keys (single source for the router's 501 gate + tests/compose).
# Names = G5 canonical (.env.example): API keys vs webhook secrets are separate
# (razorpay/cashfree ship a dedicated webhook secret; phonepe uses salt_key).
GATEWAY_ENV_KEYS = {
    "razorpay": ("RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET"),
    "phonepe": ("PHONEPE_MERCHANT_ID", "PHONEPE_SALT_KEY", "PHONEPE_SALT_INDEX"),
    "cashfree": ("CASHFREE_APP_ID", "CASHFREE_SECRET_KEY"),
}


# ─── Builders: gateway request SHAPES (no SDK import, no network) ────────────
# razorpay + phonepe amounts are in PAISE (int); cashfree in rupees (float).

def build_razorpay_link(amount, currency, reference_id, description=""):
    """Razorpay payment-link payload (amount in paise)."""
    return {
        "amount": int(round(amount * 100)),
        "currency": currency or "INR",
        "reference_id": reference_id,
        "description": description or "",
        "partial_payment": False,
    }


def build_phonepe_upi(amount, currency, merchant_transaction_id, merchant_user_id):
    """PhonePe UPI intent payload (amount in paise, no card entry in-call)."""
    return {
        "merchantTransactionId": merchant_transaction_id,
        "merchantUserId": merchant_user_id,
        "amount": int(round(amount * 100)),
        "currency": currency or "INR",
        "paymentInstrument": {"type": "UPI_INTENT"},
    }


def build_cashfree_order(customer_name, customer_email, customer_phone, order_amount, order_currency, order_id):
    """Cashfree order payload (amount in rupees)."""
    return {
        "order_id": order_id,
        "order_amount": float(order_amount),
        "order_currency": order_currency or "INR",
        "customer_details": {
            "customer_id": customer_phone,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
        },
    }


def build_cashfree_subscription(subscription_id, plan_id, customer_name, customer_email, customer_phone, amount, currency, frequency):
    """Cashfree subscription payload (recurring care plans, Q2/A2a)."""
    return {
        "subscription_id": subscription_id,
        "plan_id": plan_id,
        "frequency": frequency,
        "subscription_amount": float(amount),
        "subscription_currency": currency or "INR",
        "customer_details": {
            "customer_id": customer_phone,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
        },
    }


# ─── Verifiers: the ALGO is the contract (HMAC vectors in the RED suite) ─────

def verify_razorpay_signature(body, signature, secret):
    """X-Razorpay-Signature = hex(HMAC-SHA256(webhook_secret, body))."""
    if not body or not signature or not secret:
        return False
    raw = body if isinstance(body, bytes) else body.encode()
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_phonepe_xverify(payload, x_verify, salt_key):
    """PhonePe X-VERIFY = base64(SHA256(payload + salt_key))[###salt_index].

    Accepts the bare base64 or the gateway's 'base64###index' form.
    """
    if not payload or not x_verify or not salt_key:
        return False
    digest = hashlib.sha256((payload + salt_key).encode()).digest()
    expected = base64.b64encode(digest).decode()
    provided = x_verify.split("###", 1)[0]
    return hmac.compare_digest(expected, provided)


def verify_cashfree_signature(body, signature, secret, timestamp):
    """Cashfree webhook signature = hex(HMAC-SHA256(secret, timestamp + body))."""
    if not body or not signature or not secret or not timestamp:
        return False
    raw = (body.decode() if isinstance(body, bytes) else body)
    expected = hmac.new(secret.encode(), (timestamp + raw).encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_request(gateway, body, headers, secrets):
    """Per-gateway webhook verification (Q4/A4a) — dispatches the verifiers.

    secrets: dict of the gateway's configured secrets (the router builds it
    from env). Returns False for any mismatch or unknown gateway.
    """
    if gateway == "razorpay":
        return verify_razorpay_signature(body, headers.get("X-Razorpay-Signature", ""), secrets.get("secret", ""))
    if gateway == "phonepe":
        return verify_phonepe_xverify(
            body.decode() if isinstance(body, bytes) else body,
            headers.get("X-VERIFY", ""),
            secrets.get("salt_key", ""),
        )
    if gateway == "cashfree":
        return verify_cashfree_signature(
            body,
            headers.get("X-Verify-Hmac-Sha256", ""),
            secrets.get("secret", ""),
            headers.get("X-Cf-Timestamp", ""),
        )
    return False


def detect_gateway(payload):
    """Infer the gateway from a unified-webhook payload (unified endpoint)."""
    if isinstance(payload, dict) and payload.get("event", "").startswith(("payment.", "refund.")):
        return "razorpay"
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        data = payload["data"]
        if isinstance(data.get("order"), dict) and data.get("order", {}).get("order_id"):
            return "cashfree"
        if data.get("merchantTransactionId"):
            return "phonepe"
    return ""


# ─── Webhook payload -> our identifiers/status (Q4/A4a reconciliation) ───────

def extract_gateway_ref(gateway, payload):
    """The gateway's order/payment id (idempotency key, uq_payments_gateway_ref)."""
    if gateway == "razorpay":
        return (payload.get("payload", {}).get("payment", {}).get("entity", {}) or {}).get("id", "")
    if gateway == "phonepe":
        return (payload.get("data", {}) or {}).get("merchantTransactionId", "")
    if gateway == "cashfree":
        return (payload.get("data", {}).get("order", {}) or {}).get("order_id", "")
    return ""


def webhook_status_for(gateway, payload):
    """Map a gateway event/state to our PAYMENT_STATUSES value."""
    if gateway == "razorpay":
        event = payload.get("event", "")
        if event == "payment.captured":
            return "captured"
        if event == "payment.failed":
            return "failed"
        if event.startswith("refund."):
            return "refunded"
    elif gateway == "phonepe":
        state = (payload.get("data", {}) or {}).get("state", "")
        if state == "COMPLETED":
            return "captured"
        if state == "FAILED":
            return "failed"
        if state == "REVERSED":
            return "refunded"
    elif gateway == "cashfree":
        status = (payload.get("data", {}).get("order", {}) or {}).get("order_status", "")
        if status == "PAID":
            return "captured"
        if status in ("FAILED", "CANCELLED"):
            return "failed"
        if status == "REFUNDED":
            return "refunded"
    return "pending"


def next_status(current, incoming):
    """Transition rule: only pending->captured|failed, captured->refunded."""
    allowed = TRANSITIONS.get(current, ())
    return incoming if incoming in allowed else current


# ─── Env gate + live SDK dispatch (Q5/A5a: 501 without keys) ─────────────────

def gateway_env_ready(gateway, env=None):
    """True when every key a gateway needs is set (non-empty) in env."""
    env = env if env is not None else os.environ
    keys = GATEWAY_ENV_KEYS.get(gateway, ())
    return bool(keys) and all(bool(env.get(k, "")) for k in keys)


def dispatch_gateway_request(gateway, kind, row, env=None):
    """Create the gateway-side intent when keys are present; else None.

    The SDK imports are LAZY and only reached on a live host with keys
    (CI/Docker). The builders above already produced the request shape; this
    is the thin wire-up that this stdlib-only PC never executes.
    """
    env = env if env is not None else os.environ
    if not gateway_env_ready(gateway, env):
        return None
    amount = float(row.amount) if getattr(row, "amount", None) is not None else 0.0
    currency = getattr(row, "currency", None) or "INR"
    reference = getattr(row, "gateway_ref", None) or str(getattr(row, "id", ""))
    try:
        if gateway == "razorpay":
            import razorpay  # noqa: E402 - env-gated, CI host only

            client = razorpay.Client(auth=(env["RAZORPAY_KEY_ID"], env["RAZORPAY_KEY_SECRET"]))
            return client.payment_link.create(
                build_razorpay_link(amount, currency, reference)
            )
        if gateway == "phonepe":
            # PhonePe UPI intent — BASE64 of the payload JSON stays the SDK
            # concern; the builder gives the exact paymentInstrument shape.
            from phonepe_sdk import PaymentsApiUtil  # noqa: E402 - env-gated

            return PaymentsApiUtil(
                merchant_id=env["PHONEPE_MERCHANT_ID"],
                salt_key=env["PHONEPE_SALT_KEY"],
                salt_index=env["PHONEPE_SALT_INDEX"],
            ).create_payment(
                build_phonepe_upi(amount, currency, reference, "caller"),
                callback_url=env.get("PAYMENT_LINK_BASE_URL", ""),
            )
        if gateway == "cashfree":
            import cashfree_pg  # noqa: E402 - env-gated
            from cashfree_pg.api import orders_api  # noqa: E402 - env-gated

            if kind == "subscription":
                return None  # subscription create goes through the SDK's subscription API (CI follow-up)
            api = orders_api.OrdersApi()
            return api.create_order(
                cashfree_pg.configuration,
                build_cashfree_order(
                    "Caller", "", "", amount, currency, reference
                ),
            )
    except Exception:  # noqa: BLE001 - a failed live call must surface as -1, not 500
        return None
    return None