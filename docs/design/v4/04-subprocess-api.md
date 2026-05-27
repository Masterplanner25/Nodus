# Nodus v4.0 — Design Doc 04: Subprocess API

**Phase:** 1 (design docs)
**Status:** Locked
**Implements:** Decision 8 (Subprocess API Shape) from `00-phase-0-decisions.md`
**Date:** 2026-05-26
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Problem statement

v4.0 ships a subprocess client as a Tier 1 orchestration stdlib namespace.
Decision 8 (Phase 0) locked the high-level shape: no-shell default with
separate `subprocess.shell()` function, sync default with async opt-in,
comprehensive output handling, `check: true` default. This doc specifies
the API surface in implementable detail.

Subprocess is the second-most-used orchestration capability after HTTP.
It is also the dependency for `nodus-mcp`'s stdio transport (the primary
MCP transport for local servers). Design choices here shape that
library's implementation.

This doc is drafted after `01-http-api.md` and adopts consistent patterns
where both namespaces share concerns (sync/async function variants,
streaming via channels, err record shape with category field). It
deliberately diverges where the use cases differ — most notably,
subprocess streams are line-buffered by default while HTTP streams are
byte-chunked.

---

## What Phase 0 already settled

From Decision 8:

- No-shell default with separate `subprocess.shell()` function (security)
- Sync default with async opt-in
- Function set: `subprocess.run`, `subprocess.run_async`,
  `subprocess.shell`, `subprocess.shell_async`, `subprocess.spawn`
- Options: `output` (capture/inherit/ignore), `stdout`/`stderr` per-stream
  override, `stdin`, `env` (merged by default), `env_inherit`, `cwd`,
  `timeout_ms`, `check` (default true)
- Err: `kind: "subprocess_error"` with `category` (`"exit_code"`,
  `"timeout"`, `"signal"`, `"spawn_error"`, `"io_error"`)

This doc resolves:

- Success result shape
- Process handle (spawn) shape with channel semantics
- Environment merging behavior with selective passthrough
- Timeout grace period configuration
- Per-stream output override semantics
- Shell configuration
- Shell quoting helper
- Process group management
- Signal handling cross-platform
- Stream chunking (line-buffered for subprocess, contrasting with
  byte-chunked for HTTP)
- Implementation substrate

---

## API surface

### Function set

```
subprocess.run(argv, options?)
subprocess.run_async(argv, options?)
subprocess.shell(command_string, options?)
subprocess.shell_async(command_string, options?)
subprocess.spawn(argv, options?)
subprocess.spawn_shell(command_string, options?)
subprocess.shell_quote(string)
```

Seven public functions. The `_async` variants return coroutines per
Nodus's existing coroutine system; sync variants block until process
exit (or timeout).

`subprocess.spawn_shell` was added during the design (cluster S1 review)
for symmetry with `shell`/`run`: if you want a long-running shell process
with channel-based I/O, you need it. The function is a small addition;
omitting it would force `nodus-mcp`-style consumers to choose between
`spawn` (no shell) and `shell` (no channels), which is the wrong shape.

### Options object — flat layout

Same flat layout pattern as `01-http-api.md`. Options grouped below by
concern but all live at the top level.

**Output keys:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `output` | string | `"capture"` | Default handling for both streams: `"capture"`, `"inherit"`, `"ignore"` |
| `stdout` | string | (inherits `output`) | Per-stream override: `"capture"`, `"inherit"`, `"ignore"`, or file path string |
| `stderr` | string | (inherits `output`) | Per-stream override (same values as `stdout`) |
| `output_encoding` | string | `"utf-8"` | Encoding for captured output; use `"bytes"` to get raw bytes |

**Resolution order for stream handling:**

1. Per-stream `stdout`/`stderr` takes priority if set
2. Otherwise top-level `output` applies
3. Default is `"capture"`

File-path string redirects the stream to that file. The library opens
the file for writing (truncates by default; append via `>>` prefix:
`{stdout: ">>/var/log/out.log"}`).

**Input key:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `stdin` | string, bytes, or nil | nil | Static input to write to the process's stdin |

For `subprocess.spawn`, `stdin` is ignored in favor of the channel on
the process handle (`p.stdin`).

**Environment keys:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `env` | map of string-to-string | `{}` | Environment variables to set/override |
| `env_inherit` | bool | `true` | Inherit parent process environment as base; `env` overlays on top |
| `env_passthrough` | list of string | (none) | When `env_inherit: false`, pass through only these specific vars from parent env |

**Behavior:**

- `env_inherit: true` (default): start with parent env, overlay `env`
  map. Conflict resolution: `env` wins.
- `env_inherit: false` with no `env_passthrough`: empty env, only what's
  in `env` map is set.
- `env_inherit: false` with `env_passthrough: ["PATH", "HOME"]`: start
  with empty env, copy listed vars from parent env, overlay `env` map.

**Working directory:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `cwd` | string | (current dir) | Working directory for the process |

**Timeout keys:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `timeout_ms` | int | (unlimited) | Wall-clock timeout in milliseconds |
| `kill_grace_ms` | int | `5000` | Grace period after SIGTERM before SIGKILL |

When timeout fires: SIGTERM (or platform equivalent) is sent. After
`kill_grace_ms`, if the process is still alive, SIGKILL is sent. Returns
err with `category: "timeout"`.

**Check key:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `check` | bool | `true` | Non-zero exit produces err with `category: "exit_code"`; `false` returns the result record with the actual exit_code |

**Process group key:**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `process_group` | bool | `true` | Subprocess and children form a process group; killing parent kills the group. Set `false` for daemon-style spawning. Maps to job objects on Windows. |

**Shell-specific keys (only for `subprocess.shell` and `subprocess.shell_async`):**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `shell` | string | (platform default) | Shell executable to use. Default is `/bin/sh` on Unix, `cmd.exe` on Windows |

**Spawn-specific keys (only for `subprocess.spawn` and `subprocess.spawn_shell`):**

| Key | Type | Default | Behavior |
|---|---|---|---|
| `chunk_mode` | string | `"lines"` | Stream chunking on `p.stdout` and `p.stderr` channels: `"lines"` (default), `"bytes"` |

### Result record (from `run`, `shell`, and their `_async` variants)

```nodus
let r = subprocess.run(["ls", "-la"])
r.stdout         // captured stdout (string by default, bytes if output_encoding: "bytes")
r.stderr         // captured stderr (same)
r.exit_code      // int (0 for success when check: true; actual code when check: false)
r.duration_ms    // int (wall-clock duration in ms)
r.command        // list of string (argv as invoked) or string (shell command_string)
```

When `output: "inherit"` or `output: "ignore"`, `r.stdout` and `r.stderr`
are empty strings. When a stream is redirected to a file via the
per-stream override, the corresponding result field is also empty.

### Process handle (from `subprocess.spawn` and `subprocess.spawn_shell`)

```nodus
let p = subprocess.spawn(["server", "--port", "8080"])

// Streams (channels)
for line in p.stdout { print(line) }     // line-buffered by default
for line in p.stderr { eprint(line) }    // can be consumed in parallel
p.stdin.send("hello\n")                  // write to stdin
p.stdin.close()                          // close stdin to signal EOF

// Identity
p.pid                                    // int process ID
p.command                                // list of string (argv) or string (shell)

// Lifecycle
p.wait()                                 // block until exit; returns exit_code (int) or err record
p.wait_async()                           // async coroutine version
p.is_alive()                             // bool
p.exit_code                              // nil while running; int after exit

// Control
p.terminate()                            // SIGTERM (Unix); terminate process (Windows)
p.kill()                                 // SIGKILL (Unix); kill process (Windows)
p.interrupt()                            // SIGINT (Unix); CTRL_C_EVENT (Windows)
p.signal(name)                           // raw signal by name (Unix only; Windows attempts mapping or errs)
```

**Stream chunk semantics:**

- Default `chunk_mode: "lines"`: each channel send is one line (string,
  trailing newline stripped). Encoding per `output_encoding`.
- `chunk_mode: "bytes"`: each channel send is a chunk of bytes (variable
  size, whatever the OS delivers). Encoding ignored.
- UTF-8 boundary buffering applies in `"lines"` mode (no chunk yielded
  mid-character).
- Lines split on `\n` (Unix) or `\r\n` (Windows, normalized to `\n` before
  yield).
- A final partial line (process exits without trailing newline) is
  yielded as the last channel value.

**Channel close semantics:**

- `p.stdout` and `p.stderr` channels close when the process exits and
  all output has been flushed.
- `p.stdin` is a write-channel; user closes it via `p.stdin.close()` to
  signal EOF to the process.
- If the process exits before consuming all stdin sent, the unread input
  is dropped (standard OS behavior).
- `p.terminate()`, `p.kill()`, or `p.interrupt()` close all three
  channels.

**Mid-stream errors:**

If reading from stdout/stderr fails (process killed, pipe broken),
the channel emits exactly one err record as its final value, then
closes. Same pattern as `http.stream`. Err shape:

```nodus
err {
    kind: "subprocess_error",
    payload: {
        category: "io_error",
        command: ...,
        pid: ...,
        bytes_received: ...,
        partial_output: ...
    }
}
```

---

## Err record shape

All `std:subprocess` errors return err records with this shape:

```nodus
err {
    kind: "subprocess_error",
    message: string,
    path: ..., line: ..., column: ..., stack: ...,
    payload: {
        category: string,
        command: list of string or string,    # argv or shell string
        pid: int or nil,                       # nil if spawn failed
        exit_code: int or nil,                 # nil if process didn't exit cleanly
        signal: string or nil,                 # signal name if process was signaled
        stdout: string or bytes,               # captured to truncation limit
        stderr: string or bytes,
        stdout_truncated: bool,
        stderr_truncated: bool,
        duration_ms: int,
        grace_duration_ms: int or nil          # additional grace after SIGTERM (timeout only)
    }
}
```

**Category enumeration (five values):**

| Category | When emitted |
|---|---|
| `"exit_code"` | Process exited with non-zero code (only when `check: true`) |
| `"timeout"` | `timeout_ms` exceeded; process was terminated |
| `"signal"` | Process was killed by signal other than from `timeout_ms` (e.g., OS killed it for memory pressure) |
| `"spawn_error"` | Failed to start the process (executable not found, permissions, etc.) |
| `"io_error"` | I/O failure on stdin/stdout/stderr (broken pipe, encoding errors that can't be recovered) |

**Output truncation:** captured stdout and stderr are truncated to
64KB each in err records, matching the HTTP API's body truncation
contract. The `stdout_truncated` and `stderr_truncated` flags indicate
when truncation occurred. The truncation applies only to err records;
the result record from successful runs has no truncation.

---

## Cross-platform behavior

### Signal handling

| Method | Unix | Windows |
|---|---|---|
| `p.terminate()` | SIGTERM | TerminateProcess (graceful where possible) |
| `p.kill()` | SIGKILL | TerminateProcess (forceful) |
| `p.interrupt()` | SIGINT | CTRL_C_EVENT (sent to process group) |
| `p.signal("SIGTERM")` | SIGTERM | Same as `p.terminate()` |
| `p.signal("SIGKILL")` | SIGKILL | Same as `p.kill()` |
| `p.signal("SIGINT")` | SIGINT | Same as `p.interrupt()` |
| `p.signal("SIGHUP")` | SIGHUP | Returns err (not supported on Windows) |
| `p.signal("SIGUSR1")` | SIGUSR1 | Returns err |
| `p.signal("SIGUSR2")` | SIGUSR2 | Returns err |

The universal methods (`terminate`, `kill`, `interrupt`) work on all
platforms. The raw `p.signal(name)` works fully on Unix; on Windows it
maps where possible and returns err otherwise.

Cross-platform orchestration code uses the universal methods. Platform-
specific code uses `p.signal(name)`.

### Process groups

- Unix: process group via `setsid()` on the child process; killing the
  group via `killpg()`.
- Windows: job objects with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`;
  killing the job object terminates the children.

When `process_group: false`, no group/job association is made; the
process and its children are independent.

### Shell defaults

| Platform | Default shell | Shell flag |
|---|---|---|
| Unix | `/bin/sh` | `-c` |
| Windows | `cmd.exe` | `/c` |

Override via `{shell: "/bin/bash"}` or `{shell: "powershell.exe"}`.
The library invokes the shell with the platform-appropriate flag
automatically.

### Argv quoting

For `subprocess.run(argv, options)`, the argv list is passed directly
to the OS exec call. No shell parsing, no quoting needed. The OS
handles argument passing safely.

For `subprocess.shell(command_string, options)`, the user constructs
the command string and is responsible for quoting any embedded
arguments. The `subprocess.shell_quote(string)` helper provides safe
quoting:

```nodus
let user_input = get_user_input()
let safe_arg = subprocess.shell_quote(user_input)
let cmd = "grep " + safe_arg + " /var/log/messages"
subprocess.shell(cmd)
```

The helper:
- Unix: wraps in single quotes; escapes any single quotes inside as
  `'\''`
- Windows: applies Microsoft's argument quoting rules per the Win32
  CommandLineToArgvW reference

Recommended pattern in code: when the command string contains dynamic
data, ALWAYS use `shell_quote`. The design doc and STYLE_GUIDE.md
both reinforce this.

---

## Pattern divergence from HTTP (intentional)

Two places where `std:subprocess` diverges from `std:http` patterns,
both deliberate:

### Stream chunking: lines vs bytes

| Namespace | Default chunk mode | Reasoning |
|---|---|---|
| `std:http` | byte chunks | HTTP responses are arbitrary content (binary downloads, streaming JSON, SSE). No natural line boundary. |
| `std:subprocess` | line-buffered | Subprocess output is overwhelmingly line-oriented: command output, log lines, REPL responses. Line-buffered is the dominant pattern. |

Both expose the alternative via `chunk_mode` option. The defaults differ
because the typical use cases differ.

### `check` default

| Namespace | Default failure handling | Reasoning |
|---|---|---|
| `std:http` | Non-2xx returns response (caller checks `r.ok`) | HTTP status is information, not failure. 404 may be expected. |
| `std:subprocess` | Non-zero exit returns err record (`check: true`) | Non-zero exit usually means something went wrong; failures should be explicit. |

Both are configurable. The defaults match the typical use case in each
domain.

These divergences are documented prominently because anyone moving
between the namespaces should know the defaults differ.

---

## Capability surface ceiling

`std:subprocess` is deliberately narrow. Per the capabilities-not-
orchestration principle, the following are NOT included and will not be
added unless real demand surfaces:

- **No built-in retry or restart.** Per `LANGUAGE_VISION.md` principle
  #6: orchestration via workflows, not via capability options. A
  workflow that wants to retry a failed subprocess wraps the call in
  a retry workflow.
- **No process supervision (auto-restart on crash).** A `nodus-supervisor`
  library could provide this in v5.x; the capability layer stays narrow.
- **No PTY (pseudo-terminal) support.** Some programs (REPL clients,
  curses applications) need a PTY rather than pipes. Out of scope for
  v4.0. Possibly a `nodus-pty` registry library if demand emerges.
- **No file descriptor passing.** Advanced Unix IPC pattern. Out of
  scope.
- **No process priority / nice level control.** Niche. Use shell wrapper
  if needed.
- **No CPU/memory limits (cgroups).** Linux-specific. Possibly a
  `nodus-cgroup` library in v5.x.
- **No streaming-stdin file-redirect.** `{stdin: "/path/to/file"}` for
  reading from a file is NOT supported in v4.0. Workaround: read the
  file in Nodus, pass the contents as `stdin: contents`. If real demand
  surfaces, add in v4.x as additive.

### Reconsideration triggers

`std:subprocess` scope expands if:

- Real user issues request a specific addition (10+ issues across
  distinct use cases for the same feature)
- A v4.0 library's implementation requires a primitive only cleanly
  provided by `std:subprocess`
- Cross-platform parity requires features added to handle a specific
  platform's edge cases

Until one of those fires, scope is locked.

---

## Implementation outline

### Substrate: hybrid sync + async

`std:subprocess` is implemented on top of Python's stdlib `subprocess`
module for sync paths and `asyncio.subprocess` for async paths.

Reasoning:

1. Both are in Python's stdlib; no external dependency added
2. Both are mature and well-tested
3. The async asyncio bridge already needed for HTTP (per
   `01-http-api.md`) extends naturally to subprocess
4. Option translation logic is shared between the two paths; only the
   final invocation differs

No new dependencies in `pyproject.toml` beyond what HTTP already adds.

### Async bridging

Same pattern as HTTP. When `subprocess.run_async(...)` is called:

1. Nodus VM suspends the calling coroutine
2. Schedules `asyncio.subprocess.create_subprocess_exec(...)` on the
   VM's asyncio loop
3. Resumes the Nodus coroutine when the result is ready

For `subprocess.spawn`, the spawn itself happens synchronously
(creating the process handle is fast). The channel-based stdout/stderr
reading runs as asyncio tasks that pump data into the Nodus channels.
`p.wait_async()` is the coroutine for awaiting exit.

### Process group / job object implementation

- Unix: child process calls `setsid()` after fork, before exec. Library
  tracks the resulting session ID. `p.terminate()` / `p.kill()` use
  `killpg()` on the group; `signal()` uses `kill()` on the leader.
- Windows: subprocess created in a job object via `CreateJobObjectW`
  and `AssignProcessToJobObject`. Job has
  `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. Termination via
  `TerminateJobObject`.

### Stream pumping

For `spawn`:

- Two asyncio tasks per process: one for stdout, one for stderr
- Each task reads from the process's pipe and pushes onto the Nodus
  channel
- Line buffering with UTF-8 boundary handling implemented in the pump
  loop
- A third asyncio task reads from `p.stdin` channel and writes to the
  process's stdin pipe
- When the process exits, all three tasks drain remaining data and
  close their channels

### File path redirection

When `stdout` or `stderr` is a file path string:

- Open the file with appropriate mode (truncate or append)
- Pass the file descriptor to subprocess as the stream redirect
- No channel pumping needed for that stream
- File closed when process exits

---

## Open implementation questions for Phase 3B

1. **Asyncio loop sharing with HTTP.** Both `std:http` and
   `std:subprocess` use the asyncio bridge. Same VM-level loop, or
   separate loops? Tentative: shared per-VM loop; subprocess and HTTP
   tasks coexist.

2. **Stream pump task lifecycle.** If the consumer doesn't read from
   `p.stdout`, the pump task keeps buffering. Bounded buffer or
   unbounded? Tentative: bounded channel with backpressure; if the
   buffer fills, the pump blocks until the consumer reads. This
   provides automatic backpressure into the OS pipe.

3. **Line buffer size limits.** A pathological process can emit a
   gigabyte-long line. Should there be a line-length cap? Tentative:
   1MB line limit; lines longer than that get split with a `line_truncated`
   flag on the channel record. Reconsider if real demand surfaces.

4. **Process group cleanup on VM shutdown.** When the Nodus VM exits,
   what happens to spawned subprocess handles? Tentative: VM shutdown
   terminates all process groups it spawned with `process_group: true`,
   leaves the others. Document explicitly.

5. **Windows job object inheritance.** Nested job objects have
   complex rules on Windows. Tentative: each spawn creates its own
   job; if Nodus itself is in a job, child jobs nest per Windows
   rules (job-aware programs handle this; most don't matter).

6. **stdin write backpressure.** If user calls `p.stdin.send(...)`
   faster than the process consumes, the pump must apply backpressure.
   Tentative: bounded write buffer; `send()` blocks (or yields, in
   async context) when full.

---

## MCP and A2A consumer validation

### nodus-mcp consumer needs (stdio transport)

The stdio transport spawns an MCP server process and exchanges JSON-RPC
messages over stdin/stdout.

- ✓ `subprocess.spawn(["mcp-server"])` produces a process handle
- ✓ Line-buffered `p.stdout` channel yields one JSON-RPC message per
  line (MCP's wire format is `\n`-delimited JSON)
- ✓ `p.stdin.send(json_string + "\n")` sends a JSON-RPC request
- ✓ `p.stderr` channel for server's diagnostic logging (MCP separates
  stderr from stdout for this reason)
- ✓ `p.wait()` / `p.terminate()` for lifecycle management
- ✓ Process group ensures cleanup of any server children when Nodus
  terminates the server

The stdio transport will likely wrap this in a `StdioTransport` class
internally that exposes `send_message(msg)` / `receive_messages()` /
`close()`, but the underlying primitives are exactly what `std:subprocess`
provides.

### nodus-a2a consumer needs

A2A primarily uses HTTP/gRPC. The only subprocess usage would be
hypothetical: spawning a local agent binary for testing. Not a v0.1
requirement; not validated against here.

---

## Migration impact

`std:subprocess` is a new namespace in v4.0. No migration from v3.x —
there was no `std:subprocess` before. Existing v3.x code that used
Python's subprocess via the embedding API continues to work; migration
to native `std:subprocess` is opt-in.

---

## Bytecode impact

**No new opcodes required. `BYTECODE_VERSION` stays at 4.**

`std:subprocess` is implemented as Python-side builtin functions
registered through the existing builtin registry. User code calls these
functions via the existing `CALL_BUILTIN` opcode. The process handle
returned by `subprocess.spawn` is a Nodus record (existing type); its
channel-based stdout/stderr/stdin use the existing channel primitive
from v1.x.

The frozen-bytecode contract from v1.0 is preserved by this design.
Compiled v3.x `.ndbc` files remain loadable in the v4.0 VM.

---

## Cross-references

- `docs/design/v4/00-phase-0-decisions.md` Decision 8 (subprocess API
  shape)
- `docs/design/v4/00-phase-0-decisions.md` Decision 16 (nodus-mcp v0.1,
  stdio transport)
- `docs/design/v4/01-http-api.md` (sibling design; consistent err
  patterns, divergent defaults documented)
- `docs/language/LANGUAGE_VISION.md` principle #6 (capabilities not
  orchestration)
- `docs/language/DESIGN.md` § "Capability surfaces stay narrow"
- `docs/language/STYLE_GUIDE.md` § "Retry, backoff, and recovery"
- `docs/governance/LIBRARY_ECOSYSTEM.md` § "Not pursued: per-call
  orchestration options in stdlib"
- `docs/governance/TECH_DEBT.md` (Phase 3B open questions to be
  appended in this commit)

---

## Phase 3B implementation handoff

When Phase 3B begins (subprocess namespace implementation), the
following artifacts are ready:

1. This design doc (`04-subprocess-api.md`)
2. Decision 8 (Phase 0)
3. Six open implementation questions enumerated above
4. Substrate locked: Python stdlib `subprocess` + `asyncio.subprocess`
5. Test surface to cover:
   - All 7 public functions
   - All five err categories
   - Stream chunk modes (lines and bytes)
   - Line buffering with UTF-8 boundary handling
   - Env merging behavior (all three modes: inherit / passthrough / none)
   - Timeout with grace period
   - File redirection (stdout/stderr to file)
   - Process group / job object behavior
   - Cross-platform signal mapping (sanity check on both Linux and
     Windows CI)
   - `shell_quote` correctness on both platforms
   - Async variant correctness
   - MCP stdio transport pattern: spawn + line-buffered stdout +
     stdin send + terminate

Estimated implementation effort: 2-3 days focused work for full
coverage including tests. Cross-platform parity (especially Windows
job objects and signal mapping) is the most complex piece; basic
function implementations are straightforward subprocess wrapping.

---

**Phase 1 doc 04-subprocess-api.md: COMPLETE.**
