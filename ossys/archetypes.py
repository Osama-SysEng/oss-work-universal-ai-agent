"""~30 task-agent archetypes. The 300 OS task agents are data rows
in task_registry.py pointing at these archetypes — not 300 files.

Each archetype maps to a real executor:
  orchestrator | file | code | security | memory | learning
  | reader (ossys.browser) | office (ossys.office) | hosting (ossys.hosting)
  | skills (ossys.skills) | scheduler (ossys.scheduler) | engine (local LLM)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Archetype:
    id: str
    title: str
    executor: str
    background_ok: bool
    description: str


ARCHETYPES: tuple[Archetype, ...] = (
    Archetype("general", "General assistant", "orchestrator", False, "Any ad-hoc local task via the orchestrator."),
    Archetype("planner", "Task planner", "orchestrator", False, "Decompose a goal into ordered local steps."),
    Archetype("reviewer", "Work reviewer", "orchestrator", True, "Review a result against the original request."),
    Archetype("file_reader", "File reader", "file", False, "Read and summarize local files."),
    Archetype("file_organizer", "File organizer", "file", True, "Propose and apply local file organization."),
    Archetype("file_search", "File searcher", "file", True, "Search workspace contents by keyword."),
    Archetype("code_writer", "Code writer", "code", False, "Draft code from a local spec."),
    Archetype("code_reviewer", "Code reviewer", "code", False, "Static review of local code (no execution)."),
    Archetype("code_refactor", "Code refactorer", "code", False, "Refactor suggestions for local code."),
    Archetype("code_docs", "Code documenter", "code", True, "Generate documentation for local code."),
    Archetype("sec_scanner", "Security scanner", "security", True, "Scan local files for secrets and risky patterns."),
    Archetype("sec_policy", "Policy checker", "security", False, "Check an action against the safety policy."),
    Archetype("memory_writer", "Memory writer", "memory", True, "Record a durable local note."),
    Archetype("memory_reader", "Memory reader", "memory", False, "Recall durable local notes."),
    Archetype("learner", "Pattern learner", "learning", True, "Discover patterns in local history."),
    Archetype("profiler", "Usage profiler", "learning", True, "Summarize local usage profile."),
    Archetype("web_reader", "Web reader", "reader", False, "Fetch and extract text from a URL (no JS)."),
    Archetype("web_monitor", "Web monitor", "reader", True, "Re-check a URL for changes on a schedule."),
    Archetype("doc_writer", "Document writer", "office", False, "Write txt/markdown documents locally."),
    Archetype("doc_summarizer", "Document summarizer", "office", False, "Summarize local documents."),
    Archetype("sheet_keeper", "Spreadsheet keeper", "office", False, "Maintain local CSV sheets."),
    Archetype("sheet_analyst", "Sheet analyst", "office", True, "Aggregate and summarize local CSV data."),
    Archetype("deck_builder", "Deck builder", "office", False, "Build a local HTML slide deck from notes."),
    Archetype("note_taker", "Note taker", "office", False, "Append timestamped local notes."),
    Archetype("app_host", "App host", "hosting", False, "Serve a local static folder over loopback."),
    Archetype("app_publisher", "App publisher", "hosting", False, "Register a local app for serving."),
    Archetype("job_runner", "Background runner", "scheduler", True, "Run a task in the background now or later."),
    Archetype("job_watcher", "Job watcher", "scheduler", False, "Report background job states."),
    Archetype("skill_builder", "Skill builder", "skills", False, "Build a skill from yes/no answers."),
    Archetype("skill_librarian", "Skill librarian", "skills", False, "List and describe self-built skills."),
)


def all_archetypes() -> list[Archetype]:
    return list(ARCHETYPES)


def get_archetype(archetype_id: str) -> Archetype | None:
    for arch in ARCHETYPES:
        if arch.id == archetype_id:
            return arch
    return None


def executors() -> dict[str, str]:
    """Archetype id -> executor kind."""
    return {a.id: a.executor for a in ARCHETYPES}
