# AINDY Integration Plan: Nodus ↔ Runtime ↔ Applications

No timeline assigned. Work this when ready.

---

## The Key Insight

The architecture being built toward already exists conceptually — it was built in reverse.
aindy-runtime wrote the implementations, then extracted them as standalone libraries,
then Nodus wrapped those libraries as builtins. What hasn't happened yet: aindy-runtime
using the libraries it created, and the apps layer running as .nd files.

```
What happened (extraction direction):
  aindy-runtime implementations
      ↓ extracted into
  nodus-* libraries
      ↓ wrapped as
  nodus-lang 4.0 builtins

What needs to happen (re-integration direction):
  nodus-lang 4.0 builtins
      ↓ call
  nodus-* libraries (shared instances)
      ↑ also used by
  aindy-runtime (replacing internal implementations)
      ↑ scripted by
  .nd files in aindy-apps-monolith
```

Result: one implementation of every concern, used at every layer.

---

## Library Origin Map

| Library | Origin | Plan Role |
|---------|--------|-----------|
| nodus-circuit-breaker | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-retry | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-events | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-auth | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-observability | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-state | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-schema | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-protocol | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-governance | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-workflow | extracted from runtime | Phase 1 — runtime gets its own code back |
| nodus-a2a | original design | Phase 1H — adoption/alignment pass (not a drop-in swap) |
| nodus-mcp | original design | Phase 1X — additive capability, no prior impl to replace |

---

## Current Dependency Chain

```
aindy-apps-monolith
  └─ depends on: aindy-runtime>=1.0,<2.0
        └─ depends on: nodus-lang==3.0.2  ← pinned 2 major versions behind
        └─ has internal Python copies of: circuit breaker, retry/effects,
           event bus, state machine, agent coordinator, auth, observability,
           workflow engine, schema validation, protocol envelopes
        └─ does NOT depend on any nodus-* libraries it originated
```

The libraries exist at C:\dev\nodus-* but are orphaned — neither aindy-runtime
nor the apps monolith declares them as dependencies.

---

## Target Architecture

```
aindy-apps-monolith
  └─ .nd files (flows, agents, scoring, automation, goals, prompts)
  └─ Python (ORM models, FastAPI routes, bootstrap registration only)
  └─ depends on: aindy-runtime>=2.0

aindy-runtime
  └─ depends on: nodus-lang==4.0.0
  └─ depends on: nodus-circuit-breaker, nodus-retry, nodus-events,
                 nodus-auth, nodus-observability, nodus-state, nodus-schema,
                 nodus-protocol, nodus-session, nodus-governance, nodus-workflow
  └─ Nodus layer exposes: full sys.v1.* surface, event.on(), flow.define(),
                          context.current(), agent.define(), named builtins

nodus-lang 4.0.0
  └─ builtins call the same nodus-* library instances the runtime uses
  └─ circuit breaker, retry, effects, identity, syscall, memory — all shared
```

---

## Phase 0 — Foundation: nodus-lang Version Upgrade

**Scope:** One line change in aindy-runtime/pyproject.toml.

```
nodus-lang==3.0.2  →  nodus-lang==4.0.0
```

**Unlocks immediately in Nodus scripts:**
- `cb_create()` / `cb_call()` — circuit breaker as a native builtin
- Effect store / exactly-once semantics — retry with idempotency gate
- `identity.session_id()`, `identity.trace_id()`, `identity.execution_unit_id()`
- `sys.v1.*` dispatch builtin — direct syscall calls from .nd scripts
- Memory namespace builtins — `memory.ns("myapp").put()`, `memory.ns("myapp").get()`

**Testing required:** NodusWorker and NodusRuntimeAdapter compatibility verification.
Bytecode format changed (BYTECODE_VERSION 4) — compiled caches from 3.0.2 need clearing.
DeferredMemoryBuiltins injection pattern needs re-verification against 4.0.0 builtin
registration API.

**Risk:** Low. 3.0.2 → 4.0.0 is additive. No removed APIs. WorkerWaitSignal
exception pattern is unchanged.

---

## Phase 1 — Library Convergence: Runtime Uses Its Own Extractions

**Scope:** Replace 9 internal Python implementations in aindy-runtime with the libraries
it originally created. Add them as declared dependencies.

### 1A — Circuit Breaker
- **Replace:** `AINDY/kernel/circuit_breaker.py`
- **With:** `nodus-circuit-breaker`
- **Effect:** Circuit breaker behavior identical in Nodus scripts and runtime's own execution path

### 1B — Retry / Effect Store
- **Replace:** `AINDY/core/retry_policy.py` + `AINDY/db/models/effect_record.py`
- **With:** `nodus-retry` (RetryPolicy, InMemoryEffectStore → DB-backed in production)
- **Effect:** `SyscallDispatcher` idempotency gate and Nodus `effects.exactly_once()` share the same logic

### 1C — Event Bus
- **Replace:** `AINDY/kernel/event_bus.py`
- **With:** `nodus-events`
- **Effect:** Makes Phase 2's `event.on()` Nodus builtin viable — subscribes to the same bus the runtime uses

### 1D — Auth Service
- **Replace:** `AINDY/services/auth_service.py`
- **With:** `nodus-auth`
- **Effect:** JWT signing, bcrypt, API-key validation from a single source

### 1E — Observability Layer
- **Replace:** `AINDY/platform_layer/otel.py` + `AINDY/platform_layer/metrics.py`
- **With:** `nodus-observability` + `nodus-observability-framework`
- **Effect:** `init_otel()`, `create_registry()`, `configure_logging()` become library calls

### 1F — State Machine
- **Replace:** `ExecutionUnit.status` transition logic scattered across `AINDY/core/`, `AINDY/agents/`, `AINDY/runtime/flow_engine/`
- **With:** `nodus-state` (FlowStatus, UnitStatus, AgentStatus, WaitCondition, ResumeSpec)
- **Effect:** State transitions are testable in isolation; same state model available in Nodus scripts

### 1G — Schema / Protocol Envelopes
- **Replace:** Inline syscall envelope construction in `SyscallDispatcher` + Pydantic schemas in `AINDY/schemas/`
- **With:** `nodus-schema` (validation) + `nodus-protocol` (request/response envelopes)
- **Effect:** Envelope format Nodus scripts receive matches the format defined in the protocol library

### 1H — Agent Coordinator (alignment pass required)
- **Situation:** Runtime has `AINDY/agents/agent_coordinator.py`. `nodus-a2a` is an
  independently designed abstraction — NOT an extraction. They solve the same problem
  differently.
- **What nodus-a2a adds:** `AgentRegistry`, `AgentCoordinator` (local/delegate modes),
  `DelegationRequest`, `DeadLetterService`, `StuckRunWatchdog` — more explicit and
  complete than the runtime's inline version.
- **Action:** Evaluate both coordinators side by side, align the interface, then adopt
  nodus-a2a as the shared implementation. This is a deliberate design decision, not
  a drop-in swap.
- **Must happen before Phase 2:** event subscription and agent execution builtins need
  a stable coordinator underneath.

### 1X — nodus-mcp Integration (additive, no prior impl to replace)
- **Situation:** The runtime has no MCP implementation. nodus-mcp is a completely new
  capability — original design, not extracted from anything.
- **What it adds:**
  - Any `.nd` script can call external MCP servers as tools via the ToolRegistry +
    SyscallDispatcher path
  - aindy-runtime can expose itself as an MCP server — `sys.v1.*` syscalls become MCP
    tools callable by any MCP-compatible client
  - The AINDY agent loop gets access to the MCP tool ecosystem without custom adapters
- **Sequencing:** After Phase 1 core re-integration is stable. Can run alongside Phase 3.

**After Phase 1:** aindy-runtime's pyproject.toml declares ~10 nodus-* libraries.
The `AINDY/` package shrinks — every extracted module either deletes or becomes a
thin wrapper. Runtime and Nodus builtins share actual code, not parallel copies.

---

## Phase 2 — Nodus Layer Expansion: Full Runtime Surface in .nd Files

**Scope:** Expand what Nodus scripts can call. Currently `DeferredMemoryBuiltins`
exposes 3 operations. After this phase the entire runtime surface is callable.

### 2A — Named Syscall Builtins

```nodus
flow.run("task_pipeline", {task_id: "abc"})
task.create({title: "Review", deps: ["task-1"]})
agent.execute("analyst", {objective: "score Q3 metrics"})
event.emit("task.completed", {task_id: "abc"})
memory.write("Q3 analysis complete", tags=["analytics", "q3"])
memory.recall(tags=["q3"], limit=10)
```

Each maps to the corresponding `sys.v1.*` syscall through `NodusRuntimeAdapter`.
Capability gate enforced at the dispatcher.

### 2B — Event Subscription Primitive

The most impactful new primitive. Enables reactive Nodus scripts.

```nodus
event.on("task.completed", fn(payload) {
    let task_id = payload["task_id"]
    memory.write("task \(task_id) completed", tags=["audit"])
})
```

Implementation: `event.on()` registers a Nodus function as a handler in the nodus-events
EventBus (Phase 1C). When the event fires, NodusWorker invokes the handler in a new
coroutine. WorkerWaitSignal pattern extended to support subscription.

### 2C — Context Primitive

```nodus
let ctx = context.current()
# ctx.user_id, ctx.trace_id, ctx.execution_unit_id, ctx.capabilities
context.assert_capability("memory.write")
```

### 2D — Expanded Memory Surface

```nodus
memory.link(from_id, to_id, relationship="caused_by")
memory.score(node_id, feedback={success: true, delta: 0.1})
memory.address("/memory/user123/decisions/2026/q3")
memory.forget(node_id)
memory.tag(node_id, tags=["reviewed"])
```

---

## Phase 3 — Language Primitives: New .nd Authoring Capabilities

### 3A — Flow Definition DSL

```nodus
flow "task_pipeline" {
    node "validate" {
        execute: fn(ctx) { validate_task(ctx["task_id"]) }
        on_success: "execute"
        on_error: "fail"
    }
    node "execute" {
        execute: fn(ctx) { run_task(ctx["task_id"]) }
        on_success: wait("task.completed")
    }
    node "finalize" {
        execute: fn(ctx) { memory.write("Task \(ctx["task_id"]) done") }
        on_success: "complete"
    }
}
```

Compiles to same Python dict structure that `flow_definitions.py` currently hand-writes.
Registered at boot via script registry (Phase 3D).

### 3B — Agent Definition Primitive

```nodus
agent "analyst" {
    tools: ["memory.recall", "analytics.score", "search.execute"]
    capabilities: ["memory.read", "analytics.read"]
    behavior: fn(objective, context) {
        let memories = memory.recall(tags=["analytics"], limit=5)
        let score = analytics.score({data: memories, objective: objective})
        memory.write("Analysis: \(score)", tags=["analysis", "result"])
        score
    }
}
```

### 3C — Prompt / Template Module

```nodus
import "std:prompt" as p

let rendered = p.render("
    You are analyzing {{objective}}.
    Relevant context:
    {{each memory in context}}
      - {{memory.content}}
    {{end}}
", {objective: obj, context: memories})

let result = llm.complete(rendered)
```

### 3D — Script Boot Registry

Nodus scripts declared in `aindy_plugins.json` discovered, validated, and registered
at boot — same as Python flows, syscalls, and jobs today.

```json
{
  "nodus_scripts": [
    {
      "name": "automation.infinity_loop",
      "file": "apps/automation/loops/default.nd",
      "trigger": "boot",
      "capabilities": ["memory.read", "memory.write", "event.emit"]
    },
    {
      "name": "analytics.kpi_score",
      "file": "apps/analytics/score.nd",
      "trigger": "cron:0 * * * *"
    },
    {
      "name": "rippletrace.causal_engine",
      "file": "apps/rippletrace/causal.nd",
      "trigger": "event:memory.written"
    }
  ]
}
```

`startup.py` gets a new step: `register_nodus_scripts()`.

### 3E — Cross-Invocation State Store

```nodus
state.set("automation.cursor", last_processed_id)
let cursor = state.get("automation.cursor") ?? "0"
```

Backed by runtime DB (`nodus_script_state` table). Scoped to `(script_name, user_id)`.
Enables automation scripts to maintain position across restarts without polluting memory.

### 3F — Plugin Invocation

```nodus
let plugins = plugin.list()
let result = plugin.call("arm.analyze", {code: source_code, depth: "full"})
```

Routes through `PluginHost` with the script's capability context.

---

## Phase 4 — First Migrations: High-Value Python → .nd

### 4A — Automation Flow Definitions
- **Current:** `apps/automation/flows/flow_definitions.py` — Python dicts
- **After:** `apps/automation/flows/*.nd` — Nodus flow blocks compiled at boot
- **Change:** Python file deletes; NodusFlowCompiler produces same FLOW_REGISTRY entries

### 4B — Infinity Loop Coroutines
- **Current:** `apps/automation/infinity_loop.py` — Python class
- **After:** `apps/automation/loops/default.nd` — Nodus coroutine with spawn + sleep
- **Change:** Python class deletes; registers via script boot registry with `trigger: "boot"`

### 4C — Rippletrace Scoring Engines
- **Current:** `apps/rippletrace/services/causal_engine.py`, `delta_engine.py`, `prediction_engine.py`
- **After:** `apps/rippletrace/causal.nd`, `delta.nd`, `predict.nd`
- **Change:** Scoring weights become Nodus `let` constants; Python services become thin call wrappers

### 4D — Masterplan Goal Ranking
- **Current:** `apps/masterplan/agents/ranking.py`
- **After:** `apps/masterplan/ranking.nd`
- **Change:** Ranking algorithm in Nodus; begins convergence of masterplan Goal DSL with Nodus native Goal DSL

### 4E — Analytics KPI Formulas
- **Current:** `apps/analytics/calculation.py`
- **After:** `apps/analytics/kpi.nd`
- **Change:** Data fetched by Python service, injected as script input; formula runs in Nodus

---

## Phase 5 — Full App Layer: Python as Wiring, .nd as Logic

### What Python retains permanently in every app

```
apps/{domain}/
  ├── models/          ← SQLAlchemy ORM
  ├── routes/          ← FastAPI route handlers
  ├── bootstrap.py     ← Registration (models, routers, flows, jobs)
  ├── migrations/      ← Alembic
  └── syscalls/        ← Thin wrappers calling .nd scripts
```

### What moves to .nd files

```
apps/{domain}/scripts/
  ├── flows.nd         ← Flow DAG definitions
  ├── agents.nd        ← Agent behavior definitions
  ├── automation.nd    ← Automation chains and loops
  ├── scoring.nd       ← Scoring and ranking formulas
  ├── prompts.nd       ← LLM prompt templates and pipelines
  └── rules.nd         ← Business rules and policy evaluations
```

### Per-app migration scope

| App | What Migrates to .nd | What Stays Python |
|-----|---------------------|-------------------|
| automation | infinity loops, flow definitions, trigger evaluators | models, routes, bootstrap |
| masterplan | goal ranking, success metric evaluation, state transitions | models, routes, goal persistence |
| rippletrace | causal/delta/prediction/narrative engines | models, routes, DB queries |
| analytics | KPI formulas, scoring snapshots, batch calculations | models, routes, DB queries |
| arm | DeepSeek prompt pipeline, response parsing | models, routes, API key handling |
| search | leadgen scoring, research relevance, result ranking | models, routes, external API calls |
| agent | behavior scripts, planning loop, tool selection | models, routes, CapabilityToken minting |
| tasks | dependency resolution, orchestration conditions | models, routes, persistence |
| bridge | already using Nodus (memory.nodus.execute) | models, routes |
| freelance | payment workflow state machine, delivery generation | models, routes, Stripe webhooks |
| social | rate calculation formulas | models, routes |

---

## Phase 6 — User Surface: .nd Files as Product Feature

Infrastructure already complete:
- `/platform/nodus/` HTTP routes exist
- `nodus_scheduled_jobs` table persists cron scripts
- `nodus_trace_events` table captures execution history
- `NodusSecurityService` sandboxes script execution
- `nodus_script_store.py` manages script CRUD

Needed at product layer:
- React UI in `client/` for script editing (Monaco editor + .nd syntax highlighting)
- Script templates for common patterns
- Execution history viewer (queries `nodus_trace_events`)
- Capability selector (shows what syscalls the script can use)
- Scheduled script manager (CRUD over `nodus_scheduled_jobs`)

---

## Phase Summary

| Phase | Runtime | Language | Apps | Libraries |
|-------|---------|----------|------|-----------|
| 0 | nodus-lang pin → 4.0.0 | 4.0 builtins available | no change | no change |
| 1 | Internal impls → libraries; pyproject gains 10 deps | shared instances with runtime | no change | no longer orphaned |
| 1H | agent_coordinator.py → nodus-a2a (alignment pass) | — | — | nodus-a2a adopted |
| 1X | MCP server + client added (additive) | — | — | nodus-mcp integrated |
| 2 | DeferredMemoryBuiltins → full sys.v1.*; event.on() wired | new primitives accessible | scripts can do more | event bus shared |
| 3 | Script boot registry in startup.py; state store table | flow DSL, agent DSL, prompt, plugin | aindy_plugins.json gains nodus_scripts | — |
| 4 | — | — | first .nd files; 5 Python services delete | — |
| 5 | — | — | ~20 Python logic files → .nd; Python = wiring only | — |
| 6 | — | — | React UI; users author scripts | — |

---

## What Never Moves to Nodus

These stay Python permanently:

- PostgreSQL + pgvector persistence
- Alembic migrations
- SQLAlchemy ORM models
- FastAPI route handlers
- JWT signing and bcrypt
- OTel span management
- PluginHost sandbox process management
- SyscallDispatcher enforcement gate (the security boundary)
- Redis EventBus infrastructure
- APScheduler clock management
- Bootstrap registration and startup sequencing

Everything else is logic. Logic belongs in Nodus.
