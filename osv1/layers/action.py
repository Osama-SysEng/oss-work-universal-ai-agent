"""Layer 6 — Adaptive Action Engine (spec section 8.6).

Purpose: produce the final answer, decision, code, or action through tools.

Contract: every action has a permission, a log entry, and a rollback path
where one is possible.

Failure handling: a failed action is rolled back where possible and reported
with its log.

The layer is the only place where a tool ever runs, which is what makes the
safety rules enforceable: the kill switch, the permission scopes, and the
human approval for irreversible work are all checked here, in one place.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.contracts import ActionRecord, Plan, PlanStep
from osv1.layers.context import LayerContext
from osv1.layers.world_model import WorldModel
from osv1.safety.permissions import SCOPE_FILES, SCOPE_IRREVERSIBLE, SCOPE_NETWORK, SCOPE_PROGRAMS
from osv1.tools.registry import RISK_IRREVERSIBLE, ToolResult

TOOL_SCOPE = {
    "file.list": SCOPE_FILES,
    "file.read": SCOPE_FILES,
    "file.search": SCOPE_FILES,
    "file.write": SCOPE_FILES,
    "file.move": SCOPE_FILES,
    "file.delete": SCOPE_IRREVERSIBLE,
    "code.analyze": SCOPE_FILES,
    "code.run": SCOPE_PROGRAMS,
    "sheet.read": SCOPE_FILES,
    "sheet.summarize": SCOPE_FILES,
    "sheet.write_csv": SCOPE_FILES,
    "dashboard.build": SCOPE_FILES,
    "format.analyze": SCOPE_FILES,
    "format.synthesize": SCOPE_FILES,
    "office.write": SCOPE_FILES,
    "office.read": SCOPE_FILES,
    "office.deck": SCOPE_FILES,
    "web.read": SCOPE_NETWORK,
    "rea.analyze": SCOPE_FILES,
    "program.run": SCOPE_PROGRAMS,
}

APPROVAL_ACTIONS = {"file.delete": "delete"}


@dataclass
class ActionEngine:
    """Executes a plan under the safety layer."""

    context: LayerContext
    world: WorldModel
    actions: list[ActionRecord] = field(default_factory=list)
    approvals_needed: list[dict[str, Any]] = field(default_factory=list)
    _backups: list[tuple[Path, Path]] = field(default_factory=list)

    # ── helpers ───────────────────────────────────────────────

    def _scope_for(self, step: PlanStep) -> str:
        return TOOL_SCOPE.get(step.tool, SCOPE_FILES)

    def _target_for(self, step: PlanStep) -> str:
        if step.tool in ("file.write", "file.move", "file.delete", "file.read"):
            return step.target
        if step.tool in ("sheet.write_csv", "dashboard.build"):
            return step.target
        if step.tool == "web.read":
            return step.target
        return step.target or "*"

    def _backup_dir(self) -> Path:
        path = Path(self.context.settings.state_dir) / "backups" / self.context.request_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _take_backup(self, step: PlanStep) -> str:
        """Copy a file before it is changed, so the change can be undone."""
        if step.tool not in ("file.write", "sheet.write_csv"):
            return ""
        target = Path(step.target)
        if not target.exists() or not target.is_file():
            return ""
        backup = self._backup_dir() / f"{target.name}.{len(self._backups)}.bak"
        shutil.copy2(target, backup)
        self._backups.append((target, backup))
        return str(backup)

    def _rollback(self) -> list[str]:
        """Undo the changes made so far, newest first."""
        restored: list[str] = []
        for target, backup in reversed(self._backups):
            try:
                shutil.copy2(backup, target)
                restored.append(str(target))
            except OSError:
                continue
        return restored

    # ── execution ─────────────────────────────────────────────

    def execute(self, plan: Plan) -> list[ActionRecord]:
        """Run every step of the plan, in order."""
        context = self.context
        self.actions = []
        self.approvals_needed = []
        for step in plan.steps:
            if context.stopped():
                context.emit("action.halted", reason="the kill switch is engaged")
                self.actions.append(
                    ActionRecord(
                        action=step.action,
                        tool=step.tool,
                        target=step.target,
                        outcome="blocked",
                        detail="the kill switch stopped the run before this step",
                    )
                )
                break

            if not context.tools.has(step.tool):
                self.actions.append(
                    ActionRecord(
                        action=step.action,
                        tool=step.tool,
                        target=step.target,
                        outcome="failed",
                        detail=f"unknown tool: {step.tool}",
                    )
                )
                continue

            tool = context.tools.tool(step.tool)
            scope = self._scope_for(step)
            target = self._target_for(step)

            if tool.risk == RISK_IRREVERSIBLE or scope == SCOPE_IRREVERSIBLE:
                approval = context.approvals.consume(
                    APPROVAL_ACTIONS.get(step.tool, step.action), target, request_id=context.request_id
                )
                if approval is None:
                    request = context.approvals.create(
                        APPROVAL_ACTIONS.get(step.tool, "delete"),
                        target,
                        reason=step.detail or step.action,
                        request_id=context.request_id,
                    )
                    self.approvals_needed.append(request.as_dict())
                    context.emit("action.approval_required", action=step.action, target=target, approval=request.id)
                    self.actions.append(
                        ActionRecord(
                            action=step.action,
                            tool=step.tool,
                            target=target,
                            outcome="blocked",
                            permission="human approval required",
                            detail=f"waiting for approval {request.id}",
                        )
                    )
                    break
                context.emit("action.approved", approval=approval.id, action=step.action)

            if not context.permissions.allows(scope, target) and scope != SCOPE_IRREVERSIBLE:
                self.actions.append(
                    ActionRecord(
                        action=step.action,
                        tool=step.tool,
                        target=target,
                        outcome="blocked",
                        permission=f"no {scope} grant covers this target",
                        detail=f"grant a {scope} scope for {target} to allow this step",
                    )
                )
                context.emit("action.blocked", action=step.action, reason=f"no {scope} grant")
                continue

            backup = self._take_backup(step)
            prediction = self.world.predict(step.tool, target)
            context.emit("action.start", action=step.action, tool=step.tool, target=target)

            result: ToolResult = self._run_tool(step)
            observed = result.output or result.error
            self.world.compare(prediction, observed, ok=result.ok)

            record = ActionRecord(
                action=step.action,
                tool=step.tool,
                target=target,
                outcome="completed" if result.ok else "failed",
                permission=f"{scope}:{target}",
                rollback=result.rollback or (f"restore from {backup}" if backup else ""),
                detail=(result.error or result.output)[:400],
            )
            self.actions.append(record)
            context.log_action(
                "action.executed",
                target=target,
                outcome=record.outcome,
                tool=step.tool,
                action=step.action,
            )
            context.emit(
                "action.done",
                action=step.action,
                tool=step.tool,
                outcome=record.outcome,
            )
            if not result.ok:
                restored = self._rollback()
                if restored:
                    context.emit("action.rolled_back", files=restored)
                    for path in restored:
                        self.actions.append(
                            ActionRecord(
                                action=f"rollback {path}",
                                tool="rollback",
                                target=path,
                                outcome="rolled_back",
                                detail="the file was restored to its previous content",
                            )
                        )
                break
        return self.actions

    def _run_tool(self, step: PlanStep) -> ToolResult:
        arguments: dict[str, Any] = {}
        if step.tool in ("file.read", "file.list", "file.write", "file.move", "file.delete"):
            arguments["path"] = step.target
        elif step.tool == "file.search":
            arguments["pattern"] = step.detail or step.target or "."
            arguments["root"] = step.target or None
        elif step.tool in ("code.analyze",):
            source = step.detail
            filename = step.target or "<source>"
            if not source and step.target:
                # The analysis works on the content, so the file is read first.
                read = self.context.tools.execute("file.read", path=step.target)
                if read.ok:
                    source = read.output
                else:
                    return ToolResult(ok=False, error=f"cannot read {step.target}: {read.error}")
            arguments["source"] = source
            arguments["filename"] = filename
        elif step.tool == "code.run":
            arguments["code"] = step.detail
        elif step.tool in ("sheet.read", "sheet.summarize"):
            arguments["path"] = step.target
        elif step.tool == "sheet.write_csv":
            arguments["path"] = step.target
            arguments["rows"] = _parse_rows(step.detail)
        elif step.tool == "dashboard.build":
            arguments["path"] = step.target
            arguments["title"] = step.detail or "Dashboard"
        elif step.tool == "format.analyze" or step.tool == "format.synthesize":
            arguments["path"] = step.target
        elif step.tool in ("office.write",):
            arguments["name"] = step.target
            arguments["content"] = step.detail
        elif step.tool == "office.read":
            arguments["name"] = step.target
        elif step.tool == "office.deck":
            arguments["title"] = step.detail or "Deck"
            arguments["slides"] = [part for part in (step.target or "").split("\n---") if part.strip()]
        elif step.tool == "web.read":
            arguments["url"] = step.target
        elif step.tool == "rea.analyze":
            arguments["target"] = step.target
            arguments["authorization_basis"] = step.detail
        elif step.tool == "program.run":
            arguments["program"] = step.target
            arguments["arguments"] = step.detail
        try:
            return self.context.tools.execute(step.tool, **arguments)
        except TypeError as exc:
            return ToolResult(ok=False, error=f"the tool rejected the arguments: {exc}")
        except Exception as exc:  # noqa: BLE001 - a tool failure is reported, not raised
            return ToolResult(ok=False, error=str(exc))


def _parse_rows(detail: str) -> list[dict[str, Any]]:
    """Read a JSON list of rows out of a step detail, when there is one."""
    import json

    text = (detail or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        return [data]
    return []
