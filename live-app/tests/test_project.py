# -*- coding: utf-8 -*-
"""Projects: goal → milestones → tasks with state that outlives any run.

Planning, ordered execution, per-task persistence (resume = no rework),
honest failure after one bounce. run_agent is mocked; persistence and the
state machine are REAL (files on disk)."""
import json

import pytest

import osv_agent as ag
import osv_project as pj


PLAN_OK = ('```json\n{"name": "متجر", "milestones": ['
           '{"title": "أساس", "tasks": ["اكتب backend.py", "اكتب tests.py"]}, '
           '{"title": "واجهة", "tasks": ["اكتب ui.html"]}]}\n```')


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(pj, "_root", lambda: tmp_path / "pr")
    (tmp_path / "pr").mkdir(exist_ok=True)


def _gw_plan(cfg, msgs, effort=None, timeout=120, max_tokens=2000):
    return [PLAN_OK]


# ------------------------------------------------------------------- planning

def test_plan_parses_and_normalizes():
    doc = pj.plan("ابنِ متجراً", [{}], _gw_plan)
    assert doc["name"] == "متجر"
    assert [len(m["tasks"]) for m in doc["milestones"]] == [2, 1]
    assert all(t["status"] == "pending" for m in doc["milestones"]
               for t in m["tasks"])


def test_plan_without_chain_is_honest_none():
    assert pj.plan("هدف", [], _gw_plan) is None


def test_plan_bad_json_is_honest_none():
    def gw_bad(cfg, msgs, effort=None, timeout=120, max_tokens=2000):
        return ["نص بلا خطة"]
    assert pj.plan("هدف", [{}], gw_bad) is None


# --------------------------------------------------------------- persistence

def test_save_load_roundtrip_and_status(tmp_path):
    doc = pj.plan("هدف", [{}], _gw_plan)
    pj.save("p1", doc)
    loaded = pj.load("p1")
    assert loaded["name"] == "متجر"
    st = pj.status(loaded)
    assert st["tasks_total"] == 3 and st["tasks_pending"] == 3


def test_load_missing_and_damaged_are_none(tmp_path):
    assert pj.load("لا_يوجد") is None
    (tmp_path / "pr" / "broken.json").write_text("{هش", encoding="utf-8")
    assert pj.load("broken") is None


# ------------------------------------------------------------------- running

def _mk_worker(results):
    """results: list of (final, ok) per call — the fake agent loop."""
    calls = []

    def worker(task, ctx, chain, on_event, memory_brief="", max_steps=None,
               require_steps=0, prior_msgs=None):
        calls.append(task)
        (ctx.workspace / f"out_{len(calls)}.py").write_text(
            f"# {task[:20]}\nx = {len(calls)}\n", encoding="utf-8")
        return results[min(len(calls), len(results)) - 1]

    worker.calls = calls
    return worker


def test_run_project_executes_in_order_and_persists(tmp_path, monkeypatch):
    worker = _mk_worker([("تم 1", True), ("تم 2", True), ("تم 3", True)])
    monkeypatch.setattr(ag, "run_agent", worker)
    doc = pj.plan("هدف", [{}], _gw_plan)
    doc = pj.run_project("p1", doc, [{}], tmp_path / "ws", lambda e: None)
    st = doc["status"]
    assert st["tasks_done"] == 3 and st["tasks_failed"] == 0
    assert len(worker.calls) == 3
    assert all(t["status"] == "done" for m in doc["milestones"]
               for t in m["tasks"])
    # persisted state on disk matches the in-memory doc
    disk = pj.load("p1")
    assert disk["status"]["tasks_done"] == 3


def test_run_project_budget_limits_one_call_and_resumes(tmp_path, monkeypatch):
    worker = _mk_worker([("تم", True)] * 6)
    monkeypatch.setattr(ag, "run_agent", worker)
    monkeypatch.setattr(pj, "_MAX_TASKS_PER_CALL", 2)
    doc = pj.plan("هدف", [{}], _gw_plan)
    doc = pj.run_project("p2", doc, [{}], tmp_path / "ws", lambda e: None)
    assert doc["status"]["tasks_pending"] == 1          # budget stopped it
    assert len(worker.calls) == 2
    # resume: the SAME doc continues where it stopped — no rework
    doc2 = pj.run_project("p2", doc, [{}], tmp_path / "ws", lambda e: None)
    assert len(worker.calls) == 3                        # only ONE more ran
    assert doc2["status"]["tasks_done"] == 3


def test_failed_task_bounces_once_then_fails_honestly(tmp_path, monkeypatch):
    calls = []

    def flaky(task, ctx, chain, on_event, memory_brief="", max_steps=None,
              require_steps=0, prior_msgs=None):
        calls.append(task)
        return ("فشلت المهمة دائماً", False)

    monkeypatch.setattr(ag, "run_agent", flaky)
    doc = pj.plan("هدف", [{}], _gw_plan)
    doc = pj.run_project("p3", doc, [{}], tmp_path / "ws", lambda e: None)
    st = doc["status"]
    assert st["tasks_failed"] == 3 and st["tasks_done"] == 0
    # bounced once = each task ran TWICE (pass 1 + pass 2), then honesty
    assert len(calls) == 6
    assert all(t["attempts"] == 2 for m in doc["milestones"]
               for t in m["tasks"] if t["status"] == "failed")
    # the failures are ON THE RECORD in the persisted file — not hidden
    disk = json.loads((tmp_path / "pr" / "p3.json").read_text(encoding="utf-8"))
    failed_results = [t["result"] for m in disk["milestones"]
                      for t in m["tasks"] if t["status"] == "failed"]
    assert failed_results and all("فشلت" in r for r in failed_results)


def test_already_done_tasks_are_never_rerun(tmp_path, monkeypatch):
    worker = _mk_worker([("تم", True)] * 5)
    monkeypatch.setattr(ag, "run_agent", worker)
    doc = pj.plan("هدف", [{}], _gw_plan)
    for m in doc["milestones"]:
        for t in m["tasks"]:
            if t["desc"].startswith("اكتب backend"):
                t["status"] = "done"          # pretend the first task is done
    doc = pj.run_project("p4", doc, [{}], tmp_path / "ws", lambda e: None)
    assert len(worker.calls) == 2             # only the remaining two ran
