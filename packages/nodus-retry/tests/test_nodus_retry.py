from __future__ import annotations

import random

import pytest

from nodus_retry import (
    AsyncRetryExecutor,
    BackoffStrategy,
    ExecutionGuarantee,
    IdempotencyConflictError,
    IdempotencyKey,
    InMemoryIdempotencyStore,
    RetryExhaustedError,
    RetryExecutor,
    RetryPolicy,
    compute_backoff_delay,
)


def test_fixed_backoff() -> None:
    delay = compute_backoff_delay(BackoffStrategy("fixed", 2.0), attempt_number=3)
    assert delay == 2.0


def test_bounded_exponential_backoff() -> None:
    delay = compute_backoff_delay(
        BackoffStrategy("bounded_exponential", 1.0, max_delay_seconds=3.0),
        attempt_number=4,
    )
    assert delay == 3.0


def test_jittered_backoff_is_bounded() -> None:
    delay = compute_backoff_delay(
        BackoffStrategy("jittered_exponential", 2.0, jitter_ratio=0.25),
        attempt_number=2,
        rng=random.Random(7),
    )
    assert 3.0 <= delay <= 5.0


def test_retry_executor_succeeds_after_retry() -> None:
    attempts = {"count": 0}
    executor = RetryExecutor()
    policy = RetryPolicy(
        max_attempts=2,
        backoff=BackoffStrategy("fixed", 0.0),
        retryable_exceptions=(ValueError,),
    )

    def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("retry")
        return "ok"

    assert executor.execute(
        operation_name="op",
        policy=policy,
        guarantee=ExecutionGuarantee.BEST_EFFORT,
        fn=flaky,
    ) == "ok"
    assert attempts["count"] == 2


def test_high_risk_no_retry() -> None:
    executor = RetryExecutor()
    policy = RetryPolicy(
        max_attempts=5,
        backoff=BackoffStrategy("fixed", 0.0),
        high_risk_no_retry=True,
        retryable_exceptions=(ValueError,),
    )
    with pytest.raises(RetryExhaustedError):
        executor.execute(
            operation_name="danger",
            policy=policy,
            guarantee=ExecutionGuarantee.BEST_EFFORT,
            fn=lambda: (_ for _ in ()).throw(ValueError("boom")),
        )


def test_idempotent_replay_returns_cached_result() -> None:
    store = InMemoryIdempotencyStore()
    executor = RetryExecutor()
    key = IdempotencyKey(action_id="a1", operation_name="op")
    policy = RetryPolicy(max_attempts=1, backoff=BackoffStrategy("fixed", 0.0))
    first = executor.execute(
        operation_name="op",
        policy=policy,
        guarantee=ExecutionGuarantee.IDEMPOTENT_REPLAY,
        idempotency_key=key,
        store=store,
        fn=lambda: {"ok": True},
    )
    second = executor.execute(
        operation_name="op",
        policy=policy,
        guarantee=ExecutionGuarantee.IDEMPOTENT_REPLAY,
        idempotency_key=key,
        store=store,
        fn=lambda: {"ok": False},
    )
    assert first == {"ok": True}
    assert second == {"ok": True}


def test_pending_duplicate_claim_conflicts() -> None:
    store = InMemoryIdempotencyStore()
    key = IdempotencyKey(action_id="a2", operation_name="op")
    store.begin(__import__("nodus_retry").EffectRecord.pending(key))
    with pytest.raises(IdempotencyConflictError):
        store.begin(__import__("nodus_retry").EffectRecord.pending(key))


@pytest.mark.asyncio
async def test_async_retry_executor() -> None:
    attempts = {"count": 0}
    executor = AsyncRetryExecutor()
    policy = RetryPolicy(
        max_attempts=2,
        backoff=BackoffStrategy("fixed", 0.0),
        retryable_exceptions=(ValueError,),
    )

    async def flaky() -> str:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise ValueError("retry")
        return "ok"

    assert await executor.aexecute(
        operation_name="op",
        policy=policy,
        guarantee=ExecutionGuarantee.BEST_EFFORT,
        fn=flaky,
    ) == "ok"
