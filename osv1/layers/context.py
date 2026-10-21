"""The shared context that travels through the six layers.

The context holds the collaborators a layer needs: the memory store, System
One, the language model, the tool registry, the permission and approval
stores, the audit log, the kill switch, and the event sink that the interface
listens to.

Every event emitted here is a real thing that happened in the system. The
interface animation is bound to these events, so it can never show a state
the system is not actually in.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from osv1.config import Settings
from osv1.contracts import new_id
from osv1.engine.llm import LlmClient
from osv1.memory.store import MemoryStore
from osv1.safety.approvals import ApprovalStore
from osv1.safety.audit import AuditLog
from osv1.safety.killswitch import KillSwitch
from osv1.safety.permissions import PermissionStore
from osv1.som import SomEngine
from osv1.tools.registry import ToolRegistry

EventSink = Callable[[dict[str, Any]], None]


@dataclass
class LayerContext:
    """Everything a layer may touch during one request."""

    request_id: str = field(default_factory=lambda: new_id("req"))
    user_id: str = "local"
    mode: str = "plan"  # plan | build
    settings: Settings = field(default_factory=Settings.load)
    memory: MemoryStore = field(default_factory=MemoryStore)
    som: SomEngine = field(default_factory=SomEngine)
    llm: LlmClient = field(default_factory=LlmClient)
    tools: ToolRegistry = field(default_factory=ToolRegistry)
    permissions: PermissionStore = field(default_factory=PermissionStore)
    approvals: ApprovalStore = field(default_factory=ApprovalStore)
    audit: AuditLog = field(default_factory=AuditLog)
    kill_switch: KillSwitch = field(default_factory=KillSwitch)
    events: list[dict[str, Any]] = field(default_factory=list)
    sink: EventSink | None = None
    started_at: float = field(default_factory=time.time)
    facts: list[str] = field(default_factory=list)
    observations: list[str] = field(default_factory=list)

    def emit(self, event: str, **payload: Any) -> dict[str, Any]:
        """Publish a real event to the interface and keep it in the trace."""
        record = {
            "event": event,
            "request_id": self.request_id,
            "at": time.time(),
            **payload,
        }
        self.events.append(record)
        if self.sink is not None:
            # A broken listener must never stop the run.
            with contextlib.suppress(Exception):
                self.sink(record)
        return record

    def elapsed_ms(self) -> float:
        return round((time.time() - self.started_at) * 1000, 2)

    def stopped(self) -> bool:
        """True when the kill switch is engaged."""
        return self.kill_switch.engaged()

    def log_action(self, event: str, *, target: str = "", outcome: str = "ok", **details: Any) -> None:
        self.audit.record(
            event,
            actor=self.user_id,
            target=target,
            outcome=outcome,
            request_id=self.request_id,
            details=details,
        )
