import unittest
from unittest.mock import patch

from payments_processing.infrastructure.db.session import build_engine, ping
from tests.live_services import DATABASE_URL, requires_database


class BuildEngineTest(unittest.TestCase):
    @patch("payments_processing.infrastructure.db.session.create_async_engine")
    def test_bounds_pool_waits_connections_and_commands(self, create_async_engine):
        build_engine("postgresql+asyncpg://localhost/payments", timeout_s=2.5)

        create_async_engine.assert_called_once_with(
            "postgresql+asyncpg://localhost/payments",
            pool_pre_ping=True,
            pool_timeout=2.5,
            connect_args={"timeout": 2.5, "command_timeout": 2.5},
        )


class PingTest(unittest.IsolatedAsyncioTestCase):
    async def test_unreachable_postgres_fails_within_the_timeout(self):
        engine = build_engine("postgresql+asyncpg://payments:payments@127.0.0.1:1/payments")
        self.addAsyncCleanup(engine.dispose)

        with self.assertRaises((OSError, TimeoutError)):
            await ping(engine, timeout_s=2)

    @requires_database
    async def test_reachable_postgres_answers(self):
        engine = build_engine(DATABASE_URL)
        self.addAsyncCleanup(engine.dispose)

        await ping(engine)
