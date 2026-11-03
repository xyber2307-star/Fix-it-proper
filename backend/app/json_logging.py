"""Structured JSON logging with request_id. Never log bodies or secrets."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from app.brand import SLUG

request_id_var: ContextVar[str] = ContextVar(f"{SLUG}_request_id", default="-")

_EXTRA_KEYS = ("method", "path", "status", "duration_ms", "client_ip", "url_host", "reason")


def get_request_id() -> str:
    """Return the request id for the current request, or '-' outside one."""
    return request_id_var.get()


class JsonFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for key in _EXTRA_KEYS:
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["error"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging(level: str) -> None:
    """Install the JSON stdout handler once. Safe to call per app instance."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler.formatter, JsonFormatter):
            root.setLevel(level)
            return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True
