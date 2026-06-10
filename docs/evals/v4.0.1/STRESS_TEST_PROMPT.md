# NODUS v4.0.1 — POST-PUBLISH STRESS-TEST EVALUATION
#
# Lineage: v4.0.0 stress test → this v4.0.1 POST-PUBLISH instance.
# Section 4 (surface to probe) updated for v4.0.1 change set.

# =====================================================================
# SECTION 0 — RELEASE PARAMETERS
# =====================================================================
#
#   TARGET VERSION      : v4.0.1
#   RELEASE TYPE        : patch (no breaking changes, no bytecode bump)
#   PRIOR BASELINE      : v4.0.0
#
#   INSTALL SOURCE      : POST-PUBLISH
#     Install command:  pip install nodus-lang==4.0.1
#     Confirm version:  nodus --version   →   must report "Nodus 4.0.1"
#     A version mismatch here invalidates the entire run. STOP if it occurs.
#
#   WORKING DIRECTORY   : C:\dev\nd-eval-401\   (empty, non-git, local-only)
#   DELIVERABLE DIR     : docs/evals/v4.0.1/   (move the four files here at end)
#
# =====================================================================

You are an independent technical evaluator. You have no prior context on
this release. Pretend you are a senior engineer who saw the v4.0.1 patch
announcement and decided to verify the claims before adopting it in
production.

You did NOT participate in building or releasing this version. You do not
trust the release notes — you verify them. Your job is to find the sharp
corners, not to confirm that the release is good. Pay particular attention
to the new features shipped in this patch: annotations, compound assignment,
multiline expressions, bit ops, sandbox allowlists, and the embedding API
additions. These are the highest-risk surfaces.

---

## 1. INTEGRITY RULES  (read these first, they govern everything)

1. **Log everything, fix nothing.** You are evaluating, not patching.
   If you find a bug, record it — do not work around it silently.
   Workarounds get logged AS workarounds, with the defect filed.

2. **No claim without evidence.** Every statement in any report must be
   traceable to an entry in `EVAL_LOG.md`. If it isn't in the log with a
   command, input, and actual output, it does not go in a report.

3. **Paste real output.** The log contains actual terminal output — exit
   codes, error text verbatim, actual printed result — not a summary.

4. **Severity is calibrated, not softened.**
   - **CRITICAL** = blocks real work.
   - **HIGH** = a documented feature doesn't behave as documented.
   - **MEDIUM** = works, but with a sharp corner a real user will hit.
   - **LOW** = minor friction, papercut.
   - **COSMETIC** = output/formatting/wording.
   Do not round a HIGH down to a MEDIUM because the rest is good.

5. **Stop-and-report when reality differs from this prompt.** If version
   doesn't resolve to v4.0.1, STOP, log it, report it.

6. **Version provenance is the first log entry.** Before any test, record:
   install command, INSTALL SOURCE = POST-PUBLISH, resolved version.

---

## 2. SETUP

In `C:\dev\nd-eval-401\` (create if needed, must be empty and non-git):

1. Record: OS, shell, Python version.
2. Create venv: `python -m venv .venv`
3. Activate: `.venv\Scripts\activate`
4. Install from PyPI (NOT local): `pip install nodus-lang==4.0.1`
5. Confirm: `nodus --version` → must report `Nodus 4.0.1`. STOP if mismatch.
6. Create `EVAL_LOG.md`. Write the provenance block as entry #1.
7. Create a `scratch/` subdirectory for test scripts.

Do not read Nodus's source code to form your assessment. Evaluate SHIPPED
BEHAVIOR from the PyPI artifact only.

---

## 3. EVALUATION ARC  (work in order, log as you go)

### 3a. First contact

- `nodus --help` — do all documented subcommands appear?
- `nodus run scratch/hello.nd` where hello.nd prints a string literal
- `nodus fmt scratch/hello.nd` — formatter runs without error?
- `nodus check scratch/hello.nd` — checker runs without error?
- Embedding quick-check:
  ```python
  from nodus import NodusRuntime
  rt = NodusRuntime(timeout_ms=None, max_steps=None)
  print(rt.run_source('print("hello")'))
  ```

### 3b. Language core — regression check vs v4.0.0

Exercise the type system, operators, control flow. Focus on anything
that v4.0.1 touched.

**v4.0.1 NEW — compound assignment (should now work, was absent in v4.0.0):**
- `let x = 5i; x += 3i; print("\(x)")` → should print `8`
- `let y = 10.0; y -= 2.5; print("\(y)")` → should print `7.5`
- `let lst = [1i, 2i, 3i]; lst[0] += 10i; print("\(lst[0])")` → `11`
- Closure constraint still applies:
  `fn make() { let c = 0i; fn inc() { c += 1i }; inc }` → should still error
  (compound assignment doesn't bypass the outer-let closure restriction)

**v4.0.1 NEW — multiline expressions (should now work):**
- Multi-line function call:
  ```
  let r = len(
    "hello"
  )
  print("\(r)")
  ```
  Should print `5`.
- Multi-line list:
  ```
  let lst = [
    1i,
    2i,
    3i
  ]
  print("\(len(lst))")
  ```
  Should print `3`.
- Multi-line map:
  ```
  let m = {
    "a": 1i,
    "b": 2i
  }
  print("\(m["a"])")
  ```
  Should print `1`.

**v4.0.0 regressions to catch (these should still work):**
- Integer vs float model: `1i + 2i` → int, `1.0 + 2.0` → float
- `len([1,2,3])` returns `3i` (int)
- `print("a", "b")` → error (single-argument)
- `fn` as identifier → reserved keyword error
- Maps vs Records distinction still correct

**Known constraints still in effect:**
- `await x` → error (no await keyword)
- Channels are built-in, `import "std:channel"` → "Import not found"
- `spawn()` takes a coroutine value, not a function literal

### 3c. Standard library — regression check

For each stdlib module, at minimum: one happy-path call, one wrong-type
call. Flag any error that is a leaked Python traceback.

**Priority: `std:math` bit operations (NEW in v4.0.1):**
- `math.bit_and(6i, 3i)` → `2i`
- `math.bit_or(6i, 3i)` → `7i`
- `math.bit_xor(6i, 3i)` → `5i`
- `math.bit_not(0i)` → `-1i` (bitwise NOT)
- `math.bit_lshift(1i, 3i)` → `8i`
- `math.bit_rshift(8i, 2i)` → `2i`
- Wrong type: `math.bit_and(1.0, 2.0)` → error, good message?
- Negative shift: `math.bit_lshift(1i, -1i)` → error?

**Regression: existing std modules still work:**
- `std:json`: parse valid, parse invalid, stringify
- `std:fs`: read, write, exists — and sandbox enforcement
- `std:hash`: `hash.sha256("hello").to_hex()` → hex string
- `std:strings`, `std:time`, `std:env`, `std:encoding`

### 3d. SURFACE TO PROBE — v4.0.1 specific (Section 4 below)

This is the primary focus for this release. Work through Section 4
methodically before writing any report.

### 3e. Build something real

Build ONE of the following using only the PyPI-installed nodus-lang:
- A log parser: reads a file, extracts lines matching a pattern, writes a summary
- A JSON transformer: reads JSON, restructures fields, writes output JSON
- A multi-step pipeline: reads a directory, processes each file, produces a report

Constraints:
- Idiomatic v4.0.1 Nodus — use at least one new v4.0.1 feature
- 50–150 lines
- Use at least 3 `std:` modules
- Use the module system (2+ .nd files)
- Save under `scratch/real_task/`

Log: where you got stuck, what docs you re-read, what would have helped.

---

## 4. SURFACE TO PROBE  (v4.0.1 change surface)

### 4.1 — @annotation syntax (@retry and @exactly_once)

This is the biggest new surface in v4.0.1. Probe it carefully.

**@retry claims to verify:**
```
import "std:retry" as retry

@retry(max_attempts: 3i, backoff_ms: 10i)
fn flaky() {
  error("oops")
}
let r = flaky()
print("\(r)")
```
- Does it compile without error?
- Does it retry 3 times before returning an error value?
- Does removing the `import "std:retry"` cause a useful error?
- Wrong parameter name: `@retry(attempts: 3i)` → compile error? Good message?
- Unknown annotation: `@nonexistent fn f() { 1i }` → compile error?
  Message should say something about unknown annotation, not crash.
- Annotation on a non-fn: `@retry(max_attempts: 3i) let x = 1i` → error?
- Nested annotations: `@retry(...) @exactly_once fn f() { ... }` → works or errors?

**@exactly_once claims to verify:**
```
@exactly_once
fn send_email(addr) {
  print("sending to \(addr)")
  addr
}
let r1 = send_email("a@b.com")
let r2 = send_email("a@b.com")
print("\(r1)")
print("\(r2)")
```
- First call: prints "sending to a@b.com", returns "a@b.com"
- Second call with same args: does NOT print again, returns cached result
- Call with different args: IS a new call
- What happens without the effects store initialized?

**Annotation + module interaction:**
- Can an annotated function be exported from a module and imported elsewhere?
- Does the annotation lowering survive the module boundary?

### 4.2 — Compound assignment operators

v4.0.1 ships `+=`, `-=`, `*=`, `/=` as parser desugaring.

**Claims to verify:**
- `let x = 10i; x += 5i` → x is 15i
- `let x = 10i; x -= 3i` → x is 7i
- `let x = 4i; x *= 3i` → x is 12i
- `let x = 9i; x /= 3i` → what type? `9i / 3i` → int or float?
- Float version: `let y = 10.0; y += 2.5` → 12.5
- Index target: `let lst = [0i, 0i]; lst[1] += 5i` → lst[1] is 5i
- Record field target: `let r = {count: 0i}; r.count += 1i` → r.count is 1i
- Map field target: `let m = {"n": 0i}; m["n"] += 1i` → m["n"] is 1i
- Formatter round-trip: does `nodus fmt` preserve `+=` or desugar it to `x = x + ...`?
- Undefined variable: `x += 1i` with no prior `let x` → error? Good message?
- Type mismatch: `let x = "hello"; x += 1i` → error? What kind?

### 4.3 — Multiline expressions

v4.0.1 adds implicit line continuation inside `(`, `[`, `{`.

**Claims to verify:**
- Multi-line function call: args on separate lines inside `()`
- Multi-line list literal: elements on separate lines inside `[]`
- Multi-line map literal: entries on separate lines inside `{}`
- Nested: multi-line call inside a multi-line list
- Mixed: `[fn_call(\n  arg1,\n  arg2\n)]` works
- Formatter: does `nodus fmt` preserve or collapse multiline style?
- Edge: trailing comma in multi-line list `[1i, 2i,]` → works or errors?
- Edge: empty multiline: `(\n)` → parse error or empty expression?
- Edge: comment inside multiline: `[1i, # comment\n2i]` → works?

### 4.4 — std:math bit operations

Six new functions. All require integer-typed arguments.

**Claims to verify** (use exact expected values):
- `math.bit_and(0b1010i, 0b1100i)` → `8i` (binary AND)
  (Nodus may not have binary literals — use `math.bit_and(10i, 12i)`)
- `math.bit_or(10i, 12i)` → `14i`
- `math.bit_xor(10i, 12i)` → `6i`
- `math.bit_not(0i)` → `-1i`
- `math.bit_not(-1i)` → `0i`
- `math.bit_lshift(1i, 4i)` → `16i`
- `math.bit_rshift(16i, 2i)` → `4i`
- Float arg → error? Message?
- Negative shift amount → error? Message?
- Very large shift: `math.bit_lshift(1i, 63i)` → what happens?

### 4.5 — Sandbox allowlists (allowed_commands, allowed_hosts)

**allowed_commands claims to verify:**
```python
from nodus import NodusRuntime
rt = NodusRuntime(timeout_ms=None, max_steps=None, allowed_commands=["echo"])
```
- `subprocess.run(["echo", "hello"])` → works (echo is in the list)
- `subprocess.run(["ls"])` → sandbox error (ls is not in the list)
- Shell mode: `subprocess.run(["echo hello"], shell=True)` → blocked when list is set?
- Empty list: `allowed_commands=[]` → all subprocess calls blocked?
- No list (None): `allowed_commands=None` → no restriction (default behaviour)
- CLI equivalent: `nodus run --allowed-commands echo script.nd` — does this flag exist?
  (Check `nodus run --help`)
- Test BOTH embedded mode (NodusRuntime) AND CLI mode (nodus run) — enforcement
  can differ between contexts.

**allowed_hosts claims to verify:**
```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, allowed_hosts=["example.com"])
```
- HTTP request to `example.com` → allowed
- HTTP request to any other host → sandbox error
- Empty list: `allowed_hosts=[]` → all HTTP blocked?
- Error message quality: does it say which host was blocked?

### 4.6 — allow_env flag

**Claims to verify:**
```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, allow_env=False)
```
- `env.get("PATH")` → sandbox error
- `env.set("X", "1")` → sandbox error
- All six `env_*` builtins blocked, including `std:env` module-method equivalents
- Child VM propagation: a module that calls `env.get` from within an imported
  module is also blocked (this was the bug fixed in v4.0.1 — verify the fix)
- `allow_env=True` (default): env access works normally

### 4.7 — Embedding API additions

**event_sinks:**
```python
events = []
rt = NodusRuntime(timeout_ms=None, max_steps=None, event_sinks=[lambda e: events.append(e)])
rt.run_source('let x = 1i + 2i')
print(len(events), events)
```
- Are events captured? What event types appear for a simple script?
- Multiple sinks: both receive each event?
- Sink that raises: does it propagate the exception or swallow it?

**coroutine_timeout_ms:**
```python
rt = NodusRuntime(timeout_ms=None, max_steps=None, coroutine_timeout_ms=50)
result = rt.run_source('''
  let c = coroutine(fn() {
    sleep(200)
    "done"
  })
  spawn(c)
  run_loop()
''')
```
- Does the coroutine get killed at 50ms?
- What does the result look like when a coroutine times out mid-run?
- coroutine_timeout_ms=None: no per-coroutine limit (default)

**get_execution_stats():**
```python
rt = NodusRuntime(timeout_ms=None, max_steps=None)
rt.run_source('let x = 1i + 2i + 3i')
stats = rt.get_execution_stats()
print(stats)
```
- Does it return `{"instructions_executed": int, "coroutines_spawned": int}`?
- Are the counts plausible for a simple script?
- Is `_last_vm` now private/removed? Verify `rt._last_vm` raises or returns None.

**clear_shared_state():**
```python
from nodus import NodusRuntime
NodusRuntime.clear_shared_state()
```
- Callable as a classmethod without a runtime instance?
- Does it complete without error?
- After `rt.shutdown()` + `clear_shared_state()`, can a new `NodusRuntime()`
  be created and run successfully?

### 4.8 — Bounded channels (channel(maxsize=N))

**Claims to verify:**
```
let ch = channel(maxsize: 2i)
send(ch, "a")
send(ch, "b")
send(ch, "c")   # should raise sandbox/runtime error — channel full
```
- Third send raises an error?
- Error message quality?
- `recv()` from the full channel makes space — can you send again?
- `channel()` without `maxsize` → unbounded (existing behavior preserved)
- `channel(maxsize: 0i)` → error or unbounded?
- `channel(maxsize: -1i)` → error?

### 4.9 — Security fix regression check (PR #197)

Seven fixes were landed in PR #197. Verify the most impactful ones:

**Path traversal via std:fs (if applicable):**
- `fs.read("../../etc/passwd")` with `allowed_paths` set — still blocked?
- Both CLI (`--allow-paths`) and embedded (`NodusRuntime(allowed_paths=[...])`) mode

**Module import flag propagation (the core bug fixed in v4.0.1):**
- Create a module `helper.nd` that calls `env.get("PATH")`
- In embedded mode with `allow_env=False`, import and call `helper.nd`
- The call must be blocked — if env access leaks through the module boundary,
  this is a CRITICAL regression

**Verify the correct flag name:**
- `nodus run --allow-paths /tmp script.nd` (not `--allowed-paths`)
- `nodus run --help` — confirm the exact flag name shown

### 4.10 — Error message quality (cross-cutting)

For every error triggered in sections 3–4, score each message:
- Does it say WHAT went wrong?
- Does it say WHERE (file, line, column)?
- Does it suggest a fix?
- Is it a Nodus error or a leaked Python traceback?

Pay particular attention to new v4.0.1 error paths:
- Unknown annotation name
- Wrong annotation parameter key
- Compound assignment to undefined variable
- Channel capacity exceeded
- Sandbox allowlist violation (subprocess + http)

---

## 5. AUDIENCE LENSES

When writing the report, assess from each angle:

- **The AI agent author.** Primary strategic user. Can a model write correct
  v4.0.1 Nodus from the docs alone? Are new features (`@retry`, `+=`,
  multiline) predictable and enumerable? Does each error tell the model how
  to fix it?
- **The human adopter.** On-ramp, docs, error legibility, trust.
- **The embedder.** `NodusRuntime` additions: are `event_sinks`,
  `coroutine_timeout_ms`, `get_execution_stats()`, `clear_shared_state()`
  documented and working as documented?
- **The v4.0.0 upgrader.** Drop-in patch — does ANYTHING break that worked
  in v4.0.0? Any behavior change that isn't in the changelog?

---

## 6. DELIVERABLES  (four files → docs/evals/v4.0.1/)

1. **`EVAL_LOG.md`** — chronological evidence trail.
2. **`NODUS_EVAL_REPORT.md`** — narrative assessment with findings by severity.
3. **`NODUS_EVAL_RUBRIC.md`** — 1–10 scoring table:

   Dimension                              | Score | Rationale
   ---------------------------------------|-------|----------
   Install and first-run UX               |       |
   CLI ergonomics                         |       |
   Error message quality                  |       |
   Parser robustness                      |       |
   Annotation syntax (@retry/@exactly_once)|      |
   Compound assignment operators          |       |
   Multiline expressions                  |       |
   std:math bit operations                |       |
   Sandbox allowlists (commands/hosts)    |       |
   Embedding API additions                |       |
   Bounded channels                       |       |
   Security fix verification              |       |
   v4.0.0 regression coverage             |       |
   Documentation accuracy                 |       |
   AI-authorability                       |       |
   Overall patch quality                  |       |

4. **`NODUS_EVAL_BUGS.md`** — filable issues, one per finding:
   ```
   ### BUG-401-NNN: <short title>
   **Severity:** CRITICAL / HIGH / MEDIUM / LOW / COSMETIC
   **Subsystem:** parser | runtime | stdlib | sandbox | embedding | docs | cli
   **Affects:** v4.0.1
   **Repro:** <exact copy-pasteable script>
   **Expected:**
   **Actual:**
   **Fix direction:**
   ```

---

## 7. EXIT CONDITION

All four deliverables produced. Every report claim cites a log entry.
All bugs filed in `NODUS_EVAL_BUGS.md`. Files moved to `docs/evals/v4.0.1/`.
Report the composite score and the single most important finding.
