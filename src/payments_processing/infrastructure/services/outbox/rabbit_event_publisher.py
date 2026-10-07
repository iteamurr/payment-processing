from __future__ import annotations

from dataclasses import dataclass, field

from faststream.rabbit import RabbitBroker

from payments_processing.domain.entities.outbox_event import OutboxEvent
from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW, declare_topology


@dataclass
class RabbitEventPublisher(EventPublisher):
    """Connects and declares the topology on the first publish, so the api starts and accepts payments
    while RabbitMQ is down; with publisher confirms a broker nack raises from publish()."""

    broker: RabbitBroker
    timeout_s: float = 10.0
    _connected: bool = field(default=False, init=False, repr=False)

    async def publish(self, event: OutboxEvent) -> None:
        if not self._connected:
            await self.broker.connect()
            await declare_topology(self.broker)
            self._connected = True
        await self.broker.publish(
            event.payload,
            exchange=PAYMENTS_EXCHANGE,
            routing_key=PAYMENTS_NEW.routing_key,
            persist=True,
            message_id=str(event.id),
            message_type=event.event_type,
            timeout=self.timeout_s,
        )
