from __future__ import annotations

import asyncio
import logging
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
        """Publishes one batch in order and stops at the first failure; events published before it stay published."""
        async with self.outbox.lock_pending(self.batch_size) as batch:
            for event in batch.events:
                try:
                    await self.publisher.publish(event)
                except Exception:
                    self._logger.exception(
                        "outbox event %s publish failed, retrying in %ss", event.id, self.poll_interval_s
                    )
                    break
                batch.mark_published(event)
        return len(batch.published)

    async def run(self) -> None:
        """Polls until cancelled; a full batch is followed by the next one without waiting."""
        while True:
            try:
                published = await self.publish_pending()
            except Exception:
                self._logger.exception("outbox relay run failed, retrying in %ss", self.poll_interval_s)
                published = 0
            if published < self.batch_size:
                await asyncio.sleep(self.poll_interval_s)
