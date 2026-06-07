from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SqlStoreConfig:
    database_url: str
    echo: bool = False


@dataclass(frozen=True, slots=True)
class RunRecord:
    run_id: str
    run_type: str
    status: str
    state_payload: Any | None
    trace_id: str | None
    correlation_id: str | None
    owner_id: str | None
    scope: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    event_type: str
    payload: Any | None
    source: str | None
    run_id: str | None
    trace_id: str | None
    correlation_id: str | None
    parent_event_id: str | None
    sequence_index: int | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class JobRecord:
    job_id: str
    task_name: str
    status: str
    payload: Any | None
    owner_id: str | None
    trace_id: str | None
    correlation_id: str | None
    attempt_count: int
    max_attempts: int
    scheduled_for: datetime | None
    claimed_by: str | None
    claimed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
