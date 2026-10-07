from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from typing import Any

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentRequest, PaymentStatus
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.values.money import Currency, Money


def payment_request(
    amount: Decimal = Decimal("100.50"),
    currency: Currency = Currency.RUB,
    description: str = "Order #1",
    metadata: dict[str, Any] | None = None,
    webhook_url: str = "http://hooks.example/ok",
) -> PaymentRequest:
    return PaymentRequest(
        money=Money(amount, currency),
        description=description,
        metadata={"order_id": 1} if metadata is None else metadata,
        webhook_url=webhook_url,
    )


class InMemoryPaymentRepository(PaymentRepository):
    """Stores copies, so a caller mutating its Payment does not change the "database"."""

    def __init__(self) -> None:
        self.payments: dict[uuid.UUID, Payment] = {}
        self.events: list[OutboxEvent] = []

    async def add(self, payment: Payment, event: OutboxEvent) -> Payment:
        for stored in self.payments.values():
            if stored.idempotency_key == payment.idempotency_key:
                return replace(stored)
        self.payments[payment.id] = replace(payment)
        self.events.append(event)
        return payment

    async def get(self, payment_id: uuid.UUID) -> Payment | None:
        payment = self.payments.get(payment_id)
        return replace(payment) if payment else None

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
    async def lock_pending(self, limit: int) -> AsyncGenerator[list[OutboxEvent]]:
        batch = self.pending[:limit]
        yield list(batch)
        self.pending = self.pending[len(batch) :]
        self.published.extend(batch)
