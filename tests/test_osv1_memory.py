"""Memory: the four types, retrieval, versioning, rollback, and user control."""

from __future__ import annotations

from pathlib import Path

from osv1.memory.store import MemoryStore


def _store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(path=tmp_path / "memory.db")


def test_the_four_types_stay_separate(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_fact("the export is a CSV file")
    store.add_experience("removing duplicates changed the row count", lesson="count before and after")
    store.add_skill(
        "clean-export", "drop duplicate rows, then report the count", conditions="csv export", tests="row count"
    )
    store.add_assumption("the weekly report runs on friday", basis="one conversation", confidence=0.4)

    counts = store.stats()["counts"]
    assert counts == {"fact": 1, "experience": 1, "skill": 1, "assumption": 1}
    assert store.list(kind="fact")[0].content == "the export is a CSV file"
    assert store.list(kind="assumption")[0].confidence == 0.4


def test_an_assumption_can_be_confirmed_or_revoked(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = store.add_assumption("the report runs on friday", basis="a guess")
    confirmed = store.confirm_assumption(entry.id, as_fact=True)
    assert confirmed is not None
    assert confirmed.kind == "fact"
    assert confirmed.confidence == 1.0

    other = store.add_assumption("another guess", basis="a guess")
    revoked = store.revoke_assumption(other.id)
    assert revoked is not None
    assert revoked.status == "revoked"
    assert all(item.id != other.id for item in store.list(status="active"))


def test_retrieval_finds_the_relevant_entries(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_fact("the sales export is a CSV file")
    store.add_fact("the office coffee machine is on the third floor")
    results = store.retrieve("csv export", limit=2)
    assert results
    assert "csv" in results[0][0].content.lower()
    assert results[0][1] > 0


def test_a_correction_bumps_the_version(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = store.add_fact("the report runs on friday")
    updated = store.update(entry.id, content="the report runs on sunday")
    assert updated is not None
    assert updated.version == 2
    assert updated.content == "the report runs on sunday"


def test_skill_usage_is_counted(tmp_path: Path) -> None:
    store = _store(tmp_path)
    skill = store.add_skill("clean-export", "drop duplicates")
    store.record_skill_use(skill.id, success=True)
    store.record_skill_use(skill.id, success=False)
    updated = store.get(skill.id)
    assert updated is not None
    assert updated.metadata["uses"] == 2
    assert updated.metadata["successes"] == 1
    assert updated.metadata["failures"] == 1


def test_a_snapshot_can_be_restored(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_fact("first fact")
    version = store.snapshot("before the change")
    store.add_fact("second fact")
    assert len(store.list(status="active")) == 2

    restored = store.rollback(version)
    assert restored == 1
    assert len(store.list(status="active")) == 1
    assert store.list(status="active")[0].content == "first fact"


def test_the_user_can_export_and_delete(tmp_path: Path) -> None:
    store = _store(tmp_path)
    entry = store.add_fact("something worth keeping")
    export = store.export()
    assert export["count"] == 1
    assert export["entries"][0]["content"] == "something worth keeping"
    assert store.delete(entry.id) is True
    assert store.list(status="active") == []


def test_memory_is_namespaced_per_user(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.add_fact("local note", user_id="local")
    store.add_fact("other note", user_id="someone-else")
    assert len(store.list(user_id="local", status="active")) == 1
    assert store.list(user_id="local", status="active")[0].content == "local note"
