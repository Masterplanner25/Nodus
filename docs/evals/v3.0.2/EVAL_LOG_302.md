# Nodus v3.0.2 — Evaluation Log

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Version under test:** nodus-lang 3.0.2 (PyPI)
**Baseline:** v3.0.1 eval scored 7.36/10, v3.0.0 scored 6.45/10
**Working directory:** C:\dev\Testing Enviroment (venv: .venv302)

---

## SECTION 0 — SETUP

### [00:00] Fresh venv
```
python -m venv .venv302
pip install nodus-lang==3.0.2
```
Installed cleanly. Wheel: 207.0 kB (slightly larger than v3.0.1's 206.7 kB — consistent with two targeted fixes).

### [00:01] Version confirm
```
nodus --version  →  Nodus 3.0.2
```
PASS.

### [00:02] Directories created
scratch302/, patch302-verification/ created.

---

## SECTION 1 — RESEARCH PASS

### [01:00] CHANGELOG [3.0.2] — 2026-05-25

**Two fixes shipped:**

**BUG-V31E-01 (#75):** Parser now produces parse error for uppercase integer suffixes (`1I`, `42I`). CHANGELOG notes the fix was packaged in v3.0.1 but failed to appear in the wheel due to a packaging gap. This is the closure of BUG-E12 (originally filed in v3.0.0 eval, listed as a patch closure failure in the v3.0.1 eval).

**BUG-V31E-02 (#76):** `math.log(value, base)` now correctly computes log-base-n. The previous implementation silently returned `ln(base)` instead of `ln(value)/ln(base)`. The fix unified `log` and `log_base` wrappers into a single function; the separate `math.log_base` export was removed.

**Migration note:** Callers using `math.log_base(n, base)` should switch to `math.log(n, base)`.

### [01:01] Scope assessment
v3.0.2 is a targeted two-fix patch. The four MEDIUM/LOW/COSMETIC bugs from the v3.0.1 eval (BUG-03 through BUG-07) are NOT addressed in this release. This is the correct scoping decision for a patch — only CRITICAL and HIGH items from the v3.0.1 eval were in scope, and both were fixed.

### [01:02] math.log_base removal — breaking change assessment
`math.log_base` is removed. Since it was introduced in v3.0.1 (two releases ago), real-world adoption is likely minimal. The migration is `math.log_base(n, b)` → `math.log(n, b)`. Semver-strictly this is a breaking change in a patch, which is a governance note. In practice: acceptable given the function was demonstrably broken in v3.0.1 (returned wrong values), so removing and replacing it is a net improvement.

---

## SECTION 2 — BASELINE

All Section 2 checks from v3.0.1 eval re-run. Results:

- `nodus run hello.nd` → `Hello from Nodus v3.0.2!` ✓
- `nodus check hello.nd` → OK ✓
- `nodus --help` → grouped sections ✓
- `nodus run --help` → all flags including --trace-errors ✓
- `nodus workflow --help` → subcommands listed ✓
- `nodus workflow run --help` → **STILL FAILS** "File not found: --help" — BUG-03 not in v3.0.2 scope
- `nodus graph run --help` → **STILL FAILS** same — BUG-03 not in scope
- `nodus debug --help` → shows debugger commands ✓
- `NodusRuntime.run_source` dict shape: ok, stage, filename, stdout, stderr, result, errors, diagnostics, error ✓
- DeprecationWarning on top-level `run_source` → fires ✓
- NODUS_TRACE_ERRORS=1 → trace output on stderr, stdout clean ✓

---

## SECTION 3 — STRESS TEST

### [03.X] v3.0.2 Patch Closure Verification (primary focus)

#### BUG-V31E-01 / BUG-E12: 1I uppercase suffix parse error

| Input | Expected | Actual | Status |
|---|---|---|---|
| `let x = 1I` | parse error with suggestion | `Syntax error: Integer suffix must be lowercase 'i', not 'I': use 1i instead of 1I` | **PASS** |
| `let x = 42I` | parse error with suggestion | `Syntax error: Integer suffix must be lowercase 'i', not 'I': use 42i instead of 42I` | **PASS** |
| `let x = 1Int` | parse error | `Syntax error: Integer suffix must be lowercase 'i', not 'I': use 1i instead of 1I` | **PASS** |
| `let x = 1i` (valid) | runs correctly | `2` (1i + 1i) | **PASS** |
| `let x = 1ii` | error | `Name error: Undefined variable: i` (LOW: parses as `1i` then `i`) | PARTIAL |
| In embedded mode | syntax error in error dict | dict with `type: 'syntax'`, correct message | **PASS** |

The error message is excellent — includes the specific offending form AND the correct fix inline. Best-in-class parse error UX for this category.

**Edge case noted:** `1ii` still gives a runtime name error rather than a parse error. `1i` lexes as an integer literal, then `i` is the next identifier. This is LOW severity — the input is nonsensical — but the error is confusing.

#### BUG-V31E-02 / BUG-02: math.log two-arg correct

| Call | Expected | Actual | Status |
|---|---|---|---|
| `math.log(100, 10)` | 2.0 | 2.0 | **PASS** |
| `math.log(8, 2)` | 3.0 | 3.0 | **PASS** |
| `math.log(1)` | 0.0 | 0.0 | **PASS** |
| `math.log(10)` | 2.302... | 2.302... | **PASS** |
| `math.log(0)` | value_error | value_error | **PASS** |
| `math.log(-1)` | value_error | value_error | **PASS** |
| `math.log(100, -1)` | value_error | value_error | **PASS** |
| `math.log_base(n, b)` | removed | key error (export gone) | **PASS** |

All math.log behaviors correct.

### [03.1] Parser and lexer — v3.0.2 changes

All v3.0.1 passing parser tests pass in v3.0.2. Additional 1I coverage above. Unicode identifier error message still: "Identifiers must use ASCII letters only" ✓. BOM ✓. CRLF ✓. Long identifiers ✓.

**Regression check:** `1i` valid integer literal still works. `1I` now correctly errors. `42I`, `100I` all correctly error with customized messages ("use 42i instead of 42I").

### [03.2] Integer type

No changes. All v3.0.1 passing tests still pass. `math.log` single-arg unchanged. `math.idiv`, `math.parse_int`, `math.to_int/to_float/is_int` unchanged. `len()` still float (v3.1 deferred). `json.parse_int` still correct.

### [03.3–03.5] Type system, map/record, err record shape

No changes in v3.0.2. All previously passing tests pass. BUG-04 (stdlib err records missing path/line/column/stack) still present — not in v3.0.2 scope.

### [03.6] Control flow

No regressions. `catch (e)` and `catch e` both work. `else if` ✓. `--step-limit` ✓. Finally behavior unchanged.

### [03.7] Module system

No regressions. `import "./mod.nd"` ✓. `import "./mod"` ✓. Circular import detected ✓. Path traversal blocked ✓.

### [03.8] Python error replacement

**Regression check on all wrapped surfaces:**
- `json.parse(123)` → type_error ✓ (BUG-E01 still fixed)
- `math.sqrt(-1)` → value_error ✓ (BUG-E02 still fixed)
- `math.log(0)` → value_error ✓
- `math.log(100, 10)` → 2.0 ✓ (BUG-02 fixed)
- `math.pow(0, -1)` → math_error ✓
- `fs.mkdir("scratch302")` (existing) → io_error ✓
- `fs.delete("nonexist.txt")` → io_error ✓
- `path.relative("foo", "/abs")` → path_error ✓
- `--trace-errors` output format unchanged ✓

### [03.9] Standard library — notable change

**strings.split arity (BUG-06 improved, undocumented):**
v3.0.1 gave "Stack underflow" for `strings.split("hello")`. v3.0.2 gives `type error: split(x, delimiter) expects a string`. This is a significant UX improvement — it's no longer a raw internal error. The message isn't perfect (doesn't explain arity), but it's Nodus-voice and gives the function signature.

This improvement is **not mentioned in the v3.0.2 CHANGELOG**. Either it's a side effect of the math.log refactor (unlikely) or it's an unreported fix. Either way, it's a positive finding.

### [03.12] Workflow runner

No changes. Basic workflow runs ✓. Cyclic workflow BUG-05 still present (returns map with "error" string, exit 0). `workflow run --help` BUG-03 still present.

### [03.14] Error message quality summary (changes from v3.0.1)

| Error scenario | v3.0.1 Quality | v3.0.2 Quality | Change |
|---|---|---|---|
| `1I` uppercase suffix | ✗ Name error | ✓ Parse error with fix hint | **Improved** |
| `42I` | ✗ Name error | ✓ "use 42i instead of 42I" | **Improved** |
| `math.log(n, base)` wrong result | no error, wrong value | correct result | **Fixed (not error quality)** |
| `strings.split` arity | ✗ Stack underflow | ✓ type error with fn signature | **Improved (undocumented)** |
| All other previously good errors | unchanged | unchanged | Same |

### [03.15] Embedding API

No regressions. `1I` in embedded mode now correctly returns a syntax error dict with the proper message rather than a runtime error dict. This is an implicit improvement of the BUG-E12 fix — embedded callers get proper error categorization.

---

## SECTION 4 — BUILD SOMETHING REAL (v3.0.2)

Same JSON transformer task as v3.0.1 eval. Rebuilt with v3.0.2.

**Time to working:** ~12 minutes (faster than v3.0.1's ~20 min; prior experience eliminated import-placement mistake and json.parse_int wrong-path exploration).

**Friction points — unchanged from v3.0.1:**
1. `len(orders)` → 3.0 (float): `"Completed: 3.0 orders"` still prints with decimal. Deferred v3.1 item.
2. No string interpolation: `str(x) + " orders"` still required.
3. `json.parse` precision loss on large IDs: unchanged.

**Friction points — improved in v3.0.2:**
None directly visible in the scripting task. The integer suffix error is relevant to authored code, not data-processing scripts.

**New friction discovered:** None. The task is cleaner to write a second time with known patterns.

**Comparison to v3.0.1 real-task:** Identical output. Same friction. The v3.0.2 fixes (1I parse error, math.log) don't surface in typical scripting work — they're correctness fixes for edge cases and math-heavy scripts. The day-to-day scripting experience is unchanged.

---

## SECTION 5 — META-OBSERVATIONS

### Patch quality assessment

v3.0.2 is a clean, targeted patch. Both CHANGELOG items verified. The math.log fix is architecturally cleaner than the v3.0.1 implementation (unified function, removed the broken log_base). The 1I fix is production-quality: the error message names the exact form, provides the correct alternative inline, and works in embedded mode.

The undocumented strings.split improvement is a positive surprise. The CHANGELOG should have noted it even if minor — users who hit "Stack underflow" in v3.0.1 would benefit from knowing this changed.

### Governance note

Removing `math.log_base` in a patch release is technically a semver violation. In practice it's justified (the function produced wrong results, so its removal is a correction). A formal deprecation cycle would be cleaner, but given the two-release age of the function and the severity of the correctness issue, this is acceptable.

### What didn't change

All four remaining MEDIUM/LOW bugs from the v3.0.1 eval are present unchanged:
- BUG-03: workflow/graph run --help broken
- BUG-04: stdlib err records missing location fields
- BUG-05: cyclic workflow detection inadequate
- BUG-07: float division by zero throws

BUG-08 (len() float cosmetic): still present, correctly deferred to v3.1.

---

## PATCH CLOSURE SUMMARY

| Bug | v3.0.1 Status | v3.0.2 Status |
|---|---|---|
| BUG-E12/BUG-01 (1I parse error) | FAIL — patch closure failure | **PASS** |
| BUG-02 (math.log two-arg wrong) | FAIL — new defect | **PASS** |
| BUG-03 (workflow run --help) | FAIL — not in scope | FAIL — not in scope |
| BUG-04 (stdlib err location fields) | FAIL — not in scope | FAIL — not in scope |
| BUG-05 (cyclic workflow) | FAIL — not in scope | FAIL — not in scope |
| BUG-06 (strings.split Stack underflow) | FAIL — not in scope | **PASS (undocumented)** |
| BUG-07 (1.0/0.0 throws) | FAIL — not in scope | FAIL — not in scope |
