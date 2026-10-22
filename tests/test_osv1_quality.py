"""The thirteen qualities: the models that make them computable, and the checks.

The formulas of specification section 27 are checked against the worked
examples the specification itself gives, so a change in the code that breaks
one of them fails here rather than in a report.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from osv1.layers.context import LayerContext
from osv1.layers.verifier import Verifier
from osv1.layers.world_model import WorldModel
from osv1.quality import models
from osv1.quality.qualities import FIXED_FOUNDATIONS, QUALITIES, QUALITY_BY_KEY, catalog, tier_kv_cache

# ── 27.1 Speed ──────────────────────────────────────────────────────────


def test_the_latency_model_matches_the_specification_example() -> None:
    # A 7B model with 4-bit weights: 3.5 GB, and about 17.5 ms per token
    # at 200 GB/s.
    seconds_per_token = models.token_time(7e9, 0.5, 200e9)
    assert seconds_per_token == pytest.approx(0.0175, rel=1e-3)
    assert 100 * seconds_per_token == pytest.approx(1.75, rel=1e-3)


def test_the_prefill_time_is_compute_bound() -> None:
    # The SOM example: 0.421e9 parameters, 200 tokens, 10 TFLOP/s.
    seconds = models.prefill_time(0.421e9, 200, 10e12)
    assert seconds == pytest.approx(0.0168, rel=1e-2)
    assert seconds * 1000 < 20, "the decision should be far faster than a generated answer"


def test_the_total_time_is_the_sum_of_the_two_parts() -> None:
    total = models.total_time(7e9, 500, 100, 10e12, 0.5, 200e9)
    prefill = models.prefill_time(7e9, 500, 10e12)
    decode = 100 * models.token_time(7e9, 0.5, 200e9)
    assert total == pytest.approx(prefill + decode)


def test_amdahl_speedup_matches_the_classic_formula() -> None:
    assert models.amdahl_speedup(0.5, 4) == pytest.approx(1.6)
    assert models.amdahl_speedup(1.0, 10) == pytest.approx(10.0)
    assert models.amdahl_speedup(0.0, 10) == pytest.approx(1.0)


def test_the_network_latency_floor_is_ten_milliseconds_for_a_thousand_kilometres() -> None:
    assert models.network_latency_floor(1000) == pytest.approx(0.010, rel=1e-3)


# ── 27.2 Intelligence ───────────────────────────────────────────────────


def test_best_of_n_matches_the_specification_example() -> None:
    assert models.best_of_n_success(0.6, 5) == pytest.approx(0.99, abs=0.001)
    assert models.best_of_n_success(0.6, 1) == pytest.approx(0.6)


def test_the_generalization_gap_shrinks_with_samples() -> None:
    assert models.generalization_gap(1000, 100) > models.generalization_gap(1000, 10000)


# ── 27.3 Power ──────────────────────────────────────────────────────────


def test_job_reliability_compounds() -> None:
    assert models.job_reliability([0.95] * 20) == pytest.approx(0.36, abs=0.01)


def test_one_verified_retry_moves_the_job_reliability() -> None:
    improved = models.step_reliability_with_retry(0.95, 0.9)
    assert improved == pytest.approx(0.9928, abs=0.001)
    assert models.job_reliability([improved] * 20) == pytest.approx(0.86, abs=0.02)


def test_energy_per_task_is_watts_times_seconds() -> None:
    assert models.energy_per_task(40, 0.0175) == pytest.approx(0.7)


# ── 27.4 Faster learning ───────────────────────────────────────────────


def test_the_power_law_of_practice_flattens() -> None:
    first = models.power_law_error(0.5, 0.05, 1, 0.5)
    later = models.power_law_error(0.5, 0.05, 100, 0.5)
    assert later < first
    assert later > 0.05


def test_the_learning_curve_is_fitted_to_a_history() -> None:
    history = [(1, 0.50), (2, 0.40), (4, 0.32), (8, 0.27), (16, 0.24)]
    fit = models.fit_learning_curve(history)
    assert fit["fitted"] is True
    assert fit["beta"] > 0
    assert fit["e_inf"] <= min(error for _, error in history)


def test_the_pac_bound_grows_with_the_hypothesis_space() -> None:
    small = models.pac_sample_bound(10, 0.1, 0.05)
    large = models.pac_sample_bound(10000, 0.1, 0.05)
    assert large > small


def test_a_lora_update_touches_a_fraction_of_the_weights() -> None:
    assert models.lora_parameter_fraction(4096, 16) == pytest.approx(0.0078, abs=0.0001)


# ── 27.5 Imagination ────────────────────────────────────────────────────


def test_the_discounted_return_weights_the_future_less() -> None:
    assert models.discounted_return([1.0, 1.0], 0.5) == pytest.approx(1.5)
    assert models.discounted_return([1.0, 1.0], 0.9) == pytest.approx(1.9)


def test_the_monte_carlo_error_shrinks_with_rollouts() -> None:
    assert models.monte_carlo_standard_error(1.0, 100) == pytest.approx(0.1)


def test_the_simulation_lemma_bound_grows_with_the_horizon() -> None:
    near = models.simulation_lemma_bound(0.1, 0.9, 1.0)
    far = models.simulation_lemma_bound(0.1, 0.99, 1.0)
    assert far > near


def test_the_negative_log_likelihood_punishes_wrong_confidence() -> None:
    confident_and_right = models.negative_log_likelihood([0.99, 0.99], [1, 1])
    confident_and_wrong = models.negative_log_likelihood([0.99, 0.99], [0, 0])
    assert confident_and_wrong > confident_and_right


def test_the_kl_divergence_is_zero_for_the_same_distribution() -> None:
    assert models.kl_divergence([0.3, 0.7], [0.3, 0.7]) == pytest.approx(0.0, abs=1e-9)
    assert models.kl_divergence([0.9, 0.1], [0.5, 0.5]) > 0


# ── 27.6 Human-mind simulation ──────────────────────────────────────────


def test_the_dual_process_cascade_matches_the_specification_example() -> None:
    assert models.cascade_time(0.020, 2.0, 0.10) == pytest.approx(0.220)
    assert models.cascade_time(0.020, 2.0, 0.02) == pytest.approx(0.060)


def test_chows_rule_sets_the_abstention_threshold() -> None:
    assert models.chow_threshold(0.1) == pytest.approx(0.9)


# ── 27.7 Absolute safety ───────────────────────────────────────────────


def test_four_independent_layers_at_one_percent_leave_one_in_a_hundred_million() -> None:
    assert models.residual_failure_probability([0.01] * 4) == pytest.approx(1e-8)


def test_the_rule_of_three_gives_the_bound_after_clean_trials() -> None:
    assert models.rule_of_three(0, 3000) == pytest.approx(0.001, rel=0.05)
    assert models.rule_of_three(0, 30000) == pytest.approx(0.0001, rel=0.05)
    assert models.rule_of_three(2, 100) == pytest.approx(0.02)


def test_expected_harm_sums_the_weighted_harms() -> None:
    assert models.expected_harm([0.5, 0.5], [10.0, 0.0]) == pytest.approx(5.0)


# ── 27.8 Reverse engineering ───────────────────────────────────────────


def test_the_information_bound_counts_bits() -> None:
    assert models.information_bits(1024) == pytest.approx(10.0)
    assert models.information_bits(1) == pytest.approx(0.0)


def test_the_mismatch_bound_after_three_thousand_clean_tests() -> None:
    assert models.mismatch_bound(3000, 0.05) == pytest.approx(0.001, rel=0.05)


def test_behavioral_parity_counts_the_matching_outputs() -> None:
    assert models.behavioral_parity([1, 2, 3, 4], [1, 2, 9, 4]) == pytest.approx(0.75)


# ── 27.9 Independence ──────────────────────────────────────────────────


def test_five_required_services_at_ninety_nine_point_nine() -> None:
    assert models.series_availability([0.999] * 5) == pytest.approx(0.995, abs=0.001)


# ── 27.10 The SOM ───────────────────────────────────────────────────────


def test_the_softmax_sums_to_one_and_keeps_the_order() -> None:
    probabilities = models.softmax([1.0, 2.0, 3.0])
    assert sum(probabilities) == pytest.approx(1.0)
    assert probabilities[2] > probabilities[1] > probabilities[0]


def test_the_temperature_flattens_the_distribution() -> None:
    sharp = models.softmax([1.0, 2.0], temperature=0.1)
    soft = models.softmax([1.0, 2.0], temperature=10.0)
    assert sharp[1] > soft[1]


def test_the_sigmoid_and_the_logit_are_inverses() -> None:
    for value in (0.1, 0.5, 0.9):
        assert models.sigmoid(models.logit(value)) == pytest.approx(value)


def test_combining_the_two_sources_moves_the_result_toward_the_heavier_one() -> None:
    combined = models.combine_logits(0.9, 0.1, weight_som=1.0, weight_llm=1.0)
    assert 0.5 < combined < 0.9
    only_som = models.combine_logits(0.9, 0.1, weight_som=1.0, weight_llm=0.0)
    assert only_som == pytest.approx(0.9, abs=1e-6)


def test_the_value_of_information_is_positive_only_when_asking_is_worth_it() -> None:
    assert models.value_of_information(0.2, 1.0, 0.1) > 0
    assert models.value_of_information(0.95, 1.0, 0.1) < 0


# ── 27.11 Mathematical logic ───────────────────────────────────────────


def test_the_float64_unit_roundoff_is_the_documented_value() -> None:
    assert pytest.approx(1.1e-16, rel=1e-2) == models.FLOAT64_UNIT_ROUNDOFF


def test_the_relative_error_scales_with_the_condition_number() -> None:
    assert models.relative_error(1.0) == pytest.approx(1.1e-16, rel=1e-2)
    assert models.relative_error(1000.0) > models.relative_error(1.0)


def test_the_dimensional_check_catches_a_mismatch() -> None:
    assert models.dimensions_match(models.VELOCITY, models.LENGTH / models.TIME)
    assert not models.dimensions_match(models.FORCE, models.ENERGY)
    assert models.ENERGY.describe() == "kg·m²·s⁻²"


# ── 27.12 Scientific grounding ─────────────────────────────────────────


def test_the_posterior_odds_multiply_by_the_likelihood_ratio() -> None:
    assert models.posterior_odds(2.0, 3.0) == pytest.approx(6.0)


def test_the_confidence_interval_narrows_with_more_samples() -> None:
    low, high = models.confidence_interval(360, 400)
    assert low == pytest.approx(0.871, abs=0.01)
    assert high == pytest.approx(0.929, abs=0.01)
    narrow_low, narrow_high = models.confidence_interval(900, 1000)
    assert (narrow_high - narrow_low) < (high - low)


def test_the_sample_size_for_a_one_percent_margin() -> None:
    assert models.sample_size_for_margin(0.9, 0.01) == pytest.approx(3457, abs=5)


# ── 27.13 Absolute knowledge ───────────────────────────────────────────


def test_the_entropy_of_a_uniform_distribution_is_one_bit() -> None:
    assert models.shannon_entropy([0.5, 0.5]) == pytest.approx(1.0)
    assert models.shannon_entropy([1.0, 0.0]) == pytest.approx(0.0)


def test_the_information_gain_is_the_drop_in_entropy() -> None:
    assert models.information_gain([0.5, 0.5], [1.0, 0.0]) == pytest.approx(1.0)


def test_the_kv_cache_cost_matches_the_specification_example() -> None:
    per_token = models.kv_cache_bytes_per_token(32, 8, 128, 2)
    assert per_token == 131_072
    total = models.kv_cache_bytes(32, 8, 128, 1_000_000, 2)
    assert total == pytest.approx(1.31e11, rel=1e-3)
    quantized = models.kv_cache_bytes(32, 8, 128, 1_000_000, 0.5)
    assert quantized == pytest.approx(3.3e10, rel=1e-2)


# ── the register ────────────────────────────────────────────────────────


def test_there_are_thirteen_qualities_with_their_laws_and_tests() -> None:
    assert len(QUALITIES) == 13
    assert [quality.number for quality in QUALITIES] == list(range(1, 14))
    for quality in QUALITIES:
        assert quality.law and quality.formula and quality.engineering_rule and quality.test
        assert quality.metric
        assert quality.module
    assert len(QUALITY_BY_KEY) == 13


def test_the_three_foundations_that_stay_fixed_are_listed() -> None:
    keys = [key for key, _ in FIXED_FOUNDATIONS]
    assert keys == ["safety", "legal", "honesty"]


def test_the_catalog_exposes_the_register() -> None:
    data = catalog()
    assert data["count"] == 13
    assert len(data["qualities"]) == 13
    assert len(data["fixed_foundations"]) == 3


def test_the_tier_memory_cost_is_reported() -> None:
    report = tier_kv_cache("lite")
    assert report["tokens"] == 128_000
    assert report["kv_bytes_4bit"] < report["kv_bytes_16bit"]


# ── the verifier's math check ──────────────────────────────────────────


def test_the_math_check_catches_a_total_that_does_not_recompute() -> None:
    verifier = Verifier(context=LayerContext())
    result = verifier.verify(
        answer="the total is 99",
        goal="add up the rows",
        recomputed={"total": 120},
    )
    assert result.passed is False
    assert any("recomputes" in reason for reason in result.reasons)


def test_the_math_check_accepts_a_total_that_recomputes() -> None:
    verifier = Verifier(context=LayerContext())
    result = verifier.verify(
        answer="add up the rows: the total is 120",
        goal="add up the rows",
        recomputed={"total": 120},
    )
    assert result.passed is True


def test_the_math_check_catches_probabilities_that_do_not_sum_to_one() -> None:
    verifier = Verifier(context=LayerContext())
    result = verifier.verify(
        answer="the probabilities are 0.3, 0.3 and 0.9",
        goal="state the probabilities",
    )
    assert result.passed is False
    assert any("sums to" in reason for reason in result.reasons)


def test_a_check_that_cannot_be_applied_is_not_a_failure() -> None:
    verifier = Verifier(context=LayerContext())
    result = verifier.verify(answer="the file was read", goal="راجع الملف")
    assert result.passed is True


# ── the world model's prediction quality ────────────────────────────────


def test_the_prediction_quality_needs_samples() -> None:
    world = WorldModel(context=LayerContext())
    assert world.prediction_quality()["samples"] == 0
    assert world.prediction_quality()["nll"] is None


def test_the_prediction_quality_is_computed_from_the_comparisons() -> None:
    world = WorldModel(context=LayerContext())
    prediction = world.predict("file.read", "a.txt")
    world.compare(prediction, "read", ok=True)
    quality = world.prediction_quality()
    assert quality["samples"] == 1
    assert quality["nll"] is not None
    assert math.isfinite(quality["kl"])


# ── the expert-free completion rate ────────────────────────────────────


def test_the_expert_free_rate_counts_runs_that_finished_without_help() -> None:
    result = models.expert_free_completion_rate([(True, False), (True, True), (False, False), (True, False)])
    assert result["samples"] == 4
    assert result["rate"] == pytest.approx(0.5)


def test_the_expert_free_rate_is_not_reported_without_samples() -> None:
    result = models.expert_free_completion_rate([])
    assert result["rate"] is None
    assert result["samples"] == 0
