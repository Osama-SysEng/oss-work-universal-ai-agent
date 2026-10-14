"""Office suite: native formats round-trip; limits refused honestly."""

import pytest

from ossys.office import documents


@pytest.fixture()
def ws(tmp_path, monkeypatch):
    monkeypatch.setenv("OSS_OS_WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def test_text_roundtrip(ws):
    assert documents.write_text("notes/hello.md", "# hi")["chars"] == 4
    assert documents.read_text("notes/hello.md") == "# hi"
    documents.append_note("notes/hello.md", "second line")
    assert "second line" in documents.read_text("notes/hello.md")


def test_rejects_bad_extension(ws):
    with pytest.raises(documents.OfficeError, match=".txt/.md"):
        documents.write_text("x.pdf", "data")


def test_sheet_roundtrip_and_summary(ws):
    rows = [{"item": "a", "qty": "2"}, {"item": "b", "qty": "3"}]
    assert documents.write_sheet("s.csv", rows)["rows"] == 2
    assert documents.read_sheet("s.csv") == rows
    summary = documents.summarize_sheet("s.csv")
    assert summary.rows == 2 and summary.numeric_sums == {"qty": 5.0}
    documents.append_sheet_row("s.csv", {"item": "c", "qty": "4"})
    assert documents.summarize_sheet("s.csv").numeric_sums == {"qty": 9.0}


def test_deck_build(ws):
    out = documents.build_deck("Demo", ["first point", "second point"])
    assert out["slides"] == 2
    content = documents.read_text("deck.html")
    assert "Demo" in content and "first point" in content


def test_workspace_escape_refused(ws):
    with pytest.raises(documents.OfficeError, match="escapes workspace"):
        documents.write_text("../evil.txt", "x")


def test_docx_honest(ws):
    try:
        import docx  # noqa: F401
    except ImportError:
        with pytest.raises(documents.OfficeError, match="python-docx"):
            documents.read_docx("x.docx")
    else:
        with pytest.raises(documents.OfficeError, match="Not found"):
            documents.read_docx("missing.docx")
