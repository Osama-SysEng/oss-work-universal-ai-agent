"""Layer 3 — Reasoning Engine (spec section 8.3).

Purpose: analysis, planning, and inference.

Contract: it builds hypotheses, derives their consequences, and tests them
with tools or simulation, instead of only producing a plausible answer.

Failure handling: if a test contradicts a hypothesis, the hypothesis is
dropped and the next candidate is tried. The layer reports how many
hypotheses it opened, tested, kept, and dropped, because "search breadth" is
one of the five measurable metrics in spec section 11.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from osv1.contracts import Hypothesis, new_id
from osv1.layers.context import LayerContext

PROBE_PATTERNS = (
    (re.compile(r"read\s+(?:the\s+)?file\s+[\"'`]?([^\s\"'`]+)", re.I), "file.read"),
    (re.compile(r"search\s+for\s+[\"'`]?([^\s\"'`]+)", re.I), "file.search"),
    (re.compile(r"list\s+(?:the\s+)?(?:folder|directory)\s+[\"'`]?([^\s\"'`]*)", re.I), "file.list"),
    (re.compile(r"run\s+(?:the\s+)?code", re.I), "code.run"),
    (re.compile(r"analyz\w*\s+([^\s\"'`]+)", re.I), "code.analyze"),
)

FALLBACK_HYPOTHESES = (
    (
        "the request needs the current state of the files before anything can be decided",
        ("without the current state the plan is a guess",),
        "read the files the request names",
    ),
    (
        "the request can be satisfied by a local, reversible change",
        ("the original file stays untouched when the work happens on a copy",),
        "list the folder the request names",
    ),
    (
        "the result can be checked against the data it came from",
        ("a result that cannot be recomputed is a result nobody can trust",),
        "search for the values the result should contain",
    ),
)


@dataclass
class ReasoningEngine:
    """Hypotheses, consequences, and the tests that settle them."""

    context: LayerContext
    hypotheses: list[Hypothesis] = field(default_factory=list)
    tested: int = 0
    dropped: int = 0

    # ── hypotheses ────────────────────────────────────────────

    def hypothesize(self, task: str, *, state_summary: str = "", count: int = 3) -> list[Hypothesis]:
        """Produce candidate hypotheses for the task."""
        context = self.context
        generated = context.llm.hypotheses(task, state_summary=state_summary, count=count)
        hypotheses: list[Hypothesis] = []
        if generated:
            for item in generated:
                hypotheses.append(
                    Hypothesis(
                        id=new_id("hyp"),
                        statement=item["statement"],
                        consequences=tuple(item["consequences"]),
                        test=item["test"],
                        confidence=0.4,
                        status="open",
                    )
                )
            source = "local_engine"
        else:
            for statement, consequences, test in FALLBACK_HYPOTHESES[:count]:
                hypotheses.append(
                    Hypothesis(
                        id=new_id("hyp"),
                        statement=statement,
                        consequences=tuple(consequences),
                        test=test,
                        confidence=0.3,
                        status="open",
                    )
                )
            source = "rules"
        self.hypotheses = hypotheses
        context.emit(
            "reasoning.hypotheses",
            count=len(hypotheses),
            source=source,
            statements=[hypothesis.statement[:120] for hypothesis in hypotheses],
        )
        return hypotheses

    # ── tests ─────────────────────────────────────────────────

    def probe_for(self, hypothesis: Hypothesis) -> tuple[str, dict[str, Any]] | None:
        """Find a read-only probe that can settle the hypothesis."""
        for pattern, tool in PROBE_PATTERNS:
            match = pattern.search(hypothesis.test or "")
            if not match:
                continue
            argument = match.group(1).strip().strip(".,;:")
            if tool == "file.read":
                return tool, {"path": argument}
            if tool == "file.search":
                return tool, {"pattern": argument}
            if tool == "file.list":
                return tool, {"path": argument} if argument else {}
            if tool == "code.analyze":
                return tool, {"source": argument}
        return None

    def test(self, hypothesis: Hypothesis) -> Hypothesis:
        """Run the probe. A contradicted hypothesis is dropped."""
        context = self.context
        probe = self.probe_for(hypothesis)
        self.tested += 1
        if probe is None:
            hypothesis = self._replace(hypothesis, status="open", confidence=0.35)
            context.emit("reasoning.tested", hypothesis=hypothesis.statement[:100], probe="none")
            return hypothesis
        tool, arguments = probe
        if not context.tools.has(tool):
            hypothesis = self._replace(hypothesis, status="open", confidence=0.3)
            context.emit("reasoning.tested", hypothesis=hypothesis.statement[:100], probe=tool, outcome="tool-missing")
            return hypothesis
        try:
            result = context.tools.execute(tool, **arguments)
        except Exception as exc:  # noqa: BLE001 - a failed probe is a result, not a crash
            hypothesis = self._replace(hypothesis, status="refuted", confidence=0.1)
            self.dropped += 1
            context.emit(
                "reasoning.tested", hypothesis=hypothesis.statement[:100], probe=tool, outcome="error", error=str(exc)
            )
            return hypothesis
        supported = bool(result.ok) and bool(result.output.strip())
        status = "supported" if supported else "refuted"
        confidence = 0.65 if supported else 0.15
        hypothesis = self._replace(
            hypothesis,
            status=status,
            confidence=confidence,
            supported_by=(result.output[:200],) if supported else (),
        )
        if not supported:
            self.dropped += 1
        context.emit(
            "reasoning.tested",
            hypothesis=hypothesis.statement[:100],
            probe=tool,
            outcome=status,
        )
        return hypothesis

    @staticmethod
    def _replace(
        hypothesis: Hypothesis,
        *,
        status: str | None = None,
        confidence: float | None = None,
        supported_by: tuple[str, ...] | None = None,
    ) -> Hypothesis:
        return Hypothesis(
            id=hypothesis.id,
            statement=hypothesis.statement,
            consequences=hypothesis.consequences,
            test=hypothesis.test,
            supported_by=supported_by if supported_by is not None else hypothesis.supported_by,
            confidence=confidence if confidence is not None else hypothesis.confidence,
            status=status if status is not None else hypothesis.status,
        )

    def settle(self, task: str, *, state_summary: str = "") -> list[Hypothesis]:
        """Hypothesize, then test each one until a supported one is found."""
        self.hypothesize(task, state_summary=state_summary)
        for hypothesis in list(self.hypotheses):
            if hypothesis.status != "open":
                continue
            updated = self.test(hypothesis)
            self.hypotheses = [updated if item.id == updated.id else item for item in self.hypotheses]
            if updated.status == "supported":
                break
        supported = [hypothesis for hypothesis in self.hypotheses if hypothesis.status == "supported"]
        self.context.emit(
            "reasoning.settled",
            opened=len(self.hypotheses),
            tested=self.tested,
            supported=len(supported),
            dropped=self.dropped,
        )
        return self.hypotheses

    @property
    def supported(self) -> list[Hypothesis]:
        return [hypothesis for hypothesis in self.hypotheses if hypothesis.status == "supported"]

    def breadth(self) -> int:
        """How many paths were explored and scored (spec section 11)."""
        return len(self.hypotheses)
