"""The context window: fitting, overflow, summarization, and checkpoints."""

from __future__ import annotations

from pathlib import Path

from osv1.context import ChunkStore, ContextWindow, estimate_tokens, split_sentences


def test_the_token_estimate_is_stated_and_reasonable() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 400) == 100


def test_a_short_request_fits_whole() -> None:
    window = ContextWindow(window_tokens=1000, reserve_for_output=100)
    plan = window.fit([("user", "review the readme")])
    assert plan.overflowed is False
    assert plan.used_tokens < 1000
    assert plan.text() == "review the readme"


def test_an_oversized_request_is_summarized_and_not_dropped() -> None:
    window = ContextWindow(window_tokens=200, reserve_for_output=50)
    plan = window.fit([("file", "sentence one. " * 500)])
    assert plan.overflowed is True
    assert plan.summarized or plan.dropped
    assert any("summarized" in note for note in plan.notes)
    # Nothing disappears without a record.
    assert len(plan.kept) + len(plan.summarized) + len(plan.dropped) == 1


def test_the_rule_summary_keeps_the_head_and_counts_the_rest() -> None:
    text = "First point. Second point. Third point. Fourth point. Fifth point. Sixth point."
    summary = ContextWindow._rule_summary(text)
    assert "First point." in summary
    assert "more sentences" in summary


def test_the_summary_uses_the_model_when_it_is_available() -> None:
    class FakeEngine:
        def complete(self, prompt, max_tokens=400):
            return {"source": "local_engine", "content": "the summary from the model"}

    window = ContextWindow(window_tokens=200, reserve_for_output=50, summarizer=FakeEngine())
    plan = window.fit([("file", "word " * 2000)])
    assert plan.overflowed is True
    assert plan.summarized[0].text == "the summary from the model"
    assert "local_engine" in plan.summarized[0].reason


def test_the_window_comes_from_the_device_tier() -> None:
    from osv1.config import DEVICE_TIERS, Settings

    settings = Settings.load()
    assert settings.context_tokens == DEVICE_TIERS[settings.tier].context_tokens


def test_the_chunk_store_resumes_an_interrupted_generation(tmp_path: Path) -> None:
    store = ChunkStore(directory=tmp_path, request_id="req-1")
    assert store.completed() == []
    store.write(1, "first chunk")
    store.write(2, "second chunk")
    assert store.completed() == [1, 2]
    assert store.read(1) == "first chunk"
    assert store.read(3) is None
    store.clear()
    assert store.completed() == []


def test_the_sentence_splitter_keeps_arabic_endings() -> None:
    sentences = split_sentences("هذه جملة. وهذه أخرى؟ ونهاية")
    assert len(sentences) == 3
    assert sentences[1].endswith("؟")
