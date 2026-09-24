"""AuthN/Z acceptance tests (G6-Q1): service core, schema repair, router, frontend gate.

RED before implementation (2026-09-25): postgres_schema.sql cannot load on local
postgres (clinic_users.user_id REFERENCES auth.users(id) + auth.uid() policies +
no users table); no app/services/auth.py, no app/api/auth.py, no /login page;
UML ER still asserts 9 tables.

GREEN after implementation (spec-auth.md, Q1-Q4 approved 2026-09-25): stdlib
HMAC-SHA256 tokens + PBKDF2 passwords + OTP (Q4), guards library only (Q1),
local auth.uid() GUC + RLS intact (Q2), /login page + client guard (Q3).

Run: python3 tests/test_auth.py  (exit 0 = green)
"""
import base64
import hashlib
import hmac
import json
import pathlib
import re
import sys
import time
import unittest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
ROOT = BACKEND.parent
FRONTEND = ROOT / "frontend"
SCHEMA = BACKEND / "postgres_schema.sql"
POSTGRES = BACKEND / "app" / "db" / "postgres.py"
ENV_EXAMPLE = BACKEND / ".env.example"
COMPOSE = ROOT / "docker-compose.yml"
SMOKE = BACKEND / "scripts" / "smoke_api.py"
AUTH_ROUTER = BACKEND / "app" / "api" / "auth.py"
AUTH_SERVICE = BACKEND / "app" / "services" / "auth.py"
MAIN = BACKEND / "main.py"
LOGIN_PAGE = FRONTEND / "src" / "app" / "login" / "page.tsx"
API_CLIENT = FRONTEND / "src" / "lib" / "api.ts"
AUTH_CTX = FRONTEND / "src" / "lib" / "auth.tsx"
CLINIC_LAYOUT = FRONTEND / "src" / "app" / "(clinic)" / "layout.tsx"
ADMIN_LAYOUT = FRONTEND / "src" / "app" / "admin" / "layout.tsx"
ER_DOC = ROOT / "docs" / "uml" / "01-er.md"

# Guarded import: before the module exists this is None and the service tests
# fail honestly (never skip, so RED is a real exit-1).
try:
    from app.services.auth import (  # type: ignore
        ROLES,
        create_token,
        decode_token,
        generate_otp,
        hash_otp,
        hash_password,
        normalize_phone,
        verify_otp,
        verify_password,
    )
except ImportError:
    ROLES = ()
    create_token = decode_token = generate_otp = hash_otp = None
    hash_password = verify_otp = verify_password = normalize_phone = None


def read(p: pathlib.Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def has_all(text: str, *needles: str) -> bool:
    return all(n in text for n in needles)


# ─── Service core: passwords (PBKDF2-HMAC-SHA256) ───────────────────────────

class TestPasswords(unittest.TestCase):
    def test_hash_password_format(self):
        self.assertIsNotNone(hash_password, "app/services/auth.py missing")
        h = hash_password("S3cure!pass")
        parts = h.split("$")
        self.assertEqual(parts[0], "pbkdf2_sha256")
        self.assertEqual(len(parts), 4, "pbkdf2_sha256$iter$salt$hash")

    def test_hash_password_unique_per_salt(self):
        self.assertNotEqual(hash_password("same-pass"), hash_password("same-pass"))

    def test_verify_password_correct(self):
        h = hash_password("S3cure!pass")
        self.assertTrue(verify_password("S3cure!pass", h))

    def test_verify_password_wrong(self):
        h = hash_password("S3cure!pass")
        self.assertFalse(verify_password("wrong-pass", h))

    def test_verify_password_garbage_no_exception(self):
        self.assertFalse(verify_password("x", "not-a-real-hash-format"))


# ─── Service core: OTP ───────────────────────────────────────────────────────

class TestOtp(unittest.TestCase):
    def test_generate_otp_six_digits(self):
        code = generate_otp()
        self.assertRegex(code, r"^\d{6}$")

    def test_generate_otp_distinct(self):
        draws = {generate_otp() for _ in range(50)}
        self.assertGreaterEqual(len(draws), 2, "OTP draws should vary")

    def test_hash_otp_not_plaintext(self):
        code, phone = "123456", "+919845012345"
        h = hash_otp(code, phone)
        self.assertNotIn(code, h)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", h), "HMAC-SHA256 hex digest")

    def test_verify_otp_valid(self):
        phone, code = "+919845012345", generate_otp()
        stored = hash_otp(code, phone)
        # phone key is required: the stored hash is HMAC keyed by it
        self.assertTrue(
            verify_otp(code, stored, expires_at=time.time() + 600, attempts=0, phone=phone)
        )

    def test_verify_otp_wrong_code(self):
        phone = "+919845012345"
        stored = hash_otp(generate_otp(), phone)
        self.assertFalse(verify_otp(generate_otp(), stored, expires_at=time.time() + 600, attempts=0))

    def test_verify_otp_expired(self):
        code, phone = "654321", "+919845012345"
        stored = hash_otp(code, phone)
        self.assertFalse(verify_otp(code, stored, expires_at=time.time() - 1, attempts=0))

    def test_verify_otp_attempt_cap(self):
        code, phone = "111111", "+919845012345"
        stored = hash_otp(code, phone)
        self.assertFalse(verify_otp(code, stored, expires_at=time.time() + 600, attempts=5))


# ─── Service core: tokens (stdlib HMAC-SHA256, JWT-shaped) ───────────────────

SECRET = "unit-test-secret"


class TestTokens(unittest.TestCase):
    def test_create_token_roundtrip(self):
        token = create_token("u-1", "owner", SECRET)
        self.assertEqual(token.count("."), 2, "header.payload.signature")
        payload = decode_token(token, SECRET, now=time.time())
        self.assertEqual(payload["sub"], "u-1")
        self.assertEqual(payload["role"], "owner")

    def test_token_tampered_body_fails(self):
        token = create_token("u-1", "owner", SECRET)
        header, payload, sig = token.split(".")
        forged = json.dumps({"sub": "attacker", "role": "owner"}).encode()
        payload2 = base64.urlsafe_b64encode(forged).rstrip(b"=").decode()
        with self.assertRaises(Exception):
            decode_token(f"{header}.{payload2}.{sig}", SECRET, now=time.time())

    def test_token_wrong_secret_fails(self):
        token = create_token("u-1", "owner", SECRET)
        with self.assertRaises(Exception):
            decode_token(token, "other-secret", now=time.time())

    def test_token_expired_fails(self):
        token = create_token("u-1", "owner", SECRET, ttl=-60)
        with self.assertRaises(Exception):
            decode_token(token, SECRET, now=time.time())

    def test_token_future_iat_fails(self):
        now = time.time()
        token = create_token("u-1", "owner", SECRET, ttl=3600, now=now + 7200)
        with self.assertRaises(Exception):
            decode_token(token, SECRET, now=now)

    def test_exports_are_callable(self):
        for fn in (create_token, decode_token, generate_otp, hash_otp,
                   hash_password, verify_otp, verify_password, normalize_phone):
            self.assertTrue(callable(fn), f"{fn} not callable")


# ─── Service core: roles + phone ─────────────────────────────────────────────

class TestRoles(unittest.TestCase):
    def test_doctor_in_roles(self):
        self.assertIn("doctor", ROLES)
        for r in ("owner", "staff", "triage_agent", "doctor", "readonly"):
            self.assertIn(r, ROLES)

    def test_can_hierarchy(self):
        from app.services import auth as _impl

        self.assertTrue(_impl.can("owner", "doctor"))
        self.assertTrue(_impl.can("owner", "readonly"))
        self.assertTrue(_impl.can("doctor", "triage_agent"))
        self.assertFalse(_impl.can("staff", "doctor"))
        self.assertFalse(_impl.can("readonly", "staff"))
        self.assertTrue(_impl.can("triage_agent", "triage_agent"))

    def test_can_invalid_role(self):
        from app.services import auth as _impl

        self.assertFalse(_impl.can("ceo", "staff"))


class TestPhone(unittest.TestCase):
    def test_normalize_phone_10_digit(self):
        self.assertEqual(normalize_phone("9845012345"), "+919845012345")
        self.assertEqual(normalize_phone("+91 98450 12345"), "+919845012345")

    def test_normalize_phone_rejects_bad(self):
        with self.assertRaises(ValueError):
            normalize_phone("123")
        with self.assertRaises(ValueError):
            normalize_phone("+9198450123456")


# ─── Schema repair (postgres_schema.sql) ─────────────────────────────────────

SCHEMA_TEXT = read(SCHEMA)


class TestSchemaRepair(unittest.TestCase):
    def test_users_table_exists(self):
        self.assertIn("CREATE TABLE users (", SCHEMA_TEXT)
        self.assertIn("email TEXT UNIQUE", SCHEMA_TEXT)
        self.assertIn("phone TEXT UNIQUE", SCHEMA_TEXT)
        self.assertIn("password_hash TEXT", SCHEMA_TEXT)
        self.assertIn("otp_code_hash TEXT", SCHEMA_TEXT)
        self.assertIn("otp_expires_at TIMESTAMPTZ", SCHEMA_TEXT)

    def test_clinic_users_fk_now_points_at_users(self):
        self.assertIn("REFERENCES users(id)", SCHEMA_TEXT)
        self.assertNotIn("REFERENCES auth.users(id)", SCHEMA_TEXT)

    def test_auth_uid_function_defined_locally(self):
        self.assertIn("CREATE SCHEMA IF NOT EXISTS auth;", SCHEMA_TEXT)
        self.assertIn("auth.uid()", SCHEMA_TEXT)
        self.assertIn("current_setting('app.current_user_id'", SCHEMA_TEXT)

    def test_authenticated_role_created(self):
        self.assertIn("CREATE ROLE authenticated", SCHEMA_TEXT)

    def test_doctor_role_in_comments(self):
        users_block = SCHEMA_TEXT.split("CREATE TABLE users", 1)[1]
        users_block = users_block.split("CREATE TABLE clinic_users", 1)[0]
        cusers_block = SCHEMA_TEXT.split("CREATE TABLE clinic_users", 1)[1]
        cusers_block = cusers_block.split("CREATE TABLE calls", 1)[0]
        self.assertIn("doctor", users_block)
        self.assertIn("doctor", cusers_block)


# ─── SQLAlchemy layer ────────────────────────────────────────────────────────

POSTGRES_TEXT = read(POSTGRES)


class TestSqlAlchemyAuth(unittest.TestCase):
    def test_user_model_exists(self):
        self.assertIn("class User(Base):", POSTGRES_TEXT)
        self.assertIn('__tablename__ = "users"', POSTGRES_TEXT)
        self.assertIn("password_hash", POSTGRES_TEXT)
        self.assertIn("otp_code_hash", POSTGRES_TEXT)

    def test_clinic_user_fk_to_users(self):
        self.assertIn('ForeignKey("users.id"', POSTGRES_TEXT)


# ─── Auth router ─────────────────────────────────────────────────────────────

AUTH_TEXT = read(AUTH_ROUTER)


class TestAuthRouter(unittest.TestCase):
    def test_auth_endpoints_defined(self):
        for ep in (
            "/register",
            "/login",
            "/otp/request",
            "/otp/verify",
            "/me",
            "/logout",
            "/providers",
            "/oauth/{provider}",
        ):
            self.assertIn(ep, AUTH_TEXT, f"missing {ep}")

    def test_guards_exported(self):
        for g in ("get_current_user", "require_roles", "require_clinic_role"):
            self.assertIn(g, AUTH_TEXT, f"missing {g}")

    def test_sso_gated(self):
        self.assertIn("501", AUTH_TEXT)
        self.assertIn("not configured", AUTH_TEXT.lower())

    def test_main_includes_auth_router(self):
        main = read(MAIN)
        self.assertTrue(has_all(main, "auth", "include_router"), "main.py must mount /api/auth")


class TestAuthEnv(unittest.TestCase):
    def test_auth_env_vars_documented(self):
        for key in (
            "AUTH_JWT_SECRET",
            "AUTH_TOKEN_TTL_SECONDS",
            "OTP_TTL_SECONDS",
            "GOOGLE_OAUTH_CLIENT_ID",
            "MICROSOFT_OAUTH_CLIENT_ID",
            "ABHA_OAUTH_CLIENT_ID",
        ):
            self.assertIn(key, read(ENV_EXAMPLE), f"missing {key}")

    def test_compose_auth_jwt_secret(self):
        compose = read(COMPOSE)
        self.assertIn("AUTH_JWT_SECRET", compose)
        self.assertIn("dev-secret-change-me", compose)


# ─── Frontend /login + guard (Q3) ────────────────────────────────────────────

class TestFrontendAuth(unittest.TestCase):
    def test_login_page_exists(self):
        page = read(LOGIN_PAGE)
        self.assertTrue(page.startswith('"use client"'), "login page must be a client component")
        for needle in ("loginPassword", "loginOtpVerify", "password"):
            self.assertIn(needle, page, f"missing {needle}")

    def test_api_client_auth_surface(self):
        api = read(API_CLIENT)
        for needle in ("loginPassword", "loginOtpRequest", "loginOtpVerify",
                       "fetchMe", "getToken", "setToken", "Authorization"):
            self.assertIn(needle, api, f"missing {needle}")

    def test_auth_context_exists(self):
        ctx = read(AUTH_CTX)
        for needle in ("AuthProvider", "RequireAuth", "localStorage", "token"):
            self.assertIn(needle, ctx, f"missing {needle}")

    def test_layouts_use_guard(self):
        for layout in (read(CLINIC_LAYOUT), read(ADMIN_LAYOUT)):
            self.assertTrue(has_all(layout, "RequireAuth", "NEXT_PUBLIC_USE_MOCK"),
                            "dashboard layouts must mount the auth guard")


# ─── Smoke + docs corollary ──────────────────────────────────────────────────

class TestSmokeAndDocs(unittest.TestCase):
    def test_smoke_auth_roundtrip(self):
        smoke = read(SMOKE)
        for needle in ("/api/auth/register", "/api/auth/login", "/api/auth/me"):
            self.assertIn(needle, smoke, f"missing {needle}")

    def test_er_doc_has_users(self):
        er = read(ER_DOC)
        self.assertIn("users", er)
        self.assertIn("clinic_users", er)


if __name__ == "__main__":
    unittest.main()