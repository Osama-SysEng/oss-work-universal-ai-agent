"""Prove the surgical-edit layer: edits are exact, atomic, and verified.

These tests encode the real incident that motivated the module: a 10KB
`server.py` whose `send_json` was fused with `else/finally` because a
whole-file rewrite was truncated. Editing surgically must never produce
that class of damage, and `verify_project` must catch it when it exists.
"""
import json

import osv_agent as ag
import osv_edit


def _ctx(tmp_path):
    return ag.AgentContext(tmp_path, "t")


def test_edit_file_replaces_once_and_keeps_crlf(tmp_path):
    p = tmp_path / "a.py"
    p.write_bytes(b"x = 1\r\ny = 2\r\n")
    ok, obs = osv_edit.edit_file(_ctx(tmp_path), "a.py", "y = 2", "y = 3")
    assert ok, obs
    assert p.read_bytes() == b"x = 1\r\ny = 3\r\n"


def test_edit_file_refuses_ambiguous_match(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("v = 1\nv = 1\n", encoding="utf-8")
    ok, obs = osv_edit.edit_file(_ctx(tmp_path), "a.py", "v = 1", "v = 9")
    assert not ok and "مرات" in obs
    assert p.read_text(encoding="utf-8") == "v = 1\nv = 1\n"


def test_edit_file_replace_all(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("v = 1\nv = 1\n", encoding="utf-8")
    ok, obs = osv_edit.edit_file(_ctx(tmp_path), "a.py", "v = 1", "v = 9",
                                 replace_all=True)
    assert ok, obs
    assert p.read_text(encoding="utf-8") == "v = 9\nv = 9\n"


def test_edit_file_missing_target_reports_near_line(tmp_path):
    p = tmp_path / "a.py"
    p.write_text("def send_json(obj):\n    pass\n", encoding="utf-8")
    ok, obs = osv_edit.edit_file(_ctx(tmp_path), "a.py",
                                 "def send_json(obj): pass", "x")
    assert not ok and "send_json" in obs


def test_edit_file_rejects_path_escape(tmp_path):
    ok, obs = osv_edit.edit_file(_ctx(tmp_path), "../evil.py", "a", "b")
    assert not ok and "مرفوض" in obs


def test_apply_patch_is_atomic_on_bad_hunk(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("a = 1\n", encoding="utf-8")
    patch = (
        "--- good.py\n+++ good.py\n@@ -1,1 +1,1 @@\n-a = 1\n+a = 2\n"
        "--- bad.py\n+++ bad.py\n@@ -1,1 +1,1 @@\n-MISSING\n+x\n"
    )
    ok, _obs = osv_edit.apply_patch(_ctx(tmp_path), patch)
    assert not ok
    # the whole patch is rejected: the good file must be untouched
    assert good.read_text(encoding="utf-8") == "a = 1\n"


def test_apply_patch_creates_and_edits(tmp_path):
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    patch = (
        "--- a.py\n+++ a.py\n@@ -1,1 +1,1 @@\n-a = 1\n+a = 2\n"
        "--- b.py\n+++ b.py\n@@ -0,0 +1,2 @@\n+b = 1\n+b = 2\n"
    )
    ok, obs = osv_edit.apply_patch(_ctx(tmp_path), patch)
    assert ok, obs
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "a = 2\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "b = 1\nb = 2\n"


def test_verify_project_catches_the_server_py_breakage(tmp_path):
    (tmp_path / "server.py").write_text(
        "def send_json(c, o):\n"
        "    c.send(1)\n"
        "    else:\n"
        "        pass\n", encoding="utf-8")
    ok, obs = osv_edit.verify_project(_ctx(tmp_path))
    assert not ok and "server.py" in obs and "سطر 3" in obs


def test_verify_project_reports_missing_html_asset(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><script src="app.js"></script></html>', encoding="utf-8")
    ok, obs = osv_edit.verify_project(_ctx(tmp_path))
    assert not ok and "app.js" in obs


def test_verify_project_checks_json_and_sqlite(tmp_path):
    (tmp_path / "bad.json").write_text("{oops", encoding="utf-8")
    ok, obs = osv_edit.verify_project(_ctx(tmp_path))
    assert not ok and "bad.json" in obs


def test_verify_project_green_on_clean_site(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><script src="app.js"></script></html>', encoding="utf-8")
    (tmp_path / "app.js").write_text("const a = 1;\n", encoding="utf-8")
    (tmp_path / "srv.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps({"ok": True}),
                                       encoding="utf-8")
    ok, obs = osv_edit.verify_project(_ctx(tmp_path))
    assert ok, obs
    assert "✅" in obs


def test_edit_tools_registry_shape():
    tools = osv_edit.edit_tools()
    assert set(tools) == {"edit_file", "apply_patch", "verify_project"}
    for spec in tools.values():
        assert callable(spec["fn"]) and spec["desc"] and spec["args"]
