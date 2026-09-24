"""
CLI Interface for OSS Work — Typer-based command-line tool.
Provides: status, chat, test, update, models, imagination commands.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import typer

from core.imagination.engine import UltraIQEngine
from core.services.model_router import get_router
from core.services.skill_downloader import get_skill_downloader
from core.services.updater import get_updater


# ── CLI App ────────────────────────────────────────────────────

app = typer.Typer(
    name="oss-work",
    help="OSS Work — Open-Source Universal AI Agent CLI",
    short_help="Universal AI agent from the command line",
    add_completion=False,
)

VERSION = "0.2.0"


# ── Helpers ────────────────────────────────────────────────────

def _run_async(coro):
    """Run async coroutine in sync context."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    return asyncio.run(coro)


def _get_data_dir() -> Path:
    return Path(os.getenv("OSS_WORK_DATA_DIR", "./data"))


# ── Version ────────────────────────────────────────────────────

@app.command()
def version() -> None:
    """Show OSS Work version."""
    typer.echo(f"OSS Work v{VERSION}")
    typer.echo("NASA Space Apps Challenge 2025 Local Winner")
    typer.echo("AI Hackathon 2025 1st Place (260+ projects)")


# ── Status ─────────────────────────────────────────────────────

@app.command(name="status")
def status_cmd() -> None:
    """Show OSS Work system status."""
    typer.echo("=== OSS Work Status ===")
    typer.echo(f"Version: {VERSION}")
    typer.echo(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    typer.echo(f"Simulation Mode: {os.getenv('OSS_WORK_SIMULATION_ONLY', '1')}")

    data_dir = _get_data_dir()
    typer.echo(f"Data Directory: {data_dir}")

    # Check dependencies
    checks = {
        "Playwright": _check_import("playwright"),
        "httpx": _check_import("httpx"),
        "asyncpg": _check_import("asyncpg"),
        "redis": _check_import("redis"),
        "qdrant_client": _check_import("qdrant_client"),
        "telegram": _check_import("telegram"),
        "celery": _check_import("celery"),
        "scikit-learn": _check_import("sklearn"),
        "opencv": _check_import("cv2"),
    }

    typer.echo("\n--- Dependencies ---")
    all_ok = True
    for name, available in checks.items():
        status = "✅" if available else "❌"
        typer.echo(f"  {status} {name}")
        if not available:
            all_ok = False

    typer.echo(f"\nOverall: {'✅ All dependencies available' if all_ok else '❌ Some dependencies missing'}")


def _check_import(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False


# ── Chat ───────────────────────────────────────────────────────

@app.command(name="chat")
def chat_cmd(
    task: str = typer.Argument(..., help="Task to execute"),
    user: str = typer.Option("local", "--user", "-u", help="User ID"),
    model: str = typer.Option(None, "--model", "-m", help="Specific model to use"),
) -> None:
    """Execute a task through OSS Work."""
    typer.echo(f"\n🤖 Processing: {task}")
    typer.echo("---")

    # Use imagination engine for thought completion
    try:
        engine = UltraIQEngine(max_threads=10, simulation_depth=5)
        completed = engine.complete_thought(task, {"user_id": user})
        typer.echo(f"💭 Completed thought: {completed}")
    except Exception as e:
        typer.echo(f"⚠️ Thought completion skipped: {e}")
        completed = task

    # Route through model router
    try:
        router = get_router()
        result = _run_async(
            router.complete(completed, {"max_tokens": 2000, "temperature": 0.7}, model)
        )

        if result["status"] == "completed":
            typer.echo(f"\n✅ Response from {result['model']} ({result['provider']}):")
            typer.echo(f"\n{result['response']}")
            typer.echo(f"\n--- {result['latency_ms']}ms via {result['route']} ---")
        else:
            typer.echo(f"\n❌ Failed: {result.get('error', 'Unknown error')}")
    except Exception as e:
        typer.echo(f"\n❌ Error: {e}")
        typer.echo("Tip: Set up API keys or use simulation mode.")


# ── Models ─────────────────────────────────────────────────────

@app.command(name="models")
def models_cmd() -> None:
    """List available AI models."""
    router = get_router()
    typer.echo(f"=== Available Models ({len(router._model_map)}) ===\n")

    by_provider: dict[str, list] = {}
    for model in router._model_map.values():
        provider = model.provider.value
        if provider not in by_provider:
            by_provider[provider] = []
        by_provider[provider].append(model)

    for provider, models in sorted(by_provider.items()):
        typer.echo(f"--- {provider.upper()} ---")
        for m in sorted(models, key=lambda x: x.name):
            vision = "👁" if m.supports_vision else "  "
            free = "💰FREE" if m.cost_per_1k_tokens == 0 else f"💵${m.cost_per_1k_tokens}"
            typer.echo(f"  {vision} {m.name:30} {m.category:12} {free}  ctx:{m.context_window}")
        typer.echo()


# ── Test ───────────────────────────────────────────────────────

@app.command(name="test")
def test_cmd(
    module: str = typer.Option("all", "--module", "-m", help="Test module: all, imagination, agents, services"),
) -> None:
    """Run OSS Work tests."""
    typer.echo("Running OSS Work tests...\n")

    if module == "all":
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short"],
            cwd=os.getcwd(),
        )
        sys.exit(result.returncode)
    elif module == "imagination":
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_imagination.py", "-v"],
            cwd=os.getcwd(),
        )
        sys.exit(result.returncode)
    elif module == "agents":
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_runtime.py", "tests/test_safety.py", "-v"],
            cwd=os.getcwd(),
        )
        sys.exit(result.returncode)
    elif module == "services":
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_telemetry.py", "-v"],
            cwd=os.getcwd(),
        )
        sys.exit(result.returncode)
    else:
        typer.echo(f"Unknown module: {module}")


# ── Imagination ───────────────────────────────────────────────

@app.command(name="imagine")
def imagine_cmd(
    task: str = typer.Argument(..., help="Task to imagine solutions for"),
    threads: int = typer.Option(50, "--threads", "-t", help="Max parallel threads"),
    depth: int = typer.Option(20, "--depth", "-d", help="Simulation depth"),
    arabic: bool = typer.Option(False, "--arabic", "-a", help="Arabic response"),
) -> None:
    """Run Ultra IQ Imagination Engine on a task."""
    typer.echo(f"\n🧠 Imagining solutions for: {task}")
    typer.echo(f"Threads: {threads}, Depth: {depth}")
    typer.echo("---")

    engine = UltraIQEngine(max_threads=threads, simulation_depth=depth)
    result = _run_async(engine.process(task))

    typer.echo(f"\n✅ Solution (confidence: {result.confidence:.2f}):")
    typer.echo(f"\n{result.solution}")
    typer.echo(f"\n---")
    typer.echo(f"Threads explored: {result.threads_explored}")
    typer.echo(f"Invented: {result.invented}")
    typer.echo(f"Simulations: {result.simulation_branches}")
    typer.echo(f"Elapsed: {result.elapsed_ms:.0f}ms")

    if result.reasoning_chain:
        typer.echo(f"\n📋 Reasoning chain:")
        for i, step in enumerate(result.reasoning_chain, 1):
            typer.echo(f"  {i}. {step}")

    if result.cross_domain_bridges:
        typer.echo(f"\n🔗 Cross-domain bridges:")
        for bridge in result.cross_domain_bridges[:5]:
            typer.echo(f"  • {bridge}")


# ── Skill ──────────────────────────────────────────────────────

@app.command(name="skill")
def skill_cmd(
    capability: str = typer.Argument(..., help="Capability to acquire (e.g., browser_automation)"),
    install: bool = typer.Option(True, "--install/--no-install", help="Install after finding"),
) -> None:
    """Search and install a skill."""
    downloader = get_skill_downloader()

    typer.echo(f"🔍 Searching for skill: {capability}")

    # List installed skills first
    installed = downloader.list_installed()
    if installed:
        typer.echo("\n--- Installed Skills ---")
        for skill in installed:
            typer.echo(f"  • {skill.name} ({skill.source}) — {skill.capability}")

    if not install:
        typer.echo("\nSearch only — not installing.")
        return

    typer.echo("\nAttempting acquisition...")
    result = _run_async(downloader.acquire_skill(capability))

    if result.status == "installed":
        typer.echo(f"\n✅ Installed: {result.name} at {result.path}")
    elif result.status == "already_installed":
        typer.echo(f"\nℹ️ Already installed: {result.name}")
    elif result.status == "not_found":
        typer.echo(f"\n❌ Not found: {result.error}")
    elif result.status == "failed":
        typer.echo(f"\n❌ Failed: {result.error}")


# ── Update ─────────────────────────────────────────────────────

@app.command(name="update")
def update_cmd(check_only: bool = typer.Option(False, "--check/--apply", help="Check only or apply update")) -> None:
    """Check for or apply OSS Work updates."""
    updater = get_updater()

    typer.echo("Checking for updates...")

    if check_only:
        info = _run_async(updater.get_available_updates())
        if info.get("available"):
            typer.echo(f"\n✅ Update available: v{info['latest']}")
            typer.echo(f"Current: v{info['current']}")
            typer.echo(f"Release notes: {info.get('release_notes', '')[:200]}")
        else:
            typer.echo(f"\n✅ Up to date: v{info.get('current', 'unknown')}")
        return

    result = _run_async(updater.check_and_update())
    typer.echo(f"\nUpdate result: {result.status}")
    if result.message:
        typer.echo(f"Message: {result.message}")
    if result.error:
        typer.echo(f"Error: {result.error}")


# ── Data Directory ─────────────────────────────────────────────

@app.command(name="data-dir")
def data_dir_cmd() -> None:
    """Show OSS Work data directory."""
    typer.echo(str(_get_data_dir()))


# ── Entry Point ─────────────────────────────────────────────────

def main() -> None:
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
