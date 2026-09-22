"""TalkByte AI — FastAPI Application Entry Point"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from app.api import voice, orders, restaurants, payments, admin
from app.db.supabase import init_supabase
from app.workers.celery_app import celery_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_supabase()
    print("TalkByte AI started")
    yield
    # Shutdown
    print("TalkByte AI shutting down")


app = FastAPI(
    title="TalkByte AI",
    description="AI Phone Ordering System for Australian Restaurants",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])
app.include_router(orders.router, prefix="/api/orders", tags=["orders"])
app.include_router(restaurants.router, prefix="/api/restaurants", tags=["restaurants"])
app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "talkbyte-api"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)