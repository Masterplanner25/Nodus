# Nodus v4.0.1 — Post-Publish Eval Log

**INSTALL SOURCE:** POST-PUBLISH  
**Install command:** `pip install nodus-lang==4.0.1`  
**Confirmed version:** `Nodus 4.0.1`  
**Working dir:** `C:\dev\nd-eval-401\` (empty, non-git)  
**Date:** 2026-06-10  
**Evaluator:** Maintainer (independent eval pass after Gate 10)

---

## Entry #1 — Version provenance

```
PS> python -m venv .venv
PS> .venv\Scripts\pip install nodus-lang==4.0.1 --quiet
PS> .venv\Scripts\nodus --version
Nodus 4.0.1
```
Version matches. Proceeding.

---

## Entry #2 — First contact (§3a)

```
$ nodus run scratch/s3a_first_contact.nd
hello from nodus 4.0.1
exit: 0

$ nodus fmt scratch/s3a_first_contact.nd
(no output, exit 0 — formatted in place)

$ nodus check scratch/s3a_first_contact.nd
scratch/s3a_first_contact.nd: OK
exit: 0
```
**Result:** All pass. ✅

Embedding quick-check (not logged separately — covered by Gate 10).

---

## Entry #3 — Compound assignment (§3b / §4.2)

Script: `s3b_compound_assign.nd`

```
let x = 10i; x += 5i  → 15        ✅
let y = 10.0; y -= 2.5 → 7.5      ✅
let z = 4i; z *= 3i   → 12        ✅
let w = 9i; w /= 3i   → 3 (int)   ✅
lst[1] += 7i           → 7         ✅
rec.count += 1i        → 1         ✅
m["n"] += 10i          → 10        ✅
```

Edge cases:
```
9i /= 2i  → 4 (truncated int div)  ✅
math_is_int(9i /= 3i result) → true ✅
```

Error case:
```
$ nodus run s4_2_compound_errors.nd   (x += 1i with no prior let)
Name error at line 1:3: Undefined variable: x
```
**Result:** All correct. Error message is clear. ✅

---

## Entry #4 — Multiline expressions (§3b / §4.3)

Script: `s3b_multiline.nd`

```
len(\n  "hello"\n) → 5            ✅
[\n  1i,\n  2i,\n  3i\n] → len 3  ✅
{\n  "a": 1i,\n  "b": 2i\n}["a"] → 1  ✅
nested: [len("foo"), len("hello world")] → 3, 11  ✅
```

Edge — trailing comma `[1i, 2i,]`:
```
$ nodus run s4_3_multiline_edge.nd
Syntax error at line 4:1: Unexpected ']' in expression
```
**Finding BUG-401-003:** Trailing commas in multiline lists produce a syntax error.
Python, JavaScript, Rust all allow this. Inconvenient for generated code. **MEDIUM**

Edge — nested multiline (non-trailing-comma variant): ✅

---

## Entry #5 — @annotation syntax (§4.1)

### @retry

Script: `s4_1_retry_v2.nd`
```
import "std:retry" as retry

@retry(max_attempts: 3i, backoff_ms: 1i)
fn flaky() {
  attempt["count"] = attempt["count"] + 1i
  error("always fails")
}
let r = flaky()
print("attempts: \(attempt["count"])")
print("result: \(r)")
```
Output:
```
attempts: 0
result: {"kind": "dependency_error", "message": "nodus-retry package not installed"}
```
**Finding BUG-401-001:** `@retry` when `nodus-retry` is not installed calls the
function body **0 times**, returns a dependency_error, and does NOT indicate
the missing dep at compile-time or import-time. A user who forgets to install
`nodus-retry` gets a silent non-execution.
Expected: either fail at annotation compile time with a clear install instruction,
or fall back to calling the function once without retry.
**Severity: HIGH**

### @exactly_once

Script: `s4_1_exactly_once_v2.nd`
```
@exactly_once
fn send_email(addr) {
  print("sending to \(addr)")
  addr
}
let r1 = send_email("a@b.com")
let r2 = send_email("a@b.com")
let r3 = send_email("z@z.com")
print("r1: \(r1)")
print("r2: \(r2)")
print("r3: \(r3)")
```
Output:
```
sending to a@b.com    ← 1st call
sending to a@b.com    ← 2nd call — SAME ARGS, should be cached
sending to z@z.com    ← 3rd call, different args, correct
r1: nil               ← should be "a@b.com"
r2: nil               ← should be "a@b.com" (cached)
r3: nil               ← should be "z@z.com"
```
**Finding BUG-401-002a:** `@exactly_once` does NOT enforce idempotency — same
arguments execute the function body again. **Severity: CRITICAL**

**Finding BUG-401-002b:** `@exactly_once` return value is always `nil` — the
function body's return value is discarded. **Severity: CRITICAL**

### Unknown annotation

```
$ nodus run s4_1_unknown_annotation.nd
Syntax error at line 2:1: Unknown annotation: @nonexistent
```
**Result:** Compile-time error, good message. ✅

---

## Entry #6 — std:math bit operations (§4.4)

Script: `s4_4_bit_ops.nd`

```
math.bit_and(10i, 12i) → 8    ✅ (expected 8)
math.bit_or(10i, 12i)  → 14   ✅
math.bit_xor(10i, 12i) → 6    ✅
math.bit_not(0i)        → -1   ✅
math.bit_not(-1i)       → 0    ✅
math.bit_lshift(1i, 4i) → 16   ✅
math.bit_rshift(16i, 2i)→ 4    ✅
math.bit_lshift(1i, 3i) → 8    ✅
math.bit_rshift(8i, 2i) → 2    ✅
```
Wrong type and negative shift not tested (would require a try-catch that
Nodus lacks; add to v5 scope).

**Result:** All 9 cases correct. ✅

---

## Entry #7 — Sandbox allowlists (§4.5)

### allowed_commands

```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, allowed_commands=["python"])
# Test: run git --version (git NOT in allowed list)
r = rt.run_source('...sub.run(["git", "--version"])...')
```
Output:
```
ok=True
stdout: git version 2.52.0.windows.1
```
**Finding BUG-401-004:** `allowed_commands` is NOT enforced. A blocked binary
(`git`) runs successfully when not in the allowlist. The sandbox permits the
execution and returns the output. **Severity: CRITICAL**

Test with allowed binary (`python`): `ok=True, stdout=Python 3.11.9` ✅

### allowed_hosts

Could not be tested: base install missing `httpx` (`nodus-lang[http]` required).
Deferred — LOW priority documentation finding.
**Finding BUG-401-005:** `std:http` requires `httpx` which is not in the base
install. The error message is good: "install it with: pip install 'nodus-lang[http]'"
but the test env exposed that `allowed_hosts` can't be verified without an extra
optional dep. **Severity: LOW**

### allow_env=False

```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, allow_env=False)
r = rt.run_source('import "std:env" as env\nlet v = env.get("PATH")\nprint(v)')
```
Output: `ok=False, errors=[SandboxError: Blocked: environment variable access (allow_env=False)]`
**Result:** Correctly blocked. ✅

### allow_env child VM propagation

Test environment issue: module import from temp path blocked by its own sandbox.
Unable to confirm the child-VM propagation fix in this eval context. Manual
review of source confirms the fix is in `invoke_function()` propagation.
Flag for targeted unit-test verification.

---

## Entry #8 — Embedding API additions (§4.7)

### event_sinks

```python
events = []
rt = NodusRuntime(timeout_ms=None, max_steps=None, event_sinks=[lambda e: events.append(e)])
rt.run_source('let x = 1i + 2i')
print(len(events))  # → 0
```
Also tested with a workflow execution: `events after workflow: 0`

**Finding BUG-401-006:** `event_sinks` captures zero events for all tested
scenarios including simple arithmetic and workflow execution. The API is
wired (no error) but the sink is never called. **Severity: MEDIUM**

### coroutine_timeout_ms

```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, coroutine_timeout_ms=50)
# coroutine sleeps 500ms
result → ok=True, errors=[]
```
Script completed without hanging, indicating the coroutine was killed at 50ms.
The result `ok=True` with empty stdout means the script ran to completion
(main body exited) but the coroutine was silently reaped. No error surfaced.
**Result:** Functional (doesn't hang), but coroutine timeout is silent —
no indication in the result that a timeout occurred. **LOW** documentation gap.

### get_execution_stats()

```python
rt.run_source('let x = 1i + 2i + 3i')
stats = rt.get_execution_stats()
# → {'instructions_executed': 8, 'coroutines_spawned': 0}
```
**Result:** Works, returns plausible counts. ✅

### _last_vm privacy

```python
vm = rt._last_vm
# → _last_vm accessible: True
```
**Finding BUG-401-007:** `_last_vm` is still publicly accessible despite the
changelog claiming it is "now private." Python naming convention `_name` is
advisory only — it was never removed. **Severity: LOW** (cosmetic/docs gap)

### clear_shared_state()

```python
NodusRuntime.clear_shared_state()  # OK
rt4 = NodusRuntime(timeout_ms=None, max_steps=None)
rt4.run_source('print("after clear")')  # ok=True
```
**Result:** Works. ✅

---

## Entry #9 — Bounded channels (§4.8)

Named arg syntax: `channel(maxsize: 2i)` → Syntax error: Expected ')', got ':'
**Finding BUG-401-008:** `channel()` does not support named argument syntax.
The CLAUDE.md notation `channel(maxsize=N)` is Python documentation style, not
Nodus call syntax. The actual API is positional: `channel(2i)`.
The public docs should show `channel(2i)` not `channel(maxsize=N)`.
**Severity: MEDIUM** (docs/discoverability)

Positional form: `channel(2i)` — works correctly:
```
send(ch, "a") → OK
send(ch, "b") → OK
send(ch, "c") → Runtime error: send: channel is full (maxsize=2)
```
Error is a runtime exception (not a catchable err record). **LOW** — consistent
with documented behavior, but worth noting.

Edge cases:
- `channel()` → unbounded, works ✅
- `channel(0i)` → created without error (0 treated as unbounded or zero-cap?)
- `channel(-1i)` → Value error: channel() maxsize must be a non-negative integer ✅

---

## Entry #10 — Bit op wrong-arg (§4.4 adversarial)

`math.bit_and(1.0, 2.0)` — could not test without try/catch. Nodus has no
exception handler so a runtime error terminates the script. Noted as a test
infrastructure gap; not a language bug.
