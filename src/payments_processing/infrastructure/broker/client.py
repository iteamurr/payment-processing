from __future__ import annotations

import logging

from faststream.rabbit import Channel, RabbitBroker


def build_broker(url: str, prefetch_count: int) -> RabbitBroker:
    """Publisher confirms are on by default; on_return_raises turns an unroutable publish into an error.

    Given a logger, FastStream logs through it instead of attaching its own plain-text handlers. On shutdown it
    waits up to graceful_timeout for messages in flight: gateway 5 s + webhook 10 s + retry publish 10 s,
    within the consumer's 30 s stop_grace_period."""
    return RabbitBroker(
        url,
        default_channel=Channel(prefetch_count=prefetch_count, on_return_raises=True),
        logger=logging.getLogger(__name__),
        graceful_timeout=25,
    )
