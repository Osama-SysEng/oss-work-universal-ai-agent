"""OS_V1 Device — real device-control tools behind the permission gate.

The OpenClaw merge goal: the agent can reach the MACHINE (not just its
sandboxed workspace) — info, notifications, processes, files anywhere,
arbitrary commands — with every dangerous lane human-gated by osv_permissions.

Difference from the confined osv_agent tools (both stay, different jobs):
- osv_agent workspace tools: confinement IS the safety (nothing outside).
- osv_device tools: reach is the point; the PERMISSION GATE is the safety.
Every tool returns (ok, observation) and logs into the engine audit.
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

from osv_permissions import AskDenied, PermissionGate, default_rules_for_device_control

CMD_TIMEOUT_S = 45
MAX_OBS_CHARS = 6000

# ---------------------------------------------------------------------------
# OpenClaw port (clean-room, from exec-safe-bin-policy.ts:32-464): a tiny
# allowlist of read-only "safe bins" is the ONLY exec class auto-allowed
# beyond the cmd-pattern policy — each with its own dangerous-flag denylist
# (grep recursion, sort external compressor, tail follow, jq file args).
# Safe bins are STDIN-ONLY: no file args, no globs, no $ expansion, no paths.
# ---------------------------------------------------------------------------
_SAFE_BINS = {"cut", "uniq", "head", "tail", "tr", "wc", "grep", "sort", "jq"}
_SAFE_BIN_DENY_FLAGS = {
    "grep": {"-r", "-R", "-d", "-f", "--recursive"},
    "sort": {"--compress-program", "--output", "-o"},
    "tail": {"-f", "-F", "--follow", "--retry"},
    "jq": {"--argfile", "--rawfile", "--slurpfile"},
}
_REJECT_CHARS = "*?$<>|&;]([" + chr(92) + "/]"


def classify_safe_bin(command: str) -> bool:
    """True iff the command is exactly one safe bin + safe flags/values —
    the OpenClaw auto-approve lane, conservatively ported."""
    try:
        argv = shlex.split((command or "").strip(), posix=False)
    except ValueError:
        return False
    if not argv or argv[0].lower().strip('"') not in _SAFE_BINS:
        return False
    deny = _SAFE_BIN_DENY_FLAGS.get(argv[0].lower().strip('"'), set())
    for tok in argv[1:]:
        t = tok.strip('"')
        if not t:
            continue
        if any(ch in t for ch in _REJECT_CHARS) or re.search(r"[\w]:[/\\]", t):
            return False          # glob/expansion/path-like token (OpenClaw rule)
        if t.startswith("-"):
            low = t.lower()
            base = low.split("=")[0]
            if low in deny or base in deny or low[:2] in deny:
                return False      # this bin's dangerous flag (=value, attached, combined)
    return True


# Patterns that must NEVER run even in yolo (machine-killer class).
_HARD_DENY = re.compile(
    r"(\bformat\b|\bdiskpart\b|rd\s+/s\s+/q\s+[a-z]:\\?($|\s)|rmdir\s+/s"
    r"|\bvssadmin\b.*delete|\bbcdedit\b|\bcipher\s+/w\b|\bdel\s+/[sq]\s+[a-z]:\\($|\s))"
    r"|\breg\s+delete\s+HKLM\b|\bsfc\s*/scannow\b|\bdism\b\s+/online\s+/cleanup-image",
    re.IGNORECASE)


def _clip(text: str, limit: int = MAX_OBS_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n… [{len(text) - limit} حرفاً اقتُطعت]"


class DeviceKit:
    """One kit per session/run — holds its own gate (own saved grants)."""

    def __init__(self, gate: PermissionGate | None = None, yolo: bool = False):
        from osv_permissions import PermissionEngine
        engine = gate.engine if gate else PermissionEngine(
            yolo=yolo, rules=default_rules_for_device_control())
        self.gate = gate or PermissionGate(engine)

    def _gated(self, action: str, resource: str, what: str) -> str | None:
        """Run the gate; a refusal becomes the OBSERVATION the model sees
        (never an exception that kills the tool loop)."""
        try:
            self.gate.check(action, resource, what)
            return None
        except AskDenied as exc:
            return f"🛑 رُفضت بصلاحيات OSS — {exc}"

    # ------------------------------------------------------------------
    # device.info — the machine's live vitals (always allowed by policy)
    # ------------------------------------------------------------------
    def info(self) -> tuple[bool, str]:
        try:
            cpu = os.cpu_count() or "?"
            lines = [f"المعالج: {cpu} نواة منطقية"]
            try:
                import psutil  # optional dep
                vm = psutil.virtual_memory()
                lines.append(f"الذاكرة: {vm.used // (1 << 20)}/{vm.total // (1 << 20)} MB مستعملة ({vm.percent}٪)")
                du = psutil.disk_usage("C:\\")
                lines.append(f"القرص C: {du.used // (1 << 30)}/{du.total // (1 << 30)} GB ({du.percent}٪)")
                bat = psutil.sensors_battery()
                if bat:
                    lines.append(f"البطارية: {bat.percent}٪{' (شاحن موصول)' if bat.power_plugged else ''}")
            except ImportError:
                lines += self._wmic_fallback()
            up = subprocess.run(["powershell", "-NoProfile", "-Command",
                                 "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime"],
                                check=False, capture_output=True, text=True, timeout=15,
                                encoding="utf-8", errors="replace")
            if up.returncode == 0 and up.stdout.strip():
                lines.append(f"آخر إقلاع: {up.stdout.strip()[:40]}")
            return True, "\n".join(lines)
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذر جمع معلومات الجهاز: {exc}"

    @staticmethod
    def _wmic_fallback() -> list[str]:
        out = []
        for name, label in (("OS=Windows", "النظام"), ("totalPhysicalMemory", "الذاكرة")):
            _ = name, label  # wmic removed on modern Windows — keep it honest
        out.append("الذاكرة: مكتبة psutil غير مثبتة — فريق OSS يثبتها لاحقاً")
        return out

    # ------------------------------------------------------------------
    # device.notify — a real Windows toast from the agent
    # ------------------------------------------------------------------
    def notify(self, title: str, body: str = "") -> tuple[bool, str]:
        try:
            ps = ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, "
                  "ContentType = WindowsRuntime] | Out-Null; "
                  "$t=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent("
                  "[Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
                  f"$x=$t.GetElementsByTagName('text'); $x.Item(0).AppendChild($t.CreateTextNode('{title}'))|Out-Null; "
                  f"if('{body}'){{$x.Item(1).AppendChild($t.CreateTextNode('{body}'))|Out-Null}}; "
                  "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("
                  "'OSS Work').Show([Windows.UI.Notifications.ToastNotification]::new($t))")
            p = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                               check=False, capture_output=True, text=True, timeout=20,
                               encoding="utf-8", errors="replace")
            return (p.returncode == 0), ("أُرسل الإشعار" if p.returncode == 0
                                         else f"فشل الإشعار: {p.stderr[:120]}")
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذر الإشعار: {exc}"

    # ------------------------------------------------------------------
    # device.process — list free, kill gated
    # ------------------------------------------------------------------
    def process_list(self, filter: str = "") -> tuple[bool, str]:
        try:
            p = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                               check=False, capture_output=True, text=True, timeout=20,
                               encoding="utf-8", errors="replace")
            rows = []
            for line in p.stdout.splitlines():
                parts = [c.strip('"') for c in line.split('","')]
                if len(parts) >= 2 and (not filter or filter.lower() in parts[0].lower()):
                    rows.append(f"{parts[0]} (pid {parts[1]}) {parts[4] if len(parts) > 4 else ''}")
            rows = rows[:60]
            return True, "\n".join(rows) or "(لا عمليات مطابقة)"
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذر إدراج العمليات: {exc}"

    def process_kill(self, pid: int, what: str = "") -> tuple[bool, str]:
        what = what or f"إنهاء العملية رقم {pid}"
        denied = self._gated("device.process.kill", f"pid:{pid}", what)
        if denied:
            return False, denied
        try:
            p = subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               check=False, capture_output=True, text=True, timeout=15,
                               encoding="utf-8", errors="replace")
            return (p.returncode == 0), (f"أُنهيت العملية {pid}" if p.returncode == 0
                                         else f"فشل الإنهاء: {p.stderr[:120]}")
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذر الإنهاء: {exc}"

    # ------------------------------------------------------------------
    # device.file — read/write ANYWHERE, path-gated (the big-reach lane)
    # ------------------------------------------------------------------
    def file_read(self, path: str) -> tuple[bool, str]:
        p = Path(path)
        denied = self._gated("device.file.read",
                             f"path:{p.resolve().as_posix() if p.exists() else path}",
                             f"قراءة الملف {path}")
        if denied:
            return False, denied
        if not p.is_file():
            return False, f"الملف غير موجود: {path}"
        try:
            return True, _clip(p.read_text(encoding="utf-8", errors="replace"), 12000)
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذرت القراءة: {exc}"

    def file_write(self, path: str, content: str) -> tuple[bool, str]:
        p = Path(path)
        exists = p.exists()
        denied = self._gated("device.file.write",
                             f"path:{p.resolve().as_posix() if exists else path}",
                             f"{'تعديل' if exists else 'إنشاء'} الملف {path}")
        if denied:
            return False, denied
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return True, f"كُتب {path} ({len(content)} حرفاً)"
        except Exception as exc:  # noqa: BLE001
            return False, f"تعذر الكتابة: {exc}"

    # ------------------------------------------------------------------
    # device.exec — arbitrary command, cmd-pattern gated, env stripped
    # ------------------------------------------------------------------
    def exec(self, command: str) -> tuple[bool, str]:
        if _HARD_DENY.search(command or ""):
            self.gate.engine._log("device.exec", f"cmd:{command}", "deny", "hard-deny")
            return False, "أمر محظور نهائياً (فئة مدمرة للجهاز) — حتى وضع الثقة الكاملة"
        verdict = self.gate.engine.evaluate("device.exec", f"cmd:{command}")
        if verdict == "deny":
            self.gate.engine._log("device.exec", f"cmd:{command}", "deny", "policy")
            return False, "🛑 رُفضت بسياسة صلاحيات OSS (منع صريح)"
        if verdict == "ask" and not classify_safe_bin(command):
            denied = self._gated("device.exec", f"cmd:{command}", f"تنفيذ الأمر: {command}")
            if denied:
                return False, denied
        if verdict == "ask":
            # safe-bin lane: read-only stdin-only probes run without asking
            # (OpenClaw exec-safe-bin-policy — the only auto-allow exec class)
            self.gate.engine._log("device.exec", f"cmd:{command}", "allow", "safe-bin")
        env = {k: os.environ.get(k, "") for k in
               ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP",
                "LOCALAPPDATA", "APPDATA", "USERPROFILE", "PYTHONIOENCODING")}
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            p = subprocess.run(
                ["cmd", "/c", command] if os.name == "nt" else ["bash", "-c", command],
                check=False, env=env, capture_output=True, text=True,
                stdin=subprocess.DEVNULL,   # OpenClaw port: empty stdin — no blocking readers
                timeout=CMD_TIMEOUT_S, encoding="utf-8", errors="replace")
            obs = f"exit={p.returncode}"
            if p.stdout.strip():
                obs += f"\nstdout:\n{p.stdout.strip()}"
            if p.stderr.strip():
                obs += f"\nstderr:\n{p.stderr.strip()}"
            return p.returncode == 0, _clip(obs)
        except subprocess.TimeoutExpired:
            return False, f"انتهت مهلة الأمر ({CMD_TIMEOUT_S}s) — أُلغي"
        except Exception as exc:  # noqa: BLE001
            return False, f"فشل التنفيذ: {exc}"


# ---------------------------------------------------------------------------
# Registry — plugs into the agent tool loop (osv_agent.TOOLS shape)
# ---------------------------------------------------------------------------

def device_tools(kit: DeviceKit) -> dict:
    """Build the tool descriptors; each fn closure keeps its kit."""
    return {
        "device_info":     {"fn": lambda ctx, **a: kit.info(),
                            "args": {}, "desc": "قياسات حية للجهاز (معالج/ذاكرة/قرص/بطارية)"},
        "device_notify":   {"fn": lambda ctx, title="OS_V1", body="", **a: kit.notify(title, body),
                            "args": {"title": "str", "body": "str (اختياري)"},
                            "desc": "إشعار ويندوز حقيقي على شاشة المستخدم"},
        "device_ps":       {"fn": lambda ctx, filter="", **a: kit.process_list(filter),
                            "args": {"filter": "str (اختياري)"},
                            "desc": "إدراج العمليات العاملة على الجهاز"},
        "device_kill":     {"fn": lambda ctx, pid=0, **a: kit.process_kill(int(pid)),
                            "args": {"pid": "int"}, "desc": "إنهاء عملية — يحتاج موافقة"},
        "device_read":     {"fn": lambda ctx, path="", **a: kit.file_read(path),
                            "args": {"path": "str مسار كامل"}, "desc": "قراءة أي ملف على الجهاز (بمسار كامل)"},
        "device_write":    {"fn": lambda ctx, path="", content="", **a: kit.file_write(path, content),
                            "args": {"path": "str مسار كامل", "content": "str"},
                            "desc": "كتابة/إنشاء أي ملف على الجهاز (بمسار كامل)"},
        "device_exec":     {"fn": lambda ctx, command="", **a: kit.exec(command),
                            "args": {"command": "str"}, "desc": "تنفيذ أمر على الجهاز الحقيقي (مصنّف بالصلاحيات)"},
    }


DEVICE_DENY_ASK = {  # these tools can be removed wholesale by policy
    "device_kill", "device_exec", "device_write",
}
