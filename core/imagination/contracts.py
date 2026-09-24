"""
Imagination Engine Contracts — typed result contracts for Ultra IQ.

Defines: ImaginationResult, Thread, Simulation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Thread:
    """A single parallel reasoning thread exploring one domain."""
    domain: str
    approach: str
    outcome: str
    confidence: float
    novel_connections: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class Simulation:
    """A future timeline branch from Tesla-style simulation."""
    timeline: str
    outcome: str
    probability: float
    failure_modes: list[str] = field(default_factory=list)
    time_horizons: dict[str, str] = field(default_factory=dict)


@dataclass
class ImaginationResult:
    """The final output of the Imagination Engine."""
    solution: str
    reasoning_chain: list[str]
    confidence: float
    threads_explored: int
    invented: bool
    simulation_branches: int = 0
    cross_domain_bridges: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    selected_domain: str = ""
    selected_approach: str = ""


@dataclass
class ImaginationEngineConfig:
    """Configuration for the Ultra IQ Imagination Engine."""
    max_threads: int = 1000
    invention_enabled: bool = True
    simulation_depth: int = 100
    domains: int = 50
    data_dir: str = "./data/imagination"


# Compatibility exports
ThreadData = Thread
SimulationData = Simulation
ResultData = ImaginationResult
