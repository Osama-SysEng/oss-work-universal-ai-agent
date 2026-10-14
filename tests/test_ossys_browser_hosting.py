"""Browser reader + local hosting: real loopback round-trip, no mocks."""

import pytest

from ossys import browser, hosting

PAGE = (
    "<html><head><title>Demo Page</title></head>"
    "<body><h1>Hello</h1><script>var x = 1;</script>"
    "<p>Local content here.</p>"
    "<a href='https://example.com/x'>link</a></body></html>"
)


def test_extract_pure():
    page = browser.extract(PAGE)
    assert page["title"] == "Demo Page"
    assert "Local content here." in page["text"]
    assert "var x" not in page["text"]
    assert page["links"] == ["https://example.com/x"]


def test_unsupported_is_honest():
    with pytest.raises(browser.BrowserUnsupported):
        browser.screenshot("https://example.com")
    with pytest.raises(browser.BrowserUnsupported):
        browser.fill_form("https://example.com", {"q": "x"})
    with pytest.raises(browser.BrowserUnsupported):
        browser.run_javascript("alert(1)")
    with pytest.raises(browser.BrowserError, match="http/https"):
        browser.fetch("ftp://example.com/x")


def test_host_and_fetch(tmp_path):
    (tmp_path / "index.html").write_text(PAGE, encoding="utf-8")
    manager = hosting.HostManager()
    manager.register("demo", str(tmp_path))
    url = manager.serve("demo")
    try:
        assert url.startswith("http://127.0.0.1:")
        page = browser.fetch(url)
        assert page["title"] == "Demo Page"
        assert "Local content here." in page["text"]
        assert manager.list()[0]["running"] is True
    finally:
        manager.stop_all()
    assert manager.list()[0]["running"] is False


def test_host_errors(tmp_path):
    manager = hosting.HostManager()
    with pytest.raises(hosting.HostingError, match="missing"):
        hosting.HostedApp("x", str(tmp_path / "nope"), 0).start()
    with pytest.raises(hosting.HostingError, match="Unknown app"):
        manager.serve("ghost")
