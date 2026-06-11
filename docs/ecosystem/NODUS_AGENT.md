# `nodus-agent`

> **Status:** v0.1.0 implemented and **published on PyPI** ✅ — `C:\dev\nodus-agent`, 28 tests.
> This document is the original design spec; the implementation was built against it.

## Summary

`nodus-agent` is a Python-first agent orchestration framework for AI-native
runtimes. Its public Python API is the canonical contract that a future thin
Nodus builtin will wrap. The framework exists to make plan, approve, execute,
delegate, recover, and replay loops first-class primitives for agent builders.

V1 scope is a reusable orchestration shell. It owns lifecycle semantics and
guardrails, but it does not own domain tools, UI workflows, or provider
transport logic.

## Public Python API

Required public types:

- `AgentFramework`
- `AgentFrameworkConfig`
- `AgentRun`
- `AgentPlan`
- `AgentPlanStep`
- `AgentEvent`
- `PlannerBackend` protocol
- `ApprovalPolicy` protocol
- `CapabilityPolicy` protocol
- `DelegationPolicy` protocol
- `RecoveryPolicy` protocol
- `ToolRegistry`
- `AgentFrameworkError`
- `ApprovalRequiredError`
- `CapabilityViolationError`
- `DelegationBlockedError`

Canonical surface:

```python
framework = AgentFramework(...)
run = framework.create_run(objective="...", user_id="user-1")
framework.approve_run(run.run_id)
framework.execute_run(run.run_id)
framework.recover_run(run.run_id)
framework.replay_run(run.run_id)
```

Future thin builtins should wrap these typed orchestration operations rather
than re-implementing lifecycle state transitions in the language runtime.

## Public Model Contracts

### `AgentPlanStep`

Required fields:

- `tool_name: str`
- `args: dict[str, object]`
- `risk_level: str`
- `description: str`

### `AgentPlan`

Required fields:

- `executive_summary: str`
- `steps: list[AgentPlanStep]`
- `overall_risk: str`
- `planner_name: str | None`
- `planner_metadata: dict[str, str]`

### `AgentRun`

Required fields:

- `run_id: str`
- `objective: str`
- `user_id: str`
- `status: str`
- `plan: AgentPlan`
- `capability_token: dict[str, object] | None`
- `trace_id: str | None`
- `correlation_id: str | None`
- `parent_run_id: str | None`
- `delegated_to: str | None`
- `steps_completed: int`
- `created_at: datetime`
- `updated_at: datetime`
- `started_at: datetime | None`
- `completed_at: datetime | None`
- `result: dict[str, object] | None`
- `error: str | None`

### `AgentEvent`

Required fields:

- `event_id: str`
- `run_id: str`
- `event_type: str`
- `payload: dict[str, object]`
- `created_at: datetime`

## Core Interfaces

### `PlannerBackend`

Required method:

```python
plan(objective: str, *, user_id: str, available_tools: list[dict[str, object]]) -> AgentPlan
```

The planner backend is responsible only for generating structured plans.
Execution semantics remain in the framework.

### `ApprovalPolicy`

Required method:

```python
requires_approval(plan: AgentPlan, *, user_id: str) -> bool
```

### `CapabilityPolicy`

Required methods:

- `mint(plan: AgentPlan, *, user_id: str) -> dict[str, object]`
- `check(tool_name: str, capability_token: dict[str, object] | None) -> bool`

### `DelegationPolicy`

Required method:

```python
allow(parent_run: AgentRun, *, target_agent: str, ancestor_chain: list[str]) -> tuple[bool, str | None]
```

### `RecoveryPolicy`

Required method:

```python
can_recover(run: AgentRun) -> bool
```

## Tool Registry

The framework must treat tools as external registrations.

Required tool metadata:

- `name`
- `description`
- `risk_level`
- `required_capability`
- `handler`

The registry must allow:

- registering tools
- listing tool metadata for planning
- resolving a handler by tool name

## Architecture

Split the framework into four layers:

1. Pure orchestration models
2. Policy and registry layer
3. Framework lifecycle layer
4. Optional persistence and event adapters

### Pure orchestration models

Contains:

- plan models
- run models
- event models
- status constants
- framework errors

No storage or transport imports are allowed here.

### Policy and registry layer

Contains:

- planner protocol
- approval policy
- capability policy
- delegation policy
- recovery policy
- tool registry

This layer stays backend-free.

### Framework lifecycle layer

Contains:

- create run
- approve/reject run
- execute step loop
- delegate run
- recover run
- replay run
- event emission hooks

This is the orchestration core.

### Optional persistence and event adapters

Contains:

- repository adapters over `nodus-store-sql` or other backends
- event emission adapters over `nodus-events`

V1 may ship an in-memory default runtime path for tests and local usage.

## Behavior

Required run states in v1:

- `pending`
- `pending_approval`
- `approved`
- `executing`
- `delegated`
- `completed`
- `failed`
- `rejected`
- `stuck`

Required transitions:

- `pending -> pending_approval | approved`
- `pending_approval -> approved | rejected`
- `approved -> executing`
- `executing -> delegated | completed | failed | stuck`
- `stuck -> executing`
- terminal runs may be replayed into a new `pending` run

Execution rules:

- plans are validated before a run is persisted
- approval gating happens before capability token minting
- each step must pass capability checks before tool execution
- each step result is persisted before moving to the next step
- high-risk steps do not retry by default
- delegation must enforce loop prevention and bounded ancestry depth
- recovery resumes from the next incomplete step rather than re-running
  completed steps

The framework must not:

- embed provider-specific planner HTTP logic in the core
- own domain tool implementations
- require SQL or Redis in the core package
- expose ORM models in the public API

## Package Dependencies

Core required:

- none beyond Python stdlib typing and datetime facilities

Optional:

- none in core v1

Framework adapters may depend on other ecosystem packages later, but the public
orchestration contract should not require them at import time.

## Test Plan

Required tests:

- deterministic local planner returns a structured plan
- create run enters `pending_approval` when approval is required
- approve and reject transitions
- capability denial blocks tool execution
- successful multi-step execution
- high-risk step fails without retry
- delegation creates a child run and marks parent delegated
- delegation loop is blocked
- recovery resumes from the next incomplete step
- replay clones plan into a new pending run
- event timeline includes run and step lifecycle events

## Acceptance Criteria

- A future thin Nodus builtin can create, approve, execute, recover, and replay
  agent runs over a stable Python API.
- The framework is useful without any runtime-specific SQL or HTTP dependency.
- Policy, planning, and tool registration are pluggable.
- Execution lifecycle semantics are first-class and deterministic.
