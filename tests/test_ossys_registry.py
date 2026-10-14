"""OS registry: 300 task agents over ~30 archetypes (data, not files)."""

from ossys import archetypes, task_registry


def test_thirty_archetypes():
    archs = archetypes.all_archetypes()
    assert len(archs) == 30
    assert len({a.id for a in archs}) == 30


def test_three_hundred_tasks():
    tasks = task_registry.all_tasks()
    assert len(tasks) == 300
    ids = [t.id for t in tasks]
    assert ids == [f"T{i:03d}" for i in range(1, 301)]


def test_ten_tasks_per_archetype():
    for arch in archetypes.all_archetypes():
        assert len(task_registry.by_archetype(arch.id)) == 10
        assert all(t.background_ok == arch.background_ok for t in task_registry.by_archetype(arch.id))


def test_get_and_search():
    task = task_registry.get_task("t001")
    assert task is not None and task.id == "T001"
    assert task_registry.get_task("T999") is None
    hits = task_registry.search("spreadsheet")
    assert hits and all("spreadsheet" in (h.title + h.brief).lower() for h in hits)
    assert task_registry.search("") == []


def test_executors_are_known():
    known = {
        "orchestrator",
        "file",
        "code",
        "security",
        "memory",
        "learning",
        "reader",
        "office",
        "hosting",
        "scheduler",
        "skills",
        "engine",
    }
    kinds = set(archetypes.executors().values())
    assert kinds <= known
    assert archetypes.get_archetype("nope") is None
