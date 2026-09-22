"""POS base interface (Strategy pattern)"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List


class POSProvider(ABC):
    """Abstract POS provider - Strategy pattern"""

    @abstractmethod
    async def push_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """Push order to POS, return POS order ID and status"""
        pass

    @abstractmethod
    async def sync_menu(self, restaurant_id: str, menu_items: List[Dict]) -> bool:
        """Sync menu to POS"""
        pass

    @abstractmethod
    async def get_order_status(self, pos_order_id: str) -> Dict:
        """Get order status from POS"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Provider identifier"""
        pass