"""OS_V MCP — Model Context Protocol client (stdio transport).

The industry standard for extending an agent with EXTERNAL tools: any MCP
server (filesystem, database, browser, whatever the user runs) plugs into
OS_V1 through one module. Clean-room implementation of the JSON-RPC 2.0
handshake over stdin/stdout per the public MCP spec — no SDK, stdlib only.

Honesty law: a server that fails to start, hangs, or returns an error is
reported verbatim — an MCP tool failure is a fact, never hidden or faked.
A hung server can NEVER hang the agent: every RPC runs under a hard deadline.
Servers are configured by the user in data/mcp_servers.json (commands,
never keys — OSS law 1)."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

_CALL_TIMEOUT_S = 60


def _cfg_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "mcp_servers.json"


def load_servers() -> dict:
    """{name: {command, args?, env?}} — missing file means no servers, loudly."""
    p = _cfg_path()
    if not p.is_file():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return obj if isinstance(obj, dict) else {}


class McpSession:
    """One JSON-RPC session over a spawned server process (stdio transport).

    Thread-safe: MCP stdio is single-stream, so every write locks; responses
    are matched by incrementing id. A background reader thread feeds a queue
    so a dead or silent server surfaces as a timeout error, never a hang."""

    def __init__(self, command: str, args: list[str] | None = None,
                 env: dict | None = None):
        self._proc = subprocess.Popen(
            [command, *(args or [])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env={**os.environ, **(env or {})},
            text=True, encoding="utf-8", bufsize=1)
        self._lock = threading.Lock()
        self._next_id = 0
        self._out_q: queue.Queue = queue.Queue()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def _read_loop(self):
        try:
            for line in self._proc.stdout:
                self._out_q.put(line)
        except (ValueError, OSError):      # closed pipes during shutdown
            pass
        self._out_q.put("")                # EOF sentinel

    def _rpc(self, method: str, params: dict | None = None,
             timeout: int = 30, notify: bool = False) -> dict | None:
        with self._lock:
            body: dict = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                body["params"] = params
            if not notify:
                self._next_id += 1
                body["id"] = self._next_id
            self._proc.stdin.write(json.dumps(body) + "\n")
            self._proc.stdin.flush()
            if notify:
                return None
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(
                        f"تجاوز المهلة ({timeout}ث) بانتظار رد {method} — "
                        "الخادم صامت أو معلّق")
                try:
                    line = self._out_q.get(timeout=remaining)
                except queue.Empty:
                    continue               # loop re-checks the deadline
                if not line:
                    raise RuntimeError("أغلق خادم MCP الخرج فجأة")
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue               # logs on stdout — skip
                if msg.get("id") == body["id"]:
                    if "error" in msg:
                        raise RuntimeError(
                            f"خطأ MCP: {json.dumps(msg['error'])[:200]}")
                    return msg.get("result")

    def initialize(self) -> dict:
        res = self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "osv1-agent", "version": "1.0"}})
        self._rpc("notifications/initialized", notify=True)
        return res or {}

    def list_tools(self) -> list[dict]:
        res = self._rpc("tools/list") or {}
        return res.get("tools", [])

    def call(self, tool: str, args: dict | None = None,
             timeout: int = _CALL_TIMEOUT_S) -> str:
        res = self._rpc("tools/call",
                        {"name": tool, "arguments": args or {}},
                        timeout=timeout) or {}
        content = res.get("content") or []
        texts = [c.get("text", "") for c in content
                 if isinstance(c, dict) and c.get("type") == "text"]
        out = "\n".join(t for t in texts if t)
        if res.get("isError"):
            return f"⚠️ الأداة أعلنت فشلاً: {out[:400]}"
        return out or "(رد فارغ من الأداة)"

    def close(self):
        try:
            self._proc.stdin.close()
            self._proc.terminate()
        except (OSError, ValueError):  # a dying process is closed however it dies
            pass


def open_server(name: str) -> McpSession:
    """Spawn + initialize one configured server. Raises with an honest,
    actionable message when the config is missing or the process is dead."""
    servers = load_servers()
    if name not in servers:
        raise RuntimeError(
            f"لا يوجد خادم MCP باسم '{name}' — المعرّفون: "
            f"{sorted(servers) or 'لا أحد'}. أضفه في data/mcp_servers.json")
    cfg = servers[name] or {}
    cmd = str(cfg.get("command", "")).strip()
    if not cmd:
        raise RuntimeError(f"خادم '{name}' بلا command في الإعدادات")
    sess: McpSession | None = None
    try:
        sess = McpSession(cmd, cfg.get("args"), cfg.get("env"))
        sess.initialize()
    except Exception as exc:  # honest, actionable failure
        if sess is not None:
            try:
                sess.close()
            except (OSError, ValueError):  # never mask the real error
                pass
        raise RuntimeError(
            f"فشل بدء خادم '{name}' ({cmd}): {str(exc)[:200]}") from exc
    return sess


# --------------------------------------------------------------------------
# Agent tool surface (registered via mcp_tools() like tm.team_tool())
# --------------------------------------------------------------------------

def mcp_tools():
    """Two tools the agent sees: mcp_list (discovery) + mcp_call (invocation).
    Each call opens a fresh session — MCP servers are processes; a long-lived
    pool is a later optimization, correctness first."""

    def _list(ctx, **_a):
        servers = load_servers()
        if not servers:
            return True, ("لا خوادم MCP مُعدّة. أضفها في data/mcp_servers.json "
                          "بالشكل: {\"اسم\": {\"command\": \"برنامج\", "
                          "\"args\": [...]}} — مثال جاهز: "
                          "mcp_servers.example.json")
        out = []
        for name in servers:
            try:
                sess = open_server(name)
                tools = sess.list_tools()
                sess.close()
                out.append(f"[{name}] {len(tools)} أداة: " + ", ".join(
                    t.get("name", "?") for t in tools[:10]))
            except Exception as exc:  # noqa: BLE001 — a dead server is a fact
                out.append(f"[{name}] ⚠️ غير متاح: {str(exc)[:120]}")
        return True, "\n".join(out)

    def _call(ctx, server="", tool="", arguments=None, **_a):
        if not server or not tool:
            return False, "مطلوب: server و tool (اسأل mcp_list عن المتاح)"
        try:
            sess = open_server(str(server))
        except RuntimeError as exc:
            return False, str(exc)
        try:
            res = sess.call(str(tool), arguments if isinstance(arguments, dict)
                            else {})
            return True, res
        except Exception as exc:  # noqa: BLE001 — the failure is the answer
            return False, f"⚠️ فشل mcp_call({server}.{tool}): {str(exc)[:250]}"
        finally:
            sess.close()

    return {
        "mcp_list": {"fn": _list, "args": {},
                     "desc": "يكتشف خوادم MCP الخارجية المُعدّة وأدواتها — "
                             "قدرات إضافية خارج الصندوق"},
        "mcp_call": {"fn": _call,
                     "args": {"server": "str اسم الخادم",
                              "tool": "str اسم الأداة",
                              "arguments": "dict وسائط الأداة"},
                     "desc": "ينفذ أداة على خادم MCP خارجي (ملفات/قواعد "
                             "بيانات/متصفح... حسب ما شغّله المستخدم)"},
    }
