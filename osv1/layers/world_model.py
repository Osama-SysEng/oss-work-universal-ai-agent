"""Layer 2 — World Model and Memory (spec section 8.2).

Purpose: represent the current state of the user's work and environment, and
the cause and effect of actions, with short and long term memory.

Contract: before executing an action, it predicts the outcome. After
executing, it compares the prediction with reality and corrects itself.

Failure handling: a large gap between prediction and reality lowers
confidence and triggers verification and a smaller next step.
"""

from __future__ import annotations

from dataclasses import dataclass

from osv1.contracts import Prediction, PredictionCheck, WorldState
from osv1.layers.context import LayerContext

# What each tool is expected to change, and what a success looks like.
TOOL_EFFECTS = {
    "file.list": ("lists the entries of a folder", ()),
    "file.read": ("reads the content of a file", ()),
    "file.search": ("finds matches inside files", ()),
    "file.write": ("creates or changes a file", ()),
    "file.move": ("moves a file to another name or folder", ()),
    "file.delete": ("removes a file permanently", ()),
    "code.analyze": ("reports findings about a source file", ()),
    "code.run": ("runs code in the sandbox and returns its output", ()),
    "sheet.read": ("loads a table into the engine", ()),
    "sheet.summarize": ("reports row counts and totals for a table", ()),
    "sheet.write_csv": ("writes a table to a delimited file", ()),
    "dashboard.build": ("writes an interactive dashboard file", ()),
    "format.analyze": ("describes the structure of a file format", ()),
    "format.synthesize": ("writes a generated tool and a smoke test", ()),
    "office.write": ("writes a document into the workspace", ()),
    "office.read": ("reads a document from the workspace", ()),
    "office.deck": ("writes a slide deck into the workspace", ()),
    "web.read": ("fetches a page and returns its text", ()),
    "rea.analyze": ("returns findings about a local target", ()),
}

RISK_BY_TOOL = {
    "file.write": "medium",
    "file.move": "medium",
    "file.delete": "high",
    "code.run": "medium",
    "dashboard.build": "low",
    "format.synthesize": "low",
    "office.write": "low",
    "office.deck": "low",
    "web.read": "medium",
}


@dataclass
class WorldModel:
    """Keeps the state description and the prediction loop."""

    context: LayerContext
    state: WorldState | None = None
    prediction_gap: float = 0.0

    def snapshot(self, bundle_text: str = "", *, open_files: list[str] | None = None) -> WorldState:
        """Describe the current state from the request and from memory."""
        context = self.context
        hits: list[str] = []
        if bundle_text.strip():
            for entry, score in context.memory.retrieve(bundle_text, limit=4):
                hits.append(f"[{entry.kind}] {entry.title or entry.content[:80]} (score {score})")
        facts = list(context.facts)
        self.state = WorldState(
            request_id=context.request_id,
            facts=tuple(facts),
            open_files=tuple(open_files or []),
            recent_events=tuple(event["event"] for event in context.events[-10:]),
            memory_hits=tuple(hits),
            confidence=0.9 if hits else 0.6,
        )
        context.emit(
            "world.snapshot",
            facts=len(self.state.facts),
            memory_hits=len(self.state.memory_hits),
            confidence=self.state.confidence,
        )
        return self.state

    def predict(self, tool: str, target: str = "") -> Prediction:
        """Predict what an action will change before it runs."""
        effect, _ = TOOL_EFFECTS.get(tool, ("produces a result", ()))
        risk = RISK_BY_TOOL.get(tool, "low")
        basis = [f"tool contract: {tool} {effect}"]
        if target:
            basis.append(f"target: {target}")
        if tool == "file.write":
            basis.append("the previous content is recorded, so the change can be undone")
        if tool == "file.delete":
            basis.append("deletion is not reversible, so this one needs approval")
        prediction = Prediction(
            action=f"{tool} {target}".strip(),
            expected_effect=effect,
            expected_files=(target,) if target and tool.startswith("file.") else (),
            risk=risk,
            confidence=0.75 if tool in TOOL_EFFECTS else 0.4,
            basis=tuple(basis),
        )
        self.context.emit("world.predicted", action=prediction.action, risk=risk, confidence=prediction.confidence)
        return prediction

    def compare(self, prediction: Prediction, observed: str, *, ok: bool) -> PredictionCheck:
        """Compare the prediction with reality and record the gap."""
        matched = bool(ok)
        gap = 0.0 if matched else 0.5
        self.prediction_gap = max(self.prediction_gap, gap)
        check = PredictionCheck(
            action=prediction.action,
            predicted=prediction.expected_effect,
            observed=observed[:400] or "no output",
            matched=matched,
            gap=gap,
            note="" if matched else "the result differs from the prediction; verification is required",
        )
        self.context.emit(
            "world.compared",
            action=check.action,
            matched=matched,
            gap=gap,
        )
        if not matched:
            self.context.observations.append(
                f"prediction gap on {check.action}: predicted '{check.predicted}', observed '{check.observed}'"
            )
            # The gap lowers confidence and asks for a smaller next step.
            self.context.som.abstain_threshold = min(0.95, self.context.som.abstain_threshold + 0.1)
        return check

    def state_summary(self) -> str:
        """A short description the reasoner can read."""
        if self.state is None:
            return "no state has been captured yet"
        parts = [f"facts: {len(self.state.facts)}", f"memory hits: {len(self.state.memory_hits)}"]
        if self.state.open_files:
            parts.append(f"open files: {', '.join(self.state.open_files[:5])}")
        return "; ".join(parts)
