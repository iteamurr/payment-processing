from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Self, cast

PAYMENT_CREATED = "payment.created"


@dataclass(slots=True, frozen=True)
class PaymentCreated:
    """Body of a payment.created message; the one definition shared by producer and consumer."""

    payment_id: uuid.UUID

    def to_payload(self) -> dict[str, Any]:
        return {"payment_id": str(self.payment_id)}

    @classmethod
    def from_payload(cls, payload: Any) -> Self:
        """Raises ValueError unless payload is {"payment_id": "<uuid>"}."""
        payment_id = cast(dict[str, Any], payload).get("payment_id") if isinstance(payload, dict) else None
        if not isinstance(payment_id, str):
            raise ValueError(f"not a {PAYMENT_CREATED} payload: {payload!r}")
        return cls(uuid.UUID(payment_id))


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
