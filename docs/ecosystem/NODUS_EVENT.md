# `nodus-event`

> **Status: Not yet implemented as a standalone package.** This spec describes a higher-level
> event framework that sits above `nodus-events` (the transport/bus layer, which IS built).
> `nodus-event` (routing, causality, webhooks, replay) remains a future package.

## Summary

`nodus-event` is a Python-first event framework for Nodus runtimes and
integration builders. Its public Python API is the canonical contract that a
future thin Nodus builtin will wrap. The framework sits above `nodus-events`:
the lower-level library handles event transport and buffering, while
`nodus-event` owns event semantics, routing, causality, local handlers,
webhooks, replay, and audit-friendly history.

V1 scope is a reusable framework shell with in-memory defaults. It is not a
replacement for `nodus-events`, `nodus-http`, or `nodus-retry`.

## Public Python API

Required public types:

- `EventFramework`
- `EventEnvelope`
- `EventCause`
- `EventRoute`
- `WebhookSubscription`
- `EventReplayRequest`
- `EventReplayResult`
- `EventAuditRecord`
- `EventHandler` protocol
- `HandlerPolicy` protocol
- `DeliveryPolicy` protocol
- `WebhookPolicy` protocol
- `CausalityPolicy` protocol
- `AuditStore` protocol
- `DistributedEventPublisher` protocol
- `WebhookDispatcher` protocol
- `EventFrameworkError`

Canonical surface:

```python
framework = EventFramework(...)
framework.publish("agent.run.completed", {...})
framework.register_handler("agent.run.*", handler)
framework.register_webhook(...)
framework.replay(...)
```

Future thin builtins should wrap these typed operations instead of
re-implementing event semantics in the runtime layer.

## Public Model Contracts

### `EventCause`

Required fields:

- `parent_event_id: str | None`
- `parent_run_id: str | None`
- `parent_step_id: str | None`
- `relationship_type: str`

### `EventEnvelope`

Required fields:

- `event_id: str`
- `event_type: str`
- `payload: object`
- `timestamp: datetime`
- `source_instance_id: str`
- `trace_id: str | None`
- `correlation_id: str | None`
- `cause_chain: list[EventCause]`
- `metadata: dict[str, object]`
- `do_not_replay: bool`

### `EventRoute`

Required fields:

- `route_id: str`
- `event_pattern: str`
- `target_kind: str`
- `delivery_mode: str`
- `metadata: dict[str, object]`

### `WebhookSubscription`

Required fields:

- `subscription_id: str`
- `event_pattern: str`
- `target_url: str`
- `secret: str | None`
- `headers: dict[str, str]`
- `enabled: bool`

### `EventAuditRecord`

Required fields:

- `event_id: str`
- `envelope: EventEnvelope`
- `published_at: datetime`
- `handler_outcomes: list[dict[str, object]]`
- `webhook_outcomes: list[dict[str, object]]`
- `distributed_outcome: dict[str, object] | None`
- `replay_count: int`
- `completed: bool`

### `EventReplayRequest`

Required fields:

- `event_types: list[str]`
- `correlation_id: str | None`
- `trace_id: str | None`
- `replay_mode: str`
- `include_do_not_replay: bool`

### `EventReplayResult`

Required fields:

- `events_replayed: int`
- `handler_invocations: int`
- `webhook_invocations: int`
- `event_ids: list[str]`

## Core Interfaces

### `AuditStore`

Required operations:

- `create_record(record: EventAuditRecord) -> EventAuditRecord`
- `update_record(record: EventAuditRecord) -> EventAuditRecord`
- `get_record(event_id: str) -> EventAuditRecord | None`
- `list_records() -> list[EventAuditRecord]`

### `EventHandler`

Required behavior:

- accepts `EventEnvelope`
- may be synchronous or asynchronous
- returns arbitrary result payload

### `DistributedEventPublisher`

Required method:

```python
publish(envelope: EventEnvelope) -> dict[str, object]
```

### `WebhookDispatcher`

Required method:

```python
dispatch(subscription: WebhookSubscription, envelope: EventEnvelope, headers: dict[str, str]) -> dict[str, object]
```

### `CausalityPolicy`

Required method:

```python
attach(envelope: EventEnvelope, *, cause: EventCause | None) -> EventEnvelope
```

### `WebhookPolicy`

Required method:

```python
build_headers(subscription: WebhookSubscription, envelope: EventEnvelope) -> dict[str, str]
```

## Architecture

Split the framework into five layers:

1. Pure event models
2. Handler, audit, transport, and webhook protocols
3. Routing and pattern matching
4. Publish and replay orchestration
5. Adapter-backed delivery integration

### Pure event models

Contains:

- event, cause, route, audit, and replay models
- framework error types

No transport-specific imports are allowed here.

### Protocol layer

Contains:

- audit store interface
- distributed event publisher interface
- webhook dispatcher interface
- handler and policy contracts

This layer remains backend-agnostic.

### Routing and pattern matching

Contains:

- event type pattern matching
- local handler registration
- webhook subscription registration
- route selection

### Publish and replay orchestration

Contains:

- envelope creation
- causality attachment
- local handler dispatch
- distributed publish
- webhook dispatch
- audit recording
- replay by scope and mode

### Adapter-backed delivery integration

Contains optional adapters over:

- `nodus-events` for distributed publish
- `nodus-http` for webhook delivery
- `nodus-retry` for webhook retry policies
- SQL-backed audit storage

## Behavior

V1 event flow:

1. construct and validate envelope
2. attach explicit causality metadata
3. create audit record
4. optionally publish to distributed transport
5. dispatch matching local handlers
6. dispatch matching webhooks
7. persist outcomes
8. return completed audit record

Framework rules:

- `event_type` and `source_instance_id` are mandatory
- causality is explicit, not hidden in free-form metadata
- one handler failure must not block other handlers
- replay is explicit and must respect `do_not_replay` unless overridden
- audit history must be queryable without transport-specific coupling

The framework must not:

- expose Redis, HTTP client, or ORM details in the public API
- assume one distributed backend
- assume one webhook delivery stack
- hard-code workflow or agent semantics

## Package Dependencies

Core required:

- none beyond Python stdlib typing, asyncio, fnmatch, and datetime facilities

Optional:

- `nodus-events` adapter
- `nodus-http` adapter
- `nodus-retry` adapter

V1 should include in-memory reference implementations for audit storage and
local-only publish mode so the framework is testable without Redis, SQL, or
HTTP dependencies.

## Test Plan

Required tests:

- local handler registration and dispatch
- mixed sync and async handler execution
- wildcard event pattern routing
- one handler failure does not block other handlers
- distributed publish adapter invoked when configured
- webhook routing and header policy use
- causal chain propagation across child events
- replay by correlation id
- replay respects `do_not_replay` by default
- audit record completeness and ordering

## Acceptance Criteria

- A future thin Nodus builtin can publish, route, replay, and inspect events
  through a stable Python API.
- The framework is useful without Redis, SQL, or HTTP integrations.
- Causality, replay, and audit behavior are explicit and deterministic.
- Transport, webhook dispatch, and audit storage remain replaceable adapters.
