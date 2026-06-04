# `nodus-events`

> **Status:** v0.1.0 implemented — `C:\dev\nodus-events`, 17 tests, prepared not yet published.
> This document is the original design spec; the implementation was built against it.

## Summary

`nodus-events` is a Python-first event distribution library for AI-native
runtimes. Its public Python API is the canonical contract that a future thin
Nodus builtin will wrap. The library exists to centralize event envelopes,
cross-instance publish/subscribe, buffering during pre-ready states, and
optional audit hooks.

V1 scope is the reusable core plus optional Redis and audit adapters. It is not
a scheduler, workflow engine, or app webhook framework.

## Public Python API

Required public types:

- `EventEnvelope`
- `EventBus`
- `EventPublisher`
- `EventSubscriber`
- `Subscription`
- `DeliveryResult`
- `BufferPolicy`
- `DeliveryBackend` protocol
- `AuditStore` protocol
- `EventDeliveryError`

Canonical surface:

```python
event_bus.publish(envelope: EventEnvelope) -> DeliveryResult
subscription = event_bus.subscribe(event_type: str, handler: EventHandler)
event_bus.pause_delivery()
drained = event_bus.drain_buffer()
```

Future Nodus builtins should wrap publish, subscribe, pause, resume, and drain
over this Python API without embedding Redis or DB assumptions.

## Public Model Contracts

### `EventEnvelope`

Required fields:

- `event_id: str`
- `event_type: str`
- `timestamp: datetime`
- `source_instance_id: str`
- `correlation_id: str | None`
- `trace_id: str | None`
- `payload: object`
- `metadata: dict[str, str]`

Rules:

- envelopes are immutable after creation
- `event_id` uniqueness is caller-owned in v1
- payload may be any JSON-serializable object; serialization belongs in the
  backend adapter layer

### `DeliveryResult`

Required fields:

- `accepted: bool`
- `delivery_mode: str`
- `buffered: bool`
- `audit_recorded: bool`
- `detail: str | None`

### `BufferPolicy`

Supported v1 modes:

- `disabled`
- `bounded_drop_new`
- `bounded_drop_oldest`

Required fields:

- `mode: str`
- `max_events: int`

Buffer overflow behavior must be pure, deterministic policy logic.

### `Subscription`

Required fields:

- `subscription_id: str`
- `event_type: str`
- `handler_name: str`

## Core Interfaces

### `DeliveryBackend`

Required methods:

- `publish(envelope: EventEnvelope) -> None`
- `start(handler: Callable[[EventEnvelope], None]) -> None`
- `stop() -> None`
- `is_running() -> bool`

The backend owns transport concerns such as Redis pub/sub and reconnect loops.
The core event bus owns envelope semantics and delivery state transitions.

### `AuditStore`

Required methods:

- `record_publish_started(envelope: EventEnvelope) -> None`
- `record_publish_completed(envelope: EventEnvelope, result: DeliveryResult) -> None`
- `record_publish_failed(envelope: EventEnvelope, error: Exception) -> None`

The audit store is optional in v1 and must not be required for local operation.

## Architecture

Split the library into three layers:

1. Pure envelope and policy layer
2. Core event bus layer
3. Optional transport and audit adapters

### Pure envelope and policy layer

Contains:

- event envelope model
- source-instance dedup rules
- buffer policy rules
- pause/resume state transitions
- drain ordering rules

No `redis` or `sqlalchemy` imports are allowed here.

### Core event bus layer

Contains:

- local in-process subscriptions
- publish orchestration
- pause/resume control
- pre-ready buffering
- dispatch into subscribed handlers
- backend handoff

This layer depends only on backend protocols.

### Optional transport and audit adapters

Contains:

- Redis pub/sub backend
- reconnect and backoff loop
- SQL audit store

This is where actual network and DB integration live.

## Behavior

- local publish/subscribe works with no backend configured
- if delivery is paused, publish follows the configured buffer policy
- `drain_buffer()` dispatches buffered events in insertion order
- if a backend is configured, publish sends events to the backend after local
  handling unless configured otherwise by the core API
- source-instance deduplication is enforced on backend-delivered events using
  `source_instance_id`
- Redis reconnect logic belongs in the Redis adapter, not the core bus

The library must not:

- hard-code scheduler-specific "rehydration" concepts
- require Redis in the core package
- require SQLAlchemy in the core package

## Redis Adapter Requirements

The optional Redis backend must provide:

- JSON serialization of `EventEnvelope`
- self-source deduplication using `source_instance_id`
- reconnect loop with bounded backoff
- listener startup and shutdown lifecycle
- failure isolation so local bus semantics still work if Redis is unavailable

The adapter may use `nodus-retry` internally for reconnect policy, but only via
an explicit adapter boundary.

## SQL Audit Adapter Requirements

If shipped in v1, the SQL audit adapter must store at minimum:

- event id
- event type
- timestamp
- source instance id
- correlation id
- trace id
- publish status
- error detail if failed

Schema ownership and migrations remain adapter concerns, not core-library
concerns.

## Package Dependencies

Core required:

- none beyond Python stdlib typing and datetime facilities

Optional:

- `redis`
- `sqlalchemy`

## Test Plan

Required core tests:

- local publish to one subscriber
- local publish to multiple subscribers
- pause then buffer event
- pause with `bounded_drop_new`
- pause with `bounded_drop_oldest`
- resume then drain in insertion order
- source-instance dedup rule
- handler exception isolation

Required Redis adapter tests if shipped:

- publish serializes envelope correctly
- listener deserializes envelope correctly
- self-source event ignored
- foreign-source event delivered
- reconnect after transport interruption

Required audit adapter tests if shipped:

- publish started recorded
- publish completed recorded
- publish failed recorded

## Acceptance Criteria

- A future Nodus builtin can publish and subscribe through one stable Python
  event bus surface.
- Local-only operation works with no Redis or SQL installed.
- Pure buffering and dedup logic are testable without transport backends.
- Cross-instance transport and audit persistence remain replaceable adapters.
