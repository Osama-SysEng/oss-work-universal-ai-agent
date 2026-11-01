"""OS_V Agent — a real tool-executing agent loop for OSS Work.

Capability ported clean-room from the live opencode architecture
(sst/opencode, MIT) + the skills/persistent-memory concepts Hermes Agent
advertises (docs-only repo — design inspiration, not code).

Core pieces:
- Tool registry: bash, read_file, write_file, list_dir, glob, grep,
  web_search, web_fetch, skill — each with an exact schema the model sees.
- Confinement: every filesystem path is resolved inside a per-run workspace;
  bash runs with an empty environment, confined cwd, hard timeout, and a
  destructive-pattern denylist (lesson 18).
- The loop (in osv_agent_loop below / agent endpoint): the model emits ONE
  JSON action per turn, the tool result is fed back verbatim as observation,
  up to MAX_STEPS iterations, then an honest final answer. Text protocol on
  purpose: it works identically across gemini / freellmapi / local engine —
  no provider-specific function-calling dependence.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

MAX_STEPS = 24          # رأسية للمشاريع الكبيرة (كانت 14 — البناء الواسع يحتاج دورات أكثر)
TOOL_TIMEOUT_S = 60
BASH_TIMEOUT_S = 45
MAX_OBS_CHARS = 6000
MAX_FILE_CHARS = 12000

# Destructive patterns — never run, even inside the workspace (lesson 18).
# Includes what Crush hard-blocks regardless of permissions: global package
# installs (bash.go:180-195) — plus the copy-whole-toolchain disaster we
# actually caught a model doing (165MB xcopy of site-packages into the ws).
_BASH_DENY = re.compile(
    r"\b(rm\s+-rf\s+[/~]|\bformat\b|\bdel\s+/[sq]|shutdown|taskkill\s+/f\s+/im\s+"
    r"|reg\s+delete|rmdir\s+/s|Remove-Item\s+-Recurse\s+-Force\s+C:\\|mkfs|dd\s+if="
    r"|\bxcopy\b|\brobocopy\b|Copy-Item\s+-Recurse|\bcp\s+-[a-z]*r[a-z]*\s+[A-Za-z]:\\\\"
    r"|\binstall\s+-g\b|npm\s+install\s+-g|pip\s+install\s+--user|pip\s+install\s+.*--target"
    r"|python\s+-m\s+pip\s+install\s+--user"
    r"|^py\s+install\s|\bpy\s+install\b|\bpymanager\b|\bpython\s+install\b)",
    re.IGNORECASE)

# Environment given to every bash child: empty except what builds need.
# CAUTION (real incident): stripping LOCALAPPDATA/APPDATA makes pymanager's
# runtime-installer fall back to CWD — it installed a full Python 3.15
# (172MB) INSIDE the agent workspace. These vars are not secrets; they are
# load-bearing paths.
_BASH_ENV = {
    "PATH": os.environ.get("PATH", ""),
    "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
    "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
    "TEMP": os.environ.get("TEMP", ""),
    "TMP": os.environ.get("TMP", ""),
    "LOCALAPPDATA": os.environ.get("LOCALAPPDATA", ""),
    "APPDATA": os.environ.get("APPDATA", ""),
    "USERPROFILE": os.environ.get("USERPROFILE", ""),
    "PYTHONIOENCODING": "utf-8",
}


class AgentContext:
    """One agent run: its workspace and the transcript of tool results.
    extra_tools: device-level tools (osv_device) merged over the base registry
    — they reach the REAL machine, gated by the permission engine."""

    def __init__(self, workspace: Path, session_id: str,
                 extra_tools: dict | None = None):
        self.workspace = workspace
        self.session_id = session_id
        self.steps: list[dict] = []          # audit trail: tool, args, ok, ms
        self.chain: list[dict] | None = None  # provider chain (team_spawn reads it)
        self.tools: dict = dict(TOOLS)
        if extra_tools:
            self.tools.update(extra_tools)
        workspace.mkdir(parents=True, exist_ok=True)

    # -- confinement ------------------------------------------------------
    def resolve(self, rel: str) -> Path | None:
        """Resolve a path INSIDE the workspace, or None if it escapes."""
        if not rel or not str(rel).strip():
            return None
        p = (self.workspace / rel).resolve()
        try:
            p.relative_to(self.workspace.resolve())
        except ValueError:
            return None
        return p


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [{len(text) - limit} حرفاً اقتُطعت]"


# ---------------------------------------------------------------------------
# Tools — each returns (ok: bool, observation: str)
# ---------------------------------------------------------------------------

def tool_bash(ctx: AgentContext, command: str) -> tuple[bool, str]:
    if _BASH_DENY.search(command or ""):
        return False, "أمر مرفوض: نمط مدمّر مكتشف (حد أمان OSS)"
    argv = ["cmd", "/c", command] if os.name == "nt" else ["bash", "-c", command]
    try:
        p = subprocess.run(argv, cwd=str(ctx.workspace), env=_BASH_ENV, check=False,
                           capture_output=True, text=True, timeout=BASH_TIMEOUT_S,
                           encoding="utf-8", errors="replace")
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        obs = f"exit={p.returncode}"
        if out:
            obs += f"\nstdout:\n{out}"
        if err:
            obs += f"\nstderr:\n{err}"
        # bloat guard: a runaway command must be visible to the model at once
        try:
            total = sum(f.stat().st_size for f in ctx.workspace.rglob("*") if f.is_file())
            if total > 80_000_000:
                obs += (f"\n⚠️ مساحة العمل تضخمت إلى {total // 1_000_000}MB — "
                        "نظّف ما لا تحتاجه فوراً، ممنوع تثبيت/نسخ بئر تثبيت كامل هنا.")
        except Exception:  # noqa: BLE001, S110 — guard must never break the tool
            pass
        return p.returncode == 0, _clip(obs, MAX_OBS_CHARS)
    except subprocess.TimeoutExpired:
        return False, f"انتهت مهلة الأمر ({BASH_TIMEOUT_S}s) — أُلغي"
    except Exception as exc:  # noqa: BLE001 — tool errors are observations
        return False, f"فشل التنفيذ: {exc}"


def tool_read_file(ctx: AgentContext, path: str) -> tuple[bool, str]:
    p = ctx.resolve(path)
    if p is None:
        return False, f"مسار خارج مساحة العمل مرفوض: {path}"
    if not p.is_file():
        return False, f"الملف غير موجود: {path}"
    try:
        return True, _clip(p.read_text(encoding="utf-8", errors="replace"), MAX_FILE_CHARS)
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذرت القراءة: {exc}"


def tool_write_file(ctx: AgentContext, path: str, content: str) -> tuple[bool, str]:
    p = ctx.resolve(path)
    if p is None:
        return False, f"مسار خارج مساحة العمل مرفوض: {path}"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return True, f"كُتب {path} ({len(content)} حرفاً)"
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر الكتابة: {exc}"


def tool_list_dir(ctx: AgentContext, path: str = "") -> tuple[bool, str]:
    p = ctx.resolve(path or ".")
    if p is None or not p.is_dir():
        return False, f"مجلد غير صالح: {path}"
    try:
        entries = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = [f"{'📄' if e.is_file() else '📁'} {e.name}" for e in entries[:60]]
        return True, "\n".join(lines) or "(فارغ)"
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر الإدراج: {exc}"


def tool_glob(ctx: AgentContext, pattern: str) -> tuple[bool, str]:
    try:
        hits = [str(p.relative_to(ctx.workspace)).replace("\\", "/")
                for p in ctx.workspace.glob(pattern or "**/*") if p.is_file()][:80]
        return True, "\n".join(hits) or "(لا تطابقات)"
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر البحث بالنمط: {exc}"


def tool_grep(ctx: AgentContext, pattern: str) -> tuple[bool, str]:
    if not pattern:
        return False, "نمط فارغ"
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return False, f"نمط غير صالح: {exc}"
    hits = []
    for p in sorted(ctx.workspace.rglob("*")):
        if not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        try:
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace")
                                     .splitlines(), 1):
                if rx.search(line):
                    rel = p.relative_to(ctx.workspace)
                    hits.append(f"{rel}:{i}: {line.strip()[:140]}")
                    if len(hits) >= 40:
                        break
        except Exception:  # noqa: BLE001, S112 — unreadable file: skip
            continue
        if len(hits) >= 40:
            break
    return True, "\n".join(hits) or "(لا تطابقات)"


def tool_web_search(ctx: AgentContext, query: str) -> tuple[bool, str]:
    try:
        import oss_work_live as m
        results = m.web_search(query)
        if not results:
            return True, "(لا نتائج)"
        lines = [f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet'][:200]}"
                 for i, r in enumerate(results[:6])]
        return True, _clip("\n".join(lines), MAX_OBS_CHARS)
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر البحث: {exc}"


def tool_web_fetch(ctx: AgentContext, url: str) -> tuple[bool, str]:
    if not url.startswith(("http://", "https://")):
        return False, "رابط غير صالح"
    try:
        import oss_work_live as m
        text = m._fetch_page_text(url)
        return True, _clip(text, MAX_OBS_CHARS) if text else "(صفحة فارغة)"
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر الجلب: {exc}"


def tool_skill(ctx: AgentContext, name: str) -> tuple[bool, str]:
    """Hermes-inspired: reusable skill instructions loaded on demand.
    Reads from the team skills folder (read-only)."""
    skills_dir = Path(r"C:\Users\ce\Desktop\Skills")
    if not skills_dir.is_dir():
        return False, "مجلد المهارات غير موجود على هذا الجهاز"
    cand = skills_dir / f"{name}.md"
    if not cand.is_file():
        avail = sorted(p.stem for p in skills_dir.glob("*.md"))
        return False, f"مهارة غير موجودة. المتاح: {', '.join(avail)}"
    try:
        return True, _clip(cand.read_text(encoding="utf-8"), MAX_OBS_CHARS)
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر تحميل المهارة: {exc}"


TOOLS = {
    "bash":       {"fn": tool_bash,       "args": {"command": "str"},
                   "desc": "تنفيذ أمر داخل مساحة عمل الوكيل (cmd على ويندوز)"},
    "read_file":  {"fn": tool_read_file,  "args": {"path": "str"},
                   "desc": "قراءة ملف من مساحة العمل"},
    "write_file": {"fn": tool_write_file, "args": {"path": "str", "content": "str"},
                   "desc": "كتابة/إنشاء ملف في مساحة العمل"},
    "list_dir":   {"fn": tool_list_dir,   "args": {"path": "str (اختياري)"},
                   "desc": "عرض محتويات مجلد"},
    "glob":       {"fn": tool_glob,       "args": {"pattern": "str مثل **/*.py"},
                   "desc": "بحث ملفات بنمط"},
    "grep":       {"fn": tool_grep,       "args": {"pattern": "str regex"},
                   "desc": "بحث نصي في كل ملفات مساحة العمل"},
    "web_search": {"fn": tool_web_search, "args": {"query": "str"},
                   "desc": "بحث في الويب"},
    "web_fetch":  {"fn": tool_web_fetch,  "args": {"url": "str"},
                   "desc": "جلب نص صفحة ويب"},
    "skill":      {"fn": tool_skill,      "args": {"name": "str اسم المهارة"},
                   "desc": "تحميل تعليمات مهارة من مكتبة المهارات (23 مهارة)"},
}

EXECUTABLE = {"bash", "read_file", "write_file", "list_dir", "glob", "grep",
              "web_search", "web_fetch", "skill"}


def execute(ctx: AgentContext, name: str, args: dict) -> tuple[bool, str]:
    fn = ctx.tools.get(name, {}).get("fn")
    if fn is None:
        return False, f"أداة غير معروفة: {name}"
    t0 = time.monotonic()
    try:
        ok, obs = fn(ctx, **{k: v for k, v in args.items() if k in
                             {a for a in ctx.tools[name].get("args", {})}})
    except TypeError as exc:
        ok, obs = False, f"وسائط خاطئة: {exc}"
    ctx.steps.append({"tool": name, "args": {k: (v[:80] if isinstance(v, str) else v)
                                             for k, v in args.items()},
                      "ok": ok, "ms": round((time.monotonic() - t0) * 1000),
                      "obs": str(obs)[:500]})
    return ok, obs


# ---------------------------------------------------------------------------
# Loop plumbing — the prompt + action parsing (provider-agnostic text protocol)
# ---------------------------------------------------------------------------

def _available_skills() -> str:
    """Hermes-inspired: advertise the skill library so the model knows it can
    load deep instructions on demand (opencode does this via SkillInstructions)."""
    skills_dir = Path(r"C:\Users\ce\Desktop\Skills")
    try:
        names = sorted(p.stem for p in skills_dir.glob("*.md"))
    except Exception:  # noqa: BLE001
        return "لا توجد مهارات على هذا الجهاز"
    return ", ".join(names)


def compose_system(task: str, table: dict | None = None,
                   memory_brief: str = "") -> str:
    """The system prompt + the LEARNED context (Copilot-style retrieval:
    relevant workspace code + past-run lessons + project style rules)."""
    base = system_prompt(task, table)
    if memory_brief and memory_brief.strip():
        return (base + "\n\n=== سياق تعلّمه OSS تلقائياً (استعنه ولا تتجاهله) ===\n"
                + memory_brief.strip())
    return base


def system_prompt(task: str, table: dict | None = None) -> str:
    tool_docs = "\n".join(
        f"- {n}: {t['desc']} | وسائط: {json.dumps(t['args'], ensure_ascii=False)}"
        for n, t in (table or TOOLS).items())
    return (
        "أنت وكيل OS_V — عقل هندسي يعمل بأدوات حقيقية. مهمتك الآن:\n"
        f"{task}\n\n"
        "الأدوات المتاحة:\n" + tool_docs + "\n\n"
        f"مكتبة مهارات متاحة (حمّلها بأداة skill عند الحاجة لخبرة معمّقة): {_available_skills()}\n\n"
        "قواعد العمل الصارمة:\n"
        "1. في كل دورة تُصدر إجراءً واحداً أو أكثر (مستقلة) في كتل كود json بهذا الشكل بالضبط:\n"
        '```json\n{"tool": "اسم_الأداة", "args": {...}}\n```\n'
        "2. بعد كل إجراء سترى النتيجة الحقيقية كاملة في [النتيجة].\n"
        "3. فكّر خطوة خطوة: افحص ثم اكتب ثم نفّذ للتأكد قبل أن تقول إنك انتهت.\n"
        "4. عندما تكتمل المهمة فعلاً أجب بـ:\n"
        '```json\n{"tool": "done", "args": {"answer": "التقرير النهائي بالعربية"}}\n```\n'
        "5. ممنوع تخمين نتائج الأدوات. ممنوع ادعاء نجاح لم تجره بعينك. تقريرك النهائي "
        "ينقل ملاحظة الأداة بأمانتها: مسارات الملفات الناتجة حرفياً، وأي تحذير (⚠️) "
        "أو سبب فشل يُروى كما هو — حذفه ادعاء زور.\n"
        "6. إن فشل أمر أصلحه وجرّب بديلاً — لا تكرر نفس الفاشل.\n"
        "7. الإجراءات المستقلة تُصدر في نفس الدورة (تُنفَّذ بالتوازي) لتوفير الوقت.\n"
        "8. أنت لست برنامجاً نصياً — لديك أدوات وسائط حقيقية: image_generate تولّد صوراً "
        "و video_generate يولّد مقاطع متحركة. إذا طلب المستخدم صورة أو فيديو أو مقطعاً أو "
        "شعاراً: أطلق الأداة فوراً في أول دورة (لكل مشهد/صورة وصفاً كاملاً مفصلاً بالألوان "
        "والتفاصيل). ممنوع منعاً باتاً الاعتذار أو القول إنك نصي فقط أو أنك لا تستطيع توليد وسائط.")


def _sig(name: str, args: dict) -> str:
    import hashlib
    return hashlib.sha256(json.dumps([name, args], sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()[:16]


_ACTION_RX = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def parse_actions(text: str) -> list[dict]:
    """All valid JSON actions in a reply (opencode parallelism: one reply may
    carry several independent tool calls — executed concurrently)."""
    out = []
    for raw in _ACTION_RX.findall(text or ""):
        try:
            act = json.loads(raw)
            if isinstance(act, dict) and isinstance(act.get("tool"), str):
                out.append(act)
        except json.JSONDecodeError:
            continue
    return out


def parse_action(text: str) -> dict | None:
    """The LAST valid action — kept for single-action turns (done)."""
    acts = parse_actions(text)
    return acts[-1] if acts else None


# ---------------------------------------------------------------------------
# The agent loop — plan → act → observe → repeat → honest final report
# ---------------------------------------------------------------------------

def run_agent(task: str, ctx: AgentContext, chain: list[dict], on_event,
              memory_brief: str = "", max_steps: int | None = None,
              require_steps: int = 0):
    """Drive the real tool loop. on_event(dict) receives progress events.
    Returns (final_text, ok). Fails HONESTLY — never fakes completion.
    max_steps: workers in a team run bounded (12) — a swarm must converge.
    require_steps: ممنوع إنهاء مهمة العمل قبل تنفيذ هذا العدد من الإجراءات —
    النموذج الذي يرسل done من أول دورة بلا أن يكتب ملفاً يُردُّ للعمل إلزاماً
    (ثغرة حية اكتشفها قياس السرب: عاملان «اكتملا» بصفر خطوات وملفات وهمية)."""
    import oss_work_live as m
    steps_limit = max_steps or MAX_STEPS

    def say(evt):
        try:
            on_event(evt)
        except Exception:  # noqa: BLE001, S110 — UI hiccups must not kill the agent
            pass

    msgs = [{"role": "system", "content": compose_system(task, ctx.tools,
                                                         memory_brief)}]
    final, complied_streak = "", 0
    sigs: list[tuple[int, str]] = []       # (step, signature) — loop detection
    for step in range(1, steps_limit + 1):
        reply = ""
        for cfg in chain:
            try:
                reply = "".join(m._gw_stream(cfg, msgs, effort="low",
                                             timeout=300, max_tokens=3000)).strip()
                if reply:
                    break
            except Exception:  # noqa: BLE001, S112 — next provider in the gateway chain
                continue
        if not reply:
            return final, False

        acts = parse_actions(reply)
        if not acts:
            complied_streak += 1
            if complied_streak >= 2:
                # the model keeps prose-ing instead of acting: accept its text
                # as the answer but SAY it never used tools (honesty rule)
                say({"type": "agent_step", "step": step, "tool": "none", "ok": False})
                return reply[:2000], False
            msgs.append({"role": "assistant", "content": reply})
            msgs.append({"role": "user", "content":
                         "لم أفهم إجراءً بصيغة json. أعد الإجراء في كتلة ```json``` فقط."})
            continue
        complied_streak = 0

        # loop detection (Crush loop_detection.go): same (tool,args) repeated
        # >4 times within a 10-step window = an infinite loop — stop honestly.
        sigs.append((step, _sig(acts[-1]["tool"], acts[-1].get("args", {}))))
        recent = [s for _st, s in sigs if _st >= step - 9]
        if recent.count(recent[-1]) > 4:
            say({"type": "agent_step", "step": step, "tool": "loop-detected", "ok": False})
            return (final or "توقفت: اكتشفت حلقة مكررة (نفس الإجراء يتكرر بلا تقدم). "
                    "هذا كل ما أنجزته."), False

        done_act = next((a for a in acts if a["tool"] == "done"), None)
        if done_act:
            # الموجة الأخيرة قد تحمل عملاً مع الإنهاء (قاعدة التوازي تشجع
            # على ذلك) — نفّذ الإجراءات الأخرى أولاً وإلا سقط العمل الموعود
            others = [a for a in acts if a["tool"] != "done"]
            if others:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=4) as pool2:
                    futs2 = [(a, pool2.submit(execute, ctx, a["tool"],
                                              a.get("args", {})))
                             for a in others[:4]]
                    for a, fut2 in futs2:
                        _ok2, _obs2 = fut2.result()
                        say({"type": "agent_step", "step": step,
                             "tool": a["tool"], "ok": _ok2})
            if require_steps and len([s for s in ctx.steps if s.get("ok")]) < require_steps:
                # الصدق بنيوي: إنهاء بلا عمل ناجح فعلي = زور يُرد لا يُقبل
                # (خطوة فاشلة لا تُحتسب — الكتابة الساقطة ليست إنجازاً)
                msgs.append({"role": "assistant", "content": reply})
                msgs.append({"role": "user", "content":
                             "ممنوع الإنهاء قبل العمل الناجح: إجراءاتك لم تُنتج ملفاً "
                             "فعلياً على القرص (راجع [النتيجة] بالفشل). أعد التنفيذ "
                             "بأدواتك واكتب الملفات فعلياً، ثم أنهِ بتقرير يذكر "
                             "المسارات الحقيقية."})
                continue
            final = str(done_act.get("args", {}).get("answer", "")).strip()
            # الصدق لا يُوكل للنموذج (OSS law): أي تحذير ⚠️ أو فشل في ملاحظات
            # الأدوات يُلحق بالرد النهائي إلزاماً — النموذج لا يستطيع إخفاء
            # عطل أو بديل مهما أغفل في سردِه.
            if "⚠️" not in final and "فشل" not in final:
                notes = [s["obs"] for s in ctx.steps if s.get("obs")
                         and ("⚠️" in s["obs"] or "فشل" in s["obs"]
                              or not s.get("ok"))]
                for n in notes[-2:]:
                    final += f"\n\n[ملاحظة النظام — إلزامية]: {n}"
            say({"type": "agent_step", "step": step, "tool": "done", "ok": True})
            return final, bool(final)

        # parallel execution of the independent actions in this reply (opencode
        # parallelism: one step may carry several tool calls, run concurrently)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            futs = [(a, pool.submit(execute, ctx, a["tool"], a.get("args", {})))
                    for a in acts[:3]]
            observations = []
            for a, fut in futs:
                name = a["tool"]
                if name not in ctx.tools:
                    ok, obs = False, (f"أداة غير معروفة: {name}. "
                                      f"الأدوات: {', '.join(sorted(ctx.tools))}")
                else:
                    ok, obs = fut.result()
                observations.append(f"[{name} → {'نجح' if ok else 'فشل'}]\n{obs}")
                say({"type": "agent_step", "step": step, "tool": name, "ok": ok,
                     "preview": {k: (v[:80] if isinstance(v, str) else v)
                                 for k, v in a.get("args", {}).items()}})

        msgs.append({"role": "assistant", "content": reply})
        msgs.append({"role": "user", "content":
                     "[النتيجة]\n" + "\n\n".join(observations) +
                     "\n\nأكمل: الإجراء التالي، أو أنهِ بـ done والتقرير."})
    # budget exhausted — report what EXISTS, never pretend
    return (final or "لم أُكمل المهمة ضمن حد الدورات — هذا كل ما أنجزته: "
            + (f"{len(ctx.steps)} خطوة أداة." if ctx.steps else "لا شيء.")), False