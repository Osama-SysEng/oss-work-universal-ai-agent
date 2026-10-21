"""The 300 specialized agents: domains, specializations, registry, runner."""

from __future__ import annotations

from osv1.agents.base import AgentRunner
from osv1.agents.domains import DOMAIN_BY_KEY, DOMAINS, Domain
from osv1.agents.registry import AGENT_BY_ID, AGENTS, REGISTRY, AgentRegistry, AgentSpec
from osv1.agents.specializations import SPECIALIZATION_BY_KEY, SPECIALIZATIONS, Specialization

__all__ = [
    "AGENTS",
    "AGENT_BY_ID",
    "DOMAINS",
    "DOMAIN_BY_KEY",
    "REGISTRY",
    "SPECIALIZATIONS",
    "SPECIALIZATION_BY_KEY",
    "AgentRegistry",
    "AgentRunner",
    "AgentSpec",
    "Domain",
    "Specialization",
]
