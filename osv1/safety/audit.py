"""A tamper-evident audit log (spec section 19).

Every action and every self-evolution step is recorded. Each entry carries the
hash of the previous entry, so a removed or edited line breaks the chain and
:func:`verify_chain` reports where. The log never stores secret values: the
keys that commonly hold them are replaced with a marker before writing.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

REDACTED_KEYS = {
    "token",
    "secret",
    "password",
    "passwd",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "set-cookie",
    "private_key",
    "access_key",
    "content",
    "body",
    "payload",
}
GENESIS_HASH = "0" * 64


def _parse(text: str) -> tuple[list[dict[str, Any]], list[int]]:
    """Split raw JSON lines into entries, recording what cannot be read.

    A line that does not parse is damage, not absence: dropping it silently
    would let the last entry of a log be destroyed without
    ``verify_chain`` noticing, so the numbers are kept for it.
    """
    entries: list[dict[str, Any]] = []
    damaged: list[int] = []
    for number, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            damaged.append(number)
    return entries, damaged


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).lower() in REDACTED_KEYS:
                cleaned[key] = "[redacted]"
            else:
                cleaned[key] = _redact(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


@dataclass
class AuditLog:
    """A hash-chained, append-only log stored as JSON lines."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/audit.log"))
    entries: list[dict[str, Any]] = field(default_factory=list)
    # Line numbers in the file that could not be parsed. A line that is not
    # readable is damage, not absence: skipping it silently would let the
    # last entry of a log be destroyed without `verify_chain` noticing.
    damaged: list[int] = field(default_factory=list)

    def load(self) -> AuditLog:
        """Read the file into memory, under the same lock writes take.

        The lock is mandatory on Windows, so it is taken and released on the
        *same* handle the read comes from: opening the file a second time to
        read it while another writer holds byte 0 fails with
        ``PermissionError(13)`` — which is what a concurrent read raised
        before this was here.
        """
        if not self.path.exists():
            self.entries, self.damaged = [], []
            return self
        with self.path.open("a+", encoding="utf-8") as handle:
            self._lock(handle)
            try:
                handle.seek(0)
                text = handle.read()
            finally:
                self._unlock(handle)
        self.entries, self.damaged = _parse(text)
        return self

    # ── writing ───────────────────────────────────────────────

    @staticmethod
    def compute_hash(entry: dict[str, Any], previous: str) -> str:
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(f"{previous}{payload}".encode()).hexdigest()

    def _lock(self, handle: Any) -> Any:
        """Hold an exclusive lock on the log for the duration of one write.

        Two writers that both took ``previous`` from their own memory
        produced entries whose ``prev`` matched nothing — the chain broke
        under ordinary concurrent use, which is the exact signature the
        chain exists to detect. The lock makes read-tail-then-append one
        indivisible step. ``msvcrt`` on Windows, ``fcntl`` elsewhere.
        """
        if os.name == "nt":
            import msvcrt

            # Byte 0, not the end: every writer must contend on the same
            # byte, or two of them could lock two different positions and
            # append at the same time.
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _unlock(self, handle: Any) -> None:
        if os.name == "nt":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _tail_hash(self, handle: TextIO) -> str:
        """The hash of the last *readable* line on disk, read under the lock.

        A half-written trailing line is damage the next verification has to
        see, but it is not a reason to chain the new entry onto the genesis
        hash — that would report a break where the file was merely torn, and
        hide the real chain. So the last line that parses is used, and the
        torn line stays visible to :meth:`verify_chain` through
        :attr:`damaged`.
        """
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            return GENESIS_HASH
        handle.seek(0)
        for line in reversed(list(handle)):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            head = parsed.get("hash") if isinstance(parsed, dict) else None
            if isinstance(head, str) and head:
                return head
        return GENESIS_HASH

    def record(
        self,
        event: str,
        *,
        actor: str = "osv1",
        target: str = "",
        outcome: str = "ok",
        request_id: str = "",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Append one entry, chained to what is on disk right now.

        The previous hash is read from the file under the lock, never from
        this process's in-memory list: another writer may have appended
        since this one loaded, and a stale ``previous`` is what broke the
        chain before.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a+", encoding="utf-8") as handle:
            self._lock(handle)
            try:
                previous = self._tail_hash(handle)
                entry: dict[str, Any] = {
                    "timestamp": datetime.now(UTC).isoformat(),
                    "event": event,
                    "actor": actor,
                    "target": target,
                    "outcome": outcome,
                    "request_id": request_id,
                    "details": _redact(details or {}),
                    "prev": previous,
                }
                entry["hash"] = self.compute_hash(entry, previous)
                handle.seek(0, os.SEEK_END)
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
                # Bring the in-memory view up to date while the lock is still
                # held, through this same handle. Reopening the file to read
                # it after unlocking raised PermissionError(13): another
                # writer may own byte 0 by then, and the lock is mandatory.
                handle.seek(0)
                text = handle.read()
            finally:
                self._unlock(handle)

        # The file is the source of truth: entries other writers added while
        # this one was locked out are now part of the view too.
        self.entries, self.damaged = _parse(text)
        return entry

    # ── reading ───────────────────────────────────────────────

    def verify_chain(self) -> dict[str, Any]:
        """Check that no entry was edited, removed, or left unreadable.

        A line that does not parse is damage, not absence: without this the
        last entry of a log could be destroyed and the chain would still
        report valid, because the loader skips what it cannot read.
        """
        if self.damaged:
            return {
                "valid": False,
                "broken_at": self.damaged[0],
                "reason": f"{len(self.damaged)} line(s) in the log could not be read",
                "damaged": list(self.damaged),
            }
        previous = GENESIS_HASH
        for index, entry in enumerate(self.entries):
            if entry.get("prev") != previous:
                return {"valid": False, "broken_at": index, "reason": "the previous hash does not match"}
            recomputed = self.compute_hash({k: v for k, v in entry.items() if k != "hash"}, previous)
            if recomputed != entry.get("hash"):
                return {"valid": False, "broken_at": index, "reason": "the entry hash does not match its content"}
            previous = entry["hash"]
        return {"valid": True, "entries": len(self.entries), "head": previous}

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.entries[-limit:]

    def events(self, name: str) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry.get("event") == name]
