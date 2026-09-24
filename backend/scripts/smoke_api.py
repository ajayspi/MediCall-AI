"""MediCall AI — HTTP smoke test of the API contracts (docs/uml/03-api-contracts.md).

Stdlib-only (urllib) so it runs anywhere without pip: this PC, a CI Ubuntu
runner, or the compose host. It drives the executable endpoint contract:

    GET  /health                                    -> 200 healthy
    POST /api/auth/login (demo owner +919876543210)-> 200 access_token
    GET  /api/clinics (no auth)                     -> 401 (enforcement)
    POST /api/clinics (no auth)                     -> 401 (enforcement)
    POST /api/clinics (owner Bearer)                -> 201 create (returns id)
    GET  /api/clinics                               -> 200 list (created clinic present)
    GET  /api/clinics/{clinic_id}                   -> 200 detail
    PATCH /api/clinics/{clinic_id}                  -> 200 update
    GET  /api/clinics/{random_uuid}                 -> 404 missing row
    GET  /api/calls?clinic_id=...                   -> 200 list (empty until the voice pipeline runs)
    GET  /api/calls/{call_id}                       -> 404 missing row
    PATCH /api/calls/{call_id}/state                -> 422 invalid state value
    PATCH /api/calls/{call_id}/state                -> 404 missing row; 409 invalid transition when a call exists
    GET  /api/calls/{call_id}/transcript            -> 404 missing row
    POST /api/appointments                          -> 201 create (returns id)
    GET  /api/appointments/{appointment_id}         -> 200 detail
    GET  /api/appointments/{random_uuid}            -> 404 missing row
    PATCH /api/appointments/{appointment_id}/status -> 422 invalid status; 200 valid status
    POST /api/prescriptions                         -> 201 create (returns id)
    PATCH /api/prescriptions/{prescription_id}/status -> 422 invalid status; 200 valid status
    POST /api/payments                              -> 201 create (intent only, G6-Q5 gated)
    PATCH /api/payments/{payment_id}/status         -> 422 invalid status
    POST /api/voice/call-completed (X-Service-Token)-> 200 accepted (transcript persistence hook, D1)
    POST /api/auth/register (unique phone)          -> 201 create
    POST /api/auth/register (dup phone)             -> 409 duplicate
    POST /api/auth/login                            -> 200 access_token; 401 bad creds
    POST /api/clinics (staff Bearer)                -> 403 (role enforcement)
    GET  /api/auth/me (Bearer)                      -> 200 current user
    POST /api/auth/otp/request                      -> 200 otp_sent
    GET  /api/auth/providers                        -> 200 method flags

Auth-first flow (spec-auth-enforcement.md): every domain call carries a Bearer
token from the seeded demo owner (+919876543210 / DemoPass!2026) — the ONLY
bootstrap owner in the RLS world. 401/403 negative checks prove the guards and
RLS enforcement are live.

Usage:
    python3 smoke_api.py                       # BASE_URL defaults to http://localhost:8001
    BASE_URL=http://localhost:8001 python3 smoke_api.py
    python3 smoke_api.py http://localhost:8001

Exit code: 0 = all checks passed; 1 = at least one check failed.
"""
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE_URL = os.environ.get("BASE_URL") or (
    sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001"
)
TIMEOUT = 10
FAILURES: list = []

# Seeded demo tenant (postgres_schema.sql, spec-auth-enforcement.md Q3/A3a).
DEMO_PHONE = os.environ.get("DEMO_PHONE", "+919876543210")
DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "DemoPass!2026")
SERVICE_TOKEN = os.environ.get("WEBHOOK_SERVICE_TOKEN", "dev-service-token")

# Endpoint surface under test (03-api-contracts + app/api routers).
ENDPOINTS = (
    "/health",
    "/api/clinics",
    "/api/clinics/{clinic_id}",
    "/api/calls",
    "/api/calls/{call_id}",
    "/api/calls/{call_id}/state",
    "/api/calls/{call_id}/transcript",
    "/api/appointments",
    "/api/appointments/{appointment_id}",
    "/api/appointments/{appointment_id}/status",
    "/api/prescriptions",
    "/api/prescriptions/{prescription_id}/status",
    "/api/payments",
    "/api/payments/{payment_id}/status",
    "/api/voice/call-completed",
)


def request(method: str, path: str, body=None, headers=None):
    """Return (status, decoded-json-or-None). Network errors -> (-1, {})."""
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers=hdrs,
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return resp.status, None
    except urllib.error.HTTPError as err:
        return err.code, None
    except OSError as err:
        return -1, {"error": str(err)}


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("PASS" if ok else "FAIL"), "-", label, detail)
    if not ok:
        FAILURES.append(label)


def bearer(token: str) -> dict:
    """Authorization header dict for an access token."""
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    print(f"MediCall AI smoke test -> {BASE_URL}")
    print("=" * 60)

    # --- health --------------------------------------------------------------
    s, j = request("GET", "/health")
    check("GET /health", s == 200 and j and j.get("status") == "ok", f"(got {s})")

    # --- login as the seeded demo owner FIRST (auth-first flow) --------------
    s, tok = request("POST", "/api/auth/login", {"username": DEMO_PHONE, "password": DEMO_PASSWORD})
    check("POST /api/auth/login (demo owner) -> 200", s == 200 and tok and tok.get("access_token"), f"(got {s})")
    demo_token = (tok or {}).get("access_token", "")
    auth = bearer(demo_token) if demo_token else {}

    # --- enforcement: unauthenticated domain calls MUST 401 ------------------
    s, _ = request("GET", "/api/clinics")
    check("GET /api/clinics (no auth) -> 401", s == 401, f"(got {s})")

    clinic_payload = {
        "name": "Smoke Test Clinic",
        "phone_number": "+91 90000 00000",
        "city": "Bengaluru",
        "state": "Karnataka",
        "address": "1 MG Road",
        "pincode": "560001",
        "plan": "starter",
        "is_active": True,
    }
    s, _ = request("POST", "/api/clinics", clinic_payload)
    check("POST /api/clinics (no auth) -> 401", s == 401, f"(got {s})")

    # --- clinics: create/list/detail/patch + 404 missing row -----------------
    s, clinic = request("POST", "/api/clinics", clinic_payload, headers=auth)
    check("POST /api/clinics (owner) -> 201", s == 201 and clinic and clinic.get("id"), f"(got {s})")
    clinic_id = (clinic or {}).get("id", "")

    s, rows = request("GET", "/api/clinics", headers=auth)
    present = isinstance(rows, list) and any(r.get("id") == clinic_id for r in rows)
    check("GET /api/clinics -> 200 + created present", s == 200 and present, f"(got {s})")

    s, j = request("GET", f"/api/clinics/{clinic_id}", headers=auth)
    check("GET /api/clinics/{id} -> 200 detail", s == 200 and j and j.get("id") == clinic_id, f"(got {s})")

    s, j = request("PATCH", f"/api/clinics/{clinic_id}", {"name": "Smoke Clinic Updated"}, headers=auth)
    check("PATCH /api/clinics/{id} -> 200 update", s == 200 and j and j.get("name") == "Smoke Clinic Updated", f"(got {s})")

    s, _ = request("GET", f"/api/clinics/{uuid.uuid4()}", headers=auth)
    check("GET /api/clinics/{id} -> 404 missing row", s == 404, f"(got {s})")

    # --- calls: clinic-scoped list, 404s, 422/409 state guards ---------------
    s, rows = request("GET", f"/api/calls?clinic_id={clinic_id}", headers=auth)
    check("GET /api/calls?clinic_id= -> 200 list", s == 200 and isinstance(rows, list), f"(got {s})")

    s, _ = request("GET", f"/api/calls/{uuid.uuid4()}", headers=auth)
    check("GET /api/calls/{id} -> 404 missing row", s == 404, f"(got {s})")

    s, _ = request("PATCH", f"/api/calls/{uuid.uuid4()}/state", {"state": "not-a-state"}, headers=auth)
    check("PATCH call state invalid value -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/calls/{uuid.uuid4()}/state", {"state": "TRIAGE"}, headers=auth)
    check("PATCH call state missing row -> 404", s == 404, f"(got {s})")

    if rows:
        s, _ = request("PATCH", f"/api/calls/{rows[0]['id']}/state", {"state": rows[0]["state"]}, headers=auth)
        check("PATCH call state no-op -> 409 invalid transition", s == 409, f"(got {s})")
    else:
        print("SKIP - no call rows yet (the voice pipeline creates them); "
              "409 invalid transition is not exercisable without a live call")

    s, _ = request("GET", f"/api/calls/{uuid.uuid4()}/transcript", headers=auth)
    check("GET /api/calls/{id}/transcript -> 404 missing row", s == 404, f"(got {s})")

    # --- appointments: create/detail/404 + invalid status 422 -----------------
    appt_payload = {
        "clinic_id": clinic_id,
        "patient_name": "Smoke Patient",
        "patient_phone": "+91 90000 00001",
        "patient_language": "en",
        "scheduled_at": "2026-09-26T10:30:00+05:30",
        "reason": "smoke test",
        "duration_minutes": 30,
    }
    s, appt = request("POST", "/api/appointments", appt_payload, headers=auth)
    check("POST /api/appointments -> 201", s == 201 and appt and appt.get("id"), f"(got {s})")
    appt_id = (appt or {}).get("id", "")

    s, j = request("GET", f"/api/appointments/{appt_id}", headers=auth)
    check("GET /api/appointments/{id} -> 200 detail", s == 200 and j and j.get("id") == appt_id, f"(got {s})")

    s, _ = request("GET", f"/api/appointments/{uuid.uuid4()}", headers=auth)
    check("GET /api/appointments/{id} -> 404 missing row", s == 404, f"(got {s})")

    s, _ = request("PATCH", f"/api/appointments/{appt_id}/status", {"status": "bogus"}, headers=auth)
    check("PATCH appointment status invalid -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/appointments/{appt_id}/status", {"status": "confirmed"}, headers=auth)
    check("PATCH appointment status valid -> 200", s == 200, f"(got {s})")

    # --- prescriptions: create + invalid status 422 ---------------------------
    rx_payload = {
        "clinic_id": clinic_id,
        "patient_name": "Smoke Patient",
        "patient_phone": "+91 90000 00001",
        "medication": "Paracetamol 500mg",
        "dosage": "1 tablet",
        "frequency": "twice daily",
    }
    s, rx = request("POST", "/api/prescriptions", rx_payload, headers=auth)
    check("POST /api/prescriptions -> 201", s == 201 and rx and rx.get("id"), f"(got {s})")
    rx_id = (rx or {}).get("id", "")

    s, _ = request("PATCH", f"/api/prescriptions/{rx_id}/status", {"status": "bogus"}, headers=auth)
    check("PATCH prescription status invalid -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/prescriptions/{rx_id}/status", {"status": "approved"}, headers=auth)
    check("PATCH prescription status valid -> 200", s == 200, f"(got {s})")

    # --- payments: intent-only create (G6-Q5 gated) + invalid status 422 ------
    pay_payload = {
        "clinic_id": clinic_id,
        "call_id": "",
        "appointment_id": appt_id,
        "amount": 500.0,
        "currency": "INR",
        "gateway": "manual",
        "gateway_ref": "",
    }
    s, pay = request("POST", "/api/payments", pay_payload, headers=auth)
    check("POST /api/payments -> 201 (intent only)", s == 201 and pay and pay.get("id"), f"(got {s})")
    pay_id = (pay or {}).get("id", "")

    s, _ = request("PATCH", f"/api/payments/{pay_id}/status", {"status": "bogus"}, headers=auth)
    check("PATCH payment status invalid -> 422", s == 422, f"(got {s})")

    # --- voice: call-completed needs the service token (enforcement) ---------
    s, j = request(
        "POST",
        "/api/voice/call-completed",
        {
            "call_id": str(uuid.uuid4()),
            "transcript": [{"role": "agent", "text": "Namaste, how can I help you today?"}],
            "ended_at": "2026-09-26T10:35:00+05:30",
            "duration_seconds": 300,
            "state": "COMPLETE",
        },
    )
    check("POST /api/voice/call-completed (no token) -> 401", s == 401, f"(got {s})")

    s, j = request(
        "POST",
        "/api/voice/call-completed",
        {
            "call_id": str(uuid.uuid4()),
            "transcript": [{"role": "agent", "text": "Namaste, how can I help you today?"}],
            "ended_at": "2026-09-26T10:35:00+05:30",
            "duration_seconds": 300,
            "state": "COMPLETE",
        },
        headers={"X-Service-Token": SERVICE_TOKEN},
    )
    check("POST /api/voice/call-completed (service token) -> 200", s == 200 and j, f"(got {s})")

    # --- auth: register -> login -> role enforcement + bearer me + OTP --------
    auth_phone = "+91" + "98" + str(uuid.uuid4().int)[-8:]  # 10-digit, 9-led
    register_payload = {
        "name": "Smoke User",
        "phone": auth_phone,
        "email": f"smoke{uuid.uuid4().hex[:8]}@example.in",
        "password": "S3cure!pass",
    }
    s, u = request("POST", "/api/auth/register", register_payload)
    check("POST /api/auth/register -> 201", s == 201 and u and u.get("id"), f"(got {s})")

    s, _ = request("POST", "/api/auth/register", register_payload)
    check("POST /api/auth/register dup phone -> 409", s == 409, f"(got {s})")

    s, tok = request("POST", "/api/auth/login", {"username": auth_phone, "password": "S3cure!pass"})
    check("POST /api/auth/login -> 200 + bearer token", s == 200 and tok and tok.get("access_token"), f"(got {s})")
    staff_token = (tok or {}).get("access_token", "")

    s, _ = request("POST", "/api/auth/login", {"username": auth_phone, "password": "wrong-pass"})
    check("POST /api/auth/login bad creds -> 401", s == 401, f"(got {s})")

    # A fresh registered user is staff with no memberships — clinic create 403.
    s, _ = request("POST", "/api/clinics", clinic_payload, headers=bearer(staff_token))
    check("POST /api/clinics (staff) -> 403", s == 403, f"(got {s})")

    s, me = request(
        "GET", "/api/auth/me", headers={"Authorization": f"Bearer {staff_token}"}
    )
    check("GET /api/auth/me -> 200 (bearer)", s == 200 and me and me.get("id"), f"(got {s})")

    s, otp = request("POST", "/api/auth/otp/request", {"phone": auth_phone})
    check("POST /api/auth/otp/request -> 200 otp_sent", s == 200 and otp and otp.get("status") == "otp_sent", f"(got {s})")

    s, prov = request("GET", "/api/auth/providers")
    check("GET /api/auth/providers -> 200 flags", s == 200 and prov and prov.get("password") is True, f"(got {s})")

    # --- summary ---------------------------------------------------------------
    print("=" * 60)
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s):")
        for label in FAILURES:
            print("  -", label)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())