"""Code tools: static analysis, review, and sandboxed execution.

Analysis is AST-based, so the findings come from the parsed program rather
than from keyword matching alone. Execution always happens inside the sandbox
from :mod:`osv1.tools.sandbox`, with no network and no inherited secrets.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from typing import Any

from osv1.tools.registry import RISK_EXECUTE, RISK_READ, Tool, ToolResult
from osv1.tools.sandbox import run_python

SECRET_PATTERNS = (
    (r"\bsk-[A-Za-z0-9]{16,}\b", "openai-style key"),
    (r"\bAKIA[0-9A-Z]{16}\b", "aws access key id"),
    (r"\bghp_[A-Za-z0-9]{20,}\b", "github token"),
    (r"(?i)\b(password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]", "hardcoded credential"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
)
DANGEROUS_CALLS = {"eval", "exec", "compile", "__import__"}
MAX_FUNCTION_LINES = 60


@dataclass
class CodeAnalyzer:
    """AST-based checks over one source file."""

    findings: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, severity: str, code: str, message: str, line: int = 0) -> None:
        self.findings.append({"severity": severity, "code": code, "message": message, "line": line})

    @property
    def errors(self) -> list[dict[str, Any]]:
        return [f for f in self.findings if f["severity"] == "error"]

    @property
    def warnings(self) -> list[dict[str, Any]]:
        return [f for f in self.findings if f["severity"] == "warning"]


def analyze_source(source: str, *, filename: str = "<source>") -> tuple[CodeAnalyzer, list[dict[str, Any]]]:
    """Analyse Python source. Returns the analyzer and a parsed structure summary."""
    analyzer = CodeAnalyzer()
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        analyzer.add("error", "syntax-error", f"cannot parse the file: {exc.msg}", exc.lineno or 0)
        return analyzer, {}

    functions: list[dict[str, Any]] = []
    classes: list[dict[str, Any]] = []
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno)
            length = end - node.lineno + 1
            functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "lines": length,
                    "args": len(node.args.args),
                    "docstring": bool(ast.get_docstring(node)),
                    "branches": sum(1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.For, ast.While, ast.Try))),
                }
            )
            if length > MAX_FUNCTION_LINES:
                analyzer.add("warning", "long-function", f"function {node.name} spans {length} lines", node.lineno)
            if not ast.get_docstring(node) and not node.name.startswith("_"):
                analyzer.add("info", "missing-docstring", f"function {node.name} has no docstring", node.lineno)
        elif isinstance(node, ast.ClassDef):
            classes.append({"name": node.name, "line": node.lineno, "methods": 0})
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ",".join(a.name for a in node.names)
            imports.append(module)

    for cls in classes:
        cls["methods"] = sum(1 for f in functions if f["name"].startswith(f"{cls['name']}."))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_CALLS:
            analyzer.add("warning", "dynamic-execution", f"call to {node.func.id}()", node.lineno)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "system":
            analyzer.add("warning", "shell-call", "call to os.system()", node.lineno)

    for pattern, label in SECRET_PATTERNS:
        for match in re.finditer(pattern, source):
            line = source.count("\n", 0, match.start()) + 1
            analyzer.add("error", "possible-secret", f"possible {label} in the file", line)

    for number, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("#") and ("TODO" in stripped or "FIXME" in stripped):
            analyzer.add("info", "todo", "unresolved TODO or FIXME", number)

    summary = {
        "functions": functions,
        "classes": classes,
        "imports": imports,
        "lines": len(source.splitlines()),
    }
    analyzer.metrics = {
        "function_count": len(functions),
        "class_count": len(classes),
        "import_count": len(imports),
        "line_count": int(summary.get("lines", 0)),
        "error_count": len(analyzer.errors),
        "warning_count": len(analyzer.warnings),
    }
    return analyzer, summary


@dataclass
class CodeTools:
    """Static analysis and sandboxed execution as first-class tools."""

    timeout: float = 20.0

    def analyze(self, source: str, *, filename: str = "<source>") -> ToolResult:
        analyzer, summary = analyze_source(source, filename=filename)
        if analyzer.errors and analyzer.errors[0]["code"] == "syntax-error":
            return ToolResult(
                ok=False,
                error=analyzer.errors[0]["message"],
                data={"findings": analyzer.findings, "metrics": analyzer.metrics},
            )
        report = "\n".join(
            f"{f['severity']:>7} {f['code']:<18} line {f['line']}: {f['message']}" for f in analyzer.findings
        )
        return ToolResult(
            ok=True,
            output=report or "no findings",
            data={"findings": analyzer.findings, "metrics": analyzer.metrics, "structure": summary},
        )

    def run(self, code: str, *, timeout: float | None = None, files: dict[str, str] | None = None) -> ToolResult:
        result = run_python(code, timeout=timeout or self.timeout, files=files)
        return ToolResult(
            ok=result.ok,
            output=result.stdout,
            data=result.as_dict(),
            error=result.stderr if not result.ok else "",
            notes=result.notes,
        )

    def register(self, registry: Any) -> None:
        registry.register(
            Tool(
                name="code.analyze",
                description="Static analysis of Python source: structure, risks, and possible secrets.",
                risk=RISK_READ,
                handler=self.analyze,
            )
        )
        registry.register(
            Tool(
                name="code.run",
                description="Run Python source in the sandbox: no network, no inherited secrets, time limited.",
                risk=RISK_EXECUTE,
                scope="compute",
                handler=self.run,
            )
        )
