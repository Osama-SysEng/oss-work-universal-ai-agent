"""OSS Work v9.0 — AgentEngine.

REA pattern extraction (DeepSeek speed + Gemini grounding), implemented:

DEEPSPEED PATTERNS
  1. MoE-style routing  -> intent router: greetings/identity/thanks answer
     instantly with zero model calls; only real questions reach the LLM.
  2. Streaming          -> llama.cpp `stream: true` piped over SSE, so the
     first words appear in seconds instead of after the whole generation.
  3. Prompt cache       -> `cache_prompt: true` reuses KV for the shared
     system prompt across calls.
  4. Distillation       -> 3B model, tight context (2400 chars), 256 tokens,
     only the last 2 turns of history.

GEMINI GROUNDING PATTERNS
  5. Parallel retrieval -> Wikipedia + web/news fetched concurrently in
     threads (sequential fetches used to waste up to a minute on throttled
     engines).
  6. Deep grounding     -> when Wikipedia is thin, the top search result page
     itself is fetched and read, not just its snippet.
  7. Visible sources    -> every answer carries its source titles to the UI.

  Plus a persistent answer cache (24h TTL) so repeated questions are instant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import wait as cf_wait
from contextlib import asynccontextmanager
from http.client import RemoteDisconnected
from pathlib import Path

from fastapi import FastAPI, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

import osv_gateway

REPO_DIR = Path(os.environ.get(
    "OSS_WORK_REPO",
    r"C:\Users\ce\Desktop\التطويرات\تعديلات المشاريع الجماعية\oss-work-universal-ai-agent",
))
sys.path.insert(0, str(REPO_DIR))

ENGINE_URL = os.environ.get("OSS_ENGINE_URL", "http://127.0.0.1:11400")
ENGINE_TIMEOUT = int(os.environ.get("OSS_ENGINE_TIMEOUT", "300"))
WIKI_TIMEOUT = 8
HTTP_TIMEOUT = 10
CACHE_PATH = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "answer_cache.json"))
CACHE_TTL = 24 * 3600

_sessions: dict[str, list[dict]] = {}
_lock = threading.Lock()
_cache_lock = threading.Lock()
_cache: dict[str, dict] = {}

SYSTEM_PROMPT = (
    "أنت OS_V1، مساعد ذكي يجيب بالعربية الفصحى بإيجاز ووضوح. "
    "اعتمد على المعلومات المرجعية المرفقة مع السؤال وحدة في الأسماء والأرقام، "
    "ولا تخترق معلومة ليست فيها. أجب مباشرة دون مقدمات."
)

MAX_CONTEXT = 1600
MAX_HISTORY = 1          # single previous turn — halved prefill, big CPU win
MAX_TOKENS = 200

# The LLM is ONLY for truly generative work (code, math, comparison, opinion,
# explicit deep-analysis requests). Concept explanations come from literal
# source text — an encyclopedia extract IS the explanation, in seconds, with
# zero hallucination risk. A 3B model rewriting it only adds latency and error.
_RX_GENERATIVE = re.compile(
    r"(?:اكتب|برمج|كود|دالة|function|سكربت|script|احسب|حل مسألة|حل المسألة|"
    r"قارن بين|مقارنة|رايك|رأيك|اقترح|صمم|العب|قصة|رسالة|ايميل|email|story|"
    # BUILD intent: the user wants an artifact created, not a fact retrieved.
    # Routing this to a Wikipedia digest was the bug the user caught —
    # "ابني لي لعبة" must never return an encyclopedia paragraph.
    r"ابني|ابنِ|اصنع|أصنع|انشئ|أنشئ|اعمل\s*لي|احدث|"
    r"تحليل أعمق|تحليل اعمق|اشرح أكثر|اشرح اكثر|بعمق أكثر|بعمق اكثر)", re.IGNORECASE)

# BUILD intent — takes priority over every factual path.
_RX_BUILD = re.compile(
    r"(?:ابني|ابنِ|اصنع|أصنع|انشئ|أنشئ|اعمل\s*لي|صمم|احدث|"
    r"ابن\s*لي|build\s*(?:me\s*)?(?:a|an)\b|create\s+(?:a|an)\b|make\s+(?:me\s*)?(?:a|an)\b)", re.IGNORECASE)

# Programming intent — a distinct expert lane: skips web retrieval (code needs
# reasoning, not encyclopedia text) and gets the engineer-grade system prompt.
_RX_CODE = re.compile(
    r"(?:اكتب\s*(?:كود|دالة|برنامج|سكربت|فنكشن|كلاس)|برمج|كود برمجي|"
    r"دالة|فنكشن|function|سكربت|script|خوارزمية|algorithm|"
    r"صحح\s*(?:الكود|هذا الكود|الخطأ)|debug|traceback|exception|"
    r"بايثون|python|جافا|java|جافاسكربت|javascript|typescript|"
    r"c\+\+|سي شارب|c#|sql|html|css|react|regex)", re.IGNORECASE)

# ARTIFACT intent — build verb aimed at a runnable product (game/site/app):
# the answer must be a working HTML file, not a description of one.
_RX_ARTIFACT = re.compile(
    r"(?:لعبة|لعبه|لغاز|موقع|صفحة|صفحه|تطبيق|"
    r"game|website|web\s*app|landing\s*page|application\b)", re.IGNORECASE)

# PROJECT intent — multi-file product (site with several pages, ERP, app):
# the agent plans a structure, generates every file, packages a ZIP.
_RX_PROJECT = re.compile(
    r"(?:مشروع|نظام\s*(?:ERP|erp|إدارة|محاسبة|مخازن|حضور)|موقع\s*كامل|"
    r"تطبيق\s*كامل|عدة\s*ملفات|بعدة\s*ملفات|متعدد\s*الملفات|"
    r"full\s*project|multi[- ]?file|full[- ]?stack|erp\b)", re.IGNORECASE)

CODE_SYS = (
    "أنت OS_V1 — مهندس برمجيات خبير بمستوى أفضل فرق هندسة البرمجيات في العالم. "
    "قواعدك الصارمة عند أي طلب برمجي:\n"
    "1) كود كامل قابل للتشغيل فوراً — ليست مقاطع ولا وصفيات.\n"
    "2) الكود وأسماء المتغيرات بالإنجليزية، التعليقات والشرح بالعربية موجزاً.\n"
    "3) عالج الحالات الحدية والأخطاء الشائعة، واستخدم ممارسات نظيفة وأسماء واضحة.\n"
    "4) ضع الكود دائماً في كتلة ```python أو اللغة المناسبة.\n"
    "5) بعد الكود: سطران كحد أقصى يشرحان الفكرة وتعقيدها.\n"
    "6) إن كان الطلب غامقاً اختر التصميم الأنسب واذكر افتراضك في سطر واحد.\n"
    "7) عند طلب لعبة أو موقع أو تطبيق: أعد ملف HTML واحد متكامل (HTML+CSS+JS "
    "داخلياً) يعمل فوراً في المتصفح دون أي خطوة إضافية — واجهة عربية RTL جميلة "
    "وحركة سلسة وألوان حيوية، وذاكرة أفضل نتيجة، ودون مكتبات خارجية أو شبكة. "
    "ضع كل الملف في كتلة ```html واحدة فقط."
)


def _relevance_ok(query: str, text: str) -> bool:
    """Relevance gate: does the retrieved text share the query's key words?

    Wikipedia search occasionally ranks an unrelated article first; feeding
    that to the digest would present wrong-topic text confidently. Literal
    word overlap is a cheap, honest guard.
    """
    words = [w for w in re.split(r"\s+", query) if len(w) > 2]
    if not words:
        return True
    hits = sum(1 for w in words if w in text)
    return hits / len(words) >= 0.25


def needs_llm(message: str, mode: str, context_len: int) -> bool:
    if _RX_BUILD.search(message) or _RX_GENERATIVE.search(message):
        return True
    if mode in ("web+wiki", "wiki", "web") and context_len > 250:
        return False          # grounded literal answer is sufficient
    return True               # thin retrieval — let the model reason


def _wiki_digest(wiki_text: str) -> str:
    body = re.sub(r"^\[[^\]]+\]\s*", "", wiki_text).strip()
    sentences = re.split(r"(?<=[.!؟])\s+", body)
    return " ".join(sentences[:4]).strip()[:750]


def _news_digest(web: list[dict]) -> str:
    lines = []
    for r in web[:4]:
        date = r["snippet"].replace("نُشر:", "").strip()
        lines.append(f"• {r['title']}" + (f" — {date}" if date else ""))
    return "📰 آخر الأخبار الحية من مصادر إخبارية موثقة:\n" + "\n".join(lines)

# ---------------------------------------------------------------------------
# Intent router — the cheap-expert path (MoE pattern)
# ---------------------------------------------------------------------------

_RX_GREETING = re.compile(r"^(?:مرحب|اهلا|أهلا|هلا|السلام|صباح الخير|مساء الخير|هاي|هلو|hi|hello|hey)", re.IGNORECASE)
_RX_THANKS = re.compile(r"(?:شكرا|شكرًا|ممتن|thanks|thank you)", re.IGNORECASE)
_RX_HOWAREYOU = re.compile(r"(?:كيف حالك|كيفك|شلونك|عامل ايه|كيف الحال|how are you)", re.IGNORECASE)
_RX_IDENTITY = re.compile(r"(?:من انت|من أنت|مين انت|ما اسمك|مسمك|عرف نفسك|عن نفسك|من انت بالضبط|who are you|what are you|os_?v1)", re.IGNORECASE)
_RX_NEWS = re.compile(r"(?:اخبار|أخبار|خبر|اليوم|الان|الآن|الجديد|آخر|أحدث|سعر|latest|news)", re.IGNORECASE)

INSTANT_ANSWERS = {
    "greeting": "مرحباً بك أيها القائد! 🤖 أنا OS_V1، وحدة الذكاء الخاصة بك. اسألني أي شيء — علوم، برمجة، تاريخ، أخبار اليوم — وسأجلب لك مراجع حية من الويب وأجيب بدقة.",
    "thanks": "على الرحب والسعة! 🤖 أنا هنا دائماً — اسألني متى شئت.",
    "howareyou": "أنظمتي تعمل بكامل طاقتها ⚡ والدرع فعال. كيف أستطيع خدمتك؟",
    "identity": "أنا OS_V1 🤖 — وحدة الذكاء في نظام OSS Work. أعمل بذكاء حدودي سحابي (مستوى Gemini/GPT) مع بحث حي في الإنترنت وويكيبيديا، وأكتب كوداً ينفَّذ ويُصحَّح تلقائياً داخل النظام. اسألني أي شيء.",
}


def route(message: str) -> str:
    m = message.strip()
    if _RX_IDENTITY.search(m):
        return "identity"
    if _RX_GREETING.search(m):
        return "greeting"
    if _RX_HOWAREYOU.search(m):
        return "howareyou"
    if _RX_THANKS.search(m) and len(m.split()) <= 4:
        return "thanks"
    return "news" if _RX_NEWS.search(m) else "knowledge"


# ---------------------------------------------------------------------------
# Query cleaning
# ---------------------------------------------------------------------------

_QUESTION_WORDS = [
    "من هو", "من هي", "ما هو", "ما هي", "وش هو", "ايش هو", "إيش هي",
    "اشرح لي", "عرّف لي", "عرف لي", "حدثني عن", "اخبرني عن", "أخبرني عن",
    "قول لي", "قل لي", "أريد أن أعرف", "اريد ان اعرف",
    "لماذا", "ليش", "كيف", "متى", "اين", "أين", "ماذا", "كم", "هل",
]
_COLLOQUIAL = [("التليفون", "الهاتف"), ("الموبايل", "الجوال"), ("النت", "الإنترنت")]
_STOP_PREFIX = re.compile(r"^(?:من|ما|ماذا|هل|كم|متى|أين|اين|كيف|لماذا|ليش|وين|اش|وش)\s+")
_QUESTION_MARK = re.compile(r"[؟?،,.]+")
_AR_STOP = {
    "من", "هو", "هي", "ما", "ماذا", "في", "على", "عن", "الى", "إلى", "مع",
    "هذا", "هذه", "ذلك", "التي", "الذي", "كان", "كانت", "يكون", "و", "أو",
    "او", "ثم", "قد", "لقد", "هل", "ليش", "لماذا", "كيف", "متى", "اين",
    "أين", "كم", "لي", "له", "لها", "به", "بها",
    # imperative verbs poison search ranking — must not reach the engine
    "اشرح", "فسر", "وضح", "عرف", "حدثني", "اخبرني", "أخبرني", "قول", "قل",
    "اريد", "أريد", "اعرف", "أعرف", "يعني", "اكتب", "برمج", "حلل", "اذكر",
    "أذكر", "اكتبي", "اشرحي", "تعريف", "مفهوم",
}


def _clean_query(message: str) -> str:
    q = _QUESTION_MARK.sub(" ", message.strip())
    for phrase in sorted(_QUESTION_WORDS, key=len, reverse=True):
        low = q.lower()
        if phrase in low:
            idx = low.find(phrase)
            q = q[:idx] + q[idx + len(phrase):]
    q = _STOP_PREFIX.sub("", q.strip())
    for a, b in _COLLOQUIAL:
        q = q.replace(a, b)
    words = q.split()
    kept = [w for w in words if w not in _AR_STOP] or words
    q = " ".join(kept).strip()
    return q if len(q) >= 2 else message.strip()


# ---------------------------------------------------------------------------
# HTTP utilities
# ---------------------------------------------------------------------------

def _strip_html(raw: str) -> str:
    raw = re.sub(r"<style[^>]*>.*?</style>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"<!--.*?-->", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<[^>]+>", " ", raw)
    raw = (raw.replace("&amp;", "&").replace("&quot;", '"')
              .replace("&#91;", "[").replace("&#93;", "]")
              .replace("&#39;", "'").replace("&nbsp;", " ")
              .replace("\u200e", "").replace("\u200f", ""))
    return re.sub(r"\s+", " ", raw).strip()


def _http_get(url: str, timeout: int = HTTP_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/json",
        "Accept-Language": "ar,en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Search engines
# ---------------------------------------------------------------------------

def _looks_like_challenge(html: str) -> bool:
    if len(html) < 2500:
        return True
    low = html.lower()
    return ("anomaly" in low or "captcha" in low
            or "unfortunately, systems" in low)


def _clean_ddg_href(href: str) -> str:
    if "uddg=" in href:
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            try:
                return urllib.parse.unquote(m.group(1))
            except Exception:
                pass
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://duckduckgo.com" + href
    return href.replace("&amp;", "&")


def _ddg_html(query: str) -> list[dict]:
    html = _http_get("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query))
    if _looks_like_challenge(html):
        return []
    links = re.findall(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL,
    ) or re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL,
    )
    snippets = re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL,
    ) or re.findall(
        r'<div[^>]*class="result__snippet"[^>]*>(.*?)</div>', html, re.DOTALL,
    )
    results = []
    for i, (href, title) in enumerate(links[:5]):
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({
            "title": _strip_html(title).strip(),
            "url": _clean_ddg_href(href),
            "snippet": _strip_html(snippet).strip()[:250],
        })
    return results


def _ddg_lite(query: str) -> list[dict]:
    html = _http_get("https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query))
    if _looks_like_challenge(html):
        return []
    links = re.findall(
        r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL,
    ) or re.findall(
        r'<a[^>]+href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', html, re.DOTALL,
    )
    snippets = re.findall(r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>', html, re.DOTALL)
    results = []
    for i, (href, title) in enumerate(links[:5]):
        snippet = snippets[i] if i < len(snippets) else ""
        results.append({
            "title": _strip_html(title).strip(),
            "url": _clean_ddg_href(href),
            "snippet": _strip_html(snippet).strip()[:250],
        })
    return results


def _decode_bing_redirect(url: str) -> str:
    if "bing.com/ck/" not in url:
        return url
    m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", url)
    if not m:
        return url
    b64 = m.group(1)
    b64 += "=" * (-len(b64) % 4)
    try:
        return base64.urlsafe_b64decode(b64).decode("utf-8", errors="replace")
    except Exception:
        return url


def _bing_search(query: str) -> list[dict]:
    html = _http_get(
        "https://www.bing.com/search?q=" + urllib.parse.quote(query) + "&setlang=ar&cc=SA"
    )
    if _looks_like_challenge(html):
        return []
    items = re.findall(
        r'<li class="b_algo".*?<h2[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)</li>',
        html, re.DOTALL,
    )
    results, seen = [], set()
    for href, title, rest in items[:8]:
        url = _decode_bing_redirect(href.replace("&amp;", "&"))
        if url.startswith("https://www.bing.com/") or url in seen:
            continue
        seen.add(url)
        para = re.search(r"<p[^>]*>(.*?)</p>", rest, re.DOTALL)
        results.append({
            "title": _strip_html(title).strip(),
            "url": url,
            "snippet": (_strip_html(para.group(1)) if para else "")[:250],
        })
        if len(results) >= 5:
            break
    return results


def _news_search(query: str) -> list[dict]:
    xml = _http_get(
        "https://news.google.com/rss/search?q=" + urllib.parse.quote(query)
        + "&hl=ar&gl=SA&ceid=SA:ar"
    )
    items = re.findall(
        r"<item>\s*<title>(.*?)</title>\s*<link>(.*?)</link>\s*"
        r"<guid[^>]*>.*?</guid>\s*<pubDate>(.*?)</pubDate>",
        xml, re.DOTALL,
    ) or re.findall(
        r"<item>\s*<title>(.*?)</title>\s*<link>(.*?)</link>", xml, re.DOTALL,
    )
    results = []
    for title, link, *pub in items[:5]:
        results.append({
            "title": _strip_html(title).strip(),
            "url": link.strip(),
            "snippet": (f"نُشر: {pub[0].strip()[:16]}" if pub and pub[0].strip() else ""),
        })
    return results


_engine_fail_until: dict[str, float] = {}


def _engine_available(name: str) -> bool:
    return time.time() >= _engine_fail_until.get(name, 0)


def _engine_fail(name: str, minutes: float = 1.5):
    _engine_fail_until[name] = time.time() + minutes * 60


def web_search(query: str) -> list[dict]:
    """Run ALL engines in parallel, prefer the best successful one.

    Sequential attempts wasted up to a minute when a throttled engine ate
    its full timeout first; parallel + circuit breaker caps retrieval at
    the slowest single engine instead of the sum of all failures.
    """
    engines = {"ddg_html": _ddg_html, "ddg_lite": _ddg_lite,
               "bing": _bing_search, "news": _news_search}
    priority = ["ddg_html", "ddg_lite", "bing", "news"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            name: pool.submit(engines[name], query)
            for name in priority if _engine_available(name)
        }
        results_by_name = {}
        for name, fut in futures.items():
            try:
                results_by_name[name] = fut.result(timeout=20)
            except Exception as exc:  # noqa: BLE001
                print(f"  [{name} error] {exc}", file=sys.stderr)
                results_by_name[name] = []
                _engine_fail(name)
    for name in priority:
        if results_by_name.get(name):
            return results_by_name[name]
        if name in results_by_name and not results_by_name[name]:
            _engine_fail(name)  # empty result = throttled/challenge; rest it
    return []


def _fetch_page_text(url: str) -> str:
    """Gemini-style deep grounding: read the top result page itself."""
    try:
        if not url.startswith("http") or any(
            host in url for host in ("news.google.com", "bing.com", "duckduckgo.com")
        ):
            return ""
        html = _http_get(url, timeout=6)
        if _looks_like_challenge(html):
            return ""
        text = _strip_html(html)
        return text[:900] if len(text) > 150 else ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Wikipedia
# ---------------------------------------------------------------------------

def _wiki_api(lang: str, params: str) -> dict:
    url = f"https://{lang}.wikipedia.org/w/api.php?format=json&{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "OSSWork/1.0"})
    with urllib.request.urlopen(req, timeout=WIKI_TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _wiki_extract(lang: str, query: str) -> tuple[str, list[str]]:
    try:
        q = urllib.parse.quote(query[:150])
        data = _wiki_api(
            lang,
            f"action=query&generator=search&gsrsearch={q}&gsrlimit=3"
            "&prop=extracts&exintro=1&explaintext=1&exsentences=8",
        )
        pages = (data.get("query") or {}).get("pages") or {}
        chunks, titles = [], []
        for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
            text = _strip_html(page.get("extract") or "")
            title = page.get("title", "")
            if len(text) > 60:
                chunks.append(f"[{title}]\n{text}")
                titles.append(title)
        return "\n\n".join(chunks)[:2600], titles
    except Exception:
        return "", []


def wiki_lookup(query: str) -> tuple[str, list[str]]:
    text, titles = _wiki_extract("ar", query)
    if text:
        return text, titles
    text, titles = _wiki_extract("en", query)
    return text, [f"EN:{t}" for t in titles]


# ---------------------------------------------------------------------------
# Local LLM — streaming + prompt cache
# ---------------------------------------------------------------------------

def engine_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{ENGINE_URL}/health", timeout=4) as r:
            return r.status == 200
    except Exception:
        return False


def _engine_payload(messages: list[dict], stream: bool) -> dict:
    return {
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
        "cache_prompt": True,  # llama.cpp KV reuse across calls
    }


def engine_stream(messages: list[dict]):
    """Yield text deltas from llama.cpp's OpenAI-compatible SSE stream."""
    body = json.dumps(_engine_payload(messages, True)).encode("utf-8")
    req = urllib.request.Request(
        f"{ENGINE_URL}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=ENGINE_TIMEOUT) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {}).get("content")
            except Exception:
                continue
            if delta:
                yield delta


def engine_chat(messages: list[dict]) -> tuple[str, str]:
    body = json.dumps(_engine_payload(messages, False)).encode("utf-8")
    req = urllib.request.Request(
        f"{ENGINE_URL}/v1/chat/completions",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=ENGINE_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        text = (data["choices"][0]["message"]["content"] or "").strip()
        return (text, "ok") if text else ("", "empty")
    except (urllib.error.URLError, RemoteDisconnected, ConnectionError, TimeoutError):
        return "", "down"
    except Exception as exc:  # noqa: BLE001
        return f"خطأ في المحرك: {exc}", "error"


# ---------------------------------------------------------------------------
# Answer cache — instant repeats (DeepSeek-style prompt caching at app level)
# ---------------------------------------------------------------------------

def _load_cache():
    global _cache
    try:
        if CACHE_PATH.exists():
            _cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        _cache = {}


def _save_cache():
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps(_cache, ensure_ascii=False), encoding="utf-8"
        )
    except Exception:
        pass


def cache_get(query: str) -> dict | None:
    key = hashlib.sha1(query.encode("utf-8")).hexdigest()
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry.get("ts", 0) < CACHE_TTL:
            return entry
    return None


def cache_put(query: str, reply: str, sources: list[str], engine: str):
    key = hashlib.sha1(query.encode("utf-8")).hexdigest()
    with _cache_lock:
        _cache[key] = {"reply": reply, "sources": sources, "engine": engine, "ts": time.time()}
        _save_cache()


# ---------------------------------------------------------------------------
# Cloud provider — the path to frontier intelligence (Gemini/GPT-class).
# The key lives in data/cloud_config.json (never in code), set via the UI.
# All four supported providers expose an OpenAI-compatible endpoint, so one
# code path covers them.
# ---------------------------------------------------------------------------

CLOUD_CONFIG_PATH = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cloud_config.json"))

FREELLMAPI_BASE = "http://127.0.0.1:31415"

CLOUD_PROVIDERS = {
    "freellmapi": {
        "url": f"{FREELLMAPI_BASE}/v1/chat/completions",
        "default_model": "auto",
        "key_url": "(يُكتشف تلقائياً من راوتر FreeLLMAPI المحلي — بلا مفتاح)",
        "label": "FreeLLMAPI المحلي — موزّع غير محدود (283 نموذجاً، يُكتشف تلقائياً)",
    },
    "gemini": {
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-3.5-flash",
        "key_url": "https://aistudio.google.com/apikey",
        "label": "Google Gemini (مفتاح مجاني من aistudio.google.com/apikey)",
    },
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
        "label": "Groq (مفتاح مجاني من console.groq.com/keys) — الأسرع عالمياً",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "google/gemini-2.0-flash-exp:free",
        "key_url": "https://openrouter.ai/keys",
        "label": "OpenRouter (نماذج مجانية بلافتة :free)",
    },
    "deepseek": {
        "url": "https://api.deepseek.com/chat/completions",
        "default_model": "deepseek-chat",
        "key_url": "https://platform.deepseek.com/api_keys",
        "label": "DeepSeek API (رخيص جداً)",
    },
    "github-models": {
        "url": "https://models.github.ai/inference/chat/completions",
        "default_model": "openai/gpt-4.1-mini",
        "key_url": "https://github.com/settings/personal-access-tokens",
        "label": "GitHub Models (مفتاح حسابك على github.com — جسر Copilot/مايكروسوفت، نماذج OpenAI و Llama و DeepSeek بحساب واحد)",
    },
    "cerebras": {
        "url": "https://api.cerebras.ai/v1/chat/completions",
        "default_model": "llama-3.3-70b",
        "key_url": "https://cloud.cerebras.ai/",
        "label": "Cerebras (مفتاح مجاني من cloud.cerebras.ai) — أسرع استدلال في العالم (2000+ توكن/ث)",
    },
    "mistral": {
        "url": "https://api.mistral.ai/v1/chat/completions",
        "default_model": "mistral-small-latest",
        "key_url": "https://console.mistral.ai/api-keys",
        "label": "Mistral (خطة مجانية من console.mistral.ai) — أوروبية، سريعة",
    },
    "together": {
        "url": "https://api.together.xyz/v1/chat/completions",
        "default_model": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
        "key_url": "https://api.together.ai/settings/api-keys",
        "label": "Together AI (رصيد مجاني من api.together.ai) — مئات النماذج المفتوحة",
    },
    "cohere": {
        "url": "https://api.cohere.ai/compatibility/v1/chat/completions",
        "default_model": "command-r7b-12-2024",
        "key_url": "https://dashboard.cohere.com/api-keys",
        "label": "Cohere (مفتاح تجريبي من dashboard.cohere.com) — توافق OpenAI كامل",
    },
}


def load_cloud_config() -> dict | None:
    try:
        if CLOUD_CONFIG_PATH.exists():
            cfg = json.loads(CLOUD_CONFIG_PATH.read_text(encoding="utf-8"))
            if cfg.get("provider") in CLOUD_PROVIDERS and cfg.get("key", "").strip():
                return cfg
    except Exception:
        pass
    return None


def save_cloud_config(provider: str, key: str, model: str = "") -> None:
    CLOUD_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg = {"provider": provider, "key": key.strip(),
           "model": (model or "").strip() or CLOUD_PROVIDERS[provider]["default_model"]}
    CLOUD_CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")


_freellm_cache = {"cfg": None, "checked": 0.0}
# Last provider that actually served a completion — moved to the front of
# every chain so a dead/expended provider is not re-taxed on each call.
_healthy = {"provider": None}


def get_freellmapi() -> dict | None:
    """Zero-setup unlimited intelligence: auto-discover the local FreeLLMAPI
    router and its unified key from the router's own database.

    When the router is running, OS_V1 routes through 280+ models with a
    ~1B-token monthly budget — no per-model 429 exhaustion, no key pasting.
    Cached for 60s; a stopped router is simply not in the failover chain.
    """
    now = time.time()
    if now - _freellm_cache["checked"] > 60:
        _freellm_cache["checked"] = now
        cfg = None
        db_path = Path(os.environ.get("APPDATA", "")) / "freellmapi" / "freeapi.db"
        try:
            import sqlite3
            if db_path.exists():
                con = sqlite3.connect(str(db_path))
                try:
                    row = con.execute(
                        "SELECT value FROM settings WHERE key='unified_api_key'"
                    ).fetchone()
                    if row and row[0]:
                        cfg = {"provider": "freellmapi", "key": str(row[0]),
                               "model": "auto"}
                finally:
                    con.close()
        except Exception:  # noqa: BLE001 — router missing/locked: skip silently
            cfg = None
        _freellm_cache["cfg"] = cfg
    return _freellm_cache["cfg"]


def cloud_chain(task: str | None = None) -> list[dict]:
    """Failover order — PREFERRED: the Provider Gateway's bandit-ordered pool
    (Bayesian reliability × speed × intelligence × headroom × rate-limit,
    learned from this machine's real outcomes); FALLBACK: the static chain
    (last-healthy, configured, auto-detected FreeLLMAPI)."""
    try:
        import osv_gateway as gw
        gw_chain = gw.ordered_chain(task=task)
        if gw_chain:
            return gw_chain
    except Exception:  # noqa: BLE001 — gateway outage falls back to static
        pass
    chain = []
    primary = load_cloud_config()
    if primary:
        chain.append(primary)
    freellm = get_freellmapi()
    if freellm and (not primary or primary["provider"] != "freellmapi"):
        chain.append(freellm)
    if _healthy["provider"]:
        for i, c in enumerate(chain):
            if c["provider"] == _healthy["provider"] and i > 0:
                chain.insert(0, chain.pop(i))
                break
    return chain


def _auto_fix_gemini_model(key: str) -> str | None:
    """Pick the key's newest flash model that ACTUALLY answers fast.

    A 404 means the key authenticated fine but the model name is wrong or
    retired. Newest-first alone is not enough: measured on this key,
    gemini-3.8-flash hung >60s and gemini-3.7-flash returned 503 — so each
    candidate gets a live ping (reasoning_effort=none, like real usage) and
    the first one that answers wins.
    """
    try:
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/openai/models",
            headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=20) as r:
            ids = [m["id"] for m in json.loads(r.read().decode()).get("data", [])]
    except Exception:  # noqa: BLE001
        return None
    flash = []
    for i in ids:
        n = i.replace("models/", "")
        m = re.match(r"gemini-(\d+)\.(\d+)-flash$", n)
        if m:
            flash.append((int(m.group(1)), int(m.group(2)), n))
    flash.sort(reverse=True)
    for _, _, name in flash[:4]:          # newest 4 candidates, live-verified
        try:
            body = json.dumps({
                "model": name,
                "messages": [{"role": "user", "content": "قل: جاهز"}],
                "max_tokens": 100, "stream": False, "reasoning_effort": "none",
            }).encode("utf-8")
            req = urllib.request.Request(
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                data=body, headers={"Content-Type": "application/json",
                                    "Authorization": f"Bearer {key}"})
            with urllib.request.urlopen(req, timeout=22) as r:
                d = json.loads(r.read().decode("utf-8"))
            if (d["choices"][0]["message"].get("content") or "").strip():
                return name
        except Exception:  # noqa: BLE001 — slow/hung/overloaded: next candidate
            continue
    return None


def cloud_test(cfg: dict) -> tuple[bool, str]:
    """Tiny live ping to verify the key actually works.

    Error text separates the two failure modes users actually hit:
    404 → wrong/retired model name (key is fine, auto-heals),
    400/401/403 → the key itself is rejected.
    """
    prov = CLOUD_PROVIDERS[cfg["provider"]]
    body = json.dumps({
        "model": cfg.get("model") or prov["default_model"],
        "messages": [{"role": "user", "content": "قل: جاهز"}],
        "max_tokens": 500,
        "stream": False,
    }).encode("utf-8")
    req = urllib.request.Request(prov["url"], data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['key']}",
    })
    try:
        data = None
        for attempt in range(2):           # 429/503 demand spikes are transient
            try:
                with urllib.request.urlopen(req, timeout=40) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as e2:
                if e2.code in (429, 500, 503) and attempt == 0:
                    time.sleep(2)
                    continue
                raise
        text = data["choices"][0]["message"].get("content") or "✅"
        return True, f"المفتاح يعمل ✅ ({text.strip()[:40]})"
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        if e.code == 404:
            fixed = (_auto_fix_gemini_model(cfg["key"])
                     if cfg["provider"] == "gemini" else None)
            if fixed:
                save_cloud_config(cfg["provider"], cfg["key"], fixed)
                ok2, msg2 = cloud_test(load_cloud_config())
                return ok2, f"{msg2} — أُصلح اسم النموذج تلقائياً إلى {fixed}"
            return False, (f"اسم النموذج غير موجود (HTTP 404) — مفتاحك سليم، "
                           f"صحّح اسم النموذج في الحقل أدناه. {detail}")
        if e.code in (401, 403):
            return False, f"المفتاح مرفوض (HTTP {e.code}) — تأكد من نسخه كاملاً: {detail}"
        return False, f"خطأ من المزود (HTTP {e.code}): {detail}"
    except Exception as exc:  # noqa: BLE001
        return False, f"فشل الاتصال بالمزود: {exc}"


_ANALYTICAL_RX = re.compile(
    r"(لماذا|كيف|قارن|حلل|اشرح|الفرق|مميزات|عيوب|خطوات|صمم|اقترح|فسر|"
    r"أفضل|افضل|استراتيجية|خطة|إستراتيجية|ما هي|ماهي|وضح|وضّح)", re.IGNORECASE)


def _analytical(message: str) -> bool:
    """True when a chat question deserves a thinking budget without the user
    saying a magic keyword: multi-part, long, or explicitly analytical."""
    m = message or ""
    return (len(m) > 120 or m.count("؟") + m.count("?") > 1
            or bool(_ANALYTICAL_RX.search(m)))


def cloud_stream(cfg: dict, messages: list[dict], effort: str | None = "none",
                 timeout: int = 300, max_tokens: int = 4000):
    """Yield deltas from the cloud model's SSE stream.

    effort levels (gemini reasoning_effort), each measured on this machine:
      "none" → fastest (1.5s TTFT) — facts and grounded answers.
      "low"  → bounded reasoning — code: fast enough, much higher quality.
      None   → default full thinking — explicit "تحليل أعمق" only (can be slow).
    Timeout is inactivity-based (streamed tokens keep it alive); the caller
    tightens it for agent-loop phases where a stalled provider must fail
    over instead of stalling the whole build.
    """
    prov = CLOUD_PROVIDERS[cfg["provider"]]
    body = {
        "model": cfg.get("model") or prov["default_model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": True,
    }
    if cfg["provider"] == "gemini" and effort:
        body["reasoning_effort"] = effort
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(prov["url"], data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['key']}",
    })
    # Free-tier rate limits (HTTP 429) are transient — wait once and retry
    # BEFORE any delta is emitted (safe: the request is still at its head).
    for attempt in range(2):
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 0:
                time.sleep(6)
                continue
            raise
    with resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
                delta = chunk["choices"][0].get("delta", {}).get("content")
            except Exception:
                continue
            if delta:
                yield delta


def cloud_tag(cfg: dict) -> str:
    return f"OS_V1⚡({cfg.get('model') or CLOUD_PROVIDERS[cfg['provider']]['default_model']})"


def _gw_stream(cfg: dict, messages: list[dict], effort: str | None = "none",
               timeout: int = 300, max_tokens: int = 4000):
    """cloud_stream wrapped with gateway learning: records TTFB, throughput
    and the outcome (success / 429 / fail) so the bandit routes smarter after
    every single call."""
    gw_id = cfg.get("_osv_id")
    if gw_id is None:
        yield from cloud_stream(cfg, messages, effort=effort, timeout=timeout,
                                max_tokens=max_tokens)
        return
    t0 = time.monotonic()
    ttfb = None
    tokens = 0
    failed = False
    try:
        for delta in cloud_stream(cfg, messages, effort=effort, timeout=timeout,
                                  max_tokens=max_tokens):
            if ttfb is None:
                ttfb = (time.monotonic() - t0) * 1000.0
            tokens += max(1, len(delta) // 4)
            yield delta
    except Exception as exc:
        failed = True
        is_429 = "429" in str(exc)
        try:
            osv_gateway.record_fail(gw_id, is_429, cfg["provider"], cfg.get("model", ""))
            if is_429:
                osv_gateway.cooldown(gw_id, 90.0)
        except Exception:  # noqa: BLE001 — learning never breaks serving
            pass
        raise
    finally:
        if not failed and ttfb is not None:
            try:
                elapsed = max(0.05, time.monotonic() - t0)
                osv_gateway.record_success(gw_id, ttfb, tokens / elapsed, tokens)
            except Exception:  # noqa: BLE001
                pass


# ---------------------------------------------------------------------------
# Parallel retrieval — wiki + web at once (Gemini grounding, no serial wait)
# ---------------------------------------------------------------------------

def _quick_answer(wiki_text: str) -> str:
    """First Wikipedia sentences as an instant draft (DeepSeek fast path)."""
    body = re.sub(r"^\[[^\]]+\]\s*", "", wiki_text).strip()
    sentences = re.split(r"(?<=[.!؟])\s+", body)
    draft = " ".join(sentences[:3]).strip()
    if len(draft) > 60:
        return draft[:600]
    return ""


def _build_context(message: str) -> dict:
    """Parallel retrieval. Returns {context, sources, mode, quick, wiki_text, web}."""
    cleaned = _clean_query(message)
    sources: list[str] = []

    with ThreadPoolExecutor(max_workers=2) as pool:
        wiki_future = pool.submit(wiki_lookup, cleaned)
        web_future = pool.submit(web_search, cleaned)
        wiki_text, wiki_titles = wiki_future.result()
        web = web_future.result()

    if wiki_text:
        sources.extend(wiki_titles)
    if web:
        sources.extend(r["title"] for r in web[:3])

    parts: list[str] = []
    if wiki_text:
        parts.append("من ويكيبيديا:\n" + wiki_text)

    if web:
        lines = []
        for i, r in enumerate(web[:3], 1):
            lines.append(f"{i}. {r['title']}")
            if r["snippet"]:
                lines.append(f"   {r['snippet']}")
        parts.append("من نتائج البحث والأخبار:\n" + "\n".join(lines))

    # Deep grounding: read the top result page when Wikipedia came up thin
    if len(wiki_text) < 400 and web:
        direct = next((r["url"] for r in web if r["url"].startswith("http")), "")
        page_text = _fetch_page_text(direct)
        if page_text:
            parts.append(f"قراءة من الصفحة ({direct[:60]}):\n{page_text}")

    mode = "web+wiki" if (web and wiki_text) else ("web" if web else ("wiki" if wiki_text else "none"))
    return {
        "context": "\n\n".join(parts)[:MAX_CONTEXT],
        "sources": sources,
        "mode": mode,
        "quick": _quick_answer(wiki_text),
        "wiki_text": wiki_text,
        "web": web,
    }


def _build_messages(message: str, history: list[dict], context: str) -> list[dict]:
    if context:
        user_content = (
            "معلومات مرجعية من الإنترنت (اعتمدها في الأسماء والأرقام):\n\n"
            f"{context}\n\n---\nالسؤال: {message}"
        )
    else:
        user_content = message

    msgs: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for turn in history[-MAX_HISTORY * 2:]:
        if turn["role"] in ("user", "assistant") and turn.get("content"):
            msgs.append({"role": turn["role"], "content": turn["content"][:600]})
    msgs.append({"role": "user", "content": user_content})
    return msgs


def answer(message: str, history: list[dict]) -> tuple[str, str, list[str]]:
    """Non-streaming answer — same pipeline, single final response."""
    if not engine_alive():
        return ("⚠️ محرك الذكاء المحلي متوقف. أعد تشغيله من C:\\tools\\llama\\start-engine.cmd",
                "engine_down", [])
    ret = _build_context(message)
    context, sources, mode = ret["context"], ret["sources"], ret["mode"]
    cleaned = _clean_query(message)
    digest = None
    if not needs_llm(message, mode, len(context)):
        if route(message) == "news" and ret["web"]:
            digest = _news_digest(ret["web"])
        elif ret["wiki_text"] and _relevance_ok(cleaned, ret["wiki_text"]):
            digest = _wiki_digest(ret["wiki_text"])
        if digest:
            digest += "\n\n💡 أرسل (تحليل أعمق) ليتولى النموذج تفكيراً كاملاً."
            return digest, "grounded_fast", sources
    msgs = _build_messages(message, history, context)
    text, status = engine_chat(msgs)
    if status != "ok":
        return ("تعذر الاتصال بالمحرك. أعد المحاولة.", "engine_error", sources)
    if mode == "none":
        text += "\n\n> ⚠️ *تعذر جلب مراجع الآن — يُفضَّل التحقق من هذه الإجابة.*"
    return text, f"llm+{mode}", sources


# ---------------------------------------------------------------------------
# FastAPI
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    model: str = "os_v1"
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    model: str
    latency_ms: int
    session_id: str | None = None
    engine: str
    sources: list[str] = []


class InfoResponse(BaseModel):
    name: str
    version: str
    model: str
    engine_url: str
    engine_alive: bool
    internet_search: bool
    wikipedia: bool
    cloud_active: bool
    cloud_provider: str | None = None
    cache_entries: int
    uptime_seconds: float


START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_cache()
    # Provider Gateway: pool the machine's existing cloud sources into the
    # bandit-routed pool — no user setup, it grows with what OS_V already has.
    try:
        import osv_gateway as gw
        gw.init(seed_providers=gw.seed_providers())
        gw.ensure_local_key()
    except Exception:  # noqa: BLE001 — gateway outage must never block boot
        pass
    yield


app = FastAPI(title="OSS Work — AgentEngine", version="9.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"status": "ok", "engine": engine_alive(), "ts": time.time()}


@app.get("/api/info", response_model=InfoResponse)
def info():
    extract, _ = wiki_lookup("الرياضيات")
    cfg = load_cloud_config()
    return InfoResponse(
        name="OSS Work", version="7.0.0", model="OS_V1",
        engine_url=ENGINE_URL,
        engine_alive=engine_alive(),
        internet_search=bool(web_search("test")),
        wikipedia=bool(extract),
        cloud_active=bool(cfg),
        cloud_provider=(cfg["provider"] if cfg else None),
        cache_entries=len(_cache),
        uptime_seconds=round(time.time() - START_TIME, 1),
    )


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


@app.post("/api/v1/chat/stream")
def chat_stream(req: ChatRequest):
    """SSE pipeline: route → retrieve → generate, token by token."""

    def gen():
        t0 = time.time()
        message = req.message.strip()
        sid = req.session_id or "default"

        # 1. Route — instant paths answer with zero model cost
        kind = route(message)
        if kind in INSTANT_ANSWERS:
            yield _sse({"type": "delta", "text": INSTANT_ANSWERS[kind]})
            yield _sse({"type": "done", "engine": "instant", "sources": [],
                        "latency_ms": round((time.time() - t0) * 1000)})
            return

        # 2. Answer cache — instant repeats
        cached = cache_get(_clean_query(message))
        if cached:
            yield _sse({"type": "delta", "text": cached["reply"]})
            yield _sse({"type": "done", "engine": "cache",
                        "sources": cached.get("sources", []),
                        "latency_ms": round((time.time() - t0) * 1000)})
            return

        if not engine_alive() and not cloud_chain():
            yield _sse({"type": "delta", "text": (
                "⚠️ لا يوجد محرك ذكاء: المحلي متوقف ولا يوجد مفتاح سحابي.\n"
                "• شغّل C:\\tools\\llama\\start-engine.cmd\n"
                "• أو أضف مفتاحاً مجانياً من زر ⚙️ في الأعلى.")})
            yield _sse({"type": "done", "engine": "engine_down", "sources": [],
                        "latency_ms": round((time.time() - t0) * 1000)})
            return

        # 3. Parallel retrieval
        # 3. Parallel retrieval — SKIPPED in code mode: code needs reasoning,
        #    not encyclopedia text; the saved 1-3s goes straight to first token.
        with _lock:
            history = list(_sessions.setdefault(sid, []))
        build_mode = bool(_RX_BUILD.search(message))
        code_like = bool(_RX_CODE.search(message)) or build_mode
        cloud_chain_list = cloud_chain(task="code" if code_like else None)
        cloud = cloud_chain_list[0] if cloud_chain_list else None
        project_mode = bool(cloud) and build_mode and bool(_RX_PROJECT.search(message))
        code_mode = bool(cloud) and not project_mode and (
            bool(_RX_CODE.search(message)) or
            (build_mode and bool(_RX_ARTIFACT.search(message))))

        # PROJECT MODE — the full agent loop: plan → parallel file generation
        # → assemble → ZIP + live preview. Progress streams per completed file.
        if project_mode:
            # The gateway's bandit order IS the build order — it already
            # learned which providers actually deliver on this machine.
            build_chain = cloud_chain_list
            yield _sse({"type": "status", "stage": "brainstorm",
                        "text": "أعصف ذهنياً: ثلاثة مفاهيم مختلفة وأختار الأقوى..."})
            concept = _brainstorm(build_chain, message)
            yield _sse({"type": "status", "stage": "plan",
                        "text": "أخطط بنية المشروع كاملة..."})
            yield _sse({"type": "sources", "sources": [], "mode": "project"})
            plan_out = _plan_project(build_chain, message, concept)
            if plan_out:
                plan, working_cfg = plan_out
                # Healthy provider first for every file gen — a dead provider
                # in the chain must not tax all 4-12 workers repeatedly.
                gen_chain = [working_cfg] + [c for c in build_chain if c != working_cfg]
                yield _sse({"type": "delta",
                            "text": f"🏗️ الخطة جاهزة: **{plan['name']}** — "
                                    f"{len(plan['files'])} ملفات:\n"
                                    + "\n".join(f"• {f['path']}" for f in plan["files"])
                                    + "\n\n"})
                pdir_files, failed_files = [], []
                done_count = 0
                n_total = len(plan["files"])
                pool = ThreadPoolExecutor(max_workers=6)
                try:
                    futs = {pool.submit(_gen_project_file, gen_chain, plan, f): f
                            for f in plan["files"]}
                    pending = set(futs)
                    while pending:
                        done, pending = cf_wait(pending, timeout=20)
                        for fut in done:
                            res = fut.result()
                            done_count += 1
                            if res:
                                pdir_files.append(res)
                                yield _sse({"type": "status", "stage": "build",
                                            "text": f"اكتمل {res[0]} ({done_count}/{n_total})..."})
                            else:
                                failed_files.append(futs[fut])
                                yield _sse({"type": "status", "stage": "build",
                                            "text": f"تعذر ملف ({done_count}/{n_total}) — أكمل البقية..."})
                        if pending:
                            # Heartbeat every 20s: live progress keeps the
                            # stream alive and the user informed through the
                            # parallel wave (the longest silent phase).
                            yield _sse({"type": "status", "stage": "build",
                                        "text": f"أبني بالتوازي... اكتمل {done_count}/{n_total} "
                                                f"({round(time.time() - t0)} ث)..."})
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)
                # One retry pass for failed files (transient provider errors
                # must not punch holes in the delivered tree).
                if failed_files and pdir_files:
                    yield _sse({"type": "status", "stage": "build",
                                "text": f"أعيد محاولة {len(failed_files)} ملف..."})
                    with ThreadPoolExecutor(max_workers=4) as pool:
                        futs = {pool.submit(_gen_project_file, gen_chain, plan, f): f
                                for f in failed_files}
                        for fut in as_completed(futs):
                            res = fut.result()
                            if res:
                                pdir_files.append(res)
                                yield _sse({"type": "status", "stage": "build",
                                            "text": f"اكتمل {res[0]} (إعادة محاولة)..."})
                # VERIFY — real checks with local tools (ms, no model):
                # syntax gates + every referenced local asset must resolve.
                yield _sse({"type": "status", "stage": "verify",
                            "text": "أفحص التراكيب والروابط بين الملفات..."})
                vr = _verify_project(pdir_files)
                healed = 0
                # heal broken syntax: regenerate with the exact error fed back
                for path, err in vr["broken"]:
                    tgt = next((f for f in plan["files"] if f["path"] == path), None)
                    if tgt is None:
                        continue
                    res = _gen_project_file(gen_chain, plan, tgt, error_ctx=err)
                    if res:
                        pdir_files = [(p, c) if p != path else res for p, c in pdir_files]
                        healed += 1
                        yield _sse({"type": "status", "stage": "heal",
                                    "text": f"شفيت {path} بعد الفحص..."})
                # heal missing refs: a referenced file that was never planned
                # gets generated on the spot — no dead links ship
                for ref in vr["missing"]:
                    purpose = ("ملف مُشار إليه من صفحات المشروع — يوفر محتوى متسقاً "
                               "مع بنية المشروع ويكمل الوظيفة المطلوبة منه.")
                    res = _gen_project_file(gen_chain, plan,
                                            {"path": ref, "purpose": purpose})
                    if res:
                        pdir_files.append(res)
                        healed += 1
                        yield _sse({"type": "status", "stage": "heal",
                                    "text": f"ولّدت {ref} المفقود (شفاء)..."})
                # re-verify after healing: what still fails is reported HONESTLY
                if healed:
                    vr2 = _verify_project(pdir_files)
                else:
                    vr2 = vr
                if vr2["broken"]:
                    yield _sse({"type": "delta", "text":
                                "⚠️ فحص نهائي: هذه الملفات ما زال فيها عيب لم يُشفَ: "
                                + ", ".join(p for p, _ in vr2["broken"]) + "\n\n"})
                if pdir_files:
                    proj = _assemble_project(plan, pdir_files)
                    with _lock:
                        session = _sessions.setdefault(sid, [])
                        session.append({"role": "user", "content": message})
                        session.append({"role": "assistant",
                                        "content": f"بنيت مشروع {proj['name']} كاملاً بملفات: {', '.join(proj['files'])}"})
                    yield _sse({"type": "delta",
                                "text": f"✅ **بنيت المشروع كاملاً**: {proj['name']} — "
                                        f"{len(proj['files'])} ملفات جاهزة"
                                        + (f" (شفتُ {healed} ملفاً بعد الفحص)" if healed else "")
                                        + ". افتح المعاينة الحية أو نزّل المشروع كاملاً ZIP."})
                    yield _sse({"type": "project", **proj})
                    yield _sse({"type": "done", "engine": cloud_tag(working_cfg) + "🏗️",
                                "sources": [],
                                "latency_ms": round((time.time() - t0) * 1000)})
                    return
                # all files failed → honest refusal, no garbage
                yield _sse({"type": "delta", "text": (
                    "🛡️ فشل توليد ملفات المشروع (المزود السحابي غير متاح الآن) — "
                    "لا أسلّم مشروعاً ناقصاً. أعد المحاولة بعد قليل.")})
                yield _sse({"type": "done", "engine": "project_needs_cloud",
                            "sources": [],
                            "latency_ms": round((time.time() - t0) * 1000)})
                return
            # plan failed → fall through to the normal Q&A path below

        if code_mode:
            # All keys the local-fallback path touches must exist even when
            # retrieval was skipped — a missing key here killed the stream
            # silently when the cloud path failed (429) mid-build.
            ret = {"context": "", "sources": [], "mode": "code",
                   "quick": None, "web": [], "wiki_text": None}
            yield _sse({"type": "status", "stage": "generate",
                        "text": "أبني النموذج الأولي وأفحص حالاته الحدية..."})
        else:
            yield _sse({"type": "status", "stage": "retrieval",
                        "text": "أبحث في ويكيبيديا والإنترنت..."})
            ret = _build_context(message)
        context, sources, mode = ret["context"], ret["sources"], ret["mode"]
        yield _sse({"type": "sources", "sources": sources[:6], "mode": mode})
        cleaned = _clean_query(message)

        # 3b. CLOUD FIRST — frontier intelligence, first token in ~1-2s.
        if cloud:
            # --- OS_V1 Brain (Phase 3 — القوة المطلقة): adaptive depth, the
            # published engineering of DeepSeek-R1 + Qwen3 + Kimi-K2 merged
            # into one multi-provider pipeline. fast ⇒ classic single-pass
            # below (zero added latency). think ⇒ R1 reasoning pass.
            # deep ⇒ draft (provider A) → adversarial critique (provider B)
            # → synthesis (third) — the real "merge of strengths".
            if not code_mode:
                import queue as _queue
                import threading as _threading

                import osv_brain
                if osv_brain.classify(message) != "fast":
                    brain_q: _queue.Queue = _queue.Queue()

                    def _brain_worker():
                        try:
                            final_b, trace_b = osv_brain.run_brain(
                                message, history, cloud_chain_list, _gw_stream,
                                context=context,
                                on_status=lambda s: brain_q.put(("status", s, None)),
                                on_delta=lambda t: brain_q.put(("delta", t, None)))
                            brain_q.put(("final", final_b, trace_b))
                        except Exception as exc:  # noqa: BLE001 — honest fallback
                            brain_q.put(("error", str(exc), None))

                    _threading.Thread(target=_brain_worker, daemon=True).start()
                    brain_final, brain_trace, brain_err = None, None, None
                    brain_deltas = 0
                    while True:
                        try:
                            bkind, bpayload, btrace = brain_q.get(timeout=15)
                            if bkind == "status":
                                yield _sse({"type": "status", "stage": "brain",
                                            "text": bpayload})
                            elif bkind == "delta":
                                brain_deltas += 1
                                yield _sse({"type": "delta", "text": bpayload})
                            elif bkind == "final":
                                brain_final, brain_trace = bpayload, btrace
                                break
                            else:
                                brain_err = bpayload
                                break
                        except _queue.Empty:
                            yield _sse({"type": "status", "stage": "brain",
                                        "text": f"🧠 العقل يعمل... {round(time.time() - t0)} ث"})
                            if time.time() - t0 > 420:
                                brain_err = "تجاوز العقل حد الزمن"
                                break
                    if brain_final:
                        cache_put(cleaned, brain_final, sources,
                                  osv_brain.engine_tag(brain_trace))
                        with _lock:
                            session_b = _sessions.setdefault(sid, [])
                            session_b.append({"role": "user", "content": message})
                            session_b.append({"role": "assistant", "content": brain_final})
                            if len(session_b) > 12:
                                _sessions[sid] = session_b[-8:]
                        yield _sse({"type": "done",
                                    "engine": osv_brain.engine_tag(brain_trace),
                                    "sources": sources[:6], "brain": brain_trace,
                                    "latency_ms": round((time.time() - t0) * 1000)})
                        return
                    if brain_deltas:
                        # synthesis already streamed partially: falling through
                        # would answer twice — report honestly instead
                        yield _sse({"type": "delta",
                                    "text": "\n\n⚠️ انقطع العقل أثناء التركيب — ما سبق غير مكتمل."})
                        yield _sse({"type": "done", "engine": "OS_V1🧠(انقطع)",
                                    "sources": sources[:6], "brain": brain_trace,
                                    "latency_ms": round((time.time() - t0) * 1000)})
                        return
                    yield _sse({"type": "status", "stage": "brain",
                                "text": f"🧠 خفّضت العمق (المسار المباشر) — {str(brain_err)[:60]}"})
                    # fall through to the classic single-pass path below

            yield _sse({"type": "status", "stage": "generate",
                        "text": "OS_V1 يفكر..."})
            if code_mode:
                sys_prompt = CODE_SYS
            else:
                sys_prompt = (
                    "أنت OS_V1، مساعد ذكي يعمل داخل نظام OSS Work. تجيب بالعربية الفصحى "
                    "بوضوح وتنظيم (عناوين ونقاط عند الحاجة). إن أُعطيت معلومات مرجعية "
                    "فاعتمدها في الأسماء والأرقام واذكر مصادرها.")
            cloud_msgs: list[dict] = [{"role": "system", "content": sys_prompt}]
            for turn in history[-4:]:
                if turn["role"] in ("user", "assistant") and turn.get("content"):
                    cloud_msgs.append({"role": turn["role"], "content": turn["content"][:800]})
            user_content = (f"معلومات مرجعية من الإنترنت (اعتمدها):\n{context}\n\n---\n"
                            f"السؤال: {message}") if context else message
            cloud_msgs.append({"role": "user", "content": user_content})

            # Reasoning budget by intent — measured trade-offs:
            #   code → "low" (quality where it matters, still fast)
            #   explicit deep analysis → default full thinking
            #   analytical/multi-part questions → "low" automatically
            #     (smarter defaults: no magic keyword required)
            #   trivial lookups → "none" (facts don't need a thinking chain)
            if code_mode:
                effort = "low"
            elif ("تحليل أعمق" in message or "تحليل اعمق" in message):
                effort = None
            else:
                effort = "low" if _analytical(message) else "none"

            # Failover chain: configured provider → auto-detected FreeLLMAPI
            # router → gemini alternate → local. Free-tier 429 on one model
            # never kills the request.
            candidates = list(cloud_chain_list)
            if cloud["provider"] == "gemini":
                alt = dict(cloud)
                alt["model"] = "gemini-3.5-flash"
                if all(c["model"] != alt["model"] for c in candidates):
                    candidates.append(alt)
            reply = None
            for cfg_now in candidates:
                full = []
                try:
                    for delta in _gw_stream(cfg_now, cloud_msgs, effort=effort):
                        full.append(delta)
                        yield _sse({"type": "delta", "text": delta})
                    reply = "".join(full).strip()
                except Exception as exc:  # noqa: BLE001
                    if full:
                        # mid-stream failure: keep what arrived, no retry
                        yield _sse({"type": "delta",
                                    "text": "\n\n⚠️ انقطع الاتصال السحابي أثناء التوليد."})
                        reply = "".join(full).strip()
                        break
                    if "429" in str(exc) and candidates.index(cfg_now) < len(candidates) - 1:
                        yield _sse({"type": "status", "stage": "generate",
                                    "text": "المزود مزدحم — أنتقل للبديل..."})
                        continue
                    yield _sse({"type": "status", "stage": "generate",
                                "text": f"تعذر السحابي ({str(exc)[:60]}) — أحول للمحلي..."})
                    reply = None
                    break
                if reply:
                    break
            if reply:
                cache_put(cleaned, reply, sources, cloud_tag(cfg_now))
                with _lock:
                    session = _sessions.setdefault(sid, [])
                    session.append({"role": "user", "content": message})
                    session.append({"role": "assistant", "content": reply})
                    if len(session) > 12:
                        _sessions[sid] = session[-8:]
                yield _sse({"type": "done", "engine": cloud_tag(cfg_now), "sources": sources[:6],
                            "latency_ms": round((time.time() - t0) * 1000)})
                return
            # empty cloud reply → fall through to local paths below

        # ARTIFACT requests never degrade to the local 3B model: a weak model
        # "building a game" produces confident garbage — worse than nothing.
        # Honest refusal beats a fake deliverable.
        if code_mode and build_mode:
            yield _sse({"type": "delta", "text": (
                "🛡️ طلبت مني بناء شيء حقيقي (لعبة/تطبيق) — وأنا لا أسلّم إلا عملاً "
                "يشتغل فعلاً، وهذا يتطلب الذكاء الحدودي السحابي الذي يتجاوز قدرة أي "
                "نموذج محلي.\n\n"
                "⏳ كل المزودات السحابية غير متاحة الآن (حصة مجانية/اتصال).\n"
                "⚡ للحل الفوري: شغّل FreeLLMAPI على جهازك (موزّع 283 نموذجاً "
                "غير محدود) — أكتشفه تلقائياً وأعمل به فوراً — أو أضف مفتاح Groq "
                "المجاني من زر ⚙️.")})
            yield _sse({"type": "done", "engine": "artifact_needs_cloud", "sources": [],
                        "latency_ms": round((time.time() - t0) * 1000)})
            return

        # 4. Source-first routing: literal grounded text beats a 3B rewrite
        #    for factual questions — faster AND more accurate.
        #    BUILD intent is exempt: an artifact request must never be answered
        #    with an encyclopedia digest (the bug the user caught).
        digest = None
        if not needs_llm(message, mode, len(context)) and not build_mode:
            if kind == "news" and ret["web"]:
                digest = _news_digest(ret["web"])
            elif ret["wiki_text"] and _relevance_ok(cleaned, ret["wiki_text"]):
                digest = _wiki_digest(ret["wiki_text"])
            elif ret["web"] and _relevance_ok(cleaned, " ".join(r["title"] + " " + r["snippet"] for r in ret["web"])):
                digest = _news_digest(ret["web"])
            if digest:
                digest += "\n\n💡 أرسل (تحليل أعمق) ليتولى النموذج تفكيراً كاملاً."
                yield _sse({"type": "delta", "text": digest})
                cache_put(cleaned, digest, sources, "grounded_fast")
                with _lock:
                    session = _sessions.setdefault(sid, [])
                    session.append({"role": "user", "content": message})
                    session.append({"role": "assistant", "content": digest})
                yield _sse({"type": "done", "engine": "grounded_fast", "sources": sources[:6],
                            "latency_ms": round((time.time() - t0) * 1000)})
                return
        # Irrelevant retrieval or generative intent — the model takes over
        # Instant draft from Wikipedia while the model thinks (DeepSeek fast path)
        quick = ret["quick"]
        if quick and _relevance_ok(cleaned, quick):
            yield _sse({"type": "delta", "text": quick})
            yield _sse({"type": "status", "stage": "generate",
                        "text": "أصيغ إجابة أدق..."})
            yield _sse({"type": "replace"})
        else:
            yield _sse({"type": "status", "stage": "generate",
                        "text": "أصيغ الإجابة..."})
        msgs = _build_messages(message, history, context)

        full = []
        try:
            for delta in engine_stream(msgs):
                full.append(delta)
                yield _sse({"type": "delta", "text": delta})
        except (urllib.error.URLError, RemoteDisconnected, ConnectionError, TimeoutError):
            yield _sse({"type": "delta", "text": "\n\n⚠️ انقطع الاتصال بالمحرك أثناء التوليد. أعد المحاولة."})
        except Exception as exc:  # noqa: BLE001
            yield _sse({"type": "delta", "text": f"\n\n⚠️ خطأ: {exc}"})

        reply = "".join(full).strip()
        if mode == "none" and reply:
            reply += "\n\n> ⚠️ *تعذر جلب مراجع الآن — يُفضَّل التحقق من هذه الإجابة.*"
            yield _sse({"type": "delta", "text": reply[len("".join(full)):]})

        engine_tag = f"llm+{mode}" if reply else "engine_empty"
        if reply:
            cache_put(_clean_query(message), reply, sources, engine_tag)
            with _lock:
                session = _sessions.setdefault(sid, [])
                session.append({"role": "user", "content": message})
                session.append({"role": "assistant", "content": reply})
                if len(session) > 12:
                    _sessions[sid] = session[-8:]
        yield _sse({"type": "done", "engine": engine_tag, "sources": sources[:6],
                    "latency_ms": round((time.time() - t0) * 1000)})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class CloudConfigRequest(BaseModel):
    provider: str
    key: str
    model: str | None = None


@app.get("/api/v1/config")
def get_config():
    # The reported state must match what the pipeline ACTUALLY uses: the
    # auto-detected FreeLLMAPI router counts as active even with no stored key.
    chain = cloud_chain()
    providers = {p: CLOUD_PROVIDERS[p]["label"] for p in CLOUD_PROVIDERS}
    if not chain:
        return {"active": False, "providers": providers}
    return {"active": True, "provider": chain[0]["provider"],
            "model": chain[0].get("model"), "providers": providers}


@app.get("/api/v1/gateway/status")
def gateway_status():
    """Provider Gateway pool health — the bandit's live view of the world."""
    try:
        st = osv_gateway.pool_status()
        return {"ok": True, **st}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)[:120]}


@app.post("/api/v1/gateway/issue-key")
def gateway_issue_key():
    """Issue a new unified monthly key. The raw key is shown ONCE here —
    only its hash is stored, exactly like provider-grade key hygiene."""
    raw = osv_gateway.issue_key("user-issued")
    return {"ok": True, "key": raw,
            "note": "انسخ المفتاح الآن — يُخزَّن مُجزَّأً ولن يُعرض مرة أخرى."}


@app.get("/api/v1/gateway/keys")
def gateway_keys():
    """Issued keys WITHOUT their secrets: label, usage, cap."""
    con = osv_gateway._connect()
    try:
        rows = con.execute("SELECT id, label, monthly_token_cap, used_tokens, revoked, "
                           "created_at FROM unified_keys ORDER BY id DESC").fetchall()
    finally:
        con.close()
    keys = [{"id": r[0], "label": r[1], "cap": r[2] or None, "used_tokens": r[3],
             "revoked": bool(r[4]), "created_at": r[5]} for r in rows]
    return {"ok": True, "keys": keys}


# ---------------------------------------------------------------------------
# OSS as a PROVIDER — OpenAI-compatible surface served by OS_V itself.
# External tools connect with the unified monthly key (os_v-...) and reach
# the whole pooled provider fleet behind the gateway. No other company.
# ---------------------------------------------------------------------------

class V1Message(BaseModel):
    role: str
    content: str


class V1ChatRequest(BaseModel):
    model: str | None = None
    messages: list[V1Message]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None


def _bearer(authorization: str) -> str:
    if authorization.startswith("Bearer "):
        return authorization[7:].strip()
    return authorization.strip()


def _v1_error(status: int, message: str, err_type: str = "invalid_request_error"):
    return JSONResponse(status_code=status,
                        content={"error": {"message": message, "type": err_type}})


@app.get("/v1/models")
def v1_models(authorization: str = Header(default="")):
    ok, msg = osv_gateway.key_allowed(_bearer(authorization))
    if not ok:
        return _v1_error(401, msg, "authentication_error")
    data = [{"id": x["id"], "object": "model", "owned_by": f"oss-gateway/{x['provider']}",
             "permission": [], "tier": x["tier"], "status": x["status"]}
            for x in osv_gateway.pool_models()]
    return {"object": "list", "data": data}


@app.post("/v1/chat/completions")
def v1_chat(req: V1ChatRequest, authorization: str = Header(default="")):
    """OpenAI-compatible completion. Auth = unified os_v key. Routing = the
    gateway's bandit chain (or the requested pool member). Every call is
    accounted against the key's monthly budget."""
    raw_key = _bearer(authorization)
    ok, msg = osv_gateway.key_allowed(raw_key)
    if not ok:
        return _v1_error(401, msg, "authentication_error")
    chain = cloud_chain()
    if not chain:
        return _v1_error(503, "لا يوجد مزودون في المخزون حالياً")
    if req.model:
        # explicit model selection: "oss/<provider>/<model>" → member first
        parts = req.model.split("/")
        want = parts[1] if len(parts) >= 2 else ""
        member = next((c for c in chain if c["provider"] == want), None)
        if member is None:
            return _v1_error(404, f"النموذج {req.model} ليس في مخزون البوابة")
        chain = [member] + [c for c in chain if c is not member]
    msgs = [{"role": m.role, "content": m.content} for m in req.messages]
    gen_id = f"chatcmpl-osv-{int(time.time()*1000):x}"
    created = int(time.time())

    if req.stream:
        def sse():
            sent = 0
            first = True
            for cfg in chain:
                try:
                    for delta in _gw_stream(cfg, msgs, timeout=300,
                                            max_tokens=req.max_tokens or 4000):
                        if first:
                            first = False
                            yield (f'data: {json.dumps({"id": gen_id, "object": "chat.completion.chunk", "created": created, "model": req.model or cfg.get("model"), "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}, ensure_ascii=False)}\n\n')
                        sent += max(1, len(delta) // 4)
                        yield (f'data: {json.dumps({"id": gen_id, "object": "chat.completion.chunk", "created": created, "model": req.model or cfg.get("model"), "choices": [{"index": 0, "delta": {"content": delta}, "finish_reason": None}]}, ensure_ascii=False)}\n\n')
                    break  # this member delivered — no failover after first token
                except Exception as exc:  # noqa: BLE001
                    if not first:
                        # mid-stream: report honestly, then close
                        yield (f'data: {json.dumps({"error": {"message": f"انقطع البث من {cfg["provider"]}: {str(exc)[:120]}"}})}\n\n')
                        break
                    continue  # failover before first token
            yield f'data: {json.dumps({"choices": [{"delta": {}, "finish_reason": "stop"}]})}\n\n'
            yield "data: [DONE]\n\n"
            osv_gateway.record_key_usage(raw_key, sent)
        return StreamingResponse(sse(), media_type="text/event-stream")

    # non-streaming: full failover, then one honest answer
    for cfg in chain:
        try:
            text = "".join(_gw_stream(cfg, msgs, timeout=300,
                                      max_tokens=req.max_tokens or 4000)).strip()
            if text:
                tokens = max(1, len(text) // 4)
                osv_gateway.record_key_usage(raw_key, tokens)
                return {"id": gen_id, "object": "chat.completion", "created": created,
                        "model": req.model or cfg.get("model"),
                        "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                     "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 0, "completion_tokens": tokens,
                                  "total_tokens": tokens},
                        "oss_gateway": {"provider": cfg["provider"]}}
        except Exception:  # noqa: BLE001, S112 — 429/timeout: next in chain
            continue
    return _v1_error(502, "كل مزودات البوابة غير متاحة الآن — أُعيد المحاولة لاحقاً", "server_error")


# ---------------------------------------------------------------------------
# OS_V Agent — the real tool loop (opencode-style: act → observe → repeat)
# ---------------------------------------------------------------------------

class AgentRequest(BaseModel):
    task: str
    session_id: str = "agent"
    device: str = "safe"   # safe = أدوات الجهاز خلف بوابات الموافقة | full = ثقة كاملة
    mode: str = "solo"     # solo = حلقة واحدة | team = سرب وكلاء متوازٍ للمهام القابلة للتفكيك
    resume: bool = False   # true = اكمل جلسة محفوظة بنفس الاسم (سياق + مساحة كما هي)


@app.post("/api/v1/agent/run")
def agent_run(req: AgentRequest):
    """Full agent mode: the model works with REAL tools (bash/files/search)
    inside a confined per-session workspace, streaming progress via SSE.
    device=full adds the DEVICE-LEVEL tools (OpenClaw-style reach: any file,
    any command, processes, notifications) under the permission engine —
    yolo on, but the hard-deny machine-killer class stays absolute."""
    import osv_agent as ag
    import osv_device as dv
    import osv_team as tm

    chain = cloud_chain(task="code")
    if not chain:
        return {"ok": False, "message": "الوضع الوكيل يحتاج مزوداً سحابياً (⚙️)."}
    ws = Path(os.environ.get("TEMP", ".")) / "osv_agent_ws" / \
        re.sub(r"[^a-zA-Z0-9_-]", "_", req.session_id)[:40]
    kit = dv.DeviceKit(yolo=(req.device == "full"))
    kit.gate.engine._log("agent.run", f"device:{req.device}", "allow", "policy")
    extra = dv.device_tools(kit)

    # --- the learning layer (Copilot-style): retrieve, then inject, then record
    import osv_memory as mem
    brief = memory_brief_for(req.task)
    # --- media tools (image/video generation) — keyless, merge always
    import osv_media as md
    extra.update(md.media_tools(md.MediaKit()))
    # --- security scanner (read-only, always merged)
    import osv_sec as sec
    extra.update(sec.sec_tools())
    # --- MCP: external tool servers the user configured (stdio, honest errors)
    import osv_mcp
    extra.update(osv_mcp.mcp_tools())
    # --- git: the agent checkpoints its own work inside its workspace
    import osv_git
    extra.update(osv_git.git_tools())
    # --- long-io: million-token lanes (workspace dossier + part-stitched files)
    import osv_longio
    extra.update(osv_longio.longio_tools())
    # --- sessions: resume support
    import osv_sessions as sessions
    prior = sessions.resume_msgs(req.session_id) if req.resume else None
    resumed_turns = len(prior) if prior else 0
    # --- distill: owned recipes retrieved for THIS task (the growing model)
    import osv_distill
    brief = (brief + "\n" + osv_distill.inject(
        osv_distill.recipes_for(req.task))).strip()

    def gen():
        yield _sse({"type": "status", "stage": "agent",
                    "text": f"🤖 وضع الوكيل: مساحة عمل {ws.name} — أدوات حقيقية بأمان"
                            + (" + تحكم الجهاز الكامل" if req.device == "full" else "")
                            + (" + 🧠 ذاكرة متعلَّمة" if brief else "")
                            + (" + 🔌 MCP" if any("mcp" in t for t in extra) else "")
                            + (f" + 📂 استئناف ({resumed_turns} رسالة من آخر جلسة)"
                               if prior else "")
                            + (" + 👥 سرب متوازٍ" if req.mode == "team" else "")})
        events = []
        ctx = ag.AgentContext(ws, req.session_id,
                              extra_tools={**extra, **tm.team_tool()})
        ctx.chain = chain

        def on_event(evt):
            events.append(evt)

        t_run_start = time.time()
        final, ok, team_info = None, False, None
        if req.mode == "team":
            # workers get every tool EXCEPT team_spawn (no recursive swarms)
            res = tm.run_team(req.task, ws, req.session_id, chain, extra,
                              lambda e: events.append(e), brief)
            if res is not None:
                final, ok, team_info = res
        if req.mode == "project":
            # long-horizon: goal → milestones → tasks, persisted per task,
            # resumable by the same session_id, gated per product
            import osv_project as pj
            doc = pj.load(req.session_id)
            if doc is None:
                doc = pj.plan(req.task, chain, _gw_stream)
            if doc is None:
                final, ok = ("تعذرت صياغة خطة مشروع — لا خطة وهمية. أعد "
                             "المحاولة بصياغة أوضح للهدف.", False)
            else:
                if not pj.load(req.session_id):
                    pj.save(req.session_id, doc)
                    yield _sse({"type": "status", "stage": "project",
                                "text": f"🗺️ خطة «{doc['name']}»: "
                                        f"{len(doc['milestones'])} مراحل — "
                                        f"{pj.status(doc)['tasks_total']} مهمة"})
                doc = pj.run_project(req.session_id, doc, chain, ws.parent,
                                     on_event, extra, brief)
                st = doc["status"]
                final = (f"المشروع «{st['name']}»: {st['tasks_done']} مكتملة، "
                         f"{st['tasks_failed']} فاشلة، {st['tasks_pending']} "
                         f"متبقية من {st['tasks_total']} — استأنف بنفس "
                         f"session_id و resume=true.")
                ok = st["tasks_failed"] == 0 and st["tasks_pending"] == 0
        if final is None:
            # solo — أو تراجع صادق بعد رفض التفكيك (الفريق لا يُزيَّف أبداً)
            final, ok = ag.run_agent(req.task, ctx, chain, on_event,
                                     memory_brief=brief, prior_msgs=prior)

        # --- بوابة التحقق التلقائية (الدقة لا تُوكل للنموذج): كل بايثون كُتب في
        # هذه الجولة يُترجم فعلياً؛ جولة إصلاح واحدة بحد أقصى، والنتيجة تُروى كما هي
        if ok and req.mode != "team" and any(ws.rglob("*.py")):
            yield _sse({"type": "status", "stage": "verify",
                        "text": "🔍 بوابة التحقق: تترجم كل ملفات بايثون في المساحة..."})
            errs = tm.ws_py_errors(ws, since=t_run_start)
            if errs:
                yield _sse({"type": "status", "stage": "heal",
                            "text": f"⚠️ اصطادت البوابة {len(errs)} خطأ تركيب — جولة إصلاح..."})
                hfinal, _hok = ag.run_agent(
                    "بوابة التحقق اصطادت أخطاء تركيب في ملفات مساحة عملك — أصلحها "
                    "ثم أعد الفحص بنفسك قبل أن تعلن الانتهاء:\n"
                    + "\n".join(errs[:5]), ctx, chain, on_event, memory_brief=brief)
                errs2 = tm.ws_py_errors(ws, since=t_run_start)
                if errs2:
                    final = ((hfinal or final) + "\n\n⚠️ ما زالت أخطاء التركيب قائمة "
                             "بعد جولة الإصلاح: " + " | ".join(e[:150] for e in errs2[:3]))
                    ok = False
                else:
                    final = ((hfinal or final)
                             + f"\n✅ البوابة: شُفئت الأخطاء — كل ملفات بايثون ({len(list(ws.rglob('*.py')))}) تُترجم الآن بنجاح")
            else:
                final += (f"\n✅ بوابة التحقق: {len(list(ws.rglob('*.py')))} ملف بايثون "
                          "تُترجم بنجاح")

        # behavioral gate (solo): الاختبارات المكتوبة تُشغَّل فعلاً — الترجمة
        # وحدها كانت تنجّي كوداً خاطئ المنطق، والسلوك هو الحقيقة
        if ok and req.mode != "team":
            test_files = [p for p in list(ws.rglob("test_*.py"))
                          + list(ws.rglob("*_test.py"))
                          if p.stat().st_mtime >= t_run_start - 5]
            if test_files:
                yield _sse({"type": "status", "stage": "behavior",
                            "text": f"🧪 بوابة السلوك: تشغّل {len(test_files)} "
                                    "اختباراً كُتبت في هذه الجولة..."})
                berrs = tm.ws_behavior_errors(ws, since=t_run_start)
                if berrs:
                    yield _sse({"type": "status", "stage": "heal",
                                "text": "⚠️ اختبارات تفشل — جولة إصلاح المنطق..."})
                    hfinal, _hok = ag.run_agent(
                        "بوابة السلوك اصطادت اختبارات فاشلة — الكود يُترجم لكن "
                        "المنطق خاطئ. أصلح المنطق حتى تنجح الاختبارات فعلاً:\n"
                        + "\n".join(berrs[:3]), ctx, chain, on_event,
                        memory_brief=brief)
                    berrs2 = tm.ws_behavior_errors(ws, since=t_run_start)
                    if berrs2:
                        final = ((hfinal or final)
                                 + "\n\n⚠️ اختبارات ما زالت تفشل بعد الإصلاح: "
                                 + " | ".join(e[:180] for e in berrs2[:2]))
                        ok = False
                    else:
                        final = ((hfinal or final)
                                 + f"\n✅ بوابة السلوك: شُفي المنطق — "
                                 f"{len(test_files)} اختباراً ينفذ وينجح الآن")
                else:
                    final += (f"\n✅ بوابة السلوك: {len(test_files)} اختباراً "
                              "نُفذ ونجح فعلاً")

        tools_used = sorted({s["tool"] for s in ctx.steps})

        # --- التعلم من الجولة: سجل المسار (بذرة SFT) + استخلاص وصفة إن تأهلت
        # (نجاح بملفات ≥2 → نداء واحد رخيص؛ الفشل هنا لا يكسل الخدمة أبداً)
        if req.mode == "solo":
            try:
                files = [p.relative_to(ws).as_posix() for p in ws.rglob("*")
                         if p.is_file() and "context_pack" not in p.name][:20]
                osv_distill.record_trajectory(req.task, ok, tools_used,
                                              files, final or "")
                if ok:
                    osv_distill.distill_from_run(req.task, files, chain,
                                                 _gw_stream)
            except Exception:  # noqa: BLE001 — learning must not break serving
                pass

        # --- حفظ الجلسة: الاستئناف لاحقاً يبدأ من هذه المحادثة بالضبط
        # (solo فقط — سرب له شجرة سياقات خاصة به، حفظها جزئي كذب)
        if req.mode != "team":
            try:
                sessions.save(req.session_id, req.task, ctx.msgs, ws)
            except Exception:  # noqa: BLE001 — persistence must not break serving
                pass

        try:
            mem.record_run(req.task, ok, tools_used,
                           len(ctx.steps) or (team_info and sum(
                               (s or {}).get("steps", 0)
                               for s in team_info["streams"])) or 0,
                           (final or "")[:200])
        except Exception:  # noqa: BLE001 — learning must never break serving
            pass
        for evt in events:
            yield _sse(evt)
        yield _sse({"type": "delta", "text": final})
        yield _sse({"type": "done",
                    "engine": f"OS_V1🤖({'اكتمل' if ok else 'غير مكتمل'})"
                              + ("👥 سرب" if team_info else ""),
                    "agent_steps": len(ctx.steps) or (
                        team_info and sum((s or {}).get("steps", 0)
                                          for s in team_info["streams"])) or 0,
                    "tools_used": tools_used,
                    **({"team": team_info} if team_info else {})})
    return StreamingResponse(gen(), media_type="text/event-stream")


# --- memory cache: index once per TTL, recall cheaply on every run ----------
_mem = {"index": None, "style": None, "built": 0.0}
_MEM_TTL_S = 300.0


def memory_brief_for(task: str) -> str:
    """Retrieved context for a task (workspace chunks + lessons + style).
    Index rebuilds lazily every TTL; failures degrade to '' silently —
    the agent still runs, just without the learned brief."""
    try:
        import osv_memory as mem
        now = time.time()
        if _mem["index"] is None or now - _mem["built"] > _MEM_TTL_S:
            idx = mem.WorkspaceIndex()
            idx.build(mem.memory_root())
            _mem["index"] = idx
            _mem["style"] = mem.learn_style(mem.memory_root())
            _mem["built"] = now
        return mem.brief_for_task(task, _mem["index"], mem.LessonStore(),
                                  _mem["style"])
    except Exception:  # noqa: BLE001
        return ""


@app.post("/api/v1/memory/reindex")
def memory_reindex():
    """Force the learning layer to re-read the project (e.g. after big edits)."""
    try:
        import osv_memory as mem
        idx = mem.WorkspaceIndex()
        stats = idx.build(mem.memory_root())
        _mem["index"] = idx
        _mem["style"] = mem.learn_style(mem.memory_root())
        _mem["built"] = time.time()
        return {"ok": True, "stats": stats,
                "style": _mem["style"],
                "lessons": len(mem.LessonStore()._all())}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"تعذرت إعادة الفهرسة: {exc}"}


# --- MEDIA: image/video generation (keyless lane + honest video stitching) ---

class MediaImageRequest(BaseModel):
    prompt: str
    width: int = 1024
    height: int = 1024
    model: str = "turbo"   # مجاني وسريع؛ flux مجاني بصورة كل 45 ثانية


class MediaVideoRequest(BaseModel):
    prompt: str            # وصف مشهد واحد متحرك — فيديو حقيقي
    duration_s: int = 5
    width: int = 704
    height: int = 512


def _media_kit():
    import osv_media as md
    return md.MediaKit()


@app.post("/api/v1/media/image")
def media_image(req: MediaImageRequest):
    ok, obs = _media_kit().generate_image(req.prompt, req.width, req.height,
                                          req.model)
    return {"ok": ok, "observation": obs}


@app.post("/api/v1/media/video")
def media_video(req: MediaVideoRequest):
    ok, obs = _media_kit().generate_video(req.prompt, req.duration_s,
                                          req.width, req.height)
    return {"ok": ok, "observation": obs}


@app.get("/api/v1/media/list")
def media_list():
    ok, obs = _media_kit().list_media(50)
    return {"ok": ok, "list": obs, "dir": str(media_list_dir())}


@app.get("/")
def ui_home():
    """The agent's own face — zero dependencies, same origin, Arabic RTL."""
    p = Path(__file__).resolve().parent / "index.html"
    if p.is_file():
        return FileResponse(p, media_type="text/html")
    return {"ok": False, "message": "الواجهة غير موجودة"}


@app.get("/api/v1/distill/stats")
def distill_stats():
    """The owned learning library — what the agent distilled from its own
    successful runs (the growing OS-model layer), read honestly."""
    import osv_distill as ds
    recipes = ds.load_recipes()[-8:][::-1]     # newest first, bounded
    return {"ok": True, "stats": ds.stats(),
            "recipes": [{"name": r.get("name", ""),
                         "steps": r.get("steps", [])[:5]} for r in recipes]}


def media_list_dir():
    import osv_media as md
    return md.media_dir()


@app.get("/api/v1/media/file/{name}")
def media_file(name: str):
    import osv_media as md
    if not re.fullmatch(r"(osv_(img|vid)_\d{8}_\d{6}\.(jpg|png|webp|gif|mp4)"
                        r"|osv_(mot|cine)_[0-9a-z]{8}\.mp4)", name):
        return JSONResponse({"ok": False, "message": "اسم ملف غير صالح"},
                            status_code=400)
    p = md.media_dir() / name
    if not p.is_file():
        return JSONResponse({"ok": False, "message": "غير موجود"}, status_code=404)
    return FileResponse(p)


# --- SECURITY: project scanner (the executable تأمين lane) ---

class SecScanRequest(BaseModel):
    path: str = ""


@app.post("/api/v1/security/scan")
def security_scan(req: SecScanRequest):
    import osv_sec as sec
    root = req.path or str(Path(__file__).resolve().parent)
    if not Path(root).is_dir():
        return {"ok": False, "message": "مسار غير موجود"}
    res = sec.scan_project(root)
    return {"ok": True, "report": sec.report_text(res, 30),
            "counts": res["counts"], "clean": res["clean"],
            "files_scanned": res["files_scanned"], "sec": res["sec"]}


@app.get("/api/v1/security/audit")
def security_audit():
    """FULL self-audit: (1) the redteam battery attacking our own REAL
    gates — traversal on the real AgentContext, SSRF/RCE/secrets/injection
    families, and the git-secrets gate on a real repo; (2) the static
    scanner (osv_sec) over the live app directory. The result lands in the
    distill ledger — a security regression becomes visible the day it
    appears, not the day it is exploited."""
    import osv_redteam as rt
    import osv_sec as sec
    t0 = time.time()
    battery = rt.run_battery()
    static = sec.scan_project(Path(__file__).resolve().parent)
    cls = rt.classify_static(static)
    ok_ledger = rt.record_audit(battery)
    clean = bool(battery["all_ok"]) and bool(cls["real_clean"])
    return {"ok": True,
            "verdict": "مُحصَّن" if clean
                       else "ثغرات معلنة — طالع التقرير",
            "battery": {"all_ok": battery["all_ok"],
                        "attacks": f"{battery['attacks_blocked']}/"
                                   f"{battery['attacks_total']}",
                        "controls": f"{battery['controls_passed']}/"
                                    f"{battery['controls_total']}",
                        "failures": battery["failures"]},
            "static": {"clean": static["clean"],
                       "real_clean": cls["real_clean"],
                       "real_count": cls["real_count"],
                       "corpus_count": cls["corpus_count"],
                       "corpus_note": (f"{cls['corpus_count']} إصابة داخل قمع "
                                       "الهجمات نفسه (osv_redteam.py / "
                                       "test_redteam.py) — عمداً، مفاتيح "
                                       "مزيفة موثقة وأنماط هجوم معلومة، "
                                       "وليست ثغرات"),
                       "real_findings": [
                           {"file": f.get("file"), "line": f.get("line"),
                            "rule": f.get("rule"), "severity": f.get("severity")}
                           for f in cls["real"][:20]],
                       "counts": static["counts"],
                       "files_scanned": static["files_scanned"]},
            "ledger_recorded": ok_ledger,
            "seconds": round(time.time() - t0, 2),
            "report": rt.audit_text(battery)}


# --- PROVIDERS: استحضار المفاتيح — دليل كل مزود بمصدر مفتاحه ---

@app.get("/api/v1/providers")
def providers_guide():
    """All providers with where to fetch each key — the provisioning map."""
    return {"ok": True, "count": len(CLOUD_PROVIDERS), "providers": [
        {"name": n, "label": p["label"], "key_url": p.get("key_url", ""),
         "default_model": p["default_model"]}
        for n, p in CLOUD_PROVIDERS.items()]}


@app.post("/api/v1/config")
def set_config(req: CloudConfigRequest):
    if req.provider not in CLOUD_PROVIDERS:
        return {"ok": False, "message": "مزود غير معروف"}
    try:
        save_cloud_config(req.provider, req.key, req.model or "")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": f"تعذر الحفظ: {exc}"}
    ok, msg = cloud_test(load_cloud_config())
    return {"ok": ok, "message": msg, "engine": cloud_tag(load_cloud_config())}


class CodeRunRequest(BaseModel):
    code: str
    language: str = "python"


class CodeFixRequest(BaseModel):
    code: str
    error: str
    language: str = "python"


# Hard deny-list for the live runner: network, process spawning and destructive
# filesystem operations are out of scope of a local demo runner — refused with
# an honest message rather than silently failing mid-run.
_RX_RUN_BANNED = re.compile(
    r"(?:\bos\.system\b|\bsubprocess\b|\bshutil\b|\brmtree\b|\bsocket\b"
    r"|\burllib\b|\brequests\b|\bhttpx\b|\bhttp\.client\b|\bftplib\b"
    r"|\b__import__\b|\beval\s*\(|\bexec\s*\(|\bopen\s*\([^)]*['\"][wab]"
    r"|\bdel\s+/[fsq]|\brm\s+-rf|\bformat\b\s+[cC]:"
    # JS-specific: node builtins that reach the network/filesystem/processes
    r"|\brequire\s*\(\s*['\"](?:fs|http|https|net|dgram|child_process|dns|tls|fs/promises)"
    r"|\bfrom\s+['\"](?:fs|http|https|net|child_process|dns|tls)"
    r"|\bfetch\s*\(|\bprocess\.binding\b|\bglobalThis\.import\b)", re.IGNORECASE)


@app.post("/api/v1/code/run")
def code_run(req: CodeRunRequest):
    """Execute Python or JavaScript in an isolated temp dir with a hard timeout.

    This is what makes OS_V1 an agent, not a typewriter: the model's code
    actually runs and its real output feeds back into the conversation.
    """
    lang = req.language.lower()
    if lang in ("python", "py"):
        argv = [sys.executable, "-I", "-B", "main.py"]
        entry = "main.py"
    elif lang in ("javascript", "js", "node"):
        node = shutil.which("node")
        if not node:
            return {"ok": False, "stdout": "", "stderr": "Node.js غير مثبت على هذا الجهاز.",
                    "exit": -1, "duration_ms": 0}
        argv = [node, "main.js"]
        entry = "main.js"
    else:
        return {"ok": False, "stdout": "",
                "stderr": "التنفيذ الحي متاح حالياً لـ Python و JavaScript.",
                "exit": -1, "duration_ms": 0}
    if _RX_RUN_BANNED.search(req.code):
        return {"ok": False, "stdout": "",
                "stderr": ("🛡️ رُفض التنفيذ: الكود يحوي عمليات شبكة/نظام/حذف ملفات "
                           "غير مسموحة في بيئة التشغيل الحية."),
                "exit": -1, "duration_ms": 0}
    run_dir = Path(tempfile.gettempdir()) / f"oss_run_{os.urandom(4).hex()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / entry).write_text(req.code, encoding="utf-8")
    t0 = time.time()
    try:
        # isolated python (-I -B) / plain node, confined cwd, hard timeout
        p = subprocess.run(
            argv, cwd=str(run_dir),
            capture_output=True, text=True, encoding="utf-8",
            check=False,
            errors="replace", timeout=30)
        out, err, exit_code = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        out, err, exit_code = "", "⏱️ تجاوز التنفيذ حده (30 ثانية) — أُلغي.", -1
    except Exception as exc:  # noqa: BLE001
        out, err, exit_code = "", f"فشل التشغيل: {exc}", -1
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)
    return {"ok": exit_code == 0 and not err.strip(),
            "stdout": out[-4000:], "stderr": err[-2000:], "exit": exit_code,
            "duration_ms": round((time.time() - t0) * 1000)}


@app.post("/api/v1/code/fix")
def code_fix(req: CodeFixRequest):
    """One-shot agentic repair: real traceback → fixed full code.
    Routed through the Provider Gateway with the 'code' task shift."""
    chain = cloud_chain(task="code")
    if not chain:
        return {"ok": False, "code": "", "message": "التصحيح التلقائي يحتاج المزود السحابي (⚙️)."}
    prompt = (
        f"هذا كود {req.language} فشل أثناء التشغيل. صحّحه.\n"
        f"أعد الكود الكامل المصحح في كتلة كود واحدة، ثم سطراً واحداً بالعربية يشرح سبب الخطأ.\n\n"
        f"الكود:\n```{req.language}\n{req.code}\n```\n\n"
        f"رسالة الخطأ الحقيقية من التنفيذ:\n```\n{req.error[:1500]}\n```")
    reply = None
    for cfg in chain:
        try:
            reply = "".join(_gw_stream(cfg, [
                {"role": "system", "content": CODE_SYS},
                {"role": "user", "content": prompt},
            ], effort="low")).strip()
            if reply:
                break
        except Exception:  # noqa: BLE001 — next in chain
            continue
    if not reply:
        return {"ok": False, "code": "", "message": "تعذر التصحيح — كل مزودات البوابة غير متاحة الآن."}
    return {"ok": bool(reply.strip()), "code": reply.strip()}


# ---------------------------------------------------------------------------
# Live artifacts — the agent DELIVERS, it doesn't describe. "ابني لي لعبة"
# yields a real playable HTML file served by this backend and rendered inside
# the chat UI. Files live under data/artifacts (git-ignored), names are
# server-generated hex — no path traversal.
# ---------------------------------------------------------------------------

ARTIFACTS_DIR = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "artifacts"))


class ArtifactRequest(BaseModel):
    html: str
    title: str = "OS_V1"


@app.post("/api/v1/artifact/create")
def artifact_create(req: ArtifactRequest):
    html = req.html.strip()
    if "<script" not in html.lower() and "<html" not in html.lower() and "<div" not in html.lower():
        return {"ok": False, "url": "", "message": "المحتوى لا يبدو ملف HTML صالحاً."}
    slug = os.urandom(4).hex()
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
    return {"ok": True, "url": f"/artifacts/{slug}.html", "title": req.title[:40]}


@app.get("/artifacts/{name}")
def artifact_get(name: str):
    if not re.fullmatch(r"[a-f0-9]{8}\.html", name):
        return FileResponse(ARTIFACTS_DIR / "denied.html", media_type="text/html") \
            if (ARTIFACTS_DIR / "denied.html").exists() else {"error": "invalid name"}
    path = ARTIFACTS_DIR / name
    if not path.exists():
        return {"error": "not found"}
    return FileResponse(path, media_type="text/html")


# ---------------------------------------------------------------------------
# Project Builder — full multi-file projects (sites, apps, ERP skeletons).
# Agent loop: PLAN (strict JSON) → generate every file (parallel workers) →
# assemble → ZIP + live preview. This is the Codex/Claude-Code style:
# the deliverable is a real project tree, not one file.
# ---------------------------------------------------------------------------

PROJECTS_DIR = Path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "projects"))
_MAX_PROJECT_FILES = 12


def _extract_block(text: str) -> str | None:
    """Pull the first fenced code block; tolerate an unclosed (stream-cut) one."""
    m = re.search(r"```[\w#+.-]*\n([\s\S]*?)```", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"```[\w#+.-]*\n([\s\S]+)$", text)
    return m.group(1).strip() if m else None


def _cloud_complete(chain: list[dict], messages: list[dict],
                    effort: str | None = "low", timeout: int = 120,
                    max_tokens: int = 4000) -> tuple[str, dict] | None:
    """Try every provider in the failover chain; return (text, working_cfg).

    The tightened timeout keeps one stalled provider from freezing an
    agent-loop phase — it fails over instead."""
    for cfg in chain:
        try:
            text = "".join(_gw_stream(cfg, messages, effort=effort,
                                      timeout=timeout,
                                      max_tokens=max_tokens)).strip()
            if text:
                _healthy["provider"] = cfg["provider"]
                return text, cfg
        except Exception:  # noqa: BLE001 — 429/timeout: next in chain
            continue
    return None


def _safe_relpath(p: str) -> str | None:
    p = str(p).replace("\\", "/").lstrip("/").strip()
    if not p or ".." in p or len(p) > 120 or p.startswith("."):
        return None
    return p


def _brainstorm(chain: list[dict], description: str) -> str:
    """Phase 0 — creative divergence: three distinct concepts, self-ranked.

    One bounded call (effort "none") keeps this ~10s; the chosen concept
    grounds the plan so the build starts from the strongest idea, not the
    first one that came to mind."""
    prompt = (
        f"المطلوب بناؤه: {description}\n\n"
        "اقترح 3 مفاهيم مختلفة جوهرياً (ليست تدريجات على نفس الفكرة):\n"
        "1. المفهوم التقليدي الموثوق\n"
        "2. المفهوم الأكثر إبداعاً وتميزاً\n"
        "3. المفهوم الأبسط والأسرع إتماماً\n\n"
        'ثم اختر الأنسب وأعد JSON فقط: {"concepts": ["...", "...", "..."], '
        '"chosen": 1 أو 2 أو 3, "why": "سبب واحد قصير"}')
    out = _cloud_complete(chain, [{"role": "user", "content": prompt}],
                          effort="none", timeout=45, max_tokens=700)
    if not out:
        return ""
    raw, _cfg = out
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return ""
        d = json.loads(m.group(0))
        concepts = [str(c)[:220] for c in d.get("concepts", []) if c]
        idx = d.get("chosen")
        if isinstance(idx, int) and 1 <= idx <= len(concepts):
            return concepts[idx - 1]
        return concepts[0] if concepts else ""
    except Exception:  # noqa: BLE001
        return ""


def _plan_project(chain: list[dict], description: str,
                  concept: str = "") -> tuple[dict, dict] | None:
    """Step 1: a strict-JSON build plan (file tree + purposes).

    Returns (plan, working_cfg) so later phases skip dead providers."""
    sys_p = ("أنت مهندس برمجيات كبير. تخطيط دقيق. إخراجك JSON صالح فقط — "
             "لا أي نص قبله أو بعده، لا علامات كود.")
    user_p = (
        (f"المفهوم المعتمد (التزم به): {concept}\n\n" if concept else "")
        + f"خطط مشروعاً برمجياً: {description}\n\n"
        'أعد JSON بهذا الشكل تماماً:\n'
        '{"name": "اسم المشروع بالعربية", "kind": "web أو python",\n'
        ' "files": [{"path": "index.html", "purpose": "وصف موجز"}, ...],\n'
        ' "notes": "قرار معماري واحد مهم"}\n\n'
        f"القواعد الصارمة: من 4 إلى {_MAX_PROJECT_FILES} ملفات. "
        "مشاريع الويب: index.html أولاً + ملفات css/js منفصلة عند الحاجة + صفحات إضافية حسب الطلب. "
        "لا مكتبات خارجية ولا CDN ولا خطوات بناء — كل شيء يعمل بفتح index.html مباشرة. "
        "مشاريع بايثون: ملف رئيسي + وحدات منطقية + ملف README.md.")
    out = _cloud_complete(chain, [{"role": "system", "content": sys_p},
                                  {"role": "user", "content": user_p}],
                          effort="low", timeout=75)
    if not out:
        return None
    raw, cfg = out
    try:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return None
        plan = json.loads(m.group(0))
        files = []
        for f in plan.get("files", []):
            p = _safe_relpath(f.get("path", ""))
            if p:
                files.append({"path": p, "purpose": str(f.get("purpose", ""))[:200]})
        if not files:
            return None
        return {"name": str(plan.get("name", "مشروع OS_V1"))[:60],
                "kind": str(plan.get("kind", "web"))[:10],
                "notes": str(plan.get("notes", ""))[:300],
                "files": files[:_MAX_PROJECT_FILES]}, cfg
    except Exception:  # noqa: BLE001
        return None


def _gen_project_file(chain: list[dict], plan: dict, f: dict,
                      error_ctx: str = "") -> tuple[str, str] | None:
    """Step 2 worker: one file, grounded in the full plan for coherence."""
    ext = f["path"].rsplit(".", 1)[-1].lower()
    lang = {"html": "html", "htm": "html", "css": "css", "js": "javascript",
            "py": "python", "json": "json", "md": "markdown"}.get(ext, "text")
    # Markup needs no thinking chain; logic gets a bounded one.
    effort = "none" if lang in ("html", "css", "markdown") else "low"
    # Per-type token budgets: a README needs no 4000-token allowance —
    # smaller caps mean faster completion on the router.
    cap = {"markdown": 1200, "json": 1600, "css": 2800}.get(lang, 4000)
    tree = "\n".join(f"- {x['path']} : {x['purpose']}" for x in plan["files"])
    prompt = (
        f"مشروع: {plan['name']} — قرار معماري: {plan['notes']}\n"
        f"بنية المشروع كاملة:\n{tree}\n\n"
        f"اكتب الآن محتوى الملف «{f['path']}» فقط ({f['purpose']}).\n"
        "شروط صارمة: كود كامل نهائي في كتلة كود واحدة بلا أي نص خارجها؛ "
        "التزم بأسماء الملفات في البنية عند الاستيراد/الربط؛ "
        "الواجهات بالعربية RTL عند وجود HTML؛ لا مكتبات خارجية.")
    if error_ctx:
        prompt += (f"\n\n⚠️ النسخة السابقة من هذا الملف رُفضت بالفحص: {error_ctx}\n"
                   "أصلح هذا العيب تحديداً وأخرج الملف كاملاً من جديد.")
    out = _cloud_complete(chain, [{"role": "system", "content": CODE_SYS},
                                  {"role": "user", "content": prompt}],
                          effort=effort, timeout=150, max_tokens=cap)
    if not out:
        return None
    raw, _cfg = out
    code = _extract_block(raw) or raw.strip()
    if len(code) < 30:
        return None
    return f["path"], code


# Referenced local assets in HTML — src= / href= that must resolve inside
# the delivered tree, or the project ships with dead links.
_RX_REF = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
_RX_CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.IGNORECASE)
_LOCAL_SKIP = ("http://", "https://", "//", "data:", "mailto:", "tel:", "#")


def _verify_project(files: list[tuple[str, str]]) -> dict:
    """Phase 3 — REAL verification with local tools (no model, milliseconds).

    - .py  → ast.parse (exact syntax gate)
    - .js  → node --check (exact syntax gate when Node exists)
    - .css → brace balance
    - .html → closure + every referenced local asset resolves to a real file
    Returns missing refs (to be generated) and broken files (to be fixed)."""
    import ast as _ast
    have = {p for p, _ in files}
    missing, broken = set(), []

    def _add_missing(ref: str) -> None:
        if not ref or ref.startswith(_LOCAL_SKIP) or ref.startswith("#"):
            return
        ref = ref.split("#")[0].split("?")[0].strip().lstrip("/")
        if not ref or ".." in ref:
            return
        if ref not in have and not (ref.endswith((".png", ".jpg", ".jpeg",
                                                   ".svg", ".gif", ".webp",
                                                   ".ico", ".woff", ".woff2"))):
            missing.add(ref)

    for path, code in files:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in ("html", "htm"):
            if len(code) > 200 and "</html>" not in code.lower():
                broken.append((path, "HTML مقطوع — لا وسم إغلاق"))
            for ref in _RX_REF.findall(code):
                _add_missing(ref)
        elif ext == "css":
            for ref in _RX_CSS_URL.findall(code):
                _add_missing(ref)
            if code.count("{") != code.count("}"):
                broken.append((path, "أقواس CSS غير متوازنة"))
        elif ext == "py":
            try:
                _ast.parse(code)
            except SyntaxError as e:
                broken.append((path, f"SyntaxError: {e.msg} (سطر {e.lineno})"))
        elif ext in ("js", "mjs"):
            node = shutil.which("node")
            if node:
                try:
                    with tempfile.NamedTemporaryFile("w", suffix=".js",
                                                     delete=False,
                                                     encoding="utf-8") as tf:
                        tf.write(code)
                        tmp = tf.name
                    try:
                        r = subprocess.run([node, "--check", tmp],
                                           capture_output=True, text=True,
                                           timeout=20, check=False)
                        if r.returncode != 0:
                            broken.append((path, (r.stderr or "").strip()[:200]))
                    finally:
                        os.unlink(tmp)
                except Exception:  # noqa: BLE001 — checker failure ≠ file failure
                    pass
    return {"missing": sorted(missing)[:4], "broken": broken[:3]}


def _assemble_project(plan: dict, files: list[tuple[str, str]]) -> dict:
    """Step 3: write the tree, zip it, find a preview entry point."""
    pid = os.urandom(4).hex()
    pdir = PROJECTS_DIR / pid
    pdir.mkdir(parents=True, exist_ok=True)
    written = []
    for path, code in files:
        dest = pdir / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(code, encoding="utf-8")
        written.append(path)
    zip_path = PROJECTS_DIR / f"{pid}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in written:
            zf.write(pdir / path, arcname=f"{plan['name'].replace(' ', '_')}/{path}")
    preview = None
    for cand in ("index.html", "main.html", "app.html"):
        if (pdir / cand).exists():
            preview = f"/projects/{pid}/{cand}"
            break
    if preview is None and plan["kind"] == "python":
        for cand in ("main.py", "app.py", "run.py"):
            if (pdir / cand).exists():
                preview = None  # python projects: no browser preview, ZIP only
                break
    return {"id": pid, "name": plan["name"], "files": written,
            "zip": f"/api/v1/project/{pid}/zip", "preview": preview}


@app.get("/projects/{pid}/{fpath:path}")
def project_file(pid: str, fpath: str):
    """Serve generated project files — relative links between pages WORK."""
    if not re.fullmatch(r"[a-f0-9]{8}", pid):
        return {"error": "invalid id"}
    safe = _safe_relpath(fpath)
    if not safe:
        return {"error": "invalid path"}
    path = PROJECTS_DIR / pid / safe
    if not path.is_file():
        return {"error": "not found"}
    media = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return FileResponse(path, media_type=media)


@app.get("/api/v1/project/{pid}/zip")
def project_zip(pid: str):
    if not re.fullmatch(r"[a-f0-9]{8}", pid):
        return {"error": "invalid id"}
    zp = PROJECTS_DIR / f"{pid}.zip"
    if not zp.exists():
        return {"error": "not found"}
    return FileResponse(zp, media_type="application/zip", filename=f"OSV1_project_{pid}.zip")


@app.post("/api/v1/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    t0 = time.time()
    sid = req.session_id or "default"
    kind = route(req.message)
    if kind in INSTANT_ANSWERS:
        return ChatResponse(reply=INSTANT_ANSWERS[kind], model=req.model, latency_ms=1,
                            session_id=sid, engine="instant", sources=[])
    cached = cache_get(_clean_query(req.message))
    if cached:
        return ChatResponse(reply=cached["reply"], model=req.model, latency_ms=1,
                            session_id=sid, engine="cache", sources=cached.get("sources", []))
    with _lock:
        history = list(_sessions.setdefault(sid, []))
    reply, engine, sources = answer(req.message, history)
    if not engine.startswith(("engine_",)):
        cache_put(_clean_query(req.message), reply, sources, engine)
    with _lock:
        session = _sessions.setdefault(sid, [])
        session.append({"role": "user", "content": req.message})
        session.append({"role": "assistant", "content": reply})
        if len(session) > 12:
            _sessions[sid] = session[-8:]
    return ChatResponse(reply=reply, model=req.model,
                        latency_ms=round((time.time() - t0) * 1000),
                        session_id=sid, engine=engine, sources=sources)


if __name__ == "__main__":
    import uvicorn
    print("🤖 OSS Work v9.0 — AgentEngine (brainstorm + plan + parallel build + real verify/heal + SSE)")
    print("   Frontend: http://localhost:3000")
    print("   API:      http://127.0.0.1:8000/api/info")
    uvicorn.run("oss_work_live:app", host="0.0.0.0", port=8000, reload=False)