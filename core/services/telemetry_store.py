"""SQLite reference store for local tests; production can swap in the TimescaleDB migration."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from core.services.telemetry import TelemetryEvent


class TelemetryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS telemetry_events (event_id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, event_time TEXT NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL, request_id TEXT, payload TEXT NOT NULL, UNIQUE(organization_id, request_id))")
            db.execute("CREATE INDEX IF NOT EXISTS telemetry_org_time_idx ON telemetry_events (organization_id, event_time DESC)")
            db.commit()

    def ingest(self, events: Iterable[TelemetryEvent]) -> int:
        rows = [(str(e.event_id), str(e.organization_id), e.event_time.isoformat(), e.source, e.kind, e.request_id, json.dumps(e.payload, ensure_ascii=False, separators=(",", ":"))) for e in events]
        with sqlite3.connect(self.path) as db:
            before = db.total_changes
            db.executemany("INSERT OR IGNORE INTO telemetry_events(event_id, organization_id, event_time, source, kind, request_id, payload) VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
            db.commit()
            return db.total_changes - before

    def count(self, organization_id: str) -> int:
        with sqlite3.connect(self.path) as db:
            return int(db.execute("SELECT COUNT(*) FROM telemetry_events WHERE organization_id = ?", (organization_id,)).fetchone()[0])
