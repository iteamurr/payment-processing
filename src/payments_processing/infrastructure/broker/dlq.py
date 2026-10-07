from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from faststream.rabbit import RabbitBroker

from payments_processing.infrastructure.broker.topology import PAYMENTS_EXCHANGE, PAYMENTS_NEW, PAYMENTS_NEW_DLQ


async def replay_dead_letters(broker: RabbitBroker, timeout_s: float = 10.0) -> int:
    """Moves the messages in payments.new.dlq back to payments.new as first attempts; returns how many.

    Only the messages present at the start are moved, so one that fails again during the replay does not loop;
    the queue is redeclared for that count because the broker caches the first declaration's result.
    Each copy is published before the original is acked: a crash in between duplicates, never loses."""
    dlq = await broker.declare_queue(PAYMENTS_NEW_DLQ)
    pending = (await dlq.declare()).message_count or 0
    replayed = 0
    for _ in range(pending):
        message = await dlq.get(fail=False)
        if message is None:
            break
        await broker.publish(
            message.body,
            exchange=PAYMENTS_EXCHANGE,
            routing_key=PAYMENTS_NEW.routing_key,
            headers=_without_broker_headers(message.headers),
            persist=True,
            message_id=message.message_id,
            message_type=message.type,
            content_type=message.content_type,
            timeout=timeout_s,
        )
        await message.ack()
        replayed += 1
    return replayed


def _without_broker_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    """Drops x-attempt and the x-death bookkeeping, so the replay starts the retry count over."""
    return {name: value for name, value in headers.items() if not name.startswith("x-")}
