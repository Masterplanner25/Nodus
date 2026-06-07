from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class ExecutionGuarantee(str, Enum):
    BEST_EFFORT = "best_effort"
    AT_LEAST_ONCE = "at_least_once"
    AT_MOST_ONCE = "at_most_once"
    IDEMPOTENT_REPLAY = "idempotent_replay"


@dataclass(frozen=True, slots=True)
class BackoffStrategy:
    kind: str
    base_delay_seconds: float
    max_delay_seconds: float | None = None
    jitter_ratio: float | None = None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int
    backoff: BackoffStrategy
    high_risk_no_retry: bool = False
    retryable_exceptions: tuple[type[BaseException], ...] = ()
    non_retryable_exceptions: tuple[type[BaseException], ...] = ()

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("RetryPolicy.max_attempts must be at least 1.")


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    attempt_number: int
    next_delay_seconds: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    action_id: str
    operation_name: str
    scope: str | None = None


@dataclass(slots=True)
class EffectRecord:
    action_id: str
    operation_name: str
    status: str
    attempt_count: int
    result_payload: Any | None
    error_payload: Any | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    scope: str | None = None
    trace_id: str | None = None
    correlation_id: str | None = None

    @classmethod
    def pending(cls, key: IdempotencyKey) -> "EffectRecord":
        now = datetime.now(timezone.utc)
        return cls(
            action_id=key.action_id,
            operation_name=key.operation_name,
            status="pending",
            attempt_count=0,
            result_payload=None,
            error_payload=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
            scope=key.scope,
        )
