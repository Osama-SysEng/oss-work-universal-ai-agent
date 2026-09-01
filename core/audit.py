"""Structured audit events with no secret or payload logging."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditEvent:
    event: str
    actor: str
    target: str
    outcome: str
    timestamp: str
    request_id: str | None = None
    details: dict[str, Any] | None = None


class AuditLogger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.logger = logging.getLogger("oss_work.audit")

    def record(self, event: str, *, actor: str, target: str, outcome: str, request_id: str | None = None, details: dict[str, Any] | None = None) -> AuditEvent:
        safe_details = {k: v for k, v in (details or {}).items() if k.lower() not in {"token", "secret", "password", "api_key", "authorization", "content"}}
        item = AuditEvent(event, actor, target, outcome, datetime.now(timezone.utc).isoformat(), request_id, safe_details)
        line = json.dumps(asdict(item), ensure_ascii=False, sort_keys=True)
        self.logger.info(line)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        return item
