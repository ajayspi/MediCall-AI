# 03 — API Contracts

```mermaid
flowchart LR
    Client["Frontend dashboards / telephony webhooks / LiveKit agent"] --> Voice
    Client --> Auth
    Client --> Clinics
    Client --> Calls
    Client --> Appointments
    Client --> Prescriptions
    Client --> Payments

    Auth["/api/auth<br/>POST /api/auth/register<br/>POST /api/auth/login<br/>POST /api/auth/otp/request<br/>POST /api/auth/otp/verify<br/>GET /api/auth/me (Bearer)<br/>POST /api/auth/logout<br/>GET /api/auth/providers<br/>POST /api/auth/oauth/{provider}<br/>SSO = 501 until env keys (google / microsoft / abha)"]
    Voice["/api/voice (prefix applied in main.py)<br/>POST /webhook/exotel<br/>POST /webhook/knowlarity<br/>POST /webhook/twilio<br/>POST /livekit-agent-start<br/>POST /call-completed"]
    Clinics["/api/clinics<br/>GET /api/clinics<br/>POST /api/clinics<br/>GET /api/clinics/{clinic_id}<br/>PATCH /api/clinics/{clinic_id}"]
    Calls["/api/calls<br/>GET /api/calls (filters: state, language, severity, from, to, limit, offset)<br/>GET /api/calls/{call_id}<br/>PATCH /api/calls/{call_id}/state<br/>GET /api/calls/{call_id}/transcript"]
    Appointments["/api/appointments<br/>GET /api/appointments<br/>POST /api/appointments<br/>GET /api/appointments/{appointment_id}<br/>PATCH /api/appointments/{appointment_id}/status"]
    Prescriptions["/api/prescriptions<br/>GET /api/prescriptions<br/>POST /api/prescriptions<br/>GET /api/prescriptions/{prescription_id}<br/>PATCH /api/prescriptions/{prescription_id}/status"]
    Payments["/api/payments<br/>GET /api/payments<br/>POST /api/payments<br/>GET /api/payments/{payment_id}<br/>PATCH /api/payments/{payment_id}/status"]

    StateGuard["PATCH /api/calls/{call_id}/state<br/>409 on invalid transition (STATE_TRANSITIONS)"]
    StatusGuard["PATCH .../status (appointment / prescription / payment)<br/>422 on invalid status value"]
    NotFound["All {id} lookups<br/>404 on missing row"]
```

## Notes

- Three routers (clinics, calls, appointments, prescriptions, payments — five
  modules) each declare `APIRouter(prefix="/api/<name>")`; `voice` is registered
  with the `/api/voice` prefix and `auth` with `prefix="/api/auth"` in `main.py`
  (all seven routers included).
- This endpoint set is the executable contract in
  `backend/tests/test_api_routes.py` (`EXPECTED_ENDPOINTS`) and the basis for the
  Docker/CI HTTP smoke tests.
- Contract behaviors: 409 invalid state transition, 422 invalid status, 404
  missing row — all acceptance-tested.
- Auth contract (G6-Q1, spec-auth.md): password + OTP are live
  (`/api/auth/register|login|otp/*`); `GET /me` requires a Bearer JWT;
  SSO (`/oauth/{provider}`) returns 501 until the Google/Microsoft/ABHA env
  keys are configured.
- `POST /api/payments` records an intent row only; it never calls a gateway SDK
  (G6-Q5 gated).