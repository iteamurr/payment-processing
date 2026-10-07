from __future__ import annotations

import asyncio
import random
import uuid
from dataclasses import dataclass, field

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway


@dataclass
class FakePaymentGateway(PaymentGateway):
    """Emulated gateway: uniform 2–5 s latency, 90% success.

    Idempotent per payment.id like a real gateway given it as the idempotency key; charges are remembered
    in this process only, so consumer replicas do not share them."""

    min_delay_s: float = 2.0
    max_delay_s: float = 5.0
    success_rate: float = 0.9
    rng: random.Random = field(default_factory=random.Random)
    _charges: dict[uuid.UUID, asyncio.Task[PaymentStatus]] = field(
        default_factory=dict[uuid.UUID, asyncio.Task[PaymentStatus]], init=False, repr=False
    )

    async def charge(self, payment: Payment) -> PaymentStatus:
        if payment.id not in self._charges:
            self._charges[payment.id] = asyncio.create_task(self._charge())
        return await asyncio.shield(self._charges[payment.id])

    async def _charge(self) -> PaymentStatus:
        await asyncio.sleep(self.rng.uniform(self.min_delay_s, self.max_delay_s))
        return PaymentStatus.SUCCEEDED if self.rng.random() < self.success_rate else PaymentStatus.FAILED
