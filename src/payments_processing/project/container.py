from functools import lru_cache

import httpx
import punq
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_lookup import PaymentLookup
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.services.webhooks.webhook_sender import WebhookSender
from payments_processing.infrastructure.broker.client import build_broker
from payments_processing.infrastructure.db.session import build_engine, build_sessionmaker
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import RabbitEventPublisher
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from payments_processing.infrastructure.services.payments.sql_payment_repository import SqlPaymentRepository
from payments_processing.infrastructure.services.webhooks.http_webhook_sender import HttpWebhookSender
from payments_processing.presentation.consumer.handler import PaymentCreatedHandler
from payments_processing.project.config import Config


@lru_cache(1)
def get_api_container() -> punq.Container:
    """Cached so the app factory and resolve_depends() share the same container and singletons."""
    return build_api_container(Config.from_env())


@lru_cache(1)
def get_consumer_container() -> punq.Container:
    return build_consumer_container(Config.from_env())


def build_api_container(config: Config) -> punq.Container:
    """api process: payment creation and lookup over HTTP, plus the outbox relay."""
    if not config.api_key:
        raise RuntimeError("environment variable API_KEY is required by the api")
    container, sessions = _build_shared(config)
    container.register(OutboxRepository, instance=SqlOutboxRepository(sessions))
    container.register(EventPublisher, RabbitEventPublisher, scope=punq.Scope.singleton)
    container.register(
        OutboxRelay,
        scope=punq.Scope.singleton,
        batch_size=config.outbox_batch_size,
        poll_interval_s=config.outbox_poll_interval_s,
    )
    container.register(PaymentCreation, scope=punq.Scope.singleton)
    container.register(PaymentLookup, scope=punq.Scope.singleton)
    return container


def build_consumer_container(config: Config) -> punq.Container:
    """consumer process: charging, status updates, webhooks and retries."""
    container, _ = _build_shared(config)
    container.register(PaymentLookup, scope=punq.Scope.singleton)
    container.register(httpx.AsyncClient, instance=httpx.AsyncClient())
    container.register(WebhookSender, HttpWebhookSender, scope=punq.Scope.singleton, timeout_s=config.webhook_timeout_s)
    container.register(PaymentGateway, instance=FakePaymentGateway())
    container.register(PaymentProcessing, scope=punq.Scope.singleton)
    container.register(PaymentCreatedHandler, scope=punq.Scope.singleton)
    return container


def _build_shared(config: Config) -> tuple[punq.Container, async_sessionmaker[AsyncSession]]:
    """Composition root shared by both processes: config, Postgres and the broker client."""
    container = punq.Container()
    container.register(Config, instance=config)
    engine = build_engine(config.database_url)
    sessions = build_sessionmaker(engine)
    container.register(AsyncEngine, instance=engine)
    container.register(PaymentRepository, instance=SqlPaymentRepository(sessions))
    container.register(RabbitBroker, instance=build_broker(config.rabbitmq_url, config.consumer_prefetch_count))
    return container, sessions
