from __future__ import annotations

from dataclasses import dataclass

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.entities.payment import Payment, PaymentRequest
from payments_processing.domain.errors import IdempotencyConflictError
from payments_processing.domain.services.payments.payment_repository import PaymentRepository


@dataclass
class PaymentCreation:
    """Stores a new payment with its payment.created event; a repeated key returns the stored payment."""

    repository: PaymentRepository

    async def create(self, request: PaymentRequest, idempotency_key: str) -> Payment:
        """Raises IdempotencyConflictError if the key was already used with a different request."""
        payment = Payment.build(request, idempotency_key)
        stored = await self.repository.add(payment, OutboxEvent.payment_created(payment.id))
        if stored.request_hash != payment.request_hash:
            raise IdempotencyConflictError(f"idempotency key {idempotency_key!r} was used with a different request")
        return stored
