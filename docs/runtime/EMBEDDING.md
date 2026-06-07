# Embedding Nodus

Nodus is designed to function both as a standalone scripting language and as an embedded automation runtime inside larger systems.

This document describes how host applications can integrate with the Nodus runtime.

Embedding allows external systems to:

execute Nodus scripts

register host functions

expose services to scripts

receive runtime events

control execution environments

This makes Nodus suitable as a scripting layer for automation platforms and orchestration systems.

1. Embedding Model

At a high level, embedding Nodus involves four steps:

Host System
   ->
Create Runtime
   ->
Register Builtins / Services
   ->
Load Script
   ->
Execute

The host environment provides capabilities while the Nodus runtime executes script logic.

2. Runtime Initialization

For embedded use, create a ``NodusRuntime`` instance from ``nodus.runtime.embedding``.

``NodusRuntime`` is available directly from the ``nodus`` package as of v1.0:

  from nodus import NodusRuntime         # preferred — added to nodus.__all__ in v1.0
  from nodus.runtime.embedding import NodusRuntime  # also works

Example flow:

from nodus.runtime.embedding import NodusRuntime

runtime = NodusRuntime(
    max_steps=500_000,
    timeout_ms=5000,
    project_root="/my/project",
)
result = runtime.run_source(source_code)

**Long-lived embedding (servers, loops, MCP/A2A hosts):**

The default ``timeout_ms=200`` is designed for short sandboxed script executions
(matching ``nodus run``).  Any session whose coroutines sleep for more than 200 ms
cumulatively — including workflow steps, async I/O loops, or MCP/A2A request handlers
— must disable the deadline explicitly::

  # For servers, event loops, or any coroutine-heavy long-lived host:
  runtime = NodusRuntime(
      timeout_ms=None,    # no wall-clock deadline
      max_steps=None,     # no instruction ceiling
      project_root="/my/project",
  )

With the default, a coroutine sleeping 4 × 100 ms is killed after 200 ms total,
even though it consumed no excessive compute.  This is EMBED-001 (#97); the fix
is always to set ``timeout_ms=None`` for long-lived sessions.  Use per-task timeouts
in your Nodus workflow code instead of a session-level VM deadline.

# Optional: inject initial globals or host globals
# (useful for passing host-owned context to scripts)
result = runtime.run_source(
    source_code,
    initial_globals={"request_id": "abc123"},
    host_globals={"external_service": {"name": "example"}},
)

Constructor parameters:

- ``max_steps`` (int | None, default MAX_STEPS): Maximum total VM instructions per
  execution. Raises ``RuntimeLimitExceeded`` when exceeded. ``None`` means unlimited.
- ``timeout_ms`` (int | None, default EXECUTION_TIMEOUT_MS): Wall-clock timeout in
  milliseconds per execution. ``None`` means no timeout.
- ``max_stdout_chars`` (int | None, default MAX_STDOUT_CHARS): Maximum captured stdout
  characters per execution. Output beyond this limit is silently truncated.
- ``project_root`` (str | None, default None): Absolute path to the project root.
  Used by the module loader to resolve non-relative imports.
- ``allowed_paths`` (list[str] | None, default None): Directory paths the script may
  access via filesystem builtins. ``None`` means unrestricted.
- ``allow_input`` (bool, default False): If ``False``, the ``input()`` builtin raises
  a sandbox error.
- ``max_frames`` (int | None, default None): Maximum call stack depth. Prevents runaway
  recursion from exhausting memory. When exceeded, raises a sandbox error with
  ``kind="sandbox"``. Set to ``None`` for no limit (not recommended for untrusted code;
  the VM applies ``MAX_STACK_DEPTH`` as a hard backstop when this is ``None``).

``NodusRuntime`` handles the full pipeline internally:

tokenize
-> parse
-> resolve imports (ModuleLoader)
-> compile
-> optimize
-> execute

The ``result`` dict contains ``"ok"``, ``"stdout"``, ``"stderr"``, and on error
a structured ``"error"`` entry.

``run_source()`` / ``run_file()`` optional parameters:
- ``initial_globals``: dict injected into ``module_globals`` for the VM (script-level globals).
- ``host_globals``: dict injected into ``host_globals`` for the VM (host-provided services).

The low-level ``nodus.tooling.loader.run_source()`` function is also available
but does not provide sandbox controls or host function registration.  Prefer
``NodusRuntime`` for all embedding scenarios.

3. Registering Host Functions

One of the primary embedding mechanisms is the host function registry on
``NodusRuntime``.

Host applications can expose functionality to Nodus scripts.

Example:

from nodus.runtime.embedding import NodusRuntime

def host_log(message):
    print("[host]", message)

runtime = NodusRuntime()
runtime.register_function("log", host_log)
result = runtime.run_source('log("hello from script")')

Nodus code can then call the function:

log("hello from script")

``register_function(name, fn, arity=None)`` registers the callable before any
run; it is available in every subsequent ``run_source`` / ``run_file`` call.
Arity is inferred from the signature when not provided explicitly.

This mechanism allows scripts to interact with host services such as:

databases

APIs

task schedulers

monitoring systems

external agents

4. Providing Runtime Services

Host applications can expose structured services to the runtime.

Examples include:

tool execution

memory systems

External memory systems, including A.I.N.D.Y., can be connected by the host
application through explicit host functions or services. They are integration
concerns and are not part of Nodus core local key/value memory.

agent frameworks

orchestration infrastructure

Typical architecture:

Host System
  |- tools
  |- memory
  |- services
  - runtime environment
        ->
     Nodus Runtime

Scripts act as orchestration logic while the host system performs the actual work.

5. Script Execution Modes

Nodus supports multiple execution contexts.

Single Script Execution

Run a script once.

Example:

nodus run script.nd
REPL Execution

Interactive execution through the runtime REPL.

python -m nodus.tooling.repl

The REPL supports multiline brace-delimited input, persistent history via `~/.nodus_history` when `readline` is available, and shell inspection commands such as `:ast <expr>`, `:dis <expr>`, and `:type <expr>`.
Server Mode

The runtime can run as a service through:

server.py

This mode allows external systems to send scripts or commands to the runtime.

6. Event Integration

The runtime supports event tracing through the runtime event system.

Key module:

runtime_events.py

Hosts may subscribe to events such as:

task execution

workflow transitions

coroutine scheduling

errors

Example architecture:

VM Execution
   ->
Runtime Events
   ->
Host Event Sink

This allows external systems to observe and monitor script execution.

7. Task and Workflow Integration

Nodus includes orchestration primitives such as:

workflows

goals

task graphs

These constructs compile into runtime task graph structures.

Host systems may provide execution environments for tasks.

Example model:

Nodus Script
   ->
Workflow
   ->
Task Graph
   ->
Scheduler
   ->
Host Worker Execution

This design allows scripts to describe coordination logic while host systems execute the underlying tasks.

8. Runtime Isolation

Embedded runtimes should consider isolation strategies.

Possible approaches include:

separate runtime instances

restricted builtin sets

sandboxed file access

execution time limits

NodusRuntime accepts optional `allowed_paths` and `allow_input` settings.
`allowed_paths` restricts filesystem builtins
(`read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, and `exists`). When
set, paths outside the allowlist raise a sandbox error. When omitted, filesystem
access remains unrestricted.
`allow_input` controls whether `input()` is permitted in embedded mode (default: disabled).
`max_frames` controls the maximum VM call stack depth (default: `MAX_STACK_DEPTH`).

Isolation policies should be defined by the host environment.

9. Error Handling

As of v2.1.0 (BUG-005), `run_source()` catches all runtime and syntax errors and returns
`{"ok": false, ...}` instead of propagating Python exceptions to the caller. Users on
v2.0.x who relied on exception handling around `run_source()` must upgrade to v2.1.0
to get this behavior.

Example:

result = rt.run_source(code)
if not result["ok"]:
    print(f"Error: {result['error']}")
    print(f"Stderr: {result['stderr']}")
else:
    print(f"Result: {result['stdout']}")

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
coroutine failure as it occurs. See GitHub #193 for a planned `fail_on_spawned_errors`
flag that would fold spawned failures into `ok=False`.

Hosts may also intercept runtime errors to:

log failures

retry operations

report failures to external systems

Key modules:

errors.py
diagnostics.py

10. Embedding API Stability (v1.0)

The `NodusRuntime` embedding API is **stable as of v1.0** (2026-03-15).

- `NodusRuntime` constructor parameters are stable.
- `run_source()`, `run_file()`, `register_function()`, and `reset()` are stable.
- `from nodus import NodusRuntime` is the canonical import path.

Areas of future work include:

- structured event sinks (subscribe to runtime events from the host)
- module loading hooks (intercept or override module resolution)
- additional sandbox controls

These additions will not break the existing stable API surface.

11. Example Embedding Architecture

A typical embedded environment might look like:

Application Platform
  |- API services
  |- task workers
  |- memory systems
  - AI agents
        ->
     Nodus Runtime
        ->
     Automation Scripts

In this model:

the host platform provides capabilities

Nodus scripts orchestrate behavior

Final Note

Nodus is designed to serve as a programmable coordination layer.

When embedded inside larger systems, it allows developers to express complex workflows and automation logic using a structured scripting language rather than ad-hoc configuration systems.
