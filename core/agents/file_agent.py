"""Root-confined filesystem operations.

Reads and searches are allowed inside the configured root. Mutations require an
explicit approval flag and never follow a path outside that root.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.config import ALLOWED_ROOT
from core.contracts import DecisionRecord, TaskResult
from core.policy import Decision


class FileAgent(BaseAgent):
    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("read_file", "list_directory", "search_files", "file_write", "file_delete", "file_move")

    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("file", name="FileAgent", description=description, context=context, **kwargs)
        self.root = Path(self.context.get("allowed_root", ALLOWED_ROOT)).expanduser().resolve()

    def _inside_root(self, value: str | Path, *, must_exist: bool = False) -> Path:
        candidate = Path(value).expanduser()
        resolved = candidate.resolve(strict=must_exist)
        if resolved == self.root or self.root not in resolved.parents:
            raise PermissionError("path is outside the configured allowed root")
        return resolved

    def _decision(self, capability: str) -> DecisionRecord:
        approval = bool(self.context.get("approved", False))
        decision = self.policy.evaluate(capability, approval=approval)
        return DecisionRecord(capability, ["local_policy", f"root={self.root}"], decision.reason, None, "Review the proposed operation before approving it.", decision.action_attempted, decision.decision.value)

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            task = str(self.context.get("task", "list"))
            if task == "list":
                directory = self._inside_root(self.context.get("path", self.root))
                items = sorted((p.name for p in directory.iterdir()), key=str.lower) if directory.is_dir() else []
                result = TaskResult("completed", {"items": items, "root": str(self.root)})
            elif task == "read":
                target = self._inside_root(self.context.get("path", ""), must_exist=True)
                if not target.is_file():
                    raise IsADirectoryError(str(target))
                if target.stat().st_size > self.policy.max_file_bytes:
                    raise ValueError("file exceeds the configured read limit")
                content = target.read_text(encoding="utf-8", errors="replace")
                result = TaskResult("completed", {"path": str(target), "content": content, "sha256": hashlib.sha256(content.encode()).hexdigest()})
            elif task == "search":
                directory = self._inside_root(self.context.get("path", self.root))
                pattern = str(self.context.get("pattern", "*"))
                matches = [str(p) for p in directory.rglob(pattern) if self.root in p.resolve().parents]
                result = TaskResult("completed", {"matches": matches[:1000], "truncated": len(matches) > 1000})
            elif task in {"write", "delete", "move"}:
                capability = {"write": "file_write", "delete": "file_delete", "move": "file_move"}[task]
                decision = self._decision(capability)
                if decision.policy_decision != Decision.ALLOW.value:
                    result = TaskResult("denied", {"operation": task}, decision=decision)
                elif task == "write":
                    target = self._inside_root(self.context.get("path", ""))
                    content = str(self.context.get("content", ""))
                    if len(content.encode()) > self.policy.max_file_bytes:
                        raise ValueError("content exceeds the configured write limit")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(content, encoding="utf-8")
                    result = TaskResult("completed", {"path": str(target), "bytes": len(content.encode())}, decision=decision)
                elif task == "delete":
                    target = self._inside_root(self.context.get("path", ""), must_exist=True)
                    if target == self.root:
                        raise PermissionError("deleting the allowed root is forbidden")
                    if target.is_dir():
                        raise IsADirectoryError("directory deletion is not supported")
                    target.unlink()
                    result = TaskResult("completed", {"path": str(target)}, decision=decision)
                else:
                    source = self._inside_root(self.context.get("path", ""), must_exist=True)
                    destination = self._inside_root(self.context.get("destination", ""))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source), str(destination))
                    result = TaskResult("completed", {"source": str(source), "destination": str(destination)}, decision=decision)
            else:
                result = TaskResult("failed", errors=[f"unsupported task: {task}"])
            self.audit.record("file_operation", actor=str(self.context.get("user_id", "local")), target=task, outcome=result.status, details={"root": str(self.root)})
            return self.finalize(result.as_dict(), started)
        except Exception as exc:
            self.audit.record("file_operation", actor=str(self.context.get("user_id", "local")), target=str(self.context.get("task", "unknown")), outcome="failed", details={"error_type": type(exc).__name__})
            return self.fail(str(exc), started)
