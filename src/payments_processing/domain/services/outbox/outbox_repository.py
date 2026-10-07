from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from payments_processing.domain.entities.outbox_event import OutboxEvent


@dataclass
class OutboxBatch:
    """Events locked for one relay run and the ones it managed to publish."""

    events: list[OutboxEvent]
    published: list[OutboxEvent] = field(default_factory=list[OutboxEvent])

    def mark_published(self, event: OutboxEvent) -> None:
        self.published.append(event)


class OutboxRepository(ABC):
    @abstractmethod
    def lock_pending(self, limit: int) -> AbstractAsyncContextManager[OutboxBatch]:
        """Yields up to `limit` unpublished events, oldest first, locked against other relays.

        Leaving the block normally stores the events marked in the batch as published;
        an exception stores nothing."""
