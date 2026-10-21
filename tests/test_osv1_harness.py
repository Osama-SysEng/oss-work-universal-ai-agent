"""The evaluation harness: the per-layer suites, error injection, independence."""

from __future__ import annotations

from pathlib import Path

from osv1.eval.harness import LAYER_SUITES, Harness


def test_every_layer_of_the_architecture_has_a_suite() -> None:
    for layer in ("input", "world", "reasoning", "decision", "verifier", "action", "safety"):
        assert layer in LAYER_SUITES
        assert LAYER_SUITES[layer]


def test_the_verifier_catches_the_seeded_errors() -> None:
    harness = Harness(project_root=Path.cwd())
    injected = harness.inject_errors()
    seeded = [item for item in injected if not item.name.startswith("control:")]
    control = [item for item in injected if item.name.startswith("control:")]

    assert len(seeded) == 5
    assert all(item.caught for item in seeded), [item.as_dict() for item in seeded if not item.caught]
    # The control case must pass, or the catch rate means nothing.
    assert all(item.caught for item in control)


def test_the_catch_rate_is_reported_with_its_samples() -> None:
    harness = Harness(project_root=Path.cwd())
    injected = harness.inject_errors()
    seeded = [item for item in injected if not item.name.startswith("control:")]
    caught = sum(1 for item in seeded if item.caught)
    assert caught / len(seeded) == 1.0
    assert len(seeded) == 5


def test_the_independence_check_runs_the_core_without_the_model() -> None:
    harness = Harness(project_root=Path.cwd())
    result = harness.independence_check()
    assert result["ok"] is True, result


def test_a_missing_suite_is_reported_not_hidden(tmp_path: Path) -> None:
    harness = Harness(project_root=tmp_path, suites={"nothing": ("tests/test_missing.py",)})
    result = harness.run_suite("nothing", ("tests/test_missing.py",))
    assert result.passed is False
    assert result.missing
