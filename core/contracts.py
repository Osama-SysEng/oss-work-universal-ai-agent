"""Small, typed contracts used at subsystem boundaries."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    task: str
    user_id: str = "local"
    context: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)

    @classmethod
    def create(cls, task: str, *, user_id: str = "local", context: dict[str, Any] | None = None) -> "TaskRequest":
        clean = str(task).strip()
        if not clean or len(clean) > 10_000:
            raise ValueError("task must contain between 1 and 10000 characters")
        if not user_id or len(user_id) > 128:
            raise ValueError("user_id is invalid")
        return cls(uuid4().hex, clean, user_id, context or {})


@dataclass
class DecisionRecord:
    classification: str
    source_signals: list[str]
    explanation: str
    confidence: float | None
    recommended_human_action: str
    external_action_attempted: bool = False
    policy_decision: str = "deny"

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "source_signals": self.source_signals,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "recommended_human_action": self.recommended_human_action,
            "external_action_attempted": self.external_action_attempted,
            "policy_decision": self.policy_decision,
        }


@dataclass
class TaskResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    decision: DecisionRecord | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"status": self.status, "data": self.data, "errors": self.errors}
        if self.decision:
            result["decision"] = self.decision.as_dict()
        return result
