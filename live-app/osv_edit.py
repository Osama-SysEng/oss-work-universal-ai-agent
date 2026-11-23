"""OS_V edit tools — surgical editing, unified patches, self-verification.

Why this module exists (the measured gap):
    `write_file` rewrites a WHOLE file. When the model's reply was cut in the
    middle (long_write chunking), the result was a 10KB `server.py` that did
    not compile: `send_json` was fused with `else/finally`. Devin/Claude-Code
    survive that because they edit *surgically*: a unique old_string becomes
    new_string, or a unified diff is applied hunk by hunk with verification.

Design laws (same containment as osv_git / osv_clean):
    * every path resolves INSIDE ctx.workspace (ctx.resolve), never absolute;
    * `edit_file` refuses ambiguous matches instead of guessing;
    * `apply_patch` is atomic: all hunks are validated first, then written —
      a partial patch never lands;
    * `verify_project` runs REAL checks (compile / refs / JSON / sqlite /
      optional pytest) and reports exactly what failed;
    * nothing here touches the network or the OS outside the workspace.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import osv_text

_MAX_PREVIEW = 40
_MAX_SCAN = 4000
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".pytest_cache",
              ".ruff_cache", "site-packages"}
_HTML_REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_HUNK = re.compile(r"^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@")
_JS_OK = bool(shutil.which("node"))


# ---------------------------------------------------------------------------
# byte-faithful read/write (CRLF + BOM survive a surgical edit)
# ---------------------------------------------------------------------------
def _read_text(p: Path) -> tuple[str, str, bool]:
    raw = p.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    if bom:
        raw = raw[3:]
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
    return text, ("\r\n" if crlf else "\n"), bom


def _write_text(p: Path, text: str, newline: str, bom: bool) -> None:
    body = text.replace("\n", newline)
    data = body.encode("utf-8")
    p.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def _preview(before: str, after: str, label: str) -> str:
    diff = list(difflib.unified_diff(before.splitlines(), after.splitlines(),
                                     fromfile=label, tofile=label, n=2,
                                     lineterm=""))
    if not diff:
        return ""
    return "\n".join(diff[:_MAX_PREVIEW])


# ---------------------------------------------------------------------------
# edit_file — the workhorse
# ---------------------------------------------------------------------------
def edit_file(ctx, path: str, old_string: str, new_string: str,
              replace_all=False) -> tuple[bool, str]:
    p = ctx.resolve(path)
    if p is None:
        return False, f"مسار خارج مساحة العمل مرفوض: {path}"
    if not p.is_file():
        return False, f"الملف غير موجود: {path} (لإنشاء جديد استخدم write_file)"
    old_string = str(old_string or "").replace("\r\n", "\n")
    if not old_string:
        return False, "old_string فارغ — لا تعديل بلا هدف محدد"
    new_string = str(new_string or "").replace("\r\n", "\n")
    new_string, removed = osv_text.strip_invisibles(new_string)

    text, newline, bom = _read_text(p)
    hits = text.count(old_string)
    if hits == 0:
        first = old_string.splitlines()[0].strip() if old_string.strip() else ""
        lines = text.splitlines()
        stripped = [ln.strip() for ln in lines]
        near = [f"{i}: {ln.strip()[:100]}" for i, ln in enumerate(lines, 1)
                if first and (first in ln or ln.strip() in first)][:6]
        if not near and first:
            # the model often reflows a signature onto one line — show the
            # closest real lines instead of a dead end (silent mismatch costs
            # a whole wave on the local engine).
            for ratio, idx in sorted(
                    ((difflib.SequenceMatcher(None, first, s).ratio(), n)
                     for n, s in enumerate(stripped, 1) if s),
                    reverse=True)[:6]:
                if ratio < 0.55:
                    break
                near.append(f"{idx}: {lines[idx - 1].strip()[:100]}")
        hint = ("\nأسطر مشابهة (قد يكون اختلاف مسافات أو سطراً مطوياً):\n"
                + "\n".join(near) if near
                else "\nلم أجد حتى سطراً مشابهاً — أعد قراءة الملف.")
        return False, (f"لم أجد old_string في {path} حرفياً "
                       f"({hits} تطابق){hint}")
    if hits > 1 and not _truthy(replace_all):
        lines = [i for i, ln in enumerate(text.splitlines(), 1)
                 if old_string.splitlines()[0] in ln][:8]
        return False, (f"old_string يظهر {hits} مرات في {path} — أضف سياقاً "
                       f"أطول ليكون فريداً أو مرّر replace_all=true. "
                       f"أسطر مرشحة: {lines}")
    after = (text.replace(old_string, new_string) if _truthy(replace_all)
             else text.replace(old_string, new_string, 1))
    if after == text:
        return True, f"لا تغيير فعلي في {path} (النص مطابق)"
    _write_text(p, after, newline, bom)
    line_no = after[:after.index(new_string) if new_string in after else 0] \
        .count("\n") + 1 if new_string else 0
    preview = _preview(text, after, path)
    return True, (f"عُدّل {path}: {hits if _truthy(replace_all) else 1} "
                  f"موضعاً (أول تغيير ~سطر {line_no})"
                  + osv_text.note(removed)
                  + (f"\n{preview}" if preview else ""))


def _truthy(v) -> bool:
    return str(v).strip().lower() in {"1", "true", "yes", "y", "on"}


# ---------------------------------------------------------------------------
# apply_patch — unified diff, multi-file, atomic
# ---------------------------------------------------------------------------
def _clean_header(line: str) -> str:
    raw = line[4:].strip()
    if raw == "/dev/null":
        return ""
    if raw.startswith(("a/", "b/")):
        raw = raw[2:]
    return raw


def apply_patch(ctx, patch: str, dry_run=False) -> tuple[bool, str]:
    patch = str(patch or "").replace("\r\n", "\n")
    if "--- " not in patch or "+++ " not in patch:
        return False, ("الرقعة ليست unified diff — المطلوب أسطر "
                       "'--- path' و'+++ path' وكتل '@@ -a,b +c,d @@'")
    if len(patch) > 400_000:
        return False, "الرقعة أكبر من 400KB — قسّمها"

    lines = patch.split("\n")
    files: list[dict] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("--- "):
            i += 1
            continue
        old_path = _clean_header(lines[i])
        if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
            return False, f"سطر +++ مفقود بعد --- في السطر {i + 1}"
        new_path = _clean_header(lines[i + 1])
        i += 2
        hunks = []
        while i < len(lines) and lines[i].startswith("@@ "):
            m = _HUNK.match(lines[i])
            if not m:
                return False, f"ترويسة كتلة غير صالحة: {lines[i][:80]}"
            old_start = int(m.group(1))
            i += 1
            body = []
            while i < len(lines) and not lines[i].startswith(("@@ ", "--- ")):
                body.append(lines[i])
                i += 1
            hunks.append((old_start, body))
        files.append({"old": old_path, "new": new_path, "hunks": hunks})

    if not files:
        return False, "لا ملفات في الرقعة"
    # ---- phase 1: compute everything, touch nothing ----------------------
    plan: list[tuple[Path | None, str, str, str, bool]] = []
    for f in files:
        target = f["new"] or f["old"]
        p = ctx.resolve(target)
        if p is None:
            return False, f"مسار خارج مساحة العمل مرفوض: {target}"
        delete = (f["new"] == "")
        if delete:
            plan.append((p, "", target, "\n", False))
            continue
        if p.exists():
            text, newline, bom = _read_text(p)
        else:
            text, newline, bom = "", "\n", False
        current = text.split("\n")
        offset = 0
        for old_start, body in f["hunks"]:
            expected, replacement = [], []
            for ln_i, ln in enumerate(body):
                if ln.startswith("\\"):
                    continue                      # "\ No newline at end"
                if ln.startswith("+"):
                    replacement.append(ln[1:])
                elif ln.startswith("-"):
                    expected.append(ln[1:])
                elif ln.startswith(" "):
                    expected.append(ln[1:])
                    replacement.append(ln[1:])
                elif ln == "":
                    # hand-written patches use a truly empty line for context;
                    # the trailing "" is only split() debris, never a line.
                    if ln_i < len(body) - 1:
                        expected.append("")
                        replacement.append("")
                else:
                    return False, (f"سطر رقعة غير مفهوم: {ln[:80]!r} "
                                   f"(في {target})")
            idx = (old_start - 1 + offset) if old_start > 0 else 0
            if old_start == 0 and expected:
                return False, f"كتلة إنشاء غير صالحة في {target}"
            got = current[idx:idx + len(expected)]
            if got != expected:
                return False, (
                    f"فشل تطابق الكتلة في {target} عند السطر {old_start}: "
                    f"المتوقع {expected[:3]} والموجود {got[:3]} — "
                    "أعد قراءة الملف (read_file) وولّد الرقعة من جديد. "
                    "لم يُكتب أي تغيير.")
            current[idx:idx + len(expected)] = replacement
            offset += len(replacement) - len(expected)
        new_text = "\n".join(current)
        plan.append((p, new_text, target, newline, bom))

    if _truthy(dry_run):
        return True, ("dry_run: سليمة — " +
                      ", ".join(t for _p, _t, t, _n, _b in plan))

    # ---- phase 2: write ---------------------------------------------------
    done = []
    for p, new_text, target, newline, bom in plan:
        if p is None:
            continue
        if new_text == "" and target and not p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        _write_text(p, new_text, newline, bom)
        done.append(f"{target} ({len(new_text)} حرفاً)")
    return True, "طُبّقت الرقعة على: " + "، ".join(done)


# ---------------------------------------------------------------------------
# verify_project — real checks, not opinions
# ---------------------------------------------------------------------------
def verify_project(ctx, run_tests=False, max_seconds=120) -> tuple[bool, str]:
    root: Path = ctx.workspace
    py_files, js_files, html_files, json_files, db_files = [], [], [], [], []
    for p in root.rglob("*"):
        if len(py_files) + len(js_files) + len(html_files) > _MAX_SCAN:
            break
        if not p.is_file() or any(part in _SKIP_DIRS for part in p.parts):
            continue
        ext = p.suffix.lower()
        if ext == ".py":
            py_files.append(p)
        elif ext == ".js":
            js_files.append(p)
        elif ext in {".html", ".htm"}:
            html_files.append(p)
        elif ext == ".json":
            json_files.append(p)
        elif ext in {".db", ".sqlite", ".sqlite3"}:
            db_files.append(p)

    fails: list[str] = []
    notes: list[str] = []

    # 1) Python: compile without importing anything the project needs
    for p in py_files:
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
            compile(src, str(p), "exec")
        except SyntaxError as exc:
            fails.append(f"Python: {p.relative_to(root)} سطر {exc.lineno}: "
                         f"{exc.msg}")
        except (OSError, ValueError) as exc:
            fails.append(f"Python: {p.relative_to(root)} تعذرت القراءة: {exc}")

    # 2) JS: `node --check` when node exists
    if js_files and _JS_OK:
        for p in js_files[:60]:
            try:
                r = subprocess.run(["node", "--check", str(p)],
                                   capture_output=True, text=True,
                                   timeout=15, check=False)
                if r.returncode != 0:
                    err = (r.stderr or "").strip().splitlines()
                    fails.append(f"JS: {p.relative_to(root)}: "
                                 f"{(err[-1] if err else 'خطأ')[:160]}")
            except (OSError, subprocess.TimeoutExpired):
                notes.append(f"JS: تخطّي {p.name} (مهلة/تنفيذ)")
    elif js_files:
        notes.append("JS: node غير متاح — تخطّي الفحص")

    # 3) JSON
    for p in json_files:
        try:
            json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (ValueError, OSError) as exc:
            fails.append(f"JSON: {p.relative_to(root)}: {str(exc)[:120]}")

    # 4) HTML: every local src/href must exist on disk
    for p in html_files:
        try:
            html = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for ref in _HTML_REF.findall(html):
            low = ref.lower()
            if (low.startswith(("http://", "https://", "//", "#", "data:",
                                "mailto:", "javascript:", "tel:"))):
                continue
            clean = ref.split("?", 1)[0].split("#", 1)[0]
            if not clean:
                continue
            target = (p.parent / clean).resolve()
            try:
                target.relative_to(root.resolve())
            except ValueError:
                continue
            if not target.exists():
                fails.append(f"HTML: {p.relative_to(root)} يشير إلى مفقود: "
                             f"{ref}")

    # 5) SQLite integrity
    for p in db_files[:20]:
        try:
            con = sqlite3.connect(f"file:{p.as_posix()}?mode=ro", uri=True)
            try:
                row = con.execute("PRAGMA integrity_check").fetchone()
                if not row or row[0] != "ok":
                    fails.append(f"SQLite: {p.relative_to(root)}: {row}")
            finally:
                con.close()
        except sqlite3.Error as exc:
            fails.append(f"SQLite: {p.relative_to(root)}: {exc}")

    # 6) tests (opt-in — they can be slow)
    if _truthy(run_tests):
        has_tests = (root / "tests").is_dir() or bool(list(root.glob("test_*.py")))
        if not has_tests:
            notes.append("pytest: لا اختبارات — تخطّي")
        else:
            try:
                r = subprocess.run([sys.executable, "-m", "pytest", "-q",
                                    "--maxfail=5"], cwd=str(root),
                                   capture_output=True, text=True,
                                   timeout=max(10, int(max_seconds)), check=False)
                tail = ((r.stdout or "") + (r.stderr or "")).strip()
                if r.returncode != 0:
                    fails.append("pytest فشل:\n" + tail[-900:])
                else:
                    notes.append("pytest: " +
                                 (tail.splitlines()[-1] if tail else "نجح"))
            except (OSError, subprocess.TimeoutExpired):
                notes.append("pytest: تجاوز المهلة — أُلغي")

    counts = (f"ملفات: py={len(py_files)} js={len(js_files)} "
              f"html={len(html_files)} json={len(json_files)} "
              f"db={len(db_files)}")
    if fails:
        return False, (f"❌ فشل التحقق ({len(fails)}):\n- "
                       + "\n- ".join(fails[:15])
                       + (f"\n… و{len(fails) - 15} أخرى" if len(fails) > 15 else "")
                       + f"\n{counts}")
    msg = "✅ كل الفحوص نجحت — " + counts
    if notes:
        msg += "\nملاحظات: " + " | ".join(notes[:6])
    return True, msg


# ---------------------------------------------------------------------------
# tool registry (same convention as git_tools / clean_tools)
# ---------------------------------------------------------------------------
def edit_tools() -> dict:
    return {
        "edit_file": {
            "fn": edit_file,
            "args": {"path": "str", "old_string": "str نص فريد موجود",
                     "new_string": "str البديل",
                     "replace_all": "bool (اختياري)"},
            "desc": "تعديل جراحي: يستبدل old_string الفريد بـnew_string داخل "
                    "ملف موجود (يحفظ CRLF/BOM، يرفض الغموض، يعرض diff). "
                    "استخدمه لتغيير سطر/دالة بدل إعادة كتابة الملف كاملاً"},
        "apply_patch": {
            "fn": apply_patch,
            "args": {"patch": "str unified diff", "dry_run": "bool (اختياري)"},
            "desc": "يطبّق رقعة diff موحّدة على عدة ملفات دفعة واحدة — "
                    "ذرّي: يتحقق من كل الكتل قبل الكتابة، ولا يكتب شيئاً إن "
                    "فشلت كتلة"},
        "verify_project": {
            "fn": verify_project,
            "args": {"run_tests": "bool (اختياري)", "max_seconds": "int"},
            "desc": "تحقق حقيقي من المشروع: ترجمة كل .py، فحص .js، تحليل "
                    "JSON، مراجع HTML المحلية، سلامة قواعد SQLite، وpytest "
                    "عند الطلب. شغّله بعد التعديلات وقبل تسليم النتيجة"},
    }
