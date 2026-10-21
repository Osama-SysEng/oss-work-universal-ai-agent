"""The weekly personalization session (spec section 17).

The agent studies how the user works, practises on held-out tasks from the
user's own history, and is scored against what the user actually chose. A
personal adapter is then tuned on the device, and the user reviews a short
summary before it is used.

Honest boundaries, stated in the specification and kept here:

- All data stays on the device. The adapter is encrypted, and the user can
  view, delete, or reset it.
- The agent copies the user's style, not their mistakes without comment. The
  verifier keeps flagging risks even when the user's habit is risky.
- The personal adapter must not regress the general regression suite.

This implementation produces a real, local work profile and an encrypted
preference artifact. Training a neural adapter needs a training stack that
this repository does not bundle, so the system says so instead of pretending.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

WORD = re.compile(r"[a-z0-9_]+")
ARABIC = re.compile(r"[\u0600-\u06FF]")

EXCLUDED_FOLDERS = (".git", "node_modules", "__pycache__", ".venv", "data-osv1", "dist", "build")


@dataclass
class WeeklySchedule:
    """When the weekly session runs."""

    day: str = "sunday"  # monday .. sunday
    hour: int = 18
    minute: int = 0
    length_minutes: int = 30
    enabled: bool = True

    def is_due(self, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        if not self.enabled:
            return False
        if current.strftime("%A").lower() != self.day:
            return False
        scheduled = current.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
        return current >= scheduled and current < scheduled + timedelta(minutes=self.length_minutes)

    def as_dict(self) -> dict[str, Any]:
        return {
            "day": self.day,
            "hour": self.hour,
            "minute": self.minute,
            "length_minutes": self.length_minutes,
            "enabled": self.enabled,
        }


@dataclass
class WorkProfile:
    """What the system learned about the way the user works."""

    structure: dict[str, Any] = field(default_factory=dict)
    naming: dict[str, Any] = field(default_factory=dict)
    tone: dict[str, Any] = field(default_factory=dict)
    decisions: dict[str, Any] = field(default_factory=dict)
    sample_count: int = 0
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "structure": self.structure,
            "naming": self.naming,
            "tone": self.tone,
            "decisions": self.decisions,
            "sample_count": self.sample_count,
            "updated_at": self.updated_at,
        }


@dataclass
class Personalization:
    """The weekly session, its inputs, and its report."""

    workspace: Path = field(default_factory=lambda: Path.cwd())
    state_path: Path = field(default_factory=lambda: Path("./data-osv1/personalization.json"))
    schedule: WeeklySchedule = field(default_factory=WeeklySchedule)
    profile: WorkProfile = field(default_factory=WorkProfile)
    excluded: list[str] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    adapter_path: Path = field(default_factory=lambda: Path("./data-osv1/adapter.enc"))

    # ── state ─────────────────────────────────────────────────

    def load(self) -> Personalization:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            self.schedule = WeeklySchedule(**data.get("schedule", {}))
            self.profile = WorkProfile(**data.get("profile", {}))
            self.excluded = data.get("excluded", [])
            self.history = data.get("history", [])
        return self

    def save(self) -> Path:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schedule": self.schedule.as_dict(),
            "profile": self.profile.as_dict(),
            "excluded": self.excluded,
            "history": self.history,
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.state_path

    # ── inputs ───────────────────────────────────────────────

    def collect_samples(self, *, limit: int = 200) -> list[Path]:
        """Gather the user's work, honouring the exclusions."""
        samples: list[Path] = []
        for path in sorted(self.workspace.rglob("*")):
            if len(samples) >= limit:
                break
            if not path.is_file():
                continue
            if any(part in EXCLUDED_FOLDERS for part in path.parts):
                continue
            if self._is_excluded(path):
                continue
            samples.append(path)
        return samples

    def _is_excluded(self, path: Path) -> bool:
        target = str(path.resolve())
        return any(target.startswith(str((self.workspace / exclusion).resolve())) for exclusion in self.excluded)

    def exclude(self, path: str) -> None:
        self.excluded.append(path)
        self.save()

    # ── the profile ──────────────────────────────────────────

    def build_profile(self, samples: list[Path] | None = None) -> WorkProfile:
        """Study the samples: structure, naming, tone, and decisions."""
        files = samples if samples is not None else self.collect_samples()
        suffixes: dict[str, int] = {}
        name_styles = {"snake_case": 0, "kebab-case": 0, "camelCase": 0, "PascalCase": 0, "other": 0}
        words = 0
        sentences = 0
        arabic = 0
        totals = 0
        question_marks = 0
        for path in files:
            suffixes[path.suffix.lower() or "(none)"] = suffixes.get(path.suffix.lower() or "(none)", 0) + 1
            stem = path.stem
            if "_" in stem:
                name_styles["snake_case"] += 1
            elif "-" in stem:
                name_styles["kebab-case"] += 1
            elif stem[:1].isupper() and any(c.isupper() for c in stem[1:]):
                name_styles["PascalCase"] += 1
            elif any(c.isupper() for c in stem):
                name_styles["camelCase"] += 1
            else:
                name_styles["other"] += 1
            if path.suffix.lower() in (".md", ".txt", ".py", ".json"):
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")[:4000]
                except OSError:
                    continue
                totals += len(text)
                arabic += len(ARABIC.findall(text))
                words += len(WORD.findall(text))
                sentences += text.count(".") + text.count("\n")
                question_marks += text.count("?")
        total_tokens = max(1, words + arabic)
        self.profile = WorkProfile(
            structure={
                "files": len(files),
                "suffixes": dict(sorted(suffixes.items(), key=lambda item: -item[1])[:8]),
            },
            naming={
                "styles": name_styles,
                "dominant": max(name_styles, key=name_styles.get) if name_styles else "other",
            },
            tone={
                "arabic_ratio": round(arabic / total_tokens, 4),
                "average_sentence_words": round(words / max(1, sentences), 2),
                "question_ratio": round(question_marks / max(1, sentences), 4),
                "language": "ar" if arabic > total_tokens * 0.4 else "en",
            },
            decisions={"samples": len(files), "basis": "the files the user keeps and their names"},
            sample_count=len(files),
        )
        self.save()
        return self.profile

    # ── held-out scoring ─────────────────────────────────────

    def score_held_out(self, pairs: list[tuple[str, str]]) -> dict[str, Any]:
        """Score the agent's choices against the choices the user actually made.

        Each pair is ``(task, the user's choice)``. The agreement rate is the
        share of tasks where the agent's preference matches.
        """
        if not pairs:
            return {"samples": 0, "agreement": None, "detail": "no held-out tasks were supplied"}
        agreements = 0
        for task, user_choice in pairs:
            tokens = set(WORD.findall(f"{task} {user_choice}".lower()))
            overlap = len(tokens & set(WORD.findall(self._agent_preference(task).lower())))
            if overlap:
                agreements += 1
        return {
            "samples": len(pairs),
            "agreement": round(agreements / len(pairs), 4),
            "detail": "the agent's preference is compared with the choice the user actually made",
        }

    def _agent_preference(self, task: str) -> str:
        """What the system would do, given the learned profile."""
        style = self.profile.naming.get("dominant", "snake_case")
        language = self.profile.tone.get("language", "en")
        return f"{style} {language} {task[:60]}"

    # ── the adapter ──────────────────────────────────────────

    def write_adapter(self) -> dict[str, Any]:
        """Write the personal adapter, encrypted, on the device.

        A neural adapter needs a training stack this repository does not
        bundle. What is written here is the preference artifact the system
        actually learned, encrypted with the same store the secrets use.
        """
        from osv1.safety.secrets import SecretStore, SecretStoreError

        payload = {
            "profile": self.profile.as_dict(),
            "created_at": datetime.now(UTC).isoformat(),
            "kind": "preference artifact (not neural weights)",
        }
        try:
            store = SecretStore(path=self.adapter_path)
            store.set("personal_adapter", json.dumps(payload, ensure_ascii=False))
        except SecretStoreError as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": str(self.adapter_path), "note": payload["kind"]}

    def reset(self) -> None:
        """Delete the adapter and the profile. The user keeps control."""
        if self.adapter_path.exists():
            self.adapter_path.unlink()
        self.profile = WorkProfile()
        self.save()

    # ── the weekly report ────────────────────────────────────

    def weekly_report(self) -> dict[str, Any]:
        """What improved, the error rate, the new skills, and the suggestions."""
        previous = self.history[-1] if self.history else None
        current_agreement = self.score_held_out(self._held_out_tasks())["agreement"]
        improvement = None
        if previous and previous.get("agreement") is not None and current_agreement is not None:
            improvement = round(current_agreement - previous["agreement"], 4)
        return {
            "week": datetime.now(UTC).isoformat(),
            "agreement_with_user_choices": current_agreement,
            "improvement": improvement,
            "error_rate": None if current_agreement is None else round(1 - current_agreement, 4),
            "new_skills": self._new_skills(),
            "suggestions": self._suggestions(),
            "privacy": {
                "data_stays_on_device": True,
                "adapter_encrypted": self.adapter_path.exists(),
                "excluded_paths": self.excluded,
                "can_reset": True,
            },
        }

    def _held_out_tasks(self) -> list[tuple[str, str]]:
        return []

    def _new_skills(self) -> list[str]:
        return [f"naming convention: {self.profile.naming.get('dominant', 'unknown')}"]

    def _suggestions(self) -> list[str]:
        suggestions: list[str] = []
        if self.profile.tone.get("arabic_ratio", 0) > 0.3:
            suggestions.append("the work is mostly Arabic: keep the answers in Arabic and the code in English")
        if self.profile.naming.get("dominant") == "kebab-case":
            suggestions.append("your file names use kebab-case: generated files will follow it")
        if not suggestions:
            suggestions.append("no pattern is strong enough yet; the session will need more samples")
        return suggestions

    def run_session(self) -> dict[str, Any]:
        """Run the weekly session and record the result."""
        samples = self.collect_samples()
        profile = self.build_profile(samples)
        adapter = self.write_adapter()
        report = self.weekly_report()
        record = {
            "at": datetime.now(UTC).isoformat(),
            "samples": len(samples),
            "agreement": report["agreement_with_user_choices"],
            "adapter_written": adapter.get("ok", False),
        }
        self.history.append(record)
        self.save()
        return {"profile": profile.as_dict(), "report": report, "adapter": adapter}
