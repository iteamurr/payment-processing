import asyncio
import random
import unittest
from unittest.mock import AsyncMock, Mock, patch

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from tests.mocks import payment_request


class FakePaymentGatewayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rng = Mock(spec=random.Random)
        self.rng.uniform.return_value = 3.5
        self.payment = Payment.build(payment_request(), "key-1")

    async def charge(self, roll: float) -> PaymentStatus:
        self.rng.random.return_value = roll
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            status = await FakePaymentGateway(rng=self.rng).charge(self.payment)
        self.sleep = sleep
        return status

    async def test_waits_a_random_two_to_five_seconds(self):
        await self.charge(0.0)

        self.rng.uniform.assert_called_once_with(2.0, 5.0)
        self.sleep.assert_awaited_once_with(3.5)

    async def test_roll_below_success_rate_succeeds(self):
        self.assertIs(await self.charge(0.89), PaymentStatus.SUCCEEDED)

    async def test_roll_at_or_above_success_rate_fails(self):
        self.assertIs(await self.charge(0.9), PaymentStatus.FAILED)

    def instant_gateway(self, *rolls: float, max_remembered: int = 10_000) -> FakePaymentGateway:
        self.rng.uniform.return_value = 0
        self.rng.random.side_effect = list(rolls)
        return FakePaymentGateway(rng=self.rng, max_remembered=max_remembered)

    async def test_repeated_charge_of_a_payment_returns_the_first_result_without_charging_again(self):
        """A duplicate delivery of payments.new must not charge twice: the gateway is idempotent per payment.id."""
        gateway = self.instant_gateway(0.0, 0.99)

        first = await gateway.charge(self.payment)
        second = await gateway.charge(self.payment)

        self.assertIs(first, PaymentStatus.SUCCEEDED)
        self.assertIs(second, PaymentStatus.SUCCEEDED)
        self.rng.random.assert_called_once()

    async def test_concurrent_charges_of_a_payment_share_one_charge(self):
        gateway = self.instant_gateway(0.0, 0.99, 0.0, 0.99, 0.99)

        results = await asyncio.gather(*(gateway.charge(self.payment) for _ in range(5)))

        self.assertEqual(results, [PaymentStatus.SUCCEEDED] * 5)
        self.rng.random.assert_called_once()

    async def test_different_payments_are_charged_independently(self):
        gateway = self.instant_gateway(0.0, 0.99)
        other = Payment.build(payment_request(), "key-2")

        self.assertIs(await gateway.charge(self.payment), PaymentStatus.SUCCEEDED)
        self.assertIs(await gateway.charge(other), PaymentStatus.FAILED)

    async def test_remembers_only_the_most_recent_charges(self):
        """Bounded memory in a long-running consumer; a forgotten payment is long past pending anyway."""
        gateway = self.instant_gateway(0.0, 0.0, 0.0, 0.99, max_remembered=2)
        first, second, third = (Payment.build(payment_request(), f"key-{i}") for i in range(3))

        for payment in (first, second, third):
            self.assertIs(await gateway.charge(payment), PaymentStatus.SUCCEEDED)

        self.assertIs(await gateway.charge(third), PaymentStatus.SUCCEEDED)
        self.assertIs(await gateway.charge(first), PaymentStatus.FAILED)
