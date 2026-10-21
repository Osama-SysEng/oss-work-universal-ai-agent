"""Provenance: where every model and dataset came from, and under what licence.

Spec section 20 requires that the licence and origin of every model and
dataset is recorded. Spec section 23 adds the rule that a non-permissive
licence needs a legal review before it is used.

The registry is a local JSON file. It ships with the entries the system
already depends on, and it records the local model the user brings, so the
answer to "what is running, and may I use it?" is a file, not a memory.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PERMISSIVE_LICENSES = ("apache-2.0", "apache 2.0", "mit", "bsd", "bsd-2-clause", "bsd-3-clause", "isc", "mpl-2.0")
REVIEW_NEEDED = ("gpl", "agpl", "lgpl", "cc-by-nc", "non-commercial", "community", "custom", "unknown", "proprietary")

KINDS = ("model", "dataset", "tool", "dependency", "skill")


@dataclass
class ProvenanceRecord:
    """One thing the system uses, and where it came from."""

    kind: str
    name: str
    origin: str
    license: str = "unknown"
    version: str = ""
    sha256: str = ""
    added_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    notes: str = ""
    needs_legal_review: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "name": self.name,
            "origin": self.origin,
            "license": self.license,
            "version": self.version,
            "sha256": self.sha256,
            "added_at": self.added_at,
            "notes": self.notes,
            "needs_legal_review": self.needs_legal_review,
        }


def needs_review(license_name: str) -> bool:
    """True when a licence cannot be used without a legal review first."""
    lowered = (license_name or "unknown").strip().lower()
    if lowered in PERMISSIVE_LICENSES:
        return False
    return any(marker in lowered for marker in REVIEW_NEEDED)


def file_digest(path: str | Path) -> str:
    """The SHA-256 of a file, when it can be read."""
    try:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""


# The entries the system already depends on. The licences come from the
# projects themselves; nothing here is guessed.
BUILT_IN_RECORDS: tuple[ProvenanceRecord, ...] = (
    ProvenanceRecord(
        kind="tool",
        name="REA (morluto/rea)",
        origin="https://github.com/morluto/rea",
        license="MIT",
        version="pinned in osv1/tools/rea.py",
        notes="binary and application analysis; the adapter refuses an unpinned copy",
    ),
    ProvenanceRecord(
        kind="tool",
        name="Ghidra",
        origin="https://github.com/NationalSecurityAgency/ghidra",
        license="Apache-2.0",
        notes="the default analysis engine for native binaries",
    ),
    ProvenanceRecord(
        kind="dependency",
        name="Python",
        origin="https://www.python.org/",
        license="PSF",
        notes="the runtime; the PSF licence is permissive for this use",
    ),
    ProvenanceRecord(
        kind="dependency",
        name="llama.cpp",
        origin="https://github.com/ggml-org/llama.cpp",
        license="MIT",
        notes="serves the local model over an OpenAI-compatible API",
    ),
    ProvenanceRecord(
        kind="model",
        name="local model (user provided)",
        origin="C:/tools/llama/models",
        license="unknown",
        notes="the user supplies the weights; record the exact licence before redistribution",
    ),
)


@dataclass
class ProvenanceRegistry:
    """The local record of what is used and under which licence."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/provenance.json"))
    records: list[ProvenanceRecord] = field(default_factory=list)

    # ── persistence ───────────────────────────────────────────

    def load(self) -> ProvenanceRegistry:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"records": []}
            self.records = [ProvenanceRecord(**item) for item in data.get("records", [])]
            # The review flag is derived from the licence, never trusted as
            # it was written: a record saved before a licence changed still
            # has to be reviewed.
            self.records = [
                ProvenanceRecord(
                    kind=record.kind,
                    name=record.name,
                    origin=record.origin,
                    license=record.license,
                    version=record.version,
                    sha256=record.sha256,
                    added_at=record.added_at,
                    notes=record.notes,
                    needs_legal_review=needs_review(record.license),
                )
                for record in self.records
            ]
            return self
        self.records = [
            ProvenanceRecord(
                kind=record.kind,
                name=record.name,
                origin=record.origin,
                license=record.license,
                version=record.version,
                sha256=record.sha256,
                added_at=record.added_at,
                notes=record.notes,
                needs_legal_review=needs_review(record.license),
            )
            for record in BUILT_IN_RECORDS
        ]
        self.save()
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [record.as_dict() for record in self.records]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    # ── writing ───────────────────────────────────────────────

    def add(
        self,
        kind: str,
        name: str,
        origin: str,
        *,
        license: str = "unknown",
        version: str = "",
        sha256: str = "",
        notes: str = "",
    ) -> ProvenanceRecord:
        if kind not in KINDS:
            raise ValueError(f"unknown provenance kind: {kind!r}")
        record = ProvenanceRecord(
            kind=kind,
            name=name,
            origin=origin,
            license=license,
            version=version,
            sha256=sha256,
            notes=notes,
            needs_legal_review=needs_review(license),
        )
        self.records = [item for item in self.records if item.name != name]
        self.records.append(record)
        self.save()
        return record

    def remove(self, name: str) -> bool:
        before = len(self.records)
        self.records = [record for record in self.records if record.name != name]
        self.save()
        return len(self.records) != before

    # ── reading ───────────────────────────────────────────────

    def list(self, kind: str | None = None) -> list[ProvenanceRecord]:
        if kind:
            return [record for record in self.records if record.kind == kind]
        return list(self.records)

    def get(self, name: str) -> ProvenanceRecord | None:
        for record in self.records:
            if record.name == name:
                return record
        return None

    def review_queue(self) -> list[ProvenanceRecord]:
        """The records that may not be used before a legal review."""
        return [record for record in self.records if record.needs_legal_review]

    def report(self) -> dict[str, Any]:
        """A summary a human can read before a release."""
        by_kind: dict[str, int] = {}
        for record in self.records:
            by_kind[record.kind] = by_kind.get(record.kind, 0) + 1
        return {
            "total": len(self.records),
            "by_kind": by_kind,
            "needs_legal_review": [record.name for record in self.review_queue()],
            "records": [record.as_dict() for record in self.records],
        }
