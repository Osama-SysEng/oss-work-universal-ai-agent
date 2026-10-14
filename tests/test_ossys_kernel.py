"""OS kernel: boot honesty, real dispatch, strict local-only routing."""

import asyncio

import pytest

from ossys.kernel import Kernel


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("OSS_OS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OSS_OS_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("OSS_OS_WORKSPACE_DIR", str(tmp_path / "ws"))
    return tmp_path


def _dead_engine(monkeypatch):
    import core.services.local_engine as engine_mod

    class _Dead:
        def health(self):
            return False

    monkeypatch.setattr(engine_mod, "LocalEngine", _Dead)


def test_boot_degraded_honestly(isolated, monkeypatch):
    _dead_engine(monkeypatch)
    status = Kernel().boot()
    assert status["booted"] is True
    assert status["engine_ok"] is False
    assert "start-engine" in status["note"]


def test_boot_reports_engine_up(isolated, monkeypatch):
    import core.services.local_engine as engine_mod

    class _Up:
        def health(self):
            return True

    monkeypatch.setattr(engine_mod, "LocalEngine", _Up)
    status = Kernel().boot()
    assert status["engine_ok"] is True


def test_run_adhoc_uses_orchestrator(isolated):
    out = Kernel().run("summarize the weekly notes")
    assert out["status"] == "completed"
    assert out["data"]["subtasks_processed"] >= 1


def test_run_with_task_agent(isolated):
    out = Kernel().run("tidy the downloads folder", task_id="T042")
    assert out["status"] in ("completed", "failed")
    assert "elapsed_s" in out


def test_submit_and_drain(isolated):
    kernel = Kernel()
    job = kernel.submit("summarize the weekly notes")
    assert job["state"] == "queued"
    outcomes = kernel.run_background_once()
    assert len(outcomes) == 1 and outcomes[0]["ok"] is True


def test_strict_mode_skips_cloud(monkeypatch):
    """Strict routing must never attempt a cloud URL — all calls fail locally."""
    import httpx

    import core.services.model_router as router_mod

    requested: list[str] = []

    class _Recorder:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def _boom(self, url, *a, **k):
            requested.append(str(url))
            raise httpx.ConnectError("down")

        get = _boom
        post = _boom

    monkeypatch.setattr(httpx, "AsyncClient", _Recorder)
    monkeypatch.setenv("OSS_OS_STRICT", "true")
    monkeypatch.setenv("OSS_LOCAL_URL", "http://127.0.0.1:9")
    router = router_mod.ModelRouter()
    out = asyncio.run(router.complete("write python code for a web scraper"))
    assert out["status"] == "failed"
    assert requested, "expected local attempts"
    assert all("127.0.0.1" in u or "localhost" in u for u in requested), requested
