"""
OSS Work — Shared Task Processor.

Shared task processor used by all local interfaces:
- Desktop CLI: standalone command-line interface
- Desktop API: local API for other desktop applications
- oss-os kernel: the OS dispatches through this

All interfaces use this central processor.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from core.agents.orchestrator import OrchestratorAgent
from core.config import VERSION, AgentConfig, load_config
from core.imagination.engine import UltraIQEngine

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# Task Processor
# ═══════════════════════════════════════════════════════════════════


class TaskProcessor:
    """
    Shared task processor — all interfaces (CLI, API, OS kernel) use this.

    Pipeline:
    1. imagination engine — completes/expands the thought
    2. orchestrator — routes through specialized agents
    3. model router — uses the local engine if needed
    """

    def __init__(self, config: AgentConfig | None = None):
        self.config = config or load_config()
        self.orchestrator = OrchestratorAgent()
        self.imagination = UltraIQEngine(
            max_threads=self.config.max_threads,
            simulation_depth=self.config.simulation_depth,
            invention_enabled=self.config.invention_enabled,
        )
        self._history: dict[str, list[dict]] = {}
        self._busy: set[str] = set()
        self._task_counter: int = 0
        self._started_at: float = time.time()

    # ── Public API ────────────────────────────────────────────────

    async def process(self, task: str, user_id: str = "local") -> dict[str, Any]:
        """
        Process a task through the full pipeline.

        Used by: desktop CLI, desktop API, oss-os kernel — all of them call this.
        """
        if not task or len(task.strip()) < 2:
            return {"status": "failed", "errors": ["المهمة قصيرة جدًا"]}

        if user_id in self._busy:
            return {"status": "busy", "error": "مهمة قيد المعالجة لمستخدم آخر"}

        self._task_counter += 1
        task_id = f"task-{self._task_counter:06d}"
        self._busy.add(user_id)

        try:
            started = time.monotonic()

            # Stage 1: imagination — completes/expands the thought
            completed = await self._complete_thought(task, user_id)

            # Stage 2: orchestrator — routes through specialized agents
            # Note: OrchestratorAgent reads self.task from construction
            orchestrator = OrchestratorAgent(task=completed, context={"user_id": user_id})
            result = orchestrator.execute()

            # Stage 3: record in the history log
            elapsed = (time.monotonic() - started) * 1000
            self._history.setdefault(user_id, []).append(
                {
                    "task_id": task_id,
                    "task": task[:200],
                    "completed": completed[:200],
                    "status": result.get("status", ""),
                    "latency_ms": round(elapsed, 1),
                    "timestamp": time.time(),
                }
            )

            result["task_id"] = task_id
            result["latency_ms"] = round(elapsed, 1)
            result["mode"] = self.config.mode

            return result

        except Exception as e:
            logger.exception("Unhandled exception in processor.py")
            return {
                "status": "failed",
                "errors": [str(e)],
                "mode": self.config.mode,
            }
        finally:
            self._busy.discard(user_id)

    async def process_batch(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process a batch of tasks in parallel."""
        results = await asyncio.gather(
            *[self.process(t.get("task", ""), t.get("user_id", "local")) for t in tasks],
            return_exceptions=True,
        )
        return [r if isinstance(r, dict) else {"status": "failed", "errors": [str(r)]} for r in results]

    # ── Internal ──────────────────────────────────────────────────

    async def _complete_thought(self, task: str, uid: str) -> str:
        """Use the imagination engine to generate the thought."""
        try:
            return self.imagination.complete_thought(task, {"user_id": uid})
        except Exception as _exc:
            logger.exception("Unhandled exception in processor.py")
            return task

    # ── Status & History ──────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """Processor status."""
        return {
            "version": VERSION,
            "mode": self.config.mode,
            "simulation_only": self.config.simulation_only,
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "total_tasks": sum(len(v) for v in self._history.values()),
            "active_tasks": len(self._busy),
            "users": list(self._history.keys()),
        }

    def get_user_history(self, user_id: str) -> list[dict]:
        """Task history for a given user."""
        return self._history.get(user_id, [])

    def clear_user_history(self, user_id: str) -> None:
        """Clear a user's history."""
        self._history.pop(user_id, None)
        self._busy.discard(user_id)

    def get_all_history(self, limit: int = 100) -> list[dict]:
        """All recent history logs."""
        all_tasks = []
        for user_tasks in self._history.values():
            all_tasks.extend(user_tasks[-limit:])
        return sorted(all_tasks, key=lambda x: x.get("timestamp", 0), reverse=True)[:limit]

    def reset(self) -> None:
        """Reset the processor."""
        self._history.clear()
        self._busy.clear()
        self._task_counter = 0
        self._started_at = time.time()


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════

_global_processor: TaskProcessor | None = None


def get_processor() -> TaskProcessor:
    """Get the shared processor (singleton)."""
    global _global_processor
    if _global_processor is None:
        config = load_config()
        _global_processor = TaskProcessor(config)
    return _global_processor


def reset_processor() -> None:
    """Reset the processor (for testing)."""
    global _global_processor
    _global_processor = None
