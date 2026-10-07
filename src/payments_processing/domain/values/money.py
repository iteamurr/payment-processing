from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from payments_processing.domain.errors import InvalidAmountError

_CENT = Decimal("0.01")


class Currency(StrEnum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


@dataclass(slots=True, frozen=True)
class Money:
    """Positive amount in major units, normalized to cents; all supported currencies have 2 decimal places."""

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not self.amount.is_finite() or self.amount <= 0:
            raise InvalidAmountError(f"amount must be positive, got {self.amount}")
        cents = self.amount.quantize(_CENT)
        if cents != self.amount:
            raise InvalidAmountError(f"amount has more than 2 decimal places: {self.amount}")
        object.__setattr__(self, "amount", cents)
