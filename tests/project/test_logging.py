import json
import logging
import sys
import unittest

from payments_processing.project.logging import JsonFormatter, configure_logging


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


class ConfigureLoggingTest(unittest.TestCase):
    def setUp(self):
        root = logging.getLogger()
        saved = (root.handlers[:], root.level)
        self.addCleanup(lambda: (setattr(root, "handlers", saved[0]), root.setLevel(saved[1])))

    def test_uvicorn_and_faststream_loggers_go_through_the_root_json_handler(self):
        """uvicorn's dictConfig and FastStream's import give these loggers their own plain-text handlers."""
        library_loggers = [
            logging.getLogger(name) for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "faststream")
        ]
        for logger in library_loggers:
            self.addCleanup(setattr, logger, "handlers", logger.handlers[:])
            self.addCleanup(setattr, logger, "propagate", logger.propagate)
            logger.handlers = [logging.StreamHandler()]
            logger.propagate = False

        configure_logging()

        [handler] = logging.getLogger().handlers
        self.assertIsInstance(handler.formatter, JsonFormatter)
        for logger in library_loggers:
            with self.subTest(logger=logger.name):
                self.assertEqual(logger.handlers, [])
                self.assertTrue(logger.propagate)
