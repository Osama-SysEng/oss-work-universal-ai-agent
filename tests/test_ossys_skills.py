"""Self-built skills: binary answers only (isolated tmp dirs)."""

import pytest

from ossys import skills

ANSWERS = {
    "repeats": "yes",
    "local_only": "yes",
    "files": "no",
    "web": "no",
    "schedule": "no",
    "office": "yes",
    "code": "no",
    "memory": "no",
}


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("OSS_OS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("OSS_OS_SKILLS_DIR", str(tmp_path / "skills"))
    return tmp_path


def test_build_skill(isolated):
    doc = skills.build_skill("Weekly Report", "Draft the weekly report", dict(ANSWERS))
    assert doc.name == "weekly-report"
    assert "office suite" in doc.summary
    text = skills.describe("weekly-report")
    assert "Purpose: Draft the weekly report" in text
    assert [s["name"] for s in skills.list_built()] == ["weekly-report"]


def test_rejects_non_binary(isolated):
    bad = dict(ANSWERS, office="maybe")
    with pytest.raises(ValueError, match="yes/no"):
        skills.build_skill("X", "purpose", bad)


def test_rejects_missing_answer(isolated):
    partial = dict(ANSWERS)
    del partial["office"]
    with pytest.raises(ValueError, match="Missing answer"):
        skills.build_skill("X", "purpose", partial)


def test_rejects_empty_name_or_purpose(isolated):
    with pytest.raises(ValueError):
        skills.build_skill("!!!", "purpose", dict(ANSWERS))
    with pytest.raises(ValueError):
        skills.build_skill("Name", "  ", dict(ANSWERS))


def test_unknown_skill(isolated):
    with pytest.raises(ValueError, match="Unknown skill"):
        skills.describe("nope")
