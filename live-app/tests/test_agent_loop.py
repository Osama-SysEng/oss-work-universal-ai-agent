"""The agent loop: honesty rules, adaptive effort, self-check, loop recovery.

Converted from the measured session of 1 Nov 2026 (lessons 38-40) into the
permanent regression suite. Everything runs OFFLINE (the LLM is mocked)."""

import oss_work_live as m
import osv_agent as ag


def _ctx(tmp):
    return ag.AgentContext(tmp, "t")


# ---------------------------------------------------------------- dual-process

def test_task_weight_simple_is_low():
    assert ag.task_weight("اشرح لي الفرق بين list و tuple") == "low"


def test_task_weight_multi_part_build_is_hard():
    assert ag.task_weight("ابنِ مشروعاً كاملاً: واجهة + خلفية + اختبارات") == "hard"


def test_task_weight_long_text_is_hard():
    assert ag.task_weight("وصف طويل " * 30) == "hard"


# ---------------------------------------------------------------- self-check

def test_done_over_unexecuted_tests_bounces_then_runs_them(tmp_path, monkeypatch):
    """The model wrote tests but never ran them → bounced once; the second
    reply runs the test via REAL bash inside the workspace."""
    replies = [
        # reply 1: writes module+test then declares done → must bounce
        ('```json\n{"tool": "write_file", "args": {"path": "calc.py", '
         '"content": "def add(a, b):\\n    return a - b\\n"}}\n```\n'
         '```json\n{"tool": "write_file", "args": {"path": "test_calc.py", '
         '"content": "from calc import add\\nassert add(2, 3) == 5\\n"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "أنجزت!"}}\n```'),
        # reply 2: runs the (failing) test for real → done accepted, but the
        # mandatory honesty note must relay the failure
        ('```json\n{"tool": "bash", "args": {"command": "python test_calc.py"}}'
         '\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "شغّلته"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "t")
    final, _ok = ag.run_agent("اكتب وحدة calc مع اختبارها", ctx,
                              [{}], lambda e: None, max_steps=6)
    assert any("لم تشغّلها" in c for c in calls)          # the bounce fired
    assert any(s["tool"] == "bash" for s in ctx.steps)    # ran the tests for real
    assert (tmp_path / "calc.py").is_file()
    assert "[ملاحظة النظام" in final or "فشل" in final     # failure not hidden


# ---------------------------------------------------------------- loop recovery

def test_infinite_loop_gets_nudge_then_honest_stop(tmp_path, monkeypatch):
    same = '```json\n{"tool": "list_dir", "args": {"path": "."}}\n```'
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [same]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("افحص المساحة", _ctx(tmp_path), [{}],
                             lambda e: None, max_steps=14)
    assert any("غيّر استراتيجيتك" in c for c in calls)   # first loop → nudge
    assert not ok and "حلقة مكررة" in final              # second → honest stop


# ---------------------------------------------------------------- require_steps

def test_done_without_successful_work_is_bounced(tmp_path, monkeypatch):
    replies = [
        '```json\n{"tool": "done", "args": {"answer": "أنجزت بلا عمل!"}}\n```',
        ('```json\n{"tool": "write_file", "args": {"path": "hello.py", '
         '"content": "print(1)"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "كتبت فعلاً"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("اكتب ملف hello.py", _ctx(tmp_path), [{}],
                             lambda e: None, max_steps=6, require_steps=1)
    assert ok and final == "كتبت فعلاً"
    assert (tmp_path / "hello.py").is_file()
    assert any("ممنوع الإنهاء" in c for c in calls)


def test_failed_write_does_not_count_toward_require_steps(tmp_path, monkeypatch):
    """A FAILED action is not work: done right after it must bounce."""
    replies = [
        ('```json\n{"tool": "bash", "args": {"command": "exit 3"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "أنجزت"}}\n```'),
        ('```json\n{"tool": "write_file", "args": {"path": "ok.txt", '
         '"content": "x"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "الآن أنجزت فعلاً"}}\n```'),
    ]
    calls = []

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        return [replies[len(calls) - 1]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    _final, ok = ag.run_agent("مهمة", _ctx(tmp_path), [{}], lambda e: None,
                              max_steps=6, require_steps=1)
    assert ok
    assert any("ممنوع الإنهاء" in c for c in calls)


# ---------------------------------------------------------------- honesty relay

def test_hidden_failure_is_appended_to_final(tmp_path, monkeypatch):
    """A tool failure the model's done-answer ignores gets appended verbatim."""
    replies = [
        ('```json\n{"tool": "bash", '
         '"args": {"command": "python missing_script_xyz.py"}}\n```\n'
         '```json\n{"tool": "done", "args": {"answer": "كل شيء تمام"}}\n```'),
    ]

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        return [replies[0]]

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    final, ok = ag.run_agent("مهمة", _ctx(tmp_path), [{}], lambda e: None,
                             max_steps=4, require_steps=0)
    # ok=True (final text exists) but the failed bash step MUST surface
    assert "[ملاحظة النظام" in final
    assert ok is True
