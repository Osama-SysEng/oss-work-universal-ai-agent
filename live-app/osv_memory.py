"""OS_V1 Memory — the Copilot-style learning layer (clean-room port).

What GitHub Copilot's published engineering does that we can honestly copy
(weights are NEVER copied — only the published MECHANISM):
  1. Workspace indexing + retrieval: rank code chunks by relevance to the
     task and inject them into the model's context (workspace embeddings;
     ours = pure-stdlib TF-IDF over line-chunks).
  2. Style learning: detect the project's conventions (indent, quotes,
     naming, comment language) and obey them.
  3. Experience memory: every run records what happened (tools, outcome);
     future runs recall relevant lessons — successes as playbooks, failures
     as things to avoid.

Everything is local (JSON/JSONL under the data dir), bounded (caps on files,
chunks, sizes), Arabic-aware (tashkeel/alef normalization in the tokenizer),
and honest: recall never invents — an empty index says so.
"""
from __future__ import annotations

import json
import math
import os
import re
import time
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Bounds — "bounded everything" (the OpenClaw/Copilot discipline)
# ---------------------------------------------------------------------------
MAX_FILES = 900          # indexed files per workspace
MAX_FILE_KB = 400        # skip monsters (build artifacts, dumps)
MAX_CHUNKS = 4000        # total chunks per index
CHUNK_LINES = 80         # chunk height
CHUNK_OVERLAP = 6        # context overlap between chunks
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".idea", ".vscode", "site-packages", ".mypy_cache",
             ".pytest_cache", "coverage", ".next", "target"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".gz",
              ".tar", ".7z", ".rar", ".exe", ".dll", ".so", ".dylib", ".woff",
              ".woff2", ".ttf", ".mp3", ".mp4", ".avi", ".sqlite", ".db",
              ".pyc", ".class", ".jar", ".bin", ".eot", ".map"}
SRC_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs", ".c",
           ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".kt", ".sh", ".md"}
MAX_BRIEF_CHARS = 4500

_TASHKEEL = re.compile("[\u064b-\u0652\u0640]")
_ALEF = {"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"}
_AR_RX = re.compile("[\u0600-\u06ff]")
_AR_PREFIX = ("للب", "وال", "بال", "كال", "فال", "لل", "ال", "و", "ل", "ب", "ف", "ك")
_AR_SUFFIX = ("ها", "هم", "ات", "ون", "ين", "ه", "ك", "ي")


def _stem_ar(w: str) -> str:
    """One known prefix + one known suffix, stem kept >= 3 chars — so
    «للمصادقة» و«المصادقة» يلتقيان على الجذع «مصادق» (الدرس 22)."""
    for p in _AR_PREFIX:
        if w.startswith(p) and len(w) - len(p) >= 3:
            w = w[len(p):]
            break
    for s in _AR_SUFFIX:
        if w.endswith(s) and len(w) - len(s) >= 3:
            w = w[:-len(s)]
            break
    return w


def tokenize(text: str) -> list[str]:
    """Lowercase + Arabic-normalized AND stemmed tokens — one vocabulary
    for Arabic tasks and English code."""
    t = _TASHKEEL.sub("", text or "")
    t = "".join(_ALEF.get(ch, ch) for ch in t).lower()
    out = []
    for w in re.split(r"[^\w]+", t):
        if len(w) < 2:
            continue
        if _AR_RX.search(w):
            w = _stem_ar(w)
        out.append(w)
    return out


def _is_binary_sample(head: bytes) -> bool:
    return b"\x00" in head[:2048]


# ---------------------------------------------------------------------------
# WorkspaceIndex — TF-IDF retrieval over code chunks
# ---------------------------------------------------------------------------

class WorkspaceIndex:
    def __init__(self, data_dir: Path | None = None):
        self._dd = Path(data_dir) if data_dir else _data_dir()
        self.chunks: list[dict] = []
        self.df: Counter = Counter()
        self.root = ""

    # -- building -----------------------------------------------------------
    def build(self, root: str | Path) -> dict:
        """Walk a project with hard bounds; chunk every text file."""
        root = Path(root)
        self.root = str(root)
        self.chunks, self.df = [], Counter()
        n_files = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if n_files >= MAX_FILES or len(self.chunks) >= MAX_CHUNKS:
                    break
                p = Path(dirpath) / fn
                if p.suffix.lower() in BINARY_EXT or p.suffix == "":
                    continue
                try:
                    if p.stat().st_size > MAX_FILE_KB * 1024:
                        continue
                    with p.open("rb") as f:
                        head = f.read(2048)
                    if _is_binary_sample(head):
                        continue
                    text = p.read_text(encoding="utf-8", errors="replace")
                except (OSError, PermissionError):
                    continue
                n_files += 1
                self._chunk(p, text)
        self._compute_df()
        stats = {"files": n_files, "chunks": len(self.chunks), "root": self.root}
        self.save()
        return stats

    def _chunk(self, p: Path, text: str) -> None:
        lines = text.splitlines()
        step = CHUNK_LINES - CHUNK_OVERLAP
        for i in range(0, len(lines), step):
            part = lines[i:i + CHUNK_LINES]
            if not part or not "\n".join(part).strip():
                continue
            self.chunks.append({
                "path": p.name, "full": str(p), "l0": i + 1,
                "l1": i + len(part), "text": "\n".join(part),
            })
            if len(self.chunks) >= MAX_CHUNKS:
                break

    def _compute_df(self) -> None:
        self.df = Counter()
        for c in self.chunks:
            self.df.update(set(tokenize(c["text"])))

    # -- retrieval ----------------------------------------------------------
    def search(self, query: str, k: int = 6) -> list[dict]:
        q = [t for t in tokenize(query) if t]
        if not q or not self.chunks:
            return []
        n = len(self.chunks)
        scored = []
        for idx, c in enumerate(self.chunks):
            tf = Counter(tokenize(c["text"]))
            s = 0.0
            for t in q:
                if tf.get(t):
                    s += tf[t] * math.log(1 + n / (1 + self.df.get(t, 0)))
            if s > 0:
                scored.append((s, idx, c))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for s, _idx, c in scored[:k]:
            out.append({"path": c["path"], "lines": f"{c['l0']}-{c['l1']}",
                        "score": round(s, 2),
                        "snippet": c["text"][:600]})
        return out

    # -- persistence --------------------------------------------------------
    def _path(self) -> Path:
        return self._dd / "workspace_index.json"

    def save(self) -> None:
        try:
            self._dd.mkdir(parents=True, exist_ok=True)
            slim = [{k: c[k] for k in ("path", "full", "l0", "l1", "text")}
                    for c in self.chunks]
            self._path().write_text(json.dumps(
                {"root": self.root, "ts": time.time(), "chunks": slim},
                ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001, S110 — memory must never crash serving
            pass

    def load(self) -> bool:
        try:
            d = json.loads(self._path().read_text(encoding="utf-8"))
            self.root = d.get("root", "")
            self.chunks = d.get("chunks", [])
            self._compute_df()
            return bool(self.chunks)
        except Exception:  # noqa: BLE001
            return False


# ---------------------------------------------------------------------------
# LessonStore — experience memory from REAL runs (successes + failures)
# ---------------------------------------------------------------------------

class LessonStore:
    def __init__(self, data_dir: Path | None = None):
        self._dd = Path(data_dir) if data_dir else _data_dir()
        self.path = self._dd / "lessons.jsonl"

    def record(self, task: str, ok: bool, tools: list[str] | None = None,
               steps: int = 0, note: str = "") -> dict:
        entry = {"ts": round(time.time(), 3), "task": task[:300], "ok": bool(ok),
                 "tools": (tools or [])[:12], "steps": steps, "note": note[:400]}
        try:
            self._dd.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:  # noqa: BLE001, S110 — lessons must never break runs
            pass
        return entry

    def _all(self) -> list[dict]:
        try:
            return [json.loads(l) for l in
                    self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        except Exception:  # noqa: BLE001
            return []

    def recall(self, task: str, k: int = 4) -> list[str]:
        """Most relevant past lessons, successes ranked above failures,
        failures phrased as things to AVOID. [] when no history — honestly."""
        lessons = self._all()
        if not lessons:
            return []
        q = set(tokenize(task))
        scored = []
        for i, l in enumerate(lessons):
            text = " ".join([l.get("task", ""), " ".join(l.get("tools", [])),
                             l.get("note", "")])
            toks = set(tokenize(text))
            overlap = len(q & toks) / max(1, len(q))
            scored.append((overlap + (0.15 if l.get("ok") else 0.0), i, l))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out = []
        for s, _i, l in scored[:k]:
            if s <= 0:
                continue
            mark = "نجحت" if l.get("ok") else "فشلت"
            avoid = "" if l.get("ok") else " — تجنَّب تكرار هذا المسار"
            tools = "،".join(l.get("tools", [])[:6]) or "بلا أدوات"
            out.append(f"[{mark}] مهمة مشابهة: {l['task'][:120]} | أدوات: "
                       f"{tools} | خطوات: {l.get('steps', 0)}{avoid}")
        return out


# ---------------------------------------------------------------------------
# Style learning — obey the project's conventions, like Copilot does
# ---------------------------------------------------------------------------

def learn_style(root: str | Path) -> dict:
    """Sample source files and infer: indent, quotes, naming, comment lang."""
    root = Path(root)
    ind_tabs = ind_spaces = dq = sq = snake = camel = 0
    arabic_comments = 0
    sampled = 0
    try:
        it = list(root.rglob("*"))[:1500] if root.exists() else []
    except OSError:
        it = []
    for p in it:
        if p.suffix.lower() not in SRC_EXT or sampled >= 30:
            continue
        try:
            if p.stat().st_size > 120 * 1024:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
        except (OSError, PermissionError):
            continue
        sampled += 1
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if line.startswith("    "):
                ind_spaces += 1
            elif line.startswith("\t"):
                ind_tabs += 1
            if stripped.startswith(("#", "//")) and re.search("[\u0600-\u06ff]", stripped):
                arabic_comments += 1
            if re.match(r'^[\w\.]+\s*=\s*"', line) or '("' in line or "('" in line:
                dq += line.count('"')
                sq += line.count("'")
        snake += len(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))
        camel += len(re.findall(r"\b[a-z]+[A-Z][a-zA-Z]*\b", text))
    if sampled == 0:
        return {}
    return {
        "files": sampled,
        "indent": "tab" if ind_tabs > ind_spaces else "spaces",
        "quotes": "double" if dq >= sq else "single",
        "naming": "snake_case" if snake >= camel else "camelCase",
        "arabic_comments": arabic_comments > 0,
    }


def render_style_rules(style: dict) -> str:
    if not style:
        return ""
    rules = [(f"- المسافة البادئة: {' tab' if style['indent'] == 'tab' else 'مسافات'}"
              f"- علامات الاقتباس: {'مزدوجة' if style['quotes'] == 'double' else 'مفردة'}"
              f"- التسمية: {style['naming']}")]
    if style.get("arabic_comments"):
        rules.append("- التعليقات بالعربية كما في المشروع")
    return "- التزم بأسلوب المشروع: " + "؛ ".join(rules)


# ---------------------------------------------------------------------------
# The brief — one block the agent's system prompt receives before planning
# ---------------------------------------------------------------------------

def _data_dir() -> Path:
    base = os.environ.get("OSV_DATA_DIR") or os.path.join(
        os.environ.get("TEMP", "."), "osv_data")
    d = Path(base) / "memory"
    d.mkdir(parents=True, exist_ok=True)
    return d


def memory_root() -> Path:
    """Which project the agent learns from. OSV_MEMORY_ROOT env wins."""
    r = os.environ.get("OSV_MEMORY_ROOT", "")
    return Path(r) if r else Path(__file__).resolve().parent


def brief_for_task(task: str, index: WorkspaceIndex, lessons: LessonStore,
                   style: dict | None = None) -> str:
    """Retrieve-and-compose: relevant code + relevant experience + style."""
    parts = []
    hits = index.search(task, k=5)
    if hits:
        lines = ["📚 سياق مسترجع من مشروعك (الأعلى صلة):"]
        for h in hits:
            lines.append(f"- {h['path']}:{h['lines']} — {h['snippet'][:220]}")
        parts.append("\n".join(lines))
    recalled = lessons.recall(task, k=4)
    if recalled:
        parts.append("🧠 خبرة OSS من جولاتك السابقة:\n" +
                     "\n".join(f"- {r}" for r in recalled))
    s = style or learn_style(index.root or memory_root())
    rules = render_style_rules(s)
    if rules:
        parts.append("🎨 " + rules)
    if not parts:
        return ""
    brief = "\n\n".join(parts)
    return brief[:MAX_BRIEF_CHARS]


def record_run(task: str, ok: bool, tools: list[str] | None = None,
               steps: int = 0, note: str = "") -> None:
    """The feedback loop's write side — called after every real agent run."""
    LessonStore().record(task, ok, tools, steps, note)
