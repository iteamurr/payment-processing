from functools import lru_cache

import httpx
import punq
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.application.payments.payment_creation import PaymentCreation
from payments_processing.application.payments.payment_processing import PaymentProcessing
from payments_processing.domain.services.outbox.event_publisher import EventPublisher
from payments_processing.domain.services.outbox.outbox_repository import OutboxRepository
from payments_processing.domain.services.payments.payment_gateway import PaymentGateway
from payments_processing.domain.services.payments.payment_repository import PaymentRepository
from payments_processing.domain.services.payments.webhook_sender import WebhookSender
from payments_processing.infrastructure.broker.rabbit import build_broker
from payments_processing.infrastructure.services.outbox.rabbit_event_publisher import RabbitEventPublisher
from payments_processing.infrastructure.services.outbox.sql_outbox_repository import SqlOutboxRepository
from payments_processing.infrastructure.services.payments.fake_payment_gateway import FakePaymentGateway
from payments_processing.infrastructure.services.payments.http_webhook_sender import HttpWebhookSender
from payments_processing.infrastructure.services.payments.sql_payment_repository import SqlPaymentRepository
from payments_processing.project.config import Config


@lru_cache(1)
def get_container() -> punq.Container:
    """Cached so the app factory and resolve_depends() share the same container and singletons."""
    return build_container(Config.from_env())


def build_container(config: Config) -> punq.Container:
    """Composition root — wires domain services to infrastructure implementations."""
    container = punq.Container()
    container.register(Config, instance=config)

    engine = create_async_engine(config.database_url, pool_pre_ping=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    container.register(AsyncEngine, instance=engine)
    container.register(PaymentRepository, instance=SqlPaymentRepository(sessions))
    container.register(OutboxRepository, instance=SqlOutboxRepository(sessions))

    container.register(RabbitBroker, instance=build_broker(config.rabbitmq_url, config.consumer_prefetch_count))
    container.register(EventPublisher, RabbitEventPublisher, scope=punq.Scope.singleton)
    container.register(
        OutboxRelay,
        scope=punq.Scope.singleton,
        batch_size=config.outbox_batch_size,
        poll_interval_s=config.outbox_poll_interval_s,
    )
    container.register(PaymentCreation, scope=punq.Scope.singleton)

    container.register(httpx.AsyncClient, instance=httpx.AsyncClient())
    container.register(WebhookSender, HttpWebhookSender, scope=punq.Scope.singleton, timeout_s=config.webhook_timeout_s)
    container.register(PaymentGateway, instance=FakePaymentGateway())
    container.register(PaymentProcessing, scope=punq.Scope.singleton)
    return container
