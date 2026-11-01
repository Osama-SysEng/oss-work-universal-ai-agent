"""Sessions: resume the exact conversation + honest absence.

Persistence is real file I/O under data/agent_sessions; the resume wiring
through run_agent is exercised with the same offline fake LLM as the loop
tests."""
import json

import osv_agent as ag
import osv_sessions as ses


def test_save_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    msgs = [{"role": "user", "content": "ابنِ لي جobra"},
            {"role": "assistant", "content": "بنيت الملف"}]
    ses.save("sess1", "مهمة الاختبار", msgs, tmp_path)
    doc = ses.load("sess1")
    assert doc is not None
    assert doc["task"] == "مهمة الاختبار"
    assert doc["workspace"] == str(tmp_path)
    assert doc["msgs"][-1]["content"] == "بنيت الملف"


def test_load_missing_is_none_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    assert ses.load("never_saved") is None
    assert ses.resume_msgs("never_saved") is None


def test_resume_msgs_strips_stale_system(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    ses.save("s2", "قديمة", [{"role": "system", "content": "التوجيه القديم"},
                             {"role": "user", "content": "س"},
                             {"role": "assistant", "content": "ج"}], tmp_path)
    prior = ses.resume_msgs("s2")
    assert prior is not None
    assert all(m["role"] != "system" for m in prior)   # fresh system composed per run
    assert len(prior) == 2


def test_context_ceiling_enforced_on_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    flood = [{"role": "user", "content": f"رسالة {i}"} for i in range(150)]
    ses.save("s3", "طويلة", flood, tmp_path)
    doc = ses.load("s3")
    assert len(doc["msgs"]) == ses.MAX_MSGS            # ceiling on the way in
    prior = ses.resume_msgs("s3")
    assert len(prior) == ses.MAX_MSGS                  # and on the way out


def test_damaged_session_file_returns_none(tmp_path, monkeypatch):
    root = tmp_path / "s"
    root.mkdir()
    (root / "broken.json").write_text("{نص غير json", encoding="utf-8")
    monkeypatch.setattr(ses, "_root", lambda: root)
    assert ses.load("broken") is None


def test_list_sessions_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    ses.save("a", "أولى", [{"role": "user", "content": "x"}], tmp_path)
    ses.save("b", "ثانية", [{"role": "user", "content": "y"}], tmp_path)
    lst = ses.list_sessions()
    assert {d["session_id"] for d in lst} == {"a", "b"}


def test_run_agent_resume_receives_prior_conversation(tmp_path, monkeypatch):
    """The wiring end-to-end: run_agent(prior_msgs=...) must put the prior
    turns + continuation message in front of the model, offline."""
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    prior = [{"role": "user", "content": "المهمة القديمة: ابنِ calc.py"},
             {"role": "assistant", "content": "أنشأت calc.py بالإضافة الصحيحة"}]
    seen_first_prompt = {}

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        seen_first_prompt["msgs"] = [m["content"] for m in msgs]
        return ['```json\n{"tool": "done", "args": {"answer": "أكملت"}}\n```']

    import oss_work_live as m
    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "res")
    final, ok = ag.run_agent("كمّل المهمة", ctx, [{}], lambda e: None,
                             prior_msgs=prior, require_steps=0)
    assert ok and final == "أكملت"
    joined = "\n".join(seen_first_prompt["msgs"])
    assert "أنشأت calc.py" in joined                 # the model SAW the old turn
    assert "استئناف جلسة سابقة" in joined           # and the continuation mark
    assert ctx.msgs is not None and len(ctx.msgs) >= 4   # transcript exposed for saving


def test_single_wave_run_saves_a_real_transcript(tmp_path, monkeypatch):
    """A done in the FIRST wave (no intermediate appends) must still seal the
    final reply into ctx.msgs — otherwise the session file is [system] only
    and there is nothing to resume from (live-measured gap)."""
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        # one parallel wave: write + done in a single reply
        return ['```json\n{"tool": "write_file", "args": {"path": "n.txt", '
                '"content": "7"}}\n```\n'
                '```json\n{"tool": "done", "args": {"answer": "كتبت الرقم '
                'السري 7734 في n.txt"}}\n```']

    import oss_work_live as m
    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    ctx = ag.AgentContext(tmp_path, "sw")
    final, ok = ag.run_agent("اكتب الرقم", ctx, [{}], lambda e: None,
                             max_steps=4, require_steps=0)
    assert ok
    roles = [mm["role"] for mm in ctx.msgs]
    assert roles[-1] == "assistant"                  # the final reply is IN
    assert "7734" in ctx.msgs[-1]["content"]         # with the report content


def test_saved_session_file_is_valid_json_on_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(ses, "_root", lambda: tmp_path / "s")
    ses.save("s9", "ت", [{"role": "user", "content": "مرحبا بالعربية"}], tmp_path)
    p = tmp_path / "s" / "s9.json"
    doc = json.loads(p.read_text(encoding="utf-8"))   # no mojibake, no BOM issues
    assert doc["msgs"][0]["content"] == "مرحبا بالعربية"
