# Failure and Degradation Model

**Version:** 4.0.3
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This document describes how the Nodus runtime fails, degrades, and what error shapes
it produces in each failure mode. It is the reference for host applications and
embedders designing error-handling strategies around Nodus.

---

## 1. Failure categories

| Category | What causes it | How it surfaces |
|----------|---------------|-----------------|
| Syntax error | Malformed source | `run_source()` returns `ok=false`, `error` has syntax details |
| Runtime error | Script throws, division by zero, nil dereference | `run_source()` returns `ok=false`, `error` has runtime details |
| Sandbox violation | Path access denied, input blocked, call stack overflow | `run_source()` returns `ok=false`, `kind="sandbox"` |
| Resource limit | `max_steps` or `timeout_ms` exceeded | `run_source()` returns `ok=false`, `RuntimeLimitExceeded` |
| Import error | Module not found, relative import escapes root | `run_source()` returns `ok=false` |
| Bytecode version mismatch | Cache from older version | Silent recompile; transparent to caller |
| Internal VM error | Bug in VM implementation | Python exception propagates (bug; should be reported) |

### 1.1 The `ok=false` contract

Since v2.1.0 (BUG-005), `NodusRuntime.run_source()` catches all expected failure modes
and returns `{"ok": false, "error": "...", "stdout": "...", "stderr": "..."}`. Callers
should check `result["ok"]`, not wrap `run_source()` in a `try/except`.

The only case where a Python exception propagates is an internal VM bug (unexpected
`AttributeError`, `TypeError`, etc. in the VM implementation itself). These should be
reported as bugs, not handled in application code.

---

## 2. Syntax errors

**Source:** Lexer (`frontend/lexer.py`) or Parser (`frontend/parser.py`).

**Shape:**
```
result["ok"] = False
result["error"] = "SyntaxError at line N, col M: <message>"
result["stderr"] = "<formatted diagnostic>"
```

Syntax errors include location information (line, column). They are produced before
any execution begins — the VM is never started for a syntax-invalid program.

**Degradation behavior:** Complete. No partial execution. All side effects from module
loading prior to the parse failure are rolled back (modules are not committed to the
cache if their parse fails).

---

## 3. Runtime errors

**Source:** VM execution (`vm.py`).

**Shape:**
```
result["ok"] = False
result["error"] = "RuntimeError: <message>"
result["stderr"] = "<stderr captured before error>"
```

**Sub-categories:**

| Sub-category | Example | Err kind |
|---|---|---|
| Uncaught thrown value | `throw "oops"` without a surrounding `catch` | `"thrown"` |
| Nil dereference | Accessing `.field` on `nil` | `"runtime"` |
| Type error | Arithmetic on a string | `"runtime"` |
| Division by zero | `x / 0` | `"runtime"` |
| Stack overflow (uncaught) | Deep recursion without `max_frames` | Python `RecursionError` → caught as internal error |
| Index out of bounds | `list[100]` on a short list | `"runtime"` |

**Degradation behavior:** Execution stops at the point of the uncaught error. Stdout
captured before the error is available in `result["stdout"]`. Workflow state that was
checkpointed before the error survives in `.nodus/graphs/`.

---

## 4. Sandbox violations

**Source:** Sandbox enforcement in VM builtin handlers.

**Shape:**
```
result["ok"] = False
result["error"] = "sandbox: <message>"
result["stderr"] = ""
```

The err record `kind` is `"sandbox"`. Sandbox violations are catchable by script code
via `try/catch` (they are thrown as runtime errors from inside the builtin).

**Sub-categories:**

| Violation | Trigger | Recoverable in script? |
|---|---|---|
| `allowed_paths` path denied | Script accesses path outside allowed set | Yes (try/catch) |
| `allow_input=False` | Script calls `input()` | Yes (try/catch) |
| `max_frames` exceeded | Call depth limit | Yes (try/catch) |

**Degradation behavior:** Execution stops at the violating builtin call. The script may
catch the sandbox error and continue if it wants.

---

## 5. Resource limits

**Source:** `vm.py::record_instruction`.

**Shape:**
```
result["ok"] = False
result["error"] = "RuntimeLimitExceeded: max_steps exceeded" (or timeout)
```

Resource limits are **not catchable** by script code. They kill the execution unconditionally.

| Limit | Parameter | Check interval |
|---|---|---|
| `max_steps` | `NodusRuntime(max_steps=N)` | Every instruction |
| `timeout_ms` | `NodusRuntime(timeout_ms=N)` | Every `_deadline_check_interval` instructions (~100) |

**Degradation behavior:** Execution stops. Stdout captured before the limit is available.
No cleanup code (finally blocks) runs after a resource limit fires — the VM is terminated.

> **v4.0.1 update — cooperative/coroutine code (SCHED-001 fixed):** Cooperative sleep
> time is no longer counted against the `timeout_ms` deadline. Only active VM instruction
> execution consumes the budget; time spent in `sleep()` calls is excluded. A coroutine
> sleeping 4×100 ms with `timeout_ms=500` now completes cleanly.

> **Important for embedders:** If scripts use `finally` blocks for cleanup (closing handles,
> releasing resources), those `finally` blocks will NOT run if a resource limit fires. Design
> host-side cleanup that does not depend on script `finally` blocks.

---

## 6. Import errors

**Source:** `runtime/module_loader.py`.

**Shape:**
```
result["ok"] = False
result["error"] = "ImportError: <message>"
```

**Sub-categories:**

| Import error | Cause |
|---|---|
| Module not found | `import "nonexistent.nd"` |
| Path escapes project root | `import "../outside.nd"` |
| Circular import (detected) | Module A imports B imports A (detected during load) |
| Stdlib module not found | `import "std:nonexistent"` |

Import errors occur during the module-loading phase, before VM execution of the importing
module begins.

---

## 7. Bytecode cache failure

**Source:** `runtime/bytecode_cache.py`.

**Failure mode:** Corrupt or mismatched cache entry is detected by SHA-256 checksum
verification. The cache entry is silently invalidated and the module is recompiled from
source. This is transparent to the caller.

**Failure mode (version mismatch):** Cache entries with a different `BYTECODE_VERSION`
are silently invalidated. The module is recompiled. Transparent to caller.

**Non-failure from attacker's perspective:** The cache cannot be used to inject arbitrary
code — the checksum verifies integrity, and `marshal` (not pickle) eliminates the
arbitrary-code-execution risk of the previous format.

---

## 8. Workflow failure modes

### 8.1 Step failure

A failing workflow step (step raises an uncaught error) transitions the task to
`FAILED` status in the task graph. Other steps are not affected. The graph is
persisted with the failed status.

### 8.2 Persistence failure

If `.nodus/graphs/` write fails (disk full, permissions), the atomic write (temp →
rename) fails without corrupting the existing snapshot. The graph retains its previous
state. The step may be re-executed on resume, depending on the checkpoint state.

### 8.3 Resuming a failed workflow

`resume_workflow` / `resume_goal` loads the persisted graph state and re-executes
only the pending or failed steps. Successfully completed steps are not re-executed
(idempotent resume, conditional on checkpoint state).

---

## 9. Coroutine failure modes

### 9.1 Unhandled exception in a spawned coroutine

If a spawned coroutine raises an uncaught exception, the exception is recorded on
the coroutine object. The scheduler continues running other coroutines. The spawning
code receives the error when it resumes or waits on the coroutine.

### 9.2 Deadlock

If all coroutines are waiting on channels and no external sender can unblock them,
the scheduler detects no runnable tasks. Behavior: the scheduler loop exits, and
execution returns to the VM's top-level. The embedding result will be `ok=true` with
whatever stdout was captured before the deadlock. This is a design limitation.

### 9.3 Channel closed before receiver consumes

A `recv()` on a closed channel with remaining items succeeds. A `recv()` on an empty
closed channel raises a runtime error (channel exhausted). Script code can catch this.

---

## 10. LSP and DAP server failure modes

The LSP and DAP servers are experimental and operate in a separate process from the VM.
Their failure modes (crash, protocol error, connection drop) are isolated from the main
VM. The main runtime is unaffected by tooling server failures.

---

## 11. Host application guidance

**For robustness:**
- Always check `result["ok"]`; never assume success
- Design host-side cleanup that does not depend on script `finally` blocks (resource limits bypass them)
- Use `max_steps` and `timeout_ms` for untrusted code; the defaults may be too generous
- Use `allowed_paths` for scripts that should not access the filesystem broadly
- Log `result["stderr"]` alongside `result["error"]` — stderr may contain diagnostic context

**For debugging:**
- Enable runtime event tracing to observe execution flow before failure
- Use `nodus.runtime.profiler` to identify slow operations
- The DAP server provides breakpoint debugging for interactive debugging sessions

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — what the runtime guarantees
- `docs/runtime/EMBEDDING.md` — embedding API reference
- `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` — operational guide
- `docs/governance/SECURITY_POSTURE.md` — security threat model
