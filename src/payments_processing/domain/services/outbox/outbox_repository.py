from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import AbstractAsyncContextManager

from payments_processing.domain.entities.outbox_event import OutboxEvent


class OutboxRepository(ABC):
    @abstractmethod
    def lock_pending(self, limit: int) -> AbstractAsyncContextManager[list[OutboxEvent]]:
        """Yields up to `limit` unpublished events, oldest first, locked against other relays.

        Leaving the block normally marks them published; an exception leaves them unpublished."""
