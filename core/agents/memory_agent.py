"""Bounded local memory store using SQLite and parameterized statements."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.config import DATA_DIR
from core.contracts import TaskResult


class MemoryAgent(BaseAgent):
    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("memory_write", "memory_read", "memory_search", "memory_delete")

    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("memory", name="MemoryAgent", description=description, context=context, **kwargs)
        self.db_path = Path(self.context.get("db_path", DATA_DIR / "memory.sqlite3")).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS memories (id INTEGER PRIMARY KEY, user_id TEXT NOT NULL, memory_key TEXT NOT NULL, value TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, memory_key))")
            db.commit()

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        task = str(self.context.get("task", "list"))
        user_id = str(self.context.get("user_id", "local"))
        try:
            with sqlite3.connect(self.db_path) as db:
                if task == "write":
                    key, value = str(self.context.get("key", "")), str(self.context.get("value", ""))
                    if not key or len(key) > 256 or len(value.encode()) > self.policy.max_file_bytes:
                        raise ValueError("invalid memory key or value size")
                    db.execute("INSERT INTO memories(user_id, memory_key, value) VALUES (?, ?, ?) ON CONFLICT(user_id, memory_key) DO UPDATE SET value=excluded.value", (user_id, key, value))
                    db.commit()
                    data = {"key": key, "stored": True}
                elif task == "read":
                    key = str(self.context.get("key", ""))
                    row = db.execute("SELECT memory_key, value, created_at FROM memories WHERE user_id=? AND memory_key=?", (user_id, key)).fetchone()
                    data = {"memory": dict(zip(("key", "value", "created_at"), row)) if row else None}
                elif task == "search":
                    query = f"%{str(self.context.get('query', ''))[:100]}%"
                    rows = db.execute("SELECT memory_key, value, created_at FROM memories WHERE user_id=? AND (memory_key LIKE ? OR value LIKE ?) LIMIT 100", (user_id, query, query)).fetchall()
                    data = {"memories": [dict(zip(("key", "value", "created_at"), row)) for row in rows]}
                elif task == "delete":
                    if not self.context.get("approved", False):
                        data = {"deleted": False, "reason": "approval required"}
                        return self.finalize(TaskResult("denied", data).as_dict(), started)
                    db.execute("DELETE FROM memories WHERE user_id=? AND memory_key=?", (user_id, str(self.context.get("key", ""))))
                    db.commit()
                    data = {"deleted": True}
                else:
                    count = db.execute("SELECT COUNT(*) FROM memories WHERE user_id=?", (user_id,)).fetchone()[0]
                    data = {"count": count}
            return self.finalize(TaskResult("completed", data).as_dict(), started)
        except Exception as exc:
            return self.fail(str(exc), started)
