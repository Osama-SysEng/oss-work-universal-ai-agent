from pathlib import Path
from uuid import uuid4

import pytest

from core.services.telemetry import TelemetryBatcher, TelemetryEvent
from core.services.telemetry_store import TelemetryStore


def test_batcher_applies_backpressure():
    organization = uuid4()
    batcher = TelemetryBatcher(max_queue=2, max_batch=1)
    events = [TelemetryEvent.create(organization, source="test", kind="event") for _ in range(3)]
    assert batcher.enqueue(events[0])
    assert batcher.enqueue(events[1])
    assert not batcher.enqueue(events[2])
    assert batcher.dropped == 1
    assert len(batcher.flush()) == 1
    assert len(batcher) == 1


def test_event_contract_rejects_invalid_uuid():
    with pytest.raises(ValueError):
        TelemetryEvent.create("not-a-uuid", source="test", kind="event")


def test_store_ignores_duplicate_event_id(tmp_path: Path):
    organization = uuid4()
    event = TelemetryEvent.create(organization, source="test", kind="event", request_id="req-1")
    store = TelemetryStore(tmp_path / "telemetry.sqlite3")
    assert store.ingest([event]) == 1
    assert store.ingest([event]) == 0
    assert store.count(str(organization)) == 1
