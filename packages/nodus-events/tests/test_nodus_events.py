from __future__ import annotations

from datetime import datetime, timezone

from nodus_events import BufferPolicy, EventBus, EventEnvelope


def make_event(event_id: str, source: str = "node-a") -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id,
        event_type="job.done",
        timestamp=datetime.now(timezone.utc),
        source_instance_id=source,
        correlation_id=None,
        trace_id=None,
        payload={"ok": True},
        metadata={},
    )


def test_local_publish_to_subscriber() -> None:
    seen: list[str] = []
    bus = EventBus(source_instance_id="node-a")
    bus.subscribe("job.done", lambda event: seen.append(event.event_id))
    result = bus.publish(make_event("e1"))
    assert result.accepted is True
    assert seen == ["e1"]


def test_pause_buffers_and_drain_replays_in_order() -> None:
    seen: list[str] = []
    bus = EventBus(
        source_instance_id="node-a",
        buffer_policy=BufferPolicy(mode="bounded_drop_new", max_events=5),
    )
    bus.subscribe("job.done", lambda event: seen.append(event.event_id))
    bus.pause_delivery()
    bus.publish(make_event("e1"))
    bus.publish(make_event("e2"))
    assert seen == []
    bus.resume_delivery()
    assert bus.drain_buffer() == 2
    assert seen == ["e1", "e2"]


def test_drop_new_policy_rejects_when_full() -> None:
    bus = EventBus(
        source_instance_id="node-a",
        buffer_policy=BufferPolicy(mode="bounded_drop_new", max_events=1),
    )
    bus.pause_delivery()
    first = bus.publish(make_event("e1"))
    second = bus.publish(make_event("e2"))
    assert first.accepted is True
    assert second.accepted is False


def test_drop_oldest_policy_keeps_latest() -> None:
    seen: list[str] = []
    bus = EventBus(
        source_instance_id="node-a",
        buffer_policy=BufferPolicy(mode="bounded_drop_oldest", max_events=1),
    )
    bus.subscribe("job.done", lambda event: seen.append(event.event_id))
    bus.pause_delivery()
    bus.publish(make_event("e1"))
    bus.publish(make_event("e2"))
    bus.resume_delivery()
    bus.drain_buffer()
    assert seen == ["e2"]


def test_handle_backend_envelope_deduplicates_same_source() -> None:
    seen: list[str] = []
    bus = EventBus(source_instance_id="node-a")
    bus.subscribe("job.done", lambda event: seen.append(event.event_id))
    assert bus.handle_backend_envelope(make_event("e1", source="node-a")) is False
    assert bus.handle_backend_envelope(make_event("e2", source="node-b")) is True
    assert seen == ["e2"]
