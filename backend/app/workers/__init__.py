"""Celery tasks for background jobs"""
from celery_app import celery_app
from app.services.pos import get_pos_provider
from app.db.supabase import get_supabase
import stripe
import os
import logging

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def push_order_to_pos(self, order_data: dict, restaurant_config: dict):
    """Push order to POS with exponential backoff retry"""
    try:
        provider = get_pos_provider(
            restaurant_config["pos_provider"],
            restaurant_config["pos_config"],
        )
        import asyncio
        result = asyncio.run(provider.push_order(order_data))
        
        # Update order with POS order ID
        supabase = get_supabase()
        supabase.table("orders").update({
            "pos_order_id": result.get("order", {}).get("id"),
            "state": "SYNCED",
        }).eq("id", order_data["id"]).execute()
        
        logger.info(f"Order {order_data['id']} pushed to POS")
        return result
    except Exception as exc:
        logger.error(f"POS push failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task
def payment_expiry_check():
    """Check for expired Stripe payment links"""
    supabase = get_supabase()
    # Find expired payments
    # TODO: Implement expiry logic
    pass


@celery_app.task(bind=True, max_retries=3, default_retry_delay=300)
def send_sms(self, phone: str, message: str, restaurant_config: dict):
    """Send SMS via Telnyx"""
    import httpx
    
    try:
        with httpx.Client() as client:
            response = client.post(
                "https://api.telnyx.com/v2/messages",
                headers={
                    "Authorization": f"Bearer {os.getenv('TELNYX_API_KEY')}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": restaurant_config["telnyx_number"],
                    "to": phone,
                    "text": message,
                },
            )
            response.raise_for_status()
    except Exception as exc:
        logger.error(f"SMS failed: {exc}")
        raise self.retry(exc=exc)