"""
مهمات إضافية لمشروع OSS-Work
يدعم:
- إدارة المهام المتقدمة
- جدولة المهام
- تقارير الأداء
- إدارة الوكلاء
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AdvancedTask:
    """مهمة متقدمة مع جدولة وإدارة أداء"""
    id: str
    task: str
    priority: TaskPriority = TaskPriority.MEDIUM
    status: TaskStatus = TaskStatus.PENDING
    assigned_agent: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "priority": self.priority.value,
            "status": self.status.value,
            "assigned_agent": self.assigned_agent,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "tags": self.tags,
        }


@dataclass
class AgentPerformance:
    """أداء الوكيل عبر الزمن"""
    agent_type: str
    tasks_completed: int = 0
    tasks_failed: int = 0
    total_execution_time: float = 0.0
    average_execution_time: float = 0.0
    success_rate: float = 0.0
    last_execution: str | None = None
    first_execution: str | None = None

    def record_result(self, success: bool, execution_time: float) -> None:
        if success:
            self.tasks_completed += 1
        else:
            self.tasks_failed += 1
        self.total_execution_time += execution_time
        total = self.tasks_completed + self.tasks_failed
        self.average_execution_time = self.total_execution_time / total if total > 0 else 0.0
        self.success_rate = (self.tasks_completed / total * 100) if total > 0 else 0.0


class TaskManager:
    """مدير المهام المتقدم مع جدولة وتتبع"""

    def __init__(self) -> None:
        self.tasks: dict[str, AdvancedTask] = {}
        self.agent_performance: dict[str, AgentPerformance] = {}
        self._next_id = 1

    def create_task(
        self,
        task: str,
        *,
        priority: TaskPriority = TaskPriority.MEDIUM,
        agent: str | None = None,
        tags: list[str] | None = None,
    ) -> AdvancedTask:
        task_id = f"task_{self._next_id:06d}"
        self._next_id += 1
        advanced_task = AdvancedTask(
            id=task_id,
            task=task,
            priority=priority,
            assigned_agent=agent,
            tags=tags or [],
        )
        self.tasks[task_id] = advanced_task
        return advanced_task

    def get_task(self, task_id: str) -> AdvancedTask | None:
        return self.tasks.get(task_id)

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        task.status = status
        if started_at:
            task.started_at = started_at
        if completed_at:
            task.completed_at = completed_at
        return True

    def record_result(
        self,
        task_id: str,
        result: dict[str, Any],
        error: str | None = None,
    ) -> bool:
        task = self.tasks.get(task_id)
        if not task:
            return False
        task.result = result
        task.error = error
        task.completed_at = datetime.now(timezone.utc).isoformat()
        task.status = TaskStatus.COMPLETED if not error else TaskStatus.FAILED

        if task.assigned_agent:
            perf = self.agent_performance.setdefault(task.assigned_agent, AgentPerformance(task.assigned_agent))
            success = task.status == TaskStatus.COMPLETED
            execution_time = 0.0
            if task.started_at and task.completed_at:
                from datetime import datetime as dt
                start = dt.fromisoformat(task.started_at)
                end = dt.fromisoformat(task.completed_at)
                execution_time = (end - start).total_seconds()
            perf.record_result(success, execution_time)
            perf.last_execution = task.completed_at
            if not perf.first_execution:
                perf.first_execution = task.created_at

        return True

    def get_pending_tasks(self, priority: TaskPriority | None = None) -> list[AdvancedTask]:
        tasks = [t for t in self.tasks.values() if t.status == TaskStatus.PENDING]
        if priority:
            tasks = [t for t in tasks if t.priority == priority]
        # ترتيب حسب الأولوية: حرجة > عالية > متوسطة > منخفضة
        priority_order = {TaskPriority.CRITICAL: 0, TaskPriority.HIGH: 1, TaskPriority.MEDIUM: 2, TaskPriority.LOW: 3}
        return sorted(tasks, key=lambda t: (priority_order.get(t.priority, 99), t.created_at))

    def get_agent_stats(self, agent_type: str) -> dict[str, Any]:
        perf = self.agent_performance.get(agent_type)
        if not perf:
            return {"agent_type": agent_type, "tasks_completed": 0, "tasks_failed": 0, "success_rate": 0.0, "average_execution_time": 0.0}
        return {
            "agent_type": perf.agent_type,
            "tasks_completed": perf.tasks_completed,
            "tasks_failed": perf.tasks_failed,
            "success_rate": perf.success_rate,
            "average_execution_time": perf.average_execution_time,
            "last_execution": perf.last_execution,
            "first_execution": perf.first_execution,
        }

    def get_summary(self) -> dict[str, Any]:
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)
        in_progress = sum(1 for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS)

        return {
            "total_tasks": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "in_progress": in_progress,
            "completion_rate": round(completed / total * 100, 2) if total > 0 else 0.0,
            "agent_stats": {a: self.get_agent_stats(a) for a in self.agent_performance},
        }


# مثال الاستخدام:
"""
from core.advanced import TaskManager, TaskPriority, TaskStatus
manager = TaskManager()

# إنشاء مهام
task1 = manager.create_task("مراجعة الكود للأمان", priority=TaskPriority.HIGH, tags=["security", "code"])
task2 = manager.create_task("تحليل البيانات", priority=TaskPriority.MEDIUM, tags=["data", "analysis"])

# تحديث الحالة
manager.update_status(task1.id, TaskStatus.IN_PROGRESS, started_at=datetime.now(timezone.utc).isoformat())

# تسجيل النتيجة
manager.record_result(task1.id, {"findings": ["no issues"]})

# الحصول على الإحصائيات
summary = manager.get_summary()
print(summary)
"""
