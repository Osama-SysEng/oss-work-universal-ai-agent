"""The 10 specializations.

A specialization is the way of working, applied to any domain: look and
explain, build it, audit it, test it, speed it up, find the fault, move it,
connect it, write it down, or research it.

Each specialization carries its own focus, its own default tools, its own
deliverable, and its own verification rules. Combined with the 30 domains
they produce the 300 specialized agents.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Specialization:
    """One way of working."""

    key: str
    title: str
    focus: str
    tools: tuple[str, ...]
    deliverable: str
    verify_rules: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "focus": self.focus,
            "tools": list(self.tools),
            "deliverable": self.deliverable,
            "verify_rules": list(self.verify_rules),
            "keywords": list(self.keywords),
        }


SPECIALIZATIONS: tuple[Specialization, ...] = (
    Specialization(
        key="analysis",
        title="Analysis",
        focus="Read what is there, explain how it works, and state what the evidence supports.",
        tools=("file.list", "file.read", "file.search", "code.analyze"),
        deliverable="an explanation that names the files and the facts behind it",
        verify_rules=(
            "the answer names the files it used",
            "every claim points to something that was actually read",
        ),
        keywords=("analyze", "analysis", "explain", "how does", "why", "inspect", "review the structure", "understand"),
    ),
    Specialization(
        key="implementation",
        title="Implementation",
        focus="Make the change, keep it reversible, and show that it works.",
        tools=("file.write", "file.move", "code.run", "code.analyze"),
        deliverable="the changed files, a summary of the change, and the result of running it",
        verify_rules=(
            "the promised files exist after the change",
            "the change was run or checked before delivery",
        ),
        keywords=("implement", "build", "create", "add", "write", "make", "develop", "code it", "set up"),
    ),
    Specialization(
        key="review",
        title="Review",
        focus="Look for what is wrong, missing, or risky, and rank the findings.",
        tools=("file.read", "file.search", "code.analyze", "rea.analyze"),
        deliverable="ranked findings, each with its evidence and its severity",
        verify_rules=(
            "every finding carries evidence",
            "the severity of a finding is stated",
        ),
        keywords=("review", "audit", "check", "critique", "evaluate", "assess", "inspect quality", "find problems"),
    ),
    Specialization(
        key="testing",
        title="Testing",
        focus="Design the checks, run them, and report what is still uncovered.",
        tools=("file.write", "code.run", "code.analyze", "file.read"),
        deliverable="the tests, the result, and the part that remains uncovered",
        verify_rules=(
            "the tests were executed",
            "the result reports failures rather than hiding them",
        ),
        keywords=("test", "tests", "testing", "coverage", "verify", "validate", "qa", "write tests"),
    ),
    Specialization(
        key="optimization",
        title="Optimization",
        focus="Measure first, change second, and report the gain against the cost.",
        tools=("code.analyze", "code.run", "file.read", "sheet.summarize"),
        deliverable="the measurement before and after, and the cost of the change",
        verify_rules=(
            "the baseline was measured before the change",
            "the claimed gain is tied to a measurement",
        ),
        keywords=("optimize", "optimise", "speed up", "performance", "faster", "slow", "bottleneck", "improve speed"),
    ),
    Specialization(
        key="debugging",
        title="Debugging",
        focus="Reproduce the fault, find the cause, and prove the cause with the fix.",
        tools=("code.run", "code.analyze", "file.search", "file.read"),
        deliverable="the reproduction, the cause, and the fix that stops it",
        verify_rules=(
            "the fault was reproduced before the fix",
            "the fix was checked against the reproduction",
        ),
        keywords=("debug", "bug", "fix", "crash", "error", "exception", "fails", "not working", "trace"),
    ),
    Specialization(
        key="migration",
        title="Migration",
        focus="Move from the old to the new without losing data and without a dead end.",
        tools=("file.read", "file.write", "file.move", "sheet.read"),
        deliverable="the migrated data, the differences that were handled, and the rollback",
        verify_rules=(
            "the row and record counts are compared before and after",
            "a rollback path is stated",
        ),
        keywords=("migrate", "migration", "port", "upgrade", "convert", "move to", "replace", "upgrade path"),
    ),
    Specialization(
        key="integration",
        title="Integration",
        focus="Connect the two systems, and make the boundary between them explicit.",
        tools=("file.read", "file.write", "web.read", "code.analyze"),
        deliverable="the integration, the contract on both sides, and the failure behaviour",
        verify_rules=(
            "the contract of both sides is written down",
            "the behaviour on failure is stated",
        ),
        keywords=("integrate", "integration", "connect", "webhook", "api call", "third party", "plugin", "link"),
    ),
    Specialization(
        key="documentation",
        title="Documentation",
        focus="Write it so the next person can act on it without asking anything.",
        tools=("file.read", "file.write", "office.write", "office.deck"),
        deliverable="the document, its structure, and the reader it assumes",
        verify_rules=(
            "the document has a stated audience and a starting point",
            "every command in the document was checked against the code",
        ),
        keywords=("document", "documentation", "readme", "guide", "write up", "manual", "explain how to", "tutorial"),
    ),
    Specialization(
        key="research",
        title="Research",
        focus="Gather from sources you can name, separate fact from guess, and say what is missing.",
        tools=("web.read", "file.read", "file.search", "rea.analyze"),
        deliverable="the findings with their sources, and the open questions",
        verify_rules=(
            "every finding names its source",
            "unknowns are stated as unknowns",
        ),
        keywords=(
            "research",
            "find out",
            "investigate",
            "compare options",
            "gather",
            "what is",
            "which is better",
            "study",
        ),
    ),
)

SPECIALIZATION_BY_KEY = {specialization.key: specialization for specialization in SPECIALIZATIONS}
