from __future__ import annotations

from abc import ABC, abstractmethod

from payments_processing.domain.entities.payment import Payment


class WebhookSender(ABC):
    @abstractmethod
    async def check_target(self, payment: Payment) -> None:
        """Raises WebhookTargetForbiddenError if payment.webhook_url may not be called, before anything is charged."""

    @abstractmethod
    async def send(self, payment: Payment) -> None:
        """Notifies payment.webhook_url of the result.

        Raises WebhookDeliveryError unless it answers 2xx, WebhookTargetForbiddenError for a non-public target."""
