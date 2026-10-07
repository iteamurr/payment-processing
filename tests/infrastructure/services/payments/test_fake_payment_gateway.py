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
