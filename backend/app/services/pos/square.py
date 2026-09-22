"""Square POS integration"""
import httpx
import os
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod


class POSProvider(ABC):
    """Abstract POS provider interface"""

    @abstractmethod
    async def push_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Push order to POS, return POS order ID"""
        pass

    @abstractmethod
    async def sync_menu(self, restaurant_id: str, menu_items: list) -> bool:
        """Sync menu to POS"""
        pass


class SquarePOS(POSProvider):
    """Square POS implementation"""

    def __init__(self, access_token: str, location_id: str):
        self.access_token = access_token
        self.location_id = location_id
        self.base_url = "https://connect.squareupsandbox.com/v2"  # Sandbox

    async def push_order(self, order_data: Dict) -> Dict:
        """Create order in Square"""
        async with httpx.AsyncClient() as client:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Square-Version": "2024-01-18",
                "Content-Type": "application/json",
            }
            payload = {
                "order": {
                    "location_id": self.location_id,
                    "line_items": [
                        {
                            "name": item["name"],
                            "quantity": str(item["quantity"]),
                            "base_price_money": {
                                "amount": item["price_cents"],
                                "currency": "AUD",
                            },
                        }
                        for item in order_data["items"]
                    ],
                },
                "idempotency_key": order_data["idempotency_key"],
            }
            response = await client.post(
                f"{self.base_url}/orders", json=payload, headers={"Authorization": f"Bearer {self.access_token}"}
            )
            response.raise_for_status()
            return response.json()

    async def sync_menu(self, restaurant_id: str, menu_items: list) -> bool:
        """Sync menu items to Square catalog"""
        # TODO: Implement Square catalog sync
        return True


def get_pos_provider(provider: str, config: Dict) -> POSProvider:
    """Factory for POS providers"""
    if provider == "square":
        return SquarePOS(config["access_token"], config["location_id"])
    elif provider == "lightspeed":
        # TODO: Implement Lightspeed
        pass
    elif provider == "kounta":
        # TODO: Implement Kounta
        pass
    raise ValueError(f"Unknown POS provider: {provider}")