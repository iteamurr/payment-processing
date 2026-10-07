import unittest

from payments_processing.infrastructure.broker.client import build_broker


class BuildBrokerTest(unittest.TestCase):
    def test_waits_for_in_flight_messages_long_enough_on_shutdown(self):
        """Worst case per message: gateway 5 s + webhook 10 s + retry publish 10 s; Docker allows 30 s."""
        broker = build_broker("amqp://user:password@localhost/", prefetch_count=1)

        self.assertEqual(broker.config.graceful_timeout, 25)
