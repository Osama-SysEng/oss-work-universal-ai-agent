"""External service facade kept simulation-only until each provider is commissioned."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import DecisionRecord, TaskResult


class IntegrationAgent(BaseAgent):
    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("integration", name="IntegrationAgent", description=description, context=context, **kwargs)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("external_message", "receive_data", "sync_data", "webhook_delivery")

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        provider = str(self.context.get("provider", "unspecified"))[:100]
        task = str(self.context.get("task", "status"))[:100]
        decision = self.policy.evaluate("external_message" if task in {"send", "webhook"} else "browser_control")
        record = DecisionRecord("external_integration", [f"provider={provider}", "no_live_credentials"], decision.reason, None, "Configure provider auth, consent, signatures, idempotency, retries, and an approval gate before activation.", False, decision.decision.value)
        result = TaskResult("simulated", {"provider": provider, "task": task, "message": "No external request or delivery was attempted."}, decision=record)
        self.audit.record("external_integration", actor=str(self.context.get("user_id", "local")), target=provider, outcome="simulated")
        return self.finalize(result.as_dict(), started)
