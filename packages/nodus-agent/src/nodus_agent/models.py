from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class AgentFrameworkConfig:
    max_delegation_depth: int = 3


@dataclass(frozen=True, slots=True)
class AgentPlanStep:
    tool_name: str
    args: dict[str, object]
    risk_level: str
    description: str


@dataclass(frozen=True, slots=True)
class AgentPlan:
    executive_summary: str
    steps: list[AgentPlanStep]
    overall_risk: str
    planner_name: str | None = None
    planner_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class AgentRun:
    run_id: str
    objective: str
    user_id: str
    status: str
    plan: AgentPlan
    capability_token: dict[str, object] | None
    trace_id: str | None
    correlation_id: str | None
    parent_run_id: str | None
    delegated_to: str | None
    steps_completed: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, object] | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AgentEvent:
    event_id: str
    run_id: str
    event_type: str
    payload: dict[str, object]
    created_at: datetime
