from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, AliasPath, BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl

from payments_processing.domain.entities.payment import PaymentRequest, PaymentStatus
from payments_processing.domain.values.money import Currency, Money
from payments_processing.presentation.api.payments.validators import reject_float, reject_unsupported_json


class CreatePaymentIn(BaseModel):
    amount: Annotated[
        Decimal,
        BeforeValidator(reject_float),
        Field(gt=0, max_digits=18, decimal_places=2, examples=["100.50"]),
    ]
    currency: Currency
    description: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(reject_unsupported_json)]
    metadata: Annotated[dict[str, Any], AfterValidator(reject_unsupported_json)] = Field(default_factory=dict)
    webhook_url: HttpUrl

    def to_request(self) -> PaymentRequest:
        return PaymentRequest(
            money=Money(self.amount, self.currency),
            description=self.description,
            metadata=self.metadata,
            webhook_url=str(self.webhook_url),
        )


class PaymentAcceptedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(validation_alias="id")
    status: PaymentStatus
    created_at: datetime


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: Decimal = Field(validation_alias=AliasPath("money", "amount"))
    currency: Currency = Field(validation_alias=AliasPath("money", "currency"))
    description: str
    metadata: dict[str, Any]
    status: PaymentStatus
    idempotency_key: str
    webhook_url: str
    created_at: datetime
    processed_at: datetime | None
