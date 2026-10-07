import asyncio
import unittest
import uuid
from unittest.mock import AsyncMock, patch

from payments_processing.domain.entities.payment import Payment, PaymentStatus
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from tests.mocks import payment_request


class FakePaymentGatewayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.payment = Payment.build(payment_request(), "key-1")
        self.payment.id = uuid.UUID(int=1)

    async def test_waits_between_two_and_five_seconds(self):
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            await FakePaymentGateway().charge(self.payment)

        assert sleep.await_args is not None
        delay = sleep.await_args.args[0]
        self.assertGreaterEqual(delay, 2.0)
        self.assertLess(delay, 5.0)

    async def test_success_rate_boundaries(self):
        with patch("asyncio.sleep", new_callable=AsyncMock):
            self.assertIs(await FakePaymentGateway(success_rate=1.0).charge(self.payment), PaymentStatus.SUCCEEDED)
            self.assertIs(await FakePaymentGateway(success_rate=0.0).charge(self.payment), PaymentStatus.FAILED)

    async def test_separate_gateway_instances_return_the_same_result_and_delay(self):
        """Consumer replicas and restarted consumers must agree without sharing an in-memory cache."""
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            first = await FakePaymentGateway().charge(self.payment)
            second = await FakePaymentGateway().charge(self.payment)

        self.assertIs(second, first)
        self.assertEqual(sleep.await_args_list[0].args, sleep.await_args_list[1].args)

    async def test_repeated_and_concurrent_deliveries_return_the_same_result(self):
        gateway = FakePaymentGateway(min_delay_s=0, max_delay_s=0)

        results = await asyncio.gather(*(gateway.charge(self.payment) for _ in range(5)))

        self.assertEqual(results, [results[0]] * 5)

    async def test_different_payments_get_independent_deterministic_values(self):
        other = Payment.build(payment_request(), "key-2")
        other.id = uuid.UUID(int=2)
        with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
            await FakePaymentGateway().charge(self.payment)
            await FakePaymentGateway().charge(other)

        self.assertNotEqual(sleep.await_args_list[0].args, sleep.await_args_list[1].args)
