from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.errors import PaymentNotFoundError
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.services.payments.webhook_sender import WebhookSender


@dataclass
class PaymentProcessing:
    """Charges a pending payment once and notifies its webhook; safe to run again for the same payment."""

    repository: PaymentRepository
    gateway: PaymentGateway
    webhooks: WebhookSender

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def process(self, payment_id: uuid.UUID) -> None:
        """Errors propagate; the caller decides whether to retry."""
        payment = await self._get(payment_id)
        if payment.status is PaymentStatus.PENDING:
            payment.complete(await self.gateway.charge(payment), datetime.now(UTC))
            if not await self.repository.save_result(payment):
                # a parallel delivery stored its result first; notify with that one
                payment = await self._get(payment_id)
            self._logger.info("payment %s processed: %s", payment.id, payment.status)
        await self.webhooks.send(payment.webhook_url, payment.webhook_payload())

    async def _get(self, payment_id: uuid.UUID) -> Payment:
        payment = await self.repository.get(payment_id)
        if payment is None:
            raise PaymentNotFoundError(f"payment {payment_id} not found")
        return payment
