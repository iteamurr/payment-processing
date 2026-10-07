from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from faststream.rabbit import RabbitBroker
from sqlalchemy.ext.asyncio import AsyncEngine

from payments_processing.application.outbox.outbox_relay import OutboxRelay
from payments_processing.presentation.api.body_limit import BodySizeLimit
from payments_processing.presentation.api.common.errors import request_validation_error
from payments_processing.presentation.api.payments.methods import router as payments_router
from payments_processing.presentation.api.probes.methods import router as probes_router
from payments_processing.project.container import get_api_container
from payments_processing.project.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Runs the outbox relay for the app's lifetime; the broker connection is the relay's concern, not startup's."""
    configure_logging()
    container = get_api_container()
    relay = asyncio.create_task(container.resolve(OutboxRelay).run())
    try:
        yield
    finally:
        relay.cancel()
        try:
            with suppress(asyncio.CancelledError):
                await relay
        finally:
            try:
                await container.resolve(RabbitBroker).stop()
            finally:
                await container.resolve(AsyncEngine).dispose()


def build_app() -> FastAPI:
    app = FastAPI(title="payments-processing", lifespan=lifespan)
    app.add_exception_handler(RequestValidationError, request_validation_error)  # pyright: ignore[reportArgumentType]
    app.add_middleware(BodySizeLimit)
    app.include_router(probes_router)
    app.include_router(payments_router)
    return app
