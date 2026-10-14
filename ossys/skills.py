"""Self-built skills: the user answers binary (yes/no) questions and the OS
generates a real skill file (markdown + optional python scaffold).

No downloads, no external store. A skill that cannot be answered with
yes/no questions is refused honestly instead of guessed.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from ossys import config, store

# (key, question) — every answer must be yes/no.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("repeats", "Will you reuse this more than three times?"),
    ("local_only", "Must it work fully offline on this machine?"),
    ("files", "Does it read or write local files?"),
    ("web", "Does it need web pages (read-only)?"),
    ("schedule", "Should it run in the background on a schedule?"),
    ("office", "Does it produce documents, sheets, or slides?"),
    ("code", "Does it generate or review code?"),
    ("memory", "Should it remember things between runs?"),
)


@dataclass
class SkillDoc:
    name: str
    summary: str
    path: str
    answers: dict[str, bool]


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    if not slug:
        raise ValueError("Skill needs a name (letters/numbers).")
    return slug


def normalize_answer(raw: str) -> bool:
    text = raw.strip().lower()
    if text in ("y", "yes", "1", "true", "نعم"):
        return True
    if text in ("n", "no", "0", "false", "لا"):
        return False
    raise ValueError(f"Answer must be yes/no, got: {raw!r}")


def build_skill(name: str, purpose: str, answers: dict[str, str | bool]) -> SkillDoc:
    """Validate binary answers and write the skill. Raises ValueError otherwise."""
    slug = _slug(name)
    if not purpose.strip():
        raise ValueError("Skill needs a one-line purpose.")
    parsed: dict[str, bool] = {}
    for key, _question in QUESTIONS:
        if key not in answers:
            raise ValueError(f"Missing answer for: {key}")
        value = answers[key]
        parsed[key] = value if isinstance(value, bool) else normalize_answer(value)

    caps: list[str] = []
    if parsed["files"]:
        caps.append("local files (read/write inside workspace)")
    if parsed["web"]:
        caps.append("web reader (read-only, no JS)")
    if parsed["schedule"]:
        caps.append("background scheduler")
    if parsed["office"]:
        caps.append("office suite (documents/sheets/slides)")
    if parsed["code"]:
        caps.append("code assistance (no untrusted execution)")
    if parsed["memory"]:
        caps.append("local memory")
    if not caps:
        caps.append("orchestrator only")

    skills_dir = config.skills_dir()
    os.makedirs(skills_dir, exist_ok=True)
    path = os.path.join(skills_dir, f"{slug}.md")
    lines = [
        f"# skill: {slug}",
        "",
        f"Purpose: {purpose.strip()}",
        "",
        "Built from binary user answers (self-built, offline):",
        "",
    ]
    for key, question in QUESTIONS:
        lines.append(f"- {question} -> {'yes' if parsed[key] else 'no'}")
    lines += [
        "",
        "Allowed capabilities:",
        "",
    ]
    lines += [f"- {cap}" for cap in caps]
    lines += [
        "",
        "Rules:",
        "- Local only. No API keys, no cloud calls.",
        "- File writes stay inside the OS workspace unless the user approves otherwise.",
        "- Report which capability produced each result.",
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    summary = f"{purpose.strip()} [{', '.join(caps)}]"
    store.save_skill(slug, summary, path)
    return SkillDoc(name=slug, summary=summary, path=path, answers=parsed)


def ask_interactive(name: str, purpose: str) -> SkillDoc:
    """Binary-question wizard over stdin. For the CLI, not for tests."""
    print(f"Building skill: {name} — answer yes/no.")
    answers: dict[str, str] = {}
    for key, question in QUESTIONS:
        while True:
            try:
                raw = input(f"{question} (yes/no): ")
                normalize_answer(raw)
                answers[key] = raw
                break
            except ValueError as exc:
                print(exc)
    return build_skill(name, purpose, answers)


def list_built() -> list[dict]:
    return store.list_skills()


def describe(name: str) -> str:
    slug = _slug(name)
    path = os.path.join(config.skills_dir(), f"{slug}.md")
    if not os.path.isfile(path):
        raise ValueError(f"Unknown skill: {slug}")
    with open(path, encoding="utf-8") as fh:
        return fh.read()
