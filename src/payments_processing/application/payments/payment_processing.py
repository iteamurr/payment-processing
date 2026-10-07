from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.services.webhooks.webhook_sender import WebhookSender


@dataclass
class PaymentProcessing:
    """Charges a pending payment once and notifies its webhook; safe to run again for the same payment."""

    lookup: PaymentLookup
    repository: PaymentRepository
    gateway: PaymentGateway
    webhooks: WebhookSender

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def process(self, payment_id: uuid.UUID) -> None:
        """Errors propagate; the caller decides whether to retry."""
        payment = await self.lookup.get(payment_id)
        if payment.status is PaymentStatus.PENDING:
            payment = await self._charge(payment)
        await self.webhooks.send(payment)

    async def _charge(self, payment: Payment) -> Payment:
        """Returns the payment as stored: if a parallel delivery saved its result first, that result wins."""
        payment.complete(await self.gateway.charge(payment), datetime.now(UTC))
        if not await self.repository.save_result(payment):
            payment = await self.lookup.get(payment.id)
        self._logger.info("payment %s processed: %s", payment.id, payment.status)
        return payment
