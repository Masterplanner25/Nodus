from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class EventCause:
    parent_event_id: str | None
    parent_run_id: str | None
    parent_step_id: str | None
    relationship_type: str


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    payload: Any
    timestamp: datetime
    source_instance_id: str
    trace_id: str | None
    correlation_id: str | None
    cause_chain: list[EventCause] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
    do_not_replay: bool = False


@dataclass(frozen=True, slots=True)
class EventRoute:
    route_id: str
    event_pattern: str
    target_kind: str
    delivery_mode: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WebhookSubscription:
    subscription_id: str
    event_pattern: str
    target_url: str
    secret: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True


@dataclass(slots=True)
class EventAuditRecord:
    event_id: str
    envelope: EventEnvelope
    published_at: datetime
    handler_outcomes: list[dict[str, object]] = field(default_factory=list)
    webhook_outcomes: list[dict[str, object]] = field(default_factory=list)
    distributed_outcome: dict[str, object] | None = None
    replay_count: int = 0
    completed: bool = False


@dataclass(frozen=True, slots=True)
class EventReplayRequest:
    event_types: list[str] = field(default_factory=list)
    correlation_id: str | None = None
    trace_id: str | None = None
    replay_mode: str = "full"
    include_do_not_replay: bool = False


@dataclass(frozen=True, slots=True)
class EventReplayResult:
    events_replayed: int
    handler_invocations: int
    webhook_invocations: int
    event_ids: list[str]
