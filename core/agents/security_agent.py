"""Dependency-free local security checks with honest scope reporting."""
from __future__ import annotations

import re
from pathlib import Path
from time import perf_counter
from typing import Any

from core.agents.base import BaseAgent
from core.contracts import TaskResult


class SecurityAgent(BaseAgent):
    def __init__(self, description: str = "", context: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__("security", name="SecurityAgent", description=description, context=context, **kwargs)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return ("static_scan", "secret_pattern_scan", "policy_report")

    def execute(self) -> dict[str, Any]:
        started = perf_counter()
        target = Path(self.context.get("target", ".")).expanduser().resolve()
        findings: list[dict[str, Any]] = []
        patterns = {
            "secret_pattern": re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*[=:]\s*[\"'][^\"']{8,}[\"']"),
            "dynamic_execution": re.compile(r"(?m)\b(exec|eval)\s*\("),
            "shell_execution": re.compile(r"(?m)\bos\.system\s*\(|shell\s*=\s*True"),
        }
        files = [target] if target.is_file() else [p for p in target.rglob("*") if p.is_file() and p.suffix in {".py", ".js", ".ts", ".tsx", ".json", ".yml", ".yaml", ".env"}]
        for path in files[:5000]:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name, pattern in patterns.items():
                if pattern.search(text):
                    findings.append({"type": name, "path": str(path), "severity": "high" if name != "secret_pattern" else "critical"})
        data = {"target": str(target), "files_scanned": len(files), "findings": findings, "scope": "Local pattern checks only; CodeQL, Snyk, ZAP, and provider security models were not invoked."}
        result = TaskResult("completed", data)
        self.audit.record("security_scan", actor=str(self.context.get("user_id", "local")), target=str(target), outcome="completed", details={"files_scanned": len(files), "finding_count": len(findings)})
        return self.finalize(result.as_dict(), started)
