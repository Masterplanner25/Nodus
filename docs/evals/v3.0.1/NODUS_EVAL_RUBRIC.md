# Nodus v3.0.1 — Evaluation Rubric

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Reference baselines:** v2.0.0: 5.52/10 | v3.0.0: 6.45/10

---

## Scoring Table

| Dimension | Score | v3.0.0 Score | Delta | Rationale |
|-----------|-------|------|-------|-----------|
| Install and first-run UX | 9/10 | 9/10 | 0 | `pip install nodus-lang==3.0.1` clean, 206 kB wheel, `nodus --version` immediate. DeprecationWarning on old API fires correctly. No regression. |
| CLI ergonomics | 7/10 | 8/10 | -1 | Grouped --help still excellent. `nodus run --help` shows all flags including --trace-errors. **Regression:** `nodus workflow run --help` and `nodus graph run --help` treat --help as a filename; broken. Minus 1 from v3.0.0. |
| Error message quality | 7/10 | 7/10 | 0 | Most runtime errors clear with file/line/col. Mixed map keys still excellent dual-fix suggestion. Unicode identifier improved ("ASCII letters only" message). **BUG-E12 not fixed:** 1I still gives name error not parse error. `strings.split` arity gives "Stack underflow." Net: no change from v3.0.0. |
| Parser robustness | 8/10 | 8/10 | 0 | Empty files, comment-only, long identifiers, BOM, CRLF all handled. Unicode identifier error improved. `1I` still lexes as two tokens (BUG-E12 not fixed). Hex/oct/bin int literals give confusing name errors. Malformed syntax handled cleanly. |
| Type system behavior | 7/10 | 7/10 | 0 | Equality coercion stable. `0 == false` true, `nil == false` false. `type()` names consistent (number/int/string/nil/bool/list/map/record). `has_key` crash on record still present (by design, documented in migration guide). `len()` float still present (documented in V3_1_PLAN). `1.0/0.0` throws (IEEE 754 surprise). No net change. |
| Integer type (v3.0.0+) | 8/10 | 8/10 | 0 | All arithmetic rules correct (int+int=int, int/int=float, etc.). Large integers precision-preserving. math.idiv, math.to_int/to_float/is_int all correct. `json.parse_int` exact. **Gap:** json.parse still returns floats — no path to preserve large integer IDs from JSON without manual parsing. `1I` not a parse error (BUG-E12). Display (bare "2" not "2i") documented in V3_1_PLAN. No net change. |
| Standard library completeness | 7/10 | 5/10 | +2 | Significant improvement: math.log, math.pow, path.relative, path.absolute, fs.mkdir, fs.delete all added. Still missing: `fs.list_dir` (correct name is `fs.listdir`; naming inconsistency with LANGUAGE_SPEC which says `listdir`). No major gaps versus error-surfaces.md contract now. +2 from v3.0.0. |
| Standard library correctness | 7/10 | 6/10 | +1 | json.parse(123) now returns err ✓. math.sqrt(-1) now returns err ✓. **NEW BUG:** math.log(n, base) computes ln(base) not log_base(n) — HIGH severity, arguments internally swapped in two-arg form. All single-arg math functions correct. fs.mkdir/delete work correctly. path.relative/absolute work correctly. +1 overall despite new math.log bug. |
| Python error replacement (v3) | 8/10 | 6/10 | +2 | Excellent improvement. All four wrapped namespaces now have complete coverage. json.parse type-checks input ✓, math.sqrt/log/pow wrapped ✓, fs.mkdir/delete wrapped ✓, path.relative/absolute wrapped ✓. --trace-errors and NODUS_TRACE_ERRORS=1 both produce correct output. No Python text in any err.message observed. math.log two-arg still returns wrong value (BUG-02) — that's a logic bug, not a voice/wrapping bug. +2 from v3.0.0. |
| err record shape (v3) | 7/10 | 8/10 | -1 | `err.payload` always nil (not absent) ✓. `err.kind` consistent ✓. **NEW FINDING:** Stdlib err records (json.parse, fs.read, math.*) are missing path/line/column/stack fields. LANGUAGE_SPEC says all err records have them. VM thrown errors have them. Documentation overstates stdlib err record field presence. -1 from v3.0.0 for this doc/impl gap. |
| Map/record disambiguation (v3) | 9/10 | 9/10 | 0 | Unchanged from v3.0.0 excellent state. `{foo: "bar"}` = record, `{"foo": "bar"}` = map, `{(k): v}` = map with computed key. Mixed keys parse error with dual fix suggestion. Multi-line map value works. Near-perfect. |
| Module system | 8/10 | 7/10 | +1 | Import with .nd extension now works (BUG-E16 fixed). Import nonexistent: clear error. Circular import: detected. Path traversal: blocked. Import inside fn: clear error. No doubling of extension. +1 from v3.0.0. |
| REPL | 5/10 | 5/10 | 0 | Not testable in automated mode. `nodus repl` starts and shows 3.0.1 banner. Banner correct. `:` commands not verified. No regression evident. |
| Workflow / graph runner | 4/10 | 4/10 | 0 | Basic workflow runs correctly. Cyclic dependency detection still inadequate (error embedded in result map, exit code 0). `nodus workflow run --help` broken. Insufficient testing of full orchestration features. Remain at 4/10. |
| Tracing / observability | 8/10 | 8/10 | 0 | `--trace` produces instruction trace ✓. `--trace-errors` produces Python backtrace on stderr ✓. NODUS_TRACE_ERRORS=1 works ✓. `--step-limit` fires ✓. `nodus debug --help` correct ✓. Trace format documented (BUG-E19 fixed). No change. |
| Embedded / programmatic API | 8/10 | 3/10 | +5 | Dramatic improvement. BUG-E03: host_globals now correctly reaches scripts. BUG-E04: host Python exceptions (ValueError, KeyError, custom) all propagate to Python caller. Two NodusRuntime instances properly isolated. DeprecationWarning on top-level run_source. Return dict shape correct. Still: top-level run_source returns VM object (confusing but deprecated). +5 from v3.0.0's critical state. |
| Documentation accuracy | 6/10 | 5/10 | +1 | migration guide now warns about has_key crash ✓ (BUG-E08). V3_1_PLAN.md correctly categorizes deferred items ✓. error-surfaces.md updated with sandbox precedence and new functions ✓. **Remaining gaps:** LANGUAGE_SPEC says all err records have path/line/column/stack — false for stdlib err records. Design docs 03/04 returned 404 from main branch. math.log two-arg behavior not documented. +1 net. |
| Documentation completeness | 7/10 | 6/10 | +1 | V3_1_PLAN.md is a useful addition — deferred items are now explicitly documented rather than silent gaps. Migration guide completeness improved. error-surfaces.md improved. Catch syntax (both forms now valid) needs documentation update (LANGUAGE_SPEC still may only show one form). +1 net. |
| Migration guide quality | 7/10 | 5/10 | +2 | has_key crash now prominently flagged as CRITICAL with crash description and safe alternative. Error kind changes documented. Record/map disambiguation documented. **Still missing:** int display convention difference, math.log two-arg behavior, workflow cyclic detection pattern change. +2 from v3.0.0 (the has_key crash fix was the highest-value doc change). |
| Stability under stress | 7/10 | 7/10 | 0 | Parser survives all stress inputs. No crashes from well-formed programs. Step limit works. Path traversal blocked. math.log two-arg gives wrong value (not crash). Cyclic workflow silently succeeds (not crash, but wrong). Recursion stack has 10001 entries when deep (BUG-048 cap applies to stderr display, not e.stack list). Stable but with new correctness issues. |
| Overall first-week usability | 7/10 | 6/10 | +1 | A competent engineer can build non-trivial things in Nodus v3.0.1 (JSON transformer built in ~20 min). Embedding API now works — Python integration is viable. Core language (integers, errors, modules, stdlib) is reliable. Sharp corners remain but are fewer and better documented. +1 from v3.0.0. |

---

## Composite Weighted Score

| Category | Weight | Score | Weighted |
|----------|--------|-------|---------|
| Core language (parser, type system, control flow) | 15% | 7.3 | 1.10 |
| New v3.0.0 features (int type, err replacement, err shape, map/record) | 20% | 7.8 | 1.56 |
| Standard library (completeness + correctness) | 15% | 7.0 | 1.05 |
| CLI and tooling | 10% | 7.5 | 0.75 |
| Embedding API | 10% | 8.0 | 0.80 |
| Documentation (accuracy + completeness + migration) | 15% | 6.7 | 1.00 |
| Error quality and observability | 10% | 7.5 | 0.75 |
| Stability under stress | 5% | 7.0 | 0.35 |

**Composite score: 7.36/10**

---

## Comparison to baselines

- v2.0.0: 5.52/10
- v3.0.0: 6.45/10
- **v3.0.1: 7.36/10** (+0.91 from v3.0.0, +1.84 from v2.0.0)

The v3.0.1 patch delivers a meaningful improvement (+14% from v3.0.0), driven almost entirely by the embedding API recovery (+5) and stdlib completion (+2 completeness, +2 error replacement).

---

## Dimensions where v3.0.1 moved vs v3.0.0

| Dimension | Direction | Driver |
|---|---|---|
| Standard library completeness | +2 | math.log/pow, path.relative/absolute, fs.mkdir/delete added |
| Python error replacement | +2 | All wrapped namespaces complete |
| Embedding API | +5 | BUG-E03 and BUG-E04 both fixed |
| Module system | +1 | .nd extension import fixed (BUG-E16) |
| Standard library correctness | +1 | json.parse type-check, math.sqrt wrapped |
| Documentation accuracy | +1 | has_key crash warning, V3_1_PLAN added |
| Documentation completeness | +1 | V3_1_PLAN, migration guide expanded |
| Migration guide quality | +2 | has_key crash now prominent |
| Overall first-week usability | +1 | Embedding works, fewer sharp corners |

## Dimensions where v3.0.1 stayed flat or regressed vs v3.0.0

| Dimension | Direction | Driver |
|---|---|---|
| CLI ergonomics | -1 | workflow run --help / graph run --help broken |
| err record shape | -1 | Stdlib err records missing location fields (documented but LANGUAGE_SPEC still wrong) |
| Install/first-run | 0 | No change (already good) |
| Error message quality | 0 | BUG-E12 not fixed, new Stack underflow in strings |
| Parser robustness | 0 | BUG-E12 not fixed |
| Type system | 0 | len() float deferred, IEEE 754 surprises remain |
| Integer type | 0 | Good but json precision gap unchanged |
| REPL | 0 | Not testable |
| Workflow runner | 0 | Cyclic detection still inadequate |
| Tracing | 0 | Already good, no regression |
| Stability | 0 | New correctness bugs (math.log) but no crashes |

---

## Scoring rationale notes

Weights unchanged from v3.0.0 eval for comparability. The +0.91 gain reflects the patch's success on the dimensions it targeted. The patch's most significant miss (BUG-E12 not landing) costs points in Error message quality and Parser robustness without causing a dimension-level drop. The new HIGH bug (math.log two-arg) prevents Standard library correctness from recovering to 8.
