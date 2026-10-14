"""SQLite state for the OS: background jobs, self-built skills, run log.

Stdlib only. One file (data-os/os.db). Timescale/Postgres stay optional
and are never required for the OS to boot.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from typing import Any

from ossys import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    run_at REAL NOT NULL,
    interval_s REAL,
    repeat INTEGER NOT NULL DEFAULT 0,
    runs INTEGER NOT NULL DEFAULT 0,
    last_result TEXT,
    last_error TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    job_id TEXT,
    task TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL
);
"""


def _connect(db: str | None = None) -> sqlite3.Connection:
    path = db or config.db_path()
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def init_db(db: str | None = None) -> str:
    path = db or config.db_path()
    conn = _connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return path


def submit_job(
    task: str,
    *,
    run_at: float | None = None,
    interval_s: float | None = None,
    repeat: bool = False,
    db: str | None = None,
) -> dict[str, Any]:
    now = time.time()
    job = {
        "id": f"job-{uuid.uuid4().hex[:12]}",
        "task": task,
        "state": "queued",
        "run_at": run_at if run_at is not None else now,
        "interval_s": interval_s,
        "repeat": 1 if repeat else 0,
        "runs": 0,
        "created_at": now,
    }
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO jobs (id, task, state, run_at, interval_s, repeat, runs, created_at)"
            " VALUES (:id, :task, :state, :run_at, :interval_s, :repeat, :runs, :created_at)",
            job,
        )
        conn.commit()
    finally:
        conn.close()
    return job


def due_jobs(now: float | None = None, db: str | None = None) -> list[dict[str, Any]]:
    now = now if now is not None else time.time()
    conn = _connect(db)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE state IN ('queued', 'scheduled') AND run_at <= ? ORDER BY run_at",
            (now,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_job(job_id: str, db: str | None = None) -> dict[str, Any] | None:
    conn = _connect(db)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_jobs(db: str | None = None) -> list[dict[str, Any]]:
    conn = _connect(db)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()]
    finally:
        conn.close()


def mark_running(job_id: str, db: str | None = None) -> None:
    conn = _connect(db)
    try:
        conn.execute("UPDATE jobs SET state = 'running' WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


def mark_finished(
    job_id: str,
    *,
    ok: bool,
    result: str = "",
    error: str = "",
    db: str | None = None,
) -> dict[str, Any] | None:
    """Record outcome; reschedule repeating jobs, else close them."""
    conn = _connect(db)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        job = dict(row)
        runs = job["runs"] + 1
        if job["repeat"] and job["interval_s"]:
            state: str = "scheduled"
            run_at: float = time.time() + float(job["interval_s"])
        else:
            state = "completed" if ok else "failed"
            run_at = job["run_at"]
        conn.execute(
            "UPDATE jobs SET state = ?, runs = ?, last_result = ?, last_error = ?, run_at = ? WHERE id = ?",
            (state, runs, result[:2000], error[:2000], run_at, job_id),
        )
        conn.commit()
        job.update({"state": state, "runs": runs, "last_result": result[:2000], "last_error": error[:2000]})
        return job
    finally:
        conn.close()


def log_run(
    task: str,
    status: str,
    detail: str = "",
    *,
    job_id: str | None = None,
    db: str | None = None,
) -> dict[str, Any]:
    now = time.time()
    entry = {
        "id": f"run-{uuid.uuid4().hex[:12]}",
        "job_id": job_id,
        "task": task,
        "status": status,
        "detail": detail[:2000],
        "started_at": now,
        "finished_at": now,
    }
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO runs (id, job_id, task, status, detail, started_at, finished_at)"
            " VALUES (:id, :job_id, :task, :status, :detail, :started_at, :finished_at)",
            entry,
        )
        conn.commit()
    finally:
        conn.close()
    return entry


def recent_runs(limit: int = 20, db: str | None = None) -> list[dict[str, Any]]:
    conn = _connect(db)
    try:
        rows = conn.execute("SELECT * FROM runs ORDER BY finished_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_skill(name: str, summary: str, path: str, db: str | None = None) -> dict[str, Any]:
    entry = {"name": name, "summary": summary, "path": path, "created_at": time.time()}
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO skills (name, summary, path, created_at)"
            " VALUES (:name, :summary, :path, :created_at)",
            entry,
        )
        conn.commit()
    finally:
        conn.close()
    return entry


def list_skills(db: str | None = None) -> list[dict[str, Any]]:
    conn = _connect(db)
    try:
        return [dict(r) for r in conn.execute("SELECT * FROM skills ORDER BY name").fetchall()]
    finally:
        conn.close()
