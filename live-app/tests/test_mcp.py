"""MCP client against a REAL server process (JSON-RPC 2.0 over stdio).

The client is never mocked: these tests spawn an actual python MCP server,
perform the full initialize → tools/list → tools/call handshake, and prove
the honesty path (missing server, dead command, tool-declared error)."""
import json
import sys

import pytest

import osv_mcp as mc

FAKE_SERVER = r'''
import sys, json
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    msg = json.loads(line)
    method = msg.get("method", "")
    if method == "initialize":
        rsp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
            "protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
            "serverInfo": {"name": "fake-echo", "version": "1.0"}}}
    elif method == "tools/list":
        rsp = {"jsonrpc": "2.0", "id": msg["id"], "result": {"tools": [
            {"name": "echo", "description": "يرد بنفس النص",
             "inputSchema": {"type": "object",
                             "properties": {"text": {"type": "string"}}}},
            {"name": "fail", "description": "يفشل بإعلان صريح",
             "inputSchema": {"type": "object", "properties": {}}}]}}
    elif method == "tools/call":
        args = msg["params"]["arguments"]
        if msg["params"]["name"] == "fail":
            rsp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
                "isError": True,
                "content": [{"type": "text", "text": "فشل متعمد للاختبار"}]}}
        else:
            rsp = {"jsonrpc": "2.0", "id": msg["id"], "result": {
                "content": [{"type": "text", "text": args.get("text", "")}]}}
    else:
        continue
    sys.stdout.write(json.dumps(rsp, ensure_ascii=False) + "\n")
    sys.stdout.flush()
'''


@pytest.fixture()
def server_env(tmp_path, monkeypatch):
    """A real config file pointing at a real spawned fake server."""
    srv = tmp_path / "fake_mcp_server.py"
    srv.write_text(FAKE_SERVER, encoding="utf-8")
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(json.dumps({
        "fake": {"command": sys.executable, "args": [str(srv)]}}),
        encoding="utf-8")
    monkeypatch.setattr(mc, "_cfg_path", lambda: cfg)
    return cfg


# ------------------------------------------------------------------ config

def test_load_servers_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_cfg_path",
                        lambda: tmp_path / "لا_أوجد.json")
    assert mc.load_servers() == {}


def test_load_servers_reads_config(server_env):
    assert "fake" in mc.load_servers()


# ------------------------------------------------------------- real session

def test_full_handshake_list_and_call_with_utf8(server_env):
    sess = mc.open_server("fake")            # REAL process + initialize
    try:
        tools = sess.list_tools()
        assert {t["name"] for t in tools} >= {"echo", "fail"}
        out = sess.call("echo", {"text": "مرحبا MCP 42"})
        assert out == "مرحبا MCP 42"         # Arabic + UTF-8 roundtrip
    finally:
        sess.close()


def test_tool_declared_error_is_surfaced_not_hidden(server_env):
    sess = mc.open_server("fake")
    try:
        out = sess.call("fail", {})
        assert out.startswith("⚠️ الأداة أعلنت فشلاً")
        assert "فشل متعمد" in out
    finally:
        sess.close()


# ------------------------------------------------------------ honesty paths

def test_missing_server_name_is_actionable_error(server_env):
    with pytest.raises(RuntimeError) as ei:
        mc.open_server("مجهول")
    assert "لا يوجد خادم" in str(ei.value)
    assert "mcp_servers.json" in str(ei.value)   # tells the user the remedy


def test_dead_command_raises_honestly(tmp_path, monkeypatch):
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(json.dumps({
        "dead": {"command": "no_such_executable_xyz_9137"}}), encoding="utf-8")
    monkeypatch.setattr(mc, "_cfg_path", lambda: cfg)
    with pytest.raises(RuntimeError) as ei:
        mc.open_server("dead")
    assert "فشل بدء" in str(ei.value)


def test_hung_server_times_out_never_hangs(tmp_path, monkeypatch):
    """A silent server must surface as a timeout error — the agent never
    freezes behind a dead pipe."""
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(json.dumps({
        "silent": {"command": sys.executable,
                   "args": ["-c", "import time; time.sleep(60)"]}}),
        encoding="utf-8")
    monkeypatch.setattr(mc, "_cfg_path", lambda: cfg)
    # open manually with a tiny rpc timeout to keep the test fast
    sess = mc.McpSession(sys.executable, ["-c", "import time; time.sleep(60)"])
    try:
        with pytest.raises(RuntimeError) as ei:
            sess._rpc("tools/list", timeout=2)
        assert "تجاوز المهلة" in str(ei.value)
    finally:
        sess.close()


# --------------------------------------------------------- agent tool surface

def test_mcp_list_without_config_is_honest(tmp_path, monkeypatch):
    monkeypatch.setattr(mc, "_cfg_path",
                        lambda: tmp_path / "لا_أوجد.json")
    tools = mc.mcp_tools()
    ok, msg = tools["mcp_list"]["fn"](None)
    assert ok and "لا خوادم" in msg and "mcp_servers.example.json" in msg


def test_mcp_list_reports_live_server_tools(server_env):
    tools = mc.mcp_tools()
    ok, msg = tools["mcp_list"]["fn"](None)
    assert ok and "[fake] 2 أداة" in msg and "echo" in msg


def test_mcp_call_through_tool_surface(server_env):
    tools = mc.mcp_tools()
    ok, out = tools["mcp_call"]["fn"](None, server="fake", tool="echo",
                                      arguments={"text": "تمرير حي"})
    assert ok and out == "تمرير حي"


def test_mcp_call_missing_args_is_guidance(server_env):
    tools = mc.mcp_tools()
    ok, msg = tools["mcp_call"]["fn"](None)
    assert not ok and "server" in msg and "tool" in msg
