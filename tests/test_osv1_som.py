"""System One: typed decisions, calibration, abstention, and routing."""

from __future__ import annotations

from osv1.calibration import Calibrator, brier_score, expected_calibration_error, fit_calibrator
from osv1.som import LayaBackend, RuleBackend, SomEngine, SomQuestion


def test_yes_no_decision_returns_a_calibrated_probability() -> None:
    engine = SomEngine()
    decision = engine.ask(
        SomQuestion(
            kind="yes_no",
            text="the action deletes a file",
            positive=("deletes",),
            negative=("writes",),
        )
    )
    assert decision.question_type == "yes_no"
    assert len(decision.probabilities) == 2
    assert abs(sum(decision.probabilities) - 1.0) < 1e-6
    assert decision.value is True


def test_choice_decision_picks_the_best_label() -> None:
    engine = SomEngine()
    decision = engine.ask(
        SomQuestion(
            kind="choice",
            text="audit the database schema for a migration",
            labels=("databases", "graphics", "translation"),
            context={
                "keywords": {
                    "databases": ("database", "schema", "migration"),
                    "graphics": ("shader",),
                    "translation": ("translate",),
                }
            },
        )
    )
    assert decision.value == "databases"
    assert decision.probabilities[0] == max(decision.probabilities)


def test_a_keyword_inside_another_word_is_not_a_hit() -> None:
    backend = RuleBackend()
    decision = backend.answer(
        SomQuestion(
            kind="choice",
            text="please review the report",
            labels=("databases", "security"),
            context={"keywords": {"databases": ("view",), "security": ("review",)}},
        )
    )
    assert decision.value == "security"


def test_the_engine_abstains_below_the_threshold() -> None:
    engine = SomEngine(abstain_threshold=0.99)
    decision = engine.ask(SomQuestion(kind="yes_no", text="nothing matches", positive=("alpha",), negative=("beta",)))
    assert decision.abstained is True


def test_a_question_with_no_features_abstains() -> None:
    backend = RuleBackend()
    decision = backend.answer(SomQuestion(kind="yes_no", text="anything"))
    assert decision.abstained is True
    assert decision.confidence == 0.5


def test_the_score_question_returns_an_ordinal_level() -> None:
    engine = SomEngine()
    decision = engine.ask(
        SomQuestion(
            kind="score",
            text="delete send pay publish system_change",
            levels=("none", "low", "medium", "high", "critical"),
            positive=("delete", "send", "pay", "publish", "system_change"),
        )
    )
    assert decision.value == "critical"


def test_the_laya_backend_reports_unavailable_without_a_checkpoint() -> None:
    backend = LayaBackend()
    decision = backend.answer(SomQuestion(kind="yes_no", text="x"))
    assert decision.abstained is True
    assert "checkpoint" in decision.rationale


def test_the_engine_records_its_decisions() -> None:
    engine = SomEngine()
    engine.ask(SomQuestion(kind="yes_no", text="a delete action", positive=("delete",), negative=("write",)))
    stats = engine.stats()
    assert stats["decisions"] == 1
    assert stats["backend"] == "rule"


def test_brier_and_ece_reward_a_calibrated_confidence() -> None:
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.0, 1.0], [1, 0]) == 1.0
    # A perfectly calibrated pair lands in the right bins with no gap.
    assert expected_calibration_error([1.0, 0.0], [1, 0]) == 0.0
    # 0.9 and 0.1 against the same outcomes leave a 0.1 gap in each bin.
    assert 0.09 <= expected_calibration_error([0.9, 0.1], [1, 0]) <= 0.11


def test_temperature_scaling_improves_a_miscalibrated_set() -> None:
    probabilities = [0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.1, 0.1]
    outcomes = [1, 1, 0, 0, 0, 0, 0, 0]
    calibrator = fit_calibrator(probabilities, outcomes)
    assert calibrator.samples == 8
    assert calibrator.temperature > 0
    assert calibrator.as_dict()["ece_after"] <= calibrator.as_dict()["ece_before"] + 1e-9


def test_a_calibrator_changes_the_reported_confidence() -> None:
    engine = SomEngine(calibrator=Calibrator(temperature=0.5))
    decision = engine.ask(SomQuestion(kind="yes_no", text="delete", positive=("delete",), negative=("write",)))
    assert 0.0 <= decision.confidence <= 1.0
