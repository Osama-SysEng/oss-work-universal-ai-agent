"""A tamper-evident audit log (spec section 19).

Every action and every self-evolution step is recorded. Each entry carries the
hash of the previous entry, so a removed or edited line breaks the chain and
:func:`verify_chain` reports where. The log never stores secret values: the
keys that commonly hold them are replaced with a marker before writing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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

    def load(self) -> AuditLog:
        self.entries = []
        if not self.path.exists():
            return self
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                self.entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return self

    # ── writing ───────────────────────────────────────────────

    @staticmethod
    def compute_hash(entry: dict[str, Any], previous: str) -> str:
        payload = json.dumps(entry, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(f"{previous}{payload}".encode()).hexdigest()

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
        previous = self.entries[-1]["hash"] if self.entries else GENESIS_HASH
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
        self.entries.append(entry)
        self._append(entry)
        return entry

    def _append(self, entry: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")

    # ── reading ───────────────────────────────────────────────

    def verify_chain(self) -> dict[str, Any]:
        """Check that no entry was edited or removed."""
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
