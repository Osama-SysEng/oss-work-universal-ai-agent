"""The cascade measurement and the held-out suite.

The suite's graders are tested against stub runtimes with known answers, so
a grader that would pass a fabricated answer, or fail a correct one, fails
here instead of hiding inside a report. Running the suite against the real
engine is measured separately, and never in the offline suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from osv1.eval.cascade import CascadeRecorder
from osv1.eval.graded import (
    CODE_TASKS,
    GAP_TASKS,
    MATH_TASKS,
    ROUTING_TASKS,
    GradedSuite,
    Task,
    _numbers_in,
    grade_code,
    grade_gap,
    grade_math,
)

# ── the cascade recorder ───────────────────────────────────────────────


def test_the_cascade_counts_the_escalations_of_the_fast_path() -> None:
    recorder = CascadeRecorder()
    recorder.record_som(10.0, abstained=False)
    recorder.record_som(20.0, abstained=True)
    recorder.record_som(30.0, abstained=True)
    report = recorder.report()
    assert report["som_decisions"] == 3
    assert report["som_abstentions"] == 2
    assert report["q_abstain"] == 0.6667


def test_the_cascade_measures_both_times_and_the_expected_time() -> None:
    recorder = CascadeRecorder()
    recorder.record_som(100.0, abstained=True)  # T1 = 100 ms, always escalates
    recorder.record_llm(500.0, ok=True)  # T2 = 500 ms
    report = recorder.report()
    assert report["t1_median_ms"] == 100.0
    assert report["t2_median_ms"] == 500.0
    assert report["expected_time_ms"] == 600.0  # E[T] = T1 + q·T2 = 100 + 1·500


def test_the_cascade_reports_an_unreachable_model_as_unreachable() -> None:
    recorder = CascadeRecorder()
    recorder.record_llm(5.0, ok=False)
    recorder.record_llm(7.0, ok=True)
    report = recorder.report()
    assert report["llm_reachable_calls"] == 1
    assert report["llm_unreachable_calls"] == 1
    assert report["q_llm"] == 0.5


def test_an_empty_recorder_reports_nothing_rather_than_zero() -> None:
    report = CascadeRecorder().report()
    assert report["q_abstain"] is None
    assert report["expected_time_ms"] is None
    assert report["samples_som"] == 0


def test_the_percentiles_are_taken_from_the_sample() -> None:
    recorder = CascadeRecorder()
    for value in (1.0, 2.0, 3.0, 4.0, 100.0):
        recorder.record_som(value, abstained=False)
    report = recorder.report()
    assert report["t1_p50_ms"] == 3.0
    assert report["t1_p95_ms"] == 100.0


def test_the_recorder_can_be_reset_between_runs() -> None:
    recorder = CascadeRecorder()
    recorder.record_som(1.0, abstained=True)
    recorder.reset()
    assert recorder.report()["som_decisions"] == 0


# ── the stub runtime the graders are tested against ────────────────────


@dataclass
class StubResult:
    answer: str = ""
    status: str = "completed"


@dataclass
class StubRuntime:
    """Answers with a fixed text, and routes to a fixed agent."""

    answer: str = ""
    status: str = "completed"
    agent: Any = None
    info: dict[str, Any] = field(default_factory=dict)

    def build(self, task: str) -> StubResult:
        return StubResult(answer=self.answer, status=self.status)

    def route(self, task: str) -> tuple[Any, dict[str, Any]]:
        return self.agent, self.info


def _task(kind: str, prompt: str, expected: Any) -> Task:
    return Task(id=f"stub-{kind}", kind=kind, prompt=prompt, expected=expected)


# report() asks the runtime for its cascade and its engine; the stub answers
# without building a real one, so these tests never touch the database.


class _StubCascade:
    def report(self, *, distribution: str = "") -> dict[str, Any]:
        return {"q_abstain": 0.5, "distribution": distribution, "som_decisions": 4}


class _StubEngine:
    def describe(self) -> dict[str, Any]:
        return {"model": "stub-model", "up": False}


@dataclass
class StubReportRuntime:
    cascade: Any = field(default_factory=_StubCascade)
    engine: Any = field(default_factory=_StubEngine)


def held_out_stub() -> dict[str, Any]:
    return {"trivial": [], "inconsistent": [], "held_out": True, "routing_tasks": 0}


def runtime_for_report() -> Any:
    return StubReportRuntime()


# ── the graders ────────────────────────────────────────────────────────


def test_the_math_grader_accepts_a_correct_number_in_any_wording() -> None:
    runtime = StubRuntime(answer="ناتج العملية هو 391 وفق الحساب.")
    result = grade_math(runtime, _task("math", "17 × 23", 391))
    assert result.passed is True


def test_the_math_grader_rejects_a_wrong_number() -> None:
    runtime = StubRuntime(answer="الناتج 392")
    result = grade_math(runtime, _task("math", "17 × 23", 391))
    assert result.passed is False
    assert "392" in result.detail


def test_the_math_grader_reports_an_answer_with_no_number() -> None:
    runtime = StubRuntime(answer="لا يمكنني إجراء العملية")
    result = grade_math(runtime, _task("math", "17 × 23", 391))
    assert result.passed is False
    assert "no number" in result.detail


def test_the_gap_grader_passes_an_answer_that_admits_it_does_not_know() -> None:
    runtime = StubRuntime(answer="لا أعرف، ولا يمكن معرفة اسم الملف.")
    result = grade_gap(runtime, _task("gap", "ما اسم الملف؟", "abstain"))
    assert result.passed is True


def test_the_gap_grader_fails_an_answer_that_fabricates() -> None:
    runtime = StubRuntime(answer="اسم الملف هو report.pdf بالتأكيد.")
    result = grade_gap(runtime, _task("gap", "ما اسم الملف؟", "abstain"))
    assert result.passed is False


def test_a_status_that_asks_instead_of_guessing_passes_the_gap_grader() -> None:
    runtime = StubRuntime(answer="", status="needs_information")
    result = grade_gap(runtime, _task("gap", "ما اسم الملف؟", "abstain"))
    assert result.passed is True


def test_the_code_grader_runs_the_code_in_the_sandbox() -> None:
    runtime = StubRuntime(answer="```python\ndef total(xs):\n    return sum(xs)\n```")
    result = grade_code(runtime, _task("code", "اجمع قائمة", "assert total([1, 2, 3]) == 6"))
    assert result.passed is True


def test_the_code_grader_fails_code_that_breaks_its_own_tests() -> None:
    runtime = StubRuntime(answer="```python\ndef total(xs):\n    return 0\n```")
    result = grade_code(runtime, _task("code", "اجمع قائمة", "assert total([1, 2, 3]) == 6"))
    assert result.passed is False


def test_the_code_grader_fails_an_answer_with_no_code() -> None:
    runtime = StubRuntime(answer="سأكتبها لك لاحقاً.")
    result = grade_code(runtime, _task("code", "اجمع قائمة", "assert total([1]) == 1"))
    assert result.passed is False
    assert "no code" in result.detail


def test_the_numbers_of_an_answer_are_extracted_with_decimals() -> None:
    assert _numbers_in("17 و3.5 و-2") == [17.0, 3.5, -2.0]


# ── a question is not an answer ────────────────────────────────────────


def test_a_number_inside_a_question_is_not_a_pass() -> None:
    """The decision engine may quote the right number among its options.

    The answer to "17 × 23" was a question offering 391 and two wrong
    alternatives. Scoring that a pass would grade the question, not an
    answer, so the status is checked first.
    """
    runtime = StubRuntime(
        answer="أيّ خيار يكمل المهمة؟ حاصل 17 × 23 هو 391 | الحساب خاطئ وليس 391 | الناتج 392",
        status="needs_information",
    )
    result = grade_math(runtime, _task("math", "17 × 23", 391))
    assert result.passed is False
    assert "needs_information" in result.detail


def test_a_planned_or_awaiting_approval_run_has_delivered_no_code() -> None:
    for status in ("planned", "needs_approval", "needs_information"):
        runtime = StubRuntime(answer="```python\ndef total(xs):\n    return sum(xs)\n```", status=status)
        result = grade_code(runtime, _task("code", "اجمع قائمة", "assert total([1]) == 1"))
        assert result.passed is False
        assert status in result.detail


def test_an_answer_cut_off_before_its_closing_fence_is_still_graded() -> None:
    """The token budget truncates long answers; the code present is graded.

    Failing for a missing closing fence would measure markdown style, not
    the code the system actually delivered.
    """
    runtime = StubRuntime(answer="```python\ndef total(xs):\n    return sum(xs)\n")
    result = grade_code(runtime, _task("code", "اجمع قائمة", "assert total([1, 2]) == 3"))
    assert result.passed is True
    assert "passed its own tests" in result.detail


# ── the suite's own structure ──────────────────────────────────────────


def test_the_suite_has_the_task_inventory_it_claims() -> None:
    assert len(ROUTING_TASKS) == 30
    assert len(MATH_TASKS) == 15
    assert len(GAP_TASKS) == 8
    assert len(CODE_TASKS) == 5
    assert len(ROUTING_TASKS) + len(MATH_TASKS) + len(GAP_TASKS) + len(CODE_TASKS) == 58


def test_the_math_answers_are_computed_from_the_arithmetic_itself() -> None:
    assert MATH_TASKS[0].expected == 391
    assert MATH_TASKS[1].expected == 1111
    assert MATH_TASKS[2].expected == 4096
    assert MATH_TASKS[3].expected == 210


def test_no_routing_task_is_a_bare_keyword() -> None:
    check = GradedSuite().held_out_check()
    assert check["trivial"] == []
    assert check["held_out"] is True
    assert check["routing_tasks"] == 30


def test_a_task_that_is_one_keyword_is_refused_instead_of_scored() -> None:
    suite = GradedSuite(tasks=(_task("arabic_routing", "شبك", ("networks", "analysis")),))
    check = suite.held_out_check()
    assert check["held_out"] is False
    assert check["trivial"] == ["stub-arabic_routing"]


def test_the_suite_names_what_a_check_cannot_prove() -> None:
    check = GradedSuite().held_out_check()
    assert "no check can prove" in check["note"]


def test_every_task_carries_its_ground_truth() -> None:
    for task in ROUTING_TASKS + MATH_TASKS + GAP_TASKS + CODE_TASKS:
        assert task.prompt and task.expected is not None
    kinds = {task.kind for task in ROUTING_TASKS + MATH_TASKS + GAP_TASKS + CODE_TASKS}
    assert kinds == {"arabic_routing", "math", "gap", "code"}


# ── the qualities that a held-out snapshot measures ────────────────────


def _snapshot() -> dict[str, Any]:
    return {
        "score": 0.6,
        "graded": 50,
        "ci95": [0.46, 0.74],
        "engine": {"model": "qwen2.5-3b", "up": True},
        "per_kind": {
            "arabic_routing": {"score": 0.3, "samples": 30},
            "gap": {"score": 0.75, "samples": 8},
        },
        "cascade": {
            "q_abstain": 0.98,
            "q_llm": 1.0,
            "t1_p50_ms": 40.0,
            "t2_p50_ms": 72000.0,
            "expected_time_ms": 70600.0,
            "som_decisions": 60,
        },
    }


def test_a_snapshot_measures_the_qualities_it_actually_can() -> None:
    from osv1.eval.harness import Harness

    measured = Harness._qualities_from_graded(_snapshot())
    assert measured["intelligence"]["value"] == 0.6
    assert measured["intelligence"]["samples"] == 50
    assert measured["intelligence"]["ci95"] == [0.46, 0.74]
    assert measured["intelligence"]["model"] == "qwen2.5-3b"
    assert measured["human-mind"]["q_abstain"] == 0.98
    assert measured["absolute-knowledge"]["value"] == 0.75
    assert measured["absolute-knowledge"]["samples"] == 8


def test_the_routing_score_is_reported_as_what_it_is() -> None:
    from osv1.eval.harness import Harness

    measured = Harness._qualities_from_graded(_snapshot())
    routing = measured["intelligence"]["routing"]
    assert routing["value"] == 0.3
    assert routing["samples"] == 30
    assert "never from the router" in routing["note"]


def test_the_absent_snapshot_is_reported_as_absent_rather_than_zero() -> None:
    from osv1.eval.harness import Harness

    suite = GradedSuite()
    assert suite.project_root == Path.cwd()
    # A harness whose project root holds no snapshot reports none.
    harness = Harness(project_root=Path("./no-such-directory"))
    assert harness._graded_snapshot() is None


def test_a_snapshot_with_no_graded_tasks_is_not_used() -> None:
    import json
    import tempfile

    from osv1.eval.harness import Harness

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data-osv1").mkdir()
        (root / "data-osv1" / "graded-evaluation.json").write_text(
            json.dumps({"graded": 0, "score": None}), encoding="utf-8"
        )
        assert Harness(project_root=root)._graded_snapshot() is None


def test_an_unparsable_snapshot_is_refused_rather_than_crashing() -> None:
    import tempfile

    from osv1.eval.harness import Harness

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "data-osv1").mkdir()
        (root / "data-osv1" / "graded-evaluation.json").write_text("{not json", encoding="utf-8")
        assert Harness(project_root=root)._graded_snapshot() is None


# ── the report keeps every task, so a failure can be diagnosed later ───


def test_the_report_keeps_every_task_and_its_detail() -> None:
    runtime = StubRuntime(answer="الناتج 391")
    tasks = (Task(id="m1", kind="math", prompt="17 × 23", expected=391),)
    suite = GradedSuite()
    report = suite.report(
        [grade_math(runtime, tasks[0])],
        skipped=[],
        held_out=held_out_stub(),
        runtime=runtime_for_report(),
        engine_up=False,
    )
    assert len(report["tasks"]) == 1
    entry = report["tasks"][0]
    assert entry["task_id"] == "m1"
    assert entry["passed"] is True
    assert "391" in entry["detail"]
    assert "seconds" in entry and "source" in entry


# ── the model is named from the engine, not from an environment variable ─


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


def test_the_llama_shape_and_the_openai_shape_are_both_read(monkeypatch: Any) -> None:
    import osv1.engine.local_engine as local_engine

    engine = local_engine.LocalEngine(model_label="local")

    monkeypatch.setattr(
        local_engine.httpx, "get", lambda *a, **k: _FakeResponse({"models": [{"name": "/path/qwen2.5-3b.gguf"}]})
    )
    assert engine.models() and engine.models()[0]["name"].endswith("qwen2.5-3b.gguf")

    monkeypatch.setattr(local_engine.httpx, "get", lambda *a, **k: _FakeResponse({"data": [{"id": "some-model"}]}))
    assert engine.models()[0]["id"] == "some-model"

    monkeypatch.setattr(local_engine.httpx, "get", lambda *a, **k: _FakeResponse({}))
    assert engine.models() == []


def test_the_describe_names_the_file_the_engine_serves(monkeypatch: Any) -> None:
    import osv1.engine.local_engine as local_engine

    engine = local_engine.LocalEngine(model_label="local")
    monkeypatch.setattr(
        local_engine.httpx,
        "get",
        lambda *a, **k: _FakeResponse({"models": [{"name": "C:\\tools\\llama\\models\\qwen2.5-3b-q4_k_m.gguf"}]}),
    )
    described = engine.describe()
    assert described["model"] == "qwen2.5-3b-q4_k_m.gguf"
    assert described["reported_by_engine"] is True
    assert described["model_label"] == "local"  # the operator's label stays visible


def test_when_the_engine_reports_nothing_the_label_is_used_and_said_to_be_a_label(monkeypatch: Any) -> None:
    import osv1.engine.local_engine as local_engine

    engine = local_engine.LocalEngine(model_label="my-label")
    monkeypatch.setattr(local_engine.httpx, "get", lambda *a, **k: _FakeResponse({}))
    described = engine.describe()
    assert described["model"] == "my-label"
    assert described["reported_by_engine"] is False
