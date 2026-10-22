"""The thirteen qualities of OS_V1, with their laws, rules, and tests.

Spec section 1.1 names the qualities; section 27 gives each one a model.
This module is the register that connects them: the core law, the key
formula, the engineering rule that follows from it, the test that measures
it, and the metric the number lands in.

Nothing here claims a value. A quality is either *measured* — with a sample
count — or it is a *target*, and the two are never mixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from osv1.quality import models


@dataclass(frozen=True)
class Quality:
    """One quality, with the model that backs it."""

    number: int
    key: str
    name: str
    law: str
    formula: str
    engineering_rule: str
    test: str
    metric: str
    module: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "key": self.key,
            "name": self.name,
            "law": self.law,
            "formula": self.formula,
            "engineering_rule": self.engineering_rule,
            "test": self.test,
            "metric": self.metric,
            "model_module": self.module,
        }


QUALITIES: tuple[Quality, ...] = (
    Quality(
        number=1,
        key="speed",
        name="Speed",
        law="Roofline and Amdahl",
        formula="T = T_prefill + N·T_token",
        engineering_rule="Route to the SOM first. Use the LLM only when generation is needed. Profile, then optimize the largest fraction first.",
        test="p50 and p95 latency per decision and per task, tokens per second, per device tier.",
        metric="p95 latency",
        module="osv1.quality.models:prefill_time, token_time, amdahl_speedup",
    ),
    Quality(
        number=2,
        key="intelligence",
        name="Intelligence",
        law="Universal intelligence, No Free Lunch",
        formula="1 − (1 − p)^n with a perfect checker",
        engineering_rule="Spend compute where uncertainty is high and save it where it is low. Keep a verifier in the loop.",
        test="A benchmark suite weighted to the user's task distribution, reported with confidence intervals.",
        metric="Benchmark score with confidence interval",
        module="osv1.quality.models:best_of_n_success, confidence_interval",
    ),
    Quality(
        number=3,
        key="power",
        name="Power",
        law="Reliability compounding",
        formula="P_job = Π p_i",
        engineering_rule="Verify every step. Checkpoint long jobs. Keep an error budget per task, and roll back at the first failed check.",
        test="End-to-end completion rate with a confidence interval, and joules per completed task.",
        metric="End-to-end completion rate",
        module="osv1.quality.models:job_reliability, step_reliability_with_retry",
    ),
    Quality(
        number=4,
        key="faster-learning",
        name="Faster learning",
        law="PAC bound, power law of practice",
        formula="e(n) = e∞ + (e0 − e∞)·n^(−β)",
        engineering_rule="Learn faster by shrinking the search space, by asking where the value of information is highest, and by protecting old knowledge with regression tests.",
        test="Fit β and e∞ to the practice-session error history. Track time to learn a new skill.",
        metric="Learning exponent β",
        module="osv1.quality.models:fit_learning_curve, pac_sample_bound",
    ),
    Quality(
        number=5,
        key="imagination",
        name="Imagination",
        law="World model, simulation lemma",
        formula="V(π) = E[Σ γ^t·r_t]",
        engineering_rule="Plan mode runs imagined rollouts and scores them. After Build, compare the prediction with what happened, and widen uncertainty with the horizon.",
        test="Negative log-likelihood and KL divergence between predicted and observed outcomes, calibration of predicted success, and plan regret.",
        metric="Prediction NLL, plan regret",
        module="osv1.quality.models:discounted_return, negative_log_likelihood, kl_divergence",
    ),
    Quality(
        number=6,
        key="human-mind",
        name="Human-mind simulation (Ultra IQ)",
        law="Dual-process cascade",
        formula="E[T] = T1 + q·T2",
        engineering_rule="Make the SOM good enough that q is small, and measure q.",
        test="The five Ultra IQ metrics, and agreement with human experts on a graded task suite.",
        metric="The five Ultra IQ metrics",
        module="osv1.quality.models:cascade_time, chow_threshold",
    ),
    Quality(
        number=7,
        key="absolute-safety",
        name="Absolute safety",
        law="Safety properties, rule of three",
        formula="P ≤ 3 / n after 0 failures",
        engineering_rule="The safety core is immutable. Contain generated code. Approve irreversible actions. Never claim 'safe'; report an upper bound with its trial count.",
        test="Red-team failure rate with an upper bound from the rule of three, and zero unauthorized irreversible actions across the test suite.",
        metric="Red-team failure bound",
        module="osv1.quality.models:rule_of_three, residual_failure_probability",
    ),
    Quality(
        number=8,
        key="reverse-engineering",
        name="The best reverse engineering",
        law="Data-processing inequality",
        formula="ε ≤ ln(1/δ) / n",
        engineering_rule="Combine static and dynamic evidence. Keep the evidence and limitations of every finding. Confirm with parity tests.",
        test="Behavioral parity Π, file compatibility, and the mismatch bound ε with its trial count.",
        metric="Behavioral parity Π",
        module="osv1.quality.models:behavioral_parity, mismatch_bound, information_bits",
    ),
    Quality(
        number=9,
        key="independence",
        name="Independence",
        law="Series availability",
        formula="A = Π A_i",
        engineering_rule="Keep a dependency inventory. Make every external dependency optional. Test with the network cut and no keys.",
        test="The independence tests: zero provider requests and full core function offline.",
        metric="Offline success rate",
        module="osv1.quality.models:series_availability, network_latency_floor",
    ),
    Quality(
        number=10,
        key="som",
        name="The SOM",
        law="Decision theory, proper scoring",
        formula="a* = argmin_a Σ p·Loss",
        engineering_rule="Start from Laya and recalibrate it. Reimplement the published ideas of the closed reference model independently. Copy nothing.",
        test="Accuracy, ECE, Brier score, latency, and abstain rate on typed-decision sets.",
        metric="ECE, Brier, latency",
        module="osv1.quality.models:softmax, sigmoid, combine_logits, value_of_information",
    ),
    Quality(
        number=11,
        key="mathematical-logic",
        name="Mathematical logic",
        law="SMT, floating-point error",
        formula="error ≈ κ·u",
        engineering_rule="The Verifier sends arithmetic to exact or high-precision computation, constraints to a solver, probabilities to explicit calculation, and physical quantities to a unit check. Outside decidable fragments it falls back to tests and labels the result 'tested, not proven'.",
        test="Share of numeric and logical claims checked by a tool, accuracy on a math-and-logic suite, and false-accept rate.",
        metric="Claims checked by a tool",
        module="osv1.quality.models:relative_error, dimensions_match; osv1.layers.verifier:check_math",
    ),
    Quality(
        number=12,
        key="scientific-grounding",
        name="Scientific grounding",
        law="Bayesian evidence",
        formula="Posterior odds = prior odds × LR",
        engineering_rule="Tag every claim as a fact with a source, a derived result with a method, or an assumption. Fix seeds, versions, and data hashes so results can be reproduced.",
        test="Share of claims supported by a checkable source, citation accuracy, and reproducibility of reported results.",
        metric="Claims with checkable sources",
        module="osv1.quality.models:posterior_odds, confidence_interval, sample_size_for_margin",
    ),
    Quality(
        number=13,
        key="absolute-knowledge",
        name="Absolute knowledge",
        law="Entropy, memory physics",
        formula="KV bytes = 2·layers·kv_heads·head_dim·L·b",
        engineering_rule="Detect gaps from the entropy of the model's predictions. Close them by search, reading, or asking. Store what was learned with its source. Report what is still unknown.",
        test="Needle-in-a-haystack recall at the full window, how well uncertainty predicts errors, and the time to close a detected gap.",
        metric="Needle recall, gap closure time",
        module="osv1.quality.models:shannon_entropy, information_gain, kv_cache_bytes",
    ),
)

QUALITY_BY_KEY = {quality.key: quality for quality in QUALITIES}

# The three foundations that stay fixed, and why (spec section 1.1).
FIXED_FOUNDATIONS = (
    (
        "safety",
        "The safety layer, the permissions, the audit log, the kill switch, and the verifier's tests "
        "are refused by the promotion gate, and the system cannot weaken them.",
    ),
    (
        "legal",
        "Licences and terms of use are respected. A non-permissive licence waits for a legal review, "
        "and closed services are never reverse engineered.",
    ),
    (
        "honesty",
        "Anything not measured is written as a target. Every metric is reported with its sample count, "
        "and a number without samples is not reported as a result.",
    ),
)


@dataclass
class QualityReport:
    """What is measured today, and what is still a target."""

    measured: dict[str, Any] = field(default_factory=dict)
    targets: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "qualities": [quality.as_dict() for quality in QUALITIES],
            "measured": self.measured,
            "targets": self.targets,
            "fixed_foundations": [{"key": key, "rule": rule} for key, rule in FIXED_FOUNDATIONS],
            "notes": list(self.notes),
        }


def catalog() -> dict[str, Any]:
    """The register itself, without any measurement."""
    return {
        "qualities": [quality.as_dict() for quality in QUALITIES],
        "fixed_foundations": [{"key": key, "rule": rule} for key, rule in FIXED_FOUNDATIONS],
        "count": len(QUALITIES),
    }


def tier_kv_cache(tier: str, *, layers: int = 32, kv_heads: int = 8, head_dimension: int = 128) -> dict[str, Any]:
    """The memory cost of the full window on a tier, in 16-bit and 4-bit."""
    from osv1.config import DEVICE_TIERS

    device_tier = DEVICE_TIERS.get(tier)
    if device_tier is None:
        raise ValueError(f"unknown tier: {tier!r}")
    tokens = device_tier.context_tokens
    return {
        "tier": tier,
        "tokens": tokens,
        "kv_bytes_16bit": models.kv_cache_bytes(layers, kv_heads, head_dimension, tokens, 2),
        "kv_bytes_4bit": models.kv_cache_bytes(layers, kv_heads, head_dimension, tokens, 0.5),
        "per_token_bytes_16bit": models.kv_cache_bytes_per_token(layers, kv_heads, head_dimension, 2),
        "per_token_bytes_4bit": models.kv_cache_bytes_per_token(layers, kv_heads, head_dimension, 0.5),
    }
