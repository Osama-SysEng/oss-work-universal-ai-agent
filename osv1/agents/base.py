"""The agent runner: how a specialized agent actually works.

An agent receives a task, builds a plan, and — only in Build mode — runs that
plan through the action engine under the safety layer. Then the verifier
checks the result against the agent's own rules, and the answer is delivered
with the evidence trail behind it.

The plan comes from the language model when the local engine is up, and from
the agent's plan template otherwise. Either way the plan names real tools,
and the answer always says which of the two produced it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from osv1.agents.registry import AgentSpec
from osv1.contracts import Plan, PlanStep, new_id
from osv1.layers.context import LayerContext
from osv1.layers.verifier import Verifier

PATH_PATTERN = re.compile(
    r"[\w./\\-]+\.(?:py|md|txt|json|ya?ml|toml|csv|tsv|html?|css|js|jsx|ts|tsx|sql|log|db|sqlite3?|xml|ini|cfg)"
)
URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+")
CODE_SUFFIXES = (
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".c",
    ".h",
    ".cpp",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".php",
    ".swift",
    ".kt",
)


def applicable(tool: str, target: str) -> bool:
    """Whether a step makes sense for this target.

    Asking a code analyzer to read a Markdown file is not a task, it is a
    mistake, and it would fail the run for no reason. Such a step is left
    out of the plan instead.
    """
    if tool != "code.analyze":
        return True
    if not target:
        return False
    return Path(target).suffix.lower() in CODE_SUFFIXES


TOOL_ARGUMENTS = {
    "file.list": ("path",),
    "file.read": ("path",),
    "file.search": ("pattern", "root"),
    "file.write": ("path",),
    "file.move": ("path",),
    "file.delete": ("path",),
    "code.analyze": ("source",),
    "code.run": ("code",),
    "sheet.read": ("path",),
    "sheet.summarize": ("path",),
    "sheet.write_csv": ("path",),
    "dashboard.build": ("path",),
    "format.analyze": ("path",),
    "format.synthesize": ("path",),
    "office.write": ("name",),
    "office.read": ("name",),
    "office.deck": ("title",),
    "web.read": ("url",),
    "rea.analyze": ("target",),
}


def extract_targets(task: str) -> tuple[list[str], list[str]]:
    """Pull file paths and URLs out of a request."""
    paths = [match.group(0) for match in PATH_PATTERN.finditer(task)]
    urls = [match.group(0) for match in URL_PATTERN.finditer(task)]
    return list(dict.fromkeys(paths)), list(dict.fromkeys(urls))


@dataclass
class AgentRunner:
    """Runs one specialized agent against one request."""

    context: LayerContext
    plan_source: str = "template"

    def build_plan(self, task: str, agent: AgentSpec) -> Plan:
        """Build the plan for this agent and task."""
        context = self.context
        paths, urls = extract_targets(task)
        tools = list(agent.capabilities)
        steps: list[PlanStep] = []

        generated = context.llm.plan(task, agent_prompt=agent.focus, available_tools=tools)
        if generated["source"] == "local_engine" and generated["steps"]:
            self.plan_source = "local_engine"
            for index, step in enumerate(generated["steps"], start=1):
                tool = step.get("tool") or ""
                if tool not in tools:
                    tool = tools[0] if tools else "file.read"
                target = step.get("target") or (paths[0] if paths else (urls[0] if urls else ""))
                if not applicable(tool, target):
                    continue
                steps.append(
                    PlanStep(
                        id=f"step-{index}",
                        action=step.get("action") or f"run {tool}",
                        tool=tool,
                        target=target,
                        detail=step.get("detail", ""),
                        requires_approval=tool == "file.delete",
                        reversible=tool != "file.delete",
                        rollback="restore the previous content" if tool == "file.write" else "",
                    )
                )
            rationale = generated["rationale"]
        else:
            self.plan_source = "template"
            rationale = f"{agent.specialization.title} plan for {agent.domain.title}."
            for index, (tool, intent) in enumerate(agent.plan_template, start=1):
                if tool not in tools:
                    continue
                target = ""
                if tool.startswith("file.") or tool.startswith("sheet.") or tool.startswith("dashboard."):
                    target = paths[0] if paths else ""
                elif tool == "web.read":
                    target = urls[0] if urls else ""
                elif tool == "code.analyze":
                    target = paths[0] if paths else ""
                if not applicable(tool, target):
                    # The step does not fit the target, so it is left out
                    # rather than run and failed.
                    continue
                steps.append(
                    PlanStep(
                        id=f"step-{index}",
                        action=f"{intent} ({tool})",
                        tool=tool,
                        target=target,
                        detail="",
                        requires_approval=tool == "file.delete",
                        reversible=tool != "file.delete",
                        rollback="restore the previous content" if tool == "file.write" else "",
                    )
                )

        if not steps:
            steps.append(
                PlanStep(
                    id="step-1",
                    action="report what is available",
                    tool="file.list",
                    target=paths[0] if paths else "",
                    detail="",
                )
            )

        plan = Plan(
            id=new_id("plan"),
            request_id=context.request_id,
            mode=context.mode,
            goal=task,
            steps=tuple(steps),
            rationale=rationale,
            agent_id=agent.id,
            agent_title=agent.title,
            confidence=0.6,
            requires_approval=any(step.requires_approval for step in steps),
        )
        context.emit(
            "plan.ready",
            agent=agent.id,
            steps=len(steps),
            source=self.plan_source,
        )
        return plan

    def answer_from(self, agent: AgentSpec, plan: Plan, actions: list[Any], goal: str) -> tuple[str, str]:
        """Compose the answer. Says whether a model or the rules wrote it."""
        context = self.context
        successes = [action for action in actions if action.outcome == "completed"]
        evidence = [f"- {action.action}: {action.detail[:200]}" for action in successes]
        blocked = [action for action in actions if action.outcome == "blocked"]

        if context.llm.healthy():
            prompt = (
                "Write the final answer to the task below. Use only the evidence given. "
                "State plainly what was done, what was not done, and what is uncertain.\n\n"
                f"Task: {goal}\n\nAgent: {agent.title}\n"
                f"Plan: {plan.rationale}\n\nEvidence:\n" + "\n".join(evidence or ["no tool produced output"])
            )
            result = context.llm.complete(prompt, max_tokens=600)
            if result["source"] == "local_engine" and result["content"].strip():
                text = result["content"].strip()
                if blocked:
                    text += "\n\nNot done (blocked by the safety layer):\n" + "\n".join(
                        f"- {action.action}: {action.detail}" for action in blocked
                    )
                return text, "local_engine"

        lines = [f"{agent.specialization.deliverable.capitalize()}:", ""]
        if evidence:
            lines.extend(evidence)
        else:
            lines.append("- no tool produced output for this request")
        if blocked:
            lines.append("")
            lines.append("Blocked by the safety layer:")
            lines.extend(f"- {action.action}: {action.detail}" for action in blocked)
        lines.append("")
        lines.append(f"Agent: {agent.id} — {agent.title}")
        lines.append(f"Planned steps: {len(plan.steps)} (plan source: {self.plan_source})")
        return "\n".join(lines), "rules"

    def verify_agent(
        self, agent: AgentSpec, *, answer: str, goal: str, plan: Plan, actions: list[Any], confidence: list[float]
    ) -> Any:
        """Run the verifier and add the agent's own rules as extra checks."""
        verifier = Verifier(context=self.context)
        verification = verifier.verify(
            answer=answer,
            goal=goal,
            plan=plan,
            actions=actions,
            confidence_values=confidence,
        )
        missing_rules = [
            rule
            for rule in agent.verify_rules
            if rule.startswith("the answer names the files") and "names the files" not in answer
        ]
        if missing_rules:
            from osv1.contracts import Check

            verification = type(verification)(
                passed=False,
                checks=verification.checks
                + (
                    Check(
                        name="agent-rules",
                        passed=False,
                        detail="the agent's own rule was not met: " + missing_rules[0],
                        evidence=(agent.id,),
                    ),
                ),
                uncertainty=verification.uncertainty,
                reasons=verification.reasons + tuple(missing_rules),
                uncertainty_note=verification.uncertainty_note,
            )
        self.context.emit(
            "verification.agent_rules",
            agent=agent.id,
            passed=verification.passed,
        )
        return verification
