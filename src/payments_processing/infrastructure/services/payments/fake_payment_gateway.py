from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway


@dataclass
class FakePaymentGateway(PaymentGateway):
    """Emulated gateway: uniform 2–5 s latency, 90% success."""

    min_delay_s: float = 2.0
    max_delay_s: float = 5.0
    success_rate: float = 0.9
    rng: random.Random = field(default_factory=random.Random)

    async def charge(self, payment: Payment) -> PaymentStatus:
        await asyncio.sleep(self.rng.uniform(self.min_delay_s, self.max_delay_s))
        return PaymentStatus.SUCCEEDED if self.rng.random() < self.success_rate else PaymentStatus.FAILED
