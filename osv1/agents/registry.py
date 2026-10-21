"""The registry of 300 specialized agents.

Thirty domains times ten specializations. Each combination is a real agent:
it has its own tool capabilities, its own risk level, its own verification
rules, its own plan template, and its own prompt for the language model. The
agents are not decoration — the runner in :mod:`osv1.agents.base` dispatches
to them, and the API and the CLI list them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from osv1.agents.domains import DOMAINS, Domain
from osv1.agents.specializations import SPECIALIZATIONS, Specialization


def _word_present(text: str, keyword: str) -> bool:
    """True when the keyword appears as a whole word. Substring matches are noise."""
    if not keyword:
        return False
    return re.search(rf"(?<![a-z0-9_]){re.escape(keyword)}(?![a-z0-9_])", text) is not None


# The order of the plan template for each specialization: what the agent does
# first, and what it does after that.
PLAN_TEMPLATES: dict[str, tuple[tuple[str, str], ...]] = {
    "analysis": (
        ("file.list", "see what is there"),
        ("file.read", "read the relevant parts"),
        ("file.search", "check the details"),
    ),
    "implementation": (
        ("file.read", "read what the change depends on"),
        ("file.write", "write the change"),
        ("code.run", "run it"),
    ),
    "review": (
        ("file.read", "read the material"),
        ("code.analyze", "analyse it"),
        ("file.search", "check the wider context"),
    ),
    "testing": (
        ("file.read", "read what is being tested"),
        ("file.write", "write the test"),
        ("code.run", "run the test"),
    ),
    "optimization": (
        ("code.analyze", "measure the current state"),
        ("code.run", "measure the behaviour"),
        ("code.run", "measure the change"),
    ),
    "debugging": (
        ("code.run", "reproduce the fault"),
        ("code.analyze", "locate the cause"),
        ("code.run", "check the fix"),
    ),
    "migration": (
        ("file.read", "read the source data"),
        ("sheet.read", "read the table"),
        ("file.write", "write the migrated form"),
    ),
    "integration": (
        ("file.read", "read the existing side"),
        ("web.read", "check the other side"),
        ("file.write", "write the bridge"),
    ),
    "documentation": (("file.read", "read the material"), ("file.write", "write the document")),
    "research": (("file.search", "look in the local material"), ("web.read", "look at the outside source")),
}


@dataclass(frozen=True)
class AgentSpec:
    """One specialized agent."""

    id: str
    domain: Domain
    specialization: Specialization
    title: str
    description: str
    capabilities: tuple[str, ...]
    risk: str
    verify_rules: tuple[str, ...]
    plan_template: tuple[tuple[str, str], ...]
    focus: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "domain": self.domain.key,
            "domain_title": self.domain.title,
            "specialization": self.specialization.key,
            "specialization_title": self.specialization.title,
            "capabilities": list(self.capabilities),
            "risk": self.risk,
            "verify_rules": list(self.verify_rules),
            "deliverable": self.specialization.deliverable,
            "plan_template": [{"tool": tool, "intent": intent} for tool, intent in self.plan_template],
        }


def _build_agents() -> tuple[AgentSpec, ...]:
    agents: list[AgentSpec] = []
    counter = 0
    for domain in DOMAINS:
        for specialization in SPECIALIZATIONS:
            counter += 1
            shared = tuple(tool for tool in specialization.tools if tool in domain.tools)
            capabilities = shared or tuple(tool for tool in specialization.tools if tool in domain.tools)
            if not capabilities:
                capabilities = ("file.read",)
            risk = "high" if domain.risk == "high" else domain.risk
            rules = tuple(specialization.verify_rules) + (f"the work stays inside the {domain.title.lower()} domain",)
            agents.append(
                AgentSpec(
                    id=f"A{counter:03d}",
                    domain=domain,
                    specialization=specialization,
                    title=f"{specialization.title} - {domain.title}",
                    description=(f"{specialization.focus} Applies to {domain.summary.lower()}"),
                    capabilities=capabilities,
                    risk=risk,
                    verify_rules=rules,
                    plan_template=PLAN_TEMPLATES[specialization.key],
                    focus=(
                        f"You are a {specialization.title.lower()} specialist in {domain.title}. "
                        f"{specialization.focus} "
                        f"Deliverable: {specialization.deliverable}. "
                        f"Available tools: {', '.join(capabilities)}."
                    ),
                )
            )
    return tuple(agents)


AGENTS: tuple[AgentSpec, ...] = _build_agents()
AGENT_BY_ID: dict[str, AgentSpec] = {agent.id: agent for agent in AGENTS}


class AgentRegistry:
    """Lookup, filtering, and routing over the 300 agents."""

    def __init__(self, agents: tuple[AgentSpec, ...] = AGENTS) -> None:
        self._agents = agents
        self._by_id = {agent.id: agent for agent in agents}

    def __len__(self) -> int:
        return len(self._agents)

    def all(self) -> tuple[AgentSpec, ...]:
        return self._agents

    def get(self, agent_id: str) -> AgentSpec | None:
        return self._by_id.get(agent_id.upper())

    def by_domain(self, domain_key: str) -> list[AgentSpec]:
        return [agent for agent in self._agents if agent.domain.key == domain_key]

    def by_specialization(self, specialization_key: str) -> list[AgentSpec]:
        return [agent for agent in self._agents if agent.specialization.key == specialization_key]

    def search(self, query: str, *, limit: int = 20) -> list[tuple[AgentSpec, int]]:
        """Find agents by keyword, domain, or specialization."""
        terms = {term for term in query.lower().replace("-", " ").split() if len(term) > 2}
        scored: list[tuple[AgentSpec, int]] = []
        for agent in self._agents:
            score = 0
            haystack = " ".join(
                (
                    agent.id.lower(),
                    agent.domain.key.replace("-", " "),
                    agent.domain.title.lower(),
                    agent.specialization.key,
                    agent.specialization.title.lower(),
                    agent.description.lower(),
                )
            )
            for term in terms:
                if term in haystack:
                    score += 2
                for keyword in agent.domain.keywords:
                    if term == keyword:
                        score += 3
            if score:
                scored.append((agent, score))
        scored.sort(key=lambda item: (-item[1], item[0].id))
        return scored[:limit]

    def route(self, task: str) -> tuple[AgentSpec | None, dict[str, Any]]:
        """Pick the agent for a task.

        The routing is transparent: it counts the vocabulary of the task
        against the vocabulary of each domain and specialization. The result
        carries the score, so a caller can tell a strong match from a weak
        one and ask the user instead of guessing.
        """
        text = task.lower()
        domain_scores: list[tuple[Domain, int]] = []
        for domain in DOMAINS:
            score = sum(1 for keyword in domain.keywords if _word_present(text, keyword))
            if domain.key.replace("-", " ") in text:
                score += 3
            domain_scores.append((domain, score))
        domain_scores.sort(key=lambda item: item[1], reverse=True)
        best_domain, domain_score = domain_scores[0]
        runner_up = domain_scores[1][1] if len(domain_scores) > 1 else 0

        spec_scores: list[tuple[Specialization, int]] = []
        for specialization in SPECIALIZATIONS:
            score = sum(1 for keyword in specialization.keywords if _word_present(text, keyword))
            if specialization.key in text:
                score += 2
            spec_scores.append((specialization, score))
        spec_scores.sort(key=lambda item: item[1], reverse=True)
        best_spec, spec_score = spec_scores[0]

        total = domain_score + spec_score
        confidence = 0.0
        if total:
            confidence = min(0.95, 0.35 + 0.1 * total + 0.05 * (domain_score - runner_up))
        agent = next(
            (
                candidate
                for candidate in self._agents
                if candidate.domain.key == best_domain.key and candidate.specialization.key == best_spec.key
            ),
            None,
        )
        return agent, {
            "domain": best_domain.key,
            "domain_score": domain_score,
            "domain_runner_up": runner_up,
            "specialization": best_spec.key,
            "specialization_score": spec_score,
            "confidence": round(confidence, 3),
            "routing": "transparent keyword scoring over the domain and specialization vocabularies",
        }

    def catalog(self) -> dict[str, Any]:
        """A summary of the whole registry, with real counts."""
        return {
            "total": len(self._agents),
            "domains": len(DOMAINS),
            "specializations": len(SPECIALIZATIONS),
            "by_domain": {domain.key: len(self.by_domain(domain.key)) for domain in DOMAINS},
            "by_specialization": {
                specialization.key: len(self.by_specialization(specialization.key))
                for specialization in SPECIALIZATIONS
            },
            "capabilities": sorted({tool for agent in self._agents for tool in agent.capabilities}),
        }


REGISTRY = AgentRegistry()
