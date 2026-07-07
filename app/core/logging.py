"""Structured JSON logging.

Each record is serialized as a single JSON object. Fields passed via
``logger.info(..., extra={...})`` are merged into the object.
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime

# Set by RequestContextMiddleware; read by log formatter and error envelope.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_RESERVED_ATTRS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "taskName",
    "message",
    "asctime",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id is not None:
            line.setdefault("request_id", request_id)
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                line[key] = value
        if record.exc_info:
            line["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
