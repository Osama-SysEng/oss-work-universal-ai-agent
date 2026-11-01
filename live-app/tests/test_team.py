"""The swarm: decompose contract, behavioral gate, merge honesty.

All offline — run_agent and the LLM calls are mocked; the gates run REAL
subprocesses (py_compile + executing real test files)."""
import json

import osv_agent as ag
import osv_team as tm

DEC_TWO = ('```json\n{"streams": [{"name": "backend", "task": "اكتب recv.py"}, '
           '{"name": "front", "task": "اكتب index.html"}]}\n```')


# ---------------------------------------------------------------- decompose

def test_decompose_parses_json_fence(monkeypatch):
    monkeypatch.setattr(tm, "_chat", lambda c, m, max_tokens=2500: DEC_TWO)
    streams = tm.decompose("مهمة", [{}])
    assert streams == [{"name": "backend", "task": "اكتب recv.py", "files": []},
                       {"name": "front", "task": "اكتب index.html", "files": []}]


def test_decompose_failure_returns_none_honestly(monkeypatch):
    monkeypatch.setattr(tm, "_chat", lambda c, m, max_tokens=2500: "نص بلا json")
    assert tm.decompose("م", [{}]) is None


def test_not_decomposable_returns_empty(monkeypatch):
    monkeypatch.setattr(tm, "_chat",
                        lambda c, m, max_tokens=2500: '{"streams": []}')
    assert tm.decompose("م", [{}]) == []


# ---------------------------------------------------------------- syntax gate

def test_ws_py_errors_catches_broken_python(tmp_path):
    (tmp_path / "broken.py").write_text("def f(:\n    pass\n", encoding="utf-8")
    errs = tm.ws_py_errors(tmp_path)
    assert len(errs) == 1 and "broken.py" in errs[0]


def test_ws_py_errors_clean_ws_is_empty(tmp_path):
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    assert tm.ws_py_errors(tmp_path) == []


def test_ws_py_errors_respects_since_window(tmp_path):
    (tmp_path / "old.py").write_text("def f(:\n    pass\n", encoding="utf-8")
    import os
    import time
    old = time.time() - 3600
    os.utime(tmp_path / "old.py", (old, old))
    assert tm.ws_py_errors(tmp_path, since=time.time()) == []   # stale ignored
    assert len(tm.ws_py_errors(tmp_path)) == 1                  # full scan sees it


# ---------------------------------------------------------------- behavior gate

def test_behavior_gate_catches_wrong_logic_that_compiles(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n",
                                      encoding="utf-8")
    (tmp_path / "test_calc.py").write_text(
        "from calc import add\nassert add(2, 3) == 5, 'wrong logic'\n",
        encoding="utf-8")
    errs = tm.ws_behavior_errors(tmp_path)
    assert len(errs) == 1 and "test_calc.py" in errs[0]
    # heal the logic → clean (with __pycache__ immunity: same size + same second)
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n",
                                      encoding="utf-8")
    assert tm.ws_behavior_errors(tmp_path) == []


# ---------------------------------------------------------------- run_team

def _fake_worker(tmp_root, backend_broken=True):
    def worker(task, ctx, chain, on_event, memory_brief="", max_steps=None,
               require_steps=0):
        if ctx.workspace.name == "backend":
            fixed = backend_broken and "أصلح" in task   # جولة الشفاء تُطيع
            (ctx.workspace / "calc.py").write_text(
                "def add(a, b):\n    return a + b\n" if fixed or not backend_broken
                else "def add(a, b):\n    return a - b\n", encoding="utf-8")
            (ctx.workspace / "test_calc.py").write_text(
                "from calc import add\nassert add(2, 3) == 5\n", encoding="utf-8")
            return "بنيت backend", True
        (ctx.workspace / "index.html").write_text("<html></html>",
                                                  encoding="utf-8")
        return "بنيت الواجهة", True
    return worker


def test_run_team_full_pipeline_catches_and_heals(tmp_path, monkeypatch):
    dec = json.dumps({"streams": [
        {"name": "backend", "task": "ا", "files": ["calc.py", "test_calc.py"]},
        {"name": "front", "task": "ب", "files": ["index.html"]}]},
        ensure_ascii=False)
    monkeypatch.setattr(tm, "_chat",
                        lambda c, m, max_tokens=2500: (dec if "يوزع" in m[-1]["content"]
                                                       else "تقرير مدمج"))
    monkeypatch.setattr(ag, "run_agent", _fake_worker(tmp_path))
    res = tm.run_team("ابنِ", tmp_path, "t1", [{}], {}, lambda e: None)
    assert res is not None
    _merged, _ok, info = res
    be = next(s for s in info["streams"] if s["name"] == "backend")
    assert be["py_errors"] == 0            # syntax was fine all along
    assert be["test_errors"] >= 1          # the BEHAVIORAL gate caught it
    assert be["healed"] is True            # ...and the heal round reports it
    assert len(info["files"]) >= 2         # products across worker workspaces


def test_run_team_missing_deliverables_disclosed(tmp_path, monkeypatch):
    dec = json.dumps({"streams": [
        {"name": "w1", "task": "ا", "files": ["calc.py", "phantom.py"]},
        {"name": "w2", "task": "ب", "files": []}]}, ensure_ascii=False)
    monkeypatch.setattr(tm, "_chat",
                        lambda c, m, max_tokens=2500: (dec if "يوزع" in m[-1]["content"]
                                                       else "مدمج"))

    def worker(task, ctx, chain, on_event, memory_brief="", max_steps=None,
               require_steps=0):
        if ctx.workspace.name == "w1":
            (ctx.workspace / "calc.py").write_text("x = 1\n", encoding="utf-8")
            return "كتبت calc.py", True
        (ctx.workspace / "readme.md").write_text("# hi\n", encoding="utf-8")
        return "كتبت readme", True

    monkeypatch.setattr(ag, "run_agent", worker)
    merged, ok, info = tm.run_team("مشروع", tmp_path, "t2", [{}], {},
                                   lambda e: None)
    w1 = next(s for s in info["streams"] if s["name"] == "w1")
    assert "phantom.py" in (w1.get("missing_files") or [])
    assert ok is False
    assert "لم تُنتَج" in merged


def test_run_team_hidden_failure_surfaced_in_merge(tmp_path, monkeypatch):
    dec = json.dumps({"streams": [
        {"name": "w1", "task": "أ", "files": []},
        {"name": "w2", "task": "ب", "files": []}]}, ensure_ascii=False)
    monkeypatch.setattr(tm, "_chat",
                        lambda c, m, max_tokens=2500: (dec if "يوزع" in m[-1]["content"]
                                                       else "كل شيء تمام بلا مشاكل"))

    def worker(task, ctx, chain, on_event, memory_brief="", max_steps=None,
               require_steps=0):
        if ctx.workspace.name == "w1":
            return "أنجزت", False            # failed but SAYS success
        return "تم", True

    monkeypatch.setattr(ag, "run_agent", worker)
    merged, ok, _info = tm.run_team("مهمة", tmp_path, "t3", [{}], {},
                                    lambda e: None)
    assert "[ملاحظة النظام" in merged and "w1" in merged
    assert ok is False
