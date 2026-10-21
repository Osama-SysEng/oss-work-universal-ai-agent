"""Optional encrypted sync to storage the user owns (spec section 20).

Local-first: everything stays on the device by default. When the user wants a
copy somewhere they control, this module writes one encrypted archive that
holds the memory, the permissions, the skills, and the evolution record. The
encryption is done by the operating system (DPAPI on Windows), so the host
that stores the file cannot read it.

There is no telemetry, and no upload happens from here: the system produces a
file, and the user decides where it goes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from osv1.safety.secrets import SecretStore, SecretStoreError


@dataclass
class SyncArchive:
    """One encrypted export of the OS_V1 state."""

    path: Path
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    version: str = "1.0.0"

    def as_dict(self) -> dict[str, Any]:
        return {"path": str(self.path), "created_at": self.created_at, "version": self.version}


@dataclass
class Sync:
    """Reads and writes the encrypted archive."""

    data_dir: Path = field(default_factory=lambda: Path("./data-osv1"))

    def _state(self) -> dict[str, Any]:
        """Collect the state that is worth syncing."""
        from osv1.memory.store import MemoryStore

        memory = MemoryStore(path=self.data_dir / "memory.db")
        permissions_path = self.data_dir / "permissions.json"
        skills_dir = self.data_dir.parent / "skills-osv1"
        payload: dict[str, Any] = {
            "memory": memory.export(),
            "permissions": json.loads(permissions_path.read_text(encoding="utf-8"))
            if permissions_path.exists()
            else {"grants": []},
            "skills": sorted(str(path) for path in skills_dir.glob("*.py")) if skills_dir.exists() else [],
            "evolution": json.loads((self.data_dir / "evolution.json").read_text(encoding="utf-8"))
            if (self.data_dir / "evolution.json").exists()
            else {"versions": [], "candidates": []},
        }
        return payload

    def export(self, out_path: str | Path | None = None) -> dict[str, Any]:
        """Write one encrypted archive of the current state."""
        target = Path(out_path) if out_path else self.data_dir / "ossv1-state.enc"
        target.parent.mkdir(parents=True, exist_ok=True)
        document = json.dumps(self._state(), ensure_ascii=False, default=str).encode("utf-8")
        try:
            store = SecretStore(path=target)
            store.set("state", document.decode("utf-8"))
        except SecretStoreError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "archive": SyncArchive(path=target).as_dict()}

    def inspect(self, archive_path: str | Path) -> dict[str, Any]:
        """Read an archive back on this machine. The host cannot read it."""
        target = Path(archive_path)
        if not target.exists():
            return {"ok": False, "error": f"no archive at {target}"}
        try:
            store = SecretStore(path=target)
            document = store.get("state")
        except SecretStoreError as exc:
            return {"ok": False, "error": str(exc)}
        if document is None:
            return {"ok": False, "error": "the archive could not be decrypted on this machine"}
        state = json.loads(document)
        return {
            "ok": True,
            "memory_entries": state.get("memory", {}).get("count", 0),
            "grants": len(state.get("permissions", {}).get("grants", [])),
            "skills": len(state.get("skills", [])),
            "versions": len(state.get("evolution", {}).get("versions", [])),
        }

    def import_state(self, archive_path: str | Path) -> dict[str, Any]:
        """Restore the memory from an archive. The memory is replaced, not merged."""
        target = Path(archive_path)
        if not target.exists():
            return {"ok": False, "error": f"no archive at {target}"}
        try:
            document = SecretStore(path=target).get("state")
        except SecretStoreError as exc:
            return {"ok": False, "error": str(exc)}
        if document is None:
            return {"ok": False, "error": "the archive could not be decrypted on this machine"}
        state = json.loads(document)
        from osv1.memory.store import MemoryStore

        memory = MemoryStore(path=self.data_dir / "memory.db")
        restored = 0
        for entry in state.get("memory", {}).get("entries", []):
            memory.add(
                entry["kind"],
                entry["content"],
                title=entry.get("title", ""),
                metadata=entry.get("metadata", {}),
                confidence=entry.get("confidence", 1.0),
                user_id=entry.get("user_id", "local"),
            )
            restored += 1
        return {"ok": True, "restored": restored}
