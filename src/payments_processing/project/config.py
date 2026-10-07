import os
from dataclasses import MISSING, dataclass, field, fields
from typing import Self


@dataclass(slots=True, frozen=True)
class Config:
    """Process settings; each field is read from the upper-cased env var of the same name."""

    database_url: str = field(repr=False)
    rabbitmq_url: str = field(repr=False)
    api_key: str = field(repr=False)
    outbox_poll_interval_s: float = 1.0
    outbox_batch_size: int = 100
    webhook_timeout_s: float = 10.0
    consumer_prefetch_count: int = 10

    @classmethod
    def from_env(cls) -> Self:
        """Builds Config from env vars named after the fields, falling back to field defaults."""
        values = {}
        for f in fields(cls):
            name = f.name.upper()
            if name in os.environ:
                values[f.name] = f.type(os.environ[name])
            elif f.default is MISSING:
                raise RuntimeError(f"required environment variable {name} is not set")
        return cls(**values)
