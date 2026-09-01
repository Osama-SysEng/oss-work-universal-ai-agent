"""Browser boundary in simulation mode; no credentials, login, or navigation are attempted."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import DecisionRecord, TaskResult
from core.policy import Decision


class BrowserAgent(BaseAgent):
    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("browser", name="BrowserAgent", description=description, context=context, **kwargs)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("browser_control", "scrape_simulation", "form_preview")

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        decision = self.policy.evaluate("browser_control")
        record = DecisionRecord("browser_control", ["simulation_only_policy"], decision.reason, None, "Review the proposed browser action manually or commission a reviewed adapter.", False, decision.decision.value)
        result = TaskResult("simulated", {"action": self.context.get("task", "navigate"), "url": self.context.get("url"), "note": "No browser session, login, scraping, or form submission was attempted."}, decision=record)
        self.audit.record("browser_action", actor=str(self.context.get("user_id", "local")), target=str(self.context.get("url", "unspecified")), outcome="simulated")
        return self.finalize(result.as_dict(), started)
