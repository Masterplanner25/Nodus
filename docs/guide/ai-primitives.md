# AI-Native Primitives

These seven stdlib modules are Nodus's answer to the infrastructure that every
production AI system needs: tool dispatch, distributed tracing, idempotency,
memory, and reliability patterns. They ship with `nodus-lang` — no separate
install required.

---

## std:tool — Tool Registry

Registers callable functions as tools discoverable by agents, with MCP-compatible
namespaced naming.

```nd
import "std:tool" as tool

tool.register({
    name: "myapp.search",
    description: "Search the knowledge base",
    handler: fn(query) {
        return http_get("https://search.example.com?q=" + query)
    },
    schema: {
        type: "object",
        properties: { query: { type: "string" } },
        required: ["query"]
    }
})

let result = tool.invoke("myapp.search", { query: "nodus coroutines" })
```

**Tool names must be dotted** (`"myapp.search"`, not `"search"`). The dotted
namespace prevents collisions across modules and is required by the tool registry.

Tools registered with `tool.register` are available to:
- Other Nodus scripts in the same runtime
- The host Python application via `NodusRuntime.tool_registry`
- MCP servers built with `nodus-mcp` (when configured)

---

## std:identity — Trace and Session IDs

Provides propagation-aware identifiers that flow automatically through all
operations in a session.

```nd
import "std:identity" as identity

let trace = identity.trace_id()       // auto-assigned per execution
let session = identity.session_id()   // stable per NodusRuntime instance
let unit = identity.execution_unit_id() // unique per run_source() call
```

IDs are set by the host via `NodusRuntime.set_trace_id(uuid)` before calling
`run_source()`. If not set, Nodus generates them automatically. Useful for
correlating logs across distributed calls.

---

## std:effects — EXACTLY_ONCE Idempotency

Prevents duplicate side effects when a workflow is retried or replayed.

```nd
import "std:effects" as fx

let action_id = fx.action_id("send-notification", { user_id: "u123" })

let status = fx.resolve(action_id)
if (status == "pending") {
    // Not yet run — execute the action
    send_notification("u123")
    fx.complete(action_id)
} else if (status == "complete") {
    // Already ran — skip (idempotent)
}
```

The effect store is injected by the host via `NodusRuntime.set_effect_store(store)`.
The default in-memory store is reset between `run_source()` calls unless you
persist it to a database (via the `nodus-store-sql` package).

---

## std:memory — Shared Namespace Memory

Reads and writes named values across coroutines and workflow steps within
a single runtime session.

```nd
import "std:memory" as mem

// Store a value
mem.share("session", "user_id", "u123")
mem.share("session", "context", { topic: "onboarding" })

// Read it back (from any coroutine or step)
let user = mem.recall_from("session", "user_id")
let all = mem.recall_all("session")   // returns map of all keys

// Tag for retrieval by semantic label
mem.tag("session", "user_id", ["active", "onboarding"])

// Remove
mem.forget("session", "user_id")
```

Namespaces are arbitrary strings. By convention: `"session"` for per-request
state, `"agent"` for agent-scoped state, `"workflow"` for workflow-scoped state.

For persistent memory across sessions, use the `nodus-memory` companion package
(provides vector search, scoring, and feedback).

---

## std:retry — Retry with Policy

Wraps a function call with configurable retry logic.

```nd
import "std:retry" as retry

let result = retry.call(
    fn() { return http_get("https://api.example.com/data") },
    {
        max_attempts: 3,
        backoff: "exponential",
        initial_delay_ms: 100,
        max_delay_ms: 5000,
        jitter: true,
        retry_on: ["network", "timeout"]
    }
)
```

Built-in policies (pass as a string instead of a map):
- `"aggressive"` — 5 attempts, 50ms initial, exponential
- `"standard"` — 3 attempts, 500ms initial, exponential with jitter
- `"conservative"` — 3 attempts, 2s initial, exponential
- `"fixed"` — 3 attempts, 1s fixed interval

Wraps the `nodus-retry` package (required dependency of nodus-lang).

---

## std:circuit_breaker — Three-State Breaker

Protects downstream services from being overwhelmed by failing calls.

```nd
import "std:circuit_breaker" as cb

// Create a named breaker with configuration
cb.create("payment-service", {
    failure_threshold: 5,
    reset_timeout_ms: 30000,
    half_open_max_calls: 2
})

// Call through the breaker
let result = cb.call("payment-service", fn() {
    return http_post("https://payments.example.com/charge", payload)
})

// Inspect state
let state = cb.state("payment-service")   // "closed" | "open" | "half_open"
cb.reset("payment-service")               // force back to closed
```

The circuit breaker is `CLOSED` (allowing calls) → trips to `OPEN` after
`failure_threshold` consecutive failures → moves to `HALF_OPEN` after
`reset_timeout_ms` → returns to `CLOSED` if the half-open probe succeeds.

Wraps the `nodus-circuit-breaker` package (required dependency of nodus-lang).

---

## std:sys — Versioned Syscall Dispatch

Provides a uniform versioned envelope for system operations, useful when
building APIs that need stable response shapes across versions.

```nd
import "std:sys" as sys

let result = sys.v1.call("read_config", { key: "api_endpoint" })
// Returns: { status: "ok"|"error", data: ..., error: nil|{...}, trace_id: ... }
```

The `sys.v1.*` namespace ensures callers can depend on the `{status, data, error,
trace_id}` envelope shape staying stable even as underlying implementations change.

---

## Combining Primitives

A realistic agent step using several primitives together:

```nd
import "std:tool" as tool
import "std:retry" as retry
import "std:identity" as identity
import "std:effects" as fx

let action_id = fx.action_id("call-tool", { tool: "myapp.search", query: query })
if (fx.resolve(action_id) == "complete") {
    return fx.get_result(action_id)
}

let result = retry.call(
    fn() { return tool.call("myapp.search", { query: query }) },
    "standard"
)
fx.complete(action_id, result)
return result
```

---

## See also

- [standard-library.md](standard-library.md) — full stdlib reference including I/O modules
- [workflows-and-tasks.md](workflows-and-tasks.md) — how goals and workflows use checkpoints
- [embedding-nodus.md](embedding-nodus.md) — set_trace_id, set_effect_store from Python
- [ecosystem.md](ecosystem.md) — nodus-memory, nodus-circuit-breaker, nodus-retry packages
