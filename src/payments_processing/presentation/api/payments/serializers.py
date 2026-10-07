from __future__ import annotations

import ipaddress
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, cast

from pydantic import AfterValidator, AliasPath, BaseModel, BeforeValidator, ConfigDict, Field, HttpUrl

from payments_processing.domain.entities.payment import PaymentRequest, PaymentStatus
from payments_processing.domain.values.money import Currency, Money


def _reject_float(value: Any) -> Any:
    """json.loads turns fractional numbers into float, which silently rounds past ~15 significant digits."""
    if isinstance(value, float):
        raise ValueError("amount must be a string or an integer")
    return value


def _reject_nul[T](value: T) -> T:
    """Postgres TEXT and JSONB cannot store U+0000."""
    if _contains_nul(value):
        raise ValueError("NUL character is not allowed")
    return value


def _contains_nul(value: object) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_contains_nul(k) or _contains_nul(v) for k, v in cast(dict[object, object], value).items())
    if isinstance(value, list):
        return any(_contains_nul(item) for item in cast(list[object], value))
    return False


def _reject_internal_host(url: HttpUrl) -> HttpUrl:
    """Refuses obviously internal targets before anything is charged; the consumer checks the resolved address."""
    host = (url.host or "").strip("[]").lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise ValueError("webhook_url must not point to localhost")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not address.is_global:
        raise ValueError("webhook_url must not point to a non-public address")
    return url


class CreatePaymentIn(BaseModel):
    amount: Annotated[
        Decimal,
        BeforeValidator(_reject_float),
        Field(gt=0, max_digits=18, decimal_places=2, examples=["100.50"]),
    ]
    currency: Currency
    description: Annotated[str, Field(min_length=1, max_length=1000), AfterValidator(_reject_nul)]
    metadata: Annotated[dict[str, Any], AfterValidator(_reject_nul)] = Field(default_factory=dict)
    webhook_url: Annotated[HttpUrl, AfterValidator(_reject_internal_host)]

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
