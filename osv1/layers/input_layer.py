"""Layer 1 — Multimodal Input (spec section 8.1).

Purpose: accept text, images, data, events, and context.

Contract: nothing enters the system without a source tag and a confidence
value. An unreadable or corrupted input is reported to the user and is never
silently skipped.

Images are recorded with their metadata only. The system does not claim to
read image content, so it does not pretend to.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from osv1.contracts import InputBundle, UnifiedInput
from osv1.layers.context import LayerContext
from osv1.safety.injection import is_untrusted, quarantine

TEXT_LIKE_SUFFIXES = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".tsv", ".html", ".sql", ".log"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}


@dataclass
class InputLayer:
    """Turns raw material into tagged, confidence-bearing inputs."""

    max_chars: int = 40_000

    def ingest_text(
        self, context: LayerContext, text: str, *, source: str = "user", kind: str = "text"
    ) -> UnifiedInput:
        body = text[: self.max_chars]
        item = UnifiedInput(source=source, kind=kind, payload=body, confidence=1.0)
        context.emit("input.received", source=source, kind=kind, chars=len(body))
        return item

    def ingest_file(self, context: LayerContext, path: str | Path) -> UnifiedInput | None:
        """Read a file and tag it. A file that cannot be read is reported."""
        target = Path(path)
        if not target.exists():
            context.emit("input.rejected", source=str(target), reason="the file does not exist")
            return None
        suffix = target.suffix.lower()
        try:
            if suffix in IMAGE_SUFFIXES:
                item = UnifiedInput(
                    source=str(target),
                    kind="image_meta",
                    payload=f"image file, {target.stat().st_size} bytes",
                    confidence=1.0,
                    reference=str(target),
                    meta={"bytes": target.stat().st_size, "analysis": "metadata only: image content is not read"},
                )
            elif suffix in TEXT_LIKE_SUFFIXES or suffix == "":
                body = target.read_text(encoding="utf-8", errors="replace")
                item = UnifiedInput(
                    source=str(target),
                    kind="file",
                    payload=body[: self.max_chars],
                    confidence=0.95,
                    reference=str(target),
                    meta={"bytes": target.stat().st_size, "suffix": suffix},
                )
            else:
                item = UnifiedInput(
                    source=str(target),
                    kind="data",
                    payload=f"binary file, {target.stat().st_size} bytes",
                    confidence=0.4,
                    reference=str(target),
                    meta={"bytes": target.stat().st_size, "suffix": suffix},
                )
        except OSError as exc:
            context.emit("input.rejected", source=str(target), reason=str(exc))
            return None
        context.emit("input.received", source=item.source, kind=item.kind, chars=len(item.payload))
        return item

    def ingest_event(self, context: LayerContext, name: str, detail: str = "") -> UnifiedInput:
        item = UnifiedInput(
            source="event", kind="event", payload=f"{name}: {detail}".strip(": "), confidence=1.0, reference=name
        )
        context.emit("input.received", source="event", kind="event", name=name)
        return item

    def build(
        self, context: LayerContext, inputs: list[UnifiedInput], rejected: list[str] | None = None
    ) -> InputBundle:
        """Bundle the inputs, marking untrusted sources as data."""
        tagged: list[UnifiedInput] = []
        for item in inputs:
            if is_untrusted(item.source):
                safe = quarantine(item.payload, source=item.source)
                item = UnifiedInput(
                    source=item.source,
                    kind=item.kind,
                    payload=safe["text"],
                    confidence=min(item.confidence, 0.9),
                    reference=item.reference,
                    meta={**item.meta, "trust": "untrusted", "flagged": safe["flagged"]},
                )
            tagged.append(item)
        bundle = InputBundle(request_id=context.request_id, inputs=tuple(tagged), rejected=tuple(rejected or ()))
        context.emit(
            "input.ready",
            inputs=len(bundle.inputs),
            rejected=len(bundle.rejected),
            sources=bundle.sources(),
        )
        return bundle

    def from_task(self, context: LayerContext, task: str) -> InputBundle:
        """The common path: one user request."""
        item = self.ingest_text(context, task, source="user", kind="text")
        return self.build(context, [item])
