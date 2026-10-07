from __future__ import annotations

import copy
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from payments_processing.domain.errors import InvalidPaymentTransitionError
from payments_processing.domain.values.money import Money


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    def can_become(self, target: PaymentStatus) -> bool:
        return self is PaymentStatus.PENDING and target is not PaymentStatus.PENDING


@dataclass(slots=True, frozen=True)
class PaymentRequest:
    money: Money
    description: str
    metadata: dict[str, Any]
    webhook_url: str

    def fingerprint(self) -> str:
        """sha256 of canonical JSON with sorted keys."""
        canonical = json.dumps(
            {
                "amount": str(self.money.amount),
                "currency": self.money.currency.value,
                "description": self.description,
                "metadata": self.metadata,
                "webhook_url": self.webhook_url,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(slots=True)
class Payment:
    id: uuid.UUID
    money: Money
    description: str
    metadata: dict[str, Any]
    webhook_url: str
    idempotency_key: str
    request_hash: str
    status: PaymentStatus = PaymentStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None

    @classmethod
    def build(cls, request: PaymentRequest, idempotency_key: str) -> Self:
        return cls(
            id=uuid.uuid4(),
            money=request.money,
            description=request.description,
            metadata=copy.deepcopy(request.metadata),
            webhook_url=request.webhook_url,
            idempotency_key=idempotency_key,
            request_hash=request.fingerprint(),
        )

    def complete(self, status: PaymentStatus, processed_at: datetime) -> None:
        """Raises InvalidPaymentTransitionError unless pending -> succeeded|failed."""
        if not self.status.can_become(status):
            raise InvalidPaymentTransitionError(f"payment {self.id}: invalid transition {self.status} -> {status}")
        self.status = status
        self.processed_at = processed_at
