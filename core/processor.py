"""
OSS Work — Shared Task Processor.

معالج المهام المشترك المستخدم من قبل جميع الأوضاع:
- Telegram mode: المهام من الهاتف学桌面 وترد على الهاتف
- Desktop CLI: واجهة سطر الأوامر المستقلة
- Desktop API: API محلي لتطبيقات桌面 الأخرى

모든 الواجهات تستخدم هذا المعالج المركزي.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.config import AgentConfig, load_config, VERSION
from core.contracts import TaskRequest
from core.agents.orchestrator import OrchestratorAgent
from core.imagination.engine import UltraIQEngine


# ═══════════════════════════════════════════════════════════════════
# Task Processor
# ═══════════════════════════════════════════════════════════════════

class TaskProcessor:
    """
    معالج المهام المشترك — جميع الواجهات (Telegram, CLI, API) تستخدم هذا.

    المسار:
    1. imagination engine — يكتمل/يوسع الفكر
    2. orchestrator — يوجّه عبر عوامل代理 متخصصة
    3. model router — يستخدم نماذج ذكاء اصطناعي مجانية إذا لزم
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
        معالجة مهمة عبر المسار الكامل.

        تستخدمها: بوت التلجرام، CLI桌面، API桌面 — جميعها تستدعي هذا.
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

            # المرحلة 1: imagination — يكتمل/يوسع الفكر
            completed = await self._complete_thought(task, user_id)

            # المرحلة 2: orchestrator — يوجّه عبر عوامل代理 متخصصة
            # ملاحظة: OrchestratorAgent يقرأ self.task من الإنشاء
            orchestrator = OrchestratorAgent(task=completed, context={"user_id": user_id})
            result = orchestrator.execute()

            # المرحلة 3: تسجيل في السجل
            elapsed = (time.monotonic() - started) * 1000
            self._history.setdefault(user_id, []).append({
                "task_id": task_id,
                "task": task[:200],
                "completed": completed[:200],
                "status": result.get("status", ""),
                "latency_ms": round(elapsed, 1),
                "timestamp": time.time(),
            })

            result["task_id"] = task_id
            result["latency_ms"] = round(elapsed, 1)
            result["mode"] = self.config.mode

            return result

        except Exception as e:
            return {
                "status": "failed",
                "errors": [str(e)],
                "mode": self.config.mode,
            }
        finally:
            self._busy.discard(user_id)

    async def process_batch(self, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """معالجة دفعة من المهام بشكل متوازي."""
        results = await asyncio.gather(
            *[self.process(t.get("task", ""), t.get("user_id", "local")) for t in tasks],
            return_exceptions=True,
        )
        return [
            r if isinstance(r, dict) else {"status": "failed", "errors": [str(r)]}
            for r in results
        ]

    # ── Internal ──────────────────────────────────────────────────

    async def _complete_thought(self, task: str, uid: str) -> str:
        """استخدام محرك الخيال لإنشاء الفكر."""
        try:
            return self.imagination.complete_thought(task, {"user_id": uid})
        except Exception:
            return task

    # ── Status & History ──────────────────────────────────────────

    def get_status(self) -> dict[str, Any]:
        """حالة المعالج."""
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
        """سجل المهام لمستخدم معين."""
        return self._history.get(user_id, [])

    def clear_user_history(self, user_id: str) -> None:
        """مسح سجل مستخدم."""
        self._history.pop(user_id, None)
        self._busy.discard(user_id)

    def get_all_history(self, limit: int = 100) -> list[dict]:
        """جميع السجلات لمدة الأخيرة."""
        all_tasks = []
        for user_tasks in self._history.values():
            all_tasks.extend(user_tasks[-limit:])
        return sorted(all_tasks, key=lambda x: x.get("timestamp", 0), reverse=True)[:limit]

    def reset(self) -> None:
        """إعادة تعيين المعالج."""
        self._history.clear()
        self._busy.clear()
        self._task_counter = 0
        self._started_at = time.time()


# ═══════════════════════════════════════════════════════════════════
# Singleton
# ═══════════════════════════════════════════════════════════════════

_global_processor: TaskProcessor | None = None


def get_processor() -> TaskProcessor:
    """الحصول على معالج مشترك (singleton)."""
    global _global_processor
    if _global_processor is None:
        config = load_config()
        _global_processor = TaskProcessor(config)
    return _global_processor


def reset_processor() -> None:
    """إعادة تعيين المعالج (للاختبار)."""
    global _global_processor
    _global_processor = None
