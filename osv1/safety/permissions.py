"""Permission scopes: explicit, revocable, and recorded (spec sections 12, 19).

Nothing runs without a matching grant. A grant names a scope — files,
network, programs, or irreversible actions — and the target it covers. The
user can revoke a grant at any time, and the decision path checks the grants
before every action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCOPE_FILES = "files"
SCOPE_NETWORK = "network"
SCOPE_PROGRAMS = "programs"
SCOPE_IRREVERSIBLE = "irreversible"
SCOPES = (SCOPE_FILES, SCOPE_NETWORK, SCOPE_PROGRAMS, SCOPE_IRREVERSIBLE)


@dataclass(frozen=True)
class Grant:
    """One permission the user gave."""

    scope: str
    target: str
    granted_by: str = "user"
    granted_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None
    readonly: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "target": self.target,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at,
            "expires_at": self.expires_at,
            "readonly": self.readonly,
        }


@dataclass
class PermissionStore:
    """The set of live grants, persisted as JSON so the user can read it."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/permissions.json"))
    grants: list[Grant] = field(default_factory=list)

    # ── persistence ───────────────────────────────────────────

    def load(self) -> PermissionStore:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {"grants": []}
            self.grants = [
                Grant(
                    scope=item.get("scope", ""),
                    target=item.get("target", ""),
                    granted_by=item.get("granted_by", "user"),
                    granted_at=item.get("granted_at", ""),
                    expires_at=item.get("expires_at"),
                    readonly=bool(item.get("readonly", False)),
                )
                for item in raw.get("grants", [])
                if item.get("scope") in SCOPES
            ]
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"grants": [grant.as_dict() for grant in self.grants]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    # ── grants ────────────────────────────────────────────────

    def grant(
        self, scope: str, target: str, *, by: str = "user", readonly: bool = False, ttl_s: float | None = None
    ) -> Grant:
        if scope not in SCOPES:
            raise ValueError(f"unknown scope: {scope!r}")
        expires_at = None
        if ttl_s:
            expires_at = datetime.fromtimestamp(datetime.now(UTC).timestamp() + ttl_s, tz=UTC).isoformat()
        record = Grant(scope=scope, target=target, granted_by=by, expires_at=expires_at, readonly=readonly)
        self.grants.append(record)
        self.save()
        return record

    def revoke(self, scope: str, target: str | None = None) -> int:
        before = len(self.grants)
        self.grants = [
            grant for grant in self.grants if not (grant.scope == scope and (target is None or grant.target == target))
        ]
        self.save()
        return before - len(self.grants)

    def revoke_all(self) -> int:
        count = len(self.grants)
        self.grants = []
        self.save()
        return count

    def list_grants(self) -> list[dict[str, Any]]:
        return [grant.as_dict() for grant in self.grants]

    # ── checks ────────────────────────────────────────────────

    def _active(self) -> list[Grant]:
        now = datetime.now(UTC)
        active: list[Grant] = []
        for grant in self.grants:
            if grant.expires_at:
                try:
                    expiry = datetime.fromisoformat(grant.expires_at)
                except ValueError:
                    continue
                if expiry < now:
                    continue
            active.append(grant)
        return active

    def allows(self, scope: str, target: str) -> bool:
        """True when a live grant covers this scope and target.

        A file grant covers a path inside its directory. A network grant
        covers a host. A program grant covers a program name. File paths are
        compared after resolution, so a relative target is checked against
        the same root the tool will actually use.
        """
        if scope not in SCOPES:
            return False
        for grant in self._active():
            if grant.scope != scope:
                continue
            if grant.target in ("*", ""):
                return True
            if scope == SCOPE_FILES:
                if self._file_allowed(grant.target, target):
                    return True
            elif scope == SCOPE_NETWORK:
                if target.startswith(grant.target) or grant.target in target:
                    return True
            elif target == grant.target:
                return True
        return False

    @staticmethod
    def _file_allowed(root: str, target: str) -> bool:
        """Compare two paths after resolving them."""
        from pathlib import Path

        try:
            root_path = Path(root).expanduser().resolve()
            candidate = Path(target).expanduser()
            if not candidate.is_absolute():
                candidate = Path.cwd() / candidate
            candidate = candidate.resolve()
        except (OSError, ValueError):
            return False
        return candidate == root_path or root_path in candidate.parents

    def requires_approval(self, scope: str, target: str) -> bool:
        """Irreversible work needs a grant and a human approval."""
        if scope == SCOPE_IRREVERSIBLE:
            return True
        return not self.allows(scope, target)
