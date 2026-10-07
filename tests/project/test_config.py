import os
import unittest
from unittest.mock import patch

from payments_processing.project.config import Config

REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://payments:secret-pass@db:5432/payments",
    "RABBITMQ_URL": "amqp://guest:guest@rabbitmq:5672/",
}


class ConfigFromEnvTest(unittest.TestCase):
    def test_reads_required_variables_and_falls_back_to_defaults(self):
        with patch.dict(os.environ, REQUIRED, clear=True):
            config = Config.from_env()

        self.assertEqual(config.database_url, REQUIRED["DATABASE_URL"])
        self.assertEqual(config.rabbitmq_url, REQUIRED["RABBITMQ_URL"])
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.outbox_poll_interval_s, 1.0)
        self.assertEqual(config.outbox_batch_size, 100)
        self.assertEqual(config.webhook_timeout_s, 10.0)
        self.assertEqual(config.consumer_prefetch_count, 10)

    def test_api_key_is_read_when_set(self):
        """Optional here: only the api needs it, and its container refuses to build without it."""
        with patch.dict(os.environ, REQUIRED | {"API_KEY": "secret-key"}, clear=True):
            self.assertEqual(Config.from_env().api_key, "secret-key")

    def test_missing_required_variable_fails_fast_naming_it(self):
        for missing in REQUIRED:
            with self.subTest(missing=missing):
                env = {k: v for k, v in REQUIRED.items() if k != missing}
                with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(RuntimeError, missing):
                    Config.from_env()

    def test_empty_required_variable_fails_fast_naming_it(self):
        for empty in REQUIRED:
            with self.subTest(empty=empty):
                env = REQUIRED | {empty: ""}
                with patch.dict(os.environ, env, clear=True), self.assertRaisesRegex(RuntimeError, empty):
                    Config.from_env()

    def test_overrides_are_parsed_to_the_field_types(self):
        env = {**REQUIRED, "OUTBOX_POLL_INTERVAL_S": "0.5", "OUTBOX_BATCH_SIZE": "10"}
        with patch.dict(os.environ, env, clear=True):
            config = Config.from_env()

        self.assertEqual(config.outbox_poll_interval_s, 0.5)
        self.assertEqual(config.outbox_batch_size, 10)
        self.assertIsInstance(config.outbox_batch_size, int)

    def test_secrets_are_not_leaked_in_repr(self):
        with patch.dict(os.environ, REQUIRED | {"API_KEY": "secret-key"}, clear=True):
            config = Config.from_env()

        self.assertNotIn("secret-key", repr(config))
        self.assertNotIn("secret-pass", repr(config))
