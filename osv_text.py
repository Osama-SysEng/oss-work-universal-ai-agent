"""osv_text.py — invisible-character hygiene for every file the agent writes.

18 Nov live: the newest workspace's server.py died with
`SyntaxError: invalid non-printable character U+200C` — an Arabic-context
model emitted zero-width joiners inside `from http.server import ...`,
the watchdog relaunched the broken server every 34 s, and the build port
stayed dead. The disease is cheap to prevent at the write boundary: strip
invisible format characters (ZWNJ/ZWJ/bidi marks/BOM) from text before it
touches the disk, and report how many were removed so the action stays
observable.
"""
from __future__ import annotations

# Zero-width and bidi control characters that break Python/JS parsers.
_INVISIBLE = (
    "\u200b", "\u200c", "\u200d", "\u200e", "\u200f",
    "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2060", "\u2061", "\u2062", "\u2063", "\u2064",
    "\ufeff",
)


def strip_invisibles(text: str) -> tuple[str, int]:
    """Return (clean_text, removed_count). Never touches normal Arabic text."""
    if not text:
        return text, 0
    removed = 0
    for ch in _INVISIBLE:
        n = text.count(ch)
        if n:
            removed += n
            text = text.replace(ch, "")
    return text, removed


def note(removed: int) -> str:
    return (f" — 🧹 أُزيلت {removed} محرفاً غير مرئي كان سيكسر الملف"
            if removed else "")
