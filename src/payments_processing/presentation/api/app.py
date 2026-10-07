from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.infrastructure.broker.rabbit import declare_topology
from payments_processing.presentation.api.payments.methods import router as payments_router
from payments_processing.presentation.api.probes.methods import router as probes_router
from payments_processing.project.container import get_container
from payments_processing.project.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Declares the broker topology and runs the outbox relay for the app's lifetime."""
    configure_logging()
    container = get_container()
    broker = container.resolve(RabbitBroker)
    await broker.connect()
    await declare_topology(broker)
    relay = asyncio.create_task(container.resolve(OutboxRelay).run())
    yield
    relay.cancel()
    with suppress(asyncio.CancelledError):
        await relay
    await broker.stop()
    await container.resolve(AsyncEngine).dispose()


def build_app() -> FastAPI:
    app = FastAPI(title="payments-processing", lifespan=lifespan)
    app.include_router(probes_router)
    app.include_router(payments_router)
    return app
