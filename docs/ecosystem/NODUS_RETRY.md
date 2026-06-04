# `nodus-retry`

> **Status:** v0.1.0 implemented and **published on PyPI** ✅ — `C:\dev\nodus-retry`, 33 tests.
> This document is the original design spec; the implementation was built against it.

## Summary

`nodus-retry` is a Python-first retry and execution-guarantee library for
AI-native runtimes. Its public Python API is the canonical contract that a
future thin Nodus builtin will wrap. The library exists to centralize retry
policy declaration, backoff semantics, execution guarantees, and idempotent
effect-record behavior.

V1 scope is the reusable core. Durable SQL persistence is supported through an
adapter seam rather than being baked into the core package.

## Public Python API

Required public types:

- `RetryPolicy`
- `BackoffStrategy`
- `RetryClassifier`
- `RetryDecision`
- `ExecutionGuarantee`
- `RetryExecutor`
- `AsyncRetryExecutor`
- `IdempotencyKey`
- `EffectRecord`
- `IdempotencyStore` protocol
- `RetryExhaustedError`
- `IdempotencyConflictError`

Canonical execution surface:

```python
result = retry_executor.execute(
    operation_name="memory.write",
    policy=policy,
    guarantee=ExecutionGuarantee.IDEMPOTENT_REPLAY,
    idempotency_key=key,
    fn=callable,
)
```

Future Nodus builtins should wrap policy declaration and execution guarantee
selection over this surface, not re-implement retries in the language runtime.

## Public Model Contracts

### `RetryPolicy`

Required fields:

- `max_attempts: int`
- `backoff: BackoffStrategy`
- `high_risk_no_retry: bool`
- `retryable_exceptions: tuple[type[BaseException], ...]`
- `non_retryable_exceptions: tuple[type[BaseException], ...]`

Rules:

- `max_attempts` must be at least 1
- `high_risk_no_retry=True` forces a single attempt regardless of classifier
- policy is immutable after creation

### `BackoffStrategy`

Supported strategy kinds in v1:

- `fixed`
- `exponential`
- `bounded_exponential`
- `jittered_exponential`

Required fields:

- `kind: str`
- `base_delay_seconds: float`
- `max_delay_seconds: float | None`
- `jitter_ratio: float | None`

Backoff calculation must be pure and deterministic except where jitter is
explicitly selected.

### `RetryDecision`

Required fields:

- `should_retry: bool`
- `attempt_number: int`
- `next_delay_seconds: float | None`
- `reason: str`

This object is the output of pure retry classification logic.

### `ExecutionGuarantee`

Required v1 values:

- `BEST_EFFORT`
- `AT_LEAST_ONCE`
- `AT_MOST_ONCE`
- `IDEMPOTENT_REPLAY`

These semantics must be explicit in the public API so future builtins can
declare runtime guarantees directly.

### `IdempotencyKey`

Required fields:

- `action_id: str`
- `scope: str | None`
- `operation_name: str`

### `EffectRecord`

Required fields:

- `action_id: str`
- `operation_name: str`
- `status: str`
- `attempt_count: int`
- `result_payload: object | None`
- `error_payload: object | None`
- `created_at: datetime`
- `updated_at: datetime`
- `completed_at: datetime | None`
- `scope: str | None`
- `trace_id: str | None`
- `correlation_id: str | None`

Allowed status values in v1:

- `pending`
- `completed`
- `failed`

## Core Interfaces

### `RetryClassifier`

Required method:

```python
classify(
    exception: BaseException,
    *,
    attempt_number: int,
    policy: RetryPolicy,
    guarantee: ExecutionGuarantee,
    operation_name: str,
) -> RetryDecision
```

This is pure logic and must not depend on any store or executor state.

### `RetryExecutor`

Required method:

```python
execute(
    *,
    operation_name: str,
    policy: RetryPolicy,
    guarantee: ExecutionGuarantee,
    fn: Callable[[], T],
    idempotency_key: IdempotencyKey | None = None,
    store: IdempotencyStore | None = None,
) -> T
```

### `AsyncRetryExecutor`

Required method:

```python
aexecute(
    *,
    operation_name: str,
    policy: RetryPolicy,
    guarantee: ExecutionGuarantee,
    fn: Callable[[], Awaitable[T]],
    idempotency_key: IdempotencyKey | None = None,
    store: IdempotencyStore | None = None,
) -> T
```

## Idempotency Store Protocol

Required methods:

- `lookup(action_id: str) -> EffectRecord | None`
- `begin(record: EffectRecord) -> EffectRecord`
- `mark_completed(action_id: str, result_payload: object) -> EffectRecord`
- `mark_failed(action_id: str, error_payload: object) -> EffectRecord`
- `increment_attempts(action_id: str) -> EffectRecord`

Rules:

- `begin()` must reject concurrent duplicate claims for the same action id
- `lookup()` of a completed effect under `IDEMPOTENT_REPLAY` must allow
  callers to return the cached result without re-executing
- the core library defines the interface only; SQLAlchemy support belongs in
  an adapter package or optional extra

## Architecture

Split the library into three layers:

1. Pure retry semantics
2. Execution wrapper layer
3. Optional persistence adapters

### Pure retry semantics

Contains:

- policy models
- backoff calculation
- exception classification
- retry decision logic
- execution guarantee interpretation

No `sqlalchemy` imports are allowed here.

### Execution wrapper layer

Contains:

- sync executor
- async executor
- policy application
- delay scheduling
- retry exhaustion behavior
- idempotency store handoff

This layer may depend on the `IdempotencyStore` protocol but not on a specific
DB backend.

### Optional persistence adapters

Contains:

- SQLAlchemy `EffectRecord` mapping
- store implementation backed by SQLAlchemy
- adapter-specific serialization rules

This is where DB ownership begins. It is not part of the pure retry core.

## Behavior

- no policy means no execution; a policy is always explicit
- `high_risk_no_retry=True` means exactly one attempt
- `BEST_EFFORT` may execute without a store
- `IDEMPOTENT_REPLAY` requires a store and an idempotency key
- completed effect records under `IDEMPOTENT_REPLAY` return cached success
  instead of running `fn` again
- duplicate pending claims surface as `IdempotencyConflictError`
- terminal exhaustion surfaces as `RetryExhaustedError`

The library must not:

- depend on workflow engine concepts
- own queue or scheduler semantics
- require SQLAlchemy in the core package

## Package Dependencies

Core required:

- none beyond Python stdlib typing/time facilities

Optional:

- `sqlalchemy`
- `tenacity`

If `tenacity` is used at all, it should be behind an internal adapter rather
than leaking into the public API.

## Test Plan

Required tests:

- fixed backoff calculation
- exponential backoff calculation
- bounded exponential cap behavior
- jittered backoff behavior with deterministic test seed
- retryable exception classified as retry
- non-retryable exception classified as terminal
- high-risk no-retry behavior
- sync executor success after retry
- async executor success after retry
- retry exhaustion error
- effect-record replay returns cached result
- duplicate `begin()` conflict handling
- store-free best-effort execution path

Adapter tests if SQLAlchemy extra is shipped:

- create pending effect record
- reject duplicate action id
- complete effect record
- lookup completed effect for replay

## Acceptance Criteria

- A future Nodus builtin can declare a retry policy and execution guarantee over
  a stable Python API without knowing anything about SQLAlchemy.
- Pure retry policy logic is importable and testable without DB dependencies.
- Idempotency semantics are reusable by HTTP, workflow, agent, and event
  delivery libraries without embedding platform-specific state machines.
