from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WebhookSender(ABC):
    @abstractmethod
    async def send(self, url: str, payload: dict[str, Any]) -> None:
        """Raises WebhookDeliveryError unless the endpoint answers 2xx."""
