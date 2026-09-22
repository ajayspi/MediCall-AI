"""Celery worker configuration"""
from celery import Celery
import os

celery_app = Celery(
    "talkbyte",
    broker=os.getenv("UPSTASH_REDIS_REST_URL"),
    backend=os.getenv("UPSTASH_REDIS_REST_URL"),
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Australia/Sydney",
    enable_utc=True,
    task_routes={
        "app.workers.tasks.push_order_to_pos": {"queue": "pos"},
        "app.workers.tasks.payment_expiry_check": {"queue": "payments"},
    },
    beat_schedule={
        "payment-expiry-check": {
            "task": "app.workers.tasks.payment_expiry_check",
            "schedule": 300.0,  # Every 5 minutes
        },
    },
)