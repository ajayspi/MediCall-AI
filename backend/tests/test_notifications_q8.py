"""G6-Q8 notifications RED contract: multi-channel messaging layer (WhatsApp-first).

Contract (sign-off 2026-09-25, Q1=A1c Q2=A2c Q3=A3a Q4=A4a):
- WhatsApp (Meta Cloud API) is the PRIMARY channel; SMS (Knowlarity -> MSG91)
  and email (SMTP) form the fallback chains; push (FCM) is a kind stub.
- Full catalog: payment_link / appointment_reminder / no_show_followup / otp /
  payment_receipt, each with a DEFAULT_CHANNEL_ORDER and per-language templates
  for all 5 languages (hi/en/ta/te/bn).
- Env-gated stdlib request builders + lazy dispatch_channel (third-party clients
  import ONLY on a keyed host); send_notification walks the kind's channel order
  with the first READY channel; non-fatal `no_provider`/`all_channels_failed`.
- New `notifications` tenant table + uq_notifications_provider_ref +
  notifications_send policy (service_request bypass OR-clause); writes under
  service_request_ctx(); payment create kind=link/upi fires payment_link
  non-fatally; auth.py untouched.
"""

import ast
import os
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TESTS = BACKEND / "tests"
APP = BACKEND / "app"

try:
    from app.services import notifications as ntf  # noqa: E402
except ImportError:  # scaffold: module not built yet (RED)
    ntf = None

SUPPORTED_LANGUAGES = ("hi", "en", "ta", "te", "bn")
CHANNELS = ("whatsapp", "sms", "email", "push")
KINDS = ("payment_link", "appointment_reminder", "no_show_followup", "otp", "payment_receipt")
EMAIL_KINDS = ("payment_link", "appointment_reminder", "payment_receipt")
WHATSAPP_FIRST_KINDS = ("payment_link", "appointment_reminder", "no_show_followup", "otp")
THIRD_PARTY_MODULES = {"httpx", "requests", "twilio", "whatsapp", "msg91", "firebase_admin"}


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

    Slices by LINE, not by character offset: splitlines(keepends=True) keeps
    each line intact so text[node.lineno-1:node.end_lineno] spans the def line
    down to the function's last line (same helper as test_auth_enforcement).
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


def module_imported_names(tree, module: str) -> set:
    out = set()
    if tree is None:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            for alias in node.names:
                out.add(alias.asname or alias.name)
    return out


def imports_at_module_level(tree) -> list:
    """[(kind, name)] where kind in {"import", "from"} — module-level only."""
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(("import", alias.name.split(".")[0]))
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(("from", node.module.split(".")[0]))
    return out


def render_test(result: dict) -> str:
    return result.get("message", "")


def recorder(calls):
    """A dispatch fake: records (channel, kind) and answers per channel."""
    def _fake(channel, kind, row, env=None):
        calls.append((channel, kind))
        if channel == "whatsapp":
            return {"status": "failed", "channel": channel, "provider": "meta"}
        return {"status": "sent", "channel": channel, "provider": "msg91", "provider_ref": "ref-1"}
    return _fake


def record_all(calls):
    """A dispatch fake that always sends on the first ready channel."""
    def _fake(channel, kind, row, env=None):
        calls.append((channel, kind))
        return {"status": "sent", "channel": channel, "provider": "meta", "provider_ref": "ref-1"}
    return _fake


class TestModuleStructure(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(ntf, "app/services/notifications.py missing (RED)")

    def test_module_parses(self):
        tree = py_tree(APP / "services" / "notifications.py")
        self.assertIsNotNone(tree, "notifications.py must parse")

    def test_docstring_marks_phase(self):
        text = read(APP / "services" / "notifications.py")
        self.assertIn("G6-Q8", text[:600], "docstring must keep the G6-Q8 marker")

    def test_no_third_party_imports_at_module_level(self):
        tree = py_tree(APP / "services" / "notifications.py")
        if tree is None:
            self.fail("notifications.py missing")
        banned = [m for _, m in imports_at_module_level(tree) if m in THIRD_PARTY_MODULES]
        self.assertEqual([], banned, "third-party clients must stay inside lazy dispatch")

    def test_catalog_constants_exist(self):
        for const in (
            "MESSAGE_TEMPLATES",
            "MESSAGE_SUBJECTS",
            "DEFAULT_CHANNEL_ORDER",
            "CHANNEL_PROVIDER_KEYS",
            "SMS_PROVIDER_KEYS",
            "SMS_PROVIDER_ORDER",
        ):
            self.assertTrue(hasattr(ntf, const), f"notifications.py missing {const}")

    def test_channels_cover_catalog(self):
        self.assertTrue(set(ntf.CHANNELS) >= set(CHANNELS), "CHANNELS must cover whatsapp/sms/email/push")
        self.assertTrue(set(ntf.KINDS) >= set(KINDS), "KINDS must cover the full catalog")

    def test_whatsapp_first_chains(self):
        for kind in WHATSAPP_FIRST_KINDS:
            order = ntf.DEFAULT_CHANNEL_ORDER[kind]
            self.assertIsInstance(order, tuple)
            self.assertGreater(len(order), 0, f"{kind}: empty channel order")
            self.assertEqual("whatsapp", order[0], f"{kind} must prefer whatsapp (Q1=A1c)")
            self.assertIn("sms", order[1:], f"{kind} must keep the SMS fallback leg")

    def test_receipt_prefers_email(self):
        self.assertEqual("email", ntf.DEFAULT_CHANNEL_ORDER["payment_receipt"][0])

    def test_channel_provider_keys_cover_all_channels(self):
        for channel in CHANNELS:
            keys = ntf.CHANNEL_PROVIDER_KEYS[channel]
            self.assertIsInstance(keys, tuple)
            self.assertGreater(len(keys), 0, f"{channel}: no env keys")
            for key in keys:
                self.assertIsInstance(key, str)
                self.assertTrue(key.isupper(), f"{channel}: env key not uppercase: {key}")

    def test_sms_keys_distinct_from_telephony(self):
        sms_keys = set(ntf.CHANNEL_PROVIDER_KEYS["sms"])
        self.assertNotIn("KNOWLARITY_API_KEY", sms_keys, "SMS keys must not collide with telephony call keys")

    def test_required_functions_exist(self):
        for fn in (
            "channel_env_ready",
            "sms_provider_ready",
            "resolve_channel_provider",
            "dispatch_channel",
            "send_notification",
            "render_template",
            "build_whatsapp_text",
            "build_sms_request",
            "build_email_mime",
            "build_push_payload",
        ):
            self.assertTrue(callable(getattr(ntf, fn, None)), f"notifications.py missing {fn}")


class TestTemplates(unittest.TestCase):
    def test_every_kind_every_language(self):
        for kind in KINDS:
            langs = ntf.MESSAGE_TEMPLATES[kind]
            self.assertEqual(set(SUPPORTED_LANGUAGES), set(langs), f"{kind}: language set must be the 5")
            for lang in SUPPORTED_LANGUAGES:
                text = langs[lang]
                self.assertIsInstance(text, str)
                self.assertGreater(len(text), 0)

    def test_fixed_english_vectors(self):
        self.assertEqual(
            "Your {clinic} payment link: {url}",
            ntf.MESSAGE_TEMPLATES["payment_link"]["en"],
        )
        self.assertEqual(
            "Your MediCall verification code is {code}. It is valid for 10 minutes.",
            ntf.MESSAGE_TEMPLATES["otp"]["en"],
        )
        self.assertEqual(
            "Reminder: your appointment at {clinic} is at {time}.",
            ntf.MESSAGE_TEMPLATES["appointment_reminder"]["en"],
        )

    def test_placeholders_survive_in_other_languages(self):
        for lang in SUPPORTED_LANGUAGES:
            self.assertIn("{url}", ntf.MESSAGE_TEMPLATES["payment_link"][lang])
            self.assertIn("{code}", ntf.MESSAGE_TEMPLATES["otp"][lang])
            self.assertIn("{clinic}", ntf.MESSAGE_TEMPLATES["appointment_reminder"][lang])
            self.assertIn("{amount}", ntf.MESSAGE_TEMPLATES["payment_receipt"][lang])

    def test_subjects_for_email_kinds(self):
        for kind in EMAIL_KINDS:
            subject = ntf.MESSAGE_SUBJECTS[kind]
            self.assertIsInstance(subject, str)
            self.assertGreater(len(subject), 0)
        for kind in ("otp", "no_show_followup"):
            self.assertNotIn(kind, ntf.MESSAGE_SUBJECTS, f"{kind}: no email leg, no subject")


class TestChannelEnvGate(unittest.TestCase):
    def test_all_channels_closed_with_empty_env(self):
        for channel in CHANNELS:
            self.assertFalse(ntf.channel_env_ready(channel, {}), f"{channel}: must be closed with no keys")

    def test_whatsapp_requires_both_keys(self):
        self.assertFalse(ntf.channel_env_ready("whatsapp", {"WHATSAPP_TOKEN": "t"}))
        self.assertFalse(ntf.channel_env_ready("whatsapp", {"WHATSAPP_PHONE_ID": "p"}))
        self.assertTrue(ntf.channel_env_ready("whatsapp", {"WHATSAPP_TOKEN": "t", "WHATSAPP_PHONE_ID": "p"}))

    def test_sms_any_provider_unlocks_channel(self):
        self.assertTrue(ntf.channel_env_ready("sms", {"KNOWLARITY_SMS_TOKEN": "t", "KNOWLARITY_SMS_SENDER_ID": "s"}))
        self.assertTrue(ntf.channel_env_ready("sms", {"MSG91_AUTH_KEY": "a", "MSG91_SENDER_ID": "s", "MSG91_ROUTE": "4"}))
        self.assertFalse(ntf.channel_env_ready("sms", {"KNOWLARITY_SMS_TOKEN": "t"}))

    def test_email_requires_all_smtp_keys(self):
        partial = {k: "v" for k in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")}
        self.assertFalse(ntf.channel_env_ready("email", partial))
        partial["SMTP_FROM"] = "noreply@medicall.in"
        self.assertTrue(ntf.channel_env_ready("email", partial))

    def test_provider_resolution(self):
        self.assertEqual("meta", ntf.resolve_channel_provider("whatsapp", {"WHATSAPP_TOKEN": "t", "WHATSAPP_PHONE_ID": "p"}))
        self.assertEqual(
            "knowlarity",
            ntf.resolve_channel_provider("sms", {"KNOWLARITY_SMS_TOKEN": "t", "KNOWLARITY_SMS_SENDER_ID": "s"}),
        )
        self.assertEqual(
            "msg91",
            ntf.resolve_channel_provider("sms", {"MSG91_AUTH_KEY": "a", "MSG91_SENDER_ID": "s", "MSG91_ROUTE": "4"}),
        )
        self.assertIsNone(ntf.resolve_channel_provider("sms", {}))


class TestLazyDispatch(unittest.TestCase):
    def test_dispatch_returns_dict_without_raising(self):
        result = ntf.dispatch_channel("whatsapp", "payment_link", {"id": "x"}, {})
        self.assertIsInstance(result, dict)
        self.assertEqual("queued", result.get("status"))
        self.assertEqual("no_provider", result.get("reason"))

    def test_dispatch_sms_no_provider(self):
        result = ntf.dispatch_channel("sms", "otp", {"id": "x"}, {})
        self.assertEqual("queued", result.get("status"))
        self.assertEqual("no_provider", result.get("reason"))

    def test_dispatch_impl_is_env_gated(self):
        text = read(APP / "services" / "notifications.py")
        block = fn_block(text, "dispatch_channel")
        self.assertGreater(len(block), 0, "dispatch_channel must exist")
        self.assertIn("env", block, "dispatch_channel must gate on env keys")
        self.assertIn("no_provider", block)


class TestSendOrchestration(unittest.TestCase):
    SEND_ARGS = ("payment_link", "+919876543210", "en", {"url": "https://pay.example/link-1", "clinic": "QuickCare"})

    def test_no_keys_queues_non_fatal(self):
        calls = []
        result = ntf.send_notification(*self.SEND_ARGS, env={}, dispatch=record_all(calls))
        self.assertEqual([], calls, "dispatch must NOT be called with no ready channel")
        self.assertEqual("queued", result["status"])
        self.assertEqual("no_provider", result["reason"])
        self.assertIn("https://pay.example/link-1", render_test(result))

    def test_whatsapp_used_when_only_whatsapp_keys(self):
        calls = []
        env = {"WHATSAPP_TOKEN": "t", "WHATSAPP_PHONE_ID": "p"}
        result = ntf.send_notification(*self.SEND_ARGS, env=env, dispatch=record_all(calls))
        self.assertEqual([("whatsapp", "payment_link")], calls)
        self.assertEqual("whatsapp", result["channel"])
        self.assertEqual("meta", result["provider"])
        self.assertEqual("sent", result["status"])

    def test_sms_only_env_uses_msg91(self):
        calls = []
        env = {"MSG91_AUTH_KEY": "a", "MSG91_SENDER_ID": "s", "MSG91_ROUTE": "4"}
        result = ntf.send_notification(*self.SEND_ARGS, env=env, dispatch=record_all(calls))
        self.assertEqual([("sms", "payment_link")], calls, "must skip whatsapp when not ready")
        self.assertEqual("sms", result["channel"])
        self.assertEqual("msg91", result["provider"])

    def test_whatsapp_fail_then_sms_fallback(self):
        calls = []
        env = {
            "WHATSAPP_TOKEN": "t",
            "WHATSAPP_PHONE_ID": "p",
            "MSG91_AUTH_KEY": "a",
            "MSG91_SENDER_ID": "s",
            "MSG91_ROUTE": "4",
        }
        result = ntf.send_notification(*self.SEND_ARGS, env=env, dispatch=recorder(calls))
        self.assertEqual([("whatsapp", "payment_link"), ("sms", "payment_link")], calls)
        self.assertEqual("sms", result["channel"])
        self.assertEqual("msg91", result["provider"])
        self.assertEqual("sent", result["status"])

    def test_all_channels_fail_records_queued(self):
        env = {"WHATSAPP_TOKEN": "t", "WHATSAPP_PHONE_ID": "p"}
        result = ntf.send_notification(*self.SEND_ARGS, env=env, dispatch=recorder([]))
        self.assertEqual("queued", result["status"])
        self.assertEqual("all_channels_failed", result["reason"])

    def test_receipt_uses_email_when_email_only(self):
        calls = []
        env = {"SMTP_HOST": "h", "SMTP_PORT": "587", "SMTP_USER": "u", "SMTP_PASSWORD": "p", "SMTP_FROM": "noreply@medicall.in"}
        result = ntf.send_notification(
            "payment_receipt", "a@b.c", "en", {"clinic": "QuickCare", "amount": "Rs 499"}, env=env, dispatch=record_all(calls)
        )
        self.assertEqual([("email", "payment_receipt")], calls)
        self.assertEqual("email", result["channel"])
        self.assertEqual("smtp", result["provider"])

    def test_result_contract_fields(self):
        result = ntf.send_notification(*self.SEND_ARGS, env={}, dispatch=record_all([]))
        for field in ("kind", "recipient", "language", "channel", "provider", "status", "reason", "message"):
            self.assertIn(field, result, f"send_notification result missing {field}")


class TestEmailMime(unittest.TestCase):
    def test_builds_stdlib_email_message(self):
        from email.message import EmailMessage

        msg = ntf.build_email_mime("Your link", "Body {url}", "a@b.c")
        self.assertIsInstance(msg, EmailMessage)
        self.assertEqual("Your link", msg["Subject"])
        self.assertEqual("a@b.c", msg["To"])
        self.assertIn("Body {url}", msg.get_content())

    def test_default_from(self):
        msg = ntf.build_email_mime("S", "B", "a@b.c")
        self.assertEqual("noreply@medicall.in", msg["From"])

    def test_from_from_env(self):
        env = {"SMTP_FROM": "clinic@medicall.in"}
        msg = ntf.build_email_mime("S", "B", "a@b.c", env=env)
        self.assertEqual("clinic@medicall.in", msg["From"])


class TestRequestShapes(unittest.TestCase):
    def test_whatsapp_text_shape(self):
        shape = ntf.build_whatsapp_text("+919876543210", "hi", env={"WHATSAPP_PHONE_ID": "pid"})
        self.assertIsInstance(shape, dict)
        self.assertEqual("whatsapp", shape.get("messaging_product"))
        self.assertEqual("+919876543210", shape.get("to"))
        self.assertEqual("hi", shape.get("text", {}).get("body"))

    def test_sms_shape_contains_phone_and_message(self):
        for provider in ("knowlarity", "msg91"):
            env = (
                {"KNOWLARITY_SMS_TOKEN": "t", "KNOWLARITY_SMS_SENDER_ID": "s"}
                if provider == "knowlarity"
                else {"MSG91_AUTH_KEY": "a", "MSG91_SENDER_ID": "s", "MSG91_ROUTE": "4"}
            )
            shape = ntf.build_sms_request(provider, "+919876543210", "hi", env=env)
            self.assertIsInstance(shape, dict)
            self.assertIn("+919876543210", str(shape))
            self.assertIn("hi", str(shape))

    def test_push_payload_shape(self):
        shape = ntf.build_push_payload("Reminder", {"clinic": "QuickCare"})
        self.assertEqual("MediCall", shape.get("title"))
        self.assertEqual("Reminder", shape.get("body"))
        self.assertIn("clinic", str(shape), "push payload must carry the template params")


class TestSchemaTable(unittest.TestCase):
    SCHEMA = BACKEND / "postgres_schema.sql"

    def test_notifications_table_exists(self):
        sql = read(self.SCHEMA)
        self.assertIn("CREATE TABLE notifications", sql)

    def test_core_columns_present(self):
        sql = read(self.SCHEMA)
        block = sql.split("CREATE TABLE notifications", 1)[1].split(");", 1)[0] if "CREATE TABLE notifications" in sql else ""
        for col in ("kind", "recipient", "language", "channel", "provider", "status", "template", "created_at"):
            self.assertIn(col, block, f"notifications table missing column {col}")

    def test_unique_index_on_provider_ref(self):
        sql = read(self.SCHEMA)
        self.assertIn("uq_notifications_provider_ref", sql)

    def test_service_policy(self):
        sql = read(self.SCHEMA)
        self.assertIn("CREATE POLICY notifications_send", sql)
        self.assertIn("app.service_request", sql)


class TestPostgresOrm(unittest.TestCase):
    def test_notification_crud_helpers(self):
        text = read(APP / "db" / "postgres.py")
        self.assertIn("notifications", text)
        self.assertIn("create_notification", text)
        self.assertIn("list_notifications", text)


class TestRouterStructure(unittest.TestCase):
    ROUTER = APP / "api" / "notifications.py"
    MAIN = BACKEND / "main.py"

    def test_router_file_exists_and_parses(self):
        self.assertTrue(self.ROUTER.exists(), "app/api/notifications.py missing")
        self.assertIsNotNone(py_tree(self.ROUTER))

    def test_router_prefix(self):
        text = read(self.ROUTER)
        self.assertIn('prefix="/api/notifications"', text)

    def test_endpoints_are_send_and_list(self):
        tree = py_tree(self.ROUTER)
        self.assertIsNotNone(tree)
        found = set()
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
        self.assertEqual({("get", ""), ("post", "/send")}, found)

    def test_send_endpoint_identity_gated(self):
        text = read(self.ROUTER)
        block = fn_block(text, "send_notification_ep")
        self.assertGreater(len(block), 0, "send_notification_ep must exist")
        self.assertIn("Depends(get_current_user)", block)

    def test_registered_in_main(self):
        tree = py_tree(self.MAIN)
        names = module_imported_names(tree, "app.api")
        self.assertIn("notifications", names, "main.py must import app.api.notifications")
        self.assertIn("notifications", read(self.MAIN))


class TestPaymentsHook(unittest.TestCase):
    def test_payments_imports_notifications(self):
        tree = py_tree(APP / "api" / "payments.py")
        names = module_imported_names(tree, "app.services.notifications")
        self.assertIn("send_notification", names)

    def test_create_payment_fires_payment_link(self):
        text = read(APP / "api" / "payments.py")
        block = fn_block(text, "create_payment_ep")
        self.assertIn("send_notification", block)
        self.assertIn("link", block)
        self.assertIn("upi", block)


class TestAuthUntouched(unittest.TestCase):
    def test_auth_not_rewired(self):
        text = read(APP / "api" / "auth.py")
        self.assertNotIn("send_notification", text, "auth OTP rewiring is a deferred follow-on")
        self.assertNotIn("app.services.notifications", text)


class TestSmokeDocsRefs(unittest.TestCase):
    def test_smoke_covers_notifications(self):
        self.assertIn("/api/notifications", read(BACKEND / "scripts" / "smoke_api.py"))

    def test_api_contracts_doc(self):
        contracts = BACKEND.parent / "docs" / "uml" / "03-api-contracts.md"
        self.assertIn("/api/notifications", read(contracts))

    def test_env_example_has_canonical_keys(self):
        env_text = read(BACKEND / ".env.example")
        for channel in CHANNELS:
            for key in ntf.CHANNEL_PROVIDER_KEYS[channel]:
                self.assertIn(key, env_text, f"{key} must appear in .env.example")


if __name__ == "__main__":
    unittest.main()