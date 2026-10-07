import json
import logging
import sys
import unittest

from payments_processing.project.logging import JsonFormatter


class JsonFormatterTest(unittest.TestCase):
    def test_formats_record_as_one_json_object(self):
        record = logging.LogRecord("payments", logging.INFO, __file__, 1, "paid %s", ("p1",), None)

        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["logger"], "payments")
        self.assertEqual(payload["message"], "paid p1")
        self.assertIn("time", payload)

    def test_includes_traceback_under_exc_info(self):
        try:
            raise ValueError("boom")
        except ValueError:
            record = logging.LogRecord("payments", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())

        payload = json.loads(JsonFormatter().format(record))

        self.assertIn("ValueError: boom", payload["exc_info"])
