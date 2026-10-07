from __future__ import annotations

import os
import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import text

from payments_processing.infrastructure.db.session import build_engine, build_sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "")
requires_database = unittest.skipUnless(DATABASE_URL, "DATABASE_URL is not set")
requires_rabbitmq = unittest.skipUnless(RABBITMQ_URL, "RABBITMQ_URL is not set")


def migrate() -> None:
    """Runs outside the test loop: env.py calls asyncio.run()."""
    command.upgrade(AlembicConfig(str(Path(__file__).parents[1] / "alembic.ini")), "head")


@requires_database
class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    """Real Postgres from docker compose; tables are emptied before every test."""

    @classmethod
    def setUpClass(cls):
        migrate()

    async def asyncSetUp(self):
        self.engine = build_engine(DATABASE_URL)
        self.addAsyncCleanup(self.engine.dispose)
        async with self.engine.begin() as connection:
            await connection.execute(text("TRUNCATE payments, outbox"))
        self.sessions = build_sessionmaker(self.engine)
