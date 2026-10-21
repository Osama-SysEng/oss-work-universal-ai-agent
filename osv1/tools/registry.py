"""Tool layer: the capabilities OS_V1 can actually execute.

Spec section 7 lists the tool layer as part of the core system: its own
spreadsheet engine, charts, a controlled reader, a code sandbox, and file
tools. Every tool declares a risk level, and the action engine refuses to run
anything without a matching permission (section 19).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

RISK_READ = "read"
RISK_WRITE = "write"
RISK_EXECUTE = "execute"
RISK_EXTERNAL = "external"
RISK_IRREVERSIBLE = "irreversible"

# Actions that need a human decision before they happen (spec section 19).
IRREVERSIBLE_ACTIONS = frozenset({"delete", "send", "pay", "publish", "system_change"})


@dataclass
class ToolResult:
    """The outcome of one tool call."""

    ok: bool
    output: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    reversible: bool = True
    rollback: str = ""
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "output": self.output,
            "data": self.data,
            "error": self.error,
            "reversible": self.reversible,
            "rollback": self.rollback,
            "notes": list(self.notes),
        }


@dataclass
class Tool:
    """A callable capability with a declared risk."""

    name: str
    description: str
    risk: str
    handler: Callable[..., ToolResult]
    requires_approval: bool = False
    reversible: bool = True
    scope: str = "files"  # files | network | programs | compute

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "requires_approval": self.requires_approval,
            "reversible": self.reversible,
            "scope": self.scope,
        }


class ToolRegistry:
    """Holds the tools and refuses unknown ones by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def tool(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"unknown tool: {name}") from None

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return sorted(self._tools)

    def catalog(self) -> list[dict[str, Any]]:
        return [self._tools[name].as_dict() for name in self.names()]

    def execute(self, name: str, **kwargs: Any) -> ToolResult:
        return self.tool(name).handler(**kwargs)
