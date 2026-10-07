from __future__ import annotations

from faststream.rabbit import Channel, ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

ATTEMPT_HEADER = "x-attempt"
MAX_ATTEMPTS = 3
# TTL is fixed per queue: changing a delay means a new queue name or deleting the old queue
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


def retry_queue(attempt: int) -> RabbitQueue | None:
    """Delay queue after failed `attempt`; None once MAX_ATTEMPTS is used up."""
    return RETRY_QUEUES[attempt - 1] if attempt < MAX_ATTEMPTS else None


async def declare_topology(broker: RabbitBroker) -> None:
    """Idempotent; api and consumer both call it, so the relay never publishes into an unbound exchange."""
    payments = await broker.declare_exchange(PAYMENTS_EXCHANGE)
    dead_letters = await broker.declare_exchange(DEAD_LETTER_EXCHANGE)
    await (await broker.declare_queue(PAYMENTS_NEW)).bind(payments, routing_key=PAYMENTS_NEW.routing_key)
    await (await broker.declare_queue(PAYMENTS_NEW_DLQ)).bind(dead_letters, routing_key=PAYMENTS_NEW_DLQ.routing_key)
    for queue in RETRY_QUEUES:
        await broker.declare_queue(queue)


def build_broker(url: str, prefetch_count: int = 10) -> RabbitBroker:
    """Publisher confirms are on by default; on_return_raises turns an unroutable publish into an error."""
    return RabbitBroker(url, default_channel=Channel(prefetch_count=prefetch_count, on_return_raises=True))
