# Nodus v3.0.1 — Evaluation Bug Report

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Baseline:** v3.0.0 eval scored 6.45/10 composite, 22 bugs filed

---

## CRITICAL

### BUG-01: 1I (uppercase suffix) still gives name error, not parse error
**Severity:** CRITICAL
**Subsystem:** parser / lexer
**Affects:** v3.0.1
**Repro:**
```nodus
let x = 1I
print(x)
```
**Expected:** `Syntax error: integer literal suffix must be lowercase i — did you mean 1i?` (per CHANGELOG v3.0.1 "integer literals with uppercase I suffix now produce helpful parse errors")
**Actual:** `Name error at ...:1:10: Undefined variable: I` — runtime name error, not parse error. `1I` still lexes as two tokens: `NUM(1)` + `ID(I)`, then the parser tries to evaluate `I` as a variable reference.
**Notes:** This is the single v3.0.1 patch closure failure. The CHANGELOG for v3.0.1 and the issue #64 both claim this is fixed. The fix did NOT land in the distributed 3.0.1 wheel. Any code using `1I` still gets a cryptic name error at runtime, not a parse-time error with a helpful message. v3.0.0 eval filed this as BUG-E12 (MEDIUM). Now CRITICAL because the patch claimed closure but the fix is absent.
**v3.0.0 regression?** NO (same behavior as v3.0.0)
**v3.0.1 patch closure issue?** YES — CRITICAL

---

## HIGH

### BUG-02: math.log(n, base) computes ln(base) not log_base(n)
**Severity:** HIGH
**Subsystem:** stdlib / math
**Affects:** v3.0.1
**Repro:**
```nodus
import "std:math" as math
print(math.log(100, 10))  // Expected: 2.0 (log base 10 of 100)
                           // Actual:   2.302... (ln(10))
print(math.log(8, 2))     // Expected: 3.0 (log base 2 of 8)
                           // Actual:   0.693... (ln(2))
```
**Expected:** `math.log(value, base)` returns `log_base(value) = ln(value)/ln(base)`. `math.log(100, 10)` should be 2.0.
**Actual:** Returns `ln(base)`, completely ignoring the first argument when a second argument is provided. The function appears to have its arguments internally swapped for the two-argument form.
**Notes:** Inconsistently, the function DOES correctly validate an invalid base (`math.log(100, -1)` returns `error{kind: "value_error"}`), so the second argument is read but used as the first argument to the underlying log computation. Single-argument form `math.log(x)` returns the correct natural log. New bug introduced in v3.0.1 when math.log was added. Any caller using the two-arg form for change-of-base computation gets completely wrong results with no error.
**v3.0.0 regression?** N/A (function didn't exist in v3.0.0)
**v3.0.1 patch closure issue?** NO (not claimed to be fixed; this is a new defect in the implementation of BUG-E05)

---

## MEDIUM

### BUG-03: nodus workflow run --help and nodus graph run --help fail
**Severity:** MEDIUM
**Subsystem:** CLI
**Affects:** v3.0.1
**Repro:**
```sh
nodus workflow run --help
# File not found: --help

nodus graph run --help
# File not found: --help
```
**Expected:** Help text for the `workflow run` and `graph run` subcommands.
**Actual:** The subcommand runner treats `--help` as a script filename. Exit code 1.
**Notes:** `nodus workflow --help` (one level up) works correctly and shows all subcommands. `nodus run --help` works. The failure is specific to multi-level subcommands (verb + subverb + --help). Users trying to discover options for workflow execution are blocked. Compare: `nodus debug --help` works (single-level subcommand). No equivalent problem in v3.0.0 eval.
**v3.0.0 regression?** Unknown (not tested in v3.0.0 eval)
**v3.0.1 patch closure issue?** NO

---

### BUG-04: Stdlib err records missing path/line/column/stack fields
**Severity:** MEDIUM
**Subsystem:** stdlib / err record shape
**Affects:** v3.0.1
**Repro:**
```nodus
import "std:json" as json
let e = json.parse("{bad")
print(e.path)    // Key error: Missing record field: path
print(e.line)    // Key error: Missing record field: line
print(e.column)  // Key error: Missing record field: column
print(e.stack)   // Key error: Missing record field: stack
```
**Expected:** Per LANGUAGE_SPEC err record table: `path`, `line`, `column`, `stack` all present on all err records.
**Actual:** Stdlib return-err records (from json.parse, math.sqrt, fs.read, etc.) have only `kind`, `message`, `payload`. Location fields absent.
**Notes:** VM-thrown/caught errors DO have all fields (tested: `try { throw {...} } catch e { e.path }` works). The gap is between stdlib err records (returned directly, not thrown) and VM error records (caught from throw/runtime). LANGUAGE_SPEC says all err records have location fields — this is inaccurate for the stdlib-returned subset. A user who checks `err.path` after an fs.read failure will get a key error crash. The safe pattern (`err.kind` and `err.message`) is documented but the spec overstates field presence. The error-handling guide is more accurate but the spec should align.
**v3.0.0 regression?** NO (same behavior in v3.0.0)
**v3.0.1 patch closure issue?** NO

---

### BUG-05: Cyclic workflow detection: error embedded in result map, not surfaced as err record or non-zero exit
**Severity:** MEDIUM
**Subsystem:** workflow runner
**Affects:** v3.0.1
**Repro:**
```nodus
workflow cyclic {
    step A after B { return 1 }
    step B after A { return 2 }
}
let result = run_workflow(cyclic)
print(type(result))   // "map" — not "error"
print(result["error"]) // "Dependency cycle or missing tasks"
```
**Expected:** Per BUG-050 (v3.0.0 fix): cyclic dependency → non-zero exit OR err record returned. The fix was supposed to make cycles error.
**Actual:** `run_workflow` returns a plain map containing an `"error"` string key. Exit code 0. No err record. No non-zero exit. The error is reported but not in the standard Nodus error pattern (`type(result) == "error"`). User code checking `type(result) == "error"` will not detect the failure.
**Notes:** BUG-050 fix in v3.0.0 apparently changed from "silently produces empty result" to "produces result map with error field." The standard Nodus idiom (err record check) still cannot detect this failure. The caller must know to check `result["error"]` which is a non-standard pattern. Script exit code 0 is also wrong — callers (CI systems, scripts) cannot detect the failure.
**v3.0.0 regression?** Partial — v3.0.0 BUG-050 fix improved detection but left the err-record contract unimplemented
**v3.0.1 patch closure issue?** NO

---

## LOW

### BUG-06: strings.split wrong arity produces "Stack underflow" (VM internal error leaks)
**Severity:** LOW
**Subsystem:** stdlib / strings
**Affects:** v3.0.1
**Repro:**
```nodus
import "std:strings" as strings
strings.split("hello")  // only 1 arg, expects 2
// Runtime error: Stack underflow
```
**Expected:** Arity error "strings.split expects 2 arguments, got 1" or similar.
**Actual:** `Stack underflow` — a raw VM internal state error that reveals implementation details. Zero information about what the user did wrong.
**Notes:** Per error-surfaces.md, `std:strings` is intentionally out of Replace-contract scope. However, "Stack underflow" is arguably worse than the Python errors Replace was designed to eliminate — it's pure implementation noise with zero user value. The arity check appears to be at the Nodus-function-call level, not the Python level, suggesting this is a VM-level bug in arity handling for native functions rather than a Python error escape. LOW rather than MEDIUM because strings is documented as unwrapped, but the error quality is worse than anything in the wrapped namespaces.
**v3.0.0 regression?** Unknown (not tested in v3.0.0 eval)
**v3.0.1 patch closure issue?** NO

---

### BUG-07: 1.0 / 0.0 throws runtime error instead of returning infinity
**Severity:** LOW
**Subsystem:** VM / arithmetic
**Affects:** v3.0.1
**Repro:**
```nodus
let r = 1.0 / 0.0
// Runtime error: Division by zero
```
**Expected (IEEE 754):** `Infinity` (positive infinity for 1.0/0.0). IEEE 754 float division by zero produces infinity, not an error.
**Actual:** VM throws `Runtime error: Division by zero`. Not catchable without try/catch.
**Notes:** This is consistent with Python's `ZeroDivisionError` for float division (Python also raises an error for `1.0 / 0.0`), so Nodus inheriting this behavior is understandable. However, IEEE 754 compliance and most modern languages (JavaScript, C, Rust for floats) produce infinity. Users expecting IEEE 754 semantics will be surprised. The LANGUAGE_SPEC says "IEEE 754 floats" in the types description, which implies IEEE 754 division semantics. LOW severity because the behavior is consistent and a try/catch workaround exists.
**v3.0.0 regression?** NO (same behavior in v3.0.0)
**v3.0.1 patch closure issue?** NO

---

## COSMETIC

### BUG-08: len() float produces "6.0 orders" in print output
**Severity:** COSMETIC
**Subsystem:** stdlib / UX
**Affects:** v3.0.1
**Repro:**
```nodus
let orders = [1, 2, 3, 4, 5, 6]
print("Loaded " + str(len(orders)) + " orders")
// Output: "Loaded 6.0 orders"
```
**Expected:** "Loaded 6 orders"
**Actual:** "Loaded 6.0 orders" — because `len()` returns float, `str(6.0)` = "6.0"
**Notes:** BUG-E15 (v3.0.0) documented `len()` returning float as a design issue. V3_1_PLAN.md correctly defers the fix to v3.1 as a breaking change. This is documented and expected. Cosmetic only because the value is correct; only the display has the float suffix. Logged as cosmetic because the v3.1 plan acknowledges it.
**v3.0.0 regression?** NO (same behavior)
**v3.0.1 patch closure issue?** NO

---

## Summary

| Severity | Count | New in v3.0.1 | v3.0.1 patch closure failures |
|---|---|---|---|
| CRITICAL | 1 | 0 (pre-existing BUG-E12 not fixed) | 1 |
| HIGH | 1 | 1 (math.log two-arg) | 0 |
| MEDIUM | 3 | 2 (CLI help, cyclic workflow) + 1 pre-existing | 0 |
| LOW | 2 | 0-1 (strings arity, float div) | 0 |
| COSMETIC | 1 | 0 (pre-existing BUG-E15) | 0 |
| **Total** | **8** | **~4 new** | **1** |

### Routing

**v3.0.2 patch (CRITICAL/HIGH, patch regression or closure failure):**
- BUG-01: Fix 1I lexer/parser to emit parse error with message
- BUG-02: Fix math.log two-arg form (argument order bug)

**v3.1 (MEDIUM, new):**
- BUG-03: Fix workflow/graph run --help to show help not file error
- BUG-04: Reconcile LANGUAGE_SPEC err record table with stdlib err record fields
- BUG-05: Make cyclic workflow return err record and exit non-zero

**v3.1 (LOW/COSMETIC):**
- BUG-06: Improve strings.split arity error message
- BUG-07: Decide IEEE 754 float division policy and document
- BUG-08: Fix len() to return int (tracked in V3_1_PLAN)

### Pre-existing issues carried from v3.0.0 (now in v3.1 plan)

Per V3_1_PLAN.md, these are documented deferred items, not bugs:
- len() returns float (BUG-E15 → V3_1_PLAN)
- type() naming inconsistency (BUG-E17 → V3_1_PLAN)
- finally skipped after catch return (BUG-041 → V3_1_PLAN, but behavior appears correct in testing)
