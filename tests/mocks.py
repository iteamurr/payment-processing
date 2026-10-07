from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Currency, Payment, PaymentRequest, PaymentStatus
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository
from payments_processing.domain.services.payments.payment_repository import PaymentRepository


def payment_request(**overrides) -> PaymentRequest:
    fields = {
        "amount": Decimal("100.50"),
        "currency": Currency.RUB,
        "description": "Order #1",
        "metadata": {"order_id": 1},
        "webhook_url": "http://hooks.example/ok",
    }
    return PaymentRequest(**(fields | overrides))


class InMemoryPaymentRepository(PaymentRepository):
    """Stores copies, so a caller mutating its Payment does not change the "database"."""

    def __init__(self) -> None:
        self.payments: dict[uuid.UUID, Payment] = {}
        self.events: list[OutboxEvent] = []

    async def add(self, payment: Payment, event: OutboxEvent) -> bool:
        if await self.get_by_idempotency_key(payment.idempotency_key) is not None:
            return False
        self.payments[payment.id] = replace(payment)
        self.events.append(event)
        return True

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        payment = self.payments.get(payment_id)
        return replace(payment) if payment else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        for payment in self.payments.values():
            if payment.idempotency_key == key:
                return replace(payment)
        return None

    async def save_result(self, payment: Payment) -> bool:
        if self.payments[payment.id].status is not PaymentStatus.PENDING:
            return False
        self.payments[payment.id] = replace(payment)
        return True


class InMemoryOutboxRepository(OutboxRepository):
    """Commit/rollback semantics of lock_pending: events move to `published` only if the block didn't raise."""

    def __init__(self, events: Iterable[OutboxEvent] = ()) -> None:
        self.pending: list[OutboxEvent] = list(events)
        self.published: list[OutboxEvent] = []

    @asynccontextmanager
    async def lock_pending(self, limit: int) -> AsyncIterator[list[OutboxEvent]]:
        batch = self.pending[:limit]
        yield list(batch)
        self.pending = self.pending[len(batch) :]
        self.published.extend(batch)
