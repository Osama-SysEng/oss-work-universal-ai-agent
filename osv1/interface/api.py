"""The local API for OS_V1.

It binds to the loopback interface only. Every endpoint reflects a real
state of the system: the agent list comes from the registry, the memory from
the store, the audit from the hash-chained log, and the event stream from
the runtime itself.

The event stream is the source of the live console. Each event is a real
thing that happened — a plan being built, a tool running, a verification
finishing — so the animation in the interface can never show a state the
system is not in.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import queue
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from osv1.agents.registry import REGISTRY
from osv1.config import Settings
from osv1.runtime import OSRuntime

WEB_DIR = Path(__file__).parent / "web"


class EventBus:
    """Fans runtime events out to the connected interface clients."""

    def __init__(self, maxsize: int = 500) -> None:
        self._subscribers: list[queue.Queue[dict[str, Any]]] = []
        self._history: list[dict[str, Any]] = []
        self._maxsize = maxsize

    def publish(self, event: dict[str, Any]) -> None:
        self._history.append(event)
        if len(self._history) > self._maxsize:
            self._history = self._history[-self._maxsize :]
        for subscriber in list(self._subscribers):
            with contextlib.suppress(queue.Full):
                subscriber.put_nowait(event)

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=200)
        self._subscribers.append(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        if subscriber in self._subscribers:
            self._subscribers.remove(subscriber)

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        return self._history[-limit:]


BUS = EventBus()
RUNTIME = OSRuntime(settings=Settings.load(), sink=BUS.publish)


class TaskBody(BaseModel):
    task: str = Field(min_length=2, max_length=10_000)
    agent_id: str = Field(default="", max_length=16)


class GrantBody(BaseModel):
    scope: str = Field(min_length=2, max_length=32)
    target: str = Field(min_length=1, max_length=1024)
    readonly: bool = False


class RevokeBody(BaseModel):
    scope: str = Field(min_length=2, max_length=32)
    target: str = Field(default="")


class DecisionBody(BaseModel):
    approve: bool
    by: str = Field(default="user", max_length=64)


class ProvenanceBody(BaseModel):
    kind: str = Field(min_length=2, max_length=32)
    name: str = Field(min_length=1, max_length=200)
    origin: str = Field(min_length=1, max_length=1024)
    license: str = Field(default="unknown", max_length=200)
    version: str = Field(default="", max_length=64)
    notes: str = Field(default="", max_length=1000)


app = FastAPI(
    title="OSS Work / OS_V1 — local API",
    version="1.0.0",
    description=(
        "The local control surface of OS_V1. It runs on the loopback interface, needs no key, "
        "and never sends data out. The plan endpoint proposes; the build endpoint executes; "
        "the event stream shows what is really happening."
    ),
)


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "product": "OSS Work", "model": "OS_V1"}


@app.get("/status")
def status() -> dict[str, Any]:
    return RUNTIME.status()


@app.get("/")
def console() -> HTMLResponse:
    page = WEB_DIR / "index.html"
    if not page.is_file():
        raise HTTPException(status_code=500, detail="the live console files are missing")
    return HTMLResponse(page.read_text(encoding="utf-8"))


@app.post("/plan")
def plan(body: TaskBody) -> dict[str, Any]:
    result = RUNTIME.plan(body.task, agent_id=body.agent_id)
    return result.as_dict()


@app.post("/build")
def build(body: TaskBody) -> dict[str, Any]:
    result = RUNTIME.build(body.task, agent_id=body.agent_id)
    return result.as_dict()


@app.get("/agents")
def agents(limit: int = 50, offset: int = 0, domain: str = "", specialization: str = "") -> dict[str, Any]:
    selected = list(REGISTRY.all())
    if domain:
        selected = [agent for agent in selected if agent.domain.key == domain]
    if specialization:
        selected = [agent for agent in selected if agent.specialization.key == specialization]
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    return {
        "total": len(selected),
        "limit": limit,
        "offset": offset,
        "agents": [agent.as_dict() for agent in selected[offset : offset + limit]],
    }


@app.get("/agents/{agent_id}")
def agent_detail(agent_id: str) -> dict[str, Any]:
    agent = REGISTRY.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"no agent {agent_id}")
    return agent.as_dict()


@app.get("/events")
async def events(request: Request) -> StreamingResponse:
    """Stream the real runtime events to the interface."""

    async def generator():
        subscriber = BUS.subscribe()
        try:
            for event in BUS.recent(30):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.to_thread(subscriber.get, True, 10.0)
                except queue.Empty:
                    yield ": keep-alive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        finally:
            BUS.unsubscribe(subscriber)

    return StreamingResponse(generator(), media_type="text/event-stream")


@app.get("/memory")
def memory(kind: str = "", limit: int = 50) -> dict[str, Any]:
    entries = RUNTIME.memory.list(kind=kind or None, limit=max(1, min(500, limit)))
    return {"entries": [entry.as_dict() for entry in entries], "stats": RUNTIME.memory.stats()}


@app.post("/memory/export")
def memory_export() -> dict[str, Any]:
    return RUNTIME.memory.export()


@app.delete("/memory/{entry_id}")
def memory_delete(entry_id: int) -> dict[str, Any]:
    if not RUNTIME.memory.delete(entry_id):
        raise HTTPException(status_code=404, detail=f"no memory entry {entry_id}")
    return {"deleted": entry_id}


@app.get("/audit")
def audit(limit: int = 50) -> dict[str, Any]:
    return {"entries": RUNTIME.audit.recent(max(1, min(500, limit)))}


@app.get("/audit/verify")
def audit_verify() -> dict[str, Any]:
    return RUNTIME.audit.verify_chain()


@app.get("/permissions")
def permissions() -> dict[str, Any]:
    return {"grants": RUNTIME.permissions.list_grants()}


@app.post("/permissions/grant")
def permissions_grant(body: GrantBody) -> dict[str, Any]:
    grant = RUNTIME.permissions.grant(body.scope, body.target, readonly=body.readonly)
    return grant.as_dict()


@app.post("/permissions/revoke")
def permissions_revoke(body: RevokeBody) -> dict[str, Any]:
    removed = RUNTIME.permissions.revoke(body.scope, body.target or None)
    return {"removed": removed}


@app.get("/approvals")
def approvals() -> dict[str, Any]:
    return {"pending": [request.as_dict() for request in RUNTIME.approvals.pending()]}


@app.post("/approvals/{approval_id}/decide")
def approvals_decide(approval_id: str, body: DecisionBody) -> dict[str, Any]:
    request = RUNTIME.approvals.decide(approval_id, approve=body.approve, by=body.by)
    if request is None:
        raise HTTPException(status_code=404, detail=f"no approval {approval_id}")
    return request.as_dict()


@app.post("/killswitch/engage")
def killswitch_engage() -> dict[str, Any]:
    RUNTIME.kill_switch.engage()
    return RUNTIME.kill_switch.status()


@app.post("/killswitch/release")
def killswitch_release() -> dict[str, Any]:
    released = RUNTIME.kill_switch.release()
    return {"released": released, **RUNTIME.kill_switch.status()}


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    return {"reports": RUNTIME.metrics.as_reports(), "som": RUNTIME.som.stats()}


@app.get("/metrics/cascade")
def metrics_cascade() -> dict[str, Any]:
    """The dual-process cascade of section 27.6, measured on this runtime."""
    return RUNTIME.cascade.report()


@app.get("/catalog")
def catalog() -> dict[str, Any]:
    return REGISTRY.catalog()


@app.get("/provenance")
def provenance() -> dict[str, Any]:
    """What the system uses, and under which licence."""
    return RUNTIME.provenance.report()


@app.post("/provenance")
def provenance_add(body: ProvenanceBody) -> dict[str, Any]:
    record = RUNTIME.provenance.add(
        body.kind,
        body.name,
        body.origin,
        license=body.license,
        version=body.version,
        notes=body.notes,
    )
    return record.as_dict()


@app.get("/context")
def context_status() -> dict[str, Any]:
    """The context window of this device tier."""
    settings = RUNTIME.settings
    return {
        "tier": settings.tier,
        "window_tokens": settings.context_tokens,
        "estimate": "four characters per token, for mixed English and Arabic text",
    }


@app.get("/qualities")
def qualities() -> dict[str, Any]:
    """The thirteen qualities, their laws, their rules, and their tests."""
    from osv1.quality.qualities import catalog

    return catalog()


@app.get("/qualities/report")
def qualities_report() -> dict[str, Any]:
    """What is measured today, and what is still a target."""
    from osv1.eval.harness import Harness

    return Harness(project_root=Path.cwd()).quality_report()


def main() -> None:
    import uvicorn

    settings = Settings.load()
    print(f"OS_V1 local API on http://{settings.api_host}:{settings.api_port} — the live console is at /")
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="info")


if __name__ == "__main__":
    main()
