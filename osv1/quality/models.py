"""The computable models behind the thirteen qualities (specification section 27).

The specification says the aim is to turn each ambition into a model that can
be computed, tested, and improved. This module is that layer: the formulas of
section 27 as functions, with the numbers they need.

Every function states what it models and what it does not model. The laws are
the laws; the inputs are measurements, and the caller is responsible for
passing measured values rather than assumed ones.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

# ── 27.1 Speed ──────────────────────────────────────────────────────────


def prefill_time(parameters: float, input_tokens: int, flops_per_second: float) -> float:
    """The compute-bound part: ``T_prefill ≈ 2·P·L / F``."""
    if flops_per_second <= 0:
        raise ValueError("flops_per_second must be positive")
    return 2.0 * parameters * input_tokens / flops_per_second


def token_time(parameters: float, bytes_per_parameter: float, bandwidth_bytes_per_second: float) -> float:
    """The bandwidth-bound part: ``T_token ≈ P·b / BW``."""
    if bandwidth_bytes_per_second <= 0:
        raise ValueError("bandwidth_bytes_per_second must be positive")
    return parameters * bytes_per_parameter / bandwidth_bytes_per_second


def total_time(
    parameters: float,
    input_tokens: int,
    output_tokens: int,
    flops_per_second: float,
    bytes_per_parameter: float,
    bandwidth_bytes_per_second: float,
) -> float:
    """``T_total = T_prefill + N · T_token``."""
    return prefill_time(parameters, input_tokens, flops_per_second) + output_tokens * token_time(
        parameters, bytes_per_parameter, bandwidth_bytes_per_second
    )


def amdahl_speedup(parallel_fraction: float, speedup_factor: float) -> float:
    """``Speedup = 1 / ((1 − p) + p/s)``."""
    if speedup_factor <= 0:
        raise ValueError("speedup_factor must be positive")
    fraction = min(1.0, max(0.0, parallel_fraction))
    return 1.0 / ((1.0 - fraction) + fraction / speedup_factor)


def network_latency_floor(distance_km: float, speed_m_per_second: float = 2e8) -> float:
    """``t ≥ 2d / v`` — the floor a remote call cannot go below."""
    if speed_m_per_second <= 0:
        raise ValueError("speed_m_per_second must be positive")
    return 2.0 * (distance_km * 1000.0) / speed_m_per_second


# ── 27.2 Intelligence ───────────────────────────────────────────────────


def best_of_n_success(single_probability: float, attempts: int) -> float:
    """``1 − (1 − p)^n`` with a perfect checker."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    return 1.0 - (1.0 - single_probability) ** attempts


def generalization_gap(complexity: float, samples: int) -> float:
    """``O(√(complexity / n))`` — the bound on the train-to-test gap."""
    if samples < 1:
        raise ValueError("samples must be at least 1")
    return math.sqrt(complexity / samples)


# ── 27.3 Power ──────────────────────────────────────────────────────────


def job_reliability(step_probabilities: Sequence[float]) -> float:
    """``P_job = Π p_i`` — reliability compounds multiplicatively."""
    product = 1.0
    for probability in step_probabilities:
        product *= probability
    return product


def step_reliability_with_retry(probability: float, catch_rate: float) -> float:
    """``p' = p + (1 − p)·d·p`` — one retry when the verifier catches the error."""
    return probability + (1.0 - probability) * catch_rate * probability


def energy_per_task(watts: float, seconds: float) -> float:
    """``E = P_avg · t`` in joules."""
    return watts * seconds


# ── 27.4 Faster learning ───────────────────────────────────────────────


def power_law_error(errors: float, floor_error: float, samples: float, beta: float) -> float:
    """``e(n) = e∞ + (e0 − e∞) · n^(−β)`` — the practice curve."""
    if samples <= 0:
        raise ValueError("samples must be positive")
    return floor_error + (errors - floor_error) * samples ** (-beta)


def fit_learning_curve(history: Sequence[tuple[int, float]]) -> dict[str, float]:
    """Fit ``β`` and ``e∞`` to the practice history by least squares.

    The history is a sequence of ``(sessions, error_rate)``. The fit is done
    on a grid of ``β`` values, which is enough for a smooth curve and keeps
    the method simple to check by hand.
    """
    if len(history) < 2:
        return {"beta": 0.0, "e_inf": 0.0, "samples": float(len(history)), "fitted": False}
    points = sorted(history)
    last_error = points[-1][1]
    floor = min(error for _, error in points)
    best: tuple[float, float, float] | None = None
    for step in range(1, 61):
        beta = step / 10.0
        errors = [power_law_error(last_error, floor, sessions, beta) for sessions, _ in points]
        actual = [error for _, error in points]
        loss = sum((e - a) ** 2 for e, a in zip(errors, actual, strict=False))
        if best is None or loss < best[0]:
            best = (loss, beta, floor)
    assert best is not None
    return {
        "beta": round(best[1], 3),
        "e_inf": round(best[2], 4),
        "samples": float(len(points)),
        "fitted": True,
    }


def pac_sample_bound(hypothesis_size: float, epsilon: float, delta: float) -> float:
    """``m ≥ (1/ε)·(ln|H| + ln(1/δ))``."""
    if epsilon <= 0 or delta <= 0:
        raise ValueError("epsilon and delta must be positive")
    if hypothesis_size <= 0:
        raise ValueError("hypothesis_size must be positive")
    return (math.log(hypothesis_size) + math.log(1.0 / delta)) / epsilon


def lora_parameter_fraction(dimension: int, rank: int) -> float:
    """The share of a weight matrix a LoRA update touches: ``2dr / d²``."""
    if dimension < 1 or rank < 1:
        raise ValueError("dimension and rank must be positive")
    return (2.0 * dimension * rank) / (dimension * dimension)


# ── 27.5 Imagination ────────────────────────────────────────────────────


def discounted_return(rewards: Sequence[float], discount: float) -> float:
    """``V(π) = E[Σ γ^t · r_t]`` for one realised trajectory."""
    return sum((discount**index) * reward for index, reward in enumerate(rewards))


def monte_carlo_standard_error(standard_deviation: float, rollouts: int) -> float:
    """``σ / √N``."""
    if rollouts < 1:
        raise ValueError("rollouts must be at least 1")
    return standard_deviation / math.sqrt(rollouts)


def simulation_lemma_bound(model_error: float, discount: float, max_reward: float) -> float:
    """``|V_model − V_true| ≤ γ·ε·R_max / (1 − γ)²``."""
    if not 0.0 <= discount < 1.0:
        raise ValueError("discount must be in [0, 1)")
    return discount * model_error * max_reward / ((1.0 - discount) ** 2)


def negative_log_likelihood(probabilities: Sequence[float], outcomes: Sequence[int]) -> float:
    """``−log p(o)`` averaged over the samples."""
    if len(probabilities) != len(outcomes) or not probabilities:
        raise ValueError("probabilities and outcomes must be the same length")
    total = 0.0
    for probability, outcome in zip(probabilities, outcomes, strict=False):
        p = min(1.0 - 1e-12, max(1e-12, probability))
        total -= math.log(p) if outcome else math.log(1.0 - p)
    return total / len(probabilities)


def kl_divergence(distribution_p: Sequence[float], distribution_q: Sequence[float]) -> float:
    """``KL(P ‖ Q)`` — how far the observed outcome is from the predicted one."""
    if len(distribution_p) != len(distribution_q) or not distribution_p:
        raise ValueError("the distributions must have the same length")
    total = 0.0
    for p, q in zip(distribution_p, distribution_q, strict=False):
        if p <= 0.0:
            continue
        total += p * math.log(p / max(q, 1e-12))
    return total


# ── 27.6 Human-mind simulation ─────────────────────────────────────────


def cascade_time(fast_time: float, slow_time: float, escalation_rate: float) -> float:
    """``E[T] = T1 + q·T2`` — the dual-process expectation."""
    return fast_time + escalation_rate * slow_time


def chow_threshold(abstain_cost: float) -> float:
    """Chow's rule: abstain if ``max_y p(y|x) < 1 − d``."""
    return 1.0 - abstain_cost


# ── 27.7 Absolute safety ───────────────────────────────────────────────


def residual_failure_probability(layer_failure_rates: Sequence[float]) -> float:
    """``P_residual = Π f_i`` — the independent-layer product."""
    product = 1.0
    for rate in layer_failure_rates:
        product *= rate
    return product


def rule_of_three(failures: int, trials: int, confidence: float = 0.95) -> float:
    """The upper bound on the failure rate after zero observed failures.

    The general form used in reliability work is ``-ln(1 − c) / n``; for the
    usual 95 % confidence this is about ``3 / n``.
    """
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if failures < 0:
        raise ValueError("failures cannot be negative")
    if failures > 0:
        return failures / trials
    return -math.log(1.0 - confidence) / trials


def expected_harm(probabilities: Sequence[float], harms: Sequence[float]) -> float:
    """``Σ p_i · harm_i``."""
    if len(probabilities) != len(harms):
        raise ValueError("probabilities and harms must have the same length")
    return sum(p * h for p, h in zip(probabilities, harms, strict=False))


# ── 27.8 Reverse engineering ────────────────────────────────────────────


def information_bits(candidate_count: float) -> float:
    """``log₂ |H|`` — the bits needed to single out one candidate."""
    if candidate_count < 1:
        raise ValueError("candidate_count must be at least 1")
    return math.log2(candidate_count)


def mismatch_bound(trials: int, delta: float = 0.05) -> float:
    """``ε ≤ ln(1/δ) / n`` after ``n`` clean random tests."""
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if delta <= 0 or delta >= 1:
        raise ValueError("delta must be in (0, 1)")
    return math.log(1.0 / delta) / trials


def behavioral_parity(outputs: Sequence[Any], reference: Sequence[Any]) -> float:
    """``Π = (1/n)·Σ 1[f_build(x_i) = f_original(x_i)]``."""
    if len(outputs) != len(reference) or not outputs:
        raise ValueError("the two sequences must have the same length")
    matches = sum(1 for built, original in zip(outputs, reference, strict=False) if built == original)
    return matches / len(outputs)


# ── 27.9 Independence ──────────────────────────────────────────────────


def series_availability(availability: Sequence[float]) -> float:
    """``A = Π A_i`` for required dependencies."""
    product = 1.0
    for value in availability:
        product *= value
    return product


# ── 27.10 The SOM ──────────────────────────────────────────────────────


def softmax(scores: Sequence[float], temperature: float = 1.0) -> list[float]:
    """``p(y|x) = softmax(z / T)``."""
    if not scores:
        raise ValueError("scores cannot be empty")
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    scaled = [score / temperature for score in scores]
    highest = max(scaled)
    exponentials = [math.exp(value - highest) for value in scaled]
    total = sum(exponentials)
    return [value / total for value in exponentials]


def sigmoid(value: float) -> float:
    """``p(true|x) = σ(z)``."""
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def logit(probability: float) -> float:
    """The inverse of the sigmoid, for combining two sources."""
    p = min(1.0 - 1e-12, max(1e-12, probability))
    return math.log(p / (1.0 - p))


def combine_logits(
    som_probability: float, llm_probability: float, weight_som: float = 1.0, weight_llm: float = 1.0
) -> float:
    """``logit(p) = w1·logit(p_SOM) + w2·logit(p_LLM)``."""
    combined = weight_som * logit(som_probability) + weight_llm * logit(llm_probability)
    return sigmoid(combined)


def value_of_information(best_probability: float, impact: float, cost_of_waiting: float) -> float:
    """``VOI = (1 − max p)·impact − cost`` — ask when this is positive."""
    return (1.0 - best_probability) * impact - cost_of_waiting


# ── 27.11 Mathematical logic ────────────────────────────────────────────


FLOAT64_UNIT_ROUNDOFF = 2.0**-53


def relative_error(condition_number: float) -> float:
    """``error ≈ κ · u`` for float64 arithmetic."""
    return condition_number * FLOAT64_UNIT_ROUNDOFF


@dataclass
class Dimension:
    """A physical dimension, for the unit check."""

    name: str
    powers: dict[str, int] = field(default_factory=dict)

    def __mul__(self, other: Dimension) -> Dimension:
        powers = dict(self.powers)
        for key, value in other.powers.items():
            powers[key] = powers.get(key, 0) + value
        return Dimension(f"{self.name}·{other.name}", {k: v for k, v in powers.items() if v})

    def __truediv__(self, other: Dimension) -> Dimension:
        powers = dict(self.powers)
        for key, value in other.powers.items():
            powers[key] = powers.get(key, 0) - value
        return Dimension(f"{self.name}/{other.name}", {k: v for k, v in powers.items() if v})

    def __pow__(self, exponent: int) -> Dimension:
        return Dimension(
            f"{self.name}^{exponent}",
            {key: value * exponent for key, value in self.powers.items() if value * exponent},
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Dimension):
            return NotImplemented
        return self.powers == other.powers

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.powers.items())))

    def describe(self) -> str:
        if not self.powers:
            return "1"
        parts = []
        for key, value in sorted(self.powers.items()):
            parts.append(key if value == 1 else f"{key}{_superscript(value)}")
        return "·".join(parts)


LENGTH = Dimension("m", {"m": 1})
MASS = Dimension("kg", {"kg": 1})
TIME = Dimension("s", {"s": 1})
VELOCITY = LENGTH / TIME
FORCE = MASS * LENGTH / (TIME**2)
ENERGY = FORCE * LENGTH


def dimensions_match(left: Dimension, right: Dimension) -> bool:
    """Dimensional consistency: a free exact test."""
    return left.powers == right.powers


# ── 27.12 Scientific grounding ─────────────────────────────────────────


def posterior_odds(prior_odds: float, likelihood_ratio: float) -> float:
    """Posterior odds = prior odds × likelihood ratio."""
    return prior_odds * likelihood_ratio


def confidence_interval(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """``p̂ ± z·√(p̂(1 − p̂)/n)``."""
    if trials < 1:
        raise ValueError("trials must be at least 1")
    p = successes / trials
    margin = z * math.sqrt((p * (1.0 - p)) / trials)
    return max(0.0, p - margin), min(1.0, p + margin)


def sample_size_for_margin(estimate: float, margin: float, z: float = 1.96) -> int:
    """``n ≈ z²·p̂(1 − p̂)/m²``."""
    if margin <= 0:
        raise ValueError("margin must be positive")
    return math.ceil((z**2) * estimate * (1.0 - estimate) / (margin**2))


# ── 27.13 Absolute knowledge ───────────────────────────────────────────


def shannon_entropy(distribution: Sequence[float]) -> float:
    """``H(X) = −Σ p·log₂ p``."""
    total = 0.0
    for probability in distribution:
        if probability <= 0.0:
            continue
        total -= probability * math.log2(probability)
    return total


def information_gain(before: Sequence[float], after: Sequence[float]) -> float:
    """``I(X;Y) = H(X) − H(X|Y)``."""
    return shannon_entropy(before) - shannon_entropy(after)


def knowledge_gap(distribution: Sequence[float]) -> float:
    """The size of the knowledge gap: the entropy of what the system expects.

    A high gap means the system does not know which outcome to expect, and
    the gap is closed by retrieval, search, reading, or asking.
    """
    return shannon_entropy(distribution)


def kv_cache_bytes_per_token(layers: int, kv_heads: int, head_dimension: int, bytes_per_element: float) -> float:
    """``2·layers·kv_heads·head_dim·bytes`` — the memory cost of one token.

    The element size may be fractional: a 4-bit cache stores half a byte per
    element, which is what makes the full window reachable on a large device.
    """
    if layers < 1 or kv_heads < 1 or head_dimension < 1 or bytes_per_element <= 0:
        raise ValueError("every argument must be positive")
    return 2 * layers * kv_heads * head_dimension * bytes_per_element


def kv_cache_bytes(layers: int, kv_heads: int, head_dimension: int, tokens: int, bytes_per_element: float) -> float:
    """The KV cache of a whole context."""
    if tokens < 1:
        raise ValueError("tokens must be at least 1")
    return kv_cache_bytes_per_token(layers, kv_heads, head_dimension, bytes_per_element) * tokens


_SUPERSCRIPTS = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")


def _superscript(value: int) -> str:
    return str(value).translate(_SUPERSCRIPTS)


# ── 27.6/27.10 helper: the expert-free completion rate ─────────────────


def expert_free_completion_rate(
    outcomes: Iterable[tuple[bool, bool]],
) -> dict[str, Any]:
    """The rate at which a non-expert gets a finished, verified result.

    Each outcome is ``(completed, needed_human_intervention)``. A run counts
    as expert-free when it completed and nobody had to step in.
    """
    total = 0
    free = 0
    for completed, intervened in outcomes:
        total += 1
        if completed and not intervened:
            free += 1
    if total == 0:
        return {"rate": None, "samples": 0, "free": 0, "total": 0}
    return {"rate": free / total, "samples": total, "free": free, "total": total}
