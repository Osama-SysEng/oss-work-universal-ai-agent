"""osv_rea — the REA / Craft Anything capability layer (8 Nov 2026).

Reverse Engineer Anything (github.com/morluto/rea, MIT) and Craft Anything
(github.com/storytold/craft-anything, MIT/Apache-2.0) are the two reference
methodologies the team adopted on 8 Nov. Their essence is implemented here
with stdlib only and honest boundaries:

- evidence ledger: every conclusion is classified observed/inferred/unknown
  and PERSISTED per-workspace in evidence/ledger.json — conclusions that live
  only in the chat transcript are folklore (the lesson-40 spirit extended:
  a "success" without a measured check and a ledger is an unverifiable claim
  presented as one).
- target routing: web target -> clean-room study; shipped artifact ->
  magic-byte inspection; built project -> a MEASURED check against the
  studied brief (difflib ratio + heading coverage + explicit gap list), the
  Craft-Anything Check step made mechanical instead of impressionistic.
- the craft cycle study -> build -> check -> refine is executed by the agent
  loop via rule 14; the tools below own study/inspect/check/record-unknown.

Boundaries (non-negotiable, mirror of the skill files): CLEAN-ROOM default —
study only what a visitor sees; analysis only of software the user owns,
is authorized to examine, or whose public surface we read; rebuilt code is
written fresh — logos, photos and owned text are never copied. Native code
decompilation is NOT available on this machine and these tools never claim
it; unknowns are recorded, not invented.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import sqlite3
import struct
import time
import urllib.request
import uuid
import zipfile
from html.parser import HTMLParser
from pathlib import Path

MAX_OBS_CHARS = 2400
_ORIG_CLIP = 6000

# ---------------------------------------------------------------------------
# HTTP (module-level so tests can mock it, same pattern as osv_cloud._http)


def _fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    """Hardened https: real CA bundle (this machine died CERTIFICATE_VERIFY_
    FAILED on every https URL) — same trust workflow as tool_web_fetch:
    unverified fallback only when the default store is empty is NOT applied
    here; a failed verify is an honest failure. size-capped 2 MB."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "OSS-Work-REA/1.0 (+educational clean-room study)"})
    try:
        from oss_work_live import _ssl_context
        ctx = _ssl_context()
    except Exception:  # noqa: BLE001 — standalone import, default context works
        ctx = None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read(2_000_000).decode("utf-8", errors="replace")
        return r.status, raw


# ---------------------------------------------------------------------------
# Evidence ledger — persists observed / inferred / unknown per workspace


def _ledger_path(ctx) -> Path:
    return ctx.workspace / "evidence" / "ledger.json"


def _load_ledger(ctx) -> list[dict]:
    p = _ledger_path(ctx)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001 — damaged ledger must not kill the tool
        return []


def _save_ledger(ctx, rows: list[dict]) -> None:
    p = _ledger_path(ctx)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                 encoding="utf-8")


def _ledger_append(ctx, kind: str, observed=(), inferred=(), unknown=(),
                   extra: dict | None = None) -> str:
    rows = _load_ledger(ctx)
    eid = "ev-" + uuid.uuid4().hex[:10]
    rows.append({"id": eid, "t": kind, "at": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "observed": list(observed), "inferred": list(inferred),
                 "unknown": list(unknown), **(extra or {})})
    _save_ledger(ctx, rows)
    return eid


def _visible(html_src: str) -> str:
    """Strip script/style and tags — what a visitor would read."""
    no = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html_src)
    no = re.sub(r"(?s)<[^>]+>", " ", no)
    return re.sub(r"\s+", " ", no).strip()


def _clip(text: str, limit: int = MAX_OBS_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n… [اقتُطعت]"


# ---------------------------------------------------------------------------
# Clean-room HTML study (what a visitor sees — no script/asset reading)


class _CleanStudy(HTMLParser):
    """Capture-stack parser: text feeds every OPEN capture (title/heading/
    link), so nesting can't cross-contaminate — and the stack pop lands on
    the tag's own capture, not whatever happened to sit on top."""

    _CAPTURE = ("title", "h1", "h2", "h3", "a")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[tuple[str, str]] = []
        self.links: list[tuple[str, str]] = []
        self.words = 0
        self.imgs = 0
        self.inputs = 0
        self.frm_count = 0
        self.btns = 0
        self.script_srcs: list[str] = []
        self.meta: dict[str, str] = {}
        self.lang = ""
        self._skip = 0
        self._stack: list[tuple[str, list[str]]] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "img":
            self.imgs += 1
        elif tag == "input":
            self.inputs += 1
        elif tag == "form":
            self.frm_count += 1
        elif tag == "button":
            self.btns += 1
        elif tag == "script":
            if a.get("src"):
                self.script_srcs.append(a["src"])
            self._skip += 1
        elif tag == "html" and a.get("lang"):
            self.lang = a["lang"]
        elif tag == "meta" and a.get("name"):
            self.meta[a["name"]] = a.get("content", "")
        elif tag in self._CAPTURE:
            href = a.get("href", "")
            self._stack.append((tag, [], href))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
            return
        if tag in ("title", "h1", "h2", "h3", "a"):
            cap = None
            for i in range(len(self._stack) - 1, -1, -1):
                if self._stack[i][0] == tag:
                    cap = self._stack.pop(i)
                    break
            if cap is None:
                return
            tag, buf, href = cap
            txt = re.sub(r"\s+", " ", "".join(buf)).strip()
            if tag == "title":
                self.title = txt or self.title
            elif tag in ("h1", "h2", "h3") and txt:
                self.headings.append((tag, txt[:120]))
            elif tag == "a" and txt:
                self.links.append((href, txt[:60]))

    def handle_startendtag(self, tag, attrs):
        pass  # void tags carry no text to capture

    def handle_data(self, data):
        if self._skip:
            return
        s = data.strip()
        if s:
            self.words += len(s.split())
        for cap in self._stack:
            cap[1].append(data)

    def visible_text(self, html_src: str) -> str:
        return _visible(html_src)


def _study_brief(st: _CleanStudy, url: str) -> str:
    hs = "; ".join(f"{t}:{x}" for t, x in st.headings[:12]) or "(بلا عناوين)"
    links = "، ".join(h for _, h in st.links[:8] if h)
    return _clip(
        f"دراسة نمط نظيف لـ {url}\n"
        f"العنوان: {st.title or '(غير مزود)'} | lang={st.lang or '?'} | "
        f"كلمات={st.words} | عناوين: {st.headings and len(st.headings)} | "
        f"صور={st.imgs} نماذج={st.frm_count} حقول={st.inputs} "
        f"أزرار={st.btns} | scripts(src)={len(st.script_srcs)}\n"
        f"H*: {hs}\nروابط: {links or '(بلا)'}\n"
        f"المجهول (سجّله لا تفترضه): سلوك الأزرار والنماذج، منطق السكربتات، "
        f"الصفحات داخلها، النهايات الخلفية — كلها غير ظاهرة في النمط النظيف. "
        f"التعمق (deep) يتطلب قرار المستخدم.")


def tool_rea_study(ctx, url: str) -> tuple[bool, str]:
    """Clean-room study of a public page: what the visitor sees, recorded."""
    if not str(url).strip():
        return False, "rea_study يحتاج url الأصل"
    if not re.match(r"^https?://", str(url), re.IGNORECASE):
        return False, "url يجب أن يبدأ http:// أو https://"
    try:
        import osv_redteam
        ok_url, why_url = osv_redteam.url_guard(url)
    except Exception:  # noqa: BLE001 — guard unavailable: keep going honest
        ok_url, why_url = True, ""
    if not ok_url:
        return False, f"رابط مرفوض بوابة الأمن: {why_url}"
    try:
        status, body = _fetch(url)
    except Exception as exc:  # noqa: BLE001 — honest failure
        return False, f"تعذر الجلب: {type(exc).__name__}: {str(exc)[:120]}"
    if status != 200:
        return False, f"HTTP {status} — الأصل لم يُجب بهذه الشكلية"
    st = _CleanStudy()
    try:
        st.feed(body)
    except Exception as exc:  # noqa: BLE001
        return False, f"تعذر تفكيك HTML: {exc}"
    visible = st.visible_text(body)[:_ORIG_CLIP]
    brief = _study_brief(st, url)
    obs = {
        "url": url, "title": st.title, "lang": st.lang, "words": st.words,
        "headings": st.headings, "links": st.links[:20],
        "counts": {"img": st.imgs, "form": st.frm_count, "input": st.inputs,
                   "button": st.btns, "script_src": len(st.script_srcs)},
        "meta_description": st.meta.get("description", ""),
        "visible_text": visible, "hash":
            hashlib.sha256(body.encode()).hexdigest()[:12],
    }
    p = ctx.workspace / "evidence" / "latest-study.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obs, ensure_ascii=False, indent=1), "utf-8")
    eid = _ledger_append(
        ctx, "study", observed=[f"HTTP 200 من {url}، {st.words} كلمة",
                                f"عنوان: {st.title}"],
        inferred=["بنية الصفحة من العناوين والروابط كما ظهرت"],
        unknown=["المنطق خلف السكربتات والأزرار", "الصفحات غير المرصودة"])
    return True, f"{brief}\n[دليل: {eid}] ({p.name} محفوظ للفحص لاحقاً)"


# ---------------------------------------------------------------------------
# Shipped-artifact inspection — magic-byte routing, stdlib only


def _zip_facts(p: Path) -> tuple[list[str], list[str]]:
    observed, unknown = [], []
    try:
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            observed.append(f"zip بـ{len(names)} مدخلاً")
            exts: dict[str, int] = {}
            for n in names:
                e = n.rsplit(".", 1)[-1].lower() if "." in n else "(بلا)"
                exts[e] = exts.get(e, 0) + 1
            observed.append("الامتدادات: " + ", ".join(
                f"{k}:{v}" for k, v in
                sorted(exts.items(), key=lambda kv: -kv[1])[:8]))
            if any(n.endswith("AndroidManifest.xml") for n in names):
                observed.append("يبدو APK (يوجد AndroidManifest.xml)")
            if any(n.endswith(".asar") for n in names):
                observed.append("فيه asar داخلي")
            if "pom.xml" in names or any(n.endswith(".class") for n in names):
                observed.append("حزمة Java (pom/classes)")
            unknown.append("محتويات المدخلات لم تُقرأ — أعلن إن أردت تفكيكاً")
    except Exception as exc:  # noqa: BLE001
        unknown.append(f"الفتح فشل: {exc}")
    return observed, unknown


def _sqlite_facts(p: Path) -> tuple[list[str], list[str]]:
    observed, unknown = [], []
    try:
        con = sqlite3.connect(str(p))
        try:
            tables = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'")]
            observed.append(f"sqlite: {len(tables)} جدولاً: {', '.join(tables[:14])}")
            for t in tables[:6]:
                n = con.execute(
                    f"SELECT COUNT(*) FROM \"{t}\"").fetchone()[0]
                observed.append(f"جدول {t}: {n} صفاً")
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001
        unknown.append(f"قراءة القاعدة فشلت: {exc}")
    return observed, unknown


def _gguf_facts(p: Path) -> tuple[list[str], list[str]]:
    observed = []
    unknown: list[str] = []
    try:
        with p.open("rb") as f:
            head = f.read(24)
        _magic, ver, tensors, kvs = struct.unpack("<4sIQQ", head)
        observed.append(f"GGUF إصدار={ver} تنسورات={tensors} مفاتيح={kvs}")
        unknown.append("بنية الملف الاسمية/قيم المفاتيح لم تُقرأ هنا — "
                       "أعلن ذلك عند الحاجة")
    except Exception as exc:  # noqa: BLE001
        return [], [f"رأس GGUF لم يُفك: {exc}"]
    return observed, unknown


_MAGIC_ROUTES = (
    (b"PK\x03\x04", "zip", _zip_facts),
    (b"SQLite format 3\x00", "sqlite", _sqlite_facts),
    (b"GGUF", "gguf", _gguf_facts),
)


def tool_rea_inspect(ctx, path: str) -> tuple[bool, str]:
    """Route a workspace file by its magic bytes and record the facts found."""
    p = ctx.resolve(str(path))
    if p is None:
        return False, "مسار عاطمٍ أو خارج المساحة"
    if not p.is_file():
        return False, f"الملف غير موجود: {path}"
    try:
        head = p.open("rb").read(64)
    except OSError as exc:
        return False, f"قراءة الرأس فشلت: {exc}"
    observed: list[str] = [f"حجم={p.stat().st_size}ب"]
    unknown: list[str] = []
    if not p.stat().st_size:
        eid = _ledger_append(ctx, "inspect", observed=observed,
                             unknown=["الملف صفر بايت — رأس وبصمة غير موجودين"])
        return True, f"تفتيش {path}\nحجم=0ب — الملف فارغ [دليل: {eid}]"
    for magic, label, fn in _MAGIC_ROUTES:
        if head.startswith(magic):
            observed.append(f"بصمة: {label}")
            o2, u2 = fn(p)
            observed.extend(o2)
            unknown.extend(u2)
            break
    else:
        if head.startswith(b"MZ"):
            observed.append("PE/EXE ويندوز — فك الكود غير متاح على هذه الآلة")
            unknown.append("جداول الاستيراد والتصدير غير مُستخرجة هنا")
        elif head.startswith(b"\x7fELF"):
            observed.append("ELF لينكس — فك الكود غير متاح على هذه الآلة")
        elif head.startswith((b"\xfe\xed\xfa", b"\xcf\xfa\xed", b"\xca\xfe")):
            observed.append("Mach-O أبل — فك الكود غير متاح هنا")
        else:
            text = None
            try:
                text = p.read_text(encoding="utf-8")[:4000]
            except UnicodeDecodeError:
                observed.append("ثنائي بلا بصمة معروفة في الرأس الأول")
                unknown.append("الصيغة غير مصَّوبة — أعلنها للمستخدم")
            if text is not None:
                nlines = text.count("\n") + 1
                observed.append(f"نص {nlines} سطراً (أول 4000 حرف)")
                if path.endswith((".py",)):
                    fns = text.count("def ")
                    observed.append(f"بايثون: {fns} دالة مرئية تقريباً")
                if "<html" in text.lower() or "<!doctype" in text.lower():
                    observed.append("HTML")
                if "{" in text and "\": " in text:
                    observed.append("يشبه JSON")
    eid = _ledger_append(ctx, "inspect", observed=observed, unknown=unknown)
    return True, _clip(f"تفتيش {path}\n" +
                       "\n".join(observed) +
                       ("\nمجهول: " + "؛ ".join(unknown) if unknown else "") +
                       f"\n[دليل: {eid}]")


# ---------------------------------------------------------------------------
# Evidence tool — record_unknown / view, the REA ledger made callable


def tool_rea_evidence(ctx, action: str = "view", text: str = "") \
        -> tuple[bool, str]:
    rows = _load_ledger(ctx)
    if action == "unknown":
        if not str(text).strip():
            return False, "rea_evidence unknown يحتاج text السؤال المفتوح"
        eid = _ledger_append(ctx, "unknown-open", unknown=[text])
        n = len([r for r in rows if r["t"] == "unknown-open"]) + 1
        return True, f"سُجّل مجهول {eid} (إجمالي مجاهيل مفتوحة: {n})"
    open_rows = [r for r in rows if r["t"] == "unknown-open"]
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r["t"]] = kinds.get(r["t"], 0) + 1
    lines = [f"ledger: {len(rows)} قيدياً — " +
             ", ".join(f"{k}:{v}" for k, v in sorted(kinds.items()))]
    for r in open_rows[-6:]:
        lines.append(f"مجهول {r['id']}: {r['unknown'][0][:90]}")
    if not rows:
        lines.append("السجل فارغ — كل قيادة هنا مرئية في evidence/ledger.json")
    return True, "\n".join(lines)


# ---------------------------------------------------------------------------
# Craft-Anything Check — the built project vs the studied original, measured


_AR_PREFIX = ("وال", "فال", "بال", "كال", "ال", "و", "ف", "ب", "ك", "ل")


def _norm(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^\w\s\u0600-\u06ff]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _root4(word: str) -> str:
    w = word.strip()
    for pre in _AR_PREFIX:
        if len(w) > len(pre) + 2 and w.startswith(pre):
            w = w[len(pre):]
            break
    return w[:5] if len(w) > 5 else w


def _heading_hit(heading: str, built_text: str) -> bool:
    words = [w for w in _norm(heading).split() if len(w) >= 3]
    if not words:
        return False
    hits = sum(1 for w in words if _root4(w) in built_text
               or w in built_text)
    return hits / len(words) >= 0.5


def tool_rea_check(ctx) -> tuple[bool, str]:
    """Compare the built workspace against the last clean-room study."""
    sp = ctx.workspace / "evidence" / "latest-study.json"
    if not sp.is_file():
        return False, "لا دراسة محفوظة — run rea_study على الأصل أولاً"
    study = json.loads(sp.read_text(encoding="utf-8"))
    orig_text = study.get("visible_text", "")
    orig_title = study.get("title", "")
    if not orig_text:
        return False, "الدراسة بلا نص مرئي مُرجَع — أعد rea_study"
    htmls = sorted(ctx.workspace.glob("**/*.html"))
    if not htmls:
        return False, "لا ملف HTML مبني في المساحة — ابنِ أولاً ثم افحص"
    # main page = shallowest html (index-like)
    built = min(htmls, key=lambda p: (len(p.relative_to(ctx.workspace)
                                       .parts),
                                      p.name.lower() != "index.html"))
    try:
        built_disp = _norm(_visible(built.read_text(encoding="utf-8")))
    except Exception as exc:  # noqa: BLE001
        return False, f"قراءة المبني فشلت: {exc}"
    ratio = difflib.SequenceMatcher(None, _norm(orig_text)[:4000],
                                    built_disp[:4000]).ratio()
    headings = [h for _, h in study.get("headings", []) if h]
    if headings:
        covered = [h for h in headings if _heading_hit(h, built_disp)]
        cov_pct = round(100 * len(covered) / len(headings))
        missing = [h for h in headings if h not in covered]
    else:
        cov_pct, missing = 0, []
    title_ok = bool(orig_title) and (
        _norm(orig_title) in built_disp or _heading_hit(orig_title, built_disp))
    obs = [f"ratio={ratio:.2f}", f"تغطية العناوين {cov_pct}%"]
    _TH_RATIO, _TH_COV = 0.55, 60
    verdict = "قريب" if (ratio >= _TH_RATIO and cov_pct >= _TH_COV) \
        else "بعيد"
    gaps = [f"عنوان غائب: {h}" for h in missing[:6]]
    if ratio < _TH_RATIO:
        gaps.append(f"نسبة التقارب {ratio:.2f} أقل من العتبة {_TH_RATIO}")
    if cov_pct < _TH_COV:
        gaps.append(f"تغطية العناوين {cov_pct}% أقل من العتبة {_TH_COV}%")
    if not title_ok and orig_title:
        gaps.append(f"العنوان الأصلي ({orig_title[:40]}) غير ظاهر")
    gid = _ledger_append(
        ctx, "craft-check", observed=obs,
        inferred=[f"حكم الفحص: {verdict} — يقاس لا يُشعر"],
        unknown=["سلوك تفاعلي (زر/نموذج/خادم) لم يوازن بالأصل"],
        extra={"ratio": round(ratio, 2), "coverage": cov_pct})
    msg = (f"فحص Craft على {built.name}: ratio={ratio:.2f} "
           f"(0.0 بداية صفر، 1.0 تطابق تام) | تغطية العناوين {cov_pct}% "
           f"({len(headings)} عنواناً) | الحكم: {verdict}\n"
           + ("فروق مُقاسة: " + "؛ ".join(gaps) if gaps
              else "بلا فروق نصية مرصودة")
           + f"\n[دليل: {gid}] — أصلح الفروق الأخطر ثم أعد الفحص.")
    return True, _clip(msg)
