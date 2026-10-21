"""Human approval for irreversible actions (spec sections 12 and 19).

Deleting, sending, paying, publishing, and changing system settings are not
allowed to happen because a model felt confident. They need an explicit
approval from the user, tied to one specific request, and the approval stops
being valid once it is used or once it expires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from osv1.tools.registry import IRREVERSIBLE_ACTIONS


@dataclass
class ApprovalRequest:
    """A request the user can approve or reject."""

    id: str
    action: str
    target: str
    reason: str
    request_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str = ""
    status: str = "pending"  # pending | approved | rejected | expired
    decided_by: str = ""
    decided_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "request_id": self.request_id,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }


@dataclass
class ApprovalStore:
    """Pending and decided approvals."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/approvals.json"))
    requests: list[ApprovalRequest] = field(default_factory=list)
    ttl_minutes: int = 30

    def load(self) -> ApprovalStore:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = {"requests": []}
            self.requests = [ApprovalRequest(**item) for item in raw.get("requests", [])]
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"requests": [request.as_dict() for request in self.requests]}
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    def create(self, action: str, target: str, *, reason: str, request_id: str = "") -> ApprovalRequest:
        if action not in IRREVERSIBLE_ACTIONS:
            raise ValueError(f"{action!r} is not an irreversible action")
        expires = datetime.now(UTC) + timedelta(minutes=self.ttl_minutes)
        record = ApprovalRequest(
            id=f"appr-{len(self.requests) + 1:04d}",
            action=action,
            target=target,
            reason=reason,
            request_id=request_id,
            expires_at=expires.isoformat(),
        )
        self.requests.append(record)
        self.save()
        return record

    def decide(self, approval_id: str, *, approve: bool, by: str = "user") -> ApprovalRequest | None:
        for request in self.requests:
            if request.id != approval_id:
                continue
            if request.status != "pending":
                return request
            if self._expired(request):
                request.status = "expired"
                self.save()
                return request
            request.status = "approved" if approve else "rejected"
            request.decided_by = by
            request.decided_at = datetime.now(UTC).isoformat()
            self.save()
            return request
        return None

    def consume(self, action: str, target: str, *, request_id: str = "") -> ApprovalRequest | None:
        """Find and use up an approval that matches this action."""
        for request in self.requests:
            if request.status != "approved":
                continue
            if request.action != action or request.target != target:
                continue
            if request.request_id and request_id and request.request_id != request_id:
                continue
            if self._expired(request):
                request.status = "expired"
                self.save()
                continue
            request.status = "used"
            self.save()
            return request
        return None

    def pending(self) -> list[ApprovalRequest]:
        return [request for request in self.requests if request.status == "pending" and not self._expired(request)]

    def _expired(self, request: ApprovalRequest) -> bool:
        if not request.expires_at:
            return False
        try:
            return datetime.fromisoformat(request.expires_at) < datetime.now(UTC)
        except ValueError:
            return False
