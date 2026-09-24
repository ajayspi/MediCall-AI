"""AuthN/Z router (G6-Q1, spec-auth.md) — register/login/OTP/me + SSO gates.

Phase-1 shape (Q1 sign-off 2026-09-25): ships the security dependencies as a
library — ``get_current_user``, ``require_roles``, ``require_clinic_role`` —
for the enforcement phase; the five domain routers stay unauthenticated.

SSO endpoints (google/microsoft/abha) are gated behind env-key presence
(501 until configured), same pattern as the payments router (G6-Q5) and the
voice /call-completed lazy wiring. Real provider calls need keys + a host.

Note: the guards are defined BEFORE the endpoints because FastAPI evaluates
``Depends(...)`` defaults at import time (no forward references allowed).
"""
from __future__ import annotations

import os
import uuid
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import (
    bump_user_otp_attempts,
    clear_user_otp,
    create_user,
    find_user,
    get_db_session,
    get_user,
    list_clinic_memberships,
    now_tz,
    service_request_ctx,
    set_current_user_id,
    set_user_otp,
)
from app.services import auth as authsvc

router = APIRouter()

# SSO provider -> env key that gates the endpoint (501 when absent)
SSO_ENV_KEYS = {
    "google": "GOOGLE_OAUTH_CLIENT_ID",
    "microsoft": "MICROSOFT_OAUTH_CLIENT_ID",
    "abha": "ABHA_OAUTH_CLIENT_ID",
}


def _secret() -> str:
    return os.getenv("AUTH_JWT_SECRET", "dev-secret-change-me")


def _user_out(user) -> dict:
    return {
        "id": str(user.id),
        "name": user.name,
        "phone": user.phone,
        "email": user.email,
        "role": user.role,
    }


def _token_response(user) -> dict:
    token = authsvc.create_token(str(user.id), user.role, _secret())
    return {"access_token": token, "token_type": "bearer", "user": _user_out(user)}


# ─── Security dependencies (guards library — enforcement phase uses these) ──

async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db_session)
):
    """Bearer-token auth dependency: returns the active User or 401.

    Sets the per-request RLS GUC (app.current_user_id) from the token sub
    BEFORE the user lookup, so the users_own_data policy sees auth.uid() and
    admits the current request's own row under FORCE RLS + medicall_app.
    """
    authz = request.headers.get("Authorization", "")
    if not authz.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authz.split(" ", 1)[1].strip()
    try:
        payload = authsvc.decode_token(token, _secret())
    except authsvc.ExpiredTokenError as exc:
        raise HTTPException(401, "token expired") from exc
    except authsvc.InvalidTokenError as exc:
        raise HTTPException(401, "invalid token") from exc
    uid = str(uuid.UUID(payload["sub"]))
    set_current_user_id(uid)
    user = await get_user(uuid.UUID(uid))
    if user is None or not user.is_active:
        raise HTTPException(401, "unknown or inactive user")
    return user


def require_roles(*roles: str):
    """Dependency factory: any listed role grants access (403 otherwise)."""
    def _dep(user=Depends(get_current_user)):
        if not any(authsvc.can(user.role, r) for r in roles):
            raise HTTPException(403, "insufficient role")
        return user
    return _dep


def require_clinic_role(clinic_id: str, *roles: str):
    """Dependency factory: user must hold one of ``roles`` in the clinic."""
    async def _dep(
        user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db_session),
    ):
        members = await list_clinic_memberships(user.id)
        allowed = any(
            str(m.clinic_id) == clinic_id and authsvc.can(m.role, r)
            for m in members
            for r in roles
        )
        if not allowed:
            raise HTTPException(403, "no clinic role")
        return user
    return _dep


# ─── Request/response models ────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1)
    phone: Optional[str] = None
    email: Optional[str] = None
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    username: str
    password: str


class OtpRequest(BaseModel):
    phone: str


class OtpVerifyRequest(BaseModel):
    phone: str
    code: str = Field(min_length=6, max_length=6)


# ─── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    """Create a user (India: phone primary; email optional). 409 on dup."""
    if not body.phone and not body.email:
        raise HTTPException(422, "phone or email required")
    phone = None
    if body.phone:
        try:
            phone = authsvc.normalize_phone(body.phone)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if await find_user(phone) is not None:
            raise HTTPException(409, "phone already registered")
    email = (body.email or "").strip().lower() or None
    if email and await find_user(email) is not None:
        raise HTTPException(409, "email already registered")
    user = await create_user(
        name=body.name,
        password_hash=authsvc.hash_password(body.password),
        phone=phone,
        email=email,
    )
    return _user_out(user)


@router.post("/login")
async def login(body: LoginRequest):
    """Password login by phone (+91…) or email. 401 on bad credentials."""
    try:
        username = authsvc.normalize_phone(body.username)
    except ValueError:
        username = body.username.strip().lower()
    user = await find_user(username)
    if user is None or not user.is_active:
        raise HTTPException(401, "invalid credentials")
    if not user.password_hash or not authsvc.verify_password(
        body.password, user.password_hash
    ):
        raise HTTPException(401, "invalid credentials")
    return _token_response(user)


@router.post("/otp/request")
async def otp_request(body: OtpRequest):
    """Issue a hashed OTP (10-min TTL, 5 attempts). SMS provider gated —
    dev mode logs the code; real delivery lands with a messaging provider."""
    try:
        phone = authsvc.normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    user = await find_user(phone)
    if user is None:
        raise HTTPException(404, "unknown phone")
    if (user.otp_attempts or 0) >= authsvc.OTP_MAX_ATTEMPTS:
        raise HTTPException(429, "too many attempts")
    code = authsvc.generate_otp()
    stored = authsvc.hash_otp(code, phone)
    await set_user_otp(user.id, stored, now_tz() + timedelta(seconds=authsvc.OTP_TTL_SECONDS))
    if os.getenv("LOG_LEVEL", "info").lower() == "debug":
        print(f"[dev-otp] phone={phone} code={code} ttl={authsvc.OTP_TTL_SECONDS}s", flush=True)
    return {"status": "otp_sent", "expires_in": authsvc.OTP_TTL_SECONDS}


@router.post("/otp/verify")
async def otp_verify(body: OtpVerifyRequest):
    """Verify an OTP; success clears OTP state and issues a token."""
    try:
        phone = authsvc.normalize_phone(body.phone)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    user = await find_user(phone)
    if user is None:
        raise HTTPException(404, "unknown phone")
    if not user.otp_code_hash or user.otp_expires_at is None:
        raise HTTPException(401, "no active OTP")
    ok = authsvc.verify_otp(
        body.code,
        user.otp_code_hash,
        user.otp_expires_at.timestamp(),
        user.otp_attempts or 0,
        phone=phone,
    )
    if not ok:
        await bump_user_otp_attempts(user.id)
        raise HTTPException(401, "invalid or expired code")
    await clear_user_otp(user.id)
    return _token_response(user)


@router.get("/me")
async def me(db: AsyncSession = Depends(get_db_session), user=Depends(get_current_user)):
    """Current user + clinic memberships (Bearer)."""
    memberships = [
        {"clinic_id": str(m.clinic_id), "role": m.role}
        for m in await list_clinic_memberships(user.id)
    ]
    return {**_user_out(user), "memberships": memberships}


@router.post("/logout")
async def logout():
    """Stateless JWT — the client discards the token; nothing to revoke."""
    return {"status": "ok"}


@router.get("/providers")
async def providers():
    """Which auth methods are enabled (SSO gated by env-key presence)."""
    return {
        "password": True,
        "otp": True,
        "google": bool(os.getenv(SSO_ENV_KEYS["google"])),
        "microsoft": bool(os.getenv(SSO_ENV_KEYS["microsoft"])),
        "abha": bool(os.getenv(SSO_ENV_KEYS["abha"])),
    }


@router.post("/oauth/{provider}")
async def oauth_start(provider: str):
    """SSO scaffold: 501 until the provider's env keys are present."""
    if provider not in SSO_ENV_KEYS:
        raise HTTPException(404, "unknown provider")
    if not os.getenv(SSO_ENV_KEYS[provider]):
        raise HTTPException(501, "not configured")
    raise HTTPException(501, "SSO flow not implemented yet")