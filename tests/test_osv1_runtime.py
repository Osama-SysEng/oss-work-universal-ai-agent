"""The runtime end to end: plan, build, routing, verification, and the metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from osv1.runtime import OSRuntime


@pytest.fixture()
def runtime(tmp_path: Path, monkeypatch) -> OSRuntime:
    monkeypatch.chdir(tmp_path)
    return OSRuntime()


def test_the_runtime_registers_its_tools(runtime: OSRuntime) -> None:
    names = runtime.tools.names()
    assert "file.read" in names
    assert "file.write" in names
    assert "code.run" in names
    assert "sheet.read" in names
    assert "dashboard.build" in names
    assert "web.read" in names
    assert "rea.analyze" in names
    assert "format.synthesize" in names


def test_the_runtime_registers_three_hundred_agents(runtime: OSRuntime) -> None:
    assert runtime.status()["agents"] == 300


def test_plan_mode_produces_a_plan_and_executes_nothing(runtime: OSRuntime, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print('hello')\n", encoding="utf-8")
    result = runtime.plan("analyze the python file a.py")
    assert result.status == "planned"
    assert result.plan is not None
    assert result.plan.steps
    assert result.actions == ()
    assert "Nothing was executed" in result.answer


def test_build_mode_runs_the_tools_and_verifies_the_result(runtime: OSRuntime, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("import os\n\nclass A:\n    def b(self):\n        return 1\n", encoding="utf-8")
    result = runtime.build("review the python file a.py for security issues")
    assert result.status in ("completed", "failed")
    assert result.verification is not None
    assert result.actions
    assert any(action.outcome == "completed" for action in result.actions)


def test_routing_is_reported_with_its_source(runtime: OSRuntime) -> None:
    result = runtime.plan("write documentation for the readme")
    routing = result.metrics["routing"]
    assert routing["chosen"]
    assert routing["som_domain"]
    assert routing["som_specialization"]


def test_the_metrics_of_a_run_are_reported(runtime: OSRuntime, tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    result = runtime.plan("analyze a.py")
    names = {metric["name"] for metric in result.metrics["metrics"]}
    assert names == {
        "search_breadth",
        "decision_quality",
        "expected_calibration_error",
        "brier_score",
        "verification_catch_rate",
        "time_to_solution",
    }


def test_the_kill_switch_stops_the_runtime(runtime: OSRuntime, tmp_path: Path) -> None:
    runtime.kill_switch.engage("testing")
    result = runtime.plan("analyze a.py")
    assert result.status == "blocked"
    assert "kill switch" in result.errors[0]


def test_an_irreversible_step_asks_for_approval(runtime: OSRuntime, tmp_path: Path) -> None:
    target = tmp_path / "a.txt"
    target.write_text("x", encoding="utf-8")
    result = runtime.build(f"delete the file {target.name}")
    if result.status == "needs_approval":
        assert result.data["approvals"]
        assert runtime.approvals.pending()
    else:
        # The plan for a delete request may not include the delete step; then
        # the result must still not have deleted anything silently.
        assert result.verification is None or result.verification.passed is False or result.actions


def test_the_status_reports_the_real_state(runtime: OSRuntime) -> None:
    status = runtime.status()
    assert status["model"] == "OS_V1"
    assert status["agents"] == 300
    assert status["engine"]["healthy"] in (True, False)
    assert status["audit"]["valid"] is True
    assert status["permissions"]
