from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class A2AFrameworkConfig:
    lease_ttl_seconds: int = 300


@dataclass(frozen=True, slots=True)
class AgentCapability:
    name: str
    version: str
    cost_hint: float
    risk_hint: str
    max_concurrency: int


@dataclass(frozen=True, slots=True)
class AgentHealth:
    status: str
    heartbeat_at: datetime
    error_rate: float
    availability: float


@dataclass(frozen=True, slots=True)
class AgentLoad:
    active_tasks: int
    queue_depth: int
    utilization_score: float
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AgentDescriptor:
    agent_id: str
    agent_kind: str
    endpoint: str | None
    capabilities: list[AgentCapability]
    supported_modes: list[str]
    health: AgentHealth
    load: AgentLoad
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelegationRequest:
    task_id: str
    objective: str
    required_capabilities: list[str]
    preferred_mode: str
    trace_id: str | None
    correlation_id: str | None
    deadline_at: datetime | None
    payload: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DelegationDecision:
    task_id: str
    selected_agent_id: str | None
    routing_mode: str
    decision_reason: str
    fallback_agent_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DelegationLease:
    lease_id: str
    task_id: str
    agent_id: str
    request: DelegationRequest
    status: str
    expires_at: datetime
    claimed_at: datetime | None
    completed_at: datetime | None
    attempt_count: int


@dataclass(frozen=True, slots=True)
class DeadLetterRecord:
    task_id: str
    request: DelegationRequest
    reason: str
    retry_count: int
    last_agent_id: str | None
    created_at: datetime
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecoveryRecord:
    task_id: str
    lease_id: str
    reason: str
    action_taken: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class A2AEvent:
    event_id: str
    event_type: str
    task_id: str
    payload: dict[str, object]
    created_at: datetime


def default_expiry(ttl_seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=ttl_seconds)
