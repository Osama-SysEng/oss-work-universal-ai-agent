"""The brain pipeline: live streaming logic (lesson 41) — think blocks must
never leak, the visible answer must stream the moment it exists."""
import osv_brain as br

CHAIN_ONE = [{"provider": "p1", "key": "k", "model": "m"}]
CHAIN_TWO = [{"provider": "pa", "key": "k", "model": "m1"},
             {"provider": "pb", "key": "k", "model": "m2"}]


def test_classify_fast_for_short_greeting():
    assert br.classify("مرحبا") == "fast"
    assert br.classify("") == "fast"


def test_classify_think_and_deep():
    assert br.classify("لماذا تفشل المشاريع البرمجية؟") in ("think", "deep")
    assert br.classify("اشرح " * 60) == "deep"          # len > 140


def _run(chunks, chain, message="سؤال", **kw):
    def fake_stream(cfg, msgs, effort=None, timeout=240, max_tokens=3000):
        return list(chunks)

    seen = []
    final, trace = br.run_brain(message, [], chain, fake_stream,
                                on_delta=seen.append, **kw)
    return final, trace, seen


def test_think_block_hidden_then_visible_streams():
    final, _tr, seen = _run(
        ["<think>سر تفكيري</think>", "الجواب: ", "42"], CHAIN_ONE)
    assert final == "الجواب: 42"
    assert all("سر تفكيري" not in d for d in seen)      # thinking never leaks
    assert "".join(seen) == "الجواب: 42"                 # streamed in order


def test_no_think_block_streams_every_chunk_immediately():
    final, _tr, seen = _run(["قطعة1 ", "قطعة2 ", "قطعة3"], CHAIN_ONE)
    assert final == "قطعة1 قطعة2 قطعة3"
    assert seen == ["قطعة1 ", "قطعة2 ", "قطعة3"]         # live, not at the end


def test_unclosed_think_block_falls_back_to_whole_text():
    final, _tr, seen = _run(["<think>بدأت أفكر ولم أغلق"], CHAIN_ONE)
    assert final == "<think>بدأت أفكر ولم أغلق"
    assert "".join(seen) == final                        # consistent view


def test_deep_verdict_clean_streams_the_draft():
    """critic says سليمة → synthesis skipped → the DRAFT is the answer and
    must reach on_delta (it was buffered while the verdict was pending)."""
    calls = []

    def fake_stream(cfg, msgs, effort=None, timeout=240, max_tokens=3000):
        calls.append(msgs[-1]["content"])
        if "مدقق نقدي صارم" in msgs[-1]["content"]:
            return ["الحكم: سليمة"]
        return ["<think>تحليل</think>المسودة المُقرّة"]

    seen = []
    final, trace = br.run_brain("سؤال عميق " * 30, [], CHAIN_TWO, fake_stream,
                                on_delta=seen.append)
    assert final == "المسودة المُقرّة"
    assert trace.get("skipped_synthesis") is True
    assert "".join(seen) == "المسودة المُقرّة"


def test_split_think_shapes():
    assert br.split_think("<think>a</think>b") == ("a", "b")
    assert br.split_think("no block") == ("", "no block")
