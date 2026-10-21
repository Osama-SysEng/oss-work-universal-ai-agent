"""Provenance: what is used, and under which licence."""

from __future__ import annotations

from pathlib import Path

from osv1.provenance import ProvenanceRegistry, file_digest, needs_review


def test_permissive_licences_do_not_need_a_review() -> None:
    assert needs_review("MIT") is False
    assert needs_review("Apache-2.0") is False
    assert needs_review("BSD-3-Clause") is False


def test_other_licences_need_a_legal_review() -> None:
    assert needs_review("GPL-3.0") is True
    assert needs_review("AGPL") is True
    assert needs_review("CC-BY-NC") is True
    assert needs_review("unknown") is True
    assert needs_review("") is True


def test_the_built_in_records_are_written_on_first_use(tmp_path: Path) -> None:
    registry = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    assert registry.records
    names = {record.name for record in registry.records}
    assert any("REA" in name for name in names)
    assert (tmp_path / "provenance.json").is_file()


def test_the_review_flag_is_derived_from_the_licence(tmp_path: Path) -> None:
    registry = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    # The user-provided model has an unknown licence, so it needs a review.
    model = registry.get("local model (user provided)")
    assert model is not None
    assert model.needs_legal_review is True
    assert "local model (user provided)" in [record.name for record in registry.review_queue()]

    # A permissive licence does not.
    rea = registry.get("REA (morluto/rea)")
    assert rea is not None
    assert rea.needs_legal_review is False


def test_a_record_is_added_and_read_back(tmp_path: Path) -> None:
    registry = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    record = registry.add("model", "my model", "C:/models/mine.gguf", license="unknown", version="1.0")
    assert record.needs_legal_review is True
    reloaded = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    assert reloaded.get("my model") is not None
    assert reloaded.get("my model").version == "1.0"


def test_the_report_lists_the_review_queue(tmp_path: Path) -> None:
    registry = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    registry.add("dataset", "customer notes", "C:/data/notes", license="proprietary")
    report = registry.report()
    assert report["total"] >= 1
    assert "customer notes" in report["needs_legal_review"]
    assert report["by_kind"]


def test_a_record_can_be_removed(tmp_path: Path) -> None:
    registry = ProvenanceRegistry(path=tmp_path / "provenance.json").load()
    registry.add("skill", "csv tool", "generated", license="MIT")
    assert registry.remove("csv tool") is True
    assert registry.get("csv tool") is None


def test_the_digest_of_a_file_is_recorded(tmp_path: Path) -> None:
    target = tmp_path / "a.bin"
    target.write_bytes(b"oss-work")
    digest = file_digest(target)
    assert len(digest) == 64
    assert file_digest(tmp_path / "missing.bin") == ""
