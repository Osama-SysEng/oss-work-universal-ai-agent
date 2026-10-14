"""Own local browser: read-only web reader. Honest limits stated up front:

- DOES: fetch http/https (httpx), extract title/text/links (stdlib html.parser).
- DOES NOT: run JavaScript, fill forms, take screenshots, log in anywhere.
  Those raise BrowserUnsupported with the reason — never simulated.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Any


class BrowserError(RuntimeError):
    pass


class BrowserUnsupported(BrowserError):
    pass


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._in_title = False
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.links.append(value[:500])

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def extract(html_text: str) -> dict[str, Any]:
    """Pure extraction (no network). Used by fetch() and tests."""
    parser = _Extractor()
    parser.feed(html_text)
    body = "\n".join(parser.text_parts)
    # Collapse blank runs.
    lines = [ln.strip() for ln in body.splitlines()]
    clean = "\n".join(ln for ln in lines if ln)
    return {
        "title": " ".join(parser.title_parts)[:300],
        "text": clean[:20000],
        "links": parser.links[:200],
    }


def fetch(url: str, timeout: float = 20.0) -> dict[str, Any]:
    """Fetch a page and extract readable content. http/https only."""
    import httpx

    if not url.lower().startswith(("http://", "https://")):
        raise BrowserError(f"Only http/https URLs are supported, got: {url!r}")
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "oss-work-OS/1.0 (local reader)"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if "html" not in content_type and "<html" not in response.text[:2000].lower():
                return {
                    "url": url,
                    "title": "",
                    "text": response.text[:20000],
                    "links": [],
                    "note": f"Non-HTML content ({content_type}).",
                }
            page = extract(response.text)
            page["url"] = url
            return page
    except BrowserError:
        raise
    except Exception as exc:
        raise BrowserError(f"Fetch failed for {url!r}: {exc}") from exc


def screenshot(_url: str) -> str:
    raise BrowserUnsupported("Screenshots need a scripted browser; the OS reader is read-only.")


def fill_form(_url: str, _fields: dict) -> str:
    raise BrowserUnsupported("Form filling is not supported by the local read-only browser.")


def run_javascript(_code: str) -> str:
    raise BrowserUnsupported("JavaScript execution is disabled in the local browser.")
