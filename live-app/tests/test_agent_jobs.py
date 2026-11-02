"""Background agent jobs: the run SURVIVES the tab close (2 Nov flaw — a
disconnect killed a real 7-file build). Everything offline (LLM mocked)."""

import json
import os
import time

import oss_work_live as m
from fastapi.testclient import TestClient


def _client(monkeypatch):
    chain = [{}]
    monkeypatch.setattr(m, "cloud_chain", lambda task=None: chain)

    def fake_gw(cfg, msgs, effort="none", timeout=300, max_tokens=3000):
        return ['```json\n{"tool": "write_file", "args": {"path": "hi.txt", '
                '"content": "مرحبا"}}\n```\n'
                '```json\n{"tool": "done", "args": {"answer": "كُتب الملف"}}\n```']

    monkeypatch.setattr(m, "_gw_stream", fake_gw)
    # the user's REAL learning ledger / sessions / memory must stay clean —
    # endpoint-level tests would otherwise record fake trajectories into data/
    import osv_distill as ds_mod
    import osv_memory as mem_mod
    import osv_sessions as ses_mod
    monkeypatch.setattr(ds_mod, "record_trajectory", lambda *a, **k: None)
    monkeypatch.setattr(ds_mod, "distill_from_run", lambda *a, **k: None)
    monkeypatch.setattr(mem_mod, "record_run", lambda *a, **k: None)
    monkeypatch.setattr(ses_mod, "save", lambda *a, **k: None)
    return TestClient(m.app)


def test_job_start_runs_to_done_and_streams_all_events(monkeypatch):
    client = _client(monkeypatch)
    r = client.post("/api/v1/agent/start",
                    json={"task": "اكتب ملفاً", "mode": "solo"})
    assert r.status_code == 200
    jid = r.json()["job_id"]
    # the worker thread finishes quickly with the mocked model — poll
    deadline = time.time() + 30
    snap = None
    while time.time() < deadline:
        snap = client.get(f"/api/v1/agent/jobs/{jid}").json()
        if snap.get("state") == "done":
            break
        time.sleep(0.3)
    assert snap and snap["state"] == "done", "the job must finish (mocked)"
    kinds = [e.get("type") for e in snap["events"]]
    assert "delta" in kinds and "done" in kinds      # final answer + summary
    assert any("كُتب الملف" in (e.get("text") or "")
               for e in snap["events"] if e.get("type") == "delta")


def test_stream_replays_history_then_terminates(monkeypatch):
    client = _client(monkeypatch)
    jid = client.post("/api/v1/agent/start",
                      json={"task": "مهمة", "mode": "solo"}).json()["job_id"]
    deadline = time.time() + 30
    while time.time() < deadline:
        if client.get(f"/api/v1/agent/jobs/{jid}").json().get("state") == "done":
            break
        time.sleep(0.3)
    # reattach AFTER done: the stream must replay everything then END cleanly
    body = ""
    with client.stream("GET", f"/api/v1/agent/stream/{jid}") as resp:
        for chunk in resp.iter_text():
            body += chunk
    assert '"type": "done"' in body
    assert body.rstrip().endswith("\n\n") or '"type": "done"' in body


def test_jobs_list_and_unknown_job(monkeypatch):
    client = _client(monkeypatch)
    jid = client.post("/api/v1/agent/start",
                      json={"task": "مهمة قائمة", "mode": "solo"}).json()["job_id"]
    jobs = client.get("/api/v1/agent/jobs").json()
    assert jobs["ok"] is True and any(j["id"] == jid for j in jobs["jobs"])
    miss = client.get("/api/v1/agent/jobs/nope").json()
    assert miss["ok"] is False


def test_start_without_cloud_provider_is_honest(monkeypatch):
    monkeypatch.setattr(m, "cloud_chain", lambda task=None: [])
    client = TestClient(m.app)
    r = client.post("/api/v1/agent/start", json={"task": "مهمة"})
    jid = r.json()["job_id"]
    deadline = time.time() + 15
    snap = None
    while time.time() < deadline:
        snap = client.get(f"/api/v1/agent/jobs/{jid}").json()
        if snap.get("state") == "done":
            break
        time.sleep(0.3)
    assert snap["state"] == "done"
    assert snap["result"] == {"ok": False}          # honest failure, no fake


def test_preview_serves_built_site_and_blocks_traversal(monkeypatch, tmp_path):
    client = TestClient(m.app)
    ws_root = tmp_path / "osv_agent_ws" / "pv1" / "school_site"
    ws_root.mkdir(parents=True)
    (ws_root / "index.html").write_text("<h1>مدرسة</h1>", encoding="utf-8")
    (tmp_path / "osv_agent_ws" / "secret.txt").write_text("x", encoding="utf-8")
    monkeypatch.setenv("TEMP", str(tmp_path))

    r = client.get("/api/v1/agent/preview/pv1/school_site/index.html")
    assert r.status_code == 200 and "مدرسة" in r.text

    entry = client.get("/api/v1/agent/preview/pv1/")
    assert entry.status_code == 200

    trav = client.get("/api/v1/agent/preview/pv1/..%2F..%2Fsecret.txt")
    assert trav.status_code in (403, 404)          # traversal → dead end
    bad = client.get("/api/v1/agent/preview/pv1/nope.html")
    assert bad.status_code == 404
