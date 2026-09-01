"""Deterministic, bounded orchestrator; it never grants capabilities by itself."""
from __future__ import annotations

from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.agents.browser_agent import BrowserAgent
from core.agents.code_agent import CodeAgent
from core.agents.file_agent import FileAgent
from core.agents.integration_agent import IntegrationAgent
from core.agents.learning_agent import LearningAgent
from core.agents.memory_agent import MemoryAgent
from core.agents.security_agent import SecurityAgent
from core.contracts import TaskRequest, TaskResult


class OrchestratorAgent(BaseAgent):
    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("task_decomposition", "bounded_delegation", "result_synthesis")

    def __init__(self, task: str | None = None, context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        context = context or {}
        super().__init__("orchestrator", name="Orchestrator", context=context, **kwargs)
        self.task = task or str(context.get("task", "status"))
        self.agent_pool = {"browser": BrowserAgent, "code": CodeAgent, "file": FileAgent, "security": SecurityAgent, "integration": IntegrationAgent, "memory": MemoryAgent, "learning": LearningAgent}

    def decompose_task(self, task: str) -> list[str]:
        lowered = task.lower()
        selected = []
        keywords = {"browser": ("browser", "web", "scrape"), "code": ("code", "program", "refactor"), "file": ("file", "folder", "directory"), "security": ("security", "scan", "vulnerability"), "integration": ("telegram", "github", "google", "whatsapp", "api"), "memory": ("memory", "remember"), "learning": ("learn", "pattern")}
        for name, words in keywords.items():
            if any(word in lowered for word in words):
                selected.append(name)
        return selected[:5] or ["learning"]

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            request = TaskRequest.create(self.task, user_id=str(self.context.get("user_id", "local")), context=self.context)
            results = []
            for agent_type in self.decompose_task(request.task):
                agent_context = dict(self.context)
                agent_context["task"] = "review" if agent_type == "code" else agent_context.get("task", "summary")
                agent = self.agent_pool[agent_type](context=agent_context, policy=self.policy, audit=self.audit)
                results.append({"agent": agent_type, "result": agent.execute()})
            data = {"request_id": request.task_id, "subtasks_processed": len(results), "results": results, "external_actions_attempted": False}
            return self.finalize(TaskResult("completed", data).as_dict(), started)
        except Exception as exc:
            return self.fail(str(exc), started)
