from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from faststream.rabbit import RabbitBroker, RabbitMessage

from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.errors import PaymentNotFoundError, WebhookTargetForbiddenError
from payments_processing.domain.messages import PaymentCreated
from payments_processing.infrastructure.broker.retry import Attempt


@dataclass
class PaymentCreatedHandler:
    """Processes one payments.new message; failures go to the next retry queue, then to the DLQ via reject.

    Manual ack: nothing may escape handle(), or the delivery stays unacked until consumer_timeout."""

    processing: PaymentProcessing
    broker: RabbitBroker
    publish_timeout_s: float = 10.0

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def handle(self, message: RabbitMessage) -> None:
        try:
            event = PaymentCreated.from_payload(json.loads(message.body))
            attempt = Attempt.from_headers(message.headers)
        except (TypeError, ValueError):
            self._logger.warning("malformed message %s, dead-lettering", message.message_id, exc_info=True)
            await message.reject()
            return

        try:
            await self.processing.process(event.payment_id)
        except (PaymentNotFoundError, WebhookTargetForbiddenError):
            self._logger.exception("payment %s cannot succeed on retry, dead-lettering", event.payment_id)
            await message.reject()
        except Exception:
            await self._retry_or_dead_letter(message, event.payment_id, attempt)
        else:
            await message.ack()

    async def _retry_or_dead_letter(self, message: RabbitMessage, payment_id: uuid.UUID, attempt: Attempt) -> None:
        """The retry copy is published before the original is acked: a crash in between duplicates, never loses."""
        retry = attempt.retry_queue()
        if retry is None:
            self._logger.exception("payment %s failed on attempt %s, dead-lettering", payment_id, attempt.number)
            await message.reject()
            return

        self._logger.warning(
            "payment %s failed on attempt %s, retrying via %s", payment_id, attempt.number, retry.name, exc_info=True
        )
        try:
            await self.broker.publish(
                message.body,
                queue=retry,
                headers=attempt.next_headers(message.headers),
                persist=True,
                message_id=message.message_id,
                content_type=message.content_type,
                timeout=self.publish_timeout_s,
            )
        except Exception:
            self._logger.exception("payment %s: retry publish failed, dead-lettering", payment_id)
            await message.reject()
            return
        await message.ack()
