# `nodus-store-sql`

> **Status:** v0.1.0 implemented — `C:\dev\nodus-store-sql`, 47 tests (31 sync + 16 async),
> prepared not yet published. Promoted from incubator scaffold.
> This document is the original design spec; the implementation was built against it.

## Summary

`nodus-store-sql` is a Python-first SQL persistence adapter library for
AI-native runtimes. Its public Python API is the canonical contract that a
future thin Nodus builtin or runtime integration will wrap. The library exists
to provide SQLAlchemy-backed persistence for durable runtime records such as
runs, events, and jobs without owning workflow, retry, queue, or scheduler
policy.

V1 scope is a reusable SQL adapter layer. It is not a runtime framework and it
does not define orchestration semantics.

## Public Python API

Required public types:

- `SqlStoreConfig`
- `SqlStore`
- `RunRecord`
- `EventRecord`
- `JobRecord`
- `RunStore`
- `EventStore`
- `JobStore`
- `SqlStoreError`
- `RecordNotFoundError`
- `OptimisticLockError`

Canonical surface:

```python
store = SqlStore(config)
run = store.runs.create(record)
store.events.append(event)
claimed = store.jobs.claim_pending(job_id, worker_id="worker-a")
```

Future thin builtins should wrap these repository calls over typed records
rather than exposing raw ORM models.

## Public Record Contracts

### `RunRecord`

Required fields:

- `run_id: str`
- `run_type: str`
- `status: str`
- `state_payload: object | None`
- `trace_id: str | None`
- `correlation_id: str | None`
- `owner_id: str | None`
- `scope: str | None`
- `version: int`
- `created_at: datetime`
- `updated_at: datetime`
- `completed_at: datetime | None`

### `EventRecord`

Required fields:

- `event_id: str`
- `event_type: str`
- `payload: object | None`
- `source: str | None`
- `run_id: str | None`
- `trace_id: str | None`
- `correlation_id: str | None`
- `parent_event_id: str | None`
- `sequence_index: int | None`
- `created_at: datetime`

### `JobRecord`

Required fields:

- `job_id: str`
- `task_name: str`
- `status: str`
- `payload: object | None`
- `owner_id: str | None`
- `trace_id: str | None`
- `correlation_id: str | None`
- `attempt_count: int`
- `max_attempts: int`
- `scheduled_for: datetime | None`
- `claimed_by: str | None`
- `claimed_at: datetime | None`
- `completed_at: datetime | None`
- `created_at: datetime`
- `updated_at: datetime`

## Repository Interfaces

### `RunStore`

Required operations:

- `create(record: RunRecord) -> RunRecord`
- `get(run_id: str) -> RunRecord | None`
- `update(record: RunRecord) -> RunRecord`
- `set_status(run_id: str, status: str, *, completed_at: datetime | None = None) -> RunRecord`
- `list_by_trace(trace_id: str) -> list[RunRecord]`

`update()` must use optimistic version checks and raise `OptimisticLockError`
on stale writes.

### `EventStore`

Required operations:

- `append(record: EventRecord) -> EventRecord`
- `get(event_id: str) -> EventRecord | None`
- `list_for_run(run_id: str) -> list[EventRecord]`
- `list_for_trace(trace_id: str) -> list[EventRecord]`

Ordering for list operations must be deterministic by creation time and
sequence index where present.

### `JobStore`

Required operations:

- `create(record: JobRecord) -> JobRecord`
- `get(job_id: str) -> JobRecord | None`
- `update(record: JobRecord) -> JobRecord`
- `claim_pending(job_id: str, worker_id: str) -> JobRecord | None`
- `list_pending(*, due_before: datetime | None = None) -> list[JobRecord]`
- `set_status(job_id: str, status: str, *, completed_at: datetime | None = None) -> JobRecord`

`claim_pending()` must be atomic from the caller’s perspective and only succeed
for pending jobs.

## Architecture

Split the package into three layers:

1. Pure record contract layer
2. Repository API layer
3. SQLAlchemy adapter layer

### Pure record contract layer

Contains:

- record dataclasses
- config model
- storage-facing errors

No SQLAlchemy ORM imports are allowed here.

### Repository API layer

Contains:

- run store interface
- event store interface
- job store interface
- transaction/unit-of-work boundaries

This layer describes storage behavior but not storage implementation details.

### SQLAlchemy adapter layer

Contains:

- ORM table mappings
- repository implementations
- engine/session setup
- transaction helper methods
- JSON payload serialization

This is the only layer that should depend directly on SQLAlchemy.

## Behavior

- the package requires explicit config; it must not depend on process-global
  env settings
- all repository APIs return typed records, not ORM model instances
- ORM models remain internal to the adapter
- transaction boundaries should be explicit and predictable
- state and payload fields should be stored in JSON-capable columns
- versioned updates are required for mutable records like runs and jobs

The library must not:

- define scheduler or queue semantics
- define retry policy
- assume FastAPI or any web framework
- assume Alembic ownership for schema lifecycle in v1

## Package Dependencies

Required:

- `SQLAlchemy`

Optional:

- none for v1

SQLite support is acceptable for tests and local development, but schema and
API design should remain Postgres-shaped where behavior matters.

## Test Plan

Required tests:

- run create/get/update round trip
- stale run update raises `OptimisticLockError`
- event append and ordered list by run
- event list by trace
- job create/get/update round trip
- `claim_pending()` succeeds exactly once for a pending job
- `claim_pending()` returns `None` for a non-pending job
- JSON payload/state serialization round trip
- session-scoped transaction helper commits and rolls back correctly

## Acceptance Criteria

- A future thin Nodus builtin or runtime integration can persist runs, events,
  and jobs through a stable Python repository API.
- The public API exposes typed records only, not ORM details.
- Pure record contracts are importable without constructing an engine.
- SQLAlchemy remains an adapter layer, not the shape of the public contract.
