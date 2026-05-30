# Nodus Workflow Framework Plan

## Purpose

`nodus-workflow` is the runtime orchestration layer that sits directly on top of Nodus execution semantics and turns lowered workflows into durable, resumable node graphs.

This document records:

- the target framework shape
- what has already been implemented in this repo
- what remains to complete the framework beyond the current local/runtime-grade milestone

## Target Outcome

The framework should provide:

- resumable workflow graph execution
- first-class `WAIT` / `RESUME`
- durable checkpointing
- retry scheduling as explicit workflow state
- claim-safe resume/execution across processes
- rehydration after restart
- operator-visible run inventory and recovery surfaces

It should not replace Nodus core language execution. It should wrap and persist workflow execution semantics so higher-level runtimes and services do not have to rebuild orchestration logic themselves.

## Framework Boundary

`nodus-workflow` is responsible for:

- workflow run lifecycle state
- persistence of run metadata, waits, retries, claims, and checkpoints
- orchestration sweep behavior
- operator inventory and replay surfaces

It is not responsible for:

- the core parser/compiler/VM
- defining Nodus syntax itself
- generic distributed infrastructure outside the workflow store boundary
- agent-specific planning or memory concerns

## Current Implementation Status

The framework is already substantially implemented in this repository.

### Completed Core Execution Semantics

- workflow runs are persisted as framework run records
- workflows can enter `waiting` state through `workflow_wait(...)`
- workflows can be resumed through `resume_workflow(...)`
- resume payloads are available through `workflow_resume_payload()`
- resumed workflows continue from persisted graph/checkpoint state
- workflow checkpoints are split into:
  - public/operator-visible checkpoints
  - engine/internal checkpoints

### Completed Durable Runtime Features

- explicit workflow run states exist, including:
  - `pending`
  - `running`
  - `waiting`
  - `retry_scheduled`
  - `completed`
  - `failed`
  - `dead_lettered`
- retry scheduling is first-class framework state
- wait timeouts can expire to `dead_lettered`
- dead-lettered runs can be listed, inspected, rearmed, and replayed
- read-time normalization exists for legacy checkpoint/state files
- explicit snapshot migration exists for older persisted workflow state

### Completed Coordination and Persistence Features

- local file-backed workflow store exists
- SQLite-backed workflow store exists
- workflow claim semantics exist for:
  - run execution
  - waiting-run resume
  - retry resume
- SQLite provides stronger cross-process coordination than the local store
- the store contract is explicit via `WorkflowStore`

### Completed Rehydration and Sweep Features

- rehydratable runs can be discovered
- explicit rehydration APIs exist
- orchestration sweep exists and performs:
  - wait-timeout expiry
  - due retry resume
  - rehydration of waiting/running/retryable runs
- runtime service startup/background sweep is wired

### Completed Operator Surfaces

- HTTP run inventory endpoints exist
- CLI workflow inventory commands exist
- dead-letter HTTP and CLI surfaces exist
- replay/rearm surfaces exist
- run inventory supports:
  - status filtering
  - workflow filtering
  - execution kind filtering
  - wait/retry/replay/time filters
  - offset pagination
  - cursor-style pagination
  - scoped status counts

## Main Code Areas

The framework currently lives across these areas:

- [src/nodus_workflow](/abs/path/C:/dev/Coding%20Language/src/nodus_workflow)
- [src/nodus/orchestration/task_graph.py](/abs/path/C:/dev/Coding%20Language/src/nodus/orchestration/task_graph.py)
- [src/nodus/vm/vm.py](/abs/path/C:/dev/Coding%20Language/src/nodus/vm/vm.py)
- [src/nodus/services/server.py](/abs/path/C:/dev/Coding%20Language/src/nodus/services/server.py)
- [src/nodus/cli/cli.py](/abs/path/C:/dev/Coding%20Language/src/nodus/cli/cli.py)

Primary tests:

- [tests/test_nodus_workflow_framework.py](/abs/path/C:/dev/Coding%20Language/tests/test_nodus_workflow_framework.py)
- [tests/test_workflow_persistence.py](/abs/path/C:/dev/Coding%20Language/tests/test_workflow_persistence.py)
- [tests/test_workflow_dsl.py](/abs/path/C:/dev/Coding%20Language/tests/test_workflow_dsl.py)
- [tests/test_server.py](/abs/path/C:/dev/Coding%20Language/tests/test_server.py)

## Remaining Work To Complete The Framework

The remaining work is no longer about basic workflow semantics. It is mostly production hardening, operator ergonomics, and packaging.

### 1. Stronger Cursor Model

Current state:

- inventory supports cursor pagination
- current cursor is offset-derived: `o:<n>`

Why this is incomplete:

- offset-derived cursors are not stable under concurrent inserts/updates
- they are adequate for local/operator usage but not ideal for a larger admin surface

Completion target:

- move to a stable cursor based on sort key and run identity
- likely use `(updated_at, run_id)` as the paging anchor
- preserve backward compatibility for existing `offset` users

### 2. Stronger Production Coordination Posture

Current state:

- local file store works for local workflows
- SQLite store provides useful cross-process claims

Why this is incomplete:

- SQLite is not the final answer for broader multi-node production coordination
- lease renewal, ownership transfer, and more explicit crash-recovery semantics are still limited

Completion target:

- decide whether SQLite is the final supported production backend or an intermediate one
- if not final, add a stronger SQL/distributed backend
- formalize lease/claim behavior more aggressively

### 3. Richer Admin Operations

Current state:

- list runs
- inspect runs
- filter runs
- list dead letters
- replay/rearm dead letters

Why this is incomplete:

- operator actions are still mostly single-run actions
- there is no bulk recovery or policy-driven requeue surface

Completion target:

- bulk replay/requeue
- batch dead-letter review/export
- richer policy controls for recovery decisions

### 4. Storage and Query Scaling

Current state:

- inventory surfaces work correctly
- local/SQLite implementations are sufficient for the current scale and tests

Why this is incomplete:

- larger inventories may need better indexing and query behavior
- current inventory path remains simple and runtime-oriented

Completion target:

- identify inventory query hot paths
- add backend-specific indexing/query improvements
- avoid full-list scans where practical for larger stores

### 5. Auth and Admin Hardening

Current state:

- workflow APIs exist
- server auth token can gate access

Why this is incomplete:

- operator APIs are not yet positioned as a hardened admin surface by default

Completion target:

- explicitly define which workflow endpoints are operator/admin only
- tighten non-local deployment posture
- document safe deployment defaults

### 6. Documentation and Packaging

Current state:

- implementation exists in the main repo
- tests cover the framework behavior

Why this is incomplete:

- there is no standalone `nodus-workflow` package/repo story yet
- docs are still scattered across runtime and test behavior

Completion target:

- create package-level README and public API guidance
- document architecture and guarantees
- decide whether to extract to `packages/nodus-workflow/` or keep in-tree longer

## Recommended Completion Order

If the goal is to move from “implemented” to “actually complete,” the recommended order is:

1. Stable cursor model
2. Production coordination decision and backend hardening
3. Admin/recovery bulk operations
4. Storage/query scaling cleanup
5. Auth/admin hardening
6. Packaging and final docs

## Proposed Definition Of “Framework Complete”

The workflow framework should be considered complete when all of the following are true:

- workflow execution semantics are durable and resumable
- retries, waits, claims, and rehydration are first-class and well-tested
- at least one non-local persistence backend is clearly supported for real operator use
- operator inventory and replay surfaces are sufficient for recovery workflows
- pagination and filtering are stable enough for growing inventories
- deployment and auth expectations are documented
- the public framework surface is documented as a real subsystem, not just an internal implementation

## Current Assessment

Current state is best described as:

- core framework semantics: complete
- local/runtime orchestration: complete
- operator surface: strong
- production hardening and packaging: partially complete

In practice, the framework is already far beyond prototype status. The remaining work is mostly about making it cleaner, more stable under scale, and easier to ship as a clearly bounded framework product.
