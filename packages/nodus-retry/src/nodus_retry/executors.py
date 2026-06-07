from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .classifier import classify_exception
from .errors import RetryExhaustedError
from .models import EffectRecord, ExecutionGuarantee, IdempotencyKey, RetryPolicy
from .stores import IdempotencyStore

T = TypeVar("T")


class RetryExecutor:
    def execute(
        self,
        *,
        operation_name: str,
        policy: RetryPolicy,
        guarantee: ExecutionGuarantee,
        fn: Callable[[], T],
        idempotency_key: IdempotencyKey | None = None,
        store: IdempotencyStore | None = None,
    ) -> T:
        record = _initialize_effect_record(
            operation_name=operation_name,
            guarantee=guarantee,
            idempotency_key=idempotency_key,
            store=store,
        )
        if record is not None and record.status == "completed":
            return record.result_payload  # type: ignore[return-value]

        attempts = 0
        while True:
            attempts += 1
            if record is not None and store is not None:
                store.increment_attempts(record.action_id)
            try:
                result = fn()
                if record is not None and store is not None:
                    store.mark_completed(record.action_id, result)
                return result
            except Exception as exc:
                if record is not None and store is not None:
                    store.mark_failed(record.action_id, {"error": str(exc)})
                decision = classify_exception(
                    exc,
                    attempt_number=attempts,
                    policy=policy,
                    guarantee=guarantee,
                    operation_name=operation_name,
                )
                if not decision.should_retry:
                    raise RetryExhaustedError(
                        f"{operation_name} failed after {attempts} attempt(s): {decision.reason}"
                    ) from exc
                time.sleep(decision.next_delay_seconds or 0.0)


class AsyncRetryExecutor:
    async def aexecute(
        self,
        *,
        operation_name: str,
        policy: RetryPolicy,
        guarantee: ExecutionGuarantee,
        fn: Callable[[], Awaitable[T]],
        idempotency_key: IdempotencyKey | None = None,
        store: IdempotencyStore | None = None,
    ) -> T:
        record = _initialize_effect_record(
            operation_name=operation_name,
            guarantee=guarantee,
            idempotency_key=idempotency_key,
            store=store,
        )
        if record is not None and record.status == "completed":
            return record.result_payload  # type: ignore[return-value]

        attempts = 0
        while True:
            attempts += 1
            if record is not None and store is not None:
                store.increment_attempts(record.action_id)
            try:
                result = await fn()
                if record is not None and store is not None:
                    store.mark_completed(record.action_id, result)
                return result
            except Exception as exc:
                if record is not None and store is not None:
                    store.mark_failed(record.action_id, {"error": str(exc)})
                decision = classify_exception(
                    exc,
                    attempt_number=attempts,
                    policy=policy,
                    guarantee=guarantee,
                    operation_name=operation_name,
                )
                if not decision.should_retry:
                    raise RetryExhaustedError(
                        f"{operation_name} failed after {attempts} attempt(s): {decision.reason}"
                    ) from exc
                await asyncio.sleep(decision.next_delay_seconds or 0.0)


def _initialize_effect_record(
    *,
    operation_name: str,
    guarantee: ExecutionGuarantee,
    idempotency_key: IdempotencyKey | None,
    store: IdempotencyStore | None,
) -> EffectRecord | None:
    if guarantee != ExecutionGuarantee.IDEMPOTENT_REPLAY:
        return None
    if idempotency_key is None or store is None:
        raise ValueError("IDEMPOTENT_REPLAY requires both an idempotency key and a store.")
    existing = store.lookup(idempotency_key.action_id)
    if existing is not None and existing.status == "completed":
        return existing
    pending = EffectRecord.pending(idempotency_key)
    pending.operation_name = operation_name
    return store.begin(pending)
