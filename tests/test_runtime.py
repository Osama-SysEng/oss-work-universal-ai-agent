from pathlib import Path

from core.agents.integration_agent import IntegrationAgent
from core.agents.memory_agent import MemoryAgent
from core.agents.orchestrator import OrchestratorAgent


def test_memory_round_trip_is_user_scoped(tmp_path: Path):
    db = tmp_path / "memory.sqlite3"
    write = MemoryAgent(
        context={"db_path": str(db), "task": "write", "user_id": "a", "key": "k", "value": "v"}
    ).execute()
    assert write["status"] == "completed"
    own = MemoryAgent(context={"db_path": str(db), "task": "read", "user_id": "a", "key": "k"}).execute()
    other = MemoryAgent(context={"db_path": str(db), "task": "read", "user_id": "b", "key": "k"}).execute()
    assert own["data"]["memory"]["value"] == "v"
    assert other["data"]["memory"] is None


def test_orchestrator_is_bounded_and_reports_no_external_actions():
    result = OrchestratorAgent(task="browser security code file integration memory learning").execute()
    assert result["status"] == "completed"
    assert result["data"]["subtasks_processed"] <= 5
    assert result["data"]["external_actions_attempted"] is False


def test_integration_is_simulation_only():
    result = IntegrationAgent(context={"task": "send", "integration": "webhook", "action": "send"}).execute()
    assert result["status"] == "simulated"
    assert result["data"]["action"] == "send"
    assert result["decision"]["external_action_attempted"] is False


def test_integration_refuses_non_localhost():
    import asyncio
    import time

    agent = IntegrationAgent(
        context={
            "task": "send",
            "integration": "webhook",
            "action": "send",
            "url": "https://example.com/hook",
        }
    )
    result = asyncio.run(agent._webhook_handler("webhook", "send", time.monotonic()))
    assert result["status"] == "failed"
    assert "loopback" in result["data"]["error"]


def test_unknown_integration_rejected():
    result = IntegrationAgent(context={"task": "x", "integration": "telegram", "action": "send"}).execute()
    assert result["status"] == "failed"
    assert "local-only" in result["data"]["error"]
