"""Code assistance without executing untrusted source in the host process."""
from __future__ import annotations

import ast
from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import DecisionRecord, TaskResult
from core.policy import Decision


class CodeAgent(BaseAgent):
    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("code_generation", "code_review", "refactoring", "code_execute")

    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("code", name="CodeAgent", description=description, context=context, **kwargs)

    def _execution_decision(self) -> DecisionRecord:
        decision = self.policy.evaluate("code_execute", approval=bool(self.context.get("approved", False)))
        return DecisionRecord("code_execution", ["safe_release_policy"], decision.reason, None, "Run only in a separately commissioned sandbox after review.", decision.action_attempted, decision.decision.value)

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        try:
            task = str(self.context.get("task", "review"))
            language = str(self.context.get("language", "python"))
            if task == "execute":
                decision = self._execution_decision()
                result = TaskResult("denied", {"language": language}, decision=decision)
            elif task == "generate":
                description = str(self.context.get("description", "return a value"))[:500]
                if language == "python":
                    generated = f'def generated_task():\n    """{description}"""\n    return None\n'
                elif language in {"javascript", "typescript"}:
                    generated = f"function generatedTask() {{\n  // {description}\n  return null;\n}}\n"
                else:
                    generated = f"// {description}\n"
                result = TaskResult("completed", {"language": language, "generated_code": generated})
            elif task == "review":
                code = str(self.context.get("code", ""))
                findings: list[str] = []
                if language == "python" and code:
                    try:
                        tree = ast.parse(code)
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"exec", "eval", "__import__"}:
                                findings.append(f"high: dynamic call {node.func.id} requires review")
                    except SyntaxError as exc:
                        findings.append(f"high: syntax error at line {exc.lineno}")
                if "subprocess" in code or "os.system" in code:
                    findings.append("high: process execution pattern requires isolation")
                if not findings:
                    findings.append("no high-risk pattern detected by the local reviewer")
                result = TaskResult("completed", {"language": language, "findings": findings})
            elif task == "refactor":
                code = str(self.context.get("code", ""))
                result = TaskResult("completed", {"language": language, "refactored_code": code.rstrip() + "\n"})
            else:
                result = TaskResult("failed", errors=[f"unsupported task: {task}"])
            return self.finalize(result.as_dict(), started)
        except Exception as exc:
            return self.fail(str(exc), started)
