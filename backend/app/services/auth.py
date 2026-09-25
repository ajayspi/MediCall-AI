"""MediCall AI — auth core (stdlib only).

Zero-dependency cryptography for Phase-1 auth (spec-auth.md, G6-Q1):

- Passwords: PBKDF2-HMAC-SHA256 (per-user 16-byte salt, 210k iterations),
  constant-time compare via hmac.compare_digest. Stored form:
  ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``.
- OTP: 6-digit codes from ``secrets``; hashed at rest (HMAC-SHA256 keyed by
  the phone) so a DB leak never yields usable codes; TTL + attempt cap.
- Tokens: JWT-shaped ``header.payload.signature`` signed with HMAC-SHA256 and
  base64url-encoded (claims: sub, role, iat, exp). Stateless, 12h default TTL.
  python-jose/passlib stay pinned in requirements.txt for the later
  SSO/OAuth2 resource-server flows; this module keeps Phase-1 verifiable on
  stdlib-only machines (CI-local parity with tests).
- Roles: owner > doctor > triage_agent > staff > readonly (clinic matrix).

Design constraint: no third-party imports — this module is unit-tested on
this PC (Python 3.14 stdlib) and imported by the FastAPI router in Docker.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Optional

# ─── Constants ───────────────────────────────────────────────────────────────

PBKDF2_ITERATIONS = 210_000
PBKDF2_ALGO = "sha256"
PREFIX = "pbkdf2_sha256"

OTP_TTL_SECONDS = 600          # 10 minutes
OTP_MAX_ATTEMPTS = 5
TOKEN_TTL_SECONDS = 43_200     # 12 hours (Phase-1 stateless JWT)
TOKEN_ALG = "HS256"

# Role matrix: platform_admin (platform operator, above the clinic scope) >
# owner > doctor > triage_agent > staff > readonly. platform_admin is the only
# role that may call the /api/admin router (G6-Q11); it is seeded out-of-band
# (demo tenant seed) — register() grants DEFAULT_ROLE only, so there is no
# self-serve path, same as owner.
ROLES = ("owner", "staff", "triage_agent", "doctor", "readonly", "platform_admin")
ROLE_WEIGHTS = {
    "readonly": 1,
    "staff": 2,
    "triage_agent": 3,
    "doctor": 4,
    "owner": 5,
    "platform_admin": 6,
}
DEFAULT_ROLE = "staff"

_PHONE_RE = re.compile(r"^(\+91)?([6-9]\d{9})$")


class AuthError(Exception):
    """Base class for auth failures."""


class InvalidTokenError(AuthError):
    """Token is malformed, tampered, or signed with the wrong key."""


class ExpiredTokenError(AuthError):
    """Token payload is outside its validity window."""


# ─── Passwords (PBKDF2-HMAC-SHA256) ─────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password with a fresh per-user salt.

    Returns ``pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>``. Never store the
    plaintext; never reuse a salt.
    """
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return "$".join(
        (
            PREFIX,
            str(PBKDF2_ITERATIONS),
            salt.hex(),
            digest.hex(),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time password check; False (never raise) on bad format."""
    try:
        prefix, iterations, salt_hex, hash_hex = stored.split("$")
        if prefix != PREFIX:
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGO, password.encode("utf-8"), salt, int(iterations)
    )
    return hmac.compare_digest(digest, expected)


# ─── OTP ────────────────────────────────────────────────────────────────────

def generate_otp() -> str:
    """6-digit OTP (zero-padded) from the CSPRNG."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str, phone: str) -> str:
    """HMAC-SHA256 of the code keyed by the phone — codes never stored raw."""
    return hmac.new(
        phone.encode("utf-8"), code.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_otp(
    code: str,
    stored_hash: str,
    expires_at: float,
    attempts: int,
    *,
    max_attempts: int = OTP_MAX_ATTEMPTS,
    phone: Optional[str] = None,
) -> bool:
    """Check an OTP against its store: expiry window, attempt cap, then
    constant-time match. ``phone`` is required when re-hashing to compare
    (the stored hash is keyed by it).
    """
    if attempts >= max_attempts:
        return False
    if time.time() > float(expires_at):
        return False
    if phone is not None:
        candidate = hash_otp(code, phone)
    else:
        candidate = code
    return hmac.compare_digest(candidate.encode("utf-8"), stored_hash.encode("utf-8"))


# ─── Tokens (JWT-shaped, HMAC-SHA256) ───────────────────────────────────────

def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_token(
    user_id: str,
    role: str,
    secret: str,
    ttl: Optional[int] = None,
    *,
    now: Optional[float] = None,
) -> str:
    """Issue a signed token. ``now`` injectable for tests (clock control)."""
    issued = int(now if now is not None else time.time())
    expires = issued + (ttl if ttl is not None else TOKEN_TTL_SECONDS)
    header = {"alg": TOKEN_ALG, "typ": "JWT"}
    payload = {"sub": user_id, "role": role, "iat": issued, "exp": expires}
    head_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    pay_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{head_b64}.{pay_b64}".encode("ascii")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{head_b64}.{pay_b64}.{_b64url_encode(sig)}"


def decode_token(
    token: str, secret: str, *, now: Optional[float] = None
) -> dict:
    """Verify signature + validity window; return the payload dict.

    Raises InvalidTokenError on malformed/tampered/wrong-key tokens and
    ExpiredTokenError when iat/exp are out of window (with 60s clock skew).
    """
    try:
        head_b64, pay_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(head_b64))
        payload = json.loads(_b64url_decode(pay_b64))
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{head_b64}.{pay_b64}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            raise InvalidTokenError("bad signature")
        if header.get("alg") != TOKEN_ALG:
            raise InvalidTokenError("bad algorithm")
    except (ValueError, json.JSONDecodeError, KeyError) as exc:
        raise InvalidTokenError("malformed token") from exc

    issued_at = int(payload.get("iat", 0))
    expires_at = int(payload.get("exp", 0))
    current = now if now is not None else time.time()
    if current < issued_at - 60:
        raise ExpiredTokenError("token not yet valid")
    if current > expires_at + 60:
        raise ExpiredTokenError("token expired")
    return payload


# ─── Roles ──────────────────────────────────────────────────────────────────

def can(role: str, required: str) -> bool:
    """True when ``role`` meets (or exceeds) ``required`` in the matrix."""
    return ROLE_WEIGHTS.get(role, 0) >= ROLE_WEIGHTS.get(required, 10**9)


# ─── Phone (India) ──────────────────────────────────────────────────────────

def normalize_phone(phone: str) -> str:
    """Canonical India phone: ``+91xxxxxxxxxx`` (10-digit, 6-9 leading).

    Tolerates formatting separators (spaces/hyphens, with or without +91).
    """
    cleaned = re.sub(r"[\s-]", "", phone.strip())
    match = _PHONE_RE.fullmatch(cleaned)
    if not match:
        raise ValueError(f"invalid Indian phone number: {phone!r}")
    return f"+91{match.group(2)}"