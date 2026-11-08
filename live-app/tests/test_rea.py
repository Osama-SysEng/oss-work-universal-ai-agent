"""osv_rea — offline tests: the REA/Craft evidence discipline.

Origin: 8 Nov 2026, the two reference methodologies (github.com/morluto/rea,
github.com/storytold/craft-anything) folded into the agent as real tools.
Every test here enforces an honesty property: observations are extracted from
bytes, unknowns are recorded instead of invented, and the craft check returns
a MEASURED ratio — never an impression.
"""

import json
import sqlite3
import struct
import zipfile

import osv_agent as ag
import osv_rea as rea

FAKE_HTML = """<html lang="ar"><head>
<meta name="description" content="مطعم الذواق">
<title>مطعم الذواق — نظام الطلبات</title>
<style>body{color:red}</style>
<script>console.log("secret")</script>
</head><body>
<h1>قائمة الطعام</h1>
<h2>المشويات</h2>
<p>شيش طاووج طازج مع رز.</p>
<a href="/order">اطلب الآن</a>
<img src="food.png" alt="">
<input type="email">
<button>أرسل</button>
</body></html>"""


def _feed(url, body, status=200):
    return lambda u, timeout=20: (status, body)


# --- clean-room study -------------------------------------------------------

def test_study_extracts_what_visitor_sees_and_records(tmp_path, monkeypatch):
    monkeypatch.setattr(rea, "_fetch", _feed("u", FAKE_HTML))
    ctx = ag.AgentContext(tmp_path, "t")
    ok, msg = rea.tool_rea_study(ctx, "https://example.com/restaurant")
    assert ok
    assert "مطعم الذواق" in msg and "قائمة الطعام" in msg
    saved = json.loads(
        (tmp_path / "evidence" / "latest-study.json").read_text("utf-8"))
    assert saved["title"] == "مطعم الذواق — نظام الطلبات"
    assert ("h1", "قائمة الطعام") in [tuple(x) for x in saved["headings"]]
    # clean-room properties: script content never leaks into visible text
    assert "secret" not in saved["visible_text"]
    assert saved["words"] > 0


def test_study_honest_failure_on_bad_status_and_bad_url(tmp_path, monkeypatch):
    ctx = ag.AgentContext(tmp_path, "t")
    ok, msg = rea.tool_rea_study(ctx, "ftp://bad")
    assert not ok and "http" in msg
    monkeypatch.setattr(rea, "_fetch", _feed("u", "x", status=404))
    ok, msg = rea.tool_rea_study(ctx, "https://example.com")
    assert not ok and "404" in msg


# --- artifact inspection ----------------------------------------------------

def test_inspect_routes_zip_sqlite_gguf(tmp_path):
    ctx = ag.AgentContext(tmp_path, "t")
    zpath = tmp_path / "app.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("main.py", "print(1)\n")
        z.writestr("AndroidManifest.xml", "<xml/>")
    ok, msg = rea.tool_rea_inspect(ctx, "app.zip")
    assert ok and "zip" in msg and "AndroidManifest" in msg

    dpath = tmp_path / "data.db"
    con = sqlite3.connect(str(dpath))
    con.execute("CREATE TABLE items (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    ok, msg = rea.tool_rea_inspect(ctx, "data.db")
    assert ok and "sqlite" in msg and "items" in msg

    gpath = tmp_path / "model.gguf"
    gpath.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 7, 1) + b"\0" * 8)
    ok, msg = rea.tool_rea_inspect(ctx, "model.gguf")
    assert ok and "تنسورات=7" in msg


def test_inspect_honest_about_no_native_decompiler(tmp_path):
    ctx = ag.AgentContext(tmp_path, "t")
    p = tmp_path / "prog.exe"
    p.write_bytes(b"MZ" + b"\0" * 30)
    ok, msg = rea.tool_rea_inspect(ctx, "prog.exe")
    assert ok and "غير متاح" in msg


def test_inspect_rejects_escape_paths(tmp_path):
    ctx = ag.AgentContext(tmp_path, "t")
    ok, _msg = rea.tool_rea_inspect(ctx, r"..\\outside.txt")
    assert not ok


# --- https infrastructure (the silent-dead web-tools fix) --------------------

def test_https_has_a_real_ca_bundle_certifi_was_dead_silently():
    """This machine's python lacked the OpenSSL default cafile, so every
    https fetch (agent web tools included) died CERTIFICATE_VERIFY_FAILED —
    silently, because callers swallowed the exception. The fix loads
    certifi's bundle into every context; a broken bundle must fail this."""
    from oss_work_live import _ssl_context
    stats = dict(_ssl_context().cert_store_stats())
    assert stats.get("x509_ca", 0) > 0


def test_fetch_survives_a_gateway_import_failure(tmp_path, monkeypatch):
    """_fetch must fall back to the default SSL context when oss_work_live
    cannot import (standalone use), instead of crashing on the fetch itself."""

    import builtins

    def fake_import(name, *args, **kw):
        if name == "oss_work_live":
            raise ImportError("simulated gateway outage")
        return real_import(name, *args, **kw)

    real_import = builtins.__import__
    real_import = builtins.__import__
    monkeypatch.setattr(builtins, "__import__", fake_import)

    # non-network path: url still validated first, fetch path exercised via
    # the fallback branch on a data-less target is impossible offline —
    # so we assert only that the fallback line executes without raising by
    # calling _fetch against an unroutable local URL and expecting URLError,
    # not ImportError.
    import urllib.error
    try:
        rea._fetch("https://127.0.0.1:1/health", timeout=2)
    except ImportError:
        raise AssertionError("_fetch leaked ImportError from the fallback")
    except (urllib.error.URLError, OSError):
        pass  # the honest expected failure
    else:  # pragma: no cover — nothing listens there
        pass


# --- evidence ledger --------------------------------------------------------

def test_evidence_records_unknown_and_views_ledger(tmp_path):
    ctx = ag.AgentContext(tmp_path, "t")
    ok, msg = rea.tool_rea_evidence(ctx, "unknown", "كيف يعمل زر الدفع؟")
    assert ok and "سُجّل" in msg
    ok, msg = rea.tool_rea_evidence(ctx, "view")
    assert ok and "كيف يعمل زر الدفع" in msg
    ok, msg = rea.tool_rea_evidence(ctx, "unknown", "")
    assert not ok  # an unknown without text is noise — refuse


# --- the craft check (measured, not impressionistic) -------------------------

def test_check_refuses_without_study_or_build(tmp_path):
    ctx = ag.AgentContext(tmp_path, "t")
    ok, msg = rea.tool_rea_check(ctx)
    assert not ok and "rea_study" in msg
    (tmp_path / "built.html").write_text("<html>hi</html>", "utf-8")
    ok, msg = rea.tool_rea_check(ctx)
    assert not ok and "rea_study" in  msg


def test_check_measures_gap_and_hits_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(rea, "_fetch", _feed("u", FAKE_HTML))
    ctx = ag.AgentContext(tmp_path, "t")
    ok, _ = rea.tool_rea_study(ctx, "https://example.com/restaurant")

    far = (tmp_path / "index.html")
    far.write_text("<html><body>title book store unrelated stuff</body></html>",
                   "utf-8")
    ok, msg = rea.tool_rea_check(ctx)
    assert ok and "بعيد" in msg
    assert "عنوان غائب" in msg or "غير ظاهر" in msg

    near = (tmp_path / "index.html")
    near.write_text(FAKE_HTML.replace("<script>console.log(\"secret\")"
                                      "</script>", ""), "utf-8")
    ok, msg = rea.tool_rea_check(ctx)
    assert ok and "قريب" in msg

    ledger = json.loads(
        (tmp_path / "evidence" / "ledger.json").read_text("utf-8"))
    kinds = [r["t"] for r in ledger]
    assert "study" in kinds and "craft-check" in kinds
    craft = [r for r in ledger if r["t"] == "craft-check"][-1]
    assert craft["inferred"]  # the verdict itself is an inference — labeled


def test_check_with_same_html_scores_high(tmp_path, monkeypatch):
    monkeypatch.setattr(rea, "_fetch", _feed("u", FAKE_HTML))
    ctx = ag.AgentContext(tmp_path, "t")
    rea.tool_rea_study(ctx, "https://example.com/restaurant")
    (tmp_path / "index.html").write_text(FAKE_HTML, "utf-8")
    ok, msg = rea.tool_rea_check(ctx)
    assert ok and "1.0" in msg and "قريب" in msg
