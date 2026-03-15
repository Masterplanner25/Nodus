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

The runtime is typically created through the execution helpers provided by the project.

Example flow:

from nodus.tooling.runner import run_source

run_source(source_code)

This function handles:

tokenize
-> parse
-> resolve imports
-> compile
-> optimize
-> execute

For embedded environments, the host system may manage these stages explicitly.

3. Registering Host Functions

One of the primary embedding mechanisms is the builtin function registry.

Host applications can expose functionality to Nodus scripts.

Example:

def host_log(message):
    print("[host]", message)

vm.register_builtin("log", host_log)

Nodus code can then call the function:

log("hello from script")

This mechanism allows scripts to interact with host services such as:

databases

APIs

task schedulers

monitoring systems

AI agents

4. Providing Runtime Services

Host applications can expose structured services to the runtime.

Examples include:

tool execution

memory systems

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

Errors originating from scripts propagate through the runtime diagnostics system.

Key modules:

errors.py
diagnostics.py

Hosts may intercept runtime errors to:

log failures

retry operations

report failures to external systems

10. Future Embedding Direction

Embedding support will continue to evolve as Nodus matures.

Areas of future work include:

stable embedding APIs

runtime configuration objects

structured event sinks

module loading hooks

sandbox environments

These improvements will allow Nodus to integrate more cleanly with larger systems.

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
