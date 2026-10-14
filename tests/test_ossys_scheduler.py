"""OS scheduler + store: persistent background jobs (isolated tmp DB)."""

import time

import pytest

from ossys import scheduler, store


@pytest.fixture()
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("OSS_OS_DATA_DIR", str(tmp_path))
    path = store.init_db()
    return path


def test_init_and_submit(db):
    job = store.submit_job("hello")
    assert job["id"].startswith("job-")
    assert job["state"] == "queued"
    assert store.get_job(job["id"])["task"] == "hello"


def test_run_due_once_success(db):
    store.submit_job("do it")
    outcomes = scheduler.run_due_once(lambda t: {"status": "completed", "echo": t})
    assert len(outcomes) == 1 and outcomes[0]["ok"] is True
    assert store.get_job(outcomes[0]["job"]["id"])["state"] == "completed"
    assert len(store.recent_runs()) == 1


def test_run_due_once_failure_and_future(db):
    store.submit_job("boom")
    store.submit_job("later", run_at=time.time() + 3600)
    outcomes = scheduler.run_due_once(lambda t: 1 / 0)
    assert len(outcomes) == 1 and outcomes[0]["ok"] is False
    assert store.get_job(outcomes[0]["job"]["id"])["state"] == "failed"


def test_repeating_job_reschedules(db):
    job = store.submit_job("tick", interval_s=60, repeat=True)
    outcomes = scheduler.run_due_once(lambda t: {"status": "completed"})
    assert outcomes[0]["ok"] is True
    again = store.get_job(job["id"])
    assert again["state"] == "scheduled"
    assert again["runs"] == 1
    assert scheduler.run_due_once(lambda t: {"status": "completed"}) == []


def test_skills_registry(db):
    store.save_skill("demo", "demo skill", "/tmp/demo.md")
    assert [s["name"] for s in store.list_skills()] == ["demo"]
