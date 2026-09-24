"""
OSS Work — Open-Source Universal AI Agent

The world's first open-source AI agent with genuine imagination.
NASA Space Apps Challenge 2025 Local Winner · AI Hackathon 2025 1st Place.

Built by Osama Mohamed Fathy.
"""

from .engine import UltraIQEngine as UltraIQE
from .contracts import (
    Thread,
    Simulation,
    ImaginationResult,
    ImaginationEngineConfig,
)

__version__ = "1.0.0-dev"
__all__ = [
    "UltraIQE",
    "Thread",
    "Simulation",
    "ImaginationResult",
    "ImaginationEngineConfig",
]
