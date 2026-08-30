# Operator / Embedder Runbook

**Version:** 4.1.1
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This runbook is for engineers who embed Nodus in a host application or operate a
service built on Nodus. It covers: setup, configuration, monitoring, troubleshooting,
and upgrade procedures.

---

## 1. Embedding setup

### 1.1 Install

```bash
pip install nodus-lang==4.1.1
```

For the FastAPI/Uvicorn server stack (experimental):
```bash
pip install "nodus-lang[server]==4.1.1"
```

### 1.2 Minimal embedding

```python
from nodus import NodusRuntime

runtime = NodusRuntime(
    max_steps=100_000,
    timeout_ms=5_000,
    allowed_paths=["/app/scripts"],
    allow_input=False,
    max_frames=500,   # tighter than the 10,000 default
)
result = runtime.run_source(source_code)
if not result["ok"]:
    logger.error("script_failed", error=result["error"], stderr=result["stderr"])
```

### 1.3 Construction once, run many times

`NodusRuntime` is designed to be constructed once and reused across multiple `run_source()`
calls. Each call is independent — globals are not shared between calls. The runtime caches
compiled module bytecode across runs.

If you need to reset the runtime state (e.g., clear module cache), call `runtime.reset()`.

---

## 2. Configuration reference

| Parameter | Type | Default | When to change |
|-----------|------|---------|----------------|
| `max_steps` | `int \| None` | `MAX_STEPS` (~10M) | Lower for untrusted/short-running scripts |
| `timeout_ms` | `int \| None` | `None` (no deadline) | Pass an explicit value (e.g. `5000`) for short-lived sandboxed scripts. The default `None` is correct for servers, loops, and MCP/A2A hosts. Cooperative sleep time is excluded from the budget — only active instruction execution counts (SCHED-001 fixed). |
| `max_stdout_chars` | `int \| None` | `MAX_STDOUT_CHARS` | Lower for log-constrained environments |
| `project_root` | `str \| None` | `None` | Set to project directory when scripts use imports |
| `allowed_paths` | `list[str] \| None` | `[os.getcwd()]` (CWD jail) | Default jails to working directory. Pass `None` to allow unrestricted access. Set explicit paths for untrusted scripts that need access outside CWD. |
| `allow_input` | `bool` | `False` | Keep `False`; set `True` only for interactive use cases |
| `max_frames` | `int \| None` | `None` → `MAX_STACK_DEPTH` (10,000) | Tighten to 200–1000 for untrusted code. This is the only limit left when `max_steps` and `timeout_ms` are both `None` |
| `allow_subprocess` | `bool` | `True` | Set `False` unless scripts must shell out |
| `allow_network` | `bool` | `True` | Set `False` unless scripts must make HTTP calls |
| `allow_env` | `bool` | `True` | Set `False` to keep scripts away from host credentials |
| `allowed_commands` | `list[str] \| None` | `None` (any command) | Allowlist executables when `allow_subprocess=True` |
| `allowed_hosts` | `list[str] \| None` | `None` (any host) | Allowlist hosts when `allow_network=True` |
| `on_error` | `callable \| None` | `None` | Set to observe spawned-coroutine failures as they occur |
| `coroutine_timeout_ms` | `int \| None` | `None` | Per-coroutine deadline |
| `event_sinks` | `list \| None` | `None` | Attach runtime event sinks for monitoring |

> **Event retention is bounded, and VM bookkeeping is off unless observed.** The bus
> keeps the most recent 50,000 events (`NODUS_EVENT_HISTORY` to change it, `0` to keep
> none while still feeding sinks), and `vm_call` / `vm_return` / `vm_instruction_batch`
> are emitted only when a sink is attached or `NODUS_TRACE_VM_EVENTS=1` is set.
>
> This matters for the long-lived-runtime pattern below: before #522 each run's VM held
> its entire event history until collected — 74 MB per 3M instructions, about 23 bytes
> per instruction executed — with no consumer on the default path. `function_calls`,
> `returns` and `instructions_executed` are counters kept independently of the bus, so
> `get_execution_stats()` is unaffected. See
> [RUNTIME_EVENTS.md](RUNTIME_EVENTS.md#retention).

> **The three `allow_*` capability switches deny by default** as of v5.0.0 (#405).
> A bare `NodusRuntime()` cannot start subprocesses, open network connections, or read
> the process environment; grant explicitly with
> `NodusRuntime(allow_subprocess=True, allow_network=True)`. `allowed_paths` is
> unchanged — it already defaulted to a CWD jail.
>
> This paragraph said the opposite ("default to permissive") from v5.0.0 until v5.3.0.
> That was true through v4.2.0. **Advice written against the old default is backwards**,
> including "a bare runtime can shell out", which several documents relied on. The CLI is
> deliberately unaffected: it builds a `VM` directly and never constructs a
> `NodusRuntime`, because what deny-by-default protects is work you did not fully author.

> **`max_frames=None` means `MAX_STACK_DEPTH` (10,000)**, the same cap the CLI applies,
> so runaway recursion raises `Call stack overflow` even with `max_steps=None` and
> `timeout_ms=None`. Through v4.1.1 it meant *no cap at all* and that configuration grew
> frames until the process ran out of memory — if you are pinned to 4.1.1 or earlier, pass
> `max_frames` explicitly. See [#350](https://github.com/Masterplanner25/Nodus/issues/350).

---

## 3. Monitoring

### 3.1 Success/failure rate

Check `result["ok"]` on every `run_source()` call and emit a metric or log entry.

```python
result = runtime.run_source(code)
metrics.increment("nodus.run", tags={"ok": str(result["ok"])})
if not result["ok"]:
    logger.warning("nodus.run.failed", error=result["error"])
```

### 3.2 Resource limit hits

`RuntimeLimitExceeded` appears in `result["error"]`. Track separately from script
errors — resource limit hits indicate scripts that are too slow or too big, not
script bugs.

```python
if not result["ok"] and "RuntimeLimitExceeded" in result.get("error", ""):
    metrics.increment("nodus.run.limit_exceeded")
```

### 3.3 Sandbox violations

`kind="sandbox"` in the error indicates a script tried to access a restricted resource.

**What a refusal promises — and what it does not.** Two fields are contractual:

| Field | Promise |
|---|---|
| `error["kind"]` | `"sandbox"` for every capability refusal. Classify on this. |
| `error["message"]` | **Contains the name of the flag that grants the capability** — `allow_subprocess`, `allow_network`, `allow_env`. |

The *wording* around the flag name is not contractual and has changed: v5.0.0
rephrased refusals to `Blocked: subprocess execution is not granted; pass
allow_subprocess=True to NodusRuntime to allow it`. An embedder matching the old
sentence saw four confinement tests go red while its guest was fully confined —
the refusals were firing correctly, with `kind: "sandbox"` and `capability_denied`
on the event bus. Assert on the flag name or on `kind`, never on the sentence.

`tests/test_downstream_contracts.py` pins both fields.

### 3.3.1 Enumerating the gated surface

To assert confinement from your own test suite, read the gate list as data rather
than scraping our source:

```python
from nodus.runtime.capability import GATED_BUILTINS, GATED_BUILTIN_NAMES

GATED_BUILTIN_NAMES                     # frozenset of all 31 gated builtins
GATED_BUILTINS["allow_subprocess"].names       # the 7 subprocess builtins
GATED_BUILTINS["allow_network"].capability     # "network" — the event-bus label
```

Each entry carries `flag`, `capability`, `description`, `arity` and `names`. The
registry builds its refusing stubs from this same data, so the published list and
the enforced gate cannot disagree.

Added in v5.0.1. Before it, the only route was a regex over
`BuiltinRegistry.register_all` — which broke on the v5.0.0 refactor that moved the
names into the `else:` branch, and began capturing flag names out of the denial
helper and reporting them as leaked builtins.

Note that `GATED_BUILTINS` is a *different* list from `BUILTIN_CAPABILITIES`:
the former is what is never registered when a flag is `False`, the latter is what
consults the capability policy at call time. They overlap by design; every
registration-gated builtin also consults the policy except `subprocess_shell_quote`
(string manipulation, runs nothing), and `BUILTIN_CAPABILITIES` is the larger of
the two, because five capabilities have no registration flag at all.

### 3.3.1a What a policy can see

Ten capabilities, of which only three have an `allow_*` switch:

| Capability | Flag | Reaches |
|---|---|---|
| `subprocess` | `allow_subprocess` | `subprocess_run`, `subprocess_shell`, … |
| `network` | `allow_network` | `http_get`, `http_post`, `http_stream`, … |
| `env` | `allow_env` | `env_get`, `env_set`, … |
| `fs.write` | — (path jail) | `write_file`, `append_file`, `mkdir`, `fs_delete` |
| `fs.read` | — (path jail) | `read_file`, `list_dir`, `path_exists`, `hash_*_file` |
| `tool.invoke` | — | `tool_call`, `tool_invoke`, `__action_tool` |
| `syscall` | — | `syscall` |
| `agent.call` | — | `agent_call`, `__action_agent` |
| `memory.read` | — | `memory_get`, `memory_has`, `memory_keys`, `memory_recall_*` |
| `memory.write` | — | `memory_put`, `memory_delete`, `memory_share` |

The bottom six are **policy-only**: there is no registration flag, so a policy is
the only way to refuse them. Through v5.2.0 the last five did not exist, and a
`CapabilityPolicy` that denied everything denied none of those surfaces (#473).
`FS_READ` was declared from v5.0.0 and attached to nothing until v5.3.0 (#467).

The `__action_*` entries are the lowerings of the `action` DSL forms.
`action tool "x"` reaches `__action_tool` without passing through `tool_call`,
and a host can shadow neither, so both spellings are governed.

**`ALL_CAPABILITIES` is closed but not fixed** — it went from five names to ten in
v5.3.0. Validate against the frozenset, never against a copy of it.

**Cost.** A governed builtin builds a `CapabilityRequest` and consults the floor
even with no policy installed: ~0.8 µs per call, against ~25 µs for a builtin call
on CPython. Ungoverned builtins pay nothing — the dict lookup already happened.

**Every builtin is classified.** `NO_AUTHORITY_BUILTINS` names the 227 that carry
no authority, grouped by why, and a test requires the two sets to cover
`BUILTIN_NAMES` exactly. A new builtin fails the suite until somebody decides
which side it is on — the point being that "is this governed?" stops depending on
whether anyone remembered.

### 3.3.1a-2 Read-only context vs editable files

`allowed_paths` bounds what the runtime may touch. `writable_paths` narrows the
subset it may *write*:

```python
NodusRuntime(
    allowed_paths=["/repo"],          # readable
    writable_paths=["/repo/src"],     # subset that may be written
)
```

```
read  /repo/ctx/readme.txt   ok
write /repo/src/out.txt      ok
write /repo/ctx/out.txt      Blocked: path 'ctx/out.txt' is readable but not writable
```

CLI: `nodus run app.nd --allow-paths /repo --writable-paths /repo/src`.

**Omitting it changes nothing** — `writable_paths=None` means "everything
readable", which is every release through 5.2.0. `[]` is a statement, not an
omission: it refuses every write while leaving reads alone. Both checks always
run, so a writable path grants nothing that `allowed_paths` does not already
allow; declaring one outside the read jail is refused at construction rather
than silently ignored.

**No environment variable, deliberately.** `NODUS_ALLOWED_PATHS` exists to widen
a *default* jail when the caller passed nothing. There is nothing to widen here,
so a variable could only narrow — and write confinement that moves with ambient
state produces a program that works locally and is refused in production with no
difference in the code.

**What this does not cover: subprocess children.** The runtime path-checks a
subprocess's `cwd` and its stdout/stderr redirect targets, so those obey both
lists. It cannot constrain what the spawned program itself writes — that is the
OS's business, not the VM's. If `allow_subprocess=True`, `writable_paths` is not
a filesystem boundary; it scopes the *runtime's* writes only. Use OS-level
confinement if you need the stronger claim.

### 3.3.1b Syscalls are gated twice

A `syscall(...)` reaches the policy **twice**, and the two are different intents:

| | Capability | Refuses |
|---|---|---|
| the `syscall` builtin | `syscall` | every syscall, whatever it is |
| the spec's own field | `SyscallSpec.capability` — e.g. `memory.write` | that authority, however it is spelled |

```
deny memory.write  -> saw ['syscall', 'memory.write']   Blocked
deny syscall       -> saw ['syscall']                   Blocked (never reaches the spec gate)
deny nothing       -> saw ['syscall', 'memory.write', 'syscall', 'memory.read']
```

So "no syscalls at all" and "no memory writes, whether through `memory_put` or
`sys.v1.memory.put`" are both expressible. A refusal at either gate raises with
`kind == "sandbox"`; it is **not** returned as a `{"status": "error"}` envelope,
which would make a capability refusal indistinguishable from a handler that
failed.

`SyscallSpec.capability` was published by `syscall_list()` and read by nothing
from v4.0 through v5.2.0 (#478). `register_syscall` now refuses a spec whose
capability is missing or outside `ALL_CAPABILITIES`, so what the registry
advertises is always something a policy can act on.

### 3.3.2 Reaching the live VM

`runtime.active_vm()` returns the VM from the most recent run, or `None` before
the first one — for reading the event bus or asserting the sandbox flags actually
in force. The accessor is supported; the `VM` object it returns is internal and
its attributes are not. `_get_active_vm()` is retained as an alias for embedders
that already pin it.

### 3.3.3 Builtin names cannot be overridden

`register_function()` raises `ValueError: Cannot override built-in function: <name>`
for any name in the builtin set. This is relied on as a security boundary: because
a builtin cannot be aliased, a host can install a fail-loud guard under a name a
guest might otherwise reach and know the guard is the only thing there. It is
pinned by test, not merely documented.

### 3.4 Stdout/stderr size

Monitor `len(result["stdout"])` relative to `max_stdout_chars`. If scripts frequently
hit the truncation limit, scripts may be producing too much output or the limit is too
low.

---

## 4. Troubleshooting

### 4.1 Script fails with `ok=false`

1. Check `result["error"]` for the error type and location
2. Check `result["stderr"]` for additional diagnostic output
3. For syntax errors: fix the script; they are always script-side issues
4. For runtime errors: check the error `kind` and `message`
5. For sandbox errors: check `allowed_paths` configuration

### 4.2 Script runs but produces no output

- Verify `result["ok"]` is `True`
- Verify the script calls `print()` (Nodus scripts must explicitly print; no auto-print)
- Check `result["stdout"]` directly
- Check `max_stdout_chars` — if the script produced more than the limit, stdout is truncated

### 4.3 Script hangs

- Set `timeout_ms` if not already set — without it, scripts with infinite loops run until
  `max_steps` fires (which may be slow)
- Use `max_steps` as a secondary guard
- Check for deadlocked coroutines (all coroutines waiting on channels with no sender)

### 4.4 Import errors

- Set `project_root` to the directory containing the script's imports
- Verify the import path is relative to the project root
- For stdlib imports (`std:json`, etc.): these are bundled — if they fail, the nodus-lang
  install may be corrupt (reinstall)

### 4.5 Module cache corruption

If a `ModuleError` mentions the cache or bytecode version mismatch:
```bash
rm -rf .nodus/cache/
```
The cache rebuilds automatically on the next run. This is always safe.

### 4.6 Workflow resume fails

If `resume_workflow()` fails:
1. Check `.nodus/graphs/<id>.json` exists and is valid JSON
2. Verify `project_root` is set consistently across the original run and the resume
3. If the graph is corrupt, delete `<id>.json` and restart the workflow from scratch

---

## 5. Upgrade procedure

### 5.1 Patch release (x.y.Z)

Patch releases are backward-compatible. Upgrade by replacing the `nodus-lang` package.
No script changes required. No API changes. The bytecode cache may be invalidated if the
patch bumps `BYTECODE_VERSION` (rare; noted in CHANGELOG.md).

```bash
pip install nodus-lang==4.1.Z
```

After upgrade, verify with `nodus --version` and a smoke-test run.

### 5.2 Minor release (x.Y.z)

Minor releases add functionality. Upgrade is safe; no breaking changes to stable APIs.
New stdlib functions may be available in scripts. Review CHANGELOG.md for new features.

### 5.3 Major release (X.y.z)

Major releases may include breaking changes to the language, stdlib, or embedding API.
Before upgrading to a major version:

1. Read CHANGELOG.md carefully — all breaking changes are listed
2. Read `docs/migration/` for migration guides (e.g., `v3-to-v4.md`)
3. Review `docs/governance/COMPATIBILITY_MODEL.md` for what changed
4. Test all scripts against the new version in a non-production environment
5. Upgrade `BYTECODE_VERSION` handling if persisting compiled bytecode (most embedders
   do not persist bytecode — they compile from source on each run)

---

## 6. Production checklist

Before deploying a Nodus-embedded application to production:

- [ ] `NodusRuntime` is configured with explicit `max_steps` and `timeout_ms`
- [ ] `allowed_paths` is set if the application handles untrusted scripts
- [ ] `allow_input=False` (the default; verify it has not been overridden)
- [ ] `max_frames` is tightened for untrusted scripts (the default is 10,000 — a real
      cap, but a generous one)
- [ ] `allow_subprocess`, `allow_network` and `allow_env` are granted **only** where
      scripts genuinely need them. All three default to **`False`** as of v5.0.0, so a
      bare `NodusRuntime()` already cannot shell out, open sockets, or read the process
      environment — the checklist item is to confirm nothing has granted them, not to
      turn them off. (Advice written against the pre-5.0.0 permissive defaults reads
      backwards. `nodus run` and the rest of the CLI are deliberately unaffected: the
      CLI builds a `VM` directly, and deny-by-default protects work you did not fully
      author.)
- [ ] `allowed_commands` / `allowed_hosts` are set if subprocess or network access
      is enabled
- [ ] `result["ok"]` is checked on every `run_source()` call
- [ ] Error logging includes both `result["error"]` and `result["stderr"]`
- [ ] Nodus version is pinned in `requirements.txt` or `pyproject.toml`
- [ ] Upgrade procedure has been tested (at minimum, a version bump smoke test)
- [ ] Workflow persistence directory (`.nodus/`) is on a persistent volume if workflows are used
- [ ] If workflows are used in production, `SQLiteWorkflowStore` is configured (see §6.1)
- [ ] Work that must survive a crash runs inside a workflow, not a bare `spawn()` (see §6.2)
- [ ] Every callable passed to `register_function()` is host-authored and trusted (see §6.3)

---

## 6.1 Workflow store durability (#174)

The default workflow runner uses `LocalWorkflowStore` — file-backed JSON at
`.nodus/workflow_framework/runs/`. This store is **not crash-safe**: a process kill
between the read-modify-write of a run file can corrupt run state. It is appropriate
for development and short-lived scripts only.

For any production deployment where workflows must survive a restart:

```python
from nodus_lang_workflow.runner import configure_default_workflow_runner

configure_default_workflow_runner(backend="sqlite", path=".nodus/workflow.db")
```

Call this once at application startup, before any `run_workflow()` or
`NodusRuntime` usage that triggers a workflow.

**Or set it in the environment**, which needs no startup hook and applies to the
default runner, `nodus serve` and the CLI alike:

```bash
NODUS_WORKFLOW_STORE_BACKEND=sqlite
NODUS_WORKFLOW_STORE_PATH=/var/lib/myapp/workflow.db   # optional
```

Until 5.7.0 these were honoured by `nodus serve` only, and the default runner
every embedder reaches through `run_workflow()` ignored them (#174). An unknown
backend name is refused rather than falling back to the JSON store, so a
misspelling cannot quietly cost you the durability you asked for.

> **Switching backends does not move existing runs.** Runs recorded in the JSON
> store are invisible to a SQLite one and vice versa — an in-flight `waiting` run
> becomes unresumable rather than relocated, and `nodus workflow migrate-state`
> migrates graph *snapshots*, not store backends. Switch when nothing is in
> flight, or drain first.

`SQLiteWorkflowStore` uses WAL mode for atomic writes and survives unexpected
process exits. The default path can be any writable path on a persistent volume.

The HTTP server (`nodus serve`) accepts `--workflow-store-backend sqlite` and
`--workflow-store-path PATH` flags for the same effect.

---

## 6.2 A bare coroutine is transient — only a workflow survives a crash (#180)

Nodus has **two** units of concurrent work, and only one of them is durable. The
distinction is invisible in the API and costs in-flight work when it is discovered
by a crash rather than by reading this.

| | Bare coroutine | Workflow step |
|---|---|---|
| Started by | `spawn(coroutine(fn))` | `run_workflow(...)` |
| State lives in | process memory only | `.nodus/graphs/` + the workflow store |
| After a `SIGKILL` / OOM / power loss | **gone, with no record that it ran** | replayable |
| Recovery API | none | `rehydrate_runs(vm_factory)` |

So an embedder building a job-processing service on `spawn()` loses every in-flight
job on an unclean exit, and nothing reports the loss — there is no partial record to
find afterwards, because none was ever written.

**What to do:** if the work must survive a restart, make it a workflow step. A
workflow's step state is persisted as it goes, and `rehydrate_runs()` replays runs
that were interrupted:

```python
from nodus_lang_workflow.runner import get_default_workflow_runner

runner = get_default_workflow_runner()
resumed = runner.rehydrate_runs(vm_factory=my_vm_factory)   # call at startup
```

Pair this with §6.1: rehydration can only replay what the store durably holds, so
`LocalWorkflowStore` weakens the guarantee this section is about.

`spawn()` remains the right tool for concurrency *within* a run — fan-out, overlapping
I/O, anything whose lifetime is bounded by the call that started it. The rule is about
what must outlive the process, not about which primitive is better.

---

## 6.3 `register_function()` runs host code with no sandbox (#169)

A callable registered with `register_function()` executes **in the host Python
process, with everything the host process can reach**. The runtime's confinement
flags — `allowed_paths`, `allow_subprocess`, `allow_network` — bound what the *guest
script* may do. They do not bound the host function, which can read any file the
process can, import any module, mutate runtime internals, and call `os._exit()`.

**This is by design, not a gap to work around.** `register_function()` is the seam
where a host deliberately lends the guest one of its own capabilities, and a host
function that could not act with host authority would be useless. Two consequences
follow, and both are load-bearing:

- **Only register callables you authored or audited.** Never register something
  supplied by the same party as the untrusted script. The guest's confinement says
  nothing about what your function does on its behalf.
- **A registered function is a capability grant.** Registering a `read_file` helper
  hands the guest file access whatever `allowed_paths` says, because the check is on
  the runtime's own filesystem builtins, not on your function.

Two properties of the surface work in your favour and are pinned by test, so you can
rely on them:

- **A builtin cannot be overridden.** `register_function()` refuses a name that is
  already a builtin (see §3.3.3), so a host can install a fail-loud guard under a
  guest-reachable name and know the guard is the only thing there.
- **The confinement flags are keyword-only, and `__init__` takes no `**kwargs`**, so
  a renamed or misspelled flag raises instead of being silently swallowed — which is
  the failure that leaves a guest running unconfined while mock-based tests stay green.

**For untrusted plugin code, use `nodus-extension` instead.** It loads third-party
extensions in a **subprocess** with a declared capability manifest, which is the
isolation `register_function()` deliberately does not provide.

### Declare the argument contract

`schema=` checks the arguments before every call, with the same validator
`std:tool` uses, so both surfaces accept the same declarations and report
failures identically:

```python
runtime.register_function(
    "host_write", write_file, arity=2,
    schema={"path": "string", "contents": "string"},
    returns_schema={"bytes": "int"},
    requires="fs.write",
)
```

The schema is an **ordered** map of parameter name to Nodus type, applied
positionally — a host function takes positional arguments, unlike a `std:tool`
handler which receives one args map. It must name exactly `arity` parameters, and
a variadic registration is refused rather than partly covered. A misspelled type
fails at registration, not on the first call.

Until 5.7.0 there was no such option (#493), so a host function had arity and
nothing else: `write_file(42, {"not": "a string"})` ran and returned
`"wrote 42 (1 bytes)"`, because `len()` of the map is 1 and nothing looked wrong.

> **A schema is a type contract, not a sandbox.** It constrains the *shape* of
> what reaches your function; it says nothing about what your function then does
> with its host authority. Everything above about trusting the callable still
> applies in full.

### Let the program declare what it needs

A `.nd` program can declare the host surface it expects (#489):

```
extern delegate(who: string, task: string) -> string
```

`NodusRuntime` then refuses **before executing anything** if the program declares
a function this runtime has not registered:

```
this program declares extern 'delegate', which this runtime has not
registered. Register it with `register_function(...)` before running, or
remove the declaration.
```

That matters operationally: without it, a missing registration surfaces at the
call, partway through a run that may already have written files, charged
something, or resumed a workflow. The declaration exists precisely so the
mismatch is knowable without executing.

It is a **compatibility contract in both directions** — the program says which
vocabulary it speaks, the runtime says which it provides, and a mismatch is
detectable by loading neither. A program that declares nothing is unaffected, so
this costs an existing deployment nothing until it opts in.

#### `nodus run` does not pre-flight, deliberately

The CLI has no way to register a host function, so pre-flighting there would
refuse **every** program declaring an `extern` — including the case the feature
exists for, which is writing a program locally before handing it to a host. So
`nodus run` runs it, and the call fails when it is reached (#664):

```
Undefined function: delegate -- declared `extern` in this program, but nothing
has registered it. `nodus run` does not register host functions; run it from a
host that calls register_function("delegate", ...), or remove the declaration.
```

`nodus check` still passes such a file: the name **is** declared, and reporting
it would put a warning on every correct extern-declaring program.

The practical consequence for developing one: everything except the extern calls
can be exercised from the CLI, and the calls themselves need a host. A small
Python driver that registers stubs and calls `run_file` is the shortest path — it
is also what pre-flights the declarations.

---

## 7. Companion library notes

### nodus-mcp

When embedding with nodus-mcp (`pip install nodus-mcp`):
- The MCP server and client are managed through `NodusRuntime.register_function()` or
  the nodus-mcp Python API directly
- Server-initiated requests (roots/list, sampling/createMessage) are stdio-compatible in v0.1

### nodus-a2a

`pip install nodus-a2a` installs the **AgentCoordinator** layer — `AgentRegistry`,
`AgentCoordinator`, `DelegationRequest`, `DeadLetterService`, `StuckRunWatchdog`. It has
no nodus-lang dependency and no HTTP server.

The A2A **wire-protocol adapter** (`A2AHttpServer.serve_in_thread()`, `token_validator`,
Agent Card discovery, message-only v0.1 scope) is a different codebase and is **not on
PyPI**. It lives at
[`nodus-a2a-wire`](https://github.com/Masterplanner25/nodus-a2a-wire); install from git.

Earlier revisions of this runbook documented the wire adapter's API under
`pip install nodus-a2a`. Following it would produce an `ImportError`. Verified against
PyPI 2026-08-07: published `nodus-a2a` 0.1.0 is *"Agent-to-Agent coordination: registry,
delegation, dead letter, and watchdog"*.

---

## Related documents

- `docs/runtime/EMBEDDING.md` — full embedding API reference
- `docs/runtime/EXECUTION_INVARIANTS.md` — runtime guarantees
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — failure modes
- `docs/governance/SECURITY_POSTURE.md` — security configuration
