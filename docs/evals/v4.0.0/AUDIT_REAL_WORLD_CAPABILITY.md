# Real-World Capability Audit — Nodus 4.0.0

**Version:** 4.0.0
**Date:** 2026-06-08
**Auditor:** Claude Sonnet 4.6
**Prompt:** `docs/governance/AUDIT_REAL_WORLD_CAPABILITY.md`

---

## Section 1 — Capability Inventory

### Execution

| Capability | Status | Notes |
|-----------|--------|-------|
| Synchronous script execution | ✅ Complete | `nodus run`, `NodusRuntime.run_source()` |
| Coroutines / cooperative async | ✅ Complete | `spawn()`, `coroutine()`, fair scheduler |
| Channels (CSP-style) | ✅ Complete | `channel()`, `send()`, `recv()`, `close()` |
| Per-coroutine timeout | ✅ Complete | `coroutine_timeout_ms` on `NodusRuntime` |
| Parallel execution | ✅ Complete | `async.parallel()`, `async.worker_pool()` |
| Pipeline execution | ✅ Complete | `async.pipeline()` — channel-coupled stage graph |
| REPL | ✅ Complete | `nodus repl` with history |
| Bytecode compilation cache | ✅ Complete | `.nodus/cache/`, SHA-256 keyed |

### Orchestration Primitives

| Capability | Status | Notes |
|-----------|--------|-------|
| Workflow DSL | ✅ Complete | `workflow`, `step`, `after`, `checkpoint`, resume |
| 7-state lifecycle | ✅ Complete | pending → running → waiting → retry_scheduled → completed/failed/dead_lettered |
| Goal DSL | ✅ Complete | `goal`, `try_action`, `success_when`, `fallback` |
| Task graph (DAG) | ✅ Complete | `graph()`, `task()` with dependency tracking |
| Workflow wait-for-event | ✅ Complete | `workflow_wait(event_type, correlation_key)` |
| Workflow resume from checkpoint | ✅ Complete | `resume_workflow(id, checkpoint, payload)` |
| Workflow dead-letter handling | ✅ Complete | Dead-letter queue with replay |
| Graph plan (dry run) | ✅ Complete | `plan_graph()`, `plan_workflow()` |

### Networking

| Capability | Status | Notes |
|-----------|--------|-------|
| HTTP client (all verbs) | ✅ Complete | GET, POST, PUT, DELETE, PATCH, HEAD, OPTIONS |
| HTTP streaming (chunked) | ✅ Complete | `http_get_stream()` → channel of chunks |
| SSE (Server-Sent Events) | ✅ Complete | `http_get_sse()` → channel of events |
| Async HTTP | ✅ Complete | `http_get_async()` etc. — non-blocking |
| Custom headers, auth, timeout | ✅ Complete | Options record on all requests |
| Host allowlist enforcement | ✅ Complete | `allowed_hosts` on `NodusRuntime` |
| HTTP server | ✅ Complete | `nodus serve` — 20+ endpoints |

### Filesystem and Subprocess

| Capability | Status | Notes |
|-----------|--------|-------|
| File read/write/append | ✅ Complete | `std:fs` — `read`, `write`, `append`, `delete` |
| Directory operations | ✅ Complete | `listdir`, `mkdir`, `exists` |
| Path manipulation | ✅ Complete | `std:path` — join, dirname, basename, etc. |
| Subprocess (sync) | ✅ Complete | `std:subprocess` — argv or shell, stdin/stdout/stderr |
| Subprocess (async, streaming) | ✅ Complete | `subprocess_run_async()`, channel-pumped streams |
| Environment access | ✅ Complete | `std:env` — gated by `allow_env` flag |
| Path sandbox enforcement | ✅ Complete | `allowed_paths` on CLI and `NodusRuntime` |

### Module and Package System

| Capability | Status | Notes |
|-----------|--------|-------|
| Standard library imports | ✅ Complete | `import "std:http"`, `std:fs`, `std:json`, etc. (25+ modules) |
| Third-party package loading | ✅ Complete | Entry-point contract via `nodus.nd` group |
| Module aliasing | ✅ Complete | `import "std:http" as http` |
| Host function injection | ✅ Complete | `NodusRuntime.register_function()` |
| Bytecode REPL | ✅ Complete | Incremental compile in repl mode |

### Memory and State

| Capability | Status | Notes |
|-----------|--------|-------|
| In-process memory store | ✅ Complete | `memory_put/get/delete/keys/has` |
| Namespaced memory (server) | ✅ Complete | Per-session and shared namespaces |
| Cross-execution state | ⚠️ Partial | In-process only; lost on restart |
| Persistent state | ✅ Via ecosystem | `nodus-store-sql` (RunStore, EventStore, JobStore) |

### Observability

| Capability | Status | Notes |
|-----------|--------|-------|
| Execution event bus | ✅ Complete | `RuntimeEventBus`, 13+ event types |
| Event sinks (embedder) | ✅ Complete | `event_sinks` on `NodusRuntime` |
| Instruction-level trace | ✅ Complete | `--trace`, `--trace-filter`, `--trace-limit` |
| Event stream trace | ✅ Complete | `--trace-events`, `--trace-file` |
| Profiler | ✅ Complete | `--profile` — opcode counts, function call times, hot spots |
| Capability audit events | ✅ Complete | `capability_use` events for http, subprocess, fs |
| Server events endpoint | ✅ Complete | `GET /runtime/events` |
| Scheduler stats | ✅ Complete | `runtime.scheduler()` from within scripts |
| Stack inspection | ✅ Complete | `runtime.stack_frame(i)`, `runtime.stack_depth()` |

### Plugin and Extension

| Capability | Status | Notes |
|-----------|--------|-------|
| Extension registry | ✅ Complete | `nodus-extension` — `ExtensionRegistry`, `ExtensionHost` |
| Subprocess sandbox tier | ✅ Complete | Extensions run in subprocess with capability gates |
| Extension language bindings | ✅ Complete | `import "nodus-extension"` — ext_load, ext_invoke |
| OCI/VM isolation tier | ❌ Not yet | Deferred to nodus-extension v0.2 |

### Worker and Distributed Execution

| Capability | Status | Notes |
|-----------|--------|-------|
| Worker registration | ✅ Complete | `POST /worker/register` with capability declaration |
| Capability-based job routing | ✅ Complete | WorkerManager routes jobs by capability |
| Worker heartbeat / expiry | ✅ Complete | Configurable timeout, dead-worker detection |
| Job result submission | ✅ Complete | `POST /worker/result` |
| Distributed queue (durable) | ✅ Via ecosystem | `nodus-queue` (Redis-backed, tenacity retry) |

### Embedding and Host Integration

| Capability | Status | Notes |
|-----------|--------|-------|
| Embedded runtime | ✅ Complete | `NodusRuntime` — full lifecycle control |
| Host function registration | ✅ Complete | `register_function(name, fn, arity=)` |
| Capability sandbox | ✅ Complete | `allow_network`, `allowed_paths`, `allowed_hosts`, `allowed_commands`, `allow_env` |
| Execution stats | ✅ Complete | `get_execution_stats()` — coroutines, steps, timeouts |
| MCP protocol (companion) | ✅ Complete | `nodus-mcp` v0.1.0 — full MCP server/client |
| Agent coordination (companion) | ✅ Complete | `nodus-a2a` v0.1.0 — AgentCoordinator, delegation |
| FastAPI integration | ✅ Via ecosystem | `nodus-sdk` — `create_nodus_router()`, middleware |

---

## Section 2 — Application Category Classification

### A — READY NOW

**Automation scripts and pipelines**
Every primitive is present: subprocess with streaming I/O, filesystem ops, HTTP
client, JSON, environment access, conditional retry (circuit breaker, retry module),
and the workflow DSL to compose multi-step pipelines with checkpoints and resume.
A CI/CD step runner, a data processing pipeline, a file-watching automation daemon —
all buildable today without reaching outside the stdlib.

**Workflow orchestration engines**
The workflow DSL is not a wrapper around another engine — it is the engine. Steps
declare dependencies with `after`, produce checkpoints, wait for external events,
resume from dead-letter queues, and execute across a 7-state lifecycle backed by
either file or SQLite storage. This is a production-quality orchestration substrate.

**Task graph runners (DAG execution)**
`graph()` + `task()` + dependency declarations produce a DAG. `plan_graph()` gives
a dry-run without execution. `run_graph()` executes with the coroutine scheduler.
Buildable: ETL runners, build systems, test harnesses with parallel steps.

**Embedded scripting platforms**
`NodusRuntime` with `register_function()` lets a Python host expose arbitrary
capabilities into the script VM while enforcing what the script can reach (paths,
hosts, commands). The event sink API gives the host a live feed of what the script
did. This is a complete embedded scripting contract.

**AI / LLM orchestration**
Tool registration (`std:tool`) is a first-class primitive, not a library pattern.
`tool.register({name: "myapp.call_llm", ...})` makes a host function callable
from any script or workflow. `nodus-mcp` adds the MCP protocol layer. `nodus-a2a`
adds agent-to-agent delegation. `nodus-llm` wraps OpenAI/Anthropic. The combination
produces an AI orchestration runtime where workflows drive LLM calls as tools and
agents coordinate via structured protocols. This is the strongest application category
in the ecosystem today.

**CLI tools**
`nodus run script.nd` + stdin/stdout + subprocess + JSON + HTTP is a full CLI
toolchain. For distribution, `NodusRuntime` embedded in a Python CLI package gives
users a scripting surface without installing Nodus separately.

**Async services (embedded)**
Coroutines, channels, `async.worker_pool()`, and `async.pipeline()` form a complete
async service substrate. An embedded runtime with a worker pool that drains a channel
of incoming jobs — fully expressible today.

**Goal-oriented execution engines**
The goal DSL is unique: declare a goal, define `try_action` blocks and a `success_when`
condition, and let the runtime plan and execute actions until the goal is achieved or
fallback paths are exhausted. Buildable: self-healing automation, multi-step AI task
execution, conditional workflow orchestration.

**Observability and trace tools**
`--trace-events` + `--trace-file` + capability_use events give machine-readable
visibility into exactly what a script did: which HTTP calls were made, which files
were touched, which subprocesses were run, and where it failed. Buildable: audit
loggers, security analyzers, execution replayers, test coverage tools.

---

### B — NEAR-TERM

**Production HTTP APIs**
`nodus serve` runs a functional HTTP server with 20+ endpoints. It is single-process
and not hardened for production traffic. `nodus-router`, `nodus-gateway`, and
`nodus-session` are on PyPI and add routing, auth, and session management. The
remaining gap is deployment tooling: no WSGI/ASGI integration, no process manager
configuration. A production API needs those wired together — achievable in weeks, not
months.

**Distributed task runners (durable)**
The WorkerManager handles capability-based routing and heartbeat expiry. `nodus-queue`
adds Redis-backed durable queues. What's missing is end-to-end documentation and a
reference implementation showing workers registering, polling, and reporting results
across processes. The substrate is complete; the "kit" is not.

**Event-driven systems**
`nodus-events` (PyPI) provides Redis-backed event sourcing. `workflow_wait()` lets
a workflow pause for an external event. These two compose into an event-driven system.
The gap is that `workflow_wait()` is wired to the in-tree workflow runner; bridging it
to `nodus-events` requires integration work that hasn't been written.

**Plugin ecosystems**
`nodus-extension` provides subprocess-sandboxed plugins with capability gates today.
What's missing for a credible plugin ecosystem: a registry (where do you find
extensions?), a versioning protocol, and the OCI/VM isolation tier for untrusted
third-party code. The subprocess tier is sufficient for trusted plugins.

**Recursive / adaptive workflows**
The architecture supports it — a workflow step can call `run_workflow()` with a
dynamically-determined workflow name. The goal DSL can run multiple action cycles.
What's missing is documentation and patterns for this mode. It's a capability, not
a feature.

**AI agent platforms**
`nodus-mcp` + `nodus-a2a` + `nodus-memory` + `nodus-llm` + the goal DSL is a
complete architecture for an AI agent platform. The gap: these packages have been
prepared but not published together as an integrated stack. The integration layer
(wiring them to a single `NodusRuntime` via `nodus-sdk`) is where work remains.

---

### C — LONG-TERM

**Database-backed applications**
`nodus-store-sql` provides `RunStore`, `EventStore`, and `JobStore`. These are
operational primitives, not a general ORM. There is no query DSL, no migration
tooling, no relationship modeling. A database-backed CRUD application would require
writing raw SQLAlchemy from Python host functions. Buildable in principle; painful
in practice until a higher-level database layer exists.

**Large-scale distributed systems**
No consensus protocol, no distributed locking, no partition tolerance, no
leader election. The WorkerManager is in-process and single-coordinator. Scaling
beyond a single nodus-serve instance requires infrastructure the ecosystem does
not provide.

**Stream processing at scale**
Channels work for in-process pipelines. SSE and HTTP streaming work for consuming
external streams. There is no Kafka-compatible consumer, no backpressure signaling
beyond channel blocking, no partition model. Suitable for low-to-moderate volume
processing tasks; not suitable for high-throughput stream processing.

---

### D — NOT REALISTIC

**GUI applications**
No rendering model, no widget system, no event loop integration with native UI
frameworks. Not an architectural gap — simply outside the execution model.

**High-performance numerical / scientific computing**
No SIMD, no vectorized operations, no NumPy compatibility, no GPU execution.
The VM is a coroutine scheduler, not a compute substrate.

**Systems programming**
No manual memory management, no zero-copy I/O, no FFI, no POSIX syscall access
below subprocess. The language has no type system strong enough for systems
programming patterns.

**Mobile applications**
No iOS/Android runtime bridge, no UI toolkit integration.

**Browser execution**
No WebAssembly target.

---

## Section 3 — Showcase Project Analysis

### 1. AI Orchestration Engine

**Why it fits:** The goal DSL + tool registration + workflow steps is an AI
orchestration architecture built into the language. Declaring tools with typed
schemas, wiring LLM calls as workflow steps, handling retry on tool failure, waiting
for external events — all of this is native syntax, not library calls.

**What it demonstrates:**
- Goal DSL: define success condition, let runtime plan action sequence
- `std:tool`: register LLM call as a first-class callable tool
- `nodus-mcp`: expose tools over the MCP protocol to any MCP client
- Workflow checkpoints: resume long-running LLM pipelines after failure
- `coroutine_timeout_ms`: bound runaway LLM calls

**Ecosystem credibility:** Proves `nodus-mcp`, `nodus-llm`, `nodus-memory`, and
the goal DSL are production-wired, not just designed.

**Feasibility:** 2–3 days for a credible demo; 1–2 weeks for a production-hardened
system.

---

### 2. Distributed Workflow Runner

**Why it fits:** The workflow engine is not simulated — it runs against real state
(SQLite or file backend), handles dead letters, replays failures, and coordinates
across workers via the WorkerManager protocol. This is a real distributed workflow
substrate.

**What it demonstrates:**
- Workflow 7-state lifecycle end-to-end
- WorkerManager: multi-process job dispatch by capability
- `nodus-queue`: durable job queue underneath
- `nodus-store-sql`: persistent run records
- `GET /workflow/runs` + dead-letter queue: operational visibility

**Ecosystem credibility:** Proves the workflow engine is production-grade, not a toy.

**Feasibility:** 3–5 days with existing infrastructure; most code already exists.

---

### 3. Automation Platform (scripts + plugins + HTTP)

**Why it fits:** The combination of subprocess, filesystem, HTTP client, sandboxing,
and the extension system is exactly what an automation platform requires. Scripts can
be sandboxed to specific paths and hosts, extensions can be loaded from a registry,
and the whole thing runs through `NodusRuntime` embedded in a Python host.

**What it demonstrates:**
- `NodusRuntime` embedding with per-run capability gating
- `nodus-extension`: plugin loading and invocation
- Subprocess streaming: run system commands with live output
- `--trace-events`: full audit log of what each script did

**Ecosystem credibility:** Proves the sandbox model and extension system are
coherent, not just documented.

**Feasibility:** 1–2 weeks for a credible platform demo.

---

### 4. Agent Coordination System

**Why it fits:** `nodus-a2a` provides `AgentCoordinator` with local and delegate
dispatch modes, `DeadLetterService`, and `StuckRunWatchdog`. The `goal` DSL
coordinates multiple agents toward a shared success condition. `agent_call()` is a
native builtin.

**What it demonstrates:**
- Multi-agent goal execution via goal DSL
- `nodus-a2a`: inter-agent delegation and coordination
- Dead-letter handling for stuck agents
- `nodus-memory`: shared state between agent runs

**Ecosystem credibility:** Proves the A2A layer is more than a spec.

**Feasibility:** 2–3 days for a 2-3 agent demo scenario.

---

### 5. Embedded Scripting SDK (developer tool)

**Why it fits:** `NodusRuntime` is a complete embedded scripting contract — not a
prototype. Host function registration, event sinks, capability sandbox, execution
stats, per-coroutine timeouts. This is demonstrably better than embedding Lua or
writing a custom expression evaluator.

**What it demonstrates:**
- Developer UX: one import, one constructor, run scripts safely
- Event sinks: live observability without modifying scripts
- `allowed_paths` + `allowed_hosts`: capability-gated sandboxing
- `get_execution_stats()`: runtime telemetry for the host

**Ecosystem credibility:** Proves the embedding story is production-ready.

**Feasibility:** The SDK exists; the showcase is documentation + example projects.

---

## Section 4 — Architectural Advantages

**Orchestration-native language semantics**
`workflow`, `step`, `after`, `checkpoint`, `goal`, `try_action`, `success_when` are
language keywords, not library calls. You cannot accidentally use them incorrectly
at the type level. An Airflow or Temporal user expresses orchestration in Python
decorator patterns that are trivially misused. In Nodus these patterns have static
semantics.

**Goal DSL**
No mainstream language runtime has a `goal` keyword. The goal DSL lets a program
declare a success condition and a set of actions; the runtime iterates until the
goal is achieved or fallback paths are exhausted. This is architecturally distinct
from both workflow engines and agent frameworks.

**Capability-gated embedding**
`NodusRuntime(allowed_paths=[...], allowed_hosts=[...], allowed_commands=[...])` is
a sandbox with a typed contract — not a best-effort restriction. A host application
can embed untrusted scripts and guarantee they cannot reach outside declared
capability bounds. This is structurally superior to subprocess isolation (which is
heavy) and eval-based sandboxing (which is leaky).

**Unified event model**
Every execution produces a `capability_use` event for each resource it touches.
An embedder with an event sink has a complete audit trail of what a script did —
which URLs it fetched, which files it read, which commands it ran — without
instrumenting the script. This is an observability primitive most runtimes do not
have.

**Coroutine + channel concurrency without callbacks**
`spawn(coroutine(fn() { ... }))` + `send(ch, value)` + `recv(ch)` is a clean
concurrent execution model with no callback pyramid, no async/await proliferation,
and no shared mutable state by default. Worker pools and pipelines are expressible
in under 20 lines of Nodus.

**Tool registration as a first-class primitive**
`tool.register({name: "myapp.action", fn: handler, schema: {...}})` makes a typed
callable available to any script or workflow step. This is the substrate for
AI/agent systems where tools are the interface between language and capability.
Most runtimes bolt this on as a framework pattern; in Nodus it is built-in.

---

## Section 5 — Weaknesses and Limits

**No persistent execution memory (structural)**
As documented in `AUDIT_INFINITY_RUNTIME.md`: runs leave no trace once the VM is
collected. There is no run_id, no execution record, no recall. This is not an
ecosystem gap — it is an unimplemented runtime feature.

**Single-coordinator distributed model**
WorkerManager is an in-process coordinator. There is no way to run two `nodus serve`
instances that share a job queue without external infrastructure. This caps the
distributed execution model at one coordinator.

**HTTP server is not production-hardened**
`nodus serve` is a development server. It has no TLS termination, no connection
pooling, no rate limiting, no graceful shutdown guarantees. For production traffic
it requires a reverse proxy and process manager integration that are not documented.

**No type system beyond runtime checks**
Nodus has runtime type errors but no static type checker. Large systems built in
Nodus lack the refactoring safety that typed languages provide. This is a language
design decision, not an oversight, but it limits the size of Nodus programs that
can be maintained without external tooling.

**Closure upvalue mutation (DESIGN-006)**
`let` variables cannot be mutated from closures. The workaround (map with quoted
keys) is functional but unintuitive. This is a known limitation deferred to v5.0.

**No standard I/O format for CLI output**
There is no structured output primitive for CLI tools — no `--json` flag convention,
no output serialization protocol. Scripts that want machine-readable output must
build it themselves with `std:json`.

---

## Section 6 — Ecosystem Gap Analysis

| Gap | Severity | Notes |
|-----|----------|-------|
| No run_id / execution record persistence | **HIGH** | Blocks recall, scoring, debugging across runs. Substrate exists (nodus-store-sql). |
| HTTP server not production-hardened | **HIGH** | Blocks building public-facing APIs on nodus serve directly. |
| No database query DSL | **HIGH** | nodus-store-sql is operational primitives only. General persistence requires host-side Python. |
| nodus-mcp / nodus-memory / nodus-sdk not integrated end-to-end | **MEDIUM** | Packages are complete but the wiring example (run nodus-sdk with mcp+memory+llm) doesn't exist yet. |
| nodus-extension OCI/VM sandbox tier missing | **MEDIUM** | Subprocess tier works for trusted plugins; untrusted third-party code needs OCI isolation (v0.2). |
| No migration / deployment tooling | **MEDIUM** | No documented pattern for deploying a nodus serve instance to production. |
| No structured CLI output convention | **LOW** | Scripts can use std:json; convention just isn't established. |
| Closure upvalue mutation (DESIGN-006) | **LOW** | Workaround via maps is functional; affects ergonomics, not capability. |
| No static type checker | **LOW** | Runtime type errors surface correctly; checker would add refactoring safety. |

---

## Section 7 — Final Assessment

### What is Nodus best suited for today?

**Orchestration, automation, and AI/agent execution.**

Nodus has a production-quality workflow engine, a goal DSL unique among language
runtimes, tool registration as a built-in primitive, a complete embedded scripting
contract with capability sandboxing, and a coroutine+channel concurrency model
that expresses async work clearly. These capabilities converge on orchestration,
automation, and AI/agent coordination as the natural application domain.

A Nodus workflow that calls an LLM as a registered tool, waits for an external
event via `workflow_wait`, checkpoints its progress, and resumes after a dead-letter
— this is not a hacked-together system. It is the intended execution model.

### What is Nodus most likely to become strong at?

**AI-native orchestration infrastructure.**

The trajectory is visible in the architecture: goal DSL → goal-driven agent execution.
Tool registration → typed capability surfaces for LLM tool calls. MCP protocol support
→ interoperability with any MCP-compatible AI client. Agent coordination → multi-agent
systems. Persistent execution memory (the primary gap) → execution history that
informs future runs.

As AI-native orchestration infrastructure, Nodus has architectural properties
(sandbox, event model, goal DSL, checkpoint/resume) that frameworks like LangChain
or CrewAI provide through Python library patterns. Nodus provides them through
language semantics.

### What projects would most effectively validate Nodus publicly?

In priority order:

1. **AI Orchestration Engine** — demonstrates the goal DSL, tool registration, and
   `nodus-mcp` together. The most differentiated use case in the ecosystem.

2. **Embedded Scripting SDK showcase** — a Python library that uses `NodusRuntime`
   to let users write automation scripts safely. Demonstrates the sandbox model and
   embedding story to Python developers.

3. **Distributed Workflow Runner** — demonstrates the workflow engine end-to-end
   with WorkerManager, nodus-queue, and nodus-store-sql. Proves the system works
   beyond a single process.

4. **Agent Coordination System** — two or three agents coordinating via `nodus-a2a`
   and the goal DSL to complete a multi-step task. The most direct proof of the
   AI-native execution story.
