from __future__ import annotations

import json
import logging


class JsonFormatter(logging.Formatter):
    """One JSON object per record, with the traceback under exc_info."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


_LIBRARY_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "faststream")
_SENSITIVE_LIBRARY_LOGGERS = ("httpx", "httpcore")


def configure_logging() -> None:
    """Routes all logging, including uvicorn's and FastStream's own loggers, through one JSON handler at INFO."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    for name in _LIBRARY_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    for name in _SENSITIVE_LIBRARY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
