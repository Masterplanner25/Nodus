from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from nodus_store_sql import (
    EventRecord,
    JobRecord,
    OptimisticLockError,
    RunRecord,
    SqlStore,
    SqlStoreConfig,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def build_store() -> SqlStore:
    store = SqlStore(SqlStoreConfig(database_url="sqlite:///:memory:"))
    store.create_all()
    return store


def test_run_round_trip_and_update() -> None:
    store = build_store()
    created = RunRecord("r1", "flow", "pending", {"x": 1}, "t1", "c1", "u1", "tenant", 1, utcnow(), utcnow())
    store.runs.create(created)
    loaded = store.runs.get("r1")
    assert loaded is not None
    assert loaded.state_payload == {"x": 1}
    updated = store.runs.update(replace(loaded, status="running"))
    assert updated.status == "running"
    assert updated.version == 2


def test_stale_run_update_raises() -> None:
    store = build_store()
    created = RunRecord("r2", "flow", "pending", None, None, None, None, None, 1, utcnow(), utcnow())
    store.runs.create(created)
    current = store.runs.get("r2")
    assert current is not None
    store.runs.update(replace(current, status="running"))
    with pytest.raises(OptimisticLockError):
        store.runs.update(replace(current, status="completed"))


def test_event_append_and_list_order() -> None:
    store = build_store()
    e1 = EventRecord("e1", "step.started", {"a": 1}, "flow", "r1", "t1", "c1", None, 1, utcnow())
    e2 = EventRecord("e2", "step.done", {"a": 2}, "flow", "r1", "t1", "c1", "e1", 2, utcnow())
    store.events.append(e1)
    store.events.append(e2)
    by_run = store.events.list_for_run("r1")
    by_trace = store.events.list_for_trace("t1")
    assert [event.event_id for event in by_run] == ["e1", "e2"]
    assert [event.event_id for event in by_trace] == ["e1", "e2"]


def test_job_claim_pending_succeeds_once() -> None:
    store = build_store()
    pending = JobRecord(
        "j1",
        "task.run",
        "pending",
        {"x": 1},
        None,
        "t1",
        "c1",
        0,
        3,
        None,
        None,
        None,
        None,
        utcnow(),
        utcnow(),
    )
    store.jobs.create(pending)
    first = store.jobs.claim_pending("j1", "worker-a")
    second = store.jobs.claim_pending("j1", "worker-b")
    assert first is not None
    assert first.status == "claimed"
    assert first.claimed_by == "worker-a"
    assert second is None


def test_job_payload_round_trip() -> None:
    store = build_store()
    job = JobRecord(
        "j2",
        "task.run",
        "pending",
        {"nested": {"ok": True}},
        "u1",
        "t2",
        "c2",
        1,
        5,
        utcnow(),
        None,
        None,
        None,
        utcnow(),
        utcnow(),
    )
    store.jobs.create(job)
    loaded = store.jobs.get("j2")
    assert loaded is not None
    assert loaded.payload == {"nested": {"ok": True}}


def test_store_session_context_commits() -> None:
    store = build_store()
    with store.session() as session:
        session.add(
            __import__("nodus_store_sql.orm").orm.RunModel(
                run_id="r3",
                run_type="flow",
                status="pending",
                state_payload=None,
                trace_id=None,
                correlation_id=None,
                owner_id=None,
                scope=None,
                version=1,
                created_at=utcnow(),
                updated_at=utcnow(),
                completed_at=None,
            )
        )
    assert store.runs.get("r3") is not None
