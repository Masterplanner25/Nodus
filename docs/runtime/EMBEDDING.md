# Embedding Nodus

Nodus is designed to function both as a standalone scripting language and as an embedded automation runtime inside larger systems.

This document describes how host applications can integrate with the Nodus runtime.

Embedding allows external systems to:

- execute Nodus scripts
- register host functions
- expose services to scripts
- receive runtime events
- control execution environments

This makes Nodus suitable as a scripting layer for automation platforms and orchestration systems.

## 1. Embedding Model

At a high level, embedding Nodus involves four steps:

```
Host System
   ->
Create Runtime
   ->
Register Builtins / Services
   ->
Load Script
   ->
Execute
```

The host environment provides capabilities while the Nodus runtime executes script logic.

## 2. Runtime Initialization

For embedded use, create a `NodusRuntime` instance from `nodus.runtime.embedding`.

`NodusRuntime` is available directly from the `nodus` package as of v1.0:

```python
from nodus import NodusRuntime         # preferred — added to nodus.__all__ in v1.0
from nodus.runtime.embedding import NodusRuntime  # also works
```

Example flow:

```python
from nodus.runtime.embedding import NodusRuntime

runtime = NodusRuntime(
    max_steps=500_000,
    timeout_ms=5000,
    project_root="/my/project",
)
result = runtime.run_source(source_code)
```

**Long-lived embedding (servers, loops, MCP/A2A hosts):**

`NodusRuntime()` defaults to `timeout_ms=None` (no deadline). Short-lived sandboxed
scripts that need a guardrail should pass an explicit value:

```python
# Short-lived sandboxed script — explicit deadline
runtime = NodusRuntime(timeout_ms=5000, max_steps=100_000)

# Long-lived host (server, MCP/A2A, workflow engine) — use default or be explicit
runtime = NodusRuntime(
    timeout_ms=None,    # no wall-clock deadline (this is already the default)
    max_steps=None,
    max_frames=1000,    # optional — tightens the 10,000 default
    project_root="/my/project",
)
```

> **`max_frames` is the guard that remains when you disable the other two.** It
> defaults to `MAX_STACK_DEPTH` (10,000), the same cap the CLI applies, so an
> infinitely recursive script raises `Call stack overflow` even with
> `max_steps=None` and `timeout_ms=None`. Pass a tighter value (200–1000) for
> untrusted code. Through v4.1.1 the default applied **no cap at all** and that
> configuration ran until the process exhausted memory
> ([#350](https://github.com/Masterplanner25/Nodus/issues/350)).

Note: as of v4.0.1 (SCHED-001), cooperative sleep time is excluded from the deadline
budget. Only active VM instruction execution consumes `timeout_ms`. A coroutine
sleeping 4 × 100 ms with `timeout_ms=500` completes cleanly.

```python
# Optional: inject initial globals or host globals
# (useful for passing host-owned context to scripts)
result = runtime.run_source(
    source_code,
    initial_globals={"request_id": "abc123"},
    host_globals={"external_service": {"name": "example"}},
)
```

Constructor parameters:

- `max_steps` (int | None, default `MAX_STEPS`): Maximum total VM instructions per
  execution. Raises `RuntimeLimitExceeded` when exceeded. `None` means unlimited.
- `timeout_ms` (int | None, default `None`): Wall-clock timeout in milliseconds per
  execution. `None` means no timeout (the default). Pass an explicit value for
  short-lived sandboxed scripts.
- `max_stdout_chars` (int | None, default `MAX_STDOUT_CHARS`): Maximum captured stdout
  characters per execution. Output beyond this limit is silently truncated.
- `project_root` (str | None, default `None`): Absolute path to the project root.
  Used by the module loader to resolve non-relative imports.
- `allowed_paths` (list[str] | None, default `[os.getcwd()]`): Directory paths the
  script may access via filesystem builtins. Defaults to the working directory at
  construction time. Pass `allowed_paths=None` to allow unrestricted filesystem access.
  Also reads `NODUS_ALLOWED_PATHS` env var (colon-separated) when the parameter is
  omitted.
- `allow_input` (bool, default `False`): If `False`, the `input()` builtin raises
  a sandbox error.
- `max_frames` (int | None, default `None` → `MAX_STACK_DEPTH`): Maximum call stack
  depth. When exceeded, raises a sandbox error with `kind="sandbox"` and the message
  `Call stack overflow`. `None` means the CLI's cap of 10,000 — the default is a real
  guard, and it is the only one left when `max_steps` and `timeout_ms` are both `None`.
  Pass 200–1000 for untrusted code. There is no "unlimited" setting; a host that wants
  an effectively unbounded stack passes a large integer, and nothing else will stop the
  growth (VM frames are heap-allocated, so Python's recursion limit never fires).
  Through v4.1.1 the default applied no cap at all
  ([#350](https://github.com/Masterplanner25/Nodus/issues/350)).

The following parameters are **capability switches**. All three **deny by default** as of
v5.0.0 ([#405](https://github.com/Masterplanner25/Nodus/issues/405)), so an embedded
script cannot shell out, open sockets, or read process environment variables unless the
host grants it:

- `allow_subprocess` (bool, default `False`): when `False`, `subprocess_run` and friends
  raise a sandbox error naming the flag.
- `allow_network` (bool, default `False`): when `False`, `http_*` builtins raise a
  sandbox error.
- `allow_env` (bool, default `False`): when `False`, the `env_*` builtins raise a sandbox
  error. Granting it exposes credentials in the host environment to the script.

> This paragraph said the opposite — "all three default to permissive, so an embedded
> script can shell out" — from v5.0.0 until it was corrected. That was true through
> v4.2.0. **Advice written against the old default is backwards**, so treat any
> instruction to turn these *off* as describing a version before 5.0.0. The CLI is
> deliberately unaffected: it builds a `VM` directly and never constructs a
> `NodusRuntime`, because what deny-by-default protects is work you did not fully author.
> Migration note: [`v5.0-deny-by-default.md`](../migration/v5.0-deny-by-default.md).
- `allowed_commands` (list[str] | None, default `None`): allowlist of executables for
  `subprocess_run`. `None` means any command (subject to `allow_subprocess`).
- `allowed_hosts` (list[str] | None, default `None`): allowlist of hosts for network
  builtins. `None` means any host (subject to `allow_network`).

Remaining parameters:

- `on_error` (callable | None, default `None`): invoked when a spawned coroutine dies
  with an uncaught exception — see §9.
- `coroutine_timeout_ms` (int | None, default `None`): per-coroutine deadline.
- `event_sinks` (list | None, default `None`): runtime event sinks — see §6.
- `share_process_state` (bool, default `False`): when `True`, the runtime uses the
  process-global memory store instead of its own. Isolated by default since 5.0.3
  ([#185](https://github.com/Masterplanner25/Nodus/issues/185)) — a guest script can
  *write* memory through `memory_put`, so a shared store is a channel between whatever
  two runtimes are hosting. Leave `False` in any multi-tenant host; to share on purpose,
  pass the same `memory_store=` to both rather than turning this on. Agents are
  deliberately *not* isolated the same way — a guest cannot register one, so the registry
  holds only what the host put there; scope it with `agent_registry=` if you want to.
- `persist_workflow_source` (bool, default `True`): whether a workflow run writes a
  verbatim copy of the whole module source into `.nodus/graphs/`
  ([#499](https://github.com/Masterplanner25/Nodus/issues/499)). That copy is the
  cross-process rebuild handle — it is what lets `nodus workflow sweep` or another
  process resume a parked run. Set `False` when hosting code you did not author and do
  not want persisted to disk; the trade is that such a run cannot be rebuilt elsewhere,
  and the run record records that it opted out rather than failing opaquely later.
- `extensions` (list[str] | None, default `None`): which domain surfaces this runtime
  carries — `workflow`, `tool`, `agent`, `syscall`, `memory`. `None` means all, so this
  is not a switch you have to think about to keep working code working. `[]` leaves a
  general-purpose scripting engine with the whole agentic surface withheld. Unlike the
  capability switches above it grants by default, because it answers *what is this
  runtime for* rather than *what may this program do*. `DOMAIN_BUILTIN_GROUPS` in
  `nodus.runtime.capability` is the published membership; an unknown name is refused at
  construction.

`NodusRuntime` handles the full pipeline internally:

```
tokenize
-> parse
-> resolve imports (ModuleLoader)
-> compile
-> optimize
-> execute
```

The `result` dict contains `"ok"`, `"stdout"`, `"stderr"`, and on error
a structured `"error"` entry.

`run_source()` / `run_file()` optional parameters:

- `initial_globals`: dict injected into `module_globals` for the VM (script-level globals).
- `host_globals`: dict injected into `host_globals` for the VM (host-provided services).

The low-level `nodus.tooling.loader.run_source()` function is also available
but does not provide sandbox controls or host function registration. Prefer
`NodusRuntime` for all embedding scenarios.

## 3. Registering Host Functions

One of the primary embedding mechanisms is the host function registry on
`NodusRuntime`.

Host applications can expose functionality to Nodus scripts.

Example:

```python
from nodus.runtime.embedding import NodusRuntime

def host_log(message):
    print("[host]", message)

runtime = NodusRuntime()
runtime.register_function("log", host_log)
result = runtime.run_source('log("hello from script")')
```

Nodus code can then call the function:

```nd
log("hello from script")
```

`register_function(name, fn, arity=None)` registers the callable before any
run; it is available in every subsequent `run_source` / `run_file` call.
Arity is inferred from the signature when not provided explicitly.

This mechanism allows scripts to interact with host services such as:

- databases
- APIs
- task schedulers
- monitoring systems
- external agents

## 4. Providing Runtime Services

Host applications can expose structured services to the runtime.

Examples include:

- tool execution
- memory systems

External memory systems, including A.I.N.D.Y., can be connected by the host
application through explicit host functions or services. They are integration
concerns and are not part of Nodus core local key/value memory.

- agent frameworks
- orchestration infrastructure

Typical architecture:

```
Host System
  |- tools
  |- memory
  |- services
  |- runtime environment
        ->
     Nodus Runtime
```

Scripts act as orchestration logic while the host system performs the actual work.

## 5. Script Execution Modes

Nodus supports multiple execution contexts.

### Single Script Execution

Run a script once.

Example:

```bash
nodus run script.nd
```

### REPL Execution

Interactive execution through the runtime REPL.

```bash
python -m nodus.tooling.repl
```

The REPL supports multiline brace-delimited input, persistent history via `~/.nodus_history` when `readline` is available, and shell inspection commands such as `:ast <expr>`, `:dis <expr>`, and `:type <expr>`.

### Server Mode

The runtime can run as a service through `server.py`.

This mode allows external systems to send scripts or commands to the runtime.

## 6. Event Integration

The runtime supports event tracing through the runtime event system.

Key module: `runtime_events.py`

Hosts may subscribe to events such as:

- task execution
- workflow transitions
- coroutine scheduling
- errors

Example architecture:

```
VM Execution
   ->
Runtime Events
   ->
Host Event Sink
```

This allows external systems to observe and monitor script execution.

## 7. Task and Workflow Integration

Nodus includes orchestration primitives such as:

- workflows
- goals
- task graphs

These constructs compile into runtime task graph structures.

Host systems may provide execution environments for tasks.

Example model:

```
Nodus Script
   ->
Workflow
   ->
Task Graph
   ->
Scheduler
   ->
Host Worker Execution
```

This design allows scripts to describe coordination logic while host systems execute the underlying tasks.

## 8. Runtime Isolation

Embedded runtimes should consider isolation strategies.

Possible approaches include:

- separate runtime instances
- restricted builtin sets
- sandboxed file access
- execution time limits

`allowed_paths` restricts filesystem builtins (`read_file`, `write_file`, `append_file`,
`mkdir`, `list_dir`, and `exists`); paths outside the allowlist raise a sandbox error.
**Omitting it does not mean unrestricted** — the default is `[os.getcwd()]`, a
working-directory jail. Pass `allowed_paths=None` for genuinely unrestricted access.

`allow_input` controls whether `input()` is permitted (default: `False`).

`max_frames` caps VM call stack depth. The default is `MAX_STACK_DEPTH` (10,000),
matching the CLI; pass 200–1000 to tighten it for untrusted code.

The three capability switches — `allow_subprocess`, `allow_network`, `allow_env` —
all default to `True`. A runtime constructed as `NodusRuntime()` can run subprocesses,
make network calls, and read the process environment. For untrusted scripts:

```python
runtime = NodusRuntime(
    allowed_paths=["/app/scripts"],
    allow_input=False,
    allow_subprocess=False,
    allow_network=False,
    allow_env=False,
    max_frames=500,
    max_steps=100_000,
    timeout_ms=5_000,
)
```

Isolation policies should be defined by the host environment.

## 9. Error Handling

As of v2.1.0 (BUG-005), `run_source()` catches all runtime and syntax errors and returns
`{"ok": false, ...}` instead of propagating Python exceptions to the caller. Users on
v2.0.x who relied on exception handling around `run_source()` must upgrade to v2.1.0
to get this behavior.

Example:

```python
result = rt.run_source(code)
if not result["ok"]:
    print(f"Error: {result['error']}")
    print(f"Stderr: {result['stderr']}")
else:
    print(f"Result: {result['stdout']}")
```

The result dict always contains `"ok"` (bool), `"stdout"` (str), and `"stderr"` (str).
On error, `"error"` contains a human-readable description of the failure.

**Spawned coroutine failures:** a script that calls `spawn()` and whose spawned
coroutine dies with an uncaught error still returns `ok=True` — the main execution
completed successfully. Spawned coroutine errors are collected separately under
`result["extras"]["spawned_errors"]` as a list of error dicts. Hosts that want strict
failure semantics must check both:

```python
result = rt.run_source(src)
if not result["ok"]:
    handle_main_error(result)
elif result.get("extras", {}).get("spawned_errors"):
    handle_spawned_errors(result["extras"]["spawned_errors"])
```

Alternatively, pass `on_error=my_callback` to `run_source()` to receive each spawned
coroutine failure as it occurs. There is no `fail_on_spawned_errors` flag; the
two-check pattern above is the supported way to get strict failure semantics.
(#193, which raised this, was closed by documenting the behavior rather than adding
the flag.)

Hosts may also intercept runtime errors to:

- log failures
- retry operations
- report failures to external systems

Key modules: `errors.py`, `diagnostics.py`

## 10. Embedding API Stability (v1.0)

The `NodusRuntime` embedding API is **stable as of v1.0** (2026-03-15).

- `NodusRuntime` constructor parameters are stable.
- `run_source()`, `run_file()`, `register_function()`, and `reset()` are stable.
- `from nodus import NodusRuntime` is the canonical import path.

Areas of future work include:

- structured event sinks (subscribe to runtime events from the host)
- module loading hooks (intercept or override module resolution)
- additional sandbox controls

These additions will not break the existing stable API surface.

## 11. Example Embedding Architecture

A typical embedded environment might look like:

```
Application Platform
  |- API services
  |- task workers
  |- memory systems
  |- AI agents
        ->
     Nodus Runtime
        ->
     Automation Scripts
```

In this model:

- the host platform provides capabilities
- Nodus scripts orchestrate behavior

## Final Note

Nodus is designed to serve as a programmable coordination layer.

When embedded inside larger systems, it allows developers to express complex workflows and automation logic using a structured scripting language rather than ad-hoc configuration systems.
