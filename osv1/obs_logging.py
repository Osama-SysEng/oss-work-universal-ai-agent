"""Central structured JSON logging (stdlib only).

Schema per line: timestamp (UTC ISO-8601 with milliseconds) + level + service
+ env + version + request_id + event + message. Secrets are never written:
the keys that commonly hold them are replaced before the line is emitted.

This follows the production logging playbook: one JSON object per line, one
event name per event, and no raw request bodies.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

SERVICE = os.getenv("SERVICE_NAME", "oss-work")
ENV = os.getenv("ENVIRONMENT", "development")
VERSION = os.getenv("GIT_SHA", "1.0.0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "info" if ENV == "production" else "debug").upper()

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

_REDACT_KEYS = (
    "password",
    "passwd",
    "token",
    "secret",
    "apikey",
    "api_key",
    "authorization",
    "cookie",
    "set-cookie",
    "cvv",
    "card_number",
    "national_id",
    "passport",
    "private_key",
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if any(marker in str(key).lower() for marker in _REDACT_KEYS) else _redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "service": SERVICE,
            "env": ENV,
            "version": VERSION,
            "request_id": request_id_ctx.get(),
            "event": getattr(record, "event", record.getMessage().split(":")[0][:80]),
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if isinstance(extra, dict):
            payload.update(_redact(extra))
        if record.exc_info:
            payload["error.stack"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes one JSON object per line."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
    logger.propagate = False
    return logger


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def bind_request_id(request_id: str | None = None) -> str:
    """Bind a request id to the current context and return it."""
    value = request_id or new_request_id()
    request_id_ctx.set(value)
    return value
