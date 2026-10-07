from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["probes"], default_response_class=PlainTextResponse)


@router.get("/health", operation_id="health")
async def health() -> PlainTextResponse:
    """Process is up; used by the compose healthcheck, no dependency checks."""
    return PlainTextResponse("ok")
