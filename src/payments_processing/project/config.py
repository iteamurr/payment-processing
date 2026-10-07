from __future__ import annotations

from typing import Annotated, Any, Self

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from payments_processing.domain.webhooks import normalize_host


class Config(BaseSettings):
    """Process settings from env vars named after the fields; an empty variable counts as unset."""

    model_config = SettingsConfigDict(frozen=True, env_ignore_empty=True, allow_inf_nan=False)

    database_url: str = Field(repr=False)
    rabbitmq_url: str = Field(repr=False)
    api_key: str = Field(default="", repr=False)
    webhook_secret: str = Field(default="", repr=False)
    outbox_poll_interval_s: Annotated[float, Field(gt=0)] = 1.0
    outbox_batch_size: Annotated[int, Field(gt=0)] = 100
    webhook_timeout_s: Annotated[float, Field(gt=0)] = 10.0
    webhook_allowed_hosts: Annotated[frozenset[str], NoDecode] = frozenset()
    consumer_prefetch_count: Annotated[int, Field(gt=0)] = 10

    @field_validator("webhook_allowed_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: Any) -> Any:
        """Comma-separated in the environment (WEBHOOK_ALLOWED_HOSTS=webhook-echo,hooks.internal), normalized."""
        hosts = value.split(",") if isinstance(value, str) else value
        return frozenset(normalize_host(host.strip()) for host in hosts if host.strip())

    @classmethod
    def from_env(cls) -> Self:
        """The required fields come from the environment, which pyright cannot see in the constructor call."""
        return cls()  # pyright: ignore[reportCallIssue]
