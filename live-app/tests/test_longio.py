# -*- coding: utf-8 -*-
"""Long-io: the million-token lanes — honest truncation in, stitched verified
output out."""
import py_compile

import pytest

import osv_agent as ag
import osv_longio as li


# ------------------------------------------------------------------ tokens

def test_estimate_tokens_positive_and_monotone():
    assert li.estimate_tokens("") == 1
    assert li.estimate_tokens("ا" * 320) > li.estimate_tokens("ا" * 32)


# ------------------------------------------------------------------ dossier

def _mk_ws(tmp_path):
    (tmp_path / "main.py").write_text("print('entry')\n" * 5, encoding="utf-8")
    (tmp_path / "lib.py").write_text("x = 1\n" * 30, encoding="utf-8")
    (tmp_path / "README.md").write_text("# doc\n" * 10, encoding="utf-8")
    sub = tmp_path / "node_modules"
    sub.mkdir()
    (sub / "junk.js").write_text("var x;\n" * 10, encoding="utf-8")
    return tmp_path


def test_dossier_packs_and_maps_every_file(tmp_path):
    root = _mk_ws(tmp_path)
    pack = li.dossier(root, budget_tokens=5000)
    assert "main.py" in pack["text"] and "lib.py" in pack["text"]
    assert pack["map"]["main.py"]["chunks_taken"] == 1
    assert "node_modules" not in pack["text"]          # skip dirs really skip
    assert pack["truncated"] == []                     # budget was generous


def test_dossier_truncation_is_labeled_not_silent(tmp_path):
    root = tmp_path
    (tmp_path / "big.py").write_text("y = 1\n" * 4000, encoding="utf-8")
    pack = li.dossier(root, budget_tokens=300)
    assert pack["truncated"] == ["big.py"]             # the cut is a FACT
    assert "مقطوعة" in pack["text"]                    # labeled inside
    assert pack["map"]["big.py"]["chunks_taken"] == 1
    assert pack["map"]["big.py"]["chunks_total"] == 2


def test_dossier_priority_entrypoints_first(tmp_path):
    root = tmp_path
    (root / "zzz.md").write_text("tail\n", encoding="utf-8")
    (root / "main.py").write_text("HEAD_OF_PACK\n", encoding="utf-8")
    pack = li.dossier(root, budget_tokens=400)
    assert pack["text"].index("HEAD_OF_PACK") < pack["text"].index("tail")


# ---------------------------------------------------------------- long_write

def _ctx(tmp_path):
    return ag.AgentContext(tmp_path, "longio")


def test_long_write_stitches_parts_and_compiles(tmp_path):
    ctx = _ctx(tmp_path)
    ok1, _m1 = li.long_write(ctx, "big.py", "def f():\n", part=1, total=2)
    assert ok1 and "أكمل الجزء 2" in _m1
    ok2, m2 = li.long_write(ctx, "big.py", "    return 42\n", part=2, total=2)
    assert ok2 and "اكتمل" in m2 and "يُترجم" in m2
    assert (tmp_path / "big.py").read_text(encoding="utf-8") == \
        "def f():\n    return 42\n"
    py_compile.compile(str(tmp_path / "big.py"), doraise=True)


def test_long_write_broken_final_part_is_refused_not_shipped(tmp_path):
    ctx = _ctx(tmp_path)
    li.long_write(ctx, "bad.py", "def f(:\n", part=1, total=1)
    ok, msg = li.long_write(ctx, "bad.py", "def f(:\n", part=1, total=1)
    assert not ok and "مرفوض" in msg and "لا يُترجم" in msg


def test_long_write_out_of_order_part_is_an_error(tmp_path):
    ctx = _ctx(tmp_path)
    ok, msg = li.long_write(ctx, "x.txt", "content", part=3, total=2)
    assert not ok and "خارج النطاق" in msg


def test_long_write_strips_code_fences(tmp_path):
    ctx = _ctx(tmp_path)
    fenced = "```python\nprint('clean')\n```"
    ok, _m = li.long_write(ctx, "fenced.py", fenced, part=1, total=1)
    assert ok
    assert (tmp_path / "fenced.py").read_text(encoding="utf-8") == \
        "print('clean')"


def test_long_write_rejects_workspace_escape(tmp_path):
    ctx = _ctx(tmp_path)
    ok, msg = li.long_write(ctx, "../outside.txt", "nope", part=1, total=1)
    assert not ok and "مرفوض" in msg


def test_ingest_tool_writes_pack_and_reports(tmp_path, monkeypatch):
    monkeypatch.setattr(li, "_CHARS_PER_TOKEN", 3.2)
    root = tmp_path / "ws"
    root.mkdir()
    _mk_ws(root)
    ctx = _ctx(root)
    ok, msg = li.longio_tools()["ingest"]["fn"](ctx, ".", 20000)
    assert ok and "context_pack.md" in msg
    pack_file = tmp_path / "ws" / "context_pack.md"
    assert pack_file.is_file() and "main.py" in pack_file.read_text(
        encoding="utf-8")
