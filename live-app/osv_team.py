"""OS_V Team — parallel sub-agent orchestration (the productivity multiplier).

SOLO agent = one sequential loop (LLM step → tools → observe → repeat).
Decomposable builds waste that: 3 independent files could build CONCURRENTLY.

Clean-room port of the orchestrator-worker pattern (opencode subagents /
Anthropic task tool spirit): ONE decomposition call → N worker agents, each
with its OWN confined workspace + tools + honest loop → merge call →
server-side verify gate (py_compile) with ONE bounded heal round per worker.

HONESTY LAW: decomposition failure or a single-stream verdict falls back to
the solo loop ANNOUNCED — a team is never faked. Worker failures surface in
the merged report verbatim (the merge model cannot hide them: server appends
any worker final carrying ⚠️/فشل if the merged text lacks them).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

MAX_STREAMS = 4
WORKER_STEPS = 12          # each worker is bounded — a team must converge
_HEAL_ROUNDS = 1

_DECOMPOSE_PROMPT = (
    "أنت مهندس قيادة يوزع العمل على فريق وكلاء متوازيين. قسّم المهمة التالية "
    "إلى 2-{max} مسارات عمل مستقلة تماماً: كل مسار يُنجز وحده بلا انتظار غيره، "
    "وممنوع أن يعدّل مساران نفس الملف. حدد في كل مسار مهاماً كاملة واضحة بذاتها "
    "(المسار لا يرى المهمة الأصلية ولا مسارات أخرى).\n\n"
    "المهمة:\n{task}\n\n"
    "أعد JSON فقط بهذا الشكل بالضبط (بلا أي نص خارج الكود):\n"
    '{{"streams": [{{"name": "اسم-لاتيني-قصير", "task": "المهمة الكاملة للمسار", '
    '"files": ["أسماء_الملفات_التي_سينتجها_هذا_المسار"]}},'
    ' ...]}}\n'
    "وإن كانت المهمة بسيطة لا تُقسم عملياً إلى عمل متوازٍ حقيقي، أعد: "
    '{{"streams": []}}')


_MERGE_PROMPT = (
    "أنت قائد الفريق. عمل كل وكيلاً من فريقك وانتهى؛ تقاريرهم الحقيقية أدناه. "
    "اكتب للمستخدم تقريراً نهائياً واحداً بالعربية: ما أُنجز فعلاً، مسارات كل "
    "ملف نُتج حرفياً، وأي تحذير (⚠️) أو فشل يُروى كما هو — منعٌ باتاً إخفاء "
    "عطل أو ادعاء عمل لم يُجرَ.\n\n"
    "الملفات الموجودة فعلياً على القرص (لا تدّعي ملفاً خارجها ولا تنقص منها):\n{files}\n\n{reports}")


def ws_behavior_errors(ws: Path, since: float = 0.0) -> list[str]:
    """Behavioral verify gate: test files written this run are EXECUTED.
    Compiling-but-wrong code used to pass the syntax gate — behavior is the
    real truth. Returns one entry per failing test file (stderr tail).
    المصدر هو الحقيقة: __pycache__ يُمسح قبل الحكم — إصلاح بنفس الحجم
    وبنفس الثانية كان يقرأ كاشاً قديماً فينجّي المنطق الخاطئ (قياس حي)."""
    for cache in list(ws.rglob("__pycache__")):
        import shutil
        shutil.rmtree(cache, ignore_errors=True)
    errs = []
    pats = ("test_*.py", "*_test.py")
    seen = set()
    for pat in pats:
        for tf in sorted(ws.rglob(pat)):
            if tf in seen:
                continue
            seen.add(tf)
            try:
                if since and tf.stat().st_mtime < since - 5:
                    continue
            except OSError:
                continue
            try:
                r = subprocess.run([sys.executable, str(tf)], cwd=str(ws),
                                   capture_output=True, timeout=120, check=False)
                if r.returncode:
                    tail = r.stdout.decode("utf-8", "replace").strip()[-250:]
                    tail += " || " + r.stderr.decode("utf-8", "replace").strip()[-250:]
                    errs.append(f"{tf.name}: {tail}")
            except Exception as exc:  # noqa: BLE001 — gate must never crash serving
                errs.append(f"{tf.name}: {type(exc).__name__}: {exc}")
    return errs


def _chat(chain: list[dict], msgs: list[dict], max_tokens: int = 2500) -> str:
    """One LLM call through the provider chain (same order/fallback as the loop)."""
    import oss_work_live as m
    for cfg in chain:
        try:
            reply = "".join(m._gw_stream(cfg, msgs, effort="low",
                                         timeout=300, max_tokens=max_tokens)).strip()
            if reply:
                return reply
        except Exception:  # noqa: BLE001, S112 — next provider in the chain
            continue
    return ""


def _json_obj(text: str) -> dict | None:
    mm = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not mm:
        return None
    try:
        obj = json.loads(mm.group(0))
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def decompose(task: str, chain: list[dict]) -> list[dict] | None:
    """Split into independent streams. [] = honestly not decomposable.
    None = the decomposition call itself failed (caller announces + goes solo)."""
    reply = _chat(chain, [{"role": "user", "content":
                           _DECOMPOSE_PROMPT.format(task=task, max=MAX_STREAMS)}],
                  max_tokens=1200)
    if not reply:
        return None
    obj = _json_obj(reply)
    if obj is None or not isinstance(obj.get("streams"), list):
        return None
    streams = []
    for st in obj["streams"][:MAX_STREAMS]:
        if (isinstance(st, dict) and str(st.get("name", "")).strip()
                and str(st.get("task", "")).strip()):
            fl = st.get("files")
            files = ([re.sub(r"[^a-zA-Z0-9_./-]", "", str(f))[:60]
                      for f in fl if str(f).strip()]
                     if isinstance(fl, list) else [])
            streams.append({"name": re.sub(r"[^a-zA-Z0-9_-]", "",
                                           str(st["name"]))[:20] or "w",
                            "task": str(st["task"]).strip(),
                            "files": files})
    return streams


def ws_py_errors(ws: Path, since: float = 0.0) -> list[str]:
    """Server-side verify gate: every .py in the workspace must compile.
    Real check with local tools (ms, no model) — same spirit as _verify_project.
    since: افحص الملفات المكتوبة بعد هذه اللحظة فقط (الجلسة تعيد استخدام المساحة
    — ملف قديم من جولة سابقة لا يُفشل الجولة الحالية)."""
    errs = []
    for py in sorted(ws.rglob("*.py")):
        try:
            if since and py.stat().st_mtime < since - 5:
                continue
        except OSError:
            continue
        try:
            r = subprocess.run([sys.executable, "-m", "py_compile", str(py)],
                               capture_output=True, timeout=90, check=False)
            if r.returncode:
                detail = r.stderr.decode("utf-8", "replace").strip()[-400:]
                errs.append(f"{py.name}: {detail}")
        except Exception as exc:  # noqa: BLE001 — gate must never crash serving
            errs.append(f"{py.name}: {type(exc).__name__}: {exc}")
    return errs


def _real_files(root_ws: Path) -> str:
    """قائمة الملفات الحقيقية (بلا كاش الترجمة) — الدمج لا يدّعي غيرها."""
    return "\n".join(sorted(
        str(w.relative_to(root_ws)) for w in root_ws.rglob("*")
        if w.is_file() and "__pycache__" not in w.parts
        and w.suffix != ".pyc")) or "(لا ملفات)"


def run_team(task: str, root_ws: Path, session_id: str, chain: list[dict],
             extra_tools: dict, on_event, memory_brief: str = "",
             max_workers: int = MAX_STREAMS):
    """Run decomposed streams CONCURRENTLY, verify, heal, merge.
    Returns (merged_final, ok, info) — or None when the task is not
    decomposable (caller falls back to the solo loop, announced)."""
    import osv_agent as ag

    def say(evt):
        try:
            on_event(evt)
        except Exception:  # noqa: BLE001, S110 — UI hiccups never kill the team
            pass

    streams = decompose(task, chain)
    if streams is None:
        say({"type": "status", "stage": "team",
             "text": "تعذر التفكيك — أنفذ المهمة solo بصدق"})
        return None
    if len(streams) < 2:
        say({"type": "status", "stage": "team",
             "text": "المهمة لا تُقسم عملياً — solo هو الأسرع لها"})
        return None

    say({"type": "status", "stage": "team",
         "text": f"👥 سرب من {len(streams)} وكلاء انطلق بالتوازي: "
                 + "، ".join(s["name"] for s in streams)})
    t0 = time.time()

    workers = []          # (stream, ctx, final, ok)
    with ThreadPoolExecutor(max_workers=max(2, max_workers)) as pool:
        futs = {}
        for st in streams:
            wws = root_ws / "team" / st["name"]
            wctx = ag.AgentContext(wws, f"{session_id}::{st['name']}",
                                   extra_tools=extra_tools)
            fut = pool.submit(ag.run_agent, st["task"], wctx, chain,
                              lambda e: None, memory_brief, WORKER_STEPS, 1)
            futs[fut] = (st, wctx)
        for fut in as_completed(futs):
            st, wctx = futs[fut]
            try:
                wfinal, wok = fut.result()
            except Exception as exc:  # noqa: BLE001 — a dead worker is a fact
                wfinal, wok = f"توقف الوكيل باستثناء: {type(exc).__name__}: {exc}", False
            workers.append((st, wctx, wfinal, wok))
            say({"type": "status", "stage": "team",
                 "text": f"[{st['name']}] {'اكتمل' if wok else 'فشل/غير مكتمل'} "
                         f"({len(wctx.steps)} خطوة) — "
                         f"{round(time.time() - t0)} ث"})

    # verify gate per worker workspace + ONE bounded heal round (real accuracy)
    # (indexed: النتائج تُثبَّت في القائمة — جولات الإصلاح يجب أن تصل لتقرير الدمج)
    for wi, (st, wctx, wfinal, wok) in enumerate(workers):
        errs = ws_py_errors(wctx.workspace)
        healed = False
        if errs:
            say({"type": "status", "stage": "team",
                 "text": f"⚠️ [{st['name']}] بوابة التحقق اصطادت {len(errs)} خطأ — جولة إصلاح"})
            hfinal, _hok2 = ag.run_agent(
                "أصلح أخطاء التركيب التالية في ملفات مساحة عملك، ثم أعد الفحص "
                "بنفسك قبل أن تعلن الانتهاء:\n" + "\n".join(errs[:5]),
                wctx, chain, lambda e: None, memory_brief, WORKER_STEPS, 1)
            if hfinal:
                wfinal = (wfinal + "\n\n[جولة الإصلاح]: " + hfinal)[:8000]
            errs2 = ws_py_errors(wctx.workspace)
            healed = not errs2
            if errs2:
                wfinal += ("\n\n⚠️ ما زالت أخطاء التركيب قائمة بعد الإصلاح: "
                           + " | ".join(e[:150] for e in errs2[:3]))

        # behavioral gate: الاختبارات المكتوبة تُشغَّل فعلاً — كود يُترجم
        # ونتيجته خاطئة كان يمرّ بلا مساءلة، والآن يُصطاد ويُصلح منطقه
        berrs = ws_behavior_errors(wctx.workspace) if not errs else []
        if berrs:
            say({"type": "status", "stage": "team",
                 "text": f"🧪 [{st['name']}] بوابة السلوك اصطادت اختباراً "
                         f"فاشلاً — إصلاح المنطق..."})
            bfinal, _bok = ag.run_agent(
                "بوابة السلوك اصطادت اختبارات فاشلة في مساحة عملك — الكود "
                "يُترجم لكن المنطق خاطئ. أصلح المنطق حتى تنجح الاختبارات فعلاً "
                "وشغّلها بنفسك للتأكد:\n" + "\n".join(berrs[:3]),
                wctx, chain, lambda e: None, memory_brief, WORKER_STEPS, 1)
            if bfinal:
                wfinal = (wfinal + "\n\n[إصلاح السلوك]: " + bfinal)[:8000]
            berrs2 = ws_behavior_errors(wctx.workspace)
            if berrs2:
                wfinal += ("\n\n⚠️ اختبارات ما زالت تفشل بعد إصلاح السلوك: "
                           + " | ".join(e[:200] for e in berrs2[:2]))
            else:
                healed = True

        info = {"name": st["name"], "ok": wok, "steps": len(wctx.steps),
                "ok_steps": len([s for s in wctx.steps if s.get("ok")]),
                "tools": [s["tool"] for s in wctx.steps][:12],
                "healed": healed, "py_errors": len(errs),
                "test_errors": len(berrs)}

        # deliverables contract: الملفات الموعودة في خطة التفكيك تُمسح على
        # القرص — الوعد بلا منتج زور يُفصح عنه إلزاماً
        missing = [f for f in st.get("files", []) if f
                   and not list(wctx.workspace.glob(f"**/{f}"))]
        if missing:
            wfinal += ("\n\n⚠️ ملفات وُعدت في خطة الفريق لم تُنتَج فعلاً: "
                       + ", ".join(missing[:5]))
            wok = False
            info["missing_files"] = missing
        info["ok"] = wok
        st["info"] = info
        workers[wi] = (st, wctx, wfinal, wok)

    reports = "\n\n".join(
        f"=== تقرير الوكيل [{st['name']}] ({'نجح' if wok else 'فشل/غير مكتمل'}) ===\n"
        f"{wfinal}" for st, _c, wfinal, wok in workers)
    merged = _chat(chain, [{"role": "user",
                            "content": _MERGE_PROMPT.format(
                                reports=reports,
                                files=_real_files(root_ws))}],
                   max_tokens=2500)
    if not merged:
        merged = reports[:4000]   # honest: the raw truth beats a fake summary

    # honesty is NOT delegated to the merge model: any worker failure the
    # merged text hides gets appended verbatim (same law as the solo loop)
    if "⚠️" not in merged and "فشل" not in merged:
        for st, _c, wfinal, wok in workers:
            if not wok or "⚠️" in wfinal or "فشل" in wfinal:
                merged += (f"\n\n[ملاحظة النظام — إلزامية] وكيل [{st['name']}]: "
                           + wfinal[:600])

    files = [str(w.relative_to(root_ws)) for w in root_ws.rglob("*")
             if w.is_file() and "__pycache__" not in w.parts and w.suffix != ".pyc"]
    files.sort()
    ok = all(wok for _s, _c, _f, wok in workers)
    say({"type": "status", "stage": "team",
         "text": f"👥 السرب اكتمل: {sum(1 for s in streams if s.get('info', {}).get('ok'))}"
                 f"/{len(streams)} وكلاء نجحوا، {len(files)} ملفاً في "
                 f"{round(time.time() - t0)} ث"})
    return merged, ok, {"streams": [s.get("info") for s in streams],
                        "files": files, "seconds": round(time.time() - t0)}


def team_tool():
    """The solo agent's self-service: it may call team_spawn when IT decides
    a task is decomposable. Nested workers never see this tool (no recursion)."""
    import osv_team as tm

    def _spawn(ctx, streams=None, **a):
        chain = getattr(ctx, "chain", None)
        if not chain:
            return False, "لا سلسلة مزودين في السياق — الفريق يحتاج مزوداً سحابياً"
        if not isinstance(streams, list) or len(streams) < 2:
            return False, ("مرر streams كقائمة من 2-4 كائنات "
                           "[{name, task}] — مسارات مستقلة فعلاً")
        streams = [{"name": str(s.get("name", f"w{i}")), "task": str(s.get("task", ""))}
                   for i, s in enumerate(streams[:tm.MAX_STREAMS])
                   if isinstance(s, dict)]
        if len(streams) < 2:
            return False, "مسارات غير صالحة — كل مسار يحتاج name و task"
        # reuse the engine on THIS workspace (workers get sub-dirs)
        res = tm.run_team(
            "نفذ المسارات التالية كفريق: " + json.dumps(streams, ensure_ascii=False),
            ctx.workspace, ctx.session_id, chain,
            {k: v for k, v in ctx.tools.items() if k != "team_spawn"},
            lambda e: None, "", max_workers=tm.MAX_STREAMS)
        if res is None:
            return False, "المسارات لم تُقسم — نفذها solo"
        merged, ok, info = res
        return ok, (f"السرب اكتمل ({info['seconds']} ث): "
                    + json.dumps(info["streams"], ensure_ascii=False)[:400]
                    + "\n" + merged[:4000])

    return {"team_spawn": {
        "fn": _spawn,
        "args": {"streams": "list[{name, task}] مسارات مستقلة 2-4 لا يشارك اثنان ملفاً"},
        "desc": "أطلق سرب وكلاء متوازيين: كل مسار وكيل مستقل بأدوات كاملة يعمل آنياً — استخدمه للمشاريع متعددة الأجزاء المستقلة (مثلاً: backend + frontend + اختبارات) لتقسيم الزمن الكلي. لا تستخدمه لمهام بسيطة أو المتسلسلة الاعتمادية"},
    }
