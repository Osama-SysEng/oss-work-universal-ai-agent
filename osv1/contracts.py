"""Typed contracts for the OS_V1 layers.

Every boundary in the pipeline passes one of these objects. The rule from the
specification (section 8) is explicit: nothing enters the system without a
source tag and a confidence value, and every action carries a permission, a
log entry, and a rollback path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    from uuid import uuid4

    return f"{prefix}-{uuid4().hex[:12]}"


# ── 8.1 Multimodal Input ───────────────────────────────────────────────


@dataclass(frozen=True)
class UnifiedInput:
    """One input with its source and the confidence attached to that source."""

    source: str
    kind: str  # text | file | table | log | event | image_meta | data
    payload: str
    confidence: float = 1.0
    reference: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InputBundle:
    """Everything the user handed over for one request."""

    request_id: str
    inputs: tuple[UnifiedInput, ...]
    rejected: tuple[str, ...] = ()

    def texts(self) -> list[str]:
        return [i.payload for i in self.inputs if i.kind in ("text", "file", "table", "log", "data")]

    def sources(self) -> list[str]:
        return [i.source for i in self.inputs]


# ── 8.2 World Model and Memory ─────────────────────────────────────────


@dataclass(frozen=True)
class WorldState:
    """A description of the current state of the user's work and environment."""

    request_id: str
    facts: tuple[str, ...] = ()
    open_files: tuple[str, ...] = ()
    recent_events: tuple[str, ...] = ()
    memory_hits: tuple[str, ...] = ()
    confidence: float = 1.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Prediction:
    """What an action is expected to change, before it runs."""

    action: str
    expected_effect: str
    expected_files: tuple[str, ...] = ()
    risk: str = "low"
    confidence: float = 0.5
    basis: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PredictionCheck:
    """Comparison between the prediction and what actually happened."""

    action: str
    predicted: str
    observed: str
    matched: bool
    gap: float
    note: str = ""


# ── 8.3 Reasoning Engine ──────────────────────────────────────────────


@dataclass(frozen=True)
class Hypothesis:
    """A candidate explanation with the consequences that follow from it."""

    id: str
    statement: str
    consequences: tuple[str, ...] = ()
    test: str = ""
    supported_by: tuple[str, ...] = ()
    confidence: float = 0.0
    status: str = "open"  # open | supported | refuted | dropped

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── 8.4 Decision Engine ───────────────────────────────────────────────


@dataclass(frozen=True)
class Option:
    """One way forward, with its probability, cost, and expected value."""

    id: str
    label: str
    probability: float
    cost: float = 1.0
    impact: float = 1.0
    detail: str = ""

    @property
    def expected_value(self) -> float:
        return self.probability * self.impact - self.cost

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["expected_value"] = round(self.expected_value, 4)
        return data


@dataclass(frozen=True)
class Decision:
    """The outcome of the decision engine, including the right to abstain."""

    outcome: str  # decide | abstain | ask_user
    option: Option | None = None
    options: tuple[Option, ...] = ()
    rationale: str = ""
    information_value: float = 0.0
    cost_of_waiting: float = 0.0
    question: str = ""
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "option": self.option.as_dict() if self.option else None,
            "options": [o.as_dict() for o in self.options],
            "rationale": self.rationale,
            "information_value": round(self.information_value, 4),
            "cost_of_waiting": round(self.cost_of_waiting, 4),
            "question": self.question,
            "confidence": round(self.confidence, 4),
        }


# ── 8.5 Verifier and Uncertainty Engine ───────────────────────────────


@dataclass(frozen=True)
class Check:
    """One independent check with its own evidence."""

    name: str
    passed: bool
    detail: str = ""
    evidence: tuple[str, ...] = ()
    weight: float = 1.0


@dataclass(frozen=True)
class Verification:
    """The verifier's verdict. It never asks the reasoner for a second opinion."""

    passed: bool
    checks: tuple[Check, ...] = ()
    uncertainty: float = 0.0
    reasons: tuple[str, ...] = ()
    uncertainty_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "checks": [asdict(c) for c in self.checks],
            "uncertainty": round(self.uncertainty, 4),
            "reasons": list(self.reasons),
            "uncertainty_note": self.uncertainty_note,
        }


# ── 8.6 Adaptive Action Engine ────────────────────────────────────────


@dataclass(frozen=True)
class Permission:
    """A granted scope. Nothing runs without one."""

    scope: str  # files | network | programs | irreversible
    target: str
    granted_by: str = "user"
    expires_at: str | None = None
    readonly: bool = True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ActionRecord:
    """What was done, under which permission, with how to undo it."""

    action: str
    tool: str
    target: str
    outcome: str  # completed | failed | rolled_back | blocked
    permission: str = ""
    rollback: str = ""
    detail: str = ""
    log_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ── Plan / Build (spec section 10) ───────────────────────────────────


@dataclass(frozen=True)
class PlanStep:
    id: str
    action: str
    tool: str
    target: str = ""
    detail: str = ""
    requires_approval: bool = False
    reversible: bool = True
    rollback: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Plan:
    """A plan the user can approve, change, or reject. Build never starts without one."""

    id: str
    request_id: str
    mode: str = "plan"
    goal: str = ""
    steps: tuple[PlanStep, ...] = ()
    rationale: str = ""
    agent_id: str = ""
    agent_title: str = ""
    confidence: float = 0.0
    requires_approval: bool = False
    created_at: str = field(default_factory=utc_now)

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["steps"] = [asdict(s) for s in self.steps]
        return data


# ── SOM typed decisions (spec section 9) ──────────────────────────────


@dataclass(frozen=True)
class SomDecision:
    """A structured, calibrated decision from System One."""

    question_type: str  # choice | score | yes_no
    question: str
    value: Any = None
    probabilities: tuple[float, ...] = ()
    labels: tuple[str, ...] = ()
    confidence: float = 0.0
    rationale: str = ""
    source: str = "rule"
    abstained: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "question_type": self.question_type,
            "question": self.question,
            "value": self.value,
            "probabilities": [round(p, 4) for p in self.probabilities],
            "labels": list(self.labels),
            "confidence": round(self.confidence, 4),
            "rationale": self.rationale,
            "source": self.source,
            "abstained": self.abstained,
        }


# ── Final result ──────────────────────────────────────────────────────


@dataclass
class TaskResult:
    """What the user receives, with the evidence trail behind it."""

    request_id: str
    status: str  # completed | failed | needs_approval | needs_information | blocked
    answer: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    plan: Plan | None = None
    decision: Decision | None = None
    verification: Verification | None = None
    actions: tuple[ActionRecord, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=utc_now)
    finished_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "status": self.status,
            "answer": self.answer,
            "data": self.data,
            "plan": self.plan.as_dict() if self.plan else None,
            "decision": self.decision.as_dict() if self.decision else None,
            "verification": self.verification.as_dict() if self.verification else None,
            "actions": [a.as_dict() for a in self.actions],
            "metrics": self.metrics,
            "errors": list(self.errors),
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
