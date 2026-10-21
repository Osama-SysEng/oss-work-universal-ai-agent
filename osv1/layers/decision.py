"""Layer 4 — Decision Engine (spec section 8.4).

Purpose: choose between options using probabilities and trade-offs.

Contract: it computes the probability and cost of each option, refuses to
decide when the evidence is insufficient, and asks for information when the
value of that information is greater than the cost of waiting.

Failure handling: when System One abstains, the decision engine asks the
user or searches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from osv1.contracts import Decision, Option
from osv1.layers.context import LayerContext
from osv1.som import SomQuestion


@dataclass
class DecisionEngine:
    """Scores the options and decides, abstains, or asks."""

    context: LayerContext
    min_probability: float = 0.35
    min_options: int = 2

    def options_from_hypotheses(self, hypotheses: list[Any]) -> list[Option]:
        """Turn the surviving hypotheses into options."""
        options: list[Option] = []
        for hypothesis in hypotheses:
            if getattr(hypothesis, "status", "") not in ("supported", "open"):
                continue
            options.append(
                Option(
                    id=hypothesis.id,
                    label=hypothesis.statement[:120],
                    probability=float(hypothesis.confidence),
                    cost=0.5,
                    impact=1.0,
                    detail="; ".join(hypothesis.consequences[:3]),
                )
            )
        options.append(
            Option(
                id="ask",
                label="ask the user for the missing information",
                probability=0.5,
                cost=0.2,
                impact=0.8,
                detail="the cost of waiting is lower than the cost of a wrong guess",
            )
        )
        return options

    def decide(self, options: list[Option], *, goal: str = "") -> Decision:
        """Choose, abstain, or ask."""
        context = self.context
        if not options:
            return Decision(
                outcome="abstain",
                rationale="no option was available, so there was nothing to decide between",
                confidence=0.0,
            )

        # System One has the first word on risk and guardrails.
        risk = context.som.ask(
            SomQuestion(
                kind="yes_no",
                text=f"is the decision for '{goal}' safe to take without asking the user?",
                positive=("safe", "read-only", "reversible", "local", "verified"),
                negative=("delete", "publish", "send", "pay", "irreversible", "external"),
            )
        )
        best = max(options, key=lambda option: option.expected_value)
        probabilities = [option.probability for option in options]
        total = sum(probabilities) or 1.0
        normalized = [probability / total for probability in probabilities]
        best_probability = normalized[options.index(best)]

        information_value = (1.0 - best_probability) * best.impact
        cost_of_waiting = 0.15
        evidence_is_thin = best_probability < self.min_probability or len(options) < self.min_options

        if evidence_is_thin or risk.abstained:
            question = self._question_for(goal, options)
            if information_value > cost_of_waiting:
                context.emit(
                    "decision.ask",
                    question=question,
                    information_value=round(information_value, 3),
                    cost_of_waiting=cost_of_waiting,
                )
                return Decision(
                    outcome="ask_user",
                    options=tuple(options),
                    rationale=(
                        "the evidence does not separate the options clearly enough, and the value of "
                        "asking is higher than the cost of waiting"
                    ),
                    information_value=information_value,
                    cost_of_waiting=cost_of_waiting,
                    question=question,
                    confidence=best_probability,
                )
            context.emit("decision.abstain", reason="insufficient evidence")
            return Decision(
                outcome="abstain",
                options=tuple(options),
                rationale="the evidence is too thin to choose, and asking would cost more than the decision",
                information_value=information_value,
                cost_of_waiting=cost_of_waiting,
                confidence=best_probability,
            )

        context.emit(
            "decision.decide",
            option=best.label[:100],
            probability=round(best_probability, 3),
        )
        return Decision(
            outcome="decide",
            option=best,
            options=tuple(options),
            rationale=f"highest expected value ({best.expected_value:.2f}) with probability {best_probability:.2f}",
            information_value=information_value,
            cost_of_waiting=cost_of_waiting,
            confidence=best_probability,
        )

    def _question_for(self, goal: str, options: list[Option]) -> str:
        labels = [option.label for option in options[:3]]
        return f"to finish '{goal[:80]}', which of these should it do? " + " | ".join(labels)
