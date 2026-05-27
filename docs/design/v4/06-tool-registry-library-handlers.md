# Nodus v4.0 — Design Doc 06: Tool Registry Library Handlers

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 12 (Tool Registry Library-Side Handlers) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 extends the tool registry to support library-side handler
registration. Decision 12 (Phase 0) locked the high-level shape: dynamic
registration (import time AND runtime), unregistration supported,
conflict-as-error, dotted namespacing, host-side adapter extension point
in the embedding API.

This doc specifies the registration API, the metadata schema, the
lifecycle semantics, the invocation patterns, and the host-side
adapter extension. It is the foundation that `nodus-mcp` and
`nodus-a2a` v0.1 both depend on — without this, neither library can
register MCP tools or A2A operations as Nodus-callable.

The architectural commitment from `LIBRARY_ECOSYSTEM.md` is at the
heart of this design: protocols are adapters; the Nodus tool registry
is the source of truth. Both MCP and A2A register their tools through
the same registry, using the same API. Future protocols register the
same way.

---

## What Phase 0 already settled

From Decision 12:

- Libraries register tools via `std:tool.register(metadata)` at import
  time AND during runtime
- Unregistration supported via `std:tool.unregister(name)`
- Conflict-as-error on registration (not silent override)
- Dotted namespacing (`library.tool_name`)
- Host-side adapter extension point in the embedding API

This doc resolves:

- Full registration metadata schema (required + optional fields)
- Schema format (simple form + JSON Schema)
- Registration lifecycle (import vs runtime, re-registration, in-flight
  invocations during unregister)
- Tool invocation API (`tool.invoke`, `tool.lookup`)
- Err contract (six categories)
- Deprecated tool handling
- Host-side adapter API surface
- Namespacing rules (convention-only enforcement)
- Bytecode impact (none)

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

All tool registry operations (`tool.register`, `tool.unregister`,
`tool.invoke`, `tool.lookup`, `tool.list_tools`) are stdlib functions
registered through the existing builtin registry. User code calls them
via the existing `CALL_BUILTIN` opcode.

The `handler` field in tool metadata is a Nodus function value (existing
type). Invoking a tool's handler is a normal function call using
existing function-call infrastructure.

The frozen-bytecode contract from v1.0 is preserved.

---

## Registration metadata schema

### Required fields

| Field | Type | Description |
|---|---|---|
| `name` | string | Dotted-namespaced tool name (e.g., `"mcp.call_tool"`) |
| `handler` | function | Function value invoked when tool is called |
| `description` | string | Human-readable description for documentation and tool listings |

### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `schema` | map (see below) | `{}` (no validation) | Input parameter schema, simple-form or JSON Schema |
| `version` | string | `"1.0.0"` | Tool version; semver convention |
| `tags` | list of string | `[]` | Categorization tags for tool discovery |
| `deprecated` | bool | `false` | If true, emits warning on invocation |
| `metadata` | map | `{}` | Arbitrary library-specific data (e.g., MCP full tool spec, A2A capability declarations) |

### Examples

Minimal registration:

```nodus
tool.register({
    name: "myapp.greet",
    handler: fn(args) { "Hello, " + args.name },
    description: "Returns a greeting"
})
```

Full registration:

```nodus
tool.register({
    name: "mcp.call_tool",
    handler: fn(args) { mcp_internal.dispatch_tool(args) },
    description: "Call a tool on an connected MCP server",
    schema: {
        type: "object",
        properties: {
            server: { type: "string" },
            tool: { type: "string" },
            args: { type: "object" }
        },
        required: ["server", "tool", "args"]
    },
    version: "0.1.0",
    tags: ["mcp", "protocol-adapter"],
    deprecated: false,
    metadata: {
        protocol: "mcp",
        spec_version: "2025-11-25"
    }
})
```

### The `metadata` escape hatch

Libraries can store protocol-specific or library-specific data in the
`metadata` field. The registry treats it as opaque (no validation, no
interpretation). Examples:

- `nodus-mcp` uses `metadata` to store the full MCP tool definition
  (input/output schemas, capability annotations)
- `nodus-a2a` uses `metadata` to store the A2A capability declaration
  (extensions, supported interfaces)
- A future protocol library uses `metadata` to store whatever
  protocol-specific data it needs

This avoids polluting the standard schema with protocol-specific
fields while keeping the data accessible via `tool.lookup(name)`.

---

## Schema format

The `schema` field supports two forms: a simple type-name map and
full JSON Schema. The library normalizes simple form to JSON Schema
internally; both are stored and retrievable.

### Simple form

A flat map of parameter name to type name:

```nodus
schema: { server: "string", tool: "string", args: "map" }
```

Supported type names (mapped to JSON Schema types):

| Nodus type name | JSON Schema type |
|---|---|
| `"string"` | `"string"` |
| `"int"` | `"integer"` |
| `"float"` | `"number"` |
| `"bool"` | `"boolean"` |
| `"map"` | `"object"` |
| `"list"` | `"array"` |
| `"nil"` | `"null"` |
| `"any"` | (no type constraint) |

All parameters in simple form are required. For optional parameters or
more complex schemas, use the full JSON Schema form.

### Full JSON Schema form

Standard JSON Schema (draft 2020-12):

```nodus
schema: {
    type: "object",
    properties: {
        server: { type: "string" },
        tool: { type: "string" },
        args: { type: "object" },
        timeout_ms: { type: "integer", default: 5000 }
    },
    required: ["server", "tool", "args"]
}
```

The library detects which form is in use by checking for the
`"type": "object"` top-level field (JSON Schema's discriminator). If
present, full JSON Schema. Otherwise, simple form.

### Normalization

Simple form is normalized to JSON Schema at registration time. The
stored schema is always JSON Schema; lookups return the normalized
form. This is consistent with how MCP and A2A both expose tool schemas
externally (both protocols use JSON Schema in their wire formats).

---

## Registration lifecycle

### Import-time registration

When a library module is imported (`import "nodus-mcp" as mcp`), its
init code runs. If the init code calls `tool.register({...})`, the
tools are available from that point until process exit or explicit
unregistration.

This is the static-registration case: tools are known at import time
and don't change during the script's lifetime.

```nodus
// In nodus-mcp's module init:
tool.register({
    name: "mcp.call_tool",
    handler: fn(args) { ... },
    description: "Call a tool on an MCP server"
})

tool.register({
    name: "mcp.list_resources",
    handler: fn(args) { ... },
    description: "List resources on an MCP server"
})
```

### Runtime registration

Tools can also be registered after import, in response to dynamic
discovery:

```nodus
// nodus-mcp connecting to a server and registering its tools
let server_info = mcp.connect(server_url)
for t in server_info.tools {
    tool.register({
        name: "mcp." + server_info.id + "." + t.name,
        handler: fn(args) { mcp.call_remote_tool(server_url, t.name, args) },
        description: t.description,
        schema: t.input_schema,
        metadata: { server_id: server_info.id, remote_tool: t.name }
    })
}
```

This is the AI-agent use case Decision 12 specifically called out: AI
agents need dynamic tool discovery, and MCP servers can add/remove
tools at runtime. The registry accommodates this directly.

### Conflict on registration

Registering a tool with a name already in the registry produces an err
record:

```nodus
tool.register({name: "mcp.call_tool", handler: f1, description: "..."})
tool.register({name: "mcp.call_tool", handler: f2, description: "..."})
// Second call returns:
// err {
//     kind: "tool_error",
//     message: "Tool 'mcp.call_tool' is already registered",
//     payload: {
//         category: "registration_conflict",
//         name: "mcp.call_tool",
//         existing_description: "...",
//         attempted_description: "..."
//     }
// }
```

The caller can:

- Call `tool.unregister("mcp.call_tool")` first, then re-register
- Use a different name
- Detect the conflict and handle accordingly

There is no `force` option for silent override; silent behavior is the
worst option for security-sensitive tool dispatch (Decision 12
explicitly rejected this).

### Unregistration

```nodus
tool.unregister("mcp.call_tool")
```

Removes the tool from the registry. Returns the previously-registered
metadata (useful for testing and migration scenarios), or err if the
name was not registered:

```nodus
let removed = tool.unregister("mcp.call_tool")
// removed is the metadata record (or err if not found)
```

### In-flight invocations during unregistration

If `tool.invoke("mcp.call_tool", args)` is in flight when
`tool.unregister("mcp.call_tool")` is called:

- The in-flight call completes (the handler function continues
  executing)
- Subsequent calls to `tool.invoke("mcp.call_tool", ...)` return err
  with `category: "tool_not_found"`

This is the natural semantics — once invoked, the handler is just a
Nodus function call; unregistration only affects future lookups.

### Re-registration after unregistration

Re-registering a previously-unregistered name is allowed without any
special flag:

```nodus
tool.register({name: "mcp.call_tool", handler: f1, ...})
tool.unregister("mcp.call_tool")
tool.register({name: "mcp.call_tool", handler: f2, ...})   // works
```

This is the dominant pattern for MCP/A2A: server disconnects, tools
are unregistered; server reconnects, tools are re-registered.
Requiring a `force: true` flag would add ceremony for the common case
without protection benefit (the only protection is against accidental
double-registration, which the initial conflict-as-error already
catches).

---

## Tool invocation API

### `tool.invoke(name, args)`

The primary invocation function. Looks up the tool, validates args
against the registered schema (if any), calls the handler, returns the
result.

```nodus
let result = tool.invoke("mcp.call_tool", {
    server: "abc123",
    tool: "read_file",
    args: {path: "/tmp/data.json"}
})
```

Behavior:

1. Look up the tool by name
2. If not found, return err with `category: "tool_not_found"`
3. If found and `schema` is registered, validate `args` against schema
4. If schema validation fails, return err with `category: "schema_mismatch"`
5. If the tool is `deprecated: true`, emit a warning (once per tool
   per VM instance)
6. Invoke the handler with `args`
7. If the handler returns or throws an err, propagate it with
   `category: "handler_error"` augmentation (the original err is
   nested in `payload.handler_err`)
8. Return the handler's return value

### `tool.lookup(name)`

Returns the registered metadata, or err if not found. Useful for
power users and library authors who need to inspect or pre-bind a
tool:

```nodus
let meta = tool.lookup("mcp.call_tool")
// meta is the metadata record (name, handler, description, schema, ...)

// Pre-bind the handler for a tight loop
let handler = meta.handler
for item in items {
    handler(item)
}
```

`tool.lookup` does NOT validate args (the caller is calling the
handler directly, bypassing the registry's validation). If the caller
wants validation, they call `tool.invoke` instead.

### `tool.list_tools(filter?)`

Returns a list of all registered tool metadata records. Optional
filter for namespace or tag:

```nodus
tool.list_tools()                              // all tools
tool.list_tools({namespace: "mcp"})            // only mcp.* tools
tool.list_tools({tag: "protocol-adapter"})     // only tools tagged "protocol-adapter"
tool.list_tools({deprecated: false})           // only non-deprecated tools
```

Returns a list of metadata records (same shape as `tool.lookup`
returns for individual tools). Used by:

- MCP server-side enumeration (Nodus exposing tools to MCP clients)
- A2A AgentCard generation (Nodus exposing tools as A2A capabilities)
- Tooling/CLI commands (`nodus tool list`)
- LSP completion

### `tool.has(name)`

Returns `true` if a tool is registered with that name; `false`
otherwise. Convenience for guard clauses:

```nodus
if tool.has("mcp.call_tool") {
    tool.invoke("mcp.call_tool", args)
} else {
    fallback_path()
}
```

Equivalent to `type(tool.lookup(name)) != "error"` but avoids the err
record allocation.

---

## Err record shape

All tool registry errors return err records with this shape:

```nodus
err {
    kind: "tool_error",
    message: string,
    path: ..., line: ..., column: ..., stack: ...,
    origin: "stdlib",
    payload: {
        category: string,
        name: string,             // tool name involved
        details: ...              // category-specific details
    }
}
```

### Category enumeration

| Category | When emitted |
|---|---|
| `"tool_not_found"` | `tool.invoke` / `tool.lookup` on unregistered name |
| `"schema_mismatch"` | Args don't match registered schema during `tool.invoke` |
| `"registration_conflict"` | `tool.register` on already-registered name |
| `"handler_error"` | Handler returned or threw an err; wrapped to identify tool origin |
| `"invalid_metadata"` | `tool.register` called with malformed metadata (missing required field, wrong type) |
| `"invalid_name"` | Tool name doesn't match naming rules (no dot, invalid characters) |

---

## Deprecated tool handling

Tools registered with `deprecated: true` still work — invoking them
calls the handler and returns the result normally. The change is a
warning emitted on first invocation per VM instance:

```
Warning: tool 'old.legacy_tool' is deprecated. (This warning is shown once per VM instance.)
```

The warning is emitted to stderr by default. Libraries embedding Nodus
can override the warning sink via the embedding API (e.g., route to a
logging system).

Deprecation tracking is per-tool: each deprecated tool emits its first-
invocation warning once, even if multiple deprecated tools exist. This
prevents log spam when many tools are deprecated simultaneously (e.g.,
during a major version migration).

The `deprecated` flag can be updated by unregistering and re-registering
with the new flag. There is no separate "mark deprecated" function;
deprecation is part of the metadata.

---

## Host-side adapter extension API

The embedding API gains a `tool_registry` entry point. Python host code
accesses the same registry that Nodus code uses:

```python
nodus_runtime = NodusRuntime(...)

# Register a tool from Python (handler is a Python callable)
nodus_runtime.tool_registry.register({
    "name": "python.embedded_tool",
    "handler": python_callable,
    "description": "A tool implemented in Python",
    "schema": {...}
})

# Invoke a Nodus-registered tool from Python
result = nodus_runtime.tool_registry.invoke("nodus.workflow", args)

# Look up a tool's metadata
meta = nodus_runtime.tool_registry.lookup("mcp.call_tool")

# List tools (for MCP server enumeration)
tools = nodus_runtime.tool_registry.list_tools()

# Unregister
nodus_runtime.tool_registry.unregister("python.embedded_tool")
```

### Value translation

Python-side handlers receive args translated from Nodus values to
Python equivalents:

| Nodus value | Python equivalent |
|---|---|
| Integer (`1i`) | `int` |
| Float | `float` |
| String | `str` |
| Boolean | `bool` |
| Nil | `None` |
| List | `list` |
| Map | `dict` (keys are `str`) |
| Record | `dict` (keys are `str`) |
| Channel | (not translatable; err) |
| Coroutine | (not translatable; err) |
| Function | (not translatable; err) |
| Err record | dict with `__nodus_err__: True` marker |

Return values translate back the other direction. The translation
rules already exist for builtins; the tool registry uses the same
infrastructure.

Channels, coroutines, and Nodus functions cannot cross the Python
boundary cleanly. Tools that need to handle these types stay on the
Nodus side (registered with Nodus-side handlers).

### Same registry, both sides

`tool.register` from Nodus code and `nodus_runtime.tool_registry.register`
from Python code write to the same underlying store. A tool registered
from Python is visible to `tool.list_tools()` in Nodus and vice versa.
The registry is a single shared resource per VM instance.

This is essential for the protocol-adapter pattern:

- `nodus-mcp` (a Nodus library) registers MCP tools from Nodus code
- `nodus-mcp` server-side (Python code in the library's implementation)
  enumerates all Nodus-registered tools to expose them via MCP
- Both halves of the library use the same registry

---

## Namespacing rules

### Naming convention

Tool names use dotted namespacing: `<namespace>.<name>` (e.g.,
`"mcp.call_tool"`, `"a2a.send_message"`).

Rules:

1. **At least one dot required.** Single-segment names are reserved
   for future stdlib use (`"echo"`, `"version"`, etc.). Library tools
   must use namespaced names.

2. **First segment is the namespace.** Convention is to match the
   library's purpose: `mcp.*` for MCP, `a2a.*` for A2A, `myapp.*` for
   application-specific tools.

3. **Character set:** `[a-z0-9_.-]`. Lowercase letters, digits,
   underscore, period, hyphen. No uppercase, no slashes, no colons.

4. **Length limit:** 200 characters total. Longer names are accepted
   but flagged via warning (orchestration code with very long names
   suggests a deeper problem).

5. **Reserved prefixes:** none in v4.0. Future versions may reserve
   specific prefixes (e.g., `"std.*"`) if needed for stdlib expansion.

### Convention-only enforcement

The registry does NOT enforce that a library registers only under its
own namespace. A library named `nodus-mcp` can technically register
tools under any namespace — the registry only checks for name
conflicts, not for namespace ownership.

This is intentional:

1. **Strict enforcement would couple the registry to the package
   system.** The registry would need to know which package a
   registration came from. Adds complexity for a problem that doesn't
   exist (libraries don't accidentally register under wrong
   namespaces).

2. **Conflict-as-error already prevents most issues.** If two libraries
   both try to register `"mcp.call_tool"`, the second one errs. No
   silent override possible.

3. **Polyglot libraries might legitimately need multiple
   namespaces.** A hypothetical library that bridges MCP and A2A could
   register tools in both namespaces.

If real issues emerge from convention-only namespacing, v4.x can add
strict enforcement (e.g., a manifest-declared `namespaces` list in the
package metadata). Starting permissive and tightening later is
recoverable; starting strict and loosening later is harder.

---

## MCP and A2A consumer validation

### nodus-mcp consumer needs

`nodus-mcp` v0.1 uses the tool registry in three places:

**1. Exposing MCP tools as Nodus-callable.** When the library connects
to an MCP server, it discovers the server's tools and registers each
one in the Nodus registry:

```nodus
import "nodus-mcp" as mcp

let server = mcp.connect("https://example.com/mcp")
// At connect time, the library calls tool.register for each MCP tool
// the server exposes. Tools become available as "mcp.<server_id>.<tool_name>".

let result = tool.invoke("mcp.example.read_file", {path: "/tmp/data.json"})
```

**2. Exposing Nodus tools as MCP tools (server side).** When Nodus
acts as an MCP server, the library enumerates Nodus-registered tools
via `tool.list_tools()` and serves them through MCP:

```python
# In nodus-mcp's Python-side MCP server code
nodus_tools = nodus_runtime.tool_registry.list_tools()
for tool_meta in nodus_tools:
    # Translate Nodus tool metadata to MCP tool definition
    mcp_tool = translate_to_mcp(tool_meta)
    mcp_server.register_tool(mcp_tool)
```

**3. Unregistering tools on disconnect.** When an MCP server
disconnects, the library unregisters its tools:

```nodus
mcp.disconnect(server)
// Library calls tool.unregister for each tool it registered for this server
```

All three patterns are supported cleanly by the v4.0 tool registry.

### nodus-a2a consumer needs

`nodus-a2a` v0.1 uses the tool registry similarly:

**1. Exposing A2A operations as Nodus-callable.** When the library
connects to an A2A agent, it registers the agent's operations:

```nodus
import "nodus-a2a" as a2a

let agent = a2a.connect(agent_card_url)
// Library registers tools like "a2a.<agent_id>.send_message",
// "a2a.<agent_id>.get_task", etc.

let task = tool.invoke("a2a.researcher.send_message", {
    content: "Research recent papers on...",
    context_id: ctx
})
```

**2. Exposing Nodus tools as A2A capabilities.** When Nodus acts as an
A2A agent, the library generates the AgentCard by enumerating
registered tools:

```python
# In nodus-a2a's Python-side server code
nodus_tools = nodus_runtime.tool_registry.list_tools()
agent_card = generate_agent_card_from_tools(nodus_tools)
a2a_server.serve(agent_card)
```

**3. Lifecycle management.** Connect/disconnect mirrors MCP's pattern.

Both libraries' patterns are first-class use cases for the tool
registry. The design works for both without library-specific
extensions.

---

## Migration impact

### Additive

The tool registry is new in v4.0. There is no v3.x tool registry to
migrate from. Existing v3.x code is unaffected unless it imports
`std:tool` (which doesn't exist in v3.x).

For library authors: existing v3.x code that exposed callable functions
through the embedding API can be migrated to register them as tools.
This is opt-in; the embedding API's existing function-registration
mechanism continues to work alongside the tool registry.

---

## Implementation outline

### Registry data structure

Single map per VM instance: `name → metadata`. The metadata is the
normalized record (schema converted to JSON Schema form, defaults
applied for optional fields).

Thread-safety: the Nodus VM is single-threaded by default, but if
embedded in a multi-threaded host (multiple Python threads calling into
the same VM), the registry needs synchronization. Tentative:
threading.RLock on registration/lookup operations.

### `tool.register` flow

1. Validate metadata structure (required fields present, types
   correct, name matches naming rules)
2. Normalize schema (simple form → JSON Schema)
3. Apply defaults for optional fields
4. Check for name conflict; return err if exists
5. Store in registry
6. Return success (the registered metadata)

### `tool.invoke` flow

1. Look up name; return tool_not_found err if absent
2. Apply schema validation if schema present
3. If tool is deprecated, emit warning (once per VM per tool)
4. Call handler with args
5. If handler returns err, wrap in handler_error category
6. Return result

### Schema validation

JSON Schema validation uses the `jsonschema` Python library (existing
dependency or new). For simple-form schemas (which are normalized to
JSON Schema), validation is straightforward type checking.

### Host-side adapter implementation

The embedding API exposes a Python-facing wrapper class:

```python
class ToolRegistry:
    def __init__(self, vm):
        self._vm = vm
        self._registry = vm.tool_registry  # the shared map

    def register(self, metadata):
        # Validate and store, same as Nodus-side tool.register
        # If handler is a Python callable, wrap it in value-translation
        ...

    def invoke(self, name, args):
        # args translated from Python to Nodus types
        # result translated from Nodus to Python types
        ...

    # ... lookup, unregister, list_tools, has
```

### Test surface

Phase 3B test cases:

- Register with minimal metadata (name, handler, description)
- Register with full metadata
- Register with simple-form schema; verify normalization to JSON Schema
- Register with full JSON Schema
- Register with invalid metadata (missing required field, wrong type)
  → err
- Register conflicting name → err with details
- Unregister existing tool → returns metadata
- Unregister non-existent tool → err
- Re-register after unregister → works
- Invoke registered tool → handler called, result returned
- Invoke with mismatched args (schema validation failure) → err
- Invoke non-existent tool → err
- Invoke deprecated tool → warning emitted once per VM
- List all tools, filter by namespace, filter by tag, filter by
  deprecated status
- `has()` returns correct boolean
- Lookup returns metadata
- Host-side registration from Python; visible to Nodus list_tools
- Host-side invocation of Nodus-registered tool
- Value translation across Python/Nodus boundary for all supported
  types
- In-flight invocation completes after unregistration
- Naming rule validation: dotted name required, character set,
  length limit warning

---

## Open implementation questions for Phase 3B

1. **JSON Schema validator dependency.** Use Python's `jsonschema`
   package or implement a minimal validator? Tentative: `jsonschema`
   package; add to `pyproject.toml` if not already present.

2. **Warning emission mechanism.** Stderr write, or a more structured
   warning channel? Tentative: stderr write with library-overridable
   sink. Aligns with Python's `warnings` module pattern.

3. **Deprecated-warning state storage.** Per-VM dict of warned-tool
   names. Tentative: simple set; clears on VM shutdown.

4. **Registry capacity limit.** Should there be a maximum number of
   registered tools? Tentative: no hard limit; very large registries
   (10000+ tools) are unusual but not problematic.

5. **Thread-safety primitive.** RLock is the conservative choice;
   verify whether actual usage patterns warrant lighter-weight
   synchronization. Tentative: RLock initially; optimize if profiling
   shows contention.

6. **Function-value handler representation.** When a Nodus function
   value is registered as a handler, the registry stores a reference.
   Verify the reference doesn't prevent garbage collection of
   un-registered tools. Tentative: weak reference where possible;
   strong reference for tools currently invocable.

---

## Capability surface ceiling

Per the capabilities-not-orchestration principle, the tool registry
does NOT include:

- **Tool composition / chaining.** No `tool.pipe(t1, t2, t3)` or
  similar. Composition is workflow's job; the registry provides
  primitives.
- **Tool-level retry, timeout, or rate-limiting.** Per the
  capabilities-not-orchestration principle, these belong to workflow
  code wrapping tool invocations.
- **Tool documentation generation (manpage / API doc output).**
  The `tool.list_tools()` API exposes the data; a separate `nodus tool
  docs` CLI command or future `nodus-toolgen` library produces formatted
  docs.
- **Access control / capability tokens.** Beyond the basic "tool
  exists" check, no permission system. The `nodus-tooling` Tier 3
  library (v5.0 milestone) is the planned home for capability
  contracts and access control.
- **Tool versioning enforcement.** The `version` field is informational;
  the registry doesn't enforce minimum versions or version compatibility.
  Future versioning support possible if real demand surfaces.

### Reconsideration triggers

Scope expands if:

- Real user issues request specific additions (10+ across distinct use
  cases per addition)
- A v4.0 library implementation requires a primitive only cleanly
  provided by the tool registry
- The protocols-are-adapters pattern requires capabilities not in v4.0
  (most likely: stricter access control, which is tracked as Tier 3
  `nodus-tooling`)

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 12 (tool registry
  library-side handlers)
- `docs/design/v4/00-phase-0-decisions.md` Decision 16 (nodus-mcp v0.1)
- `docs/design/v4/00-phase-0-decisions.md` Decision 17 (nodus-a2a v0.1)
- `docs/governance/LIBRARY_ECOSYSTEM.md` (protocols-are-adapters
  architectural commitment; tool registry is the implementation point)
- `docs/governance/LIBRARY_ECOSYSTEM.md` § Tier 3 (`nodus-tooling`
  registry library, v5.0; adds capability contracts on top of v4.0
  tool registry)
- `docs/design/v4/01-http-api.md`, `04-subprocess-api.md` (sibling
  capability designs; tool registry uses same Phase 1 patterns)
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions appended)

---

## Phase 3B implementation handoff

When Phase 3B begins (tool registry implementation), the following
artifacts are ready:

1. This design doc (`06-tool-registry-library-handlers.md`)
2. Decision 12 (Phase 0)
3. Six open implementation questions enumerated above
4. Substrate locked: Python stdlib + `jsonschema` package
5. Test surface enumeration covering registration, invocation,
   lookup, listing, host-side integration, and edge cases

Estimated implementation effort: 2-3 days focused work. The registry
data structure is simple; the value-translation layer for host-side
invocation reuses existing builtin-call infrastructure; JSON Schema
validation is a thin wrapper around the `jsonschema` library.

The tool registry is a prerequisite for both `nodus-mcp` v0.1 and
`nodus-a2a` v0.1 implementation. Once shipped, both libraries can
begin their own implementation phases against the locked API.

---

**Phase 1 doc 06-tool-registry-library-handlers.md: COMPLETE.**
