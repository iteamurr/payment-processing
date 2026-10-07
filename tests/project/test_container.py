import unittest

import httpx
import punq

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler
from payments_processing.project.config import Config
from payments_processing.project.container import build_api_container, build_consumer_container

CONFIG = Config(
    database_url="postgresql+asyncpg://payments:payments@localhost/payments",
    rabbitmq_url="amqp://guest:guest@localhost/",
    api_key="secret-key",
)


class ApiContainerTest(unittest.TestCase):
    """Building a container opens no connections, so these run without Postgres or RabbitMQ."""

    def test_resolves_what_the_api_uses(self):
        container = build_api_container(CONFIG)

        for dependency in (OutboxRelay, PaymentCreation, PaymentLookup):
            with self.subTest(dependency=dependency.__name__):
                self.assertIsInstance(container.resolve(dependency), dependency)

    def test_does_not_build_consumer_dependencies(self):
        container = build_api_container(CONFIG)

        for dependency in (PaymentProcessing, PaymentCreatedHandler, httpx.AsyncClient):
            with self.subTest(dependency=dependency.__name__), self.assertRaises(punq.MissingDependencyError):
                container.resolve(dependency)

    def test_refuses_to_build_without_an_api_key(self):
        """An empty key would let a request with an empty X-API-Key header through."""
        with self.assertRaisesRegex(RuntimeError, "API_KEY"):
            build_api_container(Config(database_url=CONFIG.database_url, rabbitmq_url=CONFIG.rabbitmq_url))


class ConsumerContainerTest(unittest.TestCase):
    def test_resolves_the_handler_and_needs_no_api_key(self):
        config = Config(database_url=CONFIG.database_url, rabbitmq_url=CONFIG.rabbitmq_url)

        container = build_consumer_container(config)

        self.assertIsInstance(container.resolve(PaymentCreatedHandler), PaymentCreatedHandler)

    def test_does_not_build_the_relay(self):
        with self.assertRaises(punq.MissingDependencyError):
            build_consumer_container(CONFIG).resolve(OutboxRelay)
