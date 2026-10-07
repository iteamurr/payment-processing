import unittest
from decimal import Decimal

from payments_processing.domain.errors import InvalidAmountError
from payments_processing.domain.values.money import Currency, Money


class MoneyTest(unittest.TestCase):
    def test_amount_is_normalized_to_cents(self):
        for raw in ("100", "100.5", "100.50", "100.500"):
            with self.subTest(raw=raw):
                self.assertEqual(str(Money(Decimal(raw), Currency.RUB).amount), "100.00" if raw == "100" else "100.50")

    def test_equal_amounts_written_differently_are_equal(self):
        self.assertEqual(Money(Decimal("7.5"), Currency.EUR), Money(Decimal("7.50"), Currency.EUR))
        self.assertNotEqual(Money(Decimal("7.50"), Currency.EUR), Money(Decimal("7.50"), Currency.USD))

    def test_invalid_amount_raises(self):
        for raw in ("0", "-1", "0.001", "1.005", "NaN", "Infinity"):
            with self.subTest(raw=raw), self.assertRaises(InvalidAmountError):
                Money(Decimal(raw), Currency.RUB)

    def test_is_immutable(self):
        money = Money(Decimal("1"), Currency.RUB)

        with self.assertRaises(AttributeError):
            money.amount = Decimal("2")  # type: ignore[misc]
