from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MemoryNode:
    node_id: str
    content: str
    tags: list[str]
    node_type: str
    memory_type: str
    source: str | None
    scope_id: str
    trace_id: str | None
    embedding: list[float] | None
    impact_score: float
    usage_count: int
    success_rate: float | None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass(frozen=True, slots=True)
class MemoryLink:
    source_node_id: str
    target_node_id: str
    relationship_type: str
    weight: float
    created_at: datetime = field(default_factory=utcnow)


@dataclass(slots=True)
class MemoryTrace:
    trace_id: str
    node_ids: list[str]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RecallRequest:
    query: str
    scope_id: str
    strategy_names: list[str]
    limit: int
    token_budget: int
    required_tags: list[str] = field(default_factory=list)
    memory_types: list[str] = field(default_factory=list)
    trace_id: str | None = None
    operation_type: str | None = None


@dataclass(frozen=True, slots=True)
class RecallResult:
    nodes: list[MemoryNode]
    scores: dict[str, float]
    score_breakdowns: dict[str, dict[str, float]]
    truncated: bool


@dataclass(frozen=True, slots=True)
class MemoryContext:
    items: list[MemoryNode]
    node_ids: list[str]
    used_tokens: int
    token_budget: int
    truncated: bool
