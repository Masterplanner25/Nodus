<!-- Reconciled 2026-05-29: nodus-a2a and nodus-mcp Tier 3 entries corrected to reflect v0.1 scope. Needs review before repo commit and push. -->

# Nodus — Library Ecosystem

**Status:** Architectural reference. Updated alongside major release cycles.
**Created:** 2026-05-25 (v4.0 cycle, Phase 0)
**Last reconciled:** 2026-05-30 (v4.0.0 — Phase 6 stdlib additions, nodus-sdk, nodus-store-sql)
**Companion to:** `docs/design/v4/00-phase-0-decisions.md`,
`docs/governance/V4_0_PLAN.md`, `docs/governance/STDLIB_PHILOSOPHY.md`
**Maintainer:** Shawn Knight (Masterplanner25)

> **Current state note (2026-05-30):** nodus-lang is at **4.0.0** (unpublished; awaiting
> coordinated launch with nodus-mcp 0.1.0). The standalone ecosystem now has 29 packages:
> 27 standalone Nodus packages + nodus-sdk v0.1.0 + nodus-store-sql v0.1.0. All packages
> have GitHub repos under Masterplanner25. For honest current-state per package:
> `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md`.

---

## Purpose

This document defines the architectural shape of the Nodus library ecosystem:
what lives in the bundled stdlib, what lives in the registry, what gets built
when, and — most importantly — what is explicitly NOT being pursued.

It exists because v4.0 establishes Nodus as an orchestration DSL with a real
library ecosystem, and that ecosystem needs durable architectural commitments.
Without them, the next surge of feature requests collapses the orchestration
DSL positioning into "another general-purpose language."

---

## Three-tier ecosystem

Libraries fall into three tiers based on what credibility they unlock and
where they live.

### Tier 1 — Bundled stdlib (shipped with the language)

Tier 1 libraries make the language credible as an orchestration DSL. They
ship with the `nodus-lang` PyPI package and are available without registry
installation.

**Implemented in v4.0 (prepared, not yet published):**

- `std:http` — HTTP client (sync + async, buffered + streaming)
- `std:env` — Environment variables
- `std:time` — Datetime, durations, timezones
- `std:hash` — Hashing (sha256, sha512, blake2b, legacy sha1/md5), HMAC,
  constant-time comparison
- `std:encoding` — base64, hex, URL encoding
- `std:secrets` — Cryptographically secure random for tokens
- `std:subprocess` — Process execution (no-shell default, with shell opt-in)
- `std:test` — Test framework (pytest/jest-equivalent scope)
- `std:tool` — Tool registry with library-side handler support (v4.1: gains
  `effects` validation and `returns_schema` contract enforcement)

**Added in v4.1 (AI-native primitives — Phase 6, prepared, not yet published):**

- `std:identity` — Execution identity: `trace_id()`, `session_id()`, `execution_unit_id()`.
  All three auto-propagate across module boundaries.
- `std:effects` — EXACTLY_ONCE idempotency: `resolve()`, `pending()`, `complete()`,
  `action_id()`, `store_size()`. Backed by `InMemoryEffectStore` (now a required dep via
  `nodus-retry`). Python host can inject a custom `EffectStore`.
- `std:sys` — Versioned syscall dispatch: `sys.call("sys.v1.domain.action", payload)`.
  Uniform envelope `{status, data, error, trace_id}`. Four built-in syscalls:
  `sys.v1.memory.{get,put,delete,recall_from}`.
- `std:memory` (extended) — Adds `recall_from(ns, key)`, `recall_all(ns)`,
  `share(ns, key, val)` to the existing KV surface. Namespace-scoped in-process storage.
- `std:retry` — Retry execution: `retry.call(func, {max_attempts, backoff_ms, ...})`.
  Optional dep (`nodus-retry`); returns dependency-error map when absent.
- `std:circuit_breaker` — Three-state circuit breaker: `cb.create/call/state/reset`.
  Optional dep (`nodus-circuit-breaker`); returns dependency-error map when absent.

**Previously implemented (in published 3.0.2):**

- `std:json` — JSON parsing and serialization
- `std:math` — Math operations (extended in v4.0 with `is_numeric`, `is_int`,
  `is_float`, `is_nan`, `is_inf`, `is_finite`, `nan`, `infinity`,
  `neg_infinity`)
- `std:strings` — String operations
- `std:collections` — Map/list operations
- `std:fs` — File system operations
- `std:path` — Path manipulation

**Tier 1 ceiling:** No general-purpose scripting expansion (regex, CSV, full
string library). These belong to the components Nodus orchestrates, not to
Nodus itself.

### Tier 2 — Infrastructure libraries (registry, post-v4.0)

Tier 2 libraries make Nodus operationally useful in production infrastructure
environments. They ship through the Nodus package registry, not bundled.

**Tracked for v5.0 milestone:**

- `nodus-queue` — Message queue abstraction (Redis, RabbitMQ, Kafka, in-memory
  fallback). Not a message broker — an orchestration abstraction over them.
- `nodus-container` — Container execution (Docker, Podman, sandbox workers).
  Aligns with execution isolation direction in the broader ecosystem.
- `nodus-observe` — Tracing, telemetry, metrics, event sourcing for workflows.
  Observability-first architecture as a first-class library.
- `nodus-runtime-introspection` — Runtime self-knowledge: list active
  workflows, tasks, memory, capabilities. The "Nodus understands itself"
  layer.
- `nodus-scheduler` — Cron/interval/calendar-based scheduling for workflows.
- `nodus-workers` — Worker pool management for distributed task execution.

The `std:secrets` namespace ships in Tier 1; an extended `nodus-secrets`
registry library MAY ship later for vault integration and scoped runtime
permissions. The Tier 1 namespace remains the API surface; the Tier 2 library
extends it.

### Tier 3 — AI / agent runtime libraries (registry, two ship with v4.0)

Tier 3 libraries make Nodus strategically unique. They expose orchestration-
native cognition and coordination primitives — not chat wrappers, not prompt
abstractions.

**Shipping with v4.0 launch (registry, parallel to PyPI release):**

- `nodus-mcp` — Model Context Protocol library. Bidirectional (client +
  server). **v0.1.0 scope:** stdio and HTTP transports; core MCP capabilities
  (Resources, Prompts, Tools, Sampling, Roots, Elicitation, Logging, Progress,
  Completion); bearer-token auth; spec target 2026-07-28 RC. **Deferred to
  v0.2+:** OAuth 2.0 / OIDC, Streamable HTTP transport, `resources/subscribe`
  server-push, server-initiated requests over HTTP. See Decision 16 in
  `docs/design/v4/00-phase-0-decisions.md` and `nodus-mcp/README.md` for
  current limitations.

- `nodus-a2a` — Agent2Agent Protocol library. **v0.1.0 scope:** HTTP+JSON/REST
  transport only; message-only (server never creates A2A Tasks — D5 decision);
  AgentCard discovery; DataPart-based tool dispatch; bearer-token auth. **Full
  A2A 1.0.0 spec coverage and multi-binding support are v0.2+ targets.**
  Deferred to v0.2+: Task lifecycle and state machine, SSE streaming, push
  notification webhooks, JSON-RPC binding, gRPC binding, OAuth/OIDC/mTLS,
  extended Agent Card, multi-part responses, tenant routing. See Decision 17 in
  `docs/design/v4/00-phase-0-decisions.md` and `nodus-a2a/README.md` for
  current limitations.

**Tracked for v5.0 milestone (post-v4.0 work):**

- `nodus-agent` — Runtime-native agent abstraction. Lifecycle, execution,
  state, capabilities, workflow participation, permissions. **Built:** v0.1.0 at
  `C:\dev\nodus-agent` (28 tests, CapabilityToken, LocalPlanner/LLMPlanner).
- `nodus-memory` — Memory primitives (store, search, link). **Built:** Tier 2
  implementation at `C:\dev\nodus-memory` (28 tests, InMemoryStore, MAS,
  EmbeddingProvider) + `nodus-native-memory-engine` (76 tests, PyO3/Maturin Rust).
- `nodus-tooling` — Tool schemas, capability declarations, syscall boundaries.
  **Partially covered** by `nodus-schema` (Group 3, 30 tests) and the HandlerContract
  infrastructure (Phase A-D in v4.0.0).
- `nodus-workflow-ai` — Workflow primitives for AI-driven planning. **Built:**
  in-tree `src/nodus_workflow/` (30 tests) + standalone `C:\dev\nodus-workflow`
  (17 tests, FlowDefinition, SchedulerEngine, FlowExecutor).

**Ecosystem SDK (v4.0.0, built alongside Phase 6):**

- `nodus-sdk v0.1.0` — Unified platform SDK at `C:\dev\nodus-sdk`. Single install story:
  `pip install nodus-sdk[agent,sql,fastapi]`. Provides `NodusSDKRuntime` (fluent
  `attach_*` API), `create_runtime()` factory with auto-wiring, and 9 bridge modules
  spanning the full 27-package ecosystem plus new Python bridges (SQLAlchemy, pgvector,
  APScheduler, webhook, FastAPI router). 99 tests.

- `nodus-store-sql v0.1.0` — SQLAlchemy 2.x persistence adapters at
  `C:\dev\nodus-store-sql`. Promoted from `packages/nodus-store-sql` incubator scaffold.
  Three stores: `RunStore` (optimistic locking), `EventStore` (append-only audit trail),
  `JobStore` (atomic claiming). Sync + async (`sqlalchemy.ext.asyncio`). 47 tests.
  Closes the last gap in both ecosystem audits.

---

## Architectural commitment: protocols are adapters

This is the single most important architectural commitment in the v4.0
ecosystem. It is what allows Nodus to participate in the agent ecosystem
without being captured by any one protocol.

### The principle

Nodus runtime primitives are the source of truth. Protocols (MCP, A2A,
future protocols) plug in as adapters against those primitives. Protocols
do NOT own the architecture.

```
Layer 1 — Nodus runtime primitives (owned by Nodus)
  - workflows
  - tasks
  - tools (via std:tool registry)
  - agents (via nodus-agent, post-v4.0)
  - memory (via nodus-memory, post-v4.0)
  - messaging (via nodus-agent's coordination layer, post-v4.0)

Layer 2 — Protocol adapters (owned by individual libraries)
  - nodus-mcp adapts MCP to Layer 1
  - nodus-a2a adapts A2A to Layer 1
  - future protocols add their own adapters
```

### Why this matters

If Nodus tightly couples to any single protocol:

- It inherits that protocol's instability
- It inherits that protocol's ecosystem politics
- It inherits that protocol's architectural assumptions
- It cannot easily swap to a successor protocol

If instead Nodus owns the orchestration primitives:

- Protocols become adapters that plug into Nodus's model
- MCP and A2A coexist without architectural tension
- Future protocols (whatever follows MCP and A2A) add a new adapter without
  changing Nodus's core
- Nodus's identity stays "orchestration DSL with a programmable runtime,"
  not "the language that implements MCP"

### Practical implication for v4.0

Both `nodus-mcp` and `nodus-a2a` register tools, expose capabilities, and
handle messaging through the same Nodus primitives:

- Tool registration: both use `std:tool.register()` (Decision 12)
- Capability declaration: both libraries declare their capabilities through
  the same patterns
- Streaming: both libraries build on Nodus's coroutine/channel primitives
  (already shipped in v1.x)

The fact that MCP and A2A both work over JSON-RPC/HTTP/SSE makes the
adapter base layer small. This is a happy accident of the current protocol
landscape, not a guarantee — future protocols may diverge, and the adapter
pattern accommodates that.

### What this rules out

Nodus will NOT:

- Add MCP-specific or A2A-specific syntax to the language
- Add MCP-specific or A2A-specific types to the type system
- Bundle MCP or A2A into the language runtime
- Optimize the runtime for one protocol at the expense of others

Nodus WILL:

- Provide the orchestration primitives (workflows, tools, channels, tasks)
  that protocols adapt to
- Keep the embedding API stable enough that library adapters can extend it
  cleanly
- Document the adapter pattern as the way to integrate future protocols

---

## What this ecosystem explicitly does NOT pursue

This section exists to keep the orchestration DSL identity clean. Pressure to
add these will come; this document is the reference for why the answer is no.

### Not pursued: general-purpose scripting expansion

- **Regex** — String parsing belongs to the components Nodus orchestrates,
  not to Nodus itself. If orchestration scripts need log parsing, they call
  a Python subprocess or an MCP tool.
- **CSV** — Data processing is a component concern. Use Python via
  subprocess, an MCP data tool, or a service.
- **Full general-purpose string library** — Orchestration needs less than
  Python or Ruby's string library. The trim/split/replace surface already
  in `std:strings` is sufficient.
- **Full general-purpose math library** — Orchestration doesn't do math.
  `std:math` covers the orchestration use case (timestamps, IDs, retries,
  basic arithmetic).

### Not pursued: web framework / app server territory

- **HTTP server frameworks** — Nodus is a client of HTTP, not a server.
  Workflows can expose HTTP endpoints through the embedding API and a
  Python wrapper, but Nodus does not become Flask/Express/FastAPI.
- **ORMs** — Database access is a component concern. Workflows call services
  that own data.
- **Template engines** — Workflows orchestrate; rendering is a component.
- **Static site generators / frontend tooling** — Out of scope by category.

### Not pursued: language replacement ambitions

- **Replacing Python for general scripting** — Python's 30 years of stdlib
  evolution is a winning competitive position. Nodus competes on
  orchestration primitives (workflows, channels, tasks), not on stdlib
  breadth.
- **Replacing bash for shell scripting** — `std:subprocess` makes Nodus
  capable of orchestrating shell commands, but bash remains the shell.
- **Replacing YAML / TOML / DSLs for config** — Nodus is a scripting
  language; configuration formats stay configuration formats.

### Not pursued: npm-style package sprawl

- **Thousands of small utility libraries** — The registry curates
  orchestration-focused libraries. Quality and architectural coherence over
  quantity.
- **Vendor-specific SDKs as first-class libraries** — Vendor SDKs belong in
  the language they're written for (Python, JavaScript, Go). Nodus calls
  them via subprocess, HTTP, or MCP.

### Not pursued: per-call orchestration options in stdlib

Retry, backoff, rate limiting, circuit breaking, and similar
orchestration patterns are not added as options to stdlib capability
functions. Nodus orchestrates retries via workflows; it doesn't bake
them into every call.

This means `std:http.get()` will never have a `retries` option,
`std:subprocess.run()` will never have a `retry_on_failure` option, and
future capability functions follow the same rule. The workflow layer
composes capabilities; capabilities don't compose themselves.

If real demand surfaces, a future `std:retry` or `std:resilience`
namespace MAY provide helper functions that compose with capability
calls. The stdlib's capability namespaces stay narrow regardless.

For the full statement of this principle, see:

- `docs/language/LANGUAGE_VISION.md` principle #6 (Orchestration
  Composes; Capabilities Don't)
- `docs/language/DESIGN.md` § "Capability Surfaces Stay Narrow"
- `docs/language/STYLE_GUIDE.md` § 18 "Retry, Backoff, and Recovery"
- `docs/governance/STDLIB_PHILOSOPHY.md` § "Capabilities, not
  orchestration" (Phase 4 deliverable)

---

## Library development guidelines (for registry libraries)

Future libraries should follow these patterns. This is summary; full
guidelines will be drafted as part of `nodus-mcp` and `nodus-a2a`
development.

### Naming

Registry libraries are named `nodus-<purpose>`. Examples: `nodus-mcp`,
`nodus-a2a`, `nodus-queue`, `nodus-agent`. The `nodus-` prefix prevents
collision with the bundled stdlib's `std:` namespace and makes provenance
clear.

### Repo and ownership

Registry libraries published by the maintainer live under
`github.com/Masterplanner25/<library-name>`. Community libraries publish
from their own repos and register via the package manifest.

### Versioning

Independent SemVer per library. Library versions are decoupled from
language versions. `nodus-mcp` may ship v0.1, v0.2, v1.0 on its own
schedule.

### Spec verification discipline

Libraries implementing external specifications (MCP, A2A, future
protocols) MUST run a final-pass spec check before public registry release
(see Decision 16 in
`docs/design/v4/00-phase-0-decisions.md`). This catches spec changes
between implementation and release.

### Tool registration

Libraries that expose tools register them via `std:tool.register()` with
dotted namespacing (`mcp.call_tool`, `a2a.send_message`). Conflicts produce
err records; silent override is forbidden.

### Err record shape

Libraries follow the same err record shape as the bundled stdlib:
`{kind, message, payload, path, line, column, stack}`. Protocol-specific
error categories go in `payload.category` (e.g., `mcp_error.category =
"transport_error"`, `a2a_error.category = "task_not_found"`).

---

## v4.0 launch ecosystem snapshot

When v4.0 ships, the ecosystem consists of:

| Component | Tier | Where |
|---|---|---|
| `nodus-lang` core | — | PyPI |
| All Tier 1 stdlib namespaces | 1 | Bundled with `nodus-lang` |
| `nodus-mcp` | 3 | Nodus registry |
| `nodus-a2a` | 3 | Nodus registry |

Three artifacts ship in coordination: `nodus-lang` 4.0.0 to PyPI,
`nodus-mcp` 0.1 to registry, `nodus-a2a` 0.1 to registry. Both libraries
are built against the locked v4.0 source before the PyPI release; the
PyPI release waits on both. See V4_0_PLAN.md Phase 5 for the sequence.

---

## Roadmap visibility

The v5.0 milestone is created at the v4.0 cycle's start as a placeholder
for Tier 2 and Tier 3 deferred libraries. Each deferred library gets a
GitHub issue against v5.0 with the `tier:4-deferred-to-v5` label and a
reference to this document.

This means: Tier 2 and Tier 3 work is tracked from day one, even though
the implementation happens after v4.0 ships. The v5.0 cycle's planning
session (post-v4.0 eval) will sequence which Tier 2 and Tier 3 libraries
get built first.

---

## Reconsideration triggers

This document's architectural commitments hold unless one of the following
fires:

- **Adapter pattern proves inadequate.** If a future protocol cannot be
  cleanly adapted to Nodus runtime primitives, the protocols-are-adapters
  commitment needs revisiting. The trigger is concrete: a protocol whose
  adapter cannot be written without modifying the Nodus runtime in
  protocol-specific ways.

- **General-purpose stdlib demand becomes overwhelming.** If multiple real
  user issues file requests for regex / CSV / full string library /
  general math, and the "use Python" workaround proves inadequate, the
  Tier 1 ceiling is revisited. The trigger is: 10+ issues across distinct
  use cases requesting the same general-purpose addition.

- **Orchestration DSL identity becomes a competitive disadvantage.** If a
  competing language adopts the orchestration DSL positioning and proves
  more capable in the same scope, Nodus's response is to deepen Tier 2
  and Tier 3 rather than widen Tier 1.

Until one of these triggers fires, the three-tier ecosystem and the
protocols-are-adapters commitment hold.

---

## File index

| What | Where |
|---|---|
| This document | `docs/governance/LIBRARY_ECOSYSTEM.md` |
| Phase 0 decisions | `docs/design/v4/00-phase-0-decisions.md` |
| v4.0 plan | `docs/governance/V4_0_PLAN.md` |
| Stdlib philosophy | `docs/governance/STDLIB_PHILOSOPHY.md` (Phase 4 deliverable) |
| nodus-mcp repo | `github.com/Masterplanner25/nodus-mcp` |
| nodus-a2a repo | `github.com/Masterplanner25/nodus-a2a` |