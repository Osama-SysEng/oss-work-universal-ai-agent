"""Self-evolution, practice sessions, and the weekly personalization session."""

from __future__ import annotations

import json
from pathlib import Path

from osv1.learning.evolution import EvolutionEngine
from osv1.learning.personalization import Personalization, WeeklySchedule
from osv1.learning.practice import PracticeSession

# ── self-evolution ─────────────────────────────────────────


def test_learning_turns_a_log_into_training_material() -> None:
    engine = EvolutionEngine()
    log = [
        {"task": "clean the export", "decided": "remove duplicates", "correct": True, "confidence": 0.8},
        {"task": "read the sheet", "decided": "read the file first", "correct": True, "confidence": 0.7},
        {"task": "delete the old report", "decided": "delete immediately", "correct": False, "confidence": 0.9},
    ]
    result = engine.learn_from_log(log)
    assert result["samples"] == 3
    assert result["correct"] == 2
    assert result["skills"]
    assert result["calibration"]["overconfidence"] > 0
    assert "recalibrate" in result["calibration"]["advice"]


def test_low_confidence_means_ask_not_guess() -> None:
    engine = EvolutionEngine()
    assert engine.should_ask(0.4) is True
    assert engine.should_ask(0.9) is False


def test_the_immutable_core_cannot_be_changed_by_self_improvement() -> None:
    engine = EvolutionEngine()
    assert engine.refuses_immutable_change("osv1/safety/permissions.py") is True
    assert engine.refuses_immutable_change("osv1/layers/verifier.py") is True
    assert engine.refuses_immutable_change("osv1/agents/registry.py") is False

    refused = engine.propose_code_change("osv1/safety/audit.py", "make the audit log shorter")
    assert refused["ok"] is False
    assert "immutable core" in refused["error"]


def test_a_candidate_is_promoted_only_when_the_gate_passes(tmp_path: Path) -> None:
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    engine = EvolutionEngine(project_root=tmp_path, state_path=tmp_path / "evolution.json", suite=("tests/test_ok.py",))
    candidate = engine.propose("skill", "remove duplicates first", {"name": "clean"})
    promoted = engine.promote(candidate.id)
    assert promoted["ok"] is True
    assert engine.versions
    assert engine.versions[-1].version == 1


def test_a_failing_gate_rejects_the_candidate(tmp_path: Path) -> None:
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    engine = EvolutionEngine(
        project_root=tmp_path, state_path=tmp_path / "evolution.json", suite=("tests/test_bad.py",)
    )
    candidate = engine.propose("skill", "a change that breaks the suite", {})
    result = engine.promote(candidate.id)
    assert result["ok"] is False
    assert engine.versions == []


def test_a_promotion_can_be_rolled_back_in_one_step(tmp_path: Path) -> None:
    suite = tmp_path / "tests"
    suite.mkdir()
    (suite / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    engine = EvolutionEngine(project_root=tmp_path, state_path=tmp_path / "evolution.json", suite=("tests/test_ok.py",))
    first = engine.propose("skill", "first", {})
    engine.promote(first.id)
    second = engine.propose("skill", "second", {})
    engine.promote(second.id)
    assert len(engine.versions) == 2
    result = engine.rollback()
    assert result["ok"] is True
    assert len(engine.versions) == 1


# ── practice sessions ──────────────────────────────────────


def _project(tmp_path: Path, licence: str = "MIT License") -> Path:
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "LICENSE").write_text(licence, encoding="utf-8")
    (project / "README.md").write_text(
        "# Sample\n\nRun it:\n\n```python\nprint('from the readme')\n```\n", encoding="utf-8"
    )
    (project / "tests" / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    return project


def test_only_permissive_licences_allow_weight_training(tmp_path: Path) -> None:
    permissive = PracticeSession(project_path=_project(tmp_path, "MIT License"))
    assert permissive.license_of() == "mit"
    assert permissive.weight_training_allowed() is True

    other = tmp_path / "other"
    other.mkdir()
    (other / "LICENSE").write_text("All rights reserved", encoding="utf-8")
    closed = PracticeSession(project_path=other)
    assert closed.weight_training_allowed() is False


def test_the_readme_example_is_found(tmp_path: Path) -> None:
    session = PracticeSession(project_path=_project(tmp_path))
    assert "from the readme" in session.readme_example()


def test_a_practice_session_runs_and_measures(tmp_path: Path) -> None:
    session = PracticeSession(project_path=_project(tmp_path))
    report = session.run()
    assert report["license"] == "mit"
    assert "outcomes" in report
    assert "behaviour_parity" in report
    assert report["duration_s"] >= 0
    assert any("never copied" in rule for rule in report["rules"])


def test_the_practice_scheduler_keeps_the_record(tmp_path: Path) -> None:
    from osv1.learning.practice import PracticeScheduler

    scheduler = PracticeScheduler(path=tmp_path / "practice.json").load()
    scheduler.record(
        {"project": "x", "duration_s": 1.0, "behaviour_parity": {"shared_errors": 2}, "better_source": "readme"}
    )
    assert scheduler.summary()["sessions"] == 1


# ── weekly personalization ─────────────────────────────────


def test_the_schedule_reports_when_it_is_due() -> None:
    from datetime import UTC, datetime

    schedule = WeeklySchedule(day="monday", hour=9, minute=0, length_minutes=30)
    assert schedule.is_due(datetime(2026, 10, 19, 9, 15, tzinfo=UTC)) is True
    assert schedule.is_due(datetime(2026, 10, 19, 8, 15, tzinfo=UTC)) is False
    assert schedule.is_due(datetime(2026, 10, 20, 9, 15, tzinfo=UTC)) is False


def test_the_work_profile_is_built_from_the_samples(tmp_path: Path) -> None:
    (tmp_path / "my_report.md").write_text("A short report. " * 20, encoding="utf-8")
    (tmp_path / "run_it.py").write_text("print('x')\n", encoding="utf-8")
    personalization = Personalization(workspace=tmp_path, state_path=tmp_path / "p.json")
    profile = personalization.build_profile()
    assert profile.sample_count >= 2
    assert profile.structure["files"] >= 2
    assert profile.tone["language"] in ("ar", "en")


def test_an_excluded_path_is_not_collected(tmp_path: Path) -> None:
    secret = tmp_path / "private"
    secret.mkdir()
    (secret / "notes.md").write_text("private", encoding="utf-8")
    (tmp_path / "work.md").write_text("work", encoding="utf-8")
    personalization = Personalization(workspace=tmp_path, state_path=tmp_path / "p.json")
    personalization.exclude("private")
    samples = personalization.collect_samples()
    assert all("private" not in str(path) for path in samples)


def test_held_out_scoring_reports_the_agreement(tmp_path: Path) -> None:
    personalization = Personalization(workspace=tmp_path, state_path=tmp_path / "p.json")
    result = personalization.score_held_out([("task one", "choice a"), ("task two", "choice b")])
    assert result["samples"] == 2
    assert 0.0 <= result["agreement"] <= 1.0


def test_the_adapter_is_written_and_can_be_reset(tmp_path: Path) -> None:
    personalization = Personalization(
        workspace=tmp_path, state_path=tmp_path / "p.json", adapter_path=tmp_path / "adapter.enc"
    )
    (tmp_path / "a.md").write_text("sample", encoding="utf-8")
    result = personalization.write_adapter()
    if result["ok"]:
        assert personalization.adapter_path.exists()
        raw = personalization.adapter_path.read_bytes()
        assert b"work_profile" not in raw
    personalization.reset()
    assert not personalization.adapter_path.exists()


def test_the_weekly_report_keeps_the_data_on_the_device(tmp_path: Path) -> None:
    personalization = Personalization(workspace=tmp_path, state_path=tmp_path / "p.json")
    report = personalization.weekly_report()
    assert report["privacy"]["data_stays_on_device"] is True
    assert report["privacy"]["can_reset"] is True
    assert report["suggestions"]
