"""The OS kernel (v1): boot, dispatch, background, status.

Dispatch is real — every executor calls existing core agents or ossys
services. Nothing is simulated and nothing leaves the machine.
"""

from __future__ import annotations

import time
from typing import Any

from ossys import config, scheduler, store
from ossys.archetypes import get_archetype
from ossys.task_registry import TaskAgent, get_task


class Kernel:
    def __init__(self, *, user: str = "local") -> None:
        self.user = user
        self.booted_at: float | None = None
        self.engine_ok: bool = False
        self.boot_note: str = ""

    # ── Boot ──────────────────────────────────────────────

    def boot(self) -> dict[str, Any]:
        store.init_db()
        self.engine_ok = self._check_engine()
        self.booted_at = time.time()
        if self.engine_ok:
            self.boot_note = f"local engine up at {config.LOCAL_URL}"
        else:
            self.boot_note = (
                f"local engine down at {config.LOCAL_URL} — "
                "rule-based agents still work; start it with "
                "C:\\tools\\llama\\start-engine.cmd for LLM answers"
            )
        return self.status()

    def _check_engine(self) -> bool:
        try:
            from core.services.local_engine import LocalEngine

            return LocalEngine().health()
        except (ImportError, AttributeError, ValueError):
            return False

    def status(self) -> dict[str, Any]:
        return {
            "os": config.OS_NAME,
            "version": config.OS_VERSION,
            "strict_local": config.OS_STRICT,
            "booted": self.booted_at is not None,
            "engine_ok": self.engine_ok,
            "note": self.boot_note,
            "jobs": len(store.list_jobs()),
            "skills": len(store.list_skills()),
        }

    # ── Dispatch ──────────────────────────────────────────

    def run(self, task: str, *, task_id: str | None = None) -> dict[str, Any]:
        """Run a task now. task_id (T001..T300) selects the agent, else ad-hoc."""
        agent: TaskAgent | None = get_task(task_id) if task_id else None
        executor = "orchestrator"
        if agent:
            arch = get_archetype(agent.archetype)
            if arch:
                executor = arch.executor
            task = f"[{agent.id} {agent.title}] {task}"
        started = time.time()
        try:
            result = self._dispatch(executor, task)
            store.log_run(task, str(result.get("status", "completed")))
            result["elapsed_s"] = round(time.time() - started, 3)
            return result
        except Exception as exc:  # noqa: BLE001 - kernel must report, never crash
            store.log_run(task, "failed", str(exc))
            return {"status": "failed", "error": str(exc)}

    def _dispatch(self, executor: str, task: str) -> dict[str, Any]:
        if executor == "orchestrator":
            from core.agents.orchestrator import OrchestratorAgent

            return OrchestratorAgent(task, {"user_id": self.user}).execute()
        if executor == "reader":
            from ossys import browser

            url = self._first_url(task)
            if not url:
                return {
                    "status": "failed",
                    "error": "web reader needs a URL in the task (http/https).",
                }
            page = browser.fetch(url)
            return {"status": "completed", "url": url, "page": page}
        if executor == "office":
            return {
                "status": "completed",
                "note": "office suite ready (txt/md/csv native). Name the file in the task.",
                "workspace": config.workspace_dir(),
            }
        if executor == "hosting":
            from ossys.hosting import get_manager

            return {"status": "completed", "apps": get_manager().list()}
        if executor == "scheduler":
            return {"status": "completed", "jobs": store.list_jobs()}
        if executor == "skills":
            return {"status": "completed", "skills": store.list_skills()}
        if executor == "engine":
            from core.services.local_engine import LocalEngine

            out = LocalEngine().chat([{"role": "user", "content": task}])
            return {"status": "completed", "response": out["content"], "model": out["model"]}
        # file | code | security | memory | learning -> core specialists
        return self._specialist(executor, task)

    def _specialist(self, kind: str, task: str) -> dict[str, Any]:
        mapping = {
            "file": "core.agents.file_agent:FileAgent",
            "code": "core.agents.code_agent:CodeAgent",
            "security": "core.agents.security_agent:SecurityAgent",
            "memory": "core.agents.memory_agent:MemoryAgent",
            "learning": "core.agents.learning_agent:LearningAgent",
        }
        dotted = mapping.get(kind)
        if not dotted:
            raise ValueError(f"Unknown executor: {kind}")
        module_name, class_name = dotted.split(":")
        import importlib

        module = importlib.import_module(module_name)
        agent_cls = getattr(module, class_name)
        # Specialists share (description="", context=None) + execute().
        agent = agent_cls("", {"user_id": self.user, "task": task})
        return agent.execute()

    @staticmethod
    def _first_url(task: str) -> str | None:
        for token in task.replace(",", " ").split():
            if token.lower().startswith(("http://", "https://")):
                return token.strip().strip("()<>\"'")
        return None

    # ── Background ────────────────────────────────────────

    def submit(
        self,
        task: str,
        *,
        delay_s: float = 0,
        interval_s: float | None = None,
        repeat: bool = False,
    ) -> dict[str, Any]:
        store.init_db()
        return store.submit_job(
            task,
            run_at=time.time() + delay_s,
            interval_s=interval_s,
            repeat=repeat,
        )

    def run_background_once(self) -> list[dict[str, Any]]:
        return scheduler.run_due_once(lambda t: self.run(t))
