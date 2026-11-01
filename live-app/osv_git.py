"""OS_V git tools — the agent versions its OWN work inside its workspace.

The gap: the agent writes great code and cannot checkpoint it — one bad
"fix" later destroys yesterday's good state. With git tools, the agent
commits working states and diffs before risky edits (what Claude Code does
for the user, done by the agent itself).

Containment (OSS safety law): every command runs with cwd=ctx.workspace,
an EXPLICIT subcommand allowlist (status/add/commit/diff/log/init), a hard
timeout, and the two absolute bans — never push, never touch remotes.
A missing repo auto-inits locally; the agent identity is set LOCALLY
(never global) only when git needs it to commit."""
from __future__ import annotations

import subprocess
from pathlib import Path

_GIT_TIMEOUT_S = 30
_ALLOWED = {"status", "add", "commit", "diff", "log", "init"}


def _run_git(args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        p = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_GIT_TIMEOUT_S,
            check=False)
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        if p.returncode != 0:
            # git يوزع مخرجاته بين المجَرَين (commit يقول "nothing to commit"
            # على stdout) — الاثنان يُعادان دائماً حتى لا تُخفى حقيقة الفشل
            return False, (err + "\n" + out).strip() or \
                f"git {' '.join(args)} خرج بكود {p.returncode}"
        return True, out or err        # commit prints to stderr — that IS success
    except FileNotFoundError:
        return False, "git غير مثبت على هذا الجهاز — ثبّته أولاً"
    except subprocess.TimeoutExpired:
        return False, f"تجاوز git المهلة ({_GIT_TIMEOUT_S}ث)"


def _ensure_repo(ctx) -> tuple[bool, str]:
    """Auto-init a LOCAL repo (no remote, ever) when the workspace is bare."""
    ok, out = _run_git(["rev-parse", "--is-inside-work-tree"], ctx.workspace)
    if ok and out == "true":
        return True, ""
    ok, out = _run_git(["init", "-q"], ctx.workspace)
    if not ok:
        return False, out
    # commit needs an identity — set it LOCALLY only, never touch the global
    _run_git(["config", "user.name", "OS_V1 Agent"], ctx.workspace)
    _run_git(["config", "user.email", "osv1@local"], ctx.workspace)
    return True, ""


def _git(ctx, sub: str, git_args: list[str]) -> tuple[bool, str]:
    if sub not in _ALLOWED:
        return False, (f"الأمر '{sub}' غير مسموح — المسموح: "
                       f"{sorted(_ALLOWED)}. (الرفع push محظور نهائياً)")
    ok, msg = _ensure_repo(ctx)
    if not ok:
        return False, msg
    ok, out = _run_git([sub, *git_args], ctx.workspace)
    return ok, out


def git_tools():
    """Four tools, same surface convention as mcp_tools()/team_tool()."""

    def _status(ctx, **_a):
        ok, out = _git(ctx, "status", ["--short", "-b"])
        return ok, out or "(المستودع نظيف — لا تغييرات)"

    def _commit(ctx, message="", **_a):
        message = str(message or "").strip()
        if not message:
            return False, "الالتزام يحتاج message — لا التزامات بلا معنى"
        ok_e, msg_e = _ensure_repo(ctx)   # repo FIRST — the gate needs status,
        if not ok_e:                      # and the FIRST commit must be gated
            return False, msg_e           # too (a live-caught flaw)
        # secrets gate: scan what WOULD be staged before it lands in history
        # (quotepath=false so Arabic filenames are never a blind spot)
        import osv_redteam
        ok_st, st = _run_git(["-c", "core.quotepath=false",
                              "status", "--porcelain"], ctx.workspace)
        if ok_st and st:
            changed = []
            for line in st.splitlines():
                path = line[3:].strip() if len(line) > 3 else ""
                if " -> " in path:
                    path = path.split(" -> ", 1)[1]
                path = path.strip('"').strip()
                if path and not path.startswith(".git"):
                    changed.append(path)
            ok_sec, why_sec = osv_redteam.screen_commit(ctx.workspace, changed)
            if not ok_sec:
                return False, why_sec
        _git(ctx, "add", ["-A"])       # workspace-scoped: the repo IS the ws
        ok, out = _git(ctx, "commit", ["-m", message])
        if not ok:
            if "nothing to commit" in out:
                return True, "لا شيء للالتزام به — لا تغييرات منذ آخر التزام"
            return False, out
        _rc, log = _run_git(["log", "-1", "--format=%h %s"], ctx.workspace)
        return True, (log or out)[:300]

    def _diff(ctx, **_a):
        return _git(ctx, "diff", ["HEAD", "--stat"]) if _has_commits(ctx) \
            else _git(ctx, "diff", ["--stat"])

    def _has_commits(ctx) -> bool:
        ok, out = _run_git(["rev-parse", "HEAD"], ctx.workspace)
        return ok and bool(out.strip())

    def _log(ctx, max_count=10, **_a):
        try:
            n = min(max(int(max_count), 1), 50)
        except (TypeError, ValueError):
            n = 10
        return _git(ctx, "log", [f"--max-count={n}", "--oneline"])

    return {
        "git_status": {"fn": _status, "args": {},
                       "desc": "يظهر ما تغيّر في مساحة عملك — استخدمه قبل "
                               "التعديلات الخطرة وبعد إتمام عمل"},
        "git_commit": {"fn": _commit,
                       "args": {"message": "str رسالة الالتزام"},
                       "desc": "يلتزم بكل تغييرات مساحة عملك برسالة — "
                               "التزم بعد كل إنجاز مستقر حتى لا يُفقد. "
                               "بوابة أمنية تفحص الملفات المُرحَّلة وترفض "
                               "الالتزام إذا وُجد مفتاح/سر مكتشف"},
        "git_diff":   {"fn": _diff, "args": {},
                       "desc": "يظهر الفرق عن آخر التزام — قبل أي إعادة "
                               "كتابة كبيرة"},
        "git_log":    {"fn": _log, "args": {"max_count": "int"},
                       "desc": "سجل الالتزامات السابقة"},
    }
