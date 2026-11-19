"""osv_clean.py — حذف آمن للمخلفات + تدقيق صحة الجهاز.

المبدأ: الفحص قراءة فقط ويشمل أي مسار. الحذف **لا يخرج أبداً** عن مجلدات
النظام المؤقتة، ولا يمسّ ملفاً أحدث من العمر المطلوب، ولا يتبع روابط/وصلات،
ويبدأ دائماً بـ dry_run. أي مسار خارج الجذور المسموحة يُرفض ويُبلَّغ السبب.

What it reports: junk candidates (tmp/log/bak/dmp/part...), executables and
scripts sitting in temp (malware's favourite parking lot), double-extension
files, and the Run/RunOnce autostart entries with suspicious commands.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

JUNK_EXT = {".tmp", ".temp", ".log", ".bak", ".old", ".dmp", ".chk", ".part",
            ".crdownload", ".~lock", ".swp", ".swo", ".gid", ".etl", ".mdmp"}
SUSPICIOUS_EXT = {".exe", ".scr", ".bat", ".cmd", ".ps1", ".vbs", ".vbe",
                  ".js", ".jse", ".wsf", ".hta", ".lnk", ".pif", ".msi"}
MAX_WALK = 20000          # سقف ملفات الفحص حتى لا يجمد الجهاز
MAX_DELETE_MB = 2048      # سقف الحذف في نداء واحد


def _temp_roots() -> list[Path]:
    cands = [os.environ.get("TEMP"), os.environ.get("TMP"),
             str(Path(os.environ.get("LOCALAPPDATA", "")) / "Temp"),
             str(Path(os.environ.get("WINDIR", r"C:\Windows")) / "Temp")]
    out, seen = [], set()
    for c in cands:
        if not c:
            continue
        p = Path(c)
        try:
            rp = p.resolve()
        except OSError:
            continue
        if rp.is_dir() and str(rp).lower() not in seen:
            seen.add(str(rp).lower())
            out.append(rp)
    return out


def _inside_allowed(p: Path, roots: list[Path]) -> bool:
    try:
        rp = p.resolve()
    except OSError:
        return False
    return any(rp == r or r in rp.parents for r in roots)


def _walk_files(root: Path):
    """لا يتبع الروابط/الوصلات، ويتوقف عند سقف MAX_WALK."""
    count = 0
    stack = [root]
    while stack and count < MAX_WALK:
        cur = stack.pop()
        try:
            entries = list(os.scandir(cur))
        except OSError:
            continue
        for e in entries:
            try:
                if e.is_symlink():
                    continue
                if e.is_dir(follow_symlinks=False):
                    stack.append(Path(e.path))
                    continue
                if e.is_file(follow_symlinks=False):
                    st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            count += 1
            yield Path(e.path), st
            if count >= MAX_WALK:
                return


def scan(paths: list[str] | None = None, min_age_days: float = 0.0,
         max_items: int = 60) -> tuple[bool, str]:
    roots = [Path(p) for p in paths] if paths else _temp_roots()
    roots = [r for r in roots if r.is_dir()]
    if not roots:
        return False, "لا مجلدات مؤقتة صالحة للفحص"
    now = time.time()
    total_n = total_b = junk_n = junk_b = 0
    by_ext: dict[str, list[int]] = {}
    junk: list[tuple[float, int, Path]] = []
    suspicious: list[Path] = []
    double_ext: list[Path] = []
    for root in roots:
        for p, st in _walk_files(root):
            total_n += 1
            total_b += st.st_size
            ext = p.suffix.lower()
            agg = by_ext.setdefault(ext or "(بلا امتداد)", [0, 0])
            agg[0] += 1
            agg[1] += st.st_size
            age_days = (now - st.st_mtime) / 86400
            if ext in SUSPICIOUS_EXT:
                suspicious.append(p)
            if len(p.suffixes) >= 2 and p.suffixes[-1].lower() in SUSPICIOUS_EXT:
                double_ext.append(p)
            if ext in JUNK_EXT and age_days >= min_age_days:
                junk_n += 1
                junk_b += st.st_size
                junk.append((st.st_mtime, st.st_size, p))
    lines = [(f"🧹 فحص {len(roots)} مجلداً مؤقتاً: {total_n} ملفاً، "
              f"{total_b / 1048576:.1f} MB")]
    lines.append(f"مرشّحات التنظيف (امتدادات مؤقتة، أقدم من {min_age_days:g} يوم): "
                 f"{junk_n} ملفاً، {junk_b / 1048576:.1f} MB")
    if by_ext:
        top = sorted(by_ext.items(), key=lambda kv: -kv[1][1])[:6]
        lines.append("أكبر الامتدادات: " + " · ".join(
            f"{k or '—'} {v[0]}ملف/{v[1] / 1048576:.1f}MB" for k, v in top))
    if suspicious:
        lines.append(f"⚠️ ملفات تنفيذية/سكربتات داخل المؤقت: {len(suspicious)} "
                     f"(أولها: {', '.join(p.name for p in suspicious[:5])})")
    if double_ext:
        lines.append("🚨 امتداد مزدوج مشبوه (مثل pdf.exe): " +
                     ", ".join(p.name for p in double_ext[:5]))
    junk.sort(key=lambda x: -x[1])
    if junk:
        lines.append("أكبر مرشّحات الحذف: " + " | ".join(
            f"{p.name} {b / 1024:.0f}KB" for _, b, p in junk[:max_items]))
    startup = _startup_entries()
    if startup:
        lines.append("🚀 بدء التشغيل:")
        for hive, name, cmd, risky in startup[:12]:
            flag = " ⚠️" if risky else ""
            lines.append(f"  [{hive}] {name} = {cmd[:110]}{flag}")
    return True, "\n".join(lines)


def _startup_entries() -> list[tuple[str, str, str, bool]]:
    """قراءة Run/RunOnce فقط — بلا أي تعديل."""
    out: list[tuple[str, str, str, bool]] = []
    try:
        import winreg
    except ImportError:
        return out
    keys = [
        ("HKCU", winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\Run"),
        ("HKCU", winreg.HKEY_CURRENT_USER,
         r"Software\Microsoft\Windows\CurrentVersion\RunOnce"),
        ("HKLM", winreg.HKEY_LOCAL_MACHINE,
         r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ]
    bad_markers = ("\\temp\\", "\\tmp\\", "appdata\\roaming\\", ".vbs", ".js",
                   ".bat", ".cmd", ".ps1", "-enc", "powershell -w hidden")
    for hive, root, sub in keys:
        try:
            with winreg.OpenKey(root, sub) as k:
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    cmd = str(val)
                    low = cmd.lower()
                    risky = any(m in low for m in bad_markers)
                    out.append((hive, str(name), cmd, risky))
        except OSError:
            continue
    return out


def apply(older_than_days: float = 7.0, dry_run: bool = True,
          include_suspicious: bool = False, paths: list[str] | None = None,
          max_mb: int = MAX_DELETE_MB) -> tuple[bool, str]:
    roots = _temp_roots()
    if not roots:
        return False, "لا مجلدات مؤقتة معروفة — لا حذف"
    targets = [Path(p) for p in paths] if paths else roots
    denied = [str(p) for p in targets if not _inside_allowed(p, roots)]
    if denied:
        return False, ("🚫 الحذف مسموح داخل المجلدات المؤقتة فقط. مرفوض: "
                       + ", ".join(denied[:5]))
    exts = set(JUNK_EXT)
    if include_suspicious:
        exts |= SUSPICIOUS_EXT
    now = time.time()
    cutoff = now - older_than_days * 86400
    deleted_n = deleted_b = skipped = 0
    examples: list[str] = []
    budget = max(1, int(max_mb)) * 1024 * 1024
    for root in targets:
        if not root.is_dir():
            continue
        for p, st in _walk_files(root):
            if deleted_b >= budget:
                break
            if p.suffix.lower() not in exts:
                continue
            if st.st_mtime > cutoff:
                continue
            if not _inside_allowed(p, roots):
                continue
            if dry_run:
                deleted_n += 1
                deleted_b += st.st_size
                if len(examples) < 20:
                    examples.append(f"{p.name} ({st.st_size // 1024}KB)")
                continue
            try:
                size = st.st_size
                p.unlink(missing_ok=True)
                deleted_n += 1
                deleted_b += size
                if len(examples) < 20:
                    examples.append(f"{p.name} ({size // 1024}KB)")
            except OSError:
                skipped += 1
    verb = "سيُحذف" if dry_run else "حُذف"
    tail = "" if not dry_run else " — هذه معاينة فقط (dry_run). نفّذ بـ dry_run=false للحذف الفعلي."
    return True, (f"🧹 {verb} {deleted_n} ملفاً ({deleted_b / 1048576:.1f} MB)"
                  + (f"، تُخطّي {skipped} قيد الاستخدام" if skipped else "")
                  + (": " + " | ".join(examples[:12]) if examples else "")
                  + tail)


def clean_tools(kit=None) -> dict:
    """registry: الفحص متاح دائماً؛ الحذف يتطلب وضع «أدوات كاملة»."""
    def _scan(ctx, paths=None, min_age_days=0, max_items=60, **a):
        if isinstance(paths, str):
            paths = [paths]
        return scan(paths, float(min_age_days), int(max_items))

    def _apply(ctx, older_than_days=7, dry_run=True, include_suspicious=False,
               paths=None, max_mb=2048, **a):
        # 18 Nov live: DeviceKit.yolo is not a real attribute — the flag
        # lives on kit.gate.engine.yolo; checking the wrong one refused
        # every full-mode call.
        yolo = False
        if kit is not None:
            engine = getattr(getattr(kit, "gate", None), "engine", None)
            yolo = bool(getattr(engine, "yolo", False))
        if not yolo:
            return False, ("🛑 الحذف يحتاج وضع «أدوات كاملة» في الواجهة "
                           "(الافتراضي الآمن لا يحذف ملفات الجهاز)")
        if isinstance(paths, str):
            paths = [paths]
        return apply(float(older_than_days), bool(dry_run),
                     bool(include_suspicious), paths, int(max_mb))

    return {
        "cleanup_scan": {
            "fn": _scan,
            "args": {"paths": "list[str] اختياري — الافتراضي مجلدات النظام المؤقتة",
                     "min_age_days": "float عمر أدنى لمرشّحات الحذف (0=الكل)",
                     "max_items": "int أقصى أمثلة تُعرض"},
            "desc": "تدقيق قراءة فقط للمخلفات: الحجم والامتدادات، ملفات تنفيذية داخل المؤقت، امتدادات مزدوجة، ومداخل بدء التشغيل المشبوهة",
        },
        "cleanup_apply": {
            "fn": _apply,
            "args": {"older_than_days": "float (افتراضي 7)",
                     "dry_run": "bool (افتراضي true — معاينة بلا حذف)",
                     "include_suspicious": "bool حذف exe/scr/bat… أيضاً (افتراضي false)",
                     "paths": "list[str] داخل مجلدات المؤقت فقط",
                     "max_mb": "int سقف الحذف"},
            "desc": "حذف آمن للمخلفات داخل مجلدات المؤقت فقط، بعمر أدنى، بمعاينة افتراضية ورفض أي مسار خارج المؤقت",
        },
    }
