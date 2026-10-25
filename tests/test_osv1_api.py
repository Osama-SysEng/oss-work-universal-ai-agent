"""The local API: every endpoint reflects a real state of the system."""

from __future__ import annotations

import os
import tempfile

# The runtime is created when the module is imported, so the directories are
# pointed at a temporary place before the import happens.
os.environ.setdefault("OSS_V1_DATA_DIR", tempfile.mkdtemp(prefix="osv1-api-data-"))
os.environ.setdefault("OSS_V1_WORKSPACE_DIR", tempfile.mkdtemp(prefix="osv1-api-ws-"))
os.environ.setdefault("OSS_V1_SKILLS_DIR", tempfile.mkdtemp(prefix="osv1-api-skills-"))

# These tests check the endpoints against a known state of the system, so the
# engine is pointed at a port nothing listens on. Without this the suite's
# result depended on whether a local model happened to be running: with one up,
# the decision engine asked the user instead of deciding and three tests here
# failed. A test that passes only while its dependency is down is not a test —
# the graded suite is what measures the engine, deliberately and separately.
os.environ.setdefault("OSS_LOCAL_URL", "http://127.0.0.1:1")

from fastapi.testclient import TestClient  # noqa: E402

from osv1.interface.api import app  # noqa: E402

client = TestClient(app)


def test_health_reports_the_product() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model"] == "OS_V1"


def test_the_status_reports_the_real_state() -> None:
    payload = client.get("/status").json()
    assert payload["agents"] == 300
    assert payload["audit"]["valid"] is True
    assert payload["kill_switch"]["engaged"] is False


def test_the_agent_list_is_paginated_and_complete() -> None:
    payload = client.get("/agents?limit=5&offset=0").json()
    assert payload["total"] == 300
    assert len(payload["agents"]) == 5
    assert payload["limit"] == 5

    page_two = client.get("/agents?limit=5&offset=5").json()
    assert page_two["agents"][0]["id"] != payload["agents"][0]["id"]


def test_one_agent_can_be_fetched() -> None:
    payload = client.get("/agents/A001").json()
    assert payload["id"] == "A001"
    assert payload["capabilities"]
    assert client.get("/agents/A999").status_code == 404


def test_the_catalog_reports_the_real_counts() -> None:
    payload = client.get("/catalog").json()
    assert payload["total"] == 300
    assert payload["domains"] == 30
    assert payload["specializations"] == 10


def test_plan_returns_a_plan_and_executes_nothing() -> None:
    response = client.post("/plan", json={"task": "analyze the readme", "agent_id": ""})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "planned"
    assert payload["plan"]["steps"]
    assert payload["actions"] == []


def test_a_short_task_is_refused() -> None:
    response = client.post("/plan", json={"task": "x"})
    assert response.status_code == 422


def test_build_runs_and_reports_the_verification() -> None:
    payload = client.post("/build", json={"task": "review the readme for security issues"}).json()
    assert payload["status"] in ("completed", "failed")
    assert payload["verification"] is not None
    assert payload["metrics"]["metrics"]


def test_the_memory_can_be_read_and_exported() -> None:
    payload = client.get("/memory").json()
    assert "entries" in payload
    assert client.post("/memory/export").status_code == 200


def test_the_audit_chain_can_be_verified() -> None:
    payload = client.get("/audit/verify").json()
    assert payload["valid"] is True


def test_a_permission_can_be_granted_and_revoked() -> None:
    granted = client.post("/permissions/grant", json={"scope": "network", "target": "example.com"}).json()
    assert granted["scope"] == "network"
    assert any(grant["target"] == "example.com" for grant in client.get("/permissions").json()["grants"])
    removed = client.post("/permissions/revoke", json={"scope": "network", "target": "example.com"}).json()
    assert removed["removed"] == 1


def test_the_kill_switch_stops_and_restarts() -> None:
    engaged = client.post("/killswitch/engage").json()
    assert engaged["engaged"] is True
    released = client.post("/killswitch/release").json()
    assert released["engaged"] is False


def test_the_metrics_endpoint_reports_the_five_metrics() -> None:
    payload = client.get("/metrics").json()
    names = {report["name"] for report in payload["reports"]}
    assert "search_breadth" in names
    assert "verification_catch_rate" in names
    assert payload["som"]["backend"]


def test_the_live_console_is_served() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "OS_V1" in response.text
    assert "EventSource" in response.text
