"""The context window: what fits, what overflows, and what happens then.

Spec section 10 sets the capacity rules: the input window scales with the
task, the output is produced as long-horizon chunks with checkpoints that can
be resumed, and when a task exceeds the window, retrieval and summarization
from memory take over so nothing is dropped silently.

The window size comes from the device tier (spec section 23): Lite 128K,
Standard 256K, Pro 1M. These are planning targets, and the code reports the
number it actually used.

Token counting is an estimate — roughly four characters per token for mixed
English and Arabic text. The estimate is stated wherever it is used, because
a capacity claim needs an honest method behind it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHARS_PER_TOKEN = 4
SENTENCE_END = re.compile(r"(?<=[.!?؟।])\s+")
PARAGRAPH = re.compile(r"\n\s*\n")


def estimate_tokens(text: str) -> int:
    """Estimate the token count of a text. Four characters per token."""
    return max(1, len(text) // CHARS_PER_TOKEN) if text else 0


def split_sentences(text: str) -> list[str]:
    """Split into sentences, keeping Arabic punctuation as an ending."""
    parts = [part.strip() for part in SENTENCE_END.split(text) if part.strip()]
    return parts or ([text.strip()] if text.strip() else [])


def split_paragraphs(text: str) -> list[str]:
    """Split into paragraphs, then into sentences inside each."""
    blocks = [block.strip() for block in PARAGRAPH.split(text) if block.strip()]
    return blocks or ([text.strip()] if text.strip() else [])


@dataclass
class ContextPiece:
    """One piece of input as it enters the window."""

    source: str
    text: str
    tokens: int
    kept: bool = True
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "tokens": self.tokens,
            "kept": self.kept,
            "reason": self.reason,
        }


@dataclass
class ContextPlan:
    """What went into the window, what was summarized, and what was dropped."""

    window_tokens: int
    used_tokens: int = 0
    kept: list[ContextPiece] = field(default_factory=list)
    summarized: list[ContextPiece] = field(default_factory=list)
    dropped: list[ContextPiece] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def overflowed(self) -> bool:
        return bool(self.summarized or self.dropped)

    def text(self) -> str:
        """The text that actually enters the window."""
        return "\n\n".join(piece.text for piece in self.kept if piece.kept)

    def as_dict(self) -> dict[str, Any]:
        return {
            "window_tokens": self.window_tokens,
            "used_tokens": self.used_tokens,
            "overflowed": self.overflowed,
            "kept": [piece.as_dict() for piece in self.kept],
            "summarized": [piece.as_dict() for piece in self.summarized],
            "dropped": [piece.as_dict() for piece in self.dropped],
            "notes": list(self.notes),
        }


@dataclass
class ContextWindow:
    """Fits inputs into the window, and overflows into memory rather than silence."""

    window_tokens: int = 128_000
    reserve_for_output: int = 8_000
    summarize: bool = True
    summarizer: Any = None  # an LlmClient, when one is available

    @property
    def input_budget(self) -> int:
        """The room left for the input once the output reserve is set aside."""
        return max(1, self.window_tokens - self.reserve_for_output)

    def fit(self, pieces: list[tuple[str, str]]) -> ContextPlan:
        """Fit the pieces into the window, summarizing what does not fit."""
        plan = ContextPlan(window_tokens=self.window_tokens)
        measured = [(source, text, estimate_tokens(text)) for source, text in pieces]
        total = sum(tokens for _, _, tokens in measured)
        if total <= self.input_budget:
            for source, text, tokens in measured:
                plan.kept.append(ContextPiece(source=source, text=text, tokens=tokens))
            plan.used_tokens = total
            return plan

        plan.notes.append(
            f"the request is about {total} tokens, and the window holds {self.input_budget} for the input"
        )
        # Keep the newest and the shortest that fit; summarize the rest.
        budget = self.input_budget
        for source, text, tokens in reversed(measured):
            if tokens <= budget:
                plan.kept.append(ContextPiece(source=source, text=text, tokens=tokens))
                budget -= tokens
            else:
                plan.summarized.append(ContextPiece(source=source, text=text, tokens=tokens))
        plan.kept.reverse()
        plan.used_tokens = sum(piece.tokens for piece in plan.kept)

        for piece in plan.summarized:
            summary, source_name = self._summarize(piece.text)
            piece.text = summary
            piece.reason = f"summarized ({source_name}) because it did not fit in the window"
            plan.notes.append(f"{piece.source}: summarized instead of dropped")
        if plan.summarized:
            plan.notes.append("nothing was dropped silently: every overflowed piece is listed with what replaced it")
        return plan

    def _summarize(self, text: str) -> tuple[str, str]:
        """Summarize a piece. The local model when it is up, the rules otherwise."""
        if self.summarizer is not None:
            result: dict[str, Any] = {}
            try:
                result = self.summarizer.complete(
                    "Summarize the text below in at most five sentences. Keep the facts and the numbers.\n\n"
                    + text[:20000],
                    max_tokens=400,
                )
            except Exception:  # noqa: BLE001 - the rule summary is the fallback
                result = {}
            if result.get("source") == "local_engine" and result.get("content", "").strip():
                return result["content"].strip(), "local_engine"
        return self._rule_summary(text), "rules"

    @staticmethod
    def _rule_summary(text: str, *, max_sentences: int = 5) -> str:
        """An extractive summary: the first sentences and the sizes involved."""
        sentences = split_sentences(text)
        if not sentences:
            return ""
        head = sentences[:max_sentences]
        tail = f" … (+{len(sentences) - max_sentences} more sentences)" if len(sentences) > max_sentences else ""
        return " ".join(head) + tail


@dataclass
class ChunkStore:
    """Checkpoints for long-horizon output, so an interruption resumes."""

    directory: Path = field(default_factory=lambda: Path("./data-osv1/state"))
    request_id: str = ""

    def folder(self) -> Path:
        path = self.directory / (self.request_id or "default")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def read(self, index: int) -> str | None:
        path = self.folder() / f"chunk_{index:03d}.txt"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def write(self, index: int, text: str) -> Path:
        path = self.folder() / f"chunk_{index:03d}.txt"
        path.write_text(text, encoding="utf-8")
        return path

    def completed(self) -> list[int]:
        folder = self.folder()
        if not folder.exists():
            return []
        indexes: list[int] = []
        for path in folder.glob("chunk_*.txt"):
            try:
                indexes.append(int(path.stem.split("_")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(indexes)

    def clear(self) -> None:
        folder = self.folder()
        if folder.exists():
            for path in folder.glob("chunk_*.txt"):
                path.unlink()
