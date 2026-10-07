from __future__ import annotations

import ipaddress
import math
from collections.abc import Set
from typing import Any, cast

from fastapi.exceptions import RequestValidationError
from pydantic import HttpUrl

from payments_processing.domain.webhooks import normalize_host


def reject_float(value: Any) -> Any:
    """json.loads turns fractional numbers into float, which silently rounds past ~15 significant digits."""
    if isinstance(value, float):
        raise ValueError("amount must be a string or an integer")
    return value


def reject_unsupported_json[T](value: T) -> T:
    """Reject values that PostgreSQL TEXT or JSONB cannot store before they reach the database."""
    _validate_json_value(value)
    return value


def _validate_json_value(value: object) -> None:
    if isinstance(value, str):
        if "\x00" in value:
            raise ValueError("NUL character is not allowed")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("numbers must be finite")
        return
    if isinstance(value, dict):
        for key, item in cast(dict[object, object], value).items():
            _validate_json_value(key)
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in cast(list[object], value):
            _validate_json_value(item)


def ensure_webhook_host_allowed(url: HttpUrl, allowed_hosts: Set[str]) -> None:
    """Raises a body validation error for an obviously internal webhook target."""
    if _is_internal_host(url, allowed_hosts):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("body", "webhook_url"),
                    "msg": "webhook_url must not point to an internal address",
                    "input": str(url),
                }
            ]
        )


def _is_internal_host(url: HttpUrl, allowed_hosts: Set[str]) -> bool:
    """Localhost names and non-public IP literals, unless allowed; the consumer also checks resolved addresses."""
    host = normalize_host(url.host or "")
    if host in allowed_hosts:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    try:
        return not ipaddress.ip_address(host).is_global
    except ValueError:
        return False
