import unittest

from payments_processing.infrastructure.broker.retry import ATTEMPT_HEADER, MAX_ATTEMPTS, Attempt
from payments_processing.infrastructure.broker.topology import RETRY_QUEUES


class AttemptTest(unittest.TestCase):
    def test_retry_delays_grow_exponentially_from_five_seconds(self):
        """5 s * 5**n: long enough to ride out a Postgres restart instead of dead-lettering everything in flight."""
        delays = [queue.arguments["x-message-ttl"] for queue in RETRY_QUEUES]

        self.assertEqual(delays, [5_000, 25_000])
        self.assertEqual([queue.name for queue in RETRY_QUEUES], ["payments.new.retry.1", "payments.new.retry.2"])
        self.assertIs(Attempt(1).retry_queue(), RETRY_QUEUES[0])
        self.assertIs(Attempt(2).retry_queue(), RETRY_QUEUES[1])

    def test_last_attempt_has_no_retry_queue(self):
        self.assertIsNone(Attempt(MAX_ATTEMPTS).retry_queue())
        self.assertIsNone(Attempt(MAX_ATTEMPTS + 1).retry_queue())

    def test_every_attempt_before_the_last_has_its_own_retry_queue(self):
        for number in range(1, MAX_ATTEMPTS):
            with self.subTest(number=number):
                self.assertIs(Attempt(number).retry_queue(), RETRY_QUEUES[number - 1])

    def test_number_below_one_is_rejected(self):
        for number in (0, -1):
            with self.subTest(number=number), self.assertRaises(ValueError):
                Attempt(number)

    def test_from_headers_defaults_to_the_first_attempt(self):
        self.assertEqual(Attempt.from_headers({}), Attempt(1))
        self.assertEqual(Attempt.from_headers({ATTEMPT_HEADER: 2}), Attempt(2))
        self.assertEqual(Attempt.from_headers({ATTEMPT_HEADER: "3"}), Attempt(3))

    def test_from_headers_rejects_a_malformed_header(self):
        for value in ("abc", None, 0):
            with self.subTest(value=value), self.assertRaises((TypeError, ValueError)):
                Attempt.from_headers({ATTEMPT_HEADER: value})

    def test_next_headers_keep_the_rest_and_count_the_next_attempt(self):
        headers = Attempt(1).next_headers({"trace": "t1", ATTEMPT_HEADER: 1})

        self.assertEqual(headers, {"trace": "t1", ATTEMPT_HEADER: 2})
