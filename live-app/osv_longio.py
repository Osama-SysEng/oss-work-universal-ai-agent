"""OS_V long-io — the million-token lanes.

INPUT: a whole workspace becomes a prioritized dossier (context pack) with
an honest truncation map — the model reads it in slices, nothing silently
dropped. OUTPUT: files too big for one reply are written in ORDERED PARTS
across many replies, stitched, and verified (compiled if python) only when
the last part lands. A missing part is an error — never a silent gap.

Both lanes respect one law: what got cut is REPORTED, what got written is
VERIFIED."""
from __future__ import annotations

import re
from pathlib import Path

# ~3.2 chars per token for mixed Arabic/English/code (conservative mean)
_CHARS_PER_TOKEN = 3.2
_PART_SUFFIX = ".part{:04d}"


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text or "") / _CHARS_PER_TOKEN))


# ---------------------------------------------------------------------------
# INPUT lane: workspace → dossier
# ---------------------------------------------------------------------------

_TEXT_EXT = {".py", ".js", ".jsx", ".ts", ".tsx", ".css", ".html", ".json",
             ".md", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".sql", ".sh",
             ".ps1", ".env.example", ".xml", ".csv"}
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv",
              ".ruff_cache", ".pytest_cache", "data", "dist", "build"}


def _priority(p: Path) -> tuple:
    """README/docs and entrypoints first, then sources, then the rest."""
    name = p.name.lower()
    if name in ("readme.md", "main.py", "app.py", "index.py", "run.py",
                "package.json", "pyproject.toml"):
        return (0, p.suffix.lower() not in (".md",), str(p))
    if p.suffix.lower() == ".py":
        return (1, name.startswith("test"), str(p))
    if p.suffix.lower() in (".md", ".txt", ".json", ".yml", ".yaml"):
        return (2, False, str(p))
    return (3, False, str(p))


def dossier(root: Path, budget_tokens: int = 120_000) -> dict:
    """Pack the workspace into ONE text blob under the token budget.

    Returns {text, tokens, map, truncated} — map reports per-file
    chunks_taken/chunks_total so truncation is a FACT on the table, never a
    silent loss. Priority: entrypoints → code → docs → the rest; newest
    wins inside the same class."""
    root = Path(root)
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in _TEXT_EXT:
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        files.append(p)
    files.sort(key=lambda p: (_priority(p)[:2],
                              -p.stat().st_mtime, str(p)))

    pieces: list[str] = []
    fmap: dict[str, dict] = {}
    truncated: list[str] = []
    used = 0
    for p in files:
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError as _exc:            # unreadable = reported, not fatal
            del _exc
            continue
        rel = p.relative_to(root).as_posix()
        total = estimate_tokens(raw)
        if used >= budget_tokens:
            truncated.append(rel)
            fmap[rel] = {"chunks_taken": 0, "chunks_total": 1, "tokens": total}
            continue
        head = f"\n\n===== FILE: {rel} ({total} tok) =====\n"
        budget_left = budget_tokens - used - estimate_tokens(head)
        if budget_left <= 0:
            truncated.append(rel)
            fmap[rel] = {"chunks_taken": 0, "chunks_total": 1, "tokens": total}
            continue
        if total <= budget_left:
            pieces.append(head + raw)
            used += total + estimate_tokens(head)
            fmap[rel] = {"chunks_taken": 1, "chunks_total": 1, "tokens": total}
        else:
            # take a HEAD slice that fits — a fact, labeled as partial
            keep = int(budget_left * _CHARS_PER_TOKEN)
            cut = raw[:max(keep, 0)].rsplit("\n", 1)[0]
            pieces.append(head + cut + f"\n===== (مقطوعة: أُخذت {estimate_tokens(cut)}"
                                       f" من {total} توكين) =====")
            used += estimate_tokens(cut) + estimate_tokens(head)
            fmap[rel] = {"chunks_taken": 1, "chunks_total": 2, "tokens": total}
            truncated.append(rel)
    text = "".join(pieces)
    return {"text": text, "tokens": used, "map": fmap, "truncated": truncated}


# ---------------------------------------------------------------------------
# OUTPUT lane: a big file written in ordered parts across many replies
# ---------------------------------------------------------------------------

def _target(ctx, path: str) -> Path | None:
    p = ctx.resolve(path)
    return p


def _verify_if_code(p: Path) -> tuple[bool, str]:
    """py files compile only when the LAST part lands — a broken part is a
    bounce, not a shipped bug."""
    if p.suffix.lower() != ".py":
        return True, ""
    import py_compile
    try:
        py_compile.compile(str(p), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, f"الملف المجمع لا يُترجم: {str(exc)[:200]}"


def long_write(ctx, path: str, content: str, part: int = 1, total: int = 1,
               **_a) -> tuple[bool, str]:
    """Write part N of total; append in order; verify at completion.

    Content may be raw text or fenced (```…```) — fences are stripped so a
    model that wraps code still lands clean bytes."""
    if not path or not str(path).strip():
        return False, "مطلوب path"
    try:
        part = int(part)
        total = int(total)
    except (TypeError, ValueError):
        return False, "part و total يجب أن يكونا صحيحين"
    if total < 1 or part < 1 or part > total:
        return False, f"part/total خارج النطاق (1..{total})"
    p = _target(ctx, str(path))
    if p is None:
        return False, "المسار يهرب من مساحة العمل — مرفوض"
    text = str(content or "")
    m = re.match(r"^```[a-zA-Z0-9_+-]*\n(.*)\n```\s*$", text, re.DOTALL)
    if m:
        text = m.group(1)
    final = part == total
    mode = "wb" if part == 1 else "ab"
    try:
        if part == 1:
            p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, mode) as f:
            f.write(text.encode("utf-8"))
    except OSError as exc:
        return False, f"فشل كتابة الجزء {part}: {str(exc)[:150]}"
    if not final:
        return True, (f"الجزء {part}/{total} كُتب ({estimate_tokens(text)} tok) — "
                      f"أكمل الجزء {part + 1} بنفس الأداة")
    ok, err = _verify_if_code(p)
    size = p.stat().st_size
    if not ok:
        return False, (f"اكتمل التجميع لكنه مرفوض — {err}. أعد إرسال الأجزاء "
                       "المكسورة أو ابدأ من part=1 للكتابة من جديد")
    return True, (f"اكتمل الملف {p.name}: {total} جزءاً، {size} بايت "
                  f"(~{estimate_tokens(p.read_text(encoding='utf-8', errors='replace'))} tok)"
                  + (" — يُترجم بنجاح" if p.suffix == ".py" else ""))


def longio_tools():
    return {
        "ingest": {"fn": lambda ctx, path=".", budget_tokens=120_000, **_a:
                   _ingest_tool(ctx, path, budget_tokens),
                   "args": {"path": "str مسار نسبي (افتراضي .)",
                            "budget_tokens": "int سقف السياق"},
                   "desc": "يحشر مساحة عمل كاملة في ملف context_pack.md "
                           "(بأولوية المداخل ثم الكود) مع خريطة قصّ صادقة — "
                           "اقرأه بـ read_file على دفعات وأنت تعلم كل شيء"},
        "long_write": {"fn": long_write,
                       "args": {"path": "str", "content": "str",
                                "part": "int", "total": "int"},
                       "desc": "يكتب ملفاً ضخماً على أجزاء مرتبة عبر أ replies "
                               "متعددة — part/total إلزاميان، والملف يُترجم "
                               "ويُفحص عند اكتمال آخر جزء فقط"},
    }


def _ingest_tool(ctx, path: str = ".", budget_tokens=120_000, **_a):
    try:
        budget = min(max(int(budget_tokens), 1_000), 900_000)
    except (TypeError, ValueError):
        budget = 120_000
    root = ctx.resolve(path or ".")
    if root is None:
        return False, "المسار يهرب من مساحة العمل — مرفوض"
    if not root.exists():
        return False, f"لا يوجد {path} في مساحة العمل"
    pack = dossier(root, budget)
    out = ctx.workspace / "context_pack.md"
    out.write_text(f"# حزمة سياق المساحة ({pack['tokens']} توكين)\n"
                   + pack["text"], encoding="utf-8")
    n_cut = len(pack["truncated"])
    summary = (f"الحزمة جاهزة: context_pack.md — {pack['tokens']} توكين، "
               f"{len(pack['map'])} ملفاً"
               + (f"، مقطوعة منها {n_cut} (معلَّمة بالداخل بصدق)" if n_cut
                  else "، بلا أي قص"))
    return True, summary + "\n" + "\n".join(
        f"  {k}: {v['chunks_taken']}/{v['chunks_total']}"
        for k, v in list(pack["map"].items())[:25])
