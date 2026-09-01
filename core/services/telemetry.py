"""Validated telemetry envelope and bounded batching primitives.

The batcher is deliberately transport-agnostic. A production worker can send
batches to PostgreSQL/TimescaleDB after authentication and tenant checks.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class TelemetryEvent:
    event_id: UUID
    organization_id: UUID
    event_time: datetime
    source: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    @classmethod
    def create(cls, organization_id: str | UUID, *, source: str, kind: str, payload: dict[str, Any] | None = None, request_id: str | None = None) -> "TelemetryEvent":
        org = UUID(str(organization_id))
        if not source or len(source) > 80 or not kind or len(kind) > 120:
            raise ValueError("source and kind are required and bounded")
        data = payload or {}
        if len(data) > 64 or len(repr(data).encode("utf-8")) > 32_768:
            raise ValueError("telemetry payload is too large")
        return cls(uuid4(), org, datetime.now(timezone.utc), source, kind, data, request_id[:128] if request_id else None)

    def as_record(self) -> dict[str, Any]:
        return {"event_id": str(self.event_id), "organization_id": str(self.organization_id), "event_time": self.event_time.isoformat(), "source": self.source, "kind": self.kind, "payload": self.payload, "request_id": self.request_id}


class TelemetryBatcher:
    def __init__(self, *, max_queue: int = 10_000, max_batch: int = 500) -> None:
        if max_queue < 1 or max_batch < 1 or max_batch > max_queue:
            raise ValueError("invalid batch limits")
        self.max_queue = max_queue
        self.max_batch = max_batch
        self._queue: list[TelemetryEvent] = []
        self._lock = Lock()
        self.dropped = 0

    def enqueue(self, event: TelemetryEvent) -> bool:
        with self._lock:
            if len(self._queue) >= self.max_queue:
                self.dropped += 1
                return False
            self._queue.append(event)
            return True

    def flush(self) -> list[TelemetryEvent]:
        with self._lock:
            batch = self._queue[: self.max_batch]
            del self._queue[: len(batch)]
            return batch

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)
