"""
محرك سير العمل (Workflow Engine)
يدعم:
- إنشاء سير العمل
- تنفيذ الخطوات
- الانتظار للشروط
- القبول والإلغاء
- التصحيح
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class StepStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class WorkflowStep:
    """خطوة في سير العمل"""
    id: str
    name: str
    description: str | None = None
    action: Callable[..., dict[str, Any]] | None = None
    depends_on: list[str] = field(default_factory=list)
    timeout_seconds: int = 300
    retry_count: int = 0
    max_retries: int = 3

    status: StepStatus = field(default=StepStatus.PENDING)
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class Workflow:
    """سير عمل كامل"""

    id: str
    name: str
    description: str | None = None
    steps: list[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = field(default=WorkflowStatus.CREATED)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    current_step_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)

    def get_pending_steps(self) -> list[WorkflowStep]:
        """الحصول على الخطوات القابلة للتنفيذ (جميع التبعيات مكتملة)"""
        completed_ids = {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
        skipped_ids = {s.id for s in self.steps if s.status == StepStatus.SKIPPED}

        pending = []
        for step in self.steps:
            if step.status != StepStatus.PENDING:
                continue
            # التحقق من تبعيات
            deps_satisfied = all(
                dep in completed_ids or dep in skipped_ids for dep in step.depends_on
            )
            if deps_satisfied:
                pending.append(step)

        return sorted(pending, key=lambda s: self.steps.index(s))

    def can_execute(self, step: WorkflowStep) -> bool:
        """التحقق مما إذا كان يمكن تنفيذ خطوة"""
        if step.status != StepStatus.PENDING:
            return False
        completed_ids = {s.id for s in self.steps if s.status == StepStatus.COMPLETED}
        skipped_ids = {s.id for s in self.steps if s.status == StepStatus.SKIPPED}
        return all(dep in completed_ids or dep in skipped_ids for dep in step.depends_on)

    def execute_step(self, step: WorkflowStep) -> dict[str, Any]:
        """تنفيذ خطوة"""
        if not self.can_execute(step):
            return {"status": "skipped", "reason": "dependencies not satisfied"}

        step.status = StepStatus.RUNNING
        step.started_at = datetime.now(timezone.utc).isoformat()

        try:
            if step.action:
                result = step.action()
            else:
                result = {"message": f"Step {step.name} executed (no action)"}

            step.status = StepStatus.COMPLETED
            step.result = result
            step.completed_at = datetime.now(timezone.utc).isoformat()
            return {"status": "completed", "result": result}

        except Exception as exc:
            step.status = StepStatus.FAILED
            step.error = str(exc)
            step.completed_at = datetime.now(timezone.utc).isoformat()
            return {"status": "failed", "error": str(exc)}

    def execute(self) -> dict[str, Any]:
        """تنفيذ سير العمل كامل"""
        if self.status not in {WorkflowStatus.CREATED, WorkflowStatus.FAILED}:
            return {"status": "error", "message": "Workflow cannot be executed in current state"}

        self.status = WorkflowStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).isoformat()

        results = []
        while True:
            pending = self.get_pending_steps()
            if not pending:
                break

            step = pending[0]
            result = self.execute_step(step)
            results.append({"step": step.id, "result": result})

            if step.status == StepStatus.FAILED:
                self.status = WorkflowStatus.FAILED
                self.completed_at = datetime.now(timezone.utc).isoformat()
                return {"status": "failed", "results": results, "failed_step": step.id}

        self.status = WorkflowStatus.COMPLETED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        return {"status": "completed", "results": results}

    def cancel(self) -> None:
        """إلغاء سير العمل"""
        self.status = WorkflowStatus.CANCELLED
        self.completed_at = datetime.now(timezone.utc).isoformat()
        for step in self.steps:
            if step.status == StepStatus.RUNNING:
                step.status = StepStatus.SKIPPED

    def get_status(self) -> dict[str, Any]:
        """الحصول على حالة سير العمل"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value,
            "steps_count": len(self.steps),
            "completed_steps": sum(1 for s in self.steps if s.status == StepStatus.COMPLETED),
            "failed_steps": sum(1 for s in self.steps if s.status == StepStatus.FAILED),
            "pending_steps": sum(1 for s in self.steps if s.status == StepStatus.PENDING),
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# مثال الاستخدام:
"""
from core.workflow import Workflow, WorkflowStep, WorkflowStatus, StepStatus

# إنشاء سير عمل
workflow = Workflow(
    id="wf_001",
    name="تحليل الكود",
    description="سير عمل لتحليل كود المشروع",
)

# إضافة خطوات
step1 = WorkflowStep(
    id="step1",
    name="فحص الأمان",
    description="فحص الكود للأخطاء الأمنية",
    action=lambda: {"findings": ["no high-severity issues"]},
)
workflow.add_step(step1)

step2 = WorkflowStep(
    id="step2",
    name="تحليل الجودة",
    description="تحليل جودة الكود",
    depends_on=["step1"],
    action=lambda: {"quality_score": 85},
)
workflow.add_step(step2)

# تنفيذ
result = workflow.execute()
print(result)
"""
