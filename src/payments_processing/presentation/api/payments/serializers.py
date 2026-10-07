from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from payments_processing.domain.entities.payment import Currency, PaymentRequest, PaymentStatus


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
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
