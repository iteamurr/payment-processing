from __future__ import annotations

from abc import ABC, abstractmethod

from payments_processing.domain.entities.payment import Payment


class WebhookSender(ABC):
    @abstractmethod
    async def send(self, payment: Payment) -> None:
        """Notifies payment.webhook_url of the result; raises WebhookDeliveryError unless it answers 2xx."""
