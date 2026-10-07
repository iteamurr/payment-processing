from __future__ import annotations

from abc import ABC, abstractmethod

from payments_processing.domain.entities.payment import Payment


class WebhookSender(ABC):
    @abstractmethod
    async def send(self, payment: Payment) -> None:
        """Notifies payment.webhook_url of the result.

        Raises WebhookDeliveryError unless it answers 2xx, WebhookTargetForbiddenError for a non-public target."""
