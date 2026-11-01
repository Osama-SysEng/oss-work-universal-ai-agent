"""OS_V distill — the agent that grows by using itself.

Every successful run is a trajectory; every repeated shape of success is a
RECIPE. Recipes are distilled (one cheap LLM call after qualifying runs),
stored locally, retrieved by short-root Arabic keyword matching (lesson 22:
"راج" catches راجع/مراجعة/تراجع), and injected into future prompts — the
owned capability that gets STRONGER with usage, independent of any provider.

Trajectories double as the seed SFT dataset: every honest (task, steps,
result) triple logged today is training data for the model we may own
tomorrow. No success is ever recorded that the gates did not confirm."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_MIN_FILES_FOR_RECIPE = 2
_MAX_RECIPES = 200
_ROOT_LEN = 4           # short Arabic roots match their derivatives


def _dir() -> Path:
    d = Path(__file__).resolve().parent / "data" / "distill"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------- trajectories

def record_trajectory(task: str, ok: bool, tools: list[str],
                      files: list[str], final_note: str) -> bool:
    """One JSONL line per run — the honest ledger (and future SFT seed)."""
    try:
        line = json.dumps({
            "ts": time.time(), "task": (task or "")[:300], "ok": bool(ok),
            "tools": tools[:12], "files": [f for f in files if f][:20],
            "note": (final_note or "")[:220]},
            ensure_ascii=False)
        with open(_dir() / "trajectories.jsonl", "ab") as f:
            f.write(line.encode("utf-8") + b"\n")
        return True
    except OSError:
        return False                     # learning never breaks serving


def _read_trajectories(limit: int = 400) -> list[dict]:
    p = _dir() / "trajectories.jsonl"
    if not p.is_file():
        return []
    out = []
    try:
        with open(p, "rb") as f:
            for raw in f.read().splitlines()[-limit:]:
                try:
                    out.append(json.loads(raw.decode("utf-8")))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
    except OSError:
        return []
    return out


# -------------------------------------------------------------------- recipes

def _roots(text: str) -> set[str]:
    """Arabic/latin words → short roots (lesson 22: the keyword must be
    derived FROM what the user types). Attached prefixes are stripped first
    (ال، و، ف، ب، ك، ل) — "ومراجعة" is "مراجعة" not a "ومرا" word; both
    hamza forms collapse; ة/ه collapse."""
    stop = {"من", "في", "على", "عن", "الى", "هذا", "هذه", "that",
            "with", "this", "from", "file", "ملف", "الملف", "الملفات"}
    words = re.findall(r"[\w\u0600-\u06FF]{3,}", (text or "").lower())
    out = set()
    for w in words:
        w = (w.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
              .replace("ة", "ه").replace("ى", "ي"))
        for pre in ("وال", "فال", "بال", "كال", "لل", "ال", "و", "ف", "ب",
                    "ك", "ل"):
            if w.startswith(pre) and len(w) - len(pre) >= 3:
                w = w[len(pre):]
        root = w[:_ROOT_LEN]
        if root and root not in stop:
            out.add(root)
    return out


def load_recipes() -> list[dict]:
    p = _dir() / "recipes.json"
    if not p.is_file():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save_recipes(recipes: list[dict]) -> None:
    (_dir() / "recipes.json").write_text(
        json.dumps(recipes[-_MAX_RECIPES:], ensure_ascii=False, indent=1),
        encoding="utf-8")


def recipes_for(task: str, k: int = 3) -> list[dict]:
    """Top-k recipes whose trigger roots overlap the task's roots — direct
    hit OR substring containment both ways (راجع ⊂ مراجع), min 3 chars so a
    one-letter coincidence can never match."""
    need = _roots(task)
    if not need:
        return []
    scored = []
    for r in load_recipes():
        overlap = 0
        for rr in r.get("roots", []):
            if rr in need or len(rr) >= 3 and any(len(w) >= 3 and (rr in w or w in rr)
                                      for w in need):
                overlap += 1
        if overlap:
            scored.append((overlap, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _n, r in scored[:k]]


def inject(recipes: list[dict]) -> str:
    """The prompt block — a recipe is a SUGGESTION proven once, not an order
    (the model may adapt it; it may not fake that it followed it)."""
    if not recipes:
        return ""
    lines = [("\n🧬 وصفات نجحت سابقاً من مكتبة أوس (اقتراح تكيّفه — لا تقل "
              "إنك اتبعتها حرفياً):")]
    for r in recipes:
        steps = " → ".join(f"{i+1}) {s}" for i, s in
                           enumerate(r.get("steps", [])[:6]))
        lines.append(f"• {r.get('name', 'وصفة')}: {steps}")
    return "\n".join(lines)


# ---------------------------------------------------------------- distillation

def _recipe_prompt(task: str, tools: list[str], files: list[str]) -> list[dict]:
    return [{"role": "user", "content":
             "من هذه المهمة المنجزة، استخرج وصفة قابلة لإعادة الاستخدام. أجب "
             "بـ JSON فقط في كتلة ```json``` بالشكل:\n"
             '{"name": "اسم قصير", "trigger_keywords": ["كلمات مفتاحية عربية"],'
             ' "steps": ["خطوة فعلية 1", "خطوة فعلية 2"]}\n'
             f"المهمة: {task[:200]}\nالأدوات المستخدمة: {', '.join(tools[:8])}\n"
             f"الملفات المنتجة: {', '.join(files[:10])}"}]


def distill_from_run(task: str, files: list[str], chain: list[dict],
                     gw_stream) -> dict | None:
    """ONE cheap call after a qualifying run (ok, ≥2 files). Bad JSON / no
    chain / any failure → honest None. The recipe that enters the library is
    the one that parsed and validated — never the one we wished for."""
    if not chain or len([f for f in files if f]) < _MIN_FILES_FOR_RECIPE:
        return None
    if len(load_recipes()) >= _MAX_RECIPES:
        return None
    raw = ""
    for cfg in chain:
        try:
            raw = "".join(gw_stream(cfg, _recipe_prompt(task, [], files),
                                    effort="low", timeout=60,
                                    max_tokens=600)).strip()
            if raw:
                break
        except Exception:  # noqa: BLE001, S112 — next provider / give up quietly
            continue
    if not raw:
        return None
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    name = str(obj.get("name", "")).strip()[:60]
    steps = [str(s).strip()[:120] for s in obj.get("steps", []) if str(s).strip()]
    keys = [str(k).strip()[:30] for k in obj.get("trigger_keywords", [])
            if str(k).strip()]
    if not name or len(steps) < 2:
        return None
    recipe = {"name": name, "steps": steps[:8],
              "roots": sorted(_roots(name + " " + " ".join(keys + [task]))),
              "ts": time.time()}
    recipes = load_recipes()
    if any(r.get("name") == name for r in recipes):
        return None                      # dedupe: same-name recipe exists
    recipes.append(recipe)
    _save_recipes(recipes)
    return recipe


def stats() -> dict:
    trajs = _read_trajectories()
    oks = [t for t in trajs if t.get("ok")]
    return {"trajectories": len(trajs), "successful": len(oks),
            "recipes": len(load_recipes())}
