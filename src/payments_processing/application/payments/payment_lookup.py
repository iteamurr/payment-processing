from __future__ import annotations

import uuid
from dataclasses import dataclass

from payments_processing.domain.entities.payment import Payment
from payments_processing.domain.errors import PaymentNotFoundError
from payments_processing.domain.services.payments.payment_repository import PaymentRepository


@dataclass
class PaymentLookup:
    repository: PaymentRepository

    async def get(self, payment_id: uuid.UUID) -> Payment:
        """Raises PaymentNotFoundError."""
        payment = await self.repository.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"payment {payment_id} not found")
        return payment
