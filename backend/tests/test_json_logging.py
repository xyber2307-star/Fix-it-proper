"""Unit tests for JSON logging. No loop needed."""

import json
import logging
from typing import Any

from app.json_logging import JsonFormatter, get_request_id, request_id_var, setup_logging


def _record(**extra: Any) -> logging.LogRecord:
    logger = logging.getLogger("fixitproper.test")
    return logger.makeRecord(logger.name, logging.INFO, __file__, 1, "hello", (), None, None, extra)


def test_formatter_includes_request_id_and_extras():
    token = request_id_var.set("req-1")
    try:
        assert get_request_id() == "req-1"
        payload = json.loads(
            JsonFormatter().format(_record(method="POST", path="/api/analyze", status=200))
        )
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-1"
    assert payload["method"] == "POST"
    assert payload["path"] == "/api/analyze"
    assert payload["status"] == 200
    assert payload["level"] == "INFO"
    assert "timestamp" in payload


def test_formatter_defaults_request_id_outside_request():
    assert get_request_id() == "-"
    payload = json.loads(JsonFormatter().format(_record()))
    assert payload["request_id"] == "-"


def test_setup_logging_is_idempotent():
    setup_logging("WARNING")
    root = logging.getLogger()
    before = sum(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
    setup_logging("WARNING")
    after = sum(isinstance(h.formatter, JsonFormatter) for h in root.handlers)
    assert before >= 1
    assert after == before
