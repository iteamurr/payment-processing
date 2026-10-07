from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment


class PaymentRepository(ABC):
    @abstractmethod
    async def add(self, payment: Payment, event: OutboxEvent) -> bool:
        """Stores the payment and its outbox event atomically; False if idempotency_key is taken."""

    @abstractmethod
    async def get(self, payment_id: uuid.UUID) -> Payment | None: ...

    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> Payment | None: ...

    @abstractmethod
    async def save_result(self, payment: Payment) -> bool:
        """Stores status/processed_at only if the stored payment is still pending; False otherwise."""
