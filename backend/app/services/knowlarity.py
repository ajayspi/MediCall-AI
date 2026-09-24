"""Knowlarity SR API client (India telephony) — G5.

Knowlarity path decision (G5-D1, approved 2026-09-24): in-house httpx client
against the public SR API. Knowlarity ships no maintained PyPI SDK, so the
correct primitive is a thin client over their REST endpoints.

Endpoints verified 2026-09-24 (developer.knowlarity.com + Gupshup/Knowlarity
docs):
    POST {base}/call/makecall          direct outbound call
    POST {base}/call/campaign          place an OBD campaign call
    GET  {base}/call/campaign/order-status/?order_id=…   campaign status
    base default https://kpi.knowlarity.com/Basic/v1/account

Auth (SR API): request headers `authorization: <key>` and `x-api-key: <key>`.

Transport methods import httpx lazily so this module stays importable on
machines without third-party packages — same pattern as G4's telephony.py
(our acceptance tests are stdlib-only; live outbound calls are Docker/CI work).
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Dict, Optional

DEFAULT_BASE_URL = "https://kpi.knowlarity.com/Basic/v1/account"
DEFAULT_TIMEZONE = "Asia/Kolkata"


@dataclass
class KnowlarityConfig:
    """Connection settings for the Knowlarity SR API (env-driven)."""

    api_key: str = ""  # x-api-key header
    authorization: str = ""  # authorization header
    k_number: str = ""  # SR number / SIP URI (default dial-out number)
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 30.0


def from_env(env: Optional[dict] = None) -> KnowlarityConfig:
    """Build a config from the environment (KNOWLARITY_* vars)."""
    env = env if env is not None else os.environ
    return KnowlarityConfig(
        api_key=env.get("KNOWLARITY_API_KEY", ""),
        authorization=env.get("KNOWLARITY_AUTHORIZATION", ""),
        k_number=env.get("KNOWLARITY_SIP_URI", ""),
    )


def headers(config: KnowlarityConfig) -> Dict[str, str]:
    """SR API auth headers — authorization + x-api-key (JSON body)."""
    return {
        "accept": "application/json",
        "authorization": config.authorization,
        "x-api-key": config.api_key,
        "content-type": "application/json",
    }


def makecall_url(config: KnowlarityConfig) -> str:
    return f"{config.base_url}/call/makecall"


def campaign_url(config: KnowlarityConfig) -> str:
    return f"{config.base_url}/call/campaign"


def order_status_url(config: KnowlarityConfig, order_id: str) -> str:
    return f"{config.base_url}/call/campaign/order-status/?order_id={order_id}"


def _utc_uniqueid() -> str:
    return f"{datetime.now(timezone.utc).timestamp():.0f}"


def makecall_payload(
    config: KnowlarityConfig,
    customer_number: str,
    agent_number: str = "",
    caller_id: str = "",
) -> dict:
    """Body for POST /call/makecall (direct outbound call).

    k_number = the SR/SIP number that originates the call; caller_id defaults
    to it so callbacks/IVR re-entry resolve to the same number.
    """
    return {
        "k_number": config.k_number,
        "agent_number": agent_number,
        "customer_number": customer_number,
        "caller_id": caller_id or config.k_number,
        "additional_params": {"uniqueid": _utc_uniqueid()},
    }


def campaign_payload(
    config: KnowlarityConfig,
    sound_id,
    additional_number: str,
    timezone: str = DEFAULT_TIMEZONE,
    start_time: Optional[str] = None,
    priority: int = 1,
) -> dict:
    """Body for POST /call/campaign (OBD campaign, single-number helper).

    The SR API wants sound_id/ivr_id as an id plus a 'yyyy-MM-dd HH:mm'
    start_time; defaulting to now keeps rapid dialing from needing a
    scheduler, matching the documented OBD flow.
    """
    if start_time is None:
        start_time = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "sound_id": str(sound_id),
        "additional_number": additional_number,
        "k_number": config.k_number,
        "timezone": timezone,
        "priority": str(priority),
        "start_time": start_time,
    }


def _id_of(data: dict) -> str:
    """Defensive request/order-id extraction (response shapes vary by plan)."""
    for key in ("request_id", "order_id", "id"):
        if key in data and data.get(key) is not None:
            return str(data[key])
    return ""


async def make_call(
    config: KnowlarityConfig,
    customer_number: str,
    agent_number: str = "",
    caller_id: str = "",
):
    """POST /call/makecall — parsed JSON response. httpx imported lazily."""
    import httpx

    url = makecall_url(config)
    payload = makecall_payload(config, customer_number, agent_number, caller_id)
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.post(url, headers=headers(config), json=payload)
        response.raise_for_status()
        return response.json()


async def place_campaign(
    config: KnowlarityConfig,
    sound_id,
    additional_number: str,
    timezone: str = DEFAULT_TIMEZONE,
    start_time: Optional[str] = None,
    priority: int = 1,
):
    """POST /call/campaign — parsed JSON response. httpx imported lazily."""
    import httpx

    url = campaign_url(config)
    payload = campaign_payload(
        config, sound_id, additional_number, timezone, start_time, priority
    )
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.post(url, headers=headers(config), json=payload)
        response.raise_for_status()
        return response.json()


async def campaign_status(config: KnowlarityConfig, order_id: str):
    """GET /call/campaign/order-status — parsed JSON response. httpx lazy."""
    import httpx

    url = order_status_url(config, order_id)
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url, headers=headers(config))
        response.raise_for_status()
        return response.json()