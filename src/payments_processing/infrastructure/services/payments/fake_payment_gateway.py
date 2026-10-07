from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway


@dataclass
class FakePaymentGateway(PaymentGateway):
    """Emulated gateway: deterministic 2–5 s latency and a 90% success distribution.

    Both values come from payment.id, so separate consumer processes and restarts return the same result without
    sharing state, like a real gateway given payment.id as its idempotency key."""

    min_delay_s: float = 2.0
    max_delay_s: float = 5.0
    success_rate: float = 0.9

    async def charge(self, payment: Payment) -> PaymentStatus:
        digest = hashlib.sha256(payment.id.bytes).digest()
        delay_roll = int.from_bytes(digest[:8]) / 2**64
        result_roll = int.from_bytes(digest[8:16]) / 2**64
        delay = self.min_delay_s + (self.max_delay_s - self.min_delay_s) * delay_roll
        await asyncio.sleep(delay)
        return PaymentStatus.SUCCEEDED if result_roll < self.success_rate else PaymentStatus.FAILED
