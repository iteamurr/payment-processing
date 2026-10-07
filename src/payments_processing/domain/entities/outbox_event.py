from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self

from payments_processing.domain.messages import PAYMENT_CREATED, PaymentCreated


@dataclass(slots=True, frozen=True)
class OutboxEvent:
    """Event stored with the business change in one transaction and published later by the relay."""

    id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    @classmethod
    def payment_created(cls, payment_id: uuid.UUID) -> Self:
        return cls(
            id=uuid.uuid4(),
            event_type=PAYMENT_CREATED,
            payload=PaymentCreated(payment_id).to_payload(),
            created_at=datetime.now(UTC),
        )
