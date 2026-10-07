from __future__ import annotations

from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

_RETRY_DELAYS_MS = (2000, 4000)

PAYMENTS_EXCHANGE = RabbitExchange("payments", ExchangeType.DIRECT, durable=True)
DEAD_LETTER_EXCHANGE = RabbitExchange("payments.dlx", ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_DLQ = RabbitQueue("payments.new.dlq", durable=True, routing_key="payments.new.dlq")
PAYMENTS_NEW = RabbitQueue(
    "payments.new",
    durable=True,
    routing_key="payments.new",
    arguments={
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE.name,
        "x-dead-letter-routing-key": PAYMENTS_NEW_DLQ.routing_key,
    },
)
RETRY_QUEUES = tuple(
    RabbitQueue(
        f"payments.new.retry.{attempt}",
        durable=True,
        arguments={
            "x-message-ttl": delay_ms,
            "x-dead-letter-exchange": PAYMENTS_EXCHANGE.name,
            "x-dead-letter-routing-key": PAYMENTS_NEW.routing_key,
        },
    )
    for attempt, delay_ms in enumerate(_RETRY_DELAYS_MS, start=1)
)


async def declare_topology(broker: RabbitBroker) -> None:
    """Idempotent; api and consumer both call it, so the relay never publishes into an unbound exchange.

    RabbitMQ refuses to redeclare a queue with different arguments: changing a retry delay
    means deleting that retry queue first or giving it a new name."""
    payments = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dead_letters = await broker.declare_exchange(DEAD_LETTER_EXCHANGE)
    new = await broker.declare_queue(PAYMENTS_NEW)
    await new.bind(payments, routing_key=PAYMENTS_NEW.routing_key)
    dlq = await broker.declare_queue(PAYMENTS_NEW_DLQ)
    await dlq.bind(dead_letters, routing_key=PAYMENTS_NEW_DLQ.routing_key)
    for queue in RETRY_QUEUES:
        await broker.declare_queue(queue)
