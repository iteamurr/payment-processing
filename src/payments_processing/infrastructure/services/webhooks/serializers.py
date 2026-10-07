from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import AliasPath, BaseModel, ConfigDict, Field

from payments_processing.domain.entities.payment import PaymentStatus
from payments_processing.domain.values.money import Currency


class WebhookPayload(BaseModel):
    """JSON body POSTed to the client's webhook_url."""

    model_config = ConfigDict(from_attributes=True)

    payment_id: uuid.UUID = Field(validation_alias="id")
    status: PaymentStatus
    amount: Decimal = Field(validation_alias=AliasPath("money", "amount"))
    currency: Currency = Field(validation_alias=AliasPath("money", "currency"))
    processed_at: datetime | None
