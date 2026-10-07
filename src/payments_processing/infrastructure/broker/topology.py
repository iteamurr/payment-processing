from __future__ import annotations

from faststream.rabbit import ExchangeType, QueueType, RabbitBroker, RabbitExchange, RabbitQueue
from faststream.rabbit.schemas.queue import QuorumQueueArgs

_RETRIES = 2
_FIRST_RETRY_DELAY_MS = 5_000
_RETRY_BACKOFF_FACTOR = 5
_RETRY_DELAYS_MS = tuple(_FIRST_RETRY_DELAY_MS * _RETRY_BACKOFF_FACTOR**n for n in range(_RETRIES))
_DELIVERY_LIMIT = 5


def _dead_letter_to(exchange: str, routing_key: str) -> QuorumQueueArgs:
    """Quorum queues dead-letter at most once by default; at-least-once needs reject-publish overflow."""
    return {
        "x-dead-letter-exchange": exchange,
        "x-dead-letter-routing-key": routing_key,
        "x-dead-letter-strategy": "at-least-once",
        "x-overflow": "reject-publish",
    }


PAYMENTS_EXCHANGE = RabbitExchange("payments", ExchangeType.DIRECT, durable=True)
DEAD_LETTER_EXCHANGE = RabbitExchange("payments.dlx", ExchangeType.DIRECT, durable=True)

PAYMENTS_NEW_DLQ = RabbitQueue(
    "payments.new.dlq", queue_type=QueueType.QUORUM, durable=True, routing_key="payments.new.dlq"
)
PAYMENTS_NEW = RabbitQueue(
    "payments.new",
    queue_type=QueueType.QUORUM,
    durable=True,
    routing_key="payments.new",
    arguments={
        **_dead_letter_to(DEAD_LETTER_EXCHANGE.name, PAYMENTS_NEW_DLQ.routing_key),
        "x-delivery-limit": _DELIVERY_LIMIT,
    },
)
RETRY_QUEUES = tuple(
    RabbitQueue(
        f"payments.new.retry.{attempt}",
        queue_type=QueueType.QUORUM,
        durable=True,
        arguments={
            **_dead_letter_to(PAYMENTS_EXCHANGE.name, PAYMENTS_NEW.routing_key),
            "x-message-ttl": delay_ms,
        },
    )
    for attempt, delay_ms in enumerate(_RETRY_DELAYS_MS, start=1)
)


async def declare_topology(broker: RabbitBroker) -> None:
    """Idempotent; api and consumer both call it, so the relay never publishes into an unbound exchange.

    Quorum queues: x-delivery-limit dead-letters a message that keeps crashing the consumer, since its redeliveries
    keep the same x-attempt. RabbitMQ refuses to redeclare a queue with different arguments: changing a retry delay
    or the queue type means deleting that queue first or giving it a new name."""
    payments = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dead_letters = await broker.declare_exchange(DEAD_LETTER_EXCHANGE)
    new = await broker.declare_queue(PAYMENTS_NEW)
    await new.bind(payments, routing_key=PAYMENTS_NEW.routing_key)
    dlq = await broker.declare_queue(PAYMENTS_NEW_DLQ)
    await dlq.bind(dead_letters, routing_key=PAYMENTS_NEW_DLQ.routing_key)
    for queue in RETRY_QUEUES:
        await broker.declare_queue(queue)
