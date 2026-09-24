"""MediCall AI — HTTP smoke test of the API contracts (docs/uml/03-api-contracts.md).

Stdlib-only (urllib) so it runs anywhere without pip: this PC, a CI Ubuntu
runner, or the compose host. It drives the executable endpoint contract:

    GET  /health                                    -> 200 healthy
    POST /api/clinics                               -> 201 create (returns id)
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
    POST /api/voice/call-completed                  -> 200 accepted (transcript persistence hook, D1)

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


def request(method: str, path: str, body=None):
    """Return (status, decoded-json-or-None). Network errors -> (-1, {})."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
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


def main() -> int:
    print(f"MediCall AI smoke test -> {BASE_URL}")
    print("=" * 60)

    # --- health --------------------------------------------------------------
    s, j = request("GET", "/health")
    check("GET /health", s == 200 and j and j.get("status") == "ok", f"(got {s})")

    # --- clinics: create/list/detail/patch + 404 missing row -----------------
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
    s, clinic = request("POST", "/api/clinics", clinic_payload)
    check("POST /api/clinics -> 201", s == 201 and clinic and clinic.get("id"), f"(got {s})")
    clinic_id = (clinic or {}).get("id", "")

    s, rows = request("GET", "/api/clinics")
    present = isinstance(rows, list) and any(r.get("id") == clinic_id for r in rows)
    check("GET /api/clinics -> 200 + created present", s == 200 and present, f"(got {s})")

    s, j = request("GET", f"/api/clinics/{clinic_id}")
    check("GET /api/clinics/{id} -> 200 detail", s == 200 and j and j.get("id") == clinic_id, f"(got {s})")

    s, j = request("PATCH", f"/api/clinics/{clinic_id}", {"name": "Smoke Clinic Updated"})
    check("PATCH /api/clinics/{id} -> 200 update", s == 200 and j and j.get("name") == "Smoke Clinic Updated", f"(got {s})")

    s, _ = request("GET", f"/api/clinics/{uuid.uuid4()}")
    check("GET /api/clinics/{id} -> 404 missing row", s == 404, f"(got {s})")

    # --- calls: clinic-scoped list, 404s, 422/409 state guards ---------------
    s, rows = request("GET", f"/api/calls?clinic_id={clinic_id}")
    check("GET /api/calls?clinic_id= -> 200 list", s == 200 and isinstance(rows, list), f"(got {s})")

    s, _ = request("GET", f"/api/calls/{uuid.uuid4()}")
    check("GET /api/calls/{id} -> 404 missing row", s == 404, f"(got {s})")

    s, _ = request("PATCH", f"/api/calls/{uuid.uuid4()}/state", {"state": "not-a-state"})
    check("PATCH call state invalid value -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/calls/{uuid.uuid4()}/state", {"state": "TRIAGE"})
    check("PATCH call state missing row -> 404", s == 404, f"(got {s})")

    if rows:
        s, _ = request("PATCH", f"/api/calls/{rows[0]['id']}/state", {"state": rows[0]["state"]})
        check("PATCH call state no-op -> 409 invalid transition", s == 409, f"(got {s})")
    else:
        print("SKIP - no call rows yet (the voice pipeline creates them); "
              "409 invalid transition is not exercisable without a live call")

    s, _ = request("GET", f"/api/calls/{uuid.uuid4()}/transcript")
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
    s, appt = request("POST", "/api/appointments", appt_payload)
    check("POST /api/appointments -> 201", s == 201 and appt and appt.get("id"), f"(got {s})")
    appt_id = (appt or {}).get("id", "")

    s, j = request("GET", f"/api/appointments/{appt_id}")
    check("GET /api/appointments/{id} -> 200 detail", s == 200 and j and j.get("id") == appt_id, f"(got {s})")

    s, _ = request("GET", f"/api/appointments/{uuid.uuid4()}")
    check("GET /api/appointments/{id} -> 404 missing row", s == 404, f"(got {s})")

    s, _ = request("PATCH", f"/api/appointments/{appt_id}/status", {"status": "bogus"})
    check("PATCH appointment status invalid -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/appointments/{appt_id}/status", {"status": "confirmed"})
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
    s, rx = request("POST", "/api/prescriptions", rx_payload)
    check("POST /api/prescriptions -> 201", s == 201 and rx and rx.get("id"), f"(got {s})")
    rx_id = (rx or {}).get("id", "")

    s, _ = request("PATCH", f"/api/prescriptions/{rx_id}/status", {"status": "bogus"})
    check("PATCH prescription status invalid -> 422", s == 422, f"(got {s})")

    s, _ = request("PATCH", f"/api/prescriptions/{rx_id}/status", {"status": "approved"})
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
    s, pay = request("POST", "/api/payments", pay_payload)
    check("POST /api/payments -> 201 (intent only)", s == 201 and pay and pay.get("id"), f"(got {s})")
    pay_id = (pay or {}).get("id", "")

    s, _ = request("PATCH", f"/api/payments/{pay_id}/status", {"status": "bogus"})
    check("PATCH payment status invalid -> 422", s == 422, f"(got {s})")

    # --- voice: call-completed transcript persistence hook (D1) ---------------
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
    check("POST /api/voice/call-completed -> 200", s == 200 and j, f"(got {s})")

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