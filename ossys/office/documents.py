"""Built-in office suite (local). Honest capability ladder:

- txt / markdown / csv: native, always available (stdlib).
- docx: only if python-docx is installed, else a clear error.
- slides: notes -> single-file HTML deck (stdlib, no dependency).
- xlsx/pptx native editing: NOT claimed. Refused with the exact reason.

All paths are confined to the OS workspace.
"""

from __future__ import annotations

import csv
import html
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from ossys import config


class OfficeError(RuntimeError):
    pass


def _confine(name: str) -> str:
    base = os.path.abspath(config.workspace_dir())
    os.makedirs(base, exist_ok=True)
    target = os.path.abspath(os.path.join(base, name))
    if target != base and not target.startswith(base + os.sep):
        raise OfficeError(f"Path escapes workspace: {name!r}")
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    return target


# ── Documents ──────────────────────────────────────────────


def write_text(name: str, content: str) -> dict:
    if os.path.splitext(name)[1].lower() not in (".txt", ".md"):
        raise OfficeError("write_text supports .txt/.md only.")
    path = _confine(name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    return {"path": path, "chars": len(content)}


def read_text(name: str) -> str:
    path = _confine(name)
    if not os.path.isfile(path):
        raise OfficeError(f"Not found: {name!r}")
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def append_note(name: str, line: str) -> dict:
    path = _confine(name)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"\n[{stamp}] {line}\n")
    return {"path": path}


def read_docx(name: str) -> str:
    """Read .docx paragraphs. Requires python-docx — never faked."""
    try:
        from docx import Document
    except ImportError as exc:
        raise OfficeError("Reading .docx needs 'python-docx' (pip install python-docx).") from exc
    path = _confine(name)
    if not os.path.isfile(path):
        raise OfficeError(f"Not found: {name!r}")
    doc = Document(path)
    return "\n".join(p.text for p in doc.paragraphs)


# ── Sheets (CSV, native) ───────────────────────────────────


@dataclass
class SheetSummary:
    rows: int
    columns: list[str]
    numeric_sums: dict[str, float]


def write_sheet(name: str, rows: list[dict]) -> dict:
    if os.path.splitext(name)[1].lower() != ".csv":
        raise OfficeError("Sheets are local .csv files.")
    if not rows:
        raise OfficeError("No rows to write.")
    path = _confine(name)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return {"path": path, "rows": len(rows)}


def read_sheet(name: str) -> list[dict]:
    path = _confine(name)
    if not os.path.isfile(path):
        raise OfficeError(f"Not found: {name!r}")
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def append_sheet_row(name: str, row: dict) -> dict:
    path = _confine(name)
    exists = os.path.isfile(path) and os.path.getsize(path) > 0
    with open(path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)
    return {"path": path}


def summarize_sheet(name: str) -> SheetSummary:
    rows = read_sheet(name)
    columns = list(rows[0].keys()) if rows else []
    sums: dict[str, float] = {}
    for col in columns:
        total = 0.0
        numeric = False
        for row in rows:
            try:
                total += float(row[col])
                numeric = True
            except (TypeError, ValueError):
                continue
        if numeric:
            sums[col] = round(total, 4)
    return SheetSummary(rows=len(rows), columns=columns, numeric_sums=sums)


# ── Slides (notes -> HTML deck) ────────────────────────────


def build_deck(title: str, slides: list[str], out_name: str = "deck.html") -> dict:
    """Build a single-file HTML slide deck from plain-text slides."""
    if not slides:
        raise OfficeError("Deck needs at least one slide.")
    if os.path.splitext(out_name)[1].lower() != ".html":
        raise OfficeError("Decks are single-file .html.")
    cards = "".join(
        f"<section><h2>Slide {i}</h2><p>{html.escape(text).replace(chr(10), '<br>')}</p></section>"
        for i, text in enumerate(slides, 1)
    )
    page = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:sans-serif;background:#111;color:#eee;margin:0}"
        "section{min-height:90vh;display:flex;flex-direction:column;justify-content:center;"
        "align-items:center;padding:4rem;text-align:center;border-bottom:2px solid #333}"
        "h2{color:#7dd3fc}p{max-width:60ch;line-height:1.7}</style></head><body>"
        f"<section><h1>{html.escape(title)}</h1><p>Built locally by oss-work OS.</p></section>"
        f"{cards}</body></html>"
    )
    path = _confine(out_name)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return {"path": path, "slides": len(slides)}
