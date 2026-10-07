from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, HttpUrl

from payments_processing.domain.entities.payment import Currency, Payment, PaymentRequest, PaymentStatus


class CreatePaymentIn(BaseModel):
    amount: Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2, examples=["100.50"])]
    currency: Currency
    description: Annotated[str, Field(min_length=1, max_length=1000)]
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: HttpUrl

    def to_request(self) -> PaymentRequest:
        return PaymentRequest(
            amount=self.amount,
            currency=self.currency,
            description=self.description,
            metadata=self.metadata,
            webhook_url=str(self.webhook_url),
        )


class PaymentAcceptedOut(BaseModel):
    payment_id: uuid.UUID
    status: PaymentStatus
    created_at: datetime


class PaymentOut(BaseModel):
    id: uuid.UUID
    amount: Annotated[Decimal, Field(decimal_places=2)]
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None

    @classmethod
    def from_entity(cls, payment: Payment) -> Self:
        return cls(
            id=payment.id,
            amount=payment.amount.quantize(Decimal("0.01")),
            currency=payment.currency,
            description=payment.description,
            metadata=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
            created_at=payment.created_at,
            processed_at=payment.processed_at,
        )
