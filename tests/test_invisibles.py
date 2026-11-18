"""18 Nov live: invisible characters (U+200C..) broke a written server.py
with SyntaxError U+200C. The write boundary now strips them and reports."""

import osv_agent
import osv_text


def test_strip_invisibles_counts_and_cleans():
    dirty = "from http.server import \u200c\u200bHTTPServer"
    clean, removed = osv_text.strip_invisibles(dirty)
    assert removed == 2
    assert clean == "from http.server import HTTPServer"


def test_normal_arabic_untouched():
    text = "مرحباً بكم في OSS Work"
    clean, removed = osv_text.strip_invisibles(text)
    assert clean == text and removed == 0


def test_write_file_sanitizes_on_disk(tmp_path):
    ctx = osv_agent.AgentContext(tmp_path, "t")
    ok, obs = osv_agent.tool_write_file(
        ctx, "srv.py", "print('\u200chello')")
    assert ok
    assert "أُزيلت 1" in obs
    assert "\u200c" not in (tmp_path / "srv.py").read_text(encoding="utf-8")
