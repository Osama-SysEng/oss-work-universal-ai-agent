"""The built-in office suite, kept on the same honest capability ladder.

- txt / markdown / csv: native, always available.
- docx: only when python-docx is installed, otherwise a clear error.
- slides: notes to a single-file HTML deck.
- Native xlsx and pptx editing is not claimed here; the spreadsheet engine in
  :mod:`osv1.tools.spreadsheet` writes real ``.xlsx`` files, and anything
  else is refused with the exact reason.

Every path is confined to the workspace directory.
"""

from __future__ import annotations

import csv
import html
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from osv1.config import Settings
from osv1.tools.registry import RISK_READ, RISK_WRITE, Tool, ToolResult


class OfficeError(RuntimeError):
    """The office suite cannot do this, and says why."""


@dataclass
class Office:
    """Document, sheet, and deck helpers confined to the workspace."""

    settings: Settings = field(default_factory=Settings.load)  # type: ignore[name-defined]

    def __post_init__(self) -> None:
        self.workspace = Path(self.settings.workspace_dir).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)

    def confine(self, name: str) -> Path:
        base = self.workspace
        target = (base / name).resolve()
        if target != base and base not in target.parents:
            raise OfficeError(f"path escapes the workspace: {name!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    # ── documents ─────────────────────────────────────────────

    def write_text(self, name: str, content: str) -> dict:
        if Path(name).suffix.lower() not in (".txt", ".md"):
            raise OfficeError("write_text supports .txt and .md only.")
        path = self.confine(name)
        path.write_text(content, encoding="utf-8")
        return {"path": str(path), "chars": len(content)}

    def read_text(self, name: str) -> str:
        path = self.confine(name)
        if not path.is_file():
            raise OfficeError(f"not found: {name!r}")
        return path.read_text(encoding="utf-8")

    def append_note(self, name: str, line: str) -> dict:
        path = self.confine(name)
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{stamp}] {line}\n")
        return {"path": str(path)}

    def read_docx(self, name: str) -> str:
        """Read .docx paragraphs. Requires python-docx — never faked."""
        try:
            from docx import Document
        except ImportError as exc:
            raise OfficeError("reading .docx needs 'python-docx' (pip install python-docx).") from exc
        path = self.confine(name)
        if not path.is_file():
            raise OfficeError(f"not found: {name!r}")
        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    # ── sheets ────────────────────────────────────────────────

    def write_sheet(self, name: str, rows: list[dict]) -> dict:
        if Path(name).suffix.lower() != ".csv":
            raise OfficeError("sheets are local .csv files.")
        if not rows:
            raise OfficeError("no rows to write.")
        path = self.confine(name)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return {"path": str(path), "rows": len(rows)}

    def read_sheet(self, name: str) -> list[dict]:
        path = self.confine(name)
        if not path.is_file():
            raise OfficeError(f"not found: {name!r}")
        with path.open("r", encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def summarize_sheet(self, name: str) -> dict:
        rows = self.read_sheet(name)
        columns = list(rows[0].keys()) if rows else []
        sums: dict[str, float] = {}
        for column in columns:
            total = 0.0
            numeric = False
            for row in rows:
                try:
                    total += float(row[column])
                    numeric = True
                except (TypeError, ValueError):
                    continue
            if numeric:
                sums[column] = round(total, 4)
        return {"rows": len(rows), "columns": columns, "numeric_sums": sums}

    # ── slides ────────────────────────────────────────────────

    def build_deck(self, title: str, slides: list[str], out_name: str = "deck.html") -> dict:
        """Build a single-file HTML slide deck from plain-text slides."""
        if not slides:
            raise OfficeError("a deck needs at least one slide.")
        if Path(out_name).suffix.lower() != ".html":
            raise OfficeError("decks are single-file .html.")
        cards = "".join(
            f"<section><h2>Slide {index}</h2><p>{html.escape(text).replace(chr(10), '<br>')}</p></section>"
            for index, text in enumerate(slides, 1)
        )
        page = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(title)}</title>"
            "<style>body{font-family:sans-serif;background:#111;color:#eee;margin:0}"
            "section{min-height:90vh;display:flex;flex-direction:column;justify-content:center;"
            "align-items:center;padding:4rem;text-align:center;border-bottom:2px solid #333}"
            "h2{color:#7dd3fc}p{max-width:60ch;line-height:1.7}</style></head><body>"
            f"<section><h1>{html.escape(title)}</h1><p>Built locally by OSS Work / OS_V1.</p></section>"
            f"{cards}</body></html>"
        )
        path = self.confine(out_name)
        path.write_text(page, encoding="utf-8")
        return {"path": str(path), "slides": len(slides)}


def register(registry: Any, office: Office | None = None) -> None:
    """Register the office tools."""
    suite = office or Office()
    registry.register(
        Tool(
            name="office.write",
            description="Write a text or markdown file into the workspace.",
            risk=RISK_WRITE,
            handler=lambda name, content: ToolResult(ok=True, output=suite.write_text(name, content)),
        )
    )
    registry.register(
        Tool(
            name="office.read",
            description="Read a text file from the workspace.",
            risk=RISK_READ,
            handler=lambda name: ToolResult(ok=True, output=suite.read_text(name)),
        )
    )
    registry.register(
        Tool(
            name="office.deck",
            description="Build a single-file HTML slide deck from plain-text slides.",
            risk=RISK_WRITE,
            handler=lambda title, slides, out_name="deck.html": ToolResult(
                ok=True, output=suite.build_deck(title, slides, out_name)
            ),
        )
    )
