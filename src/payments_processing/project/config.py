import os
from collections.abc import Callable
from dataclasses import MISSING, dataclass, field, fields
from typing import Any, Self, cast


@dataclass(slots=True, frozen=True)
class Config:
    """Process settings; each field is read from the upper-cased env var of the same name."""

    database_url: str = field(repr=False)
    rabbitmq_url: str = field(repr=False)
    api_key: str = field(default="", repr=False)
    outbox_poll_interval_s: float = 1.0
    outbox_batch_size: int = 100
    webhook_timeout_s: float = 10.0
    consumer_prefetch_count: int = 10

    @classmethod
    def from_env(cls) -> Self:
        """Builds Config from env vars named after the fields, falling back to field defaults.

        Values are parsed by calling the field annotation, so this module must not use
        `from __future__ import annotations`."""
        values: dict[str, Any] = {}
        for f in fields(cls):
            name = f.name.upper()
            if os.environ.get(name):
                parse = cast(Callable[[str], Any], f.type)
                values[f.name] = parse(os.environ[name])
            elif f.default is MISSING:
                raise RuntimeError(f"required environment variable {name} is not set or empty")
        return cls(**values)
