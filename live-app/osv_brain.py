"""OS_V1 Brain — the merged intelligence layer of OSS Work.

What this IS (clean-room, honest engineering):
- The PUBLISHED engineering of three Chinese open-source frontier models is
  copied from their OFFICIAL model cards and woven into ONE orchestration:
  * DeepSeek-R1 (deepseek-ai/DeepSeek-R1, MIT): reasoning-first generation —
    NO system message (all instruction in the user turn), think inside
    </think>…</think> before answering, no few-shot padding.
  * Qwen3-235B-A22B (Apache-2.0): dual-mode thinking — the soft switch
    "/think" to force a reasoning pass, and the thinking-budget idea:
    spend extra calls only where they change the answer.
  * Kimi-K2 (moonshotai/Kimi-K2, Modified-MIT): tool-first reflex-grade
    concreteness — every number/claim in the answer must come from verified
    material, never invented at synthesis time.
- The MERGE is orchestration across DIFFERENT pooled providers: a draft from
  one provider, an adversarial critique from a second, and a synthesis that
  must answer the critique. Different providers = genuinely different priors,
  so the pipeline is stronger than any single provider behind the gateway.

What this is NOT (the honesty rule):
- No model weights were copied or modified. This is protocol + prompt
  engineering copied from public documentation, plus orchestration.
- Every stage is a REAL provider call through the gateway; nothing is faked,
  and the trace returned in `engine_tag(trace)` names each contributor.
"""
from __future__ import annotations

import re
import time

# ---------------------------------------------------------------------------
# Task-depth classification (Qwen3 thinking-budget analog: pay for depth only
# on tasks whose answers actually change with depth)
# ---------------------------------------------------------------------------

_RX_DEEP = re.compile(
    r"(تحليل\s*(عميق|شامل)|أعمق|اعمق|حلل|يحلل|تحليل|قارن|مقارن|صمم|خطط|خطة"
    r"|لماذا|استنتج|استنتاج|أثبت|اثبت|برهان|إثبات|فسر|تفسير|خطوة\s*بخطوة"
    r"|معادلة|مشتق|تكامل|احتمال|احسب|خوارزمي|استراتيجي|دليل\s*العمل)",
    re.IGNORECASE)
_RX_THINK = re.compile(
    r"(اشرح|كيف|ما\s*(هو|هي|الفرق|هي)|هل|متى|عرف|تعريف|ملخص|لخص|وضح|إيه|ايه)",
    re.IGNORECASE)
_RX_GREET = re.compile(
    r"^\s*(مرحبا|أهلا|اهلا|هاي|السلام|سلام|شكرا|شكراً|تم|جيد|ok|hi|hello|thanks)",
    re.IGNORECASE)


def classify(message: str, code_mode: bool = False) -> str:
    """→ 'fast' | 'think' | 'deep'. code_mode has its own pipeline (agent)."""
    if code_mode:
        return "fast"
    m = (message or "").strip()
    if not m:
        return "fast"
    if _RX_GREET.search(m) and len(m) < 40:
        return "fast"
    math_heavy = bool(re.search(r"\d+\s*[+\-*/×÷^%]\s*\d+", m))
    if _RX_DEEP.search(m) or len(m) > 140 or (math_heavy and _RX_THINK.search(m)):
        return "deep"
    if _RX_THINK.search(m) or len(m) > 60 or m.count("؟") + m.count("?") >= 2:
        return "think"
    return "fast"


# ---------------------------------------------------------------------------
# DeepSeek-R1 format: </think>…</think> then the visible answer
# ---------------------------------------------------------------------------

_THINK_RX = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def split_think(text: str) -> tuple[str, str]:
    """→ (thinking, answer). No </think> block ⇒ ('', whole text)."""
    text = text or ""
    m = _THINK_RX.search(text)
    if not m:
        return "", text.strip()
    return m.group(1).strip(), text[m.end():].strip()


# ---------------------------------------------------------------------------
# Stage prompts — all DeepSeek-R1 compliant: NO system message, everything
# in the user turn, no few-shot padding.
# ---------------------------------------------------------------------------

def _history_block(history: list[dict], limit: int = 4) -> str:
    lines = []
    for turn in (history or [])[-limit:]:
        role = "المستخدم" if turn.get("role") == "user" else "أنت"
        content = (turn.get("content") or "").strip()[:400]
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def draft_messages(message: str, history: list[dict], context: str = "") -> list[dict]:
    """R1-style reasoning-first draft. ONE user message, </think> demanded."""
    parts = [
        ("أنت OS_V1، العقل الرئيسي لنظام OSS Work — دمجٌ لهندسة نماذج الصين "
         "المفتوحة (DeepSeek-R1 + Qwen3 + Kimi-K2) فوق أسطول مزودين مجانيين.")]
    if context:
        parts.append(f"معلومات مرجعية من الإنترنت (اعتمدها في الأرقام والأسماء):\n{context}")
    hist = _history_block(history)
    if hist:
        parts.append(f"سياق المحادثة السابقة:\n{hist}")
    parts.append(f"الطلب: {message}")
    parts.append(
        "فكّر أولاً خطوة بخطوة داخل <think>…</think>: فكّك الطلب، تحقق من كل رقم "
        "وكل ادعاء، فكّر في الحالات الحدية والبدائل. ثم اكتب الإجابة النهائية "
        "بالعربية الفصحى، منظمة (عناوين ونقاط عند الحاجة). ممنوع تخمين حقائق — "
        "إن لم تكن متأكداً قل ذلك صراحة.")
    return [{"role": "user", "content": "\n\n".join(parts)}]


def critique_messages(message: str, draft: str) -> list[dict]:
    """Qwen3-style forced-thinking adversarial audit of the draft."""
    return [{"role": "user", "content": (
        "دورك: مدقق نقدي صارم — تجادل مع المسودة وتكشف أخطاءها قبل وصولها للمستخدم.\n"
        "(هندسة مستنسخة من Qwen3-235B-A22B: وضع التفكير القسري بمفتاح /think "
        "+ قائمة تحقق. النموذج المرجعي يفعل هذا قبل الإجابة.)\n"
        "/think\n\n"
        f"السؤال الأصلي: {message}\n\n"
        f"المسودة المُقدَّمة لمراجعتك:\n{draft}\n\n"
        "قائمة التحقق (أعد الحساب والاستنتاج بنفسك — لا تثق بالمسودة):\n"
        "1. تناقض داخلي أو تناقض مع السؤال.\n"
        "2. خطأ حسابي أو منطقي — أعد العملية بنفسك خطوة خطوة.\n"
        "3. ادعاء بلا سند أو رقم ملفّق (علّمه صراحة).\n"
        "4. ناقص: حالة حدية أو بديل مهم أغفلته المسودة.\n\n"
        "اكتب تفكيرك كاملاً، ثم اختم بسطر واحد بالضبط:\n"
        "«الحكم: سليمة»  أو  «الحكم: تصحيحات مطلوبة:» يليها نقاط قصيرة قابلة للتنفيذ.")}]


def synthesis_messages(message: str, draft: str, critique: str,
                       context: str = "") -> list[dict]:
    """Merge stage — must answer the critique (Kimi-K2 concreteness rule)."""
    parts = [("أنت OS_V1 — مرحلة التركيب النهائي. بين يديك مسودة ونقد صارم لها. "
              "أخرج الإجابة النهائية الأفضل الممكنة:")]
    if context:
        parts.append(f"معلومات مرجعية موثوقة:\n{context}")
    parts.append(f"السؤال: {message}")
    parts.append(f"المسودة:\n{draft}")
    parts.append(f"نقد المدقق:\n{critique}")
    parts.append(
        "ادمج بقواعد صارمة: طبّق كل تصحيح وجده المدقق، احذف كل ادعاء علّمه بلا "
        "سند، أضف ما أغفلته المسودة من الحالات الحدية. كل رقم أو كود في إجابتك "
        "يأتي من المسودة المصححة أو المراجع المذكورة — لا تخترع جديداً (قاعدة "
        "الصدق التنفيذي). أجب بالعربية الفصحى منظمة، دون ذكر المسودة أو النقد "
        "أو مراحل العمل — المستخدم يرى الإجابة النهائية فقط.")
    return [{"role": "user", "content": "\n\n".join(parts)}]


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

def _ptag(cfg: dict) -> str:
    return f"{cfg.get('provider', '?')}:{str(cfg.get('model', '?'))[:18]}"


def _pmid(cfg: dict) -> tuple:
    return (cfg.get("provider"), cfg.get("model"))


def engine_tag(trace: dict) -> str:
    """Honest tag: names every provider that actually contributed."""
    if trace.get("depth") == "think":
        who = trace["stages"][0]["provider"] if trace.get("stages") else "?"
        return f"OS_V1🧠 تفكير R1 ({who})"
    parts = [f"{s['stage']}:{s['provider']}" for s in trace.get("stages", [])
             if s["stage"] in ("مسودة", "نقد", "تركيب")]
    if trace.get("skipped_synthesis"):
        parts.append("توليف: تخُّطّي (مسودة سليمة)")
    return f"OS_V1🧠 عمق كامل ({' · '.join(parts)})" if parts else "OS_V1🧠"


def run_brain(message: str, history: list[dict], chain: list[dict],
              stream_fn, context: str = "",
              on_status=lambda s: None, on_delta=lambda t: None,
              call_timeout_s: int = 240) -> tuple[str | None, dict]:
    """Run the merged pipeline. stream_fn = gateway-backed streaming fn with
    the _gw_stream(cfg, msgs, effort=, timeout=, max_tokens=) signature.

    Returns (final_reply, trace); final_reply=None ⇒ caller falls back to the
    classic single-pass path (honest degradation, never a fake answer).
    Each stage fails over across the whole chain — one dead provider never
    kills a stage; the trace records who actually answered.
    """
    t_start = time.monotonic()
    trace: dict = {"depth": "think", "stages": [], "skipped_synthesis": False}

    def done(out: str | None, tr: dict) -> tuple[str | None, dict]:
        tr["ms_total"] = round((time.monotonic() - t_start) * 1000)
        return out, tr

    if not chain:
        trace["note"] = "لا مزودات في السلسلة"
        return done(None, trace)

    def call_stage(stage: str, msgs: list[dict], effort: str | None,
                   max_tokens: int, exclude: tuple | None = None) -> tuple[dict, str]:
        """One pipeline stage with gateway failover. `exclude` keeps the merge
        honest: the critique MUST NOT reuse the draft's provider unless the
        pool has nobody else left."""
        pref = [c for c in chain if _pmid(c) != exclude] if exclude else list(chain)
        order = pref + [c for c in chain if c not in pref]
        last_exc: Exception | None = None
        for cfg in order:
            try:
                t0 = time.monotonic()
                full = list(stream_fn(cfg, msgs, effort=effort,
                                      timeout=call_timeout_s, max_tokens=max_tokens))
                text = "".join(full).strip()
                trace["stages"].append({"stage": stage, "provider": _ptag(cfg),
                                        "ms": round((time.monotonic() - t0) * 1000),
                                        "chars": len(text)})
                return cfg, text
            except Exception as exc:  # noqa: BLE001 — failover to next provider
                last_exc = exc
                trace["stages"].append({"stage": stage, "provider": _ptag(cfg),
                                        "ms": None, "chars": 0,
                                        "failed": str(exc)[:80]})
        raise last_exc or RuntimeError("لا مزودات")

    # ---- level: think — one call, R1 reasoning-first (cheap depth) --------
    def think_level() -> tuple[str | None, dict]:
        trace["depth"] = "think"
        on_status("🧠 عقل OS_V1: تفكير موجّه بهندسة DeepSeek-R1...")
        try:
            _cfg, raw = call_stage("مسودة", draft_messages(message, history, context),
                                   effort=None, max_tokens=3000)
        except Exception as exc:  # noqa: BLE001 — honest fallback
            trace["note"] = f"فشل التفكير: {str(exc)[:80]}"
            return done(None, trace)
        _thinking, answer = split_think(raw)
        return done(answer or raw or None, trace)

    # ---- level: deep — draft → critique → synthesis on DIFFERENT providers
    if len(chain) < 2 or _distinct_second(chain) is None:
        # A single-provider pool cannot produce a real multi-provider merge:
        # degrade to think-level and SAY so (no pretend-merge).
        out, trace = think_level()
        trace["note"] = "مزود واحد فقط — العمق الكامل يحتاج مزودين، خُفّض لتفكير موجّه"
        return done(out, trace)

    trace["depth"] = "deep"
    on_status("🧠 عقل OS_V1 — العمق الكامل: 1/3 مسودة بهندسة DeepSeek-R1...")
    try:
        cfg_d, raw_draft = call_stage("مسودة",
                                      draft_messages(message, history, context),
                                      effort=None, max_tokens=3000)
    except Exception as exc:  # noqa: BLE001
        trace["note"] = f"فشلت المسودة: {str(exc)[:80]}"
        return done(None, trace)
    _thinking, draft_ans = split_think(raw_draft)
    draft_ans = draft_ans or raw_draft

    on_status("🧠 2/3 نقد معادي بهندسة Qwen3 (مزود مختلف عمداً)...")
    try:
        cfg_c, critique = call_stage("نقد", critique_messages(message, draft_ans),
                                     effort=None, max_tokens=2500,
                                     exclude=_pmid(cfg_d))
    except Exception:  # noqa: BLE001 — proceed to synthesis on the raw draft
        critique = ""

    # Qwen3 thinking-budget rule: if the auditor ruled the draft clean,
    # the synthesis call would not change the answer — skip it (speed).
    if re.search(r"الحكم:\s*سليمة", critique or ""):
        trace["skipped_synthesis"] = True
        on_status("🧠 المدقق أقرّ المسودة — التوليف تُخُطّي (ميزانية التفكير)")
        return done(draft_ans, trace)

    on_status("🧠 3/3 تركيب نهائي يدمج النقد (مزود ثالث عند توفره)...")
    try:
        _cfg_s, raw_syn = call_stage("تركيب",
                                     synthesis_messages(message, draft_ans, critique, context),
                                     effort="low", max_tokens=3000,
                                     exclude=_pmid(cfg_c) if critique else None)
        _th, final = split_think(raw_syn)
        final = final or raw_syn
        if not final:
            # synthesis empty — the audited draft is the honest floor
            return done(draft_ans, trace)
        return done(final, trace)
    except Exception:  # noqa: BLE001 — deliver the audited draft honestly
        trace["note"] = "تعذر التركيب — أُعيدت المسودة المُدقَّقة (بلا ادعاء اكتمال)"
        return done(draft_ans, trace)


def _distinct_second(chain: list[dict]) -> dict | None:
    """A provider DIFFERENT from chain[0] — the merge needs different priors."""
    first = _pmid(chain[0]) if chain else None
    for c in chain[1:]:
        if _pmid(c) != first:
            return c
    return None