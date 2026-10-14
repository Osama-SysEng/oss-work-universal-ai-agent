"""Background work: persistent asyncio scheduler over the SQLite store.

- Jobs survive restarts (state lives in data-os/os.db, not in RAM).
- run_due_once(executor) executes every due job synchronously — this is
  what the loop calls and what tests use. No hidden threads.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import Any

from ossys import store

Executor = Callable[[str], dict[str, Any]]


def run_due_once(
    executor: Executor,
    *,
    now: float | None = None,
    db: str | None = None,
) -> list[dict[str, Any]]:
    """Execute all due jobs once. Returns per-job outcomes."""
    outcomes: list[dict[str, Any]] = []
    for job in store.due_jobs(now=now, db=db):
        store.mark_running(job["id"], db=db)
        try:
            result = executor(job["task"])
            status = str(result.get("status", "completed"))
            ok = status in ("completed", "simulated")
            finished = store.mark_finished(job["id"], ok=ok, result=str(result)[:2000], db=db)
            store.log_run(job["task"], status, job_id=job["id"], db=db)
            outcomes.append({"job": finished or job, "ok": ok, "result": result})
        except Exception as exc:  # noqa: BLE001 - one bad job must not kill the batch
            finished = store.mark_finished(job["id"], ok=False, error=str(exc), db=db)
            store.log_run(job["task"], "failed", str(exc), job_id=job["id"], db=db)
            outcomes.append({"job": finished or job, "ok": False, "error": str(exc)})
    return outcomes


async def loop_forever(
    executor: Executor,
    *,
    interval_s: float = 5.0,
    db: str | None = None,
    stop_after: float | None = None,
) -> int:
    """Background loop. stop_after (seconds) exists for tests/embedders."""
    started = time.monotonic()
    total = 0
    while True:
        total += len(run_due_once(executor, db=db))
        if stop_after is not None and (time.monotonic() - started) >= stop_after:
            return total
        await asyncio.sleep(interval_s)
