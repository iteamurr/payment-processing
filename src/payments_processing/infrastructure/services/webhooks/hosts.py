from __future__ import annotations


def normalize_host(host: str) -> str:
    """One spelling per host for allowlist checks in the api, the consumer and the config: lower case,
    no trailing dot, no IPv6 brackets."""
    return host.strip("[]").rstrip(".").lower()
