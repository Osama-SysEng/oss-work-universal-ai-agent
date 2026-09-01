"""Shared lifecycle contract for all agents."""
from __future__ import annotations

from abc import ABC, abstractmethod
from time import perf_counter
from typing import Any

from core.audit import AuditLogger
from core.contracts import TaskResult
from core.policy import DEFAULT_POLICY, SafetyPolicy


class BaseAgent(ABC):
    def __init__(self, agent_type: str, *, name: str | None = None, description: str = "", context: dict[str, Any] | None = None, policy: SafetyPolicy = DEFAULT_POLICY, audit: AuditLogger | None = None) -> None:
        self.agent_type = agent_type
        self.name = name or f"{agent_type}_agent"
        self.description = description
        self.context = context or {}
        self.policy = policy
        self.audit = audit or AuditLogger()
        self.execution_history: list[dict[str, Any]] = []
        self.performance_metrics = {"tasks_completed": 0, "tasks_failed": 0, "average_execution_time": 0.0, "success_rate": 0.0}

    @property
    @abstractmethod
    def capabilities(self) -> tuple[str, ...]:
        """Capabilities are descriptive and do not grant permission."""

    @abstractmethod
    def execute(self) -> dict[str, Any]:
        """Execute one validated task."""

    def validate_setup(self) -> bool:
        return True

    def pre_execute(self) -> bool:
        return self.validate_setup()

    def finalize(self, result: dict[str, Any], started: float) -> dict[str, Any]:
        elapsed = perf_counter() - started
        success = result.get("status") in {"completed", "simulated"}
        self.performance_metrics["tasks_completed" if success else "tasks_failed"] += 1
        total = self.performance_metrics["tasks_completed"] + self.performance_metrics["tasks_failed"]
        self.performance_metrics["success_rate"] = round(self.performance_metrics["tasks_completed"] / total * 100, 2)
        old = self.performance_metrics["average_execution_time"]
        self.performance_metrics["average_execution_time"] = round(((old * (total - 1)) + elapsed) / total, 6)
        self.execution_history.append({"elapsed": elapsed, "status": result.get("status")})
        return result

    def fail(self, message: str, started: float) -> dict[str, Any]:
        return self.finalize(TaskResult("failed", errors=[message]).as_dict(), started)

    def get_status(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.agent_type, "capabilities": list(self.capabilities), "metrics": self.performance_metrics.copy(), "history_count": len(self.execution_history)}
