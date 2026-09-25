"""MediCall AI — FastAPI Application Entry Point.

Indian Medical Call Center: voice-first, multi-language
(Hindi/English/Tamil/Telugu/Bengali), PostgreSQL + pgvector backend.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.api import (
    admin,
    analytics,
    appointments,
    auth,
    calls,
    clinics,
    compliance,
    notifications,
    payments,
    prescriptions,
    voice,
)
from app.db.postgres import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    print("MediCall AI started")
    yield
    # Shutdown
    print("MediCall AI shutting down")


app = FastAPI(
    title="MediCall AI",
    description="Voice-first AI Medical Call Center for India",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes: voice-first (G4) + domain APIs (calls/appointments/prescriptions/payments/clinics)
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(clinics.router)
app.include_router(calls.router)
app.include_router(appointments.router)
app.include_router(prescriptions.router)
app.include_router(payments.router)
app.include_router(notifications.router)
app.include_router(compliance.router)
app.include_router(analytics.router)
app.include_router(admin.router)
app.include_router(
    auth.router, prefix="/api/auth", tags=["auth"]
)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "medicall-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
