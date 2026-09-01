"""Explicit safety policy for OSS-Work.

The default release is local-first and simulation-first. Any capability that can
mutate a device or contact an external service requires an explicit approval token.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Decision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"
    SIMULATE = "simulate"


@dataclass(frozen=True)
class PolicyDecision:
    decision: Decision
    reason: str
    action_attempted: bool = False


@dataclass(frozen=True)
class SafetyPolicy:
    simulation_only: bool = True
    require_approval_for_mutation: bool = True
    require_approval_for_external_io: bool = True
    allow_code_execution: bool = False
    allowed_root: str | None = None
    max_file_bytes: int = 1_048_576
    max_output_bytes: int = 65_536
    max_task_seconds: int = 30

    def evaluate(self, capability: str, *, approval: bool = False) -> PolicyDecision:
        mutation = capability in {"file_write", "file_delete", "file_move", "code_execute"}
        external = capability in {"browser_control", "external_message", "webhook_delivery", "skill_install", "update_install"}
        if capability == "code_execute" and not self.allow_code_execution:
            return PolicyDecision(Decision.DENY, "Code execution is disabled in the safe release.")
        if self.simulation_only and external:
            return PolicyDecision(Decision.SIMULATE, "External action is simulation-only in this release.")
        if (mutation and self.require_approval_for_mutation) or (external and self.require_approval_for_external_io):
            if not approval:
                return PolicyDecision(Decision.REQUIRES_APPROVAL, "Explicit approval is required before this action.")
        return PolicyDecision(Decision.ALLOW, "Policy permits the action.")


DEFAULT_POLICY = SafetyPolicy()
