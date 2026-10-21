"""Memory with four separate types (spec section 14).

The specification keeps four kinds apart on purpose, so a fact never blurs
into an experience, a skill, or a guess:

1. facts — verified information.
2. experiences — what was tried, what happened, and why.
3. skills — reusable procedures that worked, with their conditions and tests.
4. assumptions — tagged as assumptions, revocable, never treated as facts.

Everything is stored locally in SQLite, versioned, and under the user's
control: the user can read it, correct it, delete it, export it, and roll it
back to an earlier snapshot.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MEMORY_TYPES = ("fact", "experience", "skill", "assumption")

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    user_id     TEXT NOT NULL DEFAULT 'local',
    title       TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    confidence  REAL NOT NULL DEFAULT 1.0,
    status      TEXT NOT NULL DEFAULT 'active',
    version     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL DEFAULT 'local',
    label       TEXT NOT NULL DEFAULT '',
    snapshot    TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_kind ON memory_entries(kind);
CREATE INDEX IF NOT EXISTS idx_memory_user ON memory_entries(user_id);
"""

TOKEN = re.compile(r"[a-z0-9_]+")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tokens(text: str) -> set[str]:
    return set(TOKEN.findall(text.lower()))


@dataclass
class MemoryEntry:
    """One stored item of any of the four types."""

    id: int
    kind: str
    user_id: str
    title: str
    content: str
    metadata: dict[str, Any]
    confidence: float
    status: str
    version: int
    created_at: str
    updated_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "status": self.status,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class MemoryStore:
    """The local memory of the system."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/memory.db"))
    user_id: str = "local"
    _local: threading.local = field(default_factory=threading.local, repr=False)

    # ── plumbing ──────────────────────────────────────────────

    def _new_connection(self) -> sqlite3.Connection:
        """Open a short-lived connection."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self.path), timeout=10.0)
        connection.row_factory = sqlite3.Row
        connection.executescript(SCHEMA)
        connection.commit()
        return connection

    def connect(self) -> sqlite3.Connection:
        """Return the connection that belongs to the calling thread.

        The store is used from the API's worker threads as well as from the
        command line. SQLite forbids sharing one connection between threads,
        so every thread keeps its own.
        """
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = self._new_connection()
            self._local.connection = connection
        return connection

    def close(self) -> None:
        """Close the connection of the calling thread."""
        connection = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None

    # ── writing ───────────────────────────────────────────────

    def add(
        self,
        kind: str,
        content: str,
        *,
        title: str = "",
        metadata: dict[str, Any] | None = None,
        confidence: float = 1.0,
        user_id: str | None = None,
    ) -> MemoryEntry:
        if kind not in MEMORY_TYPES:
            raise ValueError(f"unknown memory type: {kind!r}")
        if not content.strip():
            raise ValueError("a memory entry needs content")
        connection = self.connect()
        stamp = _now()
        cursor = connection.execute(
            "INSERT INTO memory_entries (kind, user_id, title, content, metadata, confidence, status,"
            " version, created_at, updated_at) VALUES (?,?,?,?,?,?,'active',1,?,?)",
            (
                kind,
                user_id or self.user_id,
                title[:200],
                content,
                json.dumps(metadata or {}, ensure_ascii=False),
                float(confidence),
                stamp,
                stamp,
            ),
        )
        connection.commit()
        return self.get(int(cursor.lastrowid))

    def add_fact(self, content: str, **kwargs: Any) -> MemoryEntry:
        return self.add("fact", content, **kwargs)

    def add_experience(
        self,
        content: str,
        *,
        predicted: str = "",
        observed: str = "",
        lesson: str = "",
        **kwargs: Any,
    ) -> MemoryEntry:
        metadata = dict(kwargs.pop("metadata", {}) or {})
        metadata.update({"predicted": predicted, "observed": observed, "lesson": lesson})
        return self.add("experience", content, metadata=metadata, **kwargs)

    def add_skill(
        self,
        name: str,
        procedure: str,
        *,
        conditions: str = "",
        tests: str = "",
        **kwargs: Any,
    ) -> MemoryEntry:
        metadata = dict(kwargs.pop("metadata", {}) or {})
        metadata.update({"conditions": conditions, "tests": tests, "uses": 0, "successes": 0, "failures": 0})
        return self.add("skill", procedure, title=name, metadata=metadata, **kwargs)

    def add_assumption(self, statement: str, *, basis: str = "", confidence: float = 0.5, **kwargs: Any) -> MemoryEntry:
        metadata = dict(kwargs.pop("metadata", {}) or {})
        metadata["basis"] = basis
        return self.add("assumption", statement, metadata=metadata, confidence=confidence, **kwargs)

    def confirm_assumption(self, entry_id: int, *, as_fact: bool = True) -> MemoryEntry | None:
        """Turn an assumption into a fact, or retire it."""
        entry = self.get(entry_id)
        if entry is None or entry.kind != "assumption":
            return None
        if as_fact:
            self.update(entry_id, kind="fact", confidence=1.0, metadata={**entry.metadata, "confirmed_from": entry.id})
        else:
            self.update(entry_id, status="revoked", confidence=0.0)
        return self.get(entry_id)

    def revoke_assumption(self, entry_id: int) -> MemoryEntry | None:
        entry = self.get(entry_id)
        if entry is None:
            return None
        self.update(entry_id, status="revoked", confidence=0.0)
        return self.get(entry_id)

    def update(
        self,
        entry_id: int,
        *,
        content: str | None = None,
        kind: str | None = None,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
        confidence: float | None = None,
        status: str | None = None,
    ) -> MemoryEntry | None:
        entry = self.get(entry_id)
        if entry is None:
            return None
        connection = self.connect()
        new_content = entry.content if content is None else content
        new_metadata = entry.metadata if metadata is None else metadata
        connection.execute(
            "UPDATE memory_entries SET content=?, kind=?, title=?, metadata=?, confidence=?, status=?,"
            " version=version+1, updated_at=? WHERE id=?",
            (
                new_content,
                kind or entry.kind,
                title if title is not None else entry.title,
                json.dumps(new_metadata, ensure_ascii=False),
                entry.confidence if confidence is None else float(confidence),
                status or entry.status,
                _now(),
                entry_id,
            ),
        )
        connection.commit()
        return self.get(entry_id)

    def record_skill_use(self, entry_id: int, *, success: bool) -> MemoryEntry | None:
        entry = self.get(entry_id)
        if entry is None or entry.kind != "skill":
            return None
        metadata = dict(entry.metadata)
        metadata["uses"] = int(metadata.get("uses", 0)) + 1
        key = "successes" if success else "failures"
        metadata[key] = int(metadata.get(key, 0)) + 1
        return self.update(entry_id, metadata=metadata)

    def delete(self, entry_id: int) -> bool:
        connection = self.connect()
        cursor = connection.execute("DELETE FROM memory_entries WHERE id=?", (entry_id,))
        connection.commit()
        return cursor.rowcount > 0

    # ── reading ───────────────────────────────────────────────

    def get(self, entry_id: int) -> MemoryEntry | None:
        row = self.connect().execute("SELECT * FROM memory_entries WHERE id=?", (entry_id,)).fetchone()
        return self._row_to_entry(row) if row else None

    @staticmethod
    def _row_to_entry(row: sqlite3.Row) -> MemoryEntry:
        try:
            metadata = json.loads(row["metadata"])
        except (json.JSONDecodeError, TypeError):
            metadata = {}
        return MemoryEntry(
            id=int(row["id"]),
            kind=row["kind"],
            user_id=row["user_id"],
            title=row["title"],
            content=row["content"],
            metadata=metadata,
            confidence=float(row["confidence"]),
            status=row["status"],
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list(
        self,
        *,
        kind: str | None = None,
        user_id: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[MemoryEntry]:
        # The query is chosen from a fixed set and every value is bound, so no
        # part of the statement is ever built from user input.
        statement = "SELECT * FROM memory_entries"
        clauses: list[str] = []
        params: list[Any] = []
        if kind:
            clauses.append("kind=?")
            params.append(kind)
        if user_id:
            clauses.append("user_id=?")
            params.append(user_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            statement = f"{statement} WHERE {' AND '.join(clauses)}"
        params.append(limit)
        rows = self.connect().execute(f"{statement} ORDER BY id DESC LIMIT ?", params).fetchall()
        return [self._row_to_entry(row) for row in rows]

    def retrieve(
        self,
        query: str,
        *,
        kinds: Iterable[str] = MEMORY_TYPES,
        user_id: str | None = None,
        limit: int = 5,
    ) -> list[tuple[MemoryEntry, float]]:
        """Retrieve the entries most relevant to a query.

        Relevance is a transparent score: token overlap with the query,
        weighted by confidence and recency. It is not a learned model, and it
        does not pretend to be one.
        """
        wanted = set(kinds)
        query_tokens = _tokens(query)
        now = time.time()
        scored: list[tuple[MemoryEntry, float]] = []
        for entry in self.list(kind=None, user_id=user_id, status="active", limit=500):
            if entry.kind not in wanted:
                continue
            entry_tokens = _tokens(f"{entry.title} {entry.content}")
            overlap = len(query_tokens & entry_tokens)
            if query_tokens and overlap == 0:
                continue
            coverage = overlap / max(1, len(query_tokens))
            try:
                age_days = max(0.0, (now - datetime.fromisoformat(entry.updated_at).timestamp()) / 86400)
            except (TypeError, ValueError):
                age_days = 0.0
            recency = 1.0 / (1.0 + age_days / 30.0)
            score = coverage * 0.6 + entry.confidence * 0.25 + recency * 0.15
            scored.append((entry, round(score, 4)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return scored[:limit]

    # ── versioning and export ─────────────────────────────────

    def snapshot(self, label: str = "") -> int:
        """Store a restorable snapshot of the whole memory."""
        connection = self.connect()
        rows = connection.execute("SELECT * FROM memory_entries").fetchall()
        payload = [self._row_to_entry(row).as_dict() for row in rows]
        cursor = connection.execute(
            "INSERT INTO memory_versions (user_id, label, snapshot, created_at) VALUES (?,?,?,?)",
            (self.user_id, label[:200], json.dumps(payload, ensure_ascii=False), _now()),
        )
        connection.commit()
        return int(cursor.lastrowid)

    def versions(self) -> list[dict[str, Any]]:
        rows = (
            self.connect()
            .execute("SELECT id, user_id, label, created_at FROM memory_versions ORDER BY id DESC")
            .fetchall()
        )
        return [dict(row) for row in rows]

    def rollback(self, version_id: int) -> int:
        """Restore a snapshot. The current state is snapshotted first."""
        row = self.connect().execute("SELECT snapshot FROM memory_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            raise ValueError(f"no memory version {version_id}")
        self.snapshot(label=f"before rollback to {version_id}")
        payload = json.loads(row["snapshot"])
        connection = self.connect()
        connection.execute("DELETE FROM memory_entries")
        for item in payload:
            connection.execute(
                "INSERT INTO memory_entries (kind, user_id, title, content, metadata, confidence, status,"
                " version, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    item["kind"],
                    item["user_id"],
                    item["title"],
                    item["content"],
                    json.dumps(item["metadata"], ensure_ascii=False),
                    item["confidence"],
                    item["status"],
                    item["version"],
                    item["created_at"],
                    item["updated_at"],
                ),
            )
        connection.commit()
        return len(payload)

    def export(self, *, user_id: str | None = None) -> dict[str, Any]:
        """Export the memory in a portable form, at the user's request."""
        entries = [entry.as_dict() for entry in self.list(user_id=user_id, status="", limit=10000)]
        return {
            "exported_at": _now(),
            "product": "OSS Work / OS_V1",
            "entries": entries,
            "count": len(entries),
        }

    def stats(self) -> dict[str, Any]:
        rows = self.connect().execute("SELECT kind, COUNT(*) AS total FROM memory_entries GROUP BY kind").fetchall()
        counts = {row["kind"]: int(row["total"]) for row in rows}
        return {
            "counts": {kind: counts.get(kind, 0) for kind in MEMORY_TYPES},
            "total": sum(counts.values()),
            "versions": len(self.versions()),
        }
