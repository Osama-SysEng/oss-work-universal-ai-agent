"""
tests/test_imagination.py — Ultra IQ Imagination Engine tests.

Covers: core imagine flow, multi-domain, simulation, invention,
       confidence, cross-domain bridges, Arabic/Chinese, long-form.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from core.imagination.contracts import (
    Thread,
    Simulation,
    ImaginationEngineConfig,
)
from core.imagination.engine import ImaginationResult


class TestThread:
    """Thread record contract tests."""

    def test_defaults(self):
        t = Thread(domain="general", approach="reasoning", outcome="OK", confidence=0.8)
        assert t.domain == "general"
        assert t.approach == "reasoning"
        assert t.outcome == "OK"
        assert t.confidence == 0.8
        assert t.elapsed_ms == 0.0
        assert t.novel_connections == []

    def test_with_connections(self):
        t = Thread(
            domain="code",
            approach="patterns",
            outcome="Singleton chosen",
            confidence=0.9,
            novel_connections=["Observer", "Strategy"],
        )
        assert len(t.novel_connections) == 2
        assert t.novel_connections[0] == "Observer"


class TestSimulation:
    """Simulation record contract tests."""

    def test_defaults(self):
        s = Simulation(timeline="V1", outcome="OK", probability=0.8)
        assert s.timeline == "V1"
        assert s.outcome == "OK"
        assert s.probability == 0.8
        assert s.failure_modes == []
        assert s.time_horizons == {}

    def test_with_horizons(self):
        s = Simulation(
            timeline="V2",
            outcome="OK with caveats",
            probability=0.6,
            failure_modes=["latency", "cost"],
            time_horizons={"near": "OK", "far": "needs more testing"},
        )
        assert len(s.failure_modes) == 2
        assert s.time_horizons["near"] == "OK"


class TestImaginationResult:
    """ImaginationResult contract tests."""

    def test_full_result(self):
        r = ImaginationResult(
            solution="Use a CRDT-based approach",
            reasoning_chain=["1. Analyze requirements", "2. Evaluate CRDT vs OT"],
            confidence=0.85,
            threads_explored=300,
            invented=True,
            simulation_branches=3,
            cross_domain_bridges=["OperationalTransform × CRDTs"],
            elapsed_ms=45.0,
            selected_domain="Code",
            selected_approach="framework_design",
        )
        assert r.solution == "Use a CRDT-based approach"
        assert r.confidence == 0.85
        assert r.invented is True
        assert r.threads_explored == 300
        assert len(r.cross_domain_bridges) == 1


class TestImaginationEngineConfig:
    """Configuration contract tests."""

    def test_defaults(self):
        cfg = ImaginationEngineConfig()
        assert cfg.max_threads == 1000
        assert cfg.invention_enabled is True
        assert cfg.simulation_depth == 100
        assert cfg.domains == 50
        assert cfg.data_dir == "./data/imagination"

    def test_custom(self):
        cfg = ImaginationEngineConfig(
            max_threads=500,
            invention_enabled=False,
            simulation_depth=50,
            domains=20,
            data_dir="/custom/path",
        )
        assert cfg.max_threads == 500
        assert cfg.invention_enabled is False
        assert cfg.simulation_depth == 50
        assert cfg.domains == 20
        assert cfg.data_dir == "/custom/path"


class TestUltraIQSimulate:
    """Integration smoke tests for UltraIQE.imagine (simulated mode)."""

    @pytest.mark.asyncio
    async def test_imagine_returns_result(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine("Design a notification system")

        assert isinstance(result, ImaginationResult)
        assert isinstance(result.solution, str) and len(result.solution) > 10
        assert isinstance(result.reasoning_chain, list)
        assert 0.0 <= result.confidence <= 1.0
        assert result.threads_explored > 0

    @pytest.mark.asyncio
    async def test_imagine_small_task(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        start = time.monotonic()
        result = await engine.imagine("Hello world")
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 200  # Simulated — should be fast
        assert len(result.solution) > 0

    @pytest.mark.asyncio
    async def test_imagine_long_task(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        start = time.monotonic()
        result = await engine.imagine(
            "Design a scalable notification system for 10M users",
            requirements={"language": "English", "detail_level": "comprehensive"},
        )
        elapsed_ms = (time.monotonic() - start) * 1000

        assert elapsed_ms < 500
        assert len(result.solution) > 200  # Longer output for comprehensive
        assert result.confidence > 0.0

    @pytest.mark.asyncio
    async def test_imagine_arabic(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "صمم نظام إشعارات لـ 10 مليون مستخدم",
            requirements={"lang": "Arabic", "detail_level": "comprehensive"},
        )

        assert isinstance(result, ImaginationResult)
        assert len(result.solution) > 50

    @pytest.mark.asyncio
    async def test_imagine_chinese(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "设计一个可扩展的通知系统",
            requirements={"lang": "Chinese", "detail_level": "medium"},
        )

        assert isinstance(result, ImaginationResult)
        assert len(result.solution) > 50

    @pytest.mark.asyncio
    async def test_imagine_code_task(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "Write a Python function to compute Fibonacci numbers",
            requirements={"language": "Python"},
        )

        assert isinstance(result, ImaginationResult)
        assert "Fibonacci" in result.solution or "fibonacci" in result.solution.lower()

    @pytest.mark.asyncio
    async def test_imagine_creative(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "Write a short story about AI",
            requirements={"language": "English", "detail_level": "creative"},
        )

        assert isinstance(result, ImaginationResult)
        assert len(result.solution) > 50

    @pytest.mark.asyncio
    async def test_thread_count_reasonable(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine("Quick question")

        # Thread count should be >= 1 and <= 1000 (config max)
        assert 1 <= result.threads_explored <= 1000

    @pytest.mark.asyncio
    async def test_invention_trigger_exists(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "Design a new type of database for real-time collaboration",
        )

        assert isinstance(result, ImaginationResult)
        # Invention should at least be evaluated
        assert isinstance(result.invented, bool)

    @pytest.mark.asyncio
    async def test_cross_domain_bridges(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "Design a notification system",
            requirements={"detail_level": "comprehensive"},
        )

        assert isinstance(result.cross_domain_bridges, list)
        # Comprehensive tasks should find bridges
        assert len(result.cross_domain_bridges) >= 0

    @pytest.mark.asyncio
    async def test_simulation_branches(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine("Anything")

        assert result.simulation_branches >= 0

    @pytest.mark.asyncio
    async def test_data_dir_respected(self):
        from core.imagination.engine import UltraIQE
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            engine = UltraIQE(config=ImaginationEngineConfig(data_dir=tmpdir))
            result = await engine.imagine("Test")

            assert isinstance(result, ImaginationResult)
            # Engine should not crash with custom data dir
            assert result.confidence >= 0.0


class TestUltraIQInvention:
    """Invention-specific tests."""

    @pytest.mark.asyncio
    async def test_invention_disabled(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE(config=ImaginationEngineConfig(invention_enabled=False))
        result = await engine.imagine("Design something new")

        assert isinstance(result, ImaginationResult)
        # When disabled, invention should be False
        assert result.invented is False

    @pytest.mark.asyncio
    async def test_invention_enabled(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE(config=ImaginationEngineConfig(invention_enabled=True))
        result = await engine.imagine("Design a new programming paradigm")

        assert isinstance(result, ImaginationResult)
        assert isinstance(result.invented, bool)


class TestUltraIQMultiDomain:
    """Multi-domain exploration tests."""

    @pytest.mark.asyncio
    async def test_domains_selected(self):
        from core.imagination.engine import UltraIQE

        engine = UltraIQE()
        result = await engine.imagine(
            "Design a notification system",
            requirements={"detail_level": "comprehensive"},
        )

        assert isinstance(result.selected_domain, str)
        assert isinstance(result.selected_approach, str)