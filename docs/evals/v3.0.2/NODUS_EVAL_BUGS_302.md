# Nodus v3.0.2 — Evaluation Bug Report

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Baseline:** v3.0.1 filed 8 bugs; v3.0.2 closes 2 (BUG-01, BUG-02) plus 1 undocumented fix (BUG-06)

---

## MEDIUM

### BUG-03: nodus workflow run --help / nodus graph run --help fail (carried from v3.0.1)
**Severity:** MEDIUM
**Subsystem:** CLI
**Affects:** v3.0.1, v3.0.2
**Repro:**
```sh
nodus workflow run --help   →  File not found: --help
nodus graph run --help      →  File not found: --help
```
**Expected:** Help text for the subcommand.
**Actual:** Treats `--help` as a script filename. Exit 1.
**Notes:** Not addressed in v3.0.2. v3.0.2 scope was CRITICAL/HIGH only. This is the highest-priority remaining item for v3.0.3 or v3.1.
**v3.0.0 regression?** Unknown
**v3.0.2 regression?** NO (carried from v3.0.1)

---

### BUG-04: Stdlib err records missing path/line/column/stack fields (carried from v3.0.1)
**Severity:** MEDIUM
**Subsystem:** stdlib / err record shape / docs
**Affects:** v3.0.1, v3.0.2
**Repro:**
```nodus
import "std:json" as json
let e = json.parse("{bad")
print(e.path)    // Key error: Missing record field: path
```
**Expected:** LANGUAGE_SPEC says all err records have path, line, column, stack.
**Actual:** Stdlib return-err records have only kind, message, payload. VM thrown/caught errors have all fields.
**Notes:** LANGUAGE_SPEC is inaccurate. The safe pattern (check kind/message) is documented elsewhere, but the spec contract should align with reality. Not addressed in v3.0.2.
**v3.0.2 regression?** NO

---

### BUG-05: Cyclic workflow returns map with error string, exit code 0 (carried from v3.0.1)
**Severity:** MEDIUM
**Subsystem:** workflow runner
**Affects:** v3.0.1, v3.0.2
**Repro:**
```nodus
workflow cyclic { step A after B { return 1 } step B after A { return 2 } }
let r = run_workflow(cyclic)
print(type(r))   // "map" — not "error"
```
**Expected:** err record OR non-zero exit so the failure is detectable by standard patterns.
**Actual:** Returns `{"error": "Dependency cycle or missing tasks", ...}`, exit 0. Standard `type(r) == "error"` check fails to detect it.
**Notes:** Not addressed in v3.0.2.
**v3.0.2 regression?** NO

---

## LOW

### BUG-07: 1.0 / 0.0 throws runtime error instead of IEEE 754 infinity (carried from v3.0.1)
**Severity:** LOW
**Subsystem:** VM / arithmetic
**Affects:** v3.0.1, v3.0.2
**Repro:**
```nodus
let r = 1.0 / 0.0   // Runtime error: Division by zero
```
**Expected (IEEE 754):** +Infinity
**Actual:** Runtime error thrown. LANGUAGE_SPEC says "IEEE 754 floats."
**Notes:** Consistent with Python behavior. LOW because workaround (try/catch) exists. Not addressed in v3.0.2.
**v3.0.2 regression?** NO

---

### BUG-NEW-01: 1ii gives runtime name error (not parse error) — LOW
**Severity:** LOW
**Subsystem:** parser / lexer
**Affects:** v3.0.2 (new in v3.0.2 — was partially masked in v3.0.1 by BUG-E12)
**Repro:**
```nodus
let x = 1ii   // Name error: Undefined variable: i
```
**Expected:** Parse error — `1ii` is not a valid integer literal.
**Actual:** `1i` lexes as the integer literal 1, then `i` is a separate identifier that resolves to a name error.
**Notes:** Corner case exposed by the 1I fix. When the lexer sees `1ii`, it correctly takes `1i` as the int literal, leaving `i` as an identifier. The name error is correct behavior given the tokenization, but a user who accidentally types `1ii` gets no parse-time guidance. LOW severity because `1ii` is a sufficiently unusual form.
**v3.0.2 regression?** YES (new behavior exposed by BUG-E12 fix; previously masked)

---

## COSMETIC

### BUG-08: len() float produces "3.0 orders" in print output (carried from v3.0.1)
**Severity:** COSMETIC
**Subsystem:** stdlib / UX
**Affects:** v3.0.1, v3.0.2
**Notes:** Documented in V3_1_PLAN.md as a breaking-change deferred to v3.1. Not addressed in v3.0.2.
**v3.0.2 regression?** NO

---

## Closed in v3.0.2

### BUG-01 (was CRITICAL): 1I parse error ← CLOSED
**Closed by:** BUG-V31E-01 (#75)
**Fix quality:** Excellent. "Integer suffix must be lowercase 'i', not 'I': use 1i instead of 1I" — names the form and provides inline fix. Works in both CLI and embedded mode.

### BUG-02 (was HIGH): math.log two-arg wrong result ← CLOSED
**Closed by:** BUG-V31E-02 (#76)
**Fix quality:** Correct. `math.log(100, 10)` = 2.0, `math.log(8, 2)` = 3.0 verified. `math.log_base` removed (acknowledged migration note). Undocumented side effect: architecture is now cleaner.

### BUG-06 (was LOW): strings.split arity gave "Stack underflow" ← CLOSED (undocumented)
**Closed by:** Unknown — not mentioned in CHANGELOG.
**Fix quality:** Improved. Now gives `type error: split(x, delimiter) expects a string` instead of "Stack underflow." Message still doesn't explain the arity issue explicitly, but it's no longer an internal error leak. CHANGELOG should have noted this.

---

## Summary

| Severity | v3.0.1 count | v3.0.2 count | Delta |
|---|---|---|---|
| CRITICAL | 1 | 0 | -1 (closed) |
| HIGH | 1 | 0 | -1 (closed) |
| MEDIUM | 3 | 3 | 0 (carried) |
| LOW | 2 | 2 | 0 (1 carried, 1 new edge case) |
| COSMETIC | 1 | 1 | 0 (carried) |
| **Total** | **8** | **6** | **-2 net** |

### Routing

**v3.0.3 patch (if warranted):**
- BUG-03: workflow/graph run --help routing fix (low-effort, high-visibility)

**v3.1:**
- BUG-04: LANGUAGE_SPEC err record table reconciliation
- BUG-05: Cyclic workflow err record + non-zero exit
- BUG-07: IEEE 754 float division policy decision
- BUG-NEW-01: 1ii parse error (LOW, minor)
- BUG-08: len() → int (already in V3_1_PLAN)
