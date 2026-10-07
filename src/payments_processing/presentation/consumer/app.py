import httpx
from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage
from sqlalchemy.ext.asyncio import AsyncEngine

from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW, declare_topology
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler
from payments_processing.project.container import get_container
from payments_processing.project.logging import configure_logging


def subscribe(broker: RabbitBroker, handler: PaymentCreatedHandler) -> None:
    """Manual ack: the handler alone decides ack, retry or dead-letter."""

    @broker.subscriber(PAYMENTS_NEW, PAYMENTS_EXCHANGE, ack_policy=AckPolicy.MANUAL)
    async def on_payment_created(message: RabbitMessage) -> None:
        await handler.handle(message)


def build_consumer() -> FastStream:
    configure_logging()
    container = get_container()
    broker = container.resolve(RabbitBroker)
    subscribe(broker, container.resolve(PaymentCreatedHandler))

    async def declare() -> None:
        """Retry queues and the DLQ must exist before the first message can fail."""
        await broker.connect()
        await declare_topology(broker)

    async def close() -> None:
        await container.resolve(httpx.AsyncClient).aclose()
        await container.resolve(AsyncEngine).dispose()

    return FastStream(broker, on_startup=[declare], after_shutdown=[close])
