from __future__ import annotations

from abc import ABC, abstractmethod

from payments_processing.domain.entities.outbox_event import OutboxEvent


class EventPublisher(ABC):
    @abstractmethod
    async def publish(self, event: OutboxEvent) -> None:
        """Returns once the broker confirmed the message; raises otherwise."""
