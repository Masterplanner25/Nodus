# Nodus v3.0.2 — Independent Evaluation

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Time invested:** ~1.5 hours (focused re-run; prior research context reused)
**Baseline for comparison:** v3.0.1: 7.36/10 | v3.0.0: 6.45/10 | v2.0.0: 5.52/10

---

## TL;DR

v3.0.2 is a clean, correctly-scoped patch that closes both CRITICAL/HIGH issues from the v3.0.1 eval. The `1I` uppercase suffix now gives an excellent parse error with an inline fix suggestion ("use 1i instead of 1I"). `math.log(n, base)` now computes the correct value — `math.log(100, 10)` = 2.0, not 2.302. There is also an undocumented improvement: `strings.split` arity errors no longer leak "Stack underflow"; they now give a Nodus-voice type error. The composite score moves from **7.36 to 7.57** (+0.21). This is the right result for a two-fix patch — it fully closes its stated scope without introducing regressions. The four MEDIUM bugs from v3.0.1 (workflow help, err record location fields, cyclic workflow detection, float division) remain open and are the correct priority for v3.1.

---

## What Nodus v3.0.2 is

Nodus v3.0.2 is a targeted two-fix patch on top of v3.0.1, released the same day (2026-05-25). It addresses a packaging gap that prevented the v3.0.1 `1I` lexer fix from appearing in the distributed wheel, and corrects a logic error in the newly-added `math.log` two-argument form. No new features, no new APIs, no changes to the embedding layer, module system, or stdlib beyond the math.log fix. The language as described in the v3.0.1 evaluation is accurate for v3.0.2 modulo the two fixes.

---

## What changed from v3.0.1

**BUG-V31E-01 (#75) — 1I parse error:** The `1I` (uppercase I) lexer fix was implemented but not packaged in v3.0.1. v3.0.2 ships it correctly. `1I`, `42I`, and `100I` all produce `Syntax error: Integer suffix must be lowercase 'i', not 'I': use Ni instead of NI` with the specific form named. The error also surfaces correctly in embedded mode (returns a `type: 'syntax'` error dict, not a runtime error).

**BUG-V31E-02 (#76) — math.log two-arg:** `math.log(value, base)` now computes `ln(value)/ln(base)` correctly. `math.log(100, 10)` returns 2.0; `math.log(8, 2)` returns 3.0. The separate `math.log_base` export was removed (it produced wrong results and the two are now unified). Migration: `math.log_base(n, b)` → `math.log(n, b)`.

**Undocumented improvement:** `strings.split("hello")` (wrong arity) no longer produces "Stack underflow." It now gives a type error with the function signature. This is a meaningful improvement to error quality that should have been mentioned in the CHANGELOG.

---

## What works well

All items confirmed working in v3.0.1 continue working in v3.0.2. New additions:

- **`1I` parse error message:** Among the best error messages in the language. Specific form named, exact fix provided inline, consistent across CLI and embedded mode. ✓
- **`math.log` two-arg correctness:** All test cases verified (`log(100,10)=2.0`, `log(8,2)=3.0`, `log(0)=value_error`, `log(100,-1)=value_error`). ✓
- **`math.log_base` removed cleanly:** No residual export, proper key error if called. ✓
- **No regressions:** All 21/22 v3.0.1 patch closures still hold. `1i` valid literals unchanged. All stdlib, embedding, module system behavior unchanged. ✓
- **strings.split arity improved (undocumented):** `type error: split(x, delimiter) expects a string` — not a perfect arity message, but no longer a raw VM error. ✓

---

## Where v3.0.2 still hits sharp corners

All four remaining MEDIUM bugs from v3.0.1 are present unchanged:

- **BUG-03 (MEDIUM):** `nodus workflow run --help` and `nodus graph run --help` still produce "File not found: --help".
- **BUG-04 (MEDIUM):** Stdlib err records still missing `path`/`line`/`column`/`stack` fields that LANGUAGE_SPEC promises all err records have.
- **BUG-05 (MEDIUM):** Cyclic workflow still returns a plain map with an `"error"` string key and exits 0. The standard `type(r) == "error"` check cannot detect it.
- **BUG-07 (LOW):** `1.0 / 0.0` still throws instead of returning IEEE 754 infinity.
- **BUG-NEW-01 (LOW):** New edge case: `1ii` gives `Name error: Undefined variable: i` (not a parse error). The lexer correctly tokenizes `1i` then `i`, but the result is confusing. Exposed by the 1I fix.

The core friction for daily scripting — `len()` returning float, no string interpolation, `json.parse` precision loss on large integers — remains unchanged. These are all documented in V3_1_PLAN or understood design limitations.

---

## Patch closure verification (v3.0.2)

Two items in scope; both verified closed:

| Item | Claimed | Verified | Notes |
|---|---|---|---|
| BUG-V31E-01: 1I parse error | Fixed | **PASS** | Excellent message. Works in CLI and embedded mode. |
| BUG-V31E-02: math.log two-arg | Fixed | **PASS** | Correct for all tested inputs. log_base removed cleanly. |

No regressions found in any previously-passing test. The patch is clean.

Governance note: removing `math.log_base` in a patch release is technically a semver break. Justified given the function was demonstrably wrong, but the CHANGELOG's migration note should have been more prominent — it appears in a brief bullet rather than as a prominent breaking-change callout.

---

## The build-something-real experience

Same JSON transformer task as v3.0.1. Ran cleanly in ~12 minutes (faster than v3.0.1's ~20 min due to prior experience). Output identical. Friction points unchanged from v3.0.1:

- `str(len(orders))` → "3.0 orders" (len() float, deferred to v3.1)
- No string interpolation
- json.parse precision loss on large IDs

The v3.0.2 fixes (1I, math.log) did not surface in this scripting task. For data-processing scripts, the day-to-day experience is unchanged from v3.0.1.

---

## Verdict by audience

**For language designers / hobbyists:** The 1I fix is a good sign — packaging gap acknowledged and corrected promptly. math.log fix shows willingness to do breaking-but-correct patches. **7.5/10** — solid progress, process is maturing.

**For real production scripting:** Same as v3.0.1 for everyday work. The patch doesn't move the needle on the daily friction points. **6/10** — usable, same caveats as before.

**For Python/Lua/Starlark evaluators:** Same as v3.0.1. **5/10** — the patch closes correctness holes but doesn't add features.

**For v3.0.1 users:** Upgrade immediately — zero migration risk (except `math.log_base` → `math.log`), two correctness improvements. **Recommend unconditional upgrade.**

**For v3.0.0 users:** Upgrade path is v3.0.0 → v3.0.2 directly. No intermediate step required. All v3.0.1 and v3.0.2 improvements apply. **Recommend upgrade.**

---

## What v3.0.3 or v3.1 should prioritize

**v3.0.3 patch (one targeted fix, if warranted):**
1. **BUG-03:** Fix `workflow run/graph run --help` routing. This is the most visible remaining rough edge for users trying to learn the CLI. It's likely a one-line fix in the argument parser.

**v3.1 (release cycle):**
2. **len() → int:** Already in V3_1_PLAN. The `3.0 orders` print friction is the most common daily annoyance.
3. **String interpolation:** The single biggest ergonomics gap vs. peer languages.
4. **BUG-04:** Reconcile LANGUAGE_SPEC err record table with stdlib err record reality.
5. **BUG-05:** Cyclic workflow should return an err record and exit non-zero.
6. **Stdlib expansion (first tier):** Environment variables (`env.get`), regex. These two unlock the majority of automation use cases currently requiring a Python subprocess.

---

## Score progression

| Version | Score | Primary driver |
|---|---|---|
| v2.0.0 | 5.52 | Baseline |
| v3.0.0 | 6.45 | Integer type, error replacement, map/record |
| v3.0.1 | 7.36 | Embedding API fixed, stdlib completed |
| **v3.0.2** | **7.57** | **1I parse error, math.log correctness** |
| v3.1 target | ~8.5 | len() int, string interpolation, err spec fix |
| v3.2 target | ~9.2 | Stdlib expansion (regex, env, datetime) |
