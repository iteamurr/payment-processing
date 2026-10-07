from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from faststream.rabbit import RabbitBroker, RabbitMessage
from pydantic import BaseModel

from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.infrastructure.broker.rabbit import ATTEMPT_HEADER, retry_queue


class PaymentCreated(BaseModel):
    payment_id: uuid.UUID


@dataclass
class PaymentCreatedHandler:
    """Processes one payments.new message; failures go to the next retry queue, then to the DLQ via reject.

    Manual ack: nothing may escape handle(), or the delivery stays unacked until consumer_timeout."""

    processing: PaymentProcessing
    broker: RabbitBroker

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def handle(self, message: RabbitMessage) -> None:
        try:
            payment_id, attempt = _parse(message)
        except (TypeError, ValueError):
            self._logger.warning("malformed message %s, dead-lettering", message.message_id, exc_info=True)
            await message.reject()
            return

        try:
            await self.processing.process(payment_id)
        except Exception:
            await self._retry_or_dead_letter(message, payment_id, attempt)
        else:
            await message.ack()

    async def _retry_or_dead_letter(self, message: RabbitMessage, payment_id: uuid.UUID, attempt: int) -> None:
        retry = retry_queue(attempt)
        if retry is None:
            self._logger.exception("payment %s failed on attempt %s, dead-lettering", payment_id, attempt)
            await message.reject()
            return

        self._logger.warning(
            "payment %s failed on attempt %s, retrying via %s", payment_id, attempt, retry.name, exc_info=True
        )
        try:
            # published before ack: a crash in between duplicates the message, never loses it
            await self.broker.publish(
                message.body,
                queue=retry,
                headers={**message.headers, ATTEMPT_HEADER: attempt + 1},
                persist=True,
                message_id=message.message_id,
                content_type=message.content_type,
            )
        except Exception:
            self._logger.exception("payment %s: retry publish failed, dead-lettering", payment_id)
            await message.reject()
            return
        await message.ack()


def _parse(message: RabbitMessage) -> tuple[uuid.UUID, int]:
    """Raises ValueError or TypeError on a malformed body or x-attempt header."""
    payment_id = PaymentCreated.model_validate_json(message.body).payment_id
    attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
    if attempt < 1:
        raise ValueError(f"{ATTEMPT_HEADER} must be positive, got {attempt}")
    return payment_id, attempt
