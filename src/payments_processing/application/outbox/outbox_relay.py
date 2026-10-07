from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass
from typing import ClassVar

from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository


@dataclass
class OutboxRelay:
    """Moves committed outbox events to the broker; at-least-once, the consumer absorbs duplicates."""

    outbox: OutboxRepository
    publisher: EventPublisher
    batch_size: int = 100
    poll_interval_s: float = 1.0

    _logger: ClassVar[logging.Logger] = logging.getLogger(__name__)

    async def publish_pending(self) -> int:
        """Publishes one batch; any publish error rolls the batch back for the next run."""
        async with self.outbox.lock_pending(self.batch_size) as events:
            for event in events:
                await self.publisher.publish(event)
        return len(events)

    async def run(self, shutdown: asyncio.Event) -> None:
        """Polls until `shutdown` is set; a full batch is followed by the next one without waiting."""
        while not shutdown.is_set():
            try:
                published = await self.publish_pending()
            except Exception:
                self._logger.exception("outbox publish failed, retrying in %ss", self.poll_interval_s)
                published = 0
            if published < self.batch_size:
                with suppress(TimeoutError):
                    await asyncio.wait_for(shutdown.wait(), self.poll_interval_s)
