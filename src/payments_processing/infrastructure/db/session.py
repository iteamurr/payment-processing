from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def build_engine(url: str) -> AsyncEngine:
    """pool_pre_ping drops connections Postgres closed while they sat in the pool."""
    return create_async_engine(url, pool_pre_ping=True)


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """expire_on_commit=False: reading an expired attribute lazy-loads, which raises MissingGreenlet under asyncio."""
    return async_sessionmaker(engine, expire_on_commit=False)
