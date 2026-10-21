"""The background scheduler for OS_V1.

The specification expects background work: the weekly personalization session
and the practice sessions start by themselves while the device is idle, inside
a budget the user sets.

The scheduler keeps its jobs in a local SQLite file, runs the jobs that are
due, and never lets one failing job stop the rest. The kill switch is checked
before every run, so stopping the system stops the background work too.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    task        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'practice',
    state       TEXT NOT NULL DEFAULT 'scheduled',
    run_at      REAL NOT NULL,
    interval_s  REAL,
    repeat      INTEGER NOT NULL DEFAULT 0,
    runs        INTEGER NOT NULL DEFAULT 0,
    last_result TEXT NOT NULL DEFAULT '',
    last_error  TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id      TEXT NOT NULL,
    task        TEXT NOT NULL,
    status      TEXT NOT NULL,
    detail      TEXT NOT NULL DEFAULT '',
    started_at  TEXT NOT NULL,
    finished_at TEXT NOT NULL
);
"""


@dataclass
class Scheduler:
    """Persistent background jobs over a local SQLite file."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/jobs.db"))
    executor: Callable[[str], dict[str, Any]] | None = None
    stop_flag: threading.Event = field(default_factory=threading.Event)

    # ── plumbing ──────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.commit()
        return connection

    # ── jobs ─────────────────────────────────────────────────

    def submit(
        self,
        task: str,
        *,
        run_at: float | None = None,
        interval_s: float | None = None,
        repeat: bool = False,
        kind: str = "practice",
    ) -> str:
        job_id = f"job-{int(time.time() * 1000):x}"
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO jobs (id, task, kind, state, run_at, interval_s, repeat, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    task,
                    kind,
                    "scheduled",
                    run_at if run_at is not None else time.time(),
                    interval_s,
                    1 if repeat else 0,
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()
        return job_id

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM jobs ORDER BY run_at").fetchall()
        return [dict(row) for row in rows]

    def due_jobs(self, now: float | None = None) -> list[dict[str, Any]]:
        moment = now if now is not None else time.time()
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs WHERE state IN ('scheduled','queued') AND run_at <= ? ORDER BY run_at",
                (moment,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _finish(self, job: dict[str, Any], ok: bool, result: str, error: str) -> None:
        with self._connect() as connection:
            if job["repeat"] and job["interval_s"]:
                connection.execute(
                    "UPDATE jobs SET state='scheduled', run_at=?, runs=runs+1, last_result=?, last_error=? WHERE id=?",
                    (time.time() + float(job["interval_s"]), result[:2000], error[:2000], job["id"]),
                )
            else:
                connection.execute(
                    "UPDATE jobs SET state=?, runs=runs+1, last_result=?, last_error=? WHERE id=?",
                    ("completed" if ok else "failed", result[:2000], error[:2000], job["id"]),
                )
            connection.execute(
                "INSERT INTO runs (job_id, task, status, detail, started_at, finished_at) VALUES (?,?,?,?,?,?)",
                (
                    job["id"],
                    job["task"],
                    "completed" if ok else "failed",
                    (result or error)[:2000],
                    datetime.now(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            connection.commit()

    # ── running ──────────────────────────────────────────────

    def run_due_once(self, executor: Callable[[str], dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        """Run every job that is due. One failing job never stops the rest."""
        runner = executor or self.executor
        if runner is None:
            return []
        outcomes: list[dict[str, Any]] = []
        for job in self.due_jobs():
            try:
                result = runner(job["task"])
                ok = bool(result.get("ok", result.get("status") in ("completed", "ok")))
                self._finish(job, ok, json.dumps(result, ensure_ascii=False)[:2000], "")
                outcomes.append({"job": job["id"], "ok": ok, "result": result})
            except Exception as exc:  # noqa: BLE001 - a bad job must not kill the batch
                self._finish(job, False, "", str(exc))
                outcomes.append({"job": job["id"], "ok": False, "error": str(exc)})
        return outcomes

    def run_forever(self, executor: Callable[[str], dict[str, Any]] | None = None, *, interval_s: float = 30.0) -> int:
        """Run the loop until the stop flag is set. Used by the CLI and the tests."""
        count = 0
        while not self.stop_flag.is_set():
            count += len(self.run_due_once(executor))
            self.stop_flag.wait(interval_s)
        return count

    def stop(self) -> None:
        self.stop_flag.set()

    def recent_runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
