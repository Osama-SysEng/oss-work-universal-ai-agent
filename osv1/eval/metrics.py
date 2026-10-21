"""The five measurable metrics behind the name (spec section 11).

The specification is explicit: a marketing phrase becomes a release only when
it is tied to numbers. These are those numbers.

1. Search breadth — the paths and plans explored and scored before deciding.
2. Decision quality — the share of correct decisions on a held-out set.
3. Calibration — how well the stated confidence matches the real accuracy.
4. Verification catch rate — the share of seeded errors the verifier catches
   before delivery.
5. Time to solution — the time from request to verified result.

Every function here reports what it measured, on what, and how many samples
it used. A metric without samples is not reported as a result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from osv1.calibration import brier_score, expected_calibration_error, reliability_curve


@dataclass
class MetricReport:
    """One measured metric."""

    name: str
    value: float | None
    unit: str
    samples: int
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "value": round(self.value, 4) if self.value is not None else None,
            "unit": self.unit,
            "samples": self.samples,
            "detail": self.detail,
        }


def search_breadth(paths_explored: int, plans_scored: int) -> MetricReport:
    return MetricReport(
        name="search_breadth",
        value=float(paths_explored),
        unit="paths",
        samples=paths_explored,
        detail=f"{paths_explored} paths explored, {plans_scored} plans scored before deciding",
    )


def decision_quality(correct: int, total: int) -> MetricReport:
    if not total:
        return MetricReport(
            name="decision_quality", value=None, unit="ratio", samples=0, detail="no labelled decisions"
        )
    return MetricReport(
        name="decision_quality",
        value=correct / total,
        unit="ratio",
        samples=total,
        detail=f"{correct} of {total} held-out decisions were correct",
    )


def calibration(probabilities: list[float], outcomes: list[int]) -> list[MetricReport]:
    if not probabilities:
        return [
            MetricReport(
                name="expected_calibration_error", value=None, unit="error", samples=0, detail="no labelled outcomes"
            ),
            MetricReport(name="brier_score", value=None, unit="error", samples=0, detail="no labelled outcomes"),
        ]
    return [
        MetricReport(
            name="expected_calibration_error",
            value=expected_calibration_error(probabilities, outcomes),
            unit="error",
            samples=len(probabilities),
            detail="lower is better; the gap between stated confidence and observed accuracy",
        ),
        MetricReport(
            name="brier_score",
            value=brier_score(probabilities, outcomes),
            unit="error",
            samples=len(probabilities),
            detail="lower is better; mean squared error between stated probability and outcome",
        ),
    ]


def verification_catch_rate(caught: int, seeded: int) -> MetricReport:
    if not seeded:
        return MetricReport(
            name="verification_catch_rate",
            value=None,
            unit="ratio",
            samples=0,
            detail="no errors were seeded into this run",
        )
    return MetricReport(
        name="verification_catch_rate",
        value=caught / seeded,
        unit="ratio",
        samples=seeded,
        detail=f"{caught} of {seeded} seeded errors were caught before delivery",
    )


def time_to_solution(seconds: float) -> MetricReport:
    return MetricReport(
        name="time_to_solution",
        value=seconds,
        unit="seconds",
        samples=1,
        detail="from request to verified result",
    )


def reliability(probabilities: list[float], outcomes: list[int]) -> list[dict[str, float]]:
    return reliability_curve(probabilities, outcomes)


@dataclass
class RunMetrics:
    """The metrics of one run, collected as the run happens."""

    paths_explored: int = 0
    plans_scored: int = 0
    decisions_correct: int = 0
    decisions_total: int = 0
    probabilities: list[float] = field(default_factory=list)
    outcomes: list[int] = field(default_factory=list)
    seeded_errors: int = 0
    caught_errors: int = 0
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0

    def record_decision(self, probability: float, correct: bool) -> None:
        self.decisions_total += 1
        if correct:
            self.decisions_correct += 1
        self.probabilities.append(probability)
        self.outcomes.append(1 if correct else 0)

    def as_reports(self) -> list[dict[str, Any]]:
        elapsed = (self.finished_at or time.time()) - self.started_at
        reports = [
            search_breadth(self.paths_explored, self.plans_scored),
            decision_quality(self.decisions_correct, self.decisions_total),
            *calibration(self.probabilities, self.outcomes),
            verification_catch_rate(self.caught_errors, self.seeded_errors),
            time_to_solution(elapsed),
        ]
        return [report.as_dict() for report in reports]
