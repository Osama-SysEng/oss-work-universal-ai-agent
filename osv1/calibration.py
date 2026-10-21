"""Calibration math for System One.

The specification (section 9) requires the SOM to report calibrated
confidence, and section 23 makes recalibration a required step rather than an
option. These are the standard measures:

- Brier score: mean squared error between stated probability and outcome.
- Expected calibration error (ECE): weighted average gap between stated
  confidence and observed accuracy, over confidence bins.
- Temperature scaling: a single-parameter recalibration fitted by gradient
  descent on labelled local data.

No external dependency: plain arithmetic, so it runs with no keys and no
network.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def brier_score(probabilities: list[float], outcomes: list[int]) -> float:
    """Mean squared error between stated probability and observed outcome."""
    if not probabilities or len(probabilities) != len(outcomes):
        return 0.0
    total = sum((p - o) ** 2 for p, o in zip(probabilities, outcomes, strict=False))
    return total / len(probabilities)


def expected_calibration_error(probabilities: list[float], outcomes: list[int], bins: int = 10) -> float:
    """Weighted gap between stated confidence and observed accuracy."""
    if not probabilities or len(probabilities) != len(outcomes):
        return 0.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, o in zip(probabilities, outcomes, strict=False):
        index = min(bins - 1, max(0, int(p * bins)))
        buckets[index].append((p, o))
    total = len(probabilities)
    error = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        avg_confidence = sum(p for p, _ in bucket) / len(bucket)
        avg_accuracy = sum(o for _, o in bucket) / len(bucket)
        error += (len(bucket) / total) * abs(avg_confidence - avg_accuracy)
    return error


def reliability_curve(probabilities: list[float], outcomes: list[int], bins: int = 10) -> list[dict[str, float]]:
    """Per-bin accuracy and confidence, for a reliability diagram."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, o in zip(probabilities, outcomes, strict=False):
        index = min(bins - 1, max(0, int(p * bins)))
        buckets[index].append((p, o))
    curve: list[dict[str, float]] = []
    for index, bucket in enumerate(buckets):
        if not bucket:
            continue
        avg_confidence = sum(p for p, _ in bucket) / len(bucket)
        avg_accuracy = sum(o for _, o in bucket) / len(bucket)
        curve.append(
            {
                "bin": float(index),
                "count": float(len(bucket)),
                "confidence": round(avg_confidence, 4),
                "accuracy": round(avg_accuracy, 4),
            }
        )
    return curve


def apply_temperature(probability: float, temperature: float) -> float:
    """Sharpen (T<1) or soften (T>1) a probability."""
    if temperature <= 0:
        return probability
    value = probability ** (1.0 / temperature)
    return min(1.0, max(0.0, value))


def _log_loss(probabilities: list[float], outcomes: list[int], temperature: float) -> float:
    if not probabilities or len(probabilities) != len(outcomes):
        return 0.0
    total = 0.0
    for p, o in zip(probabilities, outcomes, strict=False):
        adjusted = apply_temperature(p, temperature)
        adjusted = min(1 - 1e-9, max(1e-9, adjusted))
        total += -(o * math.log(adjusted) + (1 - o) * math.log(1 - adjusted))
    return total / len(probabilities)


@dataclass
class Calibrator:
    """A fitted temperature plus the metrics that justify it."""

    temperature: float = 1.0
    ece_before: float = 0.0
    ece_after: float = 0.0
    brier_before: float = 0.0
    brier_after: float = 0.0
    samples: int = 0

    def apply(self, probability: float) -> float:
        return apply_temperature(probability, self.temperature)

    def as_dict(self) -> dict[str, float | int]:
        return {
            "temperature": round(self.temperature, 4),
            "ece_before": round(self.ece_before, 4),
            "ece_after": round(self.ece_after, 4),
            "brier_before": round(self.brier_before, 4),
            "brier_after": round(self.brier_after, 4),
            "samples": self.samples,
        }


def fit_calibrator(
    probabilities: list[float], outcomes: list[int], *, iterations: int = 200, learning_rate: float = 0.05
) -> Calibrator:
    """Fit a single temperature by gradient descent on log loss."""
    if not probabilities or len(probabilities) != len(outcomes):
        return Calibrator()
    temperature = 1.0
    ece_before = expected_calibration_error(probabilities, outcomes)
    brier_before = brier_score(probabilities, outcomes)
    for _ in range(iterations):
        gradient = 0.0
        for p, o in zip(probabilities, outcomes, strict=False):
            adjusted = min(1 - 1e-9, max(1e-9, apply_temperature(p, temperature)))
            # d/dT of p^(1/T) with respect to T
            derivative = -adjusted * math.log(p) / temperature if p > 0 else 0.0
            gradient += (adjusted - o) * derivative
        gradient /= len(probabilities)
        temperature -= learning_rate * gradient
        temperature = min(10.0, max(0.05, temperature))
    adjusted_probs = [apply_temperature(p, temperature) for p in probabilities]
    return Calibrator(
        temperature=temperature,
        ece_before=ece_before,
        ece_after=expected_calibration_error(adjusted_probs, outcomes),
        brier_before=brier_before,
        brier_after=brier_score(adjusted_probs, outcomes),
        samples=len(probabilities),
    )
