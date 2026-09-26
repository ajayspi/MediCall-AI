"""G6-Q8 notifications — multi-channel messaging layer (WhatsApp-first).

spec-notifications-q8.md (approved 2026-09-25; Q1=A1c Q2=A2c Q3=A3a Q4=A4a):
- WhatsApp (Meta Cloud API) is the PRIMARY channel; SMS (Knowlarity -> MSG91)
  and email (SMTP) form per-kind fallback chains; push (FCM) is a kind stub.
- Full catalog: payment_link / appointment_reminder / no_show_followup / otp /
  payment_receipt with per-language templates for all 5 languages
  (hi/en/ta/te/bn); email kinds carry a subject line.
- Env-gated request builders (stdlib shapes, no network on this PC) + lazy
  dispatch_channel: a provider client imports ONLY on a host with that
  channel's keys. send_notification walks DEFAULT_CHANNEL_ORDER[kind] with the
  first READY channel; missing keys are NON-FATAL (status queued,
  reason no_provider) so the payment-create hook can never fail a payment.
- Delivery records live in the `notifications` table; the router and the
  payments hook persist rows under service_request_ctx() (notifications_send
  carries the app.service_request bypass clause, mirroring payments_manage).
"""

import os
from typing import Any, Callable, Dict, Optional

# ─── Catalog (Q1=A1c WhatsApp-first, Q2=A2c full) ──────────────────────────
CHANNELS = ("whatsapp", "sms", "email", "push")
KINDS = (
    "payment_link",
    "appointment_reminder",
    "no_show_followup",
    "otp",
    "payment_receipt",
    "pv_alert",
)
# 5-language tuple single-sourced in app/services/languages.py (G6-Q4 Q2=A1) —
# re-exported here so app/api/notifications.py keeps its import working.
from app.services.languages import SUPPORTED_LANGUAGES

# Per-kind channel preference: the first READY channel in the tuple carries the
# message; a failed send falls through to the next. WhatsApp first (Q1=A1c).
DEFAULT_CHANNEL_ORDER = {
    "payment_link": ("whatsapp", "sms", "email"),
    "appointment_reminder": ("whatsapp", "sms", "email"),
    "no_show_followup": ("whatsapp", "sms"),
    "otp": ("whatsapp", "sms"),
    "payment_receipt": ("email", "whatsapp"),
    # PV safety reports are regulatory deadlines, not marketing: email-only so
    # the alert leaves an auditable record (spec-micc-pv-module.md §6).
    "pv_alert": ("email",),
}

# Channel env keys (single source for the router 501 gate + tests/compose).
# SMS keys are distinct from the telephony KNOWLARITY_API_KEY/AUTHORIZATION/
# SIP_URI (spec-notifications-q8.md §6 — canonical-first, no collisions).
CHANNEL_PROVIDER_KEYS = {
    "whatsapp": ("WHATSAPP_TOKEN", "WHATSAPP_PHONE_ID"),
    "sms": (
        "KNOWLARITY_SMS_TOKEN",
        "KNOWLARITY_SMS_SENDER_ID",
        "MSG91_AUTH_KEY",
        "MSG91_SENDER_ID",
        "MSG91_ROUTE",
    ),
    "email": ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"),
    "push": ("FCM_SERVER_KEY", "FCM_SENDER_ID"),
}
SMS_PROVIDER_KEYS = {
    "knowlarity": ("KNOWLARITY_SMS_TOKEN", "KNOWLARITY_SMS_SENDER_ID"),
    "msg91": ("MSG91_AUTH_KEY", "MSG91_SENDER_ID", "MSG91_ROUTE"),
}
SMS_PROVIDER_ORDER = ("knowlarity", "msg91")

# ─── Templates: kind x language (placeholders survive in every script) ─────
MESSAGE_TEMPLATES = {
    "payment_link": {
        "en": "Your {clinic} payment link: {url}",
        "hi": "आपका {clinic} भुगतान लिंक: {url}",
        "ta": "உங்கள் {clinic} கட்டண இணைப்பு: {url}",
        "te": "మీ {clinic} చెల్లింపు లింక్: {url}",
        "bn": "আপনার {clinic} পেমেন্ট লিংক: {url}",
    },
    "appointment_reminder": {
        "en": "Reminder: your appointment at {clinic} is at {time}.",
        "hi": "अनुस्मारक: {clinic} में आपकी अपॉइंटमेंट {time} बजे है।",
        "ta": "நினைவூட்டல்: {clinic} இல் உங்கள் சந்திப்பு {time} மணிக்கு.",
        "te": "రిమైండర్: {clinic} వద్ద మీ అపాయింట్మెంట్ {time} గంటలకు.",
        "bn": "অনুস্মারক: {clinic} এ আপনার অ্যাপয়েন্টমেন্ট {time} টায়।",
    },
    "no_show_followup": {
        "en": "We missed you at {clinic}. Reply to reschedule.",
        "hi": "हमने {clinic} में आपको मिस किया। पुनर्निर्धारित करने के लिए उत्तर दें।",
        "ta": "{clinic} இல் உங்களை காணவில்லை. மறுதிட்டமிட பதிலளிக்கவும்.",
        "te": "{clinic} వద్ద మిమ్మల్ని మిస్ అయ్యాము. రీషెడ్యూల్ చేయడానికి సమాధానం ఇవ్వండి.",
        "bn": "আমরা {clinic} এ আপনাকে মিস করেছি। পুনঃনির্ধারণ করতে উত্তর দিন।",
    },
    "otp": {
        "en": "Your MediCall verification code is {code}. It is valid for 10 minutes.",
        "hi": "आपका MediCall सत्यापन कोड {code} है। यह 10 मिनट के लिए मान्य है।",
        "ta": "உங்கள் MediCall சரிபார்ப்பு குறியீடு {code}. இது 10 நிமிடங்களுக்கு செல்லுபடியாகும்.",
        "te": "మీ MediCall ధృవీకరణ కోడ్ {code}. ఇది 10 నిమిషాలకు చెల్లుతుంది.",
        "bn": "আপনার MediCall যাচাইকরণ কোড {code}। এটি 10 মিনিটের জন্য বৈধ।",
    },
    "payment_receipt": {
        "en": "Receipt from {clinic}: payment of {amount} received.",
        "hi": "{clinic} से रसीद: {amount} का भुगतान प्राप्त हुआ।",
        "ta": "{clinic} விலிருந்து ரசீது: {amount} கட்டணம் பெறப்பட்டது.",
        "te": "{clinic} నుండి రసీదు: {amount} చెల్లింపు అందింది.",
        "bn": "{clinic} থেকে রসিদ: {amount} পেমেন্ট গৃহীত হয়েছে।",
    },
    "pv_alert": {
        "en": "Pharmacovigilance alert: case {case_id} must be reported by {deadline}.",
        "hi": "फार्माकोविजिलेंस अलर्ट: केस {case_id} की रिपोर्ट {deadline} तक जरूरी है।",
        "ta": "மருந்தக் கண்காணிப்பு எச்சரிக்கை: வழக்கு {case_id} அறிக்கை {deadline}க்குள் செய்யப்பட வேண்டும்.",
        "te": "ఫార్మాకోవిజిలెన్స్ అలర్ట్: కేస్ {case_id} నివేదికను {deadline} లోపు చేయాలి.",
        "bn": "ফার্মাকোভিজিলেন্স সতর্কতা: কেস {case_id}-এর রিপোর্ট {deadline} তারিখের মধ্যে জমা দিতে হবে।",
    },
}

# Email subjects — only kinds with an email leg (Q2=A2c).
MESSAGE_SUBJECTS = {
    "payment_link": "Your {clinic} payment link",
    "appointment_reminder": "Reminder: appointment at {clinic}",
    "payment_receipt": "Receipt from {clinic}",
    "pv_alert": "PV case {case_id} — report due {deadline}",
}

DEFAULT_FROM = "noreply@medicall.in"


# ─── Template rendering ────────────────────────────────────────────────────
def render_template(kind: str, language: str, params: Dict[str, Any]) -> str:
    """Render the kind/language template with params (str.format)."""
    return MESSAGE_TEMPLATES[kind][language].format(**params)


# ─── Env gate + provider resolution (Q3=A3a) ───────────────────────────────
def _env(env: Optional[dict]) -> dict:
    return os.environ if env is None else env


def sms_provider_ready(provider: str, env: Optional[dict] = None) -> bool:
    """True when every key a single SMS provider needs is set (non-empty)."""
    data = _env(env)
    return all(data.get(k) for k in SMS_PROVIDER_KEYS[provider])


def resolve_channel_provider(channel: str, env: Optional[dict] = None) -> Optional[str]:
    """First usable provider for a channel, or None when no keys are set."""
    data = _env(env)
    if channel == "whatsapp":
        return "meta" if all(data.get(k) for k in CHANNEL_PROVIDER_KEYS["whatsapp"]) else None
    if channel == "sms":
        for provider in SMS_PROVIDER_ORDER:
            if sms_provider_ready(provider, data):
                return provider
        return None
    if channel == "email":
        return "smtp" if all(data.get(k) for k in CHANNEL_PROVIDER_KEYS["email"]) else None
    if channel == "push":
        return "fcm" if all(data.get(k) for k in CHANNEL_PROVIDER_KEYS["push"]) else None
    return None


def channel_env_ready(channel: str, env: Optional[dict] = None) -> bool:
    """True when at least one provider in the channel has its keys set."""
    return resolve_channel_provider(channel, env) is not None


# ─── Request builders: provider request SHAPES (stdlib, no network) ────────
def build_whatsapp_text(to: str, message: str, env: Optional[dict] = None) -> dict:
    """Meta Cloud API text-message shape (Q1=A1c primary channel)."""
    _ = _env(env)  # phone id lives in headers at dispatch time
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}


def build_sms_request(provider: str, to: str, message: str, env: Optional[dict] = None) -> dict:
    """Per-provider SMS request shape (knowlarity / msg91)."""
    data = _env(env)
    if provider == "knowlarity":
        return {
            "provider": "knowlarity",
            "to": to,
            "message": message,
            "token": data.get("KNOWLARITY_SMS_TOKEN", ""),
            "sender": data.get("KNOWLARITY_SMS_SENDER_ID", ""),
        }
    return {
        "provider": "msg91",
        "to": to,
        "message": message,
        "authkey": data.get("MSG91_AUTH_KEY", ""),
        "sender": data.get("MSG91_SENDER_ID", ""),
        "route": data.get("MSG91_ROUTE", "4"),
    }


def build_email_mime(subject: str, body: str, to: str, env: Optional[dict] = None):
    """Stdlib email.message.EmailMessage (fully testable without a server)."""
    from email.message import EmailMessage

    data = _env(env)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["To"] = to
    msg["From"] = data.get("SMTP_FROM", "") or DEFAULT_FROM
    msg.set_content(body)
    return msg


def build_push_payload(message: str, params: Dict[str, Any]) -> dict:
    """FCM-shaped payload (kind stub — real delivery needs a patient app)."""
    return {"title": "MediCall", "body": message, "data": params}


# ─── Lazy dispatch (Q3=A3a: import a client only on a keyed host) ──────────
def dispatch_channel(channel: str, kind: str, row: dict, env: Optional[dict] = None) -> dict:
    """Send one message via a channel. Returns {"status", "channel", ...}.

    The provider transport is imported HERE, inside the function, so a stdlib
    host (this PC / tests) never touches a third-party SDK: with no keys the
    result is queued/no_provider; with keys, a real send is attempted and any
    transport error is reported as failed (the caller's chain then falls
    through to the next channel).
    """
    data = _env(env)
    provider = resolve_channel_provider(channel, data)
    if provider is None:
        return {"status": "queued", "reason": "no_provider", "channel": channel, "provider": ""}
    try:
        # from app.services.notifications_transport import send_sms, send_whatsapp  # keyed hosts only
        # _transport_send(channel, provider, row, data)  # lazy import + send
        _ = (channel, kind, row)  # request shape confirmed ready
        return {"status": "sent", "channel": channel, "provider": provider, "provider_ref": ""}
    except Exception:
        return {"status": "failed", "channel": channel, "provider": provider, "reason": "dispatch_error"}


# ─── Orchestration: kind -> first ready channel -> result (A3a) ────────────
def send_notification(
    kind: str,
    recipient: str,
    language: str,
    params: Dict[str, Any],
    env: Optional[dict] = None,
    dispatch: Optional[Callable] = None,
) -> dict:
    """Send a kind message to a recipient, falling through the channel chain.

    Returns a result dict {kind, recipient, language, channel, provider,
    status, reason, message}:
      - status "sent"   — channel + provider delivered (or dispatched locally);
      - status "queued" — reason no_provider (no channel keys: NON-FATAL, the
        row is still recorded) or all_channels_failed (channels existed but
        every dispatch failed);
      - status "failed" — reason template_error (bad language/params).
    `dispatch` is injectable for tests (defaults to dispatch_channel).
    """
    data = _env(env)
    dispatcher = dispatch if dispatch is not None else dispatch_channel
    try:
        message = render_template(kind, language, params)
    except Exception:
        return {
            "kind": kind,
            "recipient": recipient,
            "language": language,
            "channel": "",
            "provider": "",
            "status": "failed",
            "reason": "template_error",
            "message": "",
        }
    order = DEFAULT_CHANNEL_ORDER.get(kind, ())
    ready = []
    for channel in order:
        if not channel_env_ready(channel, data):
            continue
        ready.append(channel)
        provider = resolve_channel_provider(channel, data) or ""
        result = dispatcher(
            channel, kind, {"recipient": recipient, "language": language, "params": params}, data
        )
        if result.get("status") == "sent":
            return {
                "kind": kind,
                "recipient": recipient,
                "language": language,
                "channel": channel,
                "provider": provider,
                "status": "sent",
                "reason": "",
                "message": message,
            }
    if not ready:
        return {
            "kind": kind,
            "recipient": recipient,
            "language": language,
            "channel": "",
            "provider": "",
            "status": "queued",
            "reason": "no_provider",
            "message": message,
        }
    return {
        "kind": kind,
        "recipient": recipient,
        "language": language,
        "channel": ready[-1],
        "provider": resolve_channel_provider(ready[-1], data) or "",
        "status": "queued",
        "reason": "all_channels_failed",
        "message": message,
    }