"""OS_V1 Sec — the security auditor (التأمين واختبار الاختراق المصرَّح به).

What an honest pentest lane IS on this system:
  1. Static security scanning of ANY project on the machine (read-only —
     always allowed by the read lanes) — secrets, injection, unsafe calls,
     insecure transport, debug leaks — with file:line evidence and severity.
  2. Active exploitation tests ONLY against targets the permission gate
     approves (device.exec lanes stay gated; hard-deny machine-killers stay
     absolute) — scanning YOUR OWN projects needs no approval, touching
     OTHER systems always goes through the human.
The agent's fixing loop: scan → read the flagged code → rewrite with
write_file → re-scan until clean. That is "التأمين" as a verifiable loop,
not a checklist claim.

False-positive design (each rule earned its precision against real noise):
  - SQL injection anchors the concat/percent form to a CLOSING QUOTE — the
    safe parameterized form ("... = ?", (args,)) never matches, and constant
    arithmetic inside SQL strings ("failures + 1") is not flagged.
  - py-eval/exec skips function DEFINITIONS (def exec(...) is not a call).
  - weak-hash flags md5 unconditionally, sha1 only in a password/secret
    context — sha1 fingerprints (cache keys) are legitimate.
  - Lines that are pure string literals (defense regexes, docstrings, hint
    texts, protocol tuples) are matched only by SECRET rules — a secret in a
    string is always reported; behavior rules never fire on pattern text.
  - insecure-url requires a real host after http:// and excludes loopback,
    bind addresses, private LAN ranges and w3.org namespaces.
  - Runtime output dirs (data/, artifacts, generated projects) are skipped:
    the scanner audits SOURCE, not what the agent built at runtime.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist",
             "build", ".idea", ".vscode", "site-packages", ".mypy_cache",
             ".pytest_cache", "media", "data-osv1", "data"}
SCAN_EXT = {".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yml", ".yaml",
            ".env", ".ini", ".cfg", ".toml", ".md", ".html", ".sql", ".sh",
            ".php", ".rb", ".go", ".rs", ".cs", ".java", ".txt"}
MAX_FILE_KB = 300
MAX_FINDINGS = 400

# (rule, severity, regex, arabic fix hint, guard-or-None)
# guard: callable(line)->bool — شرط إضافي بعد مطابقة الـregex (يقلل الإنذارات الكاذبة)
RULES = [
    ("aws-key", "critical",
     re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
     "مفتاح AWS مكشوف — ألغِ فوراً من IAM وضع المفاتيح في متغيرات بيئة",
     None),
    ("private-key", "critical",
     re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
     "مفتاح خاص ملتصق بالكود — انقله لملف خارجي مُدار ومتغير بيئة",
     None),
    ("token-literal", "critical",
     re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{20,}|xox[bpars]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})\b"),
     "توكن مزود مكشوف — ألغِه من لوحة المزود وأعد توليده، واضعه في .env غير مُرحَّل",
     None),
    ("password-literal", "critical",
     re.compile(r"(?i)(password|passwd|secret)\s*[=:]\s*[\"'][^\"']{6,}[\"']"),
     "كلمة سر/سر مكتوب حرفياً — استخدم متغير بيئة؛ اترك «CHANGE-ME» فقط كقيمة بديلة",
     None),
    ("sql-injection", "critical",
     re.compile(r"(?i)f[\"']\s*(SELECT|INSERT|UPDATE|DELETE)\b|(SELECT|INSERT|UPDATE|DELETE)[^\n]{0,120}[\"']\s*(\+\s*[a-zA-Z_]\w*|%\s*[a-zA-Z_])"),
     "استعلام SQL بدمج نصوص = حقن — استخدم بارامترات (? أو %s مع execute)",
     None),
    ("ssl-verify-off", "critical",
     re.compile(r"verify\s*=\s*False"),
     "تعطيل تحقق TLS — قاطعة هجوم الوسيط؛ أبقِ verify=True وأصلح الشهادات",
     None),
    ("py-eval", "high",
     re.compile(r"(?<![\w.])(?<!def )\b(eval|exec)\s*\(\s*[^\)]"),
     "eval/exec على بيانات = تنفيذ تعسفي — استخدم ast.literal_eval أو محللاً صريحاً",
     None),
    ("shell-true", "high",
     re.compile(r"shell\s*=\s*True"),
     "subprocess بـ shell=True مع مدخلات = حقن أوامر — مرر قائمة argv",
     None),
    ("flask-debug", "high",
     re.compile(r"(?i)\bdebug\s*=\s*True\b"),
     "وضع التصحيح في الإنتاج يكشف المصادر — أطفئه واعرف خلف WSGI",
     None),
    ("pickle-load", "high",
     re.compile(r"pickle\.loads?\s*\("),
     "pickle على بيانات خارجية = تنفيذ تعسفي — استخدم JSON",
     None),
    ("weak-hash", "medium",
     re.compile(r"(?i)\b(md5|sha1)\s*\("),
     "تجزئة ضعيفة للسريات — استخدم bcrypt/argon2 (sha1 لبصمات الكاش المقبولة مقبول)",
     lambda ln: "md5" in ln.lower()
                or bool(re.search(r"(?i)password|passwd|pwd|token|secret", ln))),
    ("insecure-url", "medium",
     re.compile(r"http://(?!localhost|127\.|0\.0\.0\.0|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|www\.w3\.org)[a-zA-Z0-9]"),
     "نقل غير مشفر لعنوان عام — استخدم https:// (عناوين الشبكة المحلية والربط استثناء)",
     None),
    ("js-eval", "medium",
     re.compile(r"(?![\w.])eval\s*\("),
     "eval في JS — استخدم JSON.parse أو خريطة دوال",
     None),
    ("innerhtml", "medium",
     re.compile(r"innerHTML\s*=|dangerouslySetInnerHTML"),
     "حقن HTML مباشر = XSS — استخدم textContent/تنظيف المدخلات",
     None),
]

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

# قواعد الأسرار تُطبق على كل سطر حتى لو كان حرفية نصية — السر سر أينما كان
_SECRET_RULES = {"aws-key", "private-key", "token-literal", "password-literal"}
_STR_PREFIXES = ("rf\"", "fr\"", "r\"", "f\"", "r'", "f'", "\"", "'")


def _string_literal_line(line: str) -> bool:
    """سطر ليس إلا حرفية نصية (نمط حماية/توثيق/رسالة) — لا سلوكاً تنفيذياً فيه."""
    s = line.strip()
    if s.startswith(("\"\"\"", "'''")):
        return True
    if not s.startswith(_STR_PREFIXES):
        return False
    return s.rstrip("),").rstrip().endswith(("\"", "'"))


def scan_file(path: str | Path) -> list[dict]:
    p = Path(path)
    try:
        if p.stat().st_size > MAX_FILE_KB * 1024:
            return []
        text = p.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError):
        return []
    findings = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 2000:
            continue
        literal_line = _string_literal_line(line)
        for rule, sev, rx, hint, guard in RULES:
            m = rx.search(line)
            if m:
                # تعليقات الأمثلة الواضحة عن تغيير-مي لا تُبلَّغ
                if "CHANGE-ME" in line and rule == "password-literal":
                    continue
                # حرفية نصية أو تعريف نمط (re.compile) + قاعدة سلوك = نص لا كود
                if rule not in _SECRET_RULES and (literal_line
                                                  or "re.compile(" in line):
                    continue
                # شرط القاعدة الإضافي (دقة weak-hash مثلًا)
                if guard is not None and not guard(line):
                    continue
                findings.append({"file": str(p), "line": lineno,
                                 "rule": rule, "severity": sev,
                                 "match": m.group(0)[:60], "hint": hint,
                                 "snippet": line.strip()[:160]})
    return findings


def scan_project(root: str | Path) -> dict:
    """Full project scan, findings sorted critical-first, honest summary."""
    root = Path(root)
    t0, findings, n_files = time.time(), [], 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if Path(fn).suffix.lower() in SCAN_EXT:
                n_files += 1
                findings.extend(scan_file(Path(dirpath) / fn))
                if len(findings) >= MAX_FINDINGS:
                    findings = findings[:MAX_FINDINGS]
                    break
        if len(findings) >= MAX_FINDINGS:
            break
    findings.sort(key=lambda f: (_SEV_ORDER.get(f["severity"], 9), f["file"], f["line"]))
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return {"root": str(root), "files_scanned": n_files,
            "findings": findings, "counts": counts,
            "clean": not findings, "sec": round(time.time() - t0, 2)}


def report_text(res: dict, limit: int = 40) -> str:
    if res["clean"]:
        return (f"✅ النظيف مؤكد: {res['files_scanned']} ملفاً فحصها الماسح في "
                f"{res['sec']}s — بلا أي إشارة أمنية من {len(RULES)} قاعدة")
    lines = [(f"🛡️ فحص {res['files_scanned']} ملفاً في {res['sec']}s — "
              f"النتيجة: {res['counts']}")]
    for f in res["findings"][:limit]:
        lines.append(f"[{f['severity'].upper()}] {f['file']}:{f['line']} — "
                     f"{f['rule']}: {f['hint']} | {f['snippet'][:100]}")
    if len(res["findings"]) > limit:
        lines.append(f"… و{len(res['findings']) - limit} إشارة أخرى")
    return "\n".join(lines)


def sec_tools() -> dict:
    """Agent-facing registry — scan is read-only (always allowed)."""
    def _scan(ctx, path="", **a):
        root = path or str(ctx.workspace)
        try:
            res = scan_project(root)
            return True, report_text(res, 25)
        except Exception as exc:  # noqa: BLE001 — scanning must not kill the loop
            return False, f"تعذّر الفحص: {exc}"

    return {
        "security_scan": {
            "fn": _scan,
            "args": {"path": "str مجلد المشروع (افتراضي: مساحة العمل)"},
            "desc": "فحص أمني شامل: أسرار مكشوفة، حقن SQL، أوامر خطر، TLS معطل — بأدلة ملف:سطر وترتيب الخطورة"},
    }
