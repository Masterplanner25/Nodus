# Nodus v4.0.1 — Eval Bug Report

**Eval date:** 2026-06-10  
**Version:** v4.0.1 (PyPI, POST-PUBLISH)

---

### BUG-401-001: @retry with missing nodus-retry dep silently calls function 0 times

**Severity:** HIGH  
**Subsystem:** runtime / annotations  
**Affects:** v4.0.1

**Repro:**
```nd
import "std:retry" as retry

@retry(max_attempts: 3i, backoff_ms: 1i)
fn flaky() {
  error("oops")
}
let r = flaky()
```
(Run without `pip install nodus-retry`)

**Expected:** Either a compile-time or import-time error saying `nodus-retry` is required, OR the function runs once as a no-retry fallback.

**Actual:** The function body runs 0 times. Returns `{"kind": "dependency_error", "message": "nodus-retry package not installed"}`. No indication at annotation parse time or import time.

**Fix direction:** The `@retry` lowering calls `retry_call()` which internally checks for the package. Move the check to annotation compile time or import resolution: fail fast with a clear install instruction rather than silently skipping the function body.

---

### BUG-401-002a: @exactly_once does not enforce idempotency

**Severity:** CRITICAL  
**Subsystem:** runtime / annotations / effects  
**Affects:** v4.0.1

**Repro:**
```nd
@exactly_once
fn send_email(addr) {
  print("sending to \(addr)")
  addr
}
let r1 = send_email("a@b.com")
let r2 = send_email("a@b.com")
```

**Expected:** Second call with same args is a no-op — body does not execute again, cached result is returned.

**Actual:** Body executes on both calls. "sending to a@b.com" prints twice.

**Fix direction:** The `effect_resolve()` / `effect_pending` / `effect_complete` lowering chain is not working correctly. The action ID computation or the cache lookup is not matching the second call. Likely the action ID is computed differently each call (e.g., using a runtime object address instead of argument values).

---

### BUG-401-002b: @exactly_once return value is always nil

**Severity:** CRITICAL  
**Subsystem:** runtime / annotations  
**Affects:** v4.0.1

**Repro:** Same as BUG-401-002a.

**Expected:** `r1` = `"a@b.com"` (the function body's return value).

**Actual:** `r1` = `nil`.

**Fix direction:** The compiler lowering for `@exactly_once` wraps the body and calls `effect_complete(result)`, but the result is not threaded through to the call site. The lowered code likely discards the return value.

---

### BUG-401-003: Trailing comma in multiline list literal is a syntax error

**Severity:** MEDIUM  
**Subsystem:** parser  
**Affects:** v4.0.1

**Repro:**
```nd
let lst = [
  1i,
  2i,
]
```

**Expected:** Valid syntax, `len(lst)` = 2. (Python, JavaScript, Rust, and Swift all allow trailing commas in collection literals.)

**Actual:** `Syntax error at line 4:1: Unexpected ']' in expression`

**Fix direction:** In the multiline-list parser, after consuming a value and a comma, allow `]` as the next token (treat it as a trailing comma terminator rather than requiring another value). Mirrors the Python parser's rule.

---

### BUG-401-004: allowed_commands sandbox is not enforced

**Severity:** CRITICAL  
**Subsystem:** sandbox / subprocess  
**Affects:** v4.0.1

**Repro:**
```python
from nodus import NodusRuntime
rt = NodusRuntime(timeout_ms=None, max_steps=None, allowed_commands=["python"])
r = rt.run_source('''
import "std:subprocess" as sub
let r = sub.run(["git", "--version"])
print(r.stdout)
''')
print(r['ok'], r['stdout'])
```

**Expected:** `ok=False`, error type `SandboxError`, message indicates `git` is not in the allowed commands list.

**Actual:** `ok=True`, `stdout='git version 2.52.0.windows.1'`. The git process ran without restriction.

**Fix direction:** The `allowed_commands` check in `subprocess_module.py` (or wherever `sub.run` is implemented) is not being applied. Verify: (a) that `NodusRuntime.__init__` actually passes `allowed_commands` into the VM/builtin registry; (b) that the check is evaluated at subprocess invocation time, not just at flag construction. Also test in CLI mode (`nodus run --allowed-commands python script.nd`).

---

### BUG-401-005: allowed_hosts cannot be tested without optional httpx dep

**Severity:** LOW  
**Subsystem:** docs / packaging  
**Affects:** v4.0.1

**Repro:** Install `nodus-lang==4.0.1` (base, no extras), try `http.get(url)`.

**Expected:** Either httpx bundled in base, or the `allowed_hosts` test is documented as requiring `nodus-lang[http]`.

**Actual:** `RuntimeError: std:http requires the httpx package — install it with: pip install 'nodus-lang[http]'`

**Fix direction:** The error message is actually good. No code change needed. Document in release notes that `allowed_hosts` verification requires the `[http]` extra. Low priority.

---

### BUG-401-006: event_sinks never called — emits zero events

**Severity:** MEDIUM  
**Subsystem:** embedding / events  
**Affects:** v4.0.1

**Repro:**
```python
from nodus import NodusRuntime
events = []
rt = NodusRuntime(timeout_ms=None, max_steps=None, event_sinks=[lambda e: events.append(e)])
rt.run_source('let x = 1i + 2i')
print(len(events))  # → 0
```
Also tested with a workflow: `events after workflow: 0`.

**Expected:** At least some events emitted for coroutine lifecycle, workflow steps, or instruction milestones.

**Actual:** Zero events captured across all test scenarios.

**Fix direction:** Verify that `NodusRuntime.__init__` correctly wires `event_sinks` into `vm.event_bus` BEFORE the VM begins execution. If the bus is wired after-the-fact or to a different bus instance than what the VM uses internally, sinks will never fire.

---

### BUG-401-007: _last_vm is still publicly accessible despite changelog claim

**Severity:** LOW (cosmetic / docs gap)  
**Subsystem:** embedding / docs  
**Affects:** v4.0.1

**Repro:**
```python
rt = NodusRuntime(timeout_ms=None, max_steps=None)
rt.run_source('let x = 1i')
print(rt._last_vm)  # → <nodus.vm.vm.VM object>
```

**Expected:** `AttributeError`, or None, consistent with changelog claim that `_last_vm` is now private and `get_execution_stats()` is the replacement.

**Actual:** `_last_vm` is still accessible and returns the VM object.

**Fix direction:** Either rename to `__last_vm` (name-mangled, truly private) or add a deprecation warning when accessed. Low urgency — `get_execution_stats()` works and is the documented API.

---

### BUG-401-008: channel() named-argument syntax not supported; docs show Python-style notation

**Severity:** MEDIUM (docs / discoverability)  
**Subsystem:** stdlib / docs  
**Affects:** v4.0.1

**Repro:**
```nd
let ch = channel(maxsize: 2i)
```

**Expected:** Creates a bounded channel with capacity 2. (The CLAUDE.md and changelog describe it as `channel(maxsize=N)`.)

**Actual:** `Syntax error: Expected ')', got ':'`

The correct call is `channel(2i)` (positional only).

**Fix direction:** Update all documentation to show `channel(2i)` not `channel(maxsize=N)`. The `=N` notation is Python parameter documentation style, not valid Nodus call syntax. A Nodus-native named-argument form (if desired) would be `channel(maxsize: 2i)` but that also fails, confirming named args are not supported for builtins.
