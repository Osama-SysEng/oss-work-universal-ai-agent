"""The OS_V1 runtime: the six layers, wired into one request path.

``plan`` produces a proposal the user can approve, change, or reject.
``build`` executes an approved plan, verifies each step, and delivers the
result with its log. Build never starts without a plan, and the verifier is
the last word before anything reaches the user.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.agents.base import AgentRunner
from osv1.agents.domains import DOMAIN_BY_KEY
from osv1.agents.registry import REGISTRY, AgentSpec
from osv1.agents.specializations import SPECIALIZATION_BY_KEY
from osv1.config import DEVICE_TIERS, Settings
from osv1.context import ContextWindow
from osv1.contracts import TaskResult, utc_now
from osv1.engine.llm import LlmClient
from osv1.eval.metrics import RunMetrics
from osv1.layers.action import ActionEngine
from osv1.layers.context import LayerContext
from osv1.layers.decision import DecisionEngine
from osv1.layers.input_layer import InputLayer
from osv1.layers.reasoning import ReasoningEngine
from osv1.layers.world_model import WorldModel
from osv1.memory.store import MemoryStore
from osv1.provenance import ProvenanceRegistry
from osv1.safety.approvals import ApprovalStore
from osv1.safety.audit import AuditLog
from osv1.safety.killswitch import KillSwitch
from osv1.safety.permissions import SCOPE_FILES, PermissionStore
from osv1.som import SomQuestion, build_som
from osv1.tools.app_synthesis import AppSynthesis
from osv1.tools.browser_tools import register as browser_tools_register
from osv1.tools.code_tools import CodeTools
from osv1.tools.dashboard import DashboardTools
from osv1.tools.file_tools import FileTools
from osv1.tools.office import Office
from osv1.tools.office import register as office_register
from osv1.tools.program_tools import ProgramRunner, allowlist_from_env
from osv1.tools.rea import ReaEngine
from osv1.tools.registry import ToolRegistry
from osv1.tools.sandbox import run_python
from osv1.tools.spreadsheet import SpreadsheetTools


@dataclass
class OSRuntime:
    """One running instance of OS_V1, bound to one user."""

    settings: Settings = field(default_factory=Settings.load)
    user_id: str = "local"
    sink: Callable[[dict[str, Any]], None] | None = None
    context: LayerContext | None = None
    metrics: RunMetrics = field(default_factory=RunMetrics)

    def __post_init__(self) -> None:
        self.settings.ensure_dirs()
        self.engine = LlmClient()
        self.som = build_som(
            engine=self.engine,
            laya_model=self.settings.laya_model,
            abstain_threshold=self.settings.som_abstain_threshold,
        )
        self.memory = MemoryStore(path=self.settings.memory_db_path, user_id=self.user_id)
        self.permissions = PermissionStore(path=self.settings.data_dir / "permissions.json").load()
        self.approvals = ApprovalStore(path=self.settings.data_dir / "approvals.json").load()
        self.audit = AuditLog(path=self.settings.audit_log).load()
        self.kill_switch = KillSwitch(path=self.settings.kill_switch_file)
        self.provenance = ProvenanceRegistry(path=self.settings.data_dir / "provenance.json").load()
        self.tools = ToolRegistry()
        self._register_tools()
        self._grant_workspace()

    # ── wiring ────────────────────────────────────────────────

    def _register_tools(self) -> None:
        roots = [self.settings.workspace_dir, self.settings.data_dir, Path.cwd()]
        file_tools = FileTools(allowed_roots=[Path(root) for root in roots], max_bytes=self.settings.max_file_bytes)
        file_tools.register(self.tools)
        CodeTools().register(self.tools)
        SpreadsheetTools().register(self.tools)
        DashboardTools().register(self.tools)
        browser_tools_register(self.tools)
        AppSynthesis(skills_dir=Path(self.settings.skills_dir)).register(self.tools)
        ReaEngine().register(self.tools)
        office_register(self.tools, Office(settings=self.settings))
        ProgramRunner(
            allowlist=allowlist_from_env(),
            workspace=Path(self.settings.workspace_dir),
            max_output_bytes=self.settings.max_output_bytes,
        ).register(self.tools)

    def _grant_workspace(self) -> None:
        """The workspace, the data directory, and the working folder are granted."""
        for root in (self.settings.workspace_dir, self.settings.data_dir, Path.cwd()):
            target = str(Path(root).resolve())
            if not self.permissions.allows(SCOPE_FILES, target):
                self.permissions.grant(SCOPE_FILES, target, by="system", readonly=False)

    # ── context ───────────────────────────────────────────────

    def new_context(self, mode: str = "plan") -> LayerContext:
        context = LayerContext(
            user_id=self.user_id,
            mode=mode,
            settings=self.settings,
            memory=self.memory,
            som=self.som,
            llm=self.engine,
            tools=self.tools,
            permissions=self.permissions,
            approvals=self.approvals,
            audit=self.audit,
            kill_switch=self.kill_switch,
            sink=self.sink,
        )
        self.context = context
        return context

    # ── routing ───────────────────────────────────────────────

    def route(self, task: str) -> tuple[AgentSpec | None, dict[str, Any]]:
        """System One routes first (spec section 9); the registry backs it up."""
        domain_labels = tuple(DOMAIN_BY_KEY)
        domain_decision = self.som.ask(
            SomQuestion(
                kind="choice",
                text=task,
                labels=domain_labels,
                context={"keywords": {key: DOMAIN_BY_KEY[key].keywords for key in domain_labels}},
            ),
            record=False,
        )
        spec_labels = tuple(SPECIALIZATION_BY_KEY)
        spec_decision = self.som.ask(
            SomQuestion(
                kind="choice",
                text=task,
                labels=spec_labels,
                context={"keywords": {key: SPECIALIZATION_BY_KEY[key].keywords for key in spec_labels}},
            ),
            record=False,
        )
        fallback_agent, fallback_info = REGISTRY.route(task)
        domain_key = domain_decision.value if domain_decision.value in DOMAIN_BY_KEY else fallback_info["domain"]
        spec_key = (
            spec_decision.value if spec_decision.value in SPECIALIZATION_BY_KEY else fallback_info["specialization"]
        )
        agent = next(
            (
                candidate
                for candidate in REGISTRY.all()
                if candidate.domain.key == domain_key and candidate.specialization.key == spec_key
            ),
            fallback_agent,
        )
        return agent, {
            "som_domain": domain_decision.value,
            "som_domain_confidence": round(domain_decision.confidence, 3),
            "som_specialization": spec_decision.value,
            "som_specialization_confidence": round(spec_decision.confidence, 3),
            "keyword_routing": fallback_info,
            "chosen": agent.id if agent else "",
        }

    # ── the request path ──────────────────────────────────────

    def plan(self, task: str, *, agent_id: str = "") -> TaskResult:
        """Produce a plan. Nothing is executed."""
        return self._run(task, mode="plan", agent_id=agent_id)

    def build(self, task: str, *, agent_id: str = "") -> TaskResult:
        """Execute an approved plan, verify it, and deliver the result."""
        return self._run(task, mode="build", agent_id=agent_id)

    def _run(self, task: str, *, mode: str, agent_id: str) -> TaskResult:
        context = self.new_context(mode)
        metrics = RunMetrics()
        self.metrics = metrics
        result = TaskResult(request_id=context.request_id, status="failed")
        started = time.time()

        if self.kill_switch.engaged():
            result.status = "blocked"
            result.errors.append("the kill switch is engaged: nothing runs until it is released")
            context.emit("runtime.blocked", reason="kill switch")
            return result

        # 8.1 Multimodal Input
        bundle = InputLayer().from_task(context, task)

        # Spec section 10: the window scales with the device tier, and an
        # overflow is summarized from memory rather than dropped silently.
        window = ContextWindow(
            window_tokens=self.settings.context_tokens,
            reserve_for_output=max(1, min(8_000, self.settings.context_tokens // 8)),
            summarizer=self.engine,
        )
        context_plan = window.fit([(item.source, item.payload) for item in bundle.inputs])
        context.emit(
            "context.fitted",
            window_tokens=context_plan.window_tokens,
            used_tokens=context_plan.used_tokens,
            overflowed=context_plan.overflowed,
        )

        world = WorldModel(context=context)
        world.snapshot(context_plan.text())

        # 8.3 Reasoning Engine
        reasoning = ReasoningEngine(context=context)
        hypotheses = reasoning.settle(task, state_summary=world.state_summary())
        metrics.paths_explored = reasoning.breadth()
        metrics.plans_scored = len(hypotheses)

        # 8.4 Decision Engine
        decision_engine = DecisionEngine(context=context)
        options = decision_engine.options_from_hypotheses(hypotheses)
        decision = decision_engine.decide(options, goal=task)
        metrics.record_decision(decision.confidence, decision.outcome == "decide")

        agent, routing = self.route(task)
        if agent_id:
            chosen = REGISTRY.get(agent_id)
            if chosen is not None:
                agent = chosen
                routing["chosen"] = chosen.id
                routing["requested"] = agent_id
        if agent is None:
            result.status = "failed"
            result.errors.append("no agent could be chosen for this request")
            return result

        result.decision = decision
        result.metrics["routing"] = routing
        result.metrics["agent"] = agent.as_dict()
        result.metrics["context"] = context_plan.as_dict()

        if decision.outcome == "ask_user":
            result.status = "needs_information"
            result.answer = decision.question
            result.errors.append("the decision engine needs more information before acting")
            metrics.finished_at = time.time()
            result.metrics["metrics"] = metrics.as_reports()
            result.finished_at = utc_now()
            return result

        # Plan (8.6 prepares it; the agent runner builds it)
        runner = AgentRunner(context=context)
        plan = runner.build_plan(task, agent)
        result.plan = plan

        if mode == "plan":
            result.status = "planned"
            result.answer = (
                f"Plan for '{task[:120]}' using agent {agent.id} — {agent.title}. "
                f"Steps: {len(plan.steps)}. Nothing was executed."
            )
            context.emit("plan.delivered", agent=agent.id, steps=len(plan.steps))
            metrics.finished_at = time.time()
            result.metrics["metrics"] = metrics.as_reports()
            result.finished_at = utc_now()
            return result

        # 8.6 Adaptive Action Engine
        engine = ActionEngine(context=context, world=world)
        actions = engine.execute(plan)
        result.actions = tuple(actions)

        if engine.approvals_needed:
            result.status = "needs_approval"
            result.answer = "The plan contains an irreversible step that needs your approval."
            result.data["approvals"] = engine.approvals_needed
            metrics.finished_at = time.time()
            result.metrics["metrics"] = metrics.as_reports()
            result.finished_at = utc_now()
            return result

        # 8.5 Verifier
        answer, answer_source = runner.answer_from(agent, plan, actions, task)
        verification = runner.verify_agent(
            agent,
            answer=answer,
            goal=task,
            plan=plan,
            actions=actions,
            confidence=[decision.confidence, plan.confidence],
        )
        result.verification = verification
        result.answer = answer
        result.data["answer_source"] = answer_source
        result.data["tools_used"] = [action.tool for action in actions]
        result.data["plan_source"] = runner.plan_source

        # 8.2 memory: record the experience, and the lesson when it worked
        succeeded = all(action.outcome in ("completed", "rolled_back") for action in actions)
        self.memory.add_experience(
            f"task: {task[:200]}",
            predicted=plan.rationale[:300],
            observed="; ".join(action.detail[:120] for action in actions)[:300],
            lesson="the plan held" if succeeded else "the plan did not hold",
            title=agent.title,
        )
        if succeeded and actions:
            self.memory.add_skill(
                name=f"{agent.domain.key}-{agent.specialization.key}",
                procedure=f"use agent {agent.id} for {agent.domain.title.lower()} work",
                conditions=task[:150],
                tests="the plan ran and the verifier passed",
            )

        result.status = "completed" if verification.passed else "failed"
        if not verification.passed:
            result.errors.extend(verification.reasons)
        metrics.finished_at = time.time()
        result.metrics["metrics"] = metrics.as_reports()
        result.metrics["elapsed_s"] = round(time.time() - started, 3)
        result.metrics["prediction_quality"] = world.prediction_quality()
        result.finished_at = utc_now()
        context.log_action("request.completed", target=task[:120], outcome=result.status)
        return result

    # ── introspection ─────────────────────────────────────────

    def status(self) -> dict[str, Any]:
        """What the system can do right now, measured rather than claimed."""
        engine_healthy = self.engine.healthy()
        return {
            "product": "OSS Work",
            "model": "OS_V1",
            "version": self.settings.describe(),
            "engine": {
                "url": self.settings.engine_url,
                "model": self.settings.engine_model,
                "healthy": engine_healthy,
                "source": "local llama.cpp server" if engine_healthy else "not running",
            },
            "agents": len(REGISTRY),
            "tools": self.tools.names(),
            "memory": self.memory.stats(),
            "permissions": self.permissions.list_grants(),
            "pending_approvals": [request.as_dict() for request in self.approvals.pending()],
            "kill_switch": self.kill_switch.status(),
            "audit": self.audit.verify_chain(),
            "som": self.som.stats(),
            "provenance": self.provenance.report(),
            "tiers": {key: tier.note for key, tier in DEVICE_TIERS.items()},
        }

    def run_python(self, code: str, *, timeout: float = 20.0) -> dict[str, Any]:
        """Run code in the sandbox. Used by the CLI and the API."""
        return run_python(code, timeout=timeout).as_dict()
