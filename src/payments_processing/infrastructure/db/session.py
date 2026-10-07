from __future__ import annotations

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(url: str) -> AsyncEngine:
    """pool_pre_ping drops connections Postgres closed while they sat in the pool."""
    return create_async_engine(url, pool_pre_ping=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """expire_on_commit=False: reading an expired attribute lazy-loads, which raises MissingGreenlet under asyncio."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def ping(engine: AsyncEngine, timeout_s: float = 2.0) -> None:
    """Raises if Postgres does not answer SELECT 1 within the timeout."""
    async with asyncio.timeout(timeout_s):
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
