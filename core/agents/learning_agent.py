"""Opt-in, bounded learning statistics; no behavioral fingerprinting by default."""
from __future__ import annotations

from collections import Counter
from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import TaskResult


class LearningAgent(BaseAgent):
    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("learning", name="LearningAgent", description=description, context=context, **kwargs)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("local_statistics", "pattern_summary", "methodology_draft")

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        task = str(self.context.get("task", "summary"))
        events = self.context.get("events", [])
        if not isinstance(events, list) or len(events) > 10_000:
            return self.fail("events must be a list of at most 10000 items", started)
        if task == "summary":
            labels = [str(item.get("label", "unknown"))[:100] for item in events if isinstance(item, dict)]
            data = {"event_count": len(labels), "label_counts": dict(Counter(labels)), "retention": "in-memory request scope only"}
        elif task == "patterns":
            data = {"patterns": [], "note": "Pattern discovery is disabled until explicit opt-in and privacy review."}
        elif task == "invent":
            data = {"draft": None, "note": "No autonomous invention or unvalidated decision-making is enabled."}
        else:
            return self.fail(f"unsupported task: {task}", started)
        return self.finalize(TaskResult("completed", data).as_dict(), started)
