from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_id: str
    event_type: str
    timestamp: datetime
    source_instance_id: str
    correlation_id: str | None
    trace_id: str | None
    payload: Any
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    accepted: bool
    delivery_mode: str
    buffered: bool
    audit_recorded: bool
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class BufferPolicy:
    mode: str
    max_events: int


@dataclass(frozen=True, slots=True)
class Subscription:
    subscription_id: str
    event_type: str
    handler_name: str
