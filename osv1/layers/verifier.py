"""Layer 5 — Verifier and Uncertainty Engine (spec section 8.5).

Purpose: test evidence, detect errors, and estimate uncertainty.

Contract: it is independent of the Reasoning Engine. If verification fails,
control returns to reasoning or to evidence gathering. Telling the model to
"think again" is not enough.

Independence in practice: the verifier never reads the reasoner's claims as
evidence. It re-derives the facts from the artifacts — the files that were
written, the rows that were counted, the tool results that were recorded —
and compares them with what the answer promises. When it cannot re-derive a
claim, it says so instead of passing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from osv1.contracts import ActionRecord, Check, Plan, Verification
from osv1.layers.context import LayerContext

WORD = re.compile(r"[a-z0-9_]+")


@dataclass
class Verifier:
    """Independent checks over the artifacts, not over the reasoning."""

    context: LayerContext
    checks: list[Check] = field(default_factory=list)

    # ── individual checks ─────────────────────────────────────

    def check_actions(self, actions: list[ActionRecord]) -> Check:
        """Every action that was supposed to work must have worked."""
        if not actions:
            return Check(name="actions", passed=True, detail="no action was executed", evidence=())
        failed = [action for action in actions if action.outcome not in ("completed", "rolled_back")]
        blocked = [action for action in actions if action.outcome == "blocked"]
        if failed:
            return Check(
                name="actions",
                passed=False,
                detail=f"{len(failed)} of {len(actions)} actions did not complete",
                evidence=tuple(f"{action.action}: {action.outcome}" for action in failed[:6]),
            )
        return Check(
            name="actions",
            passed=True,
            detail=f"{len(actions)} actions completed"
            + (f", {len(blocked)} were blocked by policy" if blocked else ""),
            evidence=tuple(action.action for action in actions[:6]),
        )

    def check_artifacts(self, plan: Plan | None) -> Check:
        """A file the plan promised must exist and must not be empty."""
        if plan is None:
            return Check(name="artifacts", passed=True, detail="no plan to check")
        written = [
            step
            for step in plan.steps
            if step.tool in ("file.write", "sheet.write_csv", "dashboard.build", "format.synthesize")
        ]
        if not written:
            return Check(name="artifacts", passed=True, detail="the plan produced no file")
        missing: list[str] = []
        empty: list[str] = []
        for step in written:
            path = Path(step.target)
            if not path.exists():
                missing.append(str(path))
            elif path.is_file() and path.stat().st_size == 0:
                empty.append(str(path))
        if missing or empty:
            return Check(
                name="artifacts",
                passed=False,
                detail=f"{len(missing)} promised files are missing, {len(empty)} are empty",
                evidence=tuple(missing + empty),
            )
        return Check(
            name="artifacts",
            passed=True,
            detail=f"{len(written)} promised files exist and are not empty",
            evidence=tuple(step.target for step in written),
        )

    def check_answer(self, answer: str, goal: str) -> Check:
        """The answer has to address the goal, not just exist."""
        if not answer.strip():
            return Check(name="answer", passed=False, detail="the answer is empty")
        goal_tokens = set(WORD.findall(goal.lower())) - {
            "the",
            "a",
            "an",
            "of",
            "and",
            "to",
            "in",
            "for",
            "this",
            "that",
        }
        if not goal_tokens:
            return Check(name="answer", passed=True, detail="the goal has no content words to check")
        answer_tokens = set(WORD.findall(answer.lower()))
        overlap = len(goal_tokens & answer_tokens) / len(goal_tokens)
        if overlap < 0.15:
            return Check(
                name="answer",
                passed=False,
                detail=f"the answer covers only {overlap:.0%} of the goal's content words",
                evidence=tuple(sorted(goal_tokens - answer_tokens)[:8]),
            )
        return Check(
            name="answer",
            passed=True,
            detail=f"the answer covers {overlap:.0%} of the goal's content words",
            evidence=(),
        )

    def check_uncertainty(self, confidence_values: list[float]) -> Check:
        """Report the uncertainty the decision and the verifier agreed on."""
        if not confidence_values:
            return Check(name="uncertainty", passed=True, detail="no confidence was claimed")
        average = sum(confidence_values) / len(confidence_values)
        spread = max(confidence_values) - min(confidence_values)
        if spread > 0.5:
            return Check(
                name="uncertainty",
                passed=True,
                detail=f"the stages disagreed (spread {spread:.2f}), so the result is reported with its range",
                evidence=(f"average confidence {average:.2f}",),
                weight=0.5,
            )
        return Check(
            name="uncertainty",
            passed=True,
            detail=f"the stages agreed within {spread:.2f}",
            evidence=(f"average confidence {average:.2f}",),
        )

    def check_injection(self, answer: str) -> Check:
        """The answer must not carry instructions lifted from untrusted content."""
        from osv1.safety.injection import scan

        scanned = scan(answer, source="answer")
        if scanned.flagged:
            return Check(
                name="injection",
                passed=False,
                detail="the answer contains instruction-like text from untrusted content",
                evidence=tuple(finding.excerpt[:120] for finding in scanned.findings[:4]),
            )
        return Check(name="injection", passed=True, detail="no instruction-like text found in the answer")

    # ── verdict ───────────────────────────────────────────────

    def verify(
        self,
        *,
        answer: str,
        goal: str,
        plan: Plan | None = None,
        actions: list[ActionRecord] | None = None,
        confidence_values: list[float] | None = None,
    ) -> Verification:
        """Run every check and return the verdict."""
        context = self.context
        actions = actions or []
        checks = [
            self.check_actions(actions),
            self.check_artifacts(plan),
            self.check_answer(answer, goal),
            self.check_injection(answer),
            self.check_uncertainty(confidence_values or []),
        ]
        self.checks = checks
        reasons = [check.detail for check in checks if not check.passed]
        passed = not reasons

        uncertainties = [check for check in checks if "uncertainty" in check.detail or "disagreed" in check.detail]
        uncertainty = 0.0
        note = ""
        if confidence_values:
            uncertainty = round(1.0 - (sum(confidence_values) / len(confidence_values)), 4)
            note = "uncertainty is one minus the average confidence of the stages that produced this answer"
        elif uncertainties:
            uncertainty = 0.4
            note = "the stages did not agree, so the uncertainty is reported as high"

        verification = Verification(
            passed=passed,
            checks=tuple(checks),
            uncertainty=uncertainty,
            reasons=tuple(reasons),
            uncertainty_note=note,
        )
        context.emit(
            "verification.done",
            passed=passed,
            checks=len(checks),
            failed=len(reasons),
            uncertainty=uncertainty,
        )
        return verification
