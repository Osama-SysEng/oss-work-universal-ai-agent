"""OS_V project — long-horizon work that survives closing the laptop.

A project = goal → milestones → ordered tasks, persisted as JSON after
EVERY task (crash = resume where it stopped, never from zero). Each task
runs through the full agent loop in its own workspace with the verify and
behavior gates; a failed task bounces once, then fails HONESTLY and the
project moves on with the failure on the record.

This is the difference between "an agent that does tasks" and "an agent
that builds systems": state that outlives any single run."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_MAX_TASKS_PER_CALL = 12        # a call does bounded work — resume continues


def _root() -> Path:
    d = Path(__file__).resolve().parent / "data" / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path(pid: str) -> Path:
    return _root() / f"{re.sub(r'[^a-zA-Z0-9_-]', '_', pid)[:40]}.json"


# ------------------------------------------------------------------- planning

def plan(goal: str, chain: list[dict], gw_stream) -> dict | None:
    """One planning call → validated structure. No chain / bad JSON / empty
    tasks → honest None (the endpoint degrades, never fakes a plan)."""
    if not chain:
        return None
    prompt = [{"role": "user", "content":
               "حلّل هذا الهدف إلى خطة تنفيذ. أجب بـ JSON فقط في كتلة "
               '```json``` بالشكل: {"name": "اسم المشروع", "milestones": '
               '[{"title": "عنوان مرحلة", "tasks": ["مهمة تنفيذية محددة '
               'بملفاتها", "..."]}]}\nالقواعد: كل مهمة قابلة للتنفيذ والتحقق '
               "(تنتج ملفات)، 2-4 مراحل، 1-3 مهام لكل مرحلة، بالترتيب "
               f"المنطقي.\nالهدف: {goal[:600]}"}]
    raw = ""
    for cfg in chain:
        try:
            raw = "".join(gw_stream(cfg, prompt, effort=None, timeout=120,
                                    max_tokens=2000)).strip()
            if raw:
                break
        except Exception:  # noqa: BLE001, S112 — next provider in the chain
            continue
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        name = str(obj.get("name", "")).strip()[:80] or "مشروع"
        ms = []
        for mi in obj.get("milestones", [])[:6]:
            if not isinstance(mi, dict):
                continue
            tasks = [str(t).strip()[:400] for t in mi.get("tasks", [])[:4]
                     if str(t).strip()]
            if tasks:
                ms.append({"title": str(mi.get("title", ""))[:100] or
                           f"المرحلة {len(ms)+1}",
                           "tasks": [{"desc": t, "status": "pending",
                                      "result": "", "attempts": 0}
                                     for t in tasks]})
        if not ms:
            return None
    except (json.JSONDecodeError, AttributeError):
        return None
    return {"name": name, "milestones": ms, "created": time.time()}


# ----------------------------------------------------------------- persistence

def save(pid: str, doc: dict) -> None:
    doc["updated"] = time.time()
    tmp = _path(pid).with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(_path(pid))


def load(pid: str) -> dict | None:
    p = _path(pid)
    if not p.is_file():
        return None
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return obj if isinstance(obj, dict) and obj.get("milestones") else None


def status(doc: dict) -> dict:
    tasks = [t for m in doc.get("milestones", []) for t in m.get("tasks", [])]
    return {"name": doc.get("name", ""),
            "tasks_total": len(tasks),
            "tasks_done": len([t for t in tasks if t["status"] == "done"]),
            "tasks_failed": len([t for t in tasks if t["status"] == "failed"]),
            "tasks_pending": len([t for t in tasks if t["status"] == "pending"]),
            "milestones": len(doc.get("milestones", []))}


# -------------------------------------------------------------------- running

def _flat(doc: dict) -> list[tuple[int, int, dict]]:
    """(mi, ti, task) in execution order — the project is a queue, not a
    metaphor."""
    out = []
    for mi, m in enumerate(doc.get("milestones", [])):
        for ti, t in enumerate(m.get("tasks", [])):
            out.append((mi, ti, t))
    return out


def run_project(pid: str, doc: dict, chain: list[dict], ws_root: Path,
                on_event, extra_tools: dict | None = None,
                memory_brief: str = "") -> dict:
    """Execute pending tasks until done or the per-call budget. Two passes:
    pass 1 runs fresh tasks; pass 2 re-runs the BOUNCED ones (a task that
    failed once gets exactly one retry — then fails honestly). Persists
    after every task; verifies every product; reports every failure. The
    workspace is the PROJECT's (all milestones share it, like a real repo),
    while each task's conversation is a session that can itself be resumed."""
    import osv_agent as ag
    import osv_team as tm

    ws = ws_root / re.sub(r"[^a-zA-Z0-9_-]", "_", pid)[:40]
    say = lambda evt: _safe_say(on_event, evt)
    executed = 0

    for pass_no in (1, 2):
        for mi, ti, task in _flat(doc):
            if task["status"] != "pending" or task.get("attempts", 0) >= pass_no:
                continue                        # done/failed, or not its pass
            if executed >= _MAX_TASKS_PER_CALL:
                say({"type": "status", "stage": "project",
                     "text": f"⏳ ميزانية هذه الجولة انتهت ({executed} مهمة) — "
                             "البقية تُستأنف بنداء جديد بنفس session_id"})
                doc["status"] = status(doc)
                save(pid, doc)
                return doc
            executed += 1
            task["attempts"] = task.get("attempts", 0) + 1
            say({"type": "status", "stage": "project",
                 "text": f"📋 [{doc['milestones'][mi]['title']}] مهمة {ti+1}"
                         + (" (إعادة)" if pass_no == 2 else "")
                         + f": {task['desc'][:90]}"})

            sid = f"{pid}_m{mi}_t{ti}"
            ctx = ag.AgentContext(ws, sid, extra_tools=extra_tools)
            ctx.chain = chain
            t0 = time.time()
            final, ok = ag.run_agent(task["desc"], ctx, chain, say,
                                     memory_brief=memory_brief)

            # verify gates on the project workspace, scoped to this task's window
            if ok:
                errs = tm.ws_py_errors(ws, since=t0)
                if errs:
                    say({"type": "status", "stage": "project",
                         "text": f"⚠️ بوابة التحقق اصطادت {len(errs)} خطأ في "
                                 "مهمة المشروع — إعادة واحدة"})
                    ok = False
            if ok:
                berrs = tm.ws_behavior_errors(ws, since=t0)
                if berrs:
                    say({"type": "status", "stage": "project",
                         "text": "🧪 بوابة السلوك اصطادت اختباراً فاشلاً — "
                                 "إعادة واحدة"})
                    ok = False

            if not ok and task["attempts"] < 2:
                task["result"] = (final or "بلا مخرج")[:200]
                task["status"] = "pending"      # pass 2 gives it its one retry
                save(pid, doc)
                continue
            task["status"] = "done" if ok else "failed"
            task["result"] = (final or "بلا مخرج")[:400]
            save(pid, doc)
            say({"type": "status", "stage": "project",
                 "text": f"{'✅' if ok else '❌'} مهمة {ti+1}: "
                         f"{task['status']} — {task['result'][:80]}"})

    doc["status"] = status(doc)
    save(pid, doc)
    return doc


def _safe_say(fn, evt):
    try:
        fn(evt)
    except Exception:  # noqa: BLE001, S110 — UI hiccups never kill a project
        pass
