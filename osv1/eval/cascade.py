"""The dual-process cascade, measured (specification section 27.6).

Section 27.6 models System One and System Two as a cascade: the fast path
answers, and the slow path is paid only when the fast one is not confident
enough. The model is ``E[T] = T1 + q·T2``, where ``q`` is the escalation
rate. The model is only worth something if ``q`` and both times are
measured, so this module measures them.

Two escalation signals are recorded, and they are never confused:

* ``q_abstain`` — System One itself said it was not confident. This is the
  ``q`` of the cascade formula, because it is the signal that decides
  whether the slow path is paid.
* ``q_llm`` — the slow path was actually reachable and produced the plan or
  the answer. In the current architecture the planner always asks the model
  when it is up, so this is the share of the work System Two did.

A number without samples is not a result, so every figure carries its count,
and the report says *what distribution it was measured on*.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any


def _percentile(values: list[float], fraction: float) -> float | None:
    """The p-th percentile of a sample, by nearest rank."""
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return round(ordered[index], 3)


@dataclass
class CascadeRecorder:
    """Collects the timings and the escalations of one runtime."""

    som_times_ms: list[float] = field(default_factory=list)
    llm_times_ms: list[float] = field(default_factory=list)
    som_abstentions: int = 0
    som_decisions: int = 0
    llm_calls: int = 0
    llm_unavailable: int = 0
    note: str = ""

    def record_som(self, milliseconds: float, *, abstained: bool) -> None:
        self.som_times_ms.append(milliseconds)
        self.som_decisions += 1
        if abstained:
            self.som_abstentions += 1

    def record_llm(self, milliseconds: float, *, ok: bool) -> None:
        self.llm_times_ms.append(milliseconds)
        if ok:
            self.llm_calls += 1
        else:
            self.llm_unavailable += 1

    def reset(self) -> None:
        self.som_times_ms.clear()
        self.llm_times_ms.clear()
        self.som_abstentions = 0
        self.som_decisions = 0
        self.llm_calls = 0
        self.llm_unavailable = 0

    # ── the report ────────────────────────────────────────────

    def report(self, *, distribution: str = "") -> dict[str, Any]:
        """``E[T] = T1 + q·T2`` with the measurements behind every term."""
        t1 = statistics.median(self.som_times_ms) if self.som_times_ms else None
        t2 = statistics.median(self.llm_times_ms) if self.llm_times_ms else None
        q_abstain = self.som_abstentions / self.som_decisions if self.som_decisions else None
        q_llm = (
            self.llm_calls / (self.llm_calls + self.llm_unavailable)
            if (self.llm_calls + self.llm_unavailable)
            else None
        )
        expected = None
        if t1 is not None and t2 is not None and q_abstain is not None:
            expected = round(t1 + q_abstain * t2, 3)
        return {
            "model": "E[T] = T1 + q·T2 (specification section 27.6)",
            "t1_median_ms": round(t1, 3) if t1 is not None else None,
            "t1_p50_ms": _percentile(self.som_times_ms, 0.5),
            "t1_p95_ms": _percentile(self.som_times_ms, 0.95),
            "t2_median_ms": round(t2, 3) if t2 is not None else None,
            "t2_p50_ms": _percentile(self.llm_times_ms, 0.5),
            "t2_p95_ms": _percentile(self.llm_times_ms, 0.95),
            "q_abstain": round(q_abstain, 4) if q_abstain is not None else None,
            "q_llm": round(q_llm, 4) if q_llm is not None else None,
            "expected_time_ms": expected,
            "som_decisions": self.som_decisions,
            "som_abstentions": self.som_abstentions,
            "llm_reachable_calls": self.llm_calls,
            "llm_unreachable_calls": self.llm_unavailable,
            "samples_som": len(self.som_times_ms),
            "samples_llm": len(self.llm_times_ms),
            "distribution": distribution,
            "note": self.note
            or "q_abstain decides whether the slow path is paid; q_llm is the share of the work it did",
        }
