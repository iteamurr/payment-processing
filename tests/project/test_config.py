import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from payments_processing.project.config import Config

REQUIRED = {
    "DATABASE_URL": "postgresql+asyncpg://payments:secret-pass@db:5432/payments",
    "RABBITMQ_URL": "amqp://guest:guest@rabbitmq:5672/",
}


def config_from(env: dict[str, str]) -> Config:
    with patch.dict(os.environ, env, clear=True):
        return Config.from_env()


class ConfigTest(unittest.TestCase):
    def test_reads_required_variables_and_falls_back_to_defaults(self):
        config = config_from(REQUIRED)

        self.assertEqual(config.database_url, REQUIRED["DATABASE_URL"])
        self.assertEqual(config.rabbitmq_url, REQUIRED["RABBITMQ_URL"])
        self.assertEqual(config.api_key, "")
        self.assertEqual(config.outbox_poll_interval_s, 1.0)
        self.assertEqual(config.outbox_batch_size, 100)
        self.assertEqual(config.webhook_timeout_s, 10.0)
        self.assertEqual(config.consumer_prefetch_count, 10)

    def test_api_key_is_read_when_set(self):
        """Optional here: only the api needs it, and its container refuses to build without it."""
        self.assertEqual(config_from(REQUIRED | {"API_KEY": "secret-key"}).api_key, "secret-key")

    def test_missing_or_empty_required_variable_fails_naming_it(self):
        for name in REQUIRED:
            for env in ({k: v for k, v in REQUIRED.items() if k != name}, REQUIRED | {name: ""}):
                with self.subTest(name=name, env=env), self.assertRaisesRegex(ValidationError, name.lower()):
                    config_from(env)

    def test_overrides_are_parsed_to_the_field_types(self):
        config = config_from(REQUIRED | {"OUTBOX_POLL_INTERVAL_S": "0.5", "OUTBOX_BATCH_SIZE": "10"})

        self.assertEqual(config.outbox_poll_interval_s, 0.5)
        self.assertEqual(config.outbox_batch_size, 10)
        self.assertIsInstance(config.outbox_batch_size, int)

    def test_malformed_number_fails_at_startup(self):
        with self.assertRaisesRegex(ValidationError, "outbox_batch_size"):
            config_from(REQUIRED | {"OUTBOX_BATCH_SIZE": "lots"})

    def test_non_positive_operational_numbers_fail_at_startup(self):
        for name in (
            "OUTBOX_POLL_INTERVAL_S",
            "OUTBOX_BATCH_SIZE",
            "WEBHOOK_TIMEOUT_S",
            "CONSUMER_PREFETCH_COUNT",
        ):
            for value in ("0", "-1"):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValidationError, name.lower()):
                    config_from(REQUIRED | {name: value})

    def test_non_finite_operational_numbers_fail_at_startup(self):
        for name in ("OUTBOX_POLL_INTERVAL_S", "WEBHOOK_TIMEOUT_S"):
            for value in ("nan", "inf", "-inf"):
                with self.subTest(name=name, value=value), self.assertRaisesRegex(ValidationError, name.lower()):
                    config_from(REQUIRED | {name: value})

    def test_webhook_timeout_must_fit_the_consumer_shutdown_budget(self):
        with self.assertRaisesRegex(ValidationError, "webhook_timeout_s"):
            config_from(REQUIRED | {"WEBHOOK_TIMEOUT_S": "10.1"})

    def test_secrets_are_not_leaked_in_repr(self):
        config = config_from(REQUIRED | {"API_KEY": "secret-key"})

        self.assertNotIn("secret-key", repr(config))
        self.assertNotIn("secret-pass", repr(config))

    def test_webhook_allowed_hosts_are_a_comma_separated_list(self):
        self.assertEqual(config_from(REQUIRED).webhook_allowed_hosts, frozenset())
        config = config_from(REQUIRED | {"WEBHOOK_ALLOWED_HOSTS": "webhook-echo, hooks.internal"})
        self.assertEqual(config.webhook_allowed_hosts, frozenset({"webhook-echo", "hooks.internal"}))

    def test_webhook_allowed_hosts_are_normalized(self):
        config = config_from(REQUIRED | {"WEBHOOK_ALLOWED_HOSTS": "Webhook-Echo., [::1]"})
        self.assertEqual(config.webhook_allowed_hosts, frozenset({"webhook-echo", "::1"}))
