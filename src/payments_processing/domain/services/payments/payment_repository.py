from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment


class PaymentRepository(ABC):
    @abstractmethod
    async def add(self, payment: Payment, event: OutboxEvent) -> Payment:
        """Stores the payment and its outbox event atomically unless idempotency_key is taken.

        Returns the payment stored under the key: `payment` itself or the one created earlier."""

    @abstractmethod
    async def get(self, payment_id: uuid.UUID) -> Payment | None: ...

    @abstractmethod
    async def save_result(self, payment: Payment) -> bool:
        """Stores status/processed_at only if the stored payment is still pending; False otherwise."""
