from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from payments_processing.presentation.api.deps import resolve_depends
from payments_processing.project.config import Config


def require_api_key(
    x_api_key: str | None = Header(default=None),
    config: Config = resolve_depends(Config),
) -> None:
    """Constant-time comparison of X-API-Key with the configured static key."""
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), config.api_key.encode()):
        raise HTTPException(status_code=401, detail="invalid api key")
