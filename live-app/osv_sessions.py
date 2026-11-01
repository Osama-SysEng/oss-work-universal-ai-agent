"""OS_V sessions — resume work where you left it.

The killer gap vs stateless loops: the agent crashed or the user closed the
tab at step 20 of 24 — with sessions, the next call with resume=true picks
up the FULL transcript and the same workspace, instead of starting over.

Storage: data/agent_sessions/<id>.json — one file per session (msgs are
small JSON; workspace files stay where they are, referenced by path).
Honesty: load of a missing session returns None — the caller says "no saved
session, starting fresh" instead of pretending it resumed."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

# سقف السياق: آخر 60 رسالة تكفي الذاكرة العاملة — التجاوز يضر التركيز والكلفة
MAX_MSGS = 60


def _root() -> Path:
    return Path(__file__).resolve().parent / "data" / "agent_sessions"


def _safe(sid: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", sid or "")[:60]
    if not clean:
        raise ValueError("معرّف جلسة فارغ بعد التنظيف")
    return clean


def save(session_id: str, task: str, msgs: list[dict],
         workspace: str | Path) -> Path:
    """Persist one agent run's transcript (the msgs list is the live object —
    saved as-is so the next resume continues the exact conversation)."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    doc = {"session_id": _safe(session_id), "task": task,
           "workspace": str(workspace), "updated": time.time(),
           "turns": len(msgs), "msgs": msgs[-MAX_MSGS:]}
    p = root / f"{_safe(session_id)}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)                      # atomic on the same volume
    return p


def load(session_id: str) -> dict | None:
    """The saved doc (msgs already trimmed to the ceiling), or None honestly."""
    p = _root() / f"{_safe(session_id)}.json"
    if not p.is_file():
        return None
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("msgs"), list):
        return None
    doc["msgs"] = [m for m in doc["msgs"]
                   if isinstance(m, dict) and m.get("role") in
                   ("user", "assistant") and isinstance(m.get("content"), str)]
    doc["msgs"] = doc["msgs"][-MAX_MSGS:]
    return doc or None


def resume_msgs(session_id: str) -> list[dict] | None:
    """Prior conversation for run_agent(prior_msgs=...) — the stale system
    message is dropped (a fresh one is composed for the new task); None when
    there is nothing to resume from."""
    doc = load(session_id)
    if not doc or not doc["msgs"]:
        return None
    msgs = doc["msgs"]
    if msgs and msgs[0].get("role") == "system":
        msgs = msgs[1:]
    return msgs or None


def list_sessions() -> list[dict]:
    """Newest first — what the UI shows before the user says 'كمل'."""
    root = _root()
    if not root.is_dir():
        return []
    out = []
    for p in root.glob("*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            out.append({"session_id": doc.get("session_id", p.stem),
                        "task": (doc.get("task") or "")[:90],
                        "turns": doc.get("turns", 0),
                        "updated": doc.get("updated", 0)})
        except (json.JSONDecodeError, OSError):
            continue                      # a damaged file is skipped, not fatal
    return sorted(out, key=lambda d: -d["updated"])
