from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Self

from faststream.rabbit import RabbitQueue

from payments_processing.infrastructure.broker.topology import RETRY_QUEUES

ATTEMPT_HEADER = "x-attempt"
MAX_ATTEMPTS = len(RETRY_QUEUES) + 1


@dataclass(slots=True, frozen=True)
class Attempt:
    """Which processing attempt a payments.new delivery is; carried in the x-attempt header."""

    number: int

    def __post_init__(self) -> None:
        if self.number < 1:
            raise ValueError(f"attempt must be positive, got {self.number}")

    @classmethod
    def from_headers(cls, headers: Mapping[str, Any]) -> Self:
        """A delivery without the header is the first attempt; raises ValueError or TypeError if it is malformed."""
        return cls(int(headers.get(ATTEMPT_HEADER, 1)))

    def retry_queue(self) -> RabbitQueue | None:
        """Delay queue after this attempt fails; None once MAX_ATTEMPTS is used up."""
        return RETRY_QUEUES[self.number - 1] if self.number < MAX_ATTEMPTS else None

    def next_headers(self, headers: Mapping[str, Any]) -> dict[str, Any]:
        return {**headers, ATTEMPT_HEADER: self.number + 1}
