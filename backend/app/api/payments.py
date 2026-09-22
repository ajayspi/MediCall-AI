"""Payments API — Stripe webhook + payment link generation"""
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import stripe
import os

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


class PaymentLinkCreate(BaseModel):
    order_id: str
    amount_cents: int
    currency: str = "aud"
    customer_phone: str


class PaymentWebhook(BaseModel):
    type: str
    data: dict


@router.post("/create-link/{order_id}")
async def create_payment_link(order_id: str, data: PaymentLinkCreate):
    """Create Stripe Payment Link for order"""
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": data.currency,
                    "product_data": {"name": f"Order {order_id}"},
                    "unit_amount": data.amount_cents,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{os.getenv('FRONTEND_URL')}/payment/success?order_id={order_id}",
            cancel_url=f"{os.getenv('FRONTEND_URL')}/payment/cancel?order_id={order_id}",
            phone_number_collection={"enabled": True},
            customer_email=None,
            metadata={"order_id": order_id},
        )
        return {"payment_link": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(500, str(e))


@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhooks"""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except Exception as e:
        raise HTTPException(400, str(e))

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        order_id = session.get("metadata", {}).get("order_id")
        # TODO: Update payment_events, mark order as paid
        pass

    return {"received": True}