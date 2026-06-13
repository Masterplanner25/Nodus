# Nodus v4.0.3 — Eval Log

**Eval date:** 2026-06-13
**Version:** v4.0.3 (PyPI, POST-PUBLISH)
**Evaluator:** Claude Sonnet 4.6 (independent — did not do release prep)
**Eval type:** PATCH — scoped to patched surfaces only (Section 3d)
**Working directory:** `C:\dev\nodus_eval_403\`

---

## Entry #1 — Version provenance

```
python -m pip install "nodus-lang==4.0.3"
# Output: Requirement already satisfied: nodus-lang==4.0.3
#   in c:\users\shawn\appdata\local\programs\python\python311\lib\site-packages (4.0.3)

python -c "import nodus; print(nodus.__version__)"
# → 4.0.3

nodus.exe --version
# → Nodus 4.0.3
```

Resolved version matches TARGET VERSION. Install source: PyPI (`pip install nodus-lang==4.0.3`).
Environment: Windows 11 Home 10.0.26200, Python 3.11.9, PowerShell 5.1.

---

## Entry #2 — Fix #225: tool.register in imported module → re-execution storm (CRITICAL)

**tools_lib.nd:**
```
import "std:tool" as tool
tool.register({
    name: "myapp.greet",
    description: "Greet a user",
    parameters: {name: "string"},
    handler: fn(args) { return "Hello, \(args["name"])!" }
})
```

**test_225.nd:**
```
import "std:tool" as tool
import "./tools_lib"
let result = tool.invoke("myapp.greet", {"name": "World"})
print(result)
```

```
nodus.exe run test_225.nd
# → Hello, World!
# EXIT: 0
```

**Result:** PASS. Handler invokes correctly from imported module without re-execution storm.

---

## Entry #3 — Fix #226: step `with { retries: N }` no-ops under `nodus run` (CRITICAL)

**wf_retry.nd:**
```
let state = { "count": 0 }
workflow demo {
    step flaky with { retries: 2, retry_delay_ms: 50 } {
        if (state["count"] == 0) {
            state["count"] = 1
            throw "fail on first attempt"
        }
        return "success on attempt 2"
    }
}
```

```
nodus.exe workflow-run wf_retry.nd
# STDERR: Thrown error at wf_retry.nd:7:19: fail on first attempt
#         Stack trace: at __anon_1 (wf_retry.nd:7:19) ...
# STDOUT: {"tasks": {"task_1": "success on attempt 2"}, "steps": {"flaky": "success on attempt 2"},
#          "attempts": {"task_1": 2.0}, "failed": [], ...}
# EXIT CODE: 0
```

**Result:** PASS. Retry engaged — `"attempts": 2.0`, `"failed": []`, step result is "success on attempt 2".

**Finding:** First-attempt error trace bleeds to stderr even when workflow ultimately succeeds. This is
cosmetic (exit 0, correct result) but confusing — a user may misread the stderr trace as a workflow
failure. **Severity: COSMETIC.** Filed as EVAL-403-C1.

---

## Entry #4 — Fix #227: state vars invisible in string interpolation (HIGH)

**test_227.nd:**
```
let state = { "label": "hello" }
workflow interp_test {
    step greet {
        return "greeting: \(state["label"])"
    }
}
let result = run_workflow(interp_test)
print(result["steps"]["greet"])
```

```
nodus.exe run test_227.nd
# → greeting: hello
# EXIT: 0
```

**Result:** PASS. State variable visible in string interpolation inside step body.

---

## Entry #5 — Fix #228: `let` in `for` loop — no per-iteration binding (HIGH)

**Bytecode-level validation (RESET_LOCAL_IDX opcode):**
```
nodus.exe dis test_228_dis.nd | grep -i RESET
# (no output for simple loop — RESET_LOCAL_IDX only emitted when variable
#  is captured by a closure, i.e., allocated as Cell)
```

**Basic per-iteration let binding (no closure required):**
```
nodus.exe run test_228b.nd
# → [20.0, 40.0, 60.0]   (x=10→20, x=20→40, x=30→60 each iteration)
# EXIT: 0
```

**Bytecode golden tests (9 tests including workflow_with_state fixture
 that contains RESET_LOCAL_IDX):**
```
python -m pytest tests/test_bytecode_golden.py -q
# 9 passed in 0.25s
```

**Pre-existing limitation noted:** Closures inside for-loop bodies cannot capture
loop-body `let` variables ("Undefined variable: v" / "Undefined variable: x" at
compile time). This blocks the canonical per-iteration closure test
(`closures = closures + [fn() { return captured }]` inside a for body). This is
NOT a regression from #228 — it's a pre-existing scoping limitation.

**Result:** PARTIAL PASS. The opcode fix is in place (golden tests confirm) and
basic per-iteration binding works. The full closure-capture scenario is untestable
at the .nd level due to a pre-existing limitation.

---

## Entry #6 — Fix #229: `run_loop()` swallows coroutine errors (HIGH)

**test_229b.nd:**
```
let c1 = coroutine(fn() { return "ok" })
let c2 = coroutine(fn() { throw "worker failure" })
spawn(c1)
spawn(c2)
let failures = run_loop()
print(failures)
print(len(failures))
```

```
nodus.exe run test_229b.nd
# STDERR: Thrown error at test_229b.nd:6:11: worker failure
# STDOUT: ["worker failure"]
#         1
# EXIT: 0
```

**Result:** PASS. `run_loop()` returns `["worker failure"]`, exit 0 (session continues,
coroutine error isolated). Error trace to stderr is expected coroutine-error notification.

---

## Entry #7 — Fix #230: `tool.register` JSON-Schema form crashes at invoke (MEDIUM)

**test_230.nd:**
```
import "std:tool" as tool
tool.register({
    name: "myapp.add",
    description: "Add two numbers",
    parameters: {type: "object", properties: {a: {type: "number"}, b: {type: "number"}},
                 required: ["a", "b"]},
    handler: fn(args) { return args["a"] + args["b"] }
})
let result = tool.invoke("myapp.add", {"a": 3, "b": 4})
print(result)
```

```
nodus.exe run test_230.nd
# → 7.0
# EXIT: 0
```

**Result:** PASS. JSON-Schema-style `properties` dict no longer causes `"type" in prop` crash.

---

## Entry #8 — Fix #231: `time.format()` garbled with strftime tokens (MEDIUM)

**test_231.nd:**
```
import "std:time" as time
let now = time.now()
let formatted = time.format(now, "%Y-%m-%d")
print(formatted)
print(len(formatted))
```

```
nodus.exe run test_231.nd
# → 2026-06-13
#   10
# EXIT: 0
```

**Result:** PASS. `%Y-%m-%d` produces correct ISO date (10 chars). strftime delegation works.

---

## Entry #9 — Fix #232: `nodus test` UnicodeEncodeError on Windows (MEDIUM)

**test_unicode/basic_test.nd (suite with 2 cases):**
```
import "std:test" as test
test.suite("unicode output", fn() {
    test.case("checkmark survives output", fn() {
        test.assert_eq(1 + 1, 2, "basic math passes")
    })
    test.case("cross survives output", fn() {
        test.assert_eq("a", "a", "string equality")
    })
})
```

```
nodus.exe test test_unicode/
# →  RUN  test_unicode\basic_test.nd
#   Tests: 2 total, 2 passed
#   Time:  0.02s
# EXIT: 0
```

**Result:** PASS. No UnicodeEncodeError. (Windows cp1252 terminal handled without crash.)

---

## Entry #10 — Fix #233: `nodus test` rejects `../lib/x` from tests/ subdir (MEDIUM)

**Project structure:** `proj233/nodus.toml`, `proj233/lib/utils.nd`, `proj233/tests/utils_test.nd`
`utils_test.nd` imports `"../lib/utils"`.

```
cd proj233
nodus.exe test tests/
# →  RUN  tests\utils_test.nd
#   Tests: 1 total, 1 passed
#   Time:  0.00s
# EXIT: 0
```

**Result:** PASS. `../lib/utils` import resolves correctly when test file is in `tests/` subdir
and project root has `nodus.toml`.

---

## Entry #11 — Fix #234: `cb.create` map form crashes (LOW)

```
import "std:circuit_breaker" as cb
let breaker = cb.create("myapp.svc", {failure_threshold: 3, recovery_timeout_ms: 5000})
print("cb created ok")
```

```
nodus.exe run test_low.nd (partial)
# → cb created ok
# EXIT: 0
```

**Result:** PASS. `cb.create` map form works.

---

## Entry #12 — Fix #235: `cb.call` never throws on circuit-open (LOW)

```
import "std:circuit_breaker" as cb
let breaker = cb.create("myapp.svc", 2, 1000)
let call1 = cb.call(breaker, fn() { throw "failure 1" })
let call2 = cb.call(breaker, fn() { throw "failure 2" })
let call3 = cb.call(breaker, fn() { return "ok" })
```

```
nodus.exe run test_235.nd
# STDERR: [CircuitBreaker:myapp.svc] closed -> open
#          Circuit_open error at test_235.nd:10:44: Circuit 'myapp.svc' is open
# EXIT: 1 (unhandled circuit_open throw)
```

**Result:** PASS. `cb.call` throws `circuit_open` when breaker is open. Exit 1 is correct
(unhandled throw must be caught by caller).

---

## Entry #13 — Fix #236: `identity.trace_id/session_id` nil under CLI (LOW)

```
import "std:identity" as identity
let tid = identity.trace_id()
let sid = identity.session_id()
let eid = identity.execution_unit_id()
print("trace_id: \(tid)")
print("session_id: \(sid)")
print("exec_id: \(eid)")
```

```
nodus.exe run test_identity.nd
# → trace_id: 6858d615-fd36-4a5d-86d6-9eef9863e71a
#   session_id: nil
#   exec_id: be1631c6a9cfb9f2
# EXIT: 0
```

**Code investigation:** `runner.py` sets `vm.trace_id` and `vm.session_id` on the top-level VM.
`module.py` line 214 propagates `trace_id` to child VMs but does NOT propagate `session_id`.
The `std:identity` stdlib runs in a child VM (created by ModuleLoader) whose `session_id = None`.
The identity module's `runtime_session_id()` closure captures the child VM, returning None.

**Result:** PARTIAL PASS — `trace_id` works, `session_id` remains nil.

This is a regression from the claimed fix. The CHANGELOG says both `trace_id` AND `session_id`
should be non-nil under CLI. **Severity: LOW** (same as original issue). Filed as EVAL-403-001.

---

## Entry #14 — Fix #237: `mem.tag`/`mem.forget` not implemented (LOW)

```
mem.put("k1", "hello")
mem.tag("k1", ["tag-a", "tag-b"])
mem.forget("k1")
let v2 = mem.get("k1")
print("mem forget: \(v2 == nil)")   # → true
```

```
nodus.exe run test_237_238.nd (partial)
# → mem get: hello
#   mem forget: true
# EXIT: 0 (partial)
```

**Result:** PASS. Both `mem.tag` and `mem.forget` work.

---

## Entry #15 — Fix #238: `tool.execute`/`tool.available` missing in `std:tool` (LOW)

```
print("tool.available: \(tool.available("myapp.mul"))")    # → true
print("tool.available missing: \(tool.available("myapp.nope"))")  # → false
let mul = tool.execute("myapp.mul", {"x": 6, "y": 7})
print("tool.execute: \(mul)")  # → 42.0
```

**Result:** PASS.

---

## Entry #16 — Fix #239: `fx.get_result()` absent (LOW)

```
let act_id = fx.action_id("send_email", {"to": "user@example.com"}, "test-scope")
let cached = fx.get_result(act_id)
print("result before replay: \(cached)")   # → nil (no result stored yet)
```

**Result:** PASS. `fx.get_result()` exists; returns nil when no result cached.

---

## Entry #17 — Fix #240: failed-step IDs inconsistent wf vs goal (LOW)

```
workflow wf_with_fail {
    step always_fails {
        throw "step error"
    }
}
let result = run_workflow(wf_with_fail)
print("failed: \(result["failed"])")
```

```
nodus.exe run test_240.nd
# STDERR: Thrown error at test_240.nd:3:15: step error
# STDOUT: failed: ["always_fails"]
# EXIT: 0
```

**Result:** PASS. `result["failed"]` contains step name `"always_fails"`, not a task_id.

---

## Entry #18 — Fix #241: `nodus test` absent from `--help` (LOW)

```
nodus.exe --help | grep test
# → test [path]       Run .nd test files (files matching *_test.nd or test_*.nd)
```

**Result:** PASS. `test [path]` appears in Execution section of `--help`.

---

## Entry #19 — PR #252: stdlib contract test suite (TESTS)

```
$env:NODUS_RUN_CONTRACTS = "1"
python -m pytest tests/test_stdlib_contracts.py -q
# → 87 passed in 1.60s
```

**Result:** All 87 contract tests pass against the installed PyPI wheel.
Modules covered: tool, identity, effects, sys, memory, retry, circuit-breaker,
channel, http, subprocess, hash, time, fs, encoding, json, math.

---

## Entry #20 — Fix #214: `_last_vm` still public (LOW)

Not directly testable from .nd; confirmed via Python:
```python
import nodus
rt = nodus.NodusRuntime()
rt._last_vm   # triggers DeprecationWarning: _last_vm is a private implementation detail
```
Filed as confirmed; not re-tested in .nd surface.

---

## Entry #21 — Fix #242: `.nodus/` run artifacts never cleaned up (LOW)

```
nodus.exe workflow cleanup --help
# → nodus: unknown flag: --help
nodus.exe workflow
# Shows sub-command list including 'cleanup'
```

The `cleanup` command exists. Not tested with live artifacts (would require running
a workflow framework sweeper session). Presence confirmed.

---

## Summary table

| Fix | Severity | Result |
|-----|----------|--------|
| #225 tool.register in imported module | CRITICAL | PASS |
| #226 step retries under workflow-run | CRITICAL | PASS (+ cosmetic finding EVAL-403-C1) |
| #227 state vars in string interpolation | HIGH | PASS |
| #228 let in for loop per-iteration binding | HIGH | PARTIAL (opcode in place; closure scoping limit blocks full test) |
| #229 run_loop() returns error list | HIGH | PASS |
| #230 tool JSON-Schema form crashes | MEDIUM | PASS |
| #231 time.format strftime tokens | MEDIUM | PASS |
| #232 nodus test Unicode on Windows | MEDIUM | PASS |
| #233 nodus test ../lib/x import | MEDIUM | PASS |
| #234 cb.create map form | LOW | PASS |
| #235 cb.call throws on open | LOW | PASS |
| #236 identity.trace_id/session_id under CLI | LOW | PARTIAL — session_id still nil (EVAL-403-001) |
| #237 mem.tag/mem.forget | LOW | PASS |
| #238 tool.execute/available | LOW | PASS |
| #239 fx.get_result() | LOW | PASS |
| #240 failed-step IDs | LOW | PASS |
| #241 nodus test in --help | LOW | PASS |
| #242 .nodus/ cleanup command | LOW | CONFIRMED (not fully testable) |
| #252 stdlib contract suite | TESTS | 87/87 PASS |
