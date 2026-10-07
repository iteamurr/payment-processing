from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from faststream.rabbit import RabbitBroker, RabbitMessage
from pydantic import BaseModel, ValidationError

from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.infrastructure.broker.rabbit import ATTEMPT_HEADER, retry_queue


class PaymentCreated(BaseModel):
    payment_id: uuid.UUID


@dataclass
class PaymentCreatedHandler:
    """Processes one payments.new message; failures go to the next retry queue, then to the DLQ via reject."""

    processing: PaymentProcessing
    broker: RabbitBroker

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def handle(self, message: RabbitMessage) -> None:
        try:
            event = PaymentCreated.model_validate_json(message.body)
        except ValidationError:
            self._logger.warning("malformed message %s, dead-lettering", message.message_id)
            await message.reject()
            return

        attempt = int(message.headers.get(ATTEMPT_HEADER, 1))
        try:
            await self.processing.process(event.payment_id)
        except Exception:
            retry = retry_queue(attempt)
            if retry is None:
                self._logger.exception("payment %s failed on attempt %s, dead-lettering", event.payment_id, attempt)
                await message.reject()
                return
            self._logger.warning(
                "payment %s failed on attempt %s, retrying via %s", event.payment_id, attempt, retry.name, exc_info=True
            )
            # publish before ack: a crash in between duplicates the message, never loses it
            await self.broker.publish(
                message.body,
                queue=retry,
                headers={**message.headers, ATTEMPT_HEADER: attempt + 1},
                persist=True,
                message_id=message.message_id,
                content_type=message.content_type,
            )
        await message.ack()
