"""oss-os CLI surface: office + apps commands (isolated env)."""

import json

import pytest

from ossys import boot


@pytest.fixture()
def isolated(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OSS_OS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OSS_OS_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("OSS_OS_WORKSPACE_DIR", str(tmp_path / "ws"))
    return tmp_path, capsys


def test_office_write_read(isolated, capsys):
    boot.main(["office", "write", "hello.md", "--text", "# hi"])
    out = json.loads(capsys.readouterr().out)
    assert out["chars"] == 4
    boot.main(["office", "read", "hello.md"])
    assert capsys.readouterr().out.strip() == "# hi"


def test_office_sheet_and_deck(isolated, capsys):
    boot.main(["office", "sheet-write", "s.csv", "--text", "a,b\n1,2\n3,4\n"])
    assert json.loads(capsys.readouterr().out)["rows"] == 2
    boot.main(["office", "sheet-sum", "s.csv"])
    assert json.loads(capsys.readouterr().out)["sums"] == {"a": 4.0, "b": 6.0}
    boot.main(["office", "deck", "d.html", "--title", "T", "--text", "one\n---\ntwo"])
    assert json.loads(capsys.readouterr().out)["slides"] == 2


def test_apps_register_serve_stop(isolated, tmp_path, capsys):
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    boot.main(["apps", "register", "--name", "demo", "--directory", str(tmp_path / "site")])
    assert json.loads(capsys.readouterr().out)["name"] == "demo"
    try:
        boot.main(["apps", "serve", "--name", "demo"])
        url = json.loads(capsys.readouterr().out)["url"]
        assert url.startswith("http://127.0.0.1:")
        boot.main(["apps"])
        assert json.loads(capsys.readouterr().out)[0]["running"] is True
    finally:
        boot.main(["apps", "stop", "--name", "demo"])
        assert json.loads(capsys.readouterr().out)["running"] is False


def test_tasks_search(isolated, capsys):
    boot.main(["tasks", "--search", "spreadsheet"])
    rows = json.loads(capsys.readouterr().out)
    assert rows and all("spreadsheet" in (r["title"]).lower() for r in rows)
