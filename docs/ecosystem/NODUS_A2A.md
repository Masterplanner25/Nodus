# `nodus-a2a`

> **Status:** Partially implemented. Current `C:\dev\nodus-a2a` is the AgentCoordinator layer
> (23 tests: AgentRegistry, AgentCoordinator, DelegationRequest, DeadLetterService,
> StuckRunWatchdog) — a subset of this spec. The full A2A wire-protocol adapter (169 tests,
> nodus-lang dep) described by this spec is preserved at github.com/Masterplanner25/nodus-a2a.

## Summary

`nodus-a2a` is a Python-first coordination framework for multi-agent Nodus
systems. Its public Python API is the canonical contract that a future thin
Nodus builtin will wrap. The framework sits above `nodus-agent`: Nodus Core
executes an individual agent run, while `nodus-a2a` owns registration,
capability matching, load-aware selection, delegation leases, dead-letter
handling, and stuck-delegation recovery.

V1 scope is a reusable framework shell with in-memory defaults. It is not a
replacement for queues, event buses, or HTTP routers.

## Public Python API

Required public types:

- `A2AFramework`
- `A2AFrameworkConfig`
- `AgentDescriptor`
- `AgentCapability`
- `AgentHealth`
- `AgentLoad`
- `DelegationRequest`
- `DelegationDecision`
- `DelegationLease`
- `DeadLetterRecord`
- `RecoveryRecord`
- `AgentRegistry` protocol
- `LeaseStore` protocol
- `DeadLetterStore` protocol
- `SelectionPolicy` protocol
- `RoutingPolicy` protocol
- `HealthPolicy` protocol
- `DeadLetterPolicy` protocol
- `WatchdogPolicy` protocol
- `A2AEvent`
- `A2AFrameworkError`

Canonical surface:

```python
a2a = A2AFramework(...)
a2a.register_agent(...)
decision = a2a.route_request(...)
a2a.claim_lease(...)
a2a.record_result(...)
a2a.scan_stuck_delegations()
```

Future thin builtins should wrap these typed operations instead of
re-implementing coordination semantics in the runtime layer.

## Public Model Contracts

### `AgentCapability`

Required fields:

- `name: str`
- `version: str`
- `cost_hint: float`
- `risk_hint: str`
- `max_concurrency: int`

### `AgentHealth`

Required fields:

- `status: str`
- `heartbeat_at: datetime`
- `error_rate: float`
- `availability: float`

### `AgentLoad`

Required fields:

- `active_tasks: int`
- `queue_depth: int`
- `utilization_score: float`
- `updated_at: datetime`

### `AgentDescriptor`

Required fields:

- `agent_id: str`
- `agent_kind: str`
- `endpoint: str | None`
- `capabilities: list[AgentCapability]`
- `supported_modes: list[str]`
- `health: AgentHealth`
- `load: AgentLoad`
- `metadata: dict[str, object]`

### `DelegationRequest`

Required fields:

- `task_id: str`
- `objective: str`
- `required_capabilities: list[str]`
- `preferred_mode: str`
- `trace_id: str | None`
- `correlation_id: str | None`
- `deadline_at: datetime | None`
- `payload: dict[str, object]`

### `DelegationDecision`

Required fields:

- `task_id: str`
- `selected_agent_id: str | None`
- `routing_mode: str`
- `decision_reason: str`
- `fallback_agent_ids: list[str]`

### `DelegationLease`

Required fields:

- `lease_id: str`
- `task_id: str`
- `agent_id: str`
- `request: DelegationRequest`
- `status: str`
- `expires_at: datetime`
- `claimed_at: datetime | None`
- `completed_at: datetime | None`
- `attempt_count: int`

### `DeadLetterRecord`

Required fields:

- `task_id: str`
- `request: DelegationRequest`
- `reason: str`
- `retry_count: int`
- `last_agent_id: str | None`
- `created_at: datetime`
- `metadata: dict[str, object]`

### `RecoveryRecord`

Required fields:

- `task_id: str`
- `lease_id: str`
- `reason: str`
- `action_taken: str`
- `created_at: datetime`

### `A2AEvent`

Required fields:

- `event_id: str`
- `event_type: str`
- `task_id: str`
- `payload: dict[str, object]`
- `created_at: datetime`

## Core Interfaces

### `AgentRegistry`

Required operations:

- `upsert(agent: AgentDescriptor) -> AgentDescriptor`
- `get(agent_id: str) -> AgentDescriptor | None`
- `list_agents() -> list[AgentDescriptor]`

### `LeaseStore`

Required operations:

- `create(lease: DelegationLease) -> DelegationLease`
- `update(lease: DelegationLease) -> DelegationLease`
- `get(lease_id: str) -> DelegationLease | None`
- `list_leases() -> list[DelegationLease]`

### `DeadLetterStore`

Required operations:

- `create(record: DeadLetterRecord) -> DeadLetterRecord`
- `list_records() -> list[DeadLetterRecord]`

### `SelectionPolicy`

Required method:

```python
rank(candidates: list[AgentDescriptor], request: DelegationRequest) -> list[AgentDescriptor]
```

### `RoutingPolicy`

Required method:

```python
decide(candidates: list[AgentDescriptor], request: DelegationRequest) -> DelegationDecision
```

### `HealthPolicy`

Required method:

```python
is_routable(agent: AgentDescriptor) -> bool
```

### `DeadLetterPolicy`

Required method:

```python
should_dead_letter(lease: DelegationLease, *, error: str | None = None) -> bool
```

### `WatchdogPolicy`

Required method:

```python
detect_expired(leases: list[DelegationLease], *, now: datetime) -> list[DelegationLease]
```

## Architecture

Split the framework into five layers:

1. Pure coordination models
2. Registry, lease, and dead-letter protocols
3. Selection and routing policies
4. Delegation lifecycle orchestration
5. Adapter-backed integrations

### Pure coordination models

Contains:

- agent, capability, health, load, request, decision, lease, dead-letter,
  recovery, and event models
- framework error types

No queue, event-bus, or HTTP-specific imports are allowed here.

### Store and protocol layer

Contains:

- registry interface
- lease store interface
- dead-letter store interface
- policy contracts

### Selection and routing layer

Contains:

- capability filtering
- health gating
- load-aware ranking
- fallback ordering

### Delegation lifecycle orchestration

Contains:

- registration
- route decision
- lease issuance
- claim and completion
- failure classification
- dead-letter handling
- watchdog scans
- event emission

### Adapter-backed integrations

Contains optional adapters over:

- `nodus-events` for coordination event delivery
- `nodus-queue` for queued handoff
- `nodus-memory` for specialization hints
- `nodus-observability` for metrics and traces
- HTTP router adapters for external coordination endpoints

## Behavior

V1 coordination flow:

1. register or refresh agent descriptor
2. receive typed delegation request
3. filter agents by capability
4. exclude unhealthy or unavailable agents
5. rank remaining agents by routing policy
6. emit a decision and create a lease
7. claim, complete, fail, reroute, or expire the lease
8. dead-letter terminal failures
9. emit audit-friendly coordination events

Framework rules:

- capability matching is explicit and typed
- routing decisions must be explainable
- lease expiration and stuck detection are first-class
- dead-letter handling is part of the API, not an app convention
- coordination events are observable without coupling to one backend

The framework must not:

- execute an individual agent's step logic
- expose queue or HTTP transport details in the public API
- hard-code one registry or lease backend
- assume one deployment topology

## Package Dependencies

Core required:

- none beyond Python stdlib typing and datetime facilities

Optional:

- `nodus-events`
- `nodus-queue`
- `nodus-memory`
- `nodus-observability`

V1 should include in-memory reference implementations for registry, leases,
dead letters, and watchdog logic so the framework is testable without Redis,
SQL, or HTTP dependencies.

## Test Plan

Required tests:

- agent registration and update
- capability filtering and deterministic fallback ordering
- load-aware selection prefers healthier lighter candidate
- no-candidate request creates dead letter
- lease claim and completion lifecycle
- failure reroute to fallback candidate
- terminal failure dead-letters the request
- expired lease detection by watchdog
- stuck recovery record emission
- coordination event timeline completeness

## Acceptance Criteria

- A future thin Nodus builtin can register agents, route work, inspect leases,
  and recover stuck delegations through a stable Python API.
- The framework is useful without Redis, SQL, or HTTP integrations.
- Routing, dead-letter, and watchdog behavior are explicit and observable.
- Queue, event, memory, and observability integrations remain replaceable
  adapters.
