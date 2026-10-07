from __future__ import annotations

from faststream.rabbit import Channel, RabbitBroker


def build_broker(url: str, prefetch_count: int) -> RabbitBroker:
    """Publisher confirms are on by default; on_return_raises turns an unroutable publish into an error."""
    return RabbitBroker(url, default_channel=Channel(prefetch_count=prefetch_count, on_return_raises=True))
