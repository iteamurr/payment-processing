from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from payments_processing.infrastructure.db.session import ping
from payments_processing.presentation.api.deps import resolve_depends

router = APIRouter(tags=["probes"], default_response_class=PlainTextResponse)


@router.get("/health", operation_id="health")
async def health() -> PlainTextResponse:
    """Liveness only, no dependency checks."""
    return PlainTextResponse("ok")


@router.get("/ready", operation_id="ready", responses={503: {"description": "Postgres is unreachable"}})
async def ready(engine: AsyncEngine = resolve_depends(AsyncEngine)) -> PlainTextResponse:
    """Ready while Postgres answers. RabbitMQ is not checked: the outbox accepts payments while it is down."""
    try:
        await ping(engine)
    except (OSError, TimeoutError, SQLAlchemyError):
        return PlainTextResponse("postgres unavailable", status_code=503)
    return PlainTextResponse("ok")
