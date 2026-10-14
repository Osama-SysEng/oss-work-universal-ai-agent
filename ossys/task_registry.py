"""The 300 internal task agents: data, not files.

30 archetypes x 10 variants = 300 addressable agents (T001..T300).
Each task resolves to an archetype executor in the kernel — no mocks:
executors are the real core agents and ossys services.
"""

from __future__ import annotations

from dataclasses import dataclass

from ossys.archetypes import ARCHETYPES

_VARIANTS: tuple[str, ...] = (
    "quick handling",
    "deep handling",
    "scheduled handling",
    "review pass",
    "batch handling",
    "guided handling",
    "verification pass",
    "summary handling",
    "follow-up handling",
    "audit handling",
)


@dataclass(frozen=True)
class TaskAgent:
    id: str
    archetype: str
    title: str
    brief: str
    background_ok: bool


def _build() -> list[TaskAgent]:
    tasks: list[TaskAgent] = []
    seq = 0
    for arch in ARCHETYPES:
        for variant in _VARIANTS:
            seq += 1
            tasks.append(
                TaskAgent(
                    id=f"T{seq:03d}",
                    archetype=arch.id,
                    title=f"{arch.title} — {variant}",
                    brief=f"{arch.description} Mode: {variant}.",
                    background_ok=arch.background_ok,
                )
            )
    return tasks


TASKS: list[TaskAgent] = _build()
assert len(TASKS) == 300, f"registry must hold 300 task agents, got {len(TASKS)}"


def all_tasks() -> list[TaskAgent]:
    return list(TASKS)


def get_task(task_id: str) -> TaskAgent | None:
    for task in TASKS:
        if task.id == task_id.upper():
            return task
    return None


def by_archetype(archetype_id: str) -> list[TaskAgent]:
    return [t for t in TASKS if t.archetype == archetype_id]


def search(keyword: str) -> list[TaskAgent]:
    kw = keyword.strip().lower()
    if not kw:
        return []
    return [t for t in TASKS if kw in t.title.lower() or kw in t.brief.lower()]
