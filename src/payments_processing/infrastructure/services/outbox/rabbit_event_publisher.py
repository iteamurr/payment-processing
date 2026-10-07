from __future__ import annotations

from dataclasses import dataclass

from faststream.rabbit import RabbitBroker
from pamqp.commands import Basic

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW


class PublishNotConfirmedError(ConnectionError):
    """Broker did not ack the publish."""


@dataclass
class RabbitEventPublisher(EventPublisher):
    broker: RabbitBroker
    timeout_s: float = 10.0

    async def publish(self, event: OutboxEvent) -> None:
        confirmation = await self.broker.publish(
            event.payload,
            exchange=PAYMENTS_EXCHANGE,
            routing_key=PAYMENTS_NEW.routing_key,
            persist=True,
            message_id=str(event.id),
            message_type=event.event_type,
            timeout=self.timeout_s,
        )
        if not isinstance(confirmation, Basic.Ack):
            raise PublishNotConfirmedError(f"event {event.id}: broker answered {confirmation!r}")
