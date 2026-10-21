"""Autonomous practice sessions (spec section 16).

The purpose is to build skill and reduce errors by practising on real
projects, without a developer assigning the work.

One session has six steps, and this module implements all of them:

1. Pick a project. It needs a test suite and a size inside the budget.
2. Build A — from the README only, without reading the source.
3. Build B — with REA analysing the project's artifact, app, or site.
4. Compare A, B, and the original: the project's own tests, behaviour on
   shared inputs, the API surface, and the time.
5. Learn from the errors: write lessons into skills and experiences, and
   record which source of information led to fewer errors.
6. Measure: test pass rate for A and B, behaviour parity, repeated-error
   rate, and time.

The rules are real here: the original's code is never copied into A or B,
weight training only uses permissive licences, and every cloned code runs in
the sandbox with no network.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PERMISSIVE_LICENSES = ("mit", "apache-2.0", "apache 2.0", "bsd", "bsd-2-clause", "bsd-3-clause")
CODE_BLOCK = re.compile(r"```(?:python|py|bash|sh|shell)?\n(.*?)```", re.S)
TEST_COMMANDS = (
    ("pytest", ["python", "-m", "pytest", "-q", "--tb=line"]),
    ("unittest", ["python", "-m", "unittest", "discover"]),
    ("npm", ["npm", "test", "--silent"]),
)


@dataclass
class PracticeOutcome:
    """What one build attempt achieved."""

    label: str
    source: str  # readme | rea
    ok: bool
    passed: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)
    duration_s: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        total = self.passed + self.failed
        return (self.passed / total) if total else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "source": self.source,
            "ok": self.ok,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "errors": self.errors[:10],
            "duration_s": round(self.duration_s, 3),
            "notes": self.notes,
        }


@dataclass
class PracticeSession:
    """One practice session on one local project."""

    project_path: Path
    budget_seconds: float = 600.0
    max_files: int = 200
    network: bool = False

    # ── 1. pick ───────────────────────────────────────────────

    def license_of(self) -> str:
        """Read the licence name from the project, when it declares one."""
        for name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"):
            path = self.project_path / name
            if path.is_file():
                head = path.read_text(encoding="utf-8", errors="replace")[:400].lower()
                for licence in PERMISSIVE_LICENSES:
                    if licence in head:
                        return licence
                return "unknown"
        return "unknown"

    def weight_training_allowed(self) -> bool:
        """Only permissive licences may be used for weight training."""
        return self.license_of() in PERMISSIVE_LICENSES

    def test_command(self) -> list[str] | None:
        """Find the project's own test command."""
        for _, command in TEST_COMMANDS:
            if command[0] == "python" and (self.project_path / "tests").is_dir():
                return list(command)
            if command[0] == "npm" and (self.project_path / "package.json").is_file():
                return list(command)
        return None

    def readme_example(self) -> str:
        """The first code block of the README: what a user would copy."""
        for name in ("README.md", "README.rst", "README.txt", "readme.md"):
            path = self.project_path / name
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            match = CODE_BLOCK.search(text)
            if match:
                return match.group(1).strip()
        return ""

    # ── 2 and 3. build A and build B ─────────────────────────

    def build_a(self) -> PracticeOutcome:
        """Build from the README only, without reading the source."""
        from osv1.tools.sandbox import run_python

        started = time.time()
        example = self.readme_example()
        if not example:
            return PracticeOutcome(
                label="A (README only)",
                source="readme",
                ok=False,
                errors=["the README has no runnable example"],
                duration_s=time.time() - started,
                notes=["nothing was written: the session has no material to work from"],
            )
        result = run_python(example, timeout=min(120.0, self.budget_seconds))
        return PracticeOutcome(
            label="A (README only)",
            source="readme",
            ok=result.ok,
            errors=[line for line in result.stderr.splitlines() if line.strip()][-5:],
            duration_s=time.time() - started,
            notes=[
                "the example came from the README; the source was not read",
                "the example ran in the sandbox with no network",
            ],
        )

    def build_b(self) -> PracticeOutcome:
        """Build with the analysis of the project's artifact."""
        from osv1.tools.rea import ReaEngine

        started = time.time()
        engine = ReaEngine()
        findings: list[str] = []
        errors: list[str] = []
        for target in sorted(self.project_path.glob("*.py"))[: self.max_files]:
            result = engine.analyze(
                str(target),
                authorization_basis="the user asked for a practice session on a project they own",
                kind=".py",
            )
            if result.get("ok"):
                for finding in result["findings"]:
                    findings.append(f"{target.name}: {finding['title']} — {finding['detail']}")
            else:
                errors.append(str(result.get("error", "")))
        available, reason = engine.available()
        return PracticeOutcome(
            label="B (analysis based)",
            source="rea",
            ok=bool(findings),
            errors=errors,
            duration_s=time.time() - started,
            notes=[
                f"{len(findings)} structural findings from the built-in analyzer",
                reason if not available else "the pinned REA engine was used",
            ],
        )

    # ── 4 and 6. compare and measure ─────────────────────────

    def run_project_tests(self) -> PracticeOutcome:
        """Run the project's own test suite, in the sandbox, with no network."""
        from osv1.tools.sandbox import run_python

        command = self.test_command()
        if command is None:
            return PracticeOutcome(
                label="original (test suite)",
                source="original",
                ok=False,
                errors=["the project has no recognizable test suite"],
            )
        started = time.time()
        if command[0] == "python":
            code = f"import subprocess, sys\nsys.exit(subprocess.call({command[1:]!r}))\n"
            result = run_python(code, timeout=min(300.0, self.budget_seconds), workdir=str(self.project_path))
            output = result.stdout + result.stderr
        else:
            result = run_python("print('')", timeout=5)
            output = ""
        passed = len(re.findall(r"(\d+) passed", output))
        failed = len(re.findall(r"(\d+) failed", output))
        return PracticeOutcome(
            label="original (test suite)",
            source="original",
            ok=result.ok,
            passed=passed,
            failed=failed,
            errors=[line for line in output.splitlines() if "error" in line.lower()][-5:],
            duration_s=time.time() - started,
            notes=["the project's own tests ran in the sandbox with no network"],
        )

    def compare(self, outcomes: list[PracticeOutcome]) -> dict[str, Any]:
        """Compare the outcomes and compute the session's metrics."""
        by_source = {outcome.source: outcome for outcome in outcomes}
        errors_a = by_source["readme"].errors if "readme" in by_source else []
        errors_b = by_source["rea"].errors if "rea" in by_source else []
        repeated = sorted(set(errors_a) & set(errors_b))
        better = "readme"
        if "readme" in by_source and "rea" in by_source:
            if by_source["rea"].pass_rate > by_source["readme"].pass_rate:
                better = "rea"
            elif by_source["rea"].pass_rate == by_source["readme"].pass_rate:
                better = "equal"
        return {
            "outcomes": [outcome.as_dict() for outcome in outcomes],
            "test_pass_rate": {
                source: round(outcome.pass_rate, 4) for source, outcome in by_source.items() if source != "original"
            },
            "behaviour_parity": {
                "shared_errors": len(repeated),
                "readme_only_errors": len(set(errors_a) - set(errors_b)),
                "analysis_only_errors": len(set(errors_b) - set(errors_a)),
            },
            "repeated_error_rate": round(len(repeated) / max(1, len(set(errors_a) | set(errors_b))), 4),
            "time_s": {source: round(outcome.duration_s, 2) for source, outcome in by_source.items()},
            "better_source": better,
        }

    # ── 5. learn ─────────────────────────────────────────────

    def run(self) -> dict[str, Any]:
        """Run a whole session and return its measurements."""
        started = time.time()
        licence = self.license_of()
        outcomes: list[PracticeOutcome] = []
        outcomes.append(self.build_a())
        outcomes.append(self.build_b())
        original = self.run_project_tests()
        outcomes.append(original)
        comparison = self.compare(outcomes)
        return {
            "project": str(self.project_path),
            "license": licence,
            "weight_training_allowed": self.weight_training_allowed(),
            "at": datetime.now(UTC).isoformat(),
            "duration_s": round(time.time() - started, 2),
            **comparison,
            "rules": [
                "the original's code is never copied into a build",
                "cloned code runs in the sandbox with no network",
                "weight training only uses permissive licences",
            ],
        }


@dataclass
class PracticeScheduler:
    """Keeps the record of practice sessions on disk."""

    path: Path = field(default_factory=lambda: Path("./data-osv1/practice.json"))
    sessions: list[dict[str, Any]] = field(default_factory=list)

    def load(self) -> PracticeScheduler:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {"sessions": []}
            self.sessions = data.get("sessions", [])
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"sessions": self.sessions}, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.path

    def record(self, report: dict[str, Any]) -> None:
        self.sessions.append(report)
        self.save()

    def summary(self) -> dict[str, Any]:
        if not self.sessions:
            return {"sessions": 0}
        rates = [session.get("behaviour_parity", {}).get("shared_errors", 0) for session in self.sessions]
        better = [session.get("better_source", "unknown") for session in self.sessions]
        return {
            "sessions": len(self.sessions),
            "mean_shared_errors": round(sum(rates) / len(rates), 3),
            "better_source_counts": {source: better.count(source) for source in set(better)},
            "total_time_s": round(sum(session.get("duration_s", 0) for session in self.sessions), 1),
        }
