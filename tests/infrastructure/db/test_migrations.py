import unittest
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig

from tests.live_services import migrate, requires_database


@requires_database
class MigrationsTest(unittest.TestCase):
    """Synchronous on purpose: migrations/env.py runs its own event loop."""

    def test_models_match_the_migrations(self):
        """Autogenerate would otherwise propose dropping what only the migrations declare, e.g. the outbox index."""
        migrate()

        command.check(AlembicConfig(str(Path(__file__).parents[3] / "alembic.ini")))
