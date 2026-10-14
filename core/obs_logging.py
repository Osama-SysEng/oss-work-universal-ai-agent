"""Central structured JSON logging (stdlib only).

Schema per line: timestamp (UTC ISO-8601 ms) + level + service + env + version
+ request_id + event + message. Never log secrets (see REDACTED markers).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

SERVICE = os.getenv("SERVICE_NAME", "oss-work")
ENV = os.getenv("ENVIRONMENT", "development")
VERSION = os.getenv("GIT_SHA", "dev")
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
)


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ("***" if any(s in k.lower() for s in _REDACT_KEYS) else _redact(v)) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_redact(v) for v in obj]
    return obj


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
