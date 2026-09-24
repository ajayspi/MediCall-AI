"""Pydantic request models for the MediCall AI API (API routes phase).

One module per domain; status/gateway constants here are the single source
that the API routers validate against (values mirror postgres_schema.sql
comments + the G5 payment SDK pins: razorpay / phonepe / cashfree / manual).
"""