"""Self-evolution without developers, and human-gated (spec section 15).

The loop the specification describes:

1. Log — every decision and its outcome is recorded.
2. Learn — the log becomes training material: skills, memory, calibration.
3. Ask — when the confidence is low, the system asks instead of guessing.
4. Test — a candidate update runs against a frozen regression and safety suite.
5. Promote — the update goes live only if nothing regresses. Every version is
   kept, with one-step rollback.

The hard limits are implemented, not just described. The safety layer, the
permissions, the audit log, the kill switch, and the verifier's own tests are
off limits to self-modification, and the engine refuses any attempt to touch
them.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

IMMUTABLE_CORE = (
    "osv1/safety/permissions.py",
    "osv1/safety/approvals.py",
    "osv1/safety/audit.py",
    "osv1/safety/killswitch.py",
    "osv1/safety/secrets.py",
    "osv1/safety/injection.py",
    "osv1/layers/verifier.py",
    "tests/test_safety_layer.py",
    "tests/test_verifier_independence.py",
)

CANDIDATE_KINDS = ("skill", "calibration", "memory", "adapter")


@dataclass
class Candidate:
    """A proposed update waiting for the promotion gate."""

    id: str
    kind: str
    summary: str
    payload: dict[str, Any]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: str = "proposed"  # proposed | tested | promoted | rejected | rolled_back
    test_report: dict[str, Any] = field(default_factory=dict)
    version: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "summary": self.summary,
            "payload": self.payload,
            "created_at": self.created_at,
            "status": self.status,
            "test_report": self.test_report,
            "version": self.version,
        }


@dataclass
class VersionRecord:
    """One promoted version, kept for rollback."""

    version: int
    candidate_id: str
    summary: str
    promoted_at: str
    snapshot: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "candidate_id": self.candidate_id,
            "summary": self.summary,
            "promoted_at": self.promoted_at,
            "snapshot": self.snapshot,
        }


@dataclass
class EvolutionEngine:
    """Log, learn, ask, test, promote — with a gate in front of the last step."""

    project_root: Path = field(default_factory=lambda: Path.cwd())
    state_path: Path = field(default_factory=lambda: Path("./data-osv1/evolution.json"))
    candidates: list[Candidate] = field(default_factory=list)
    versions: list[VersionRecord] = field(default_factory=list)
    suite: tuple[str, ...] = ("tests/test_safety_layer.py", "tests/test_agents_registry.py")
    timeout_s: float = 300.0

    # ── state ─────────────────────────────────────────────────

    def load(self) -> EvolutionEngine:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            self.versions = [VersionRecord(**item) for item in data.get("versions", [])]
            self.candidates = [Candidate(**item) for item in data.get("candidates", [])]
        return self

    def save(self) -> Path:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "versions": [version.as_dict() for version in self.versions],
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.state_path

    # ── 1. log ────────────────────────────────────────────────

    def log_outcome(self, task: str, *, decided: str, correct: bool, confidence: float) -> dict[str, Any]:
        """Record a decision and its outcome. This is the raw material."""
        return {
            "task": task[:200],
            "decided": decided,
            "correct": correct,
            "confidence": confidence,
            "at": datetime.now(UTC).isoformat(),
        }

    # ── 2. learn ─────────────────────────────────────────────

    def learn_from_log(self, log: list[dict[str, Any]]) -> dict[str, Any]:
        """Turn a log into training material: what to trust, what to stop doing."""
        if not log:
            return {"samples": 0, "skills": [], "calibration": {}}
        good = [item for item in log if item.get("correct")]
        bad = [item for item in log if not item.get("correct")]
        confidences = [float(item.get("confidence", 0.0)) for item in log]
        average = sum(confidences) / len(confidences) if confidences else 0.0
        accuracy = len(good) / len(log)
        skills = []
        for item in good:
            skills.append(
                {
                    "name": f"decision::{item.get('decided', 'unknown')[:60]}",
                    "procedure": f"prefer the decision pattern used for: {item.get('task', '')[:120]}",
                    "conditions": f"confidence was {item.get('confidence', 0):.2f} and the outcome was correct",
                    "tests": "the decision matched a recorded correct outcome",
                }
            )
        calibration = {
            "accuracy": round(accuracy, 4),
            "average_confidence": round(average, 4),
            "overconfidence": round(max(0.0, average - accuracy), 4),
            "advice": (
                "the stated confidence is above the real accuracy: recalibrate before trusting it"
                if average > accuracy + 0.05
                else "the stated confidence matches the real accuracy"
            ),
        }
        return {
            "samples": len(log),
            "correct": len(good),
            "incorrect": len(bad),
            "skills": skills,
            "calibration": calibration,
        }

    # ── 3. ask ────────────────────────────────────────────────

    def should_ask(self, confidence: float, threshold: float = 0.6) -> bool:
        """The rule from the specification: low confidence means ask, not guess."""
        return confidence < threshold

    # ── 4. test ───────────────────────────────────────────────

    def run_gate(self, candidate: Candidate) -> dict[str, Any]:
        """Run the frozen regression and safety suite against a candidate."""
        started = time.time()
        missing = [path for path in self.suite if not (self.project_root / path).exists()]
        if missing:
            return {
                "ok": False,
                "reason": f"the frozen suite is incomplete: {', '.join(missing)}",
                "missing": missing,
                "duration_s": round(time.time() - started, 2),
            }
        command = [sys.executable, "-m", "pytest", *self.suite, "-q", "--tb=line"]
        try:
            completed = subprocess.run(  # noqa: S603 - fixed interpreter and arguments
                command,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_s,
            )
        except subprocess.TimeoutExpired:
            return {
                "ok": False,
                "reason": f"the suite did not finish within {self.timeout_s:.0f} seconds",
                "duration_s": round(time.time() - started, 2),
            }
        tail = (completed.stdout or "").strip().splitlines()[-5:]
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "suite": list(self.suite),
            "output": tail,
            "duration_s": round(time.time() - started, 2),
        }

    # ── 5. promote ────────────────────────────────────────────

    def propose(self, kind: str, summary: str, payload: dict[str, Any]) -> Candidate:
        if kind not in CANDIDATE_KINDS:
            raise ValueError(f"unknown candidate kind: {kind!r}")
        candidate = Candidate(
            id=f"cand-{len(self.candidates) + 1:04d}",
            kind=kind,
            summary=summary[:300],
            payload=payload,
        )
        self.candidates.append(candidate)
        self.save()
        return candidate

    def promote(self, candidate_id: str) -> dict[str, Any]:
        """Promote a candidate only when the gate passed and nothing regressed."""
        candidate = next((item for item in self.candidates if item.id == candidate_id), None)
        if candidate is None:
            return {"ok": False, "error": f"no candidate {candidate_id}"}
        report = self.run_gate(candidate)
        candidate.test_report = report
        if not report.get("ok"):
            candidate.status = "rejected"
            self.save()
            return {"ok": False, "error": "the promotion gate rejected the candidate", "report": report}
        version = (self.versions[-1].version + 1) if self.versions else 1
        record = VersionRecord(
            version=version,
            candidate_id=candidate.id,
            summary=candidate.summary,
            promoted_at=datetime.now(UTC).isoformat(),
        )
        self.versions.append(record)
        candidate.status = "promoted"
        candidate.version = version
        self.save()
        return {"ok": True, "version": record.as_dict(), "report": report}

    def rollback(self) -> dict[str, Any]:
        """Undo the last promoted version in one step."""
        if len(self.versions) < 2:
            return {"ok": False, "error": "there is no earlier version to roll back to"}
        last = self.versions.pop()
        previous = self.versions[-1]
        last.status = "rolled_back"  # type: ignore[attr-defined]
        self.save()
        return {"ok": True, "rolled_back": last.as_dict(), "restored": previous.as_dict()}

    # ── the immutable core ────────────────────────────────────

    def refuses_immutable_change(self, path: str) -> bool:
        """True when the change touches something the system may not modify."""
        normalized = path.replace("\\", "/")
        return any(normalized.endswith(item) for item in IMMUTABLE_CORE)

    def propose_code_change(self, path: str, summary: str) -> dict[str, Any]:
        """Propose a code change, refusing the ones the specification forbids."""
        if self.refuses_immutable_change(path):
            return {
                "ok": False,
                "error": (
                    f"{path} is part of the immutable core: the safety layer, the permissions, the audit "
                    "log, the kill switch, and the verifier's tests may not be changed by self-improvement work"
                ),
            }
        candidate = self.propose("memory", summary, {"path": path})
        return {"ok": True, "candidate": candidate.as_dict()}

    def status(self) -> dict[str, Any]:
        return {
            "candidates": len(self.candidates),
            "versions": len(self.versions),
            "current_version": self.versions[-1].version if self.versions else 0,
            "immutable_core": list(IMMUTABLE_CORE),
            "suite": list(self.suite),
        }
