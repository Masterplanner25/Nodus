# Nodus v3.0.2 — Evaluation Rubric

**Evaluator:** Claude Code (researcher mode, stress test)
**Date:** 2026-05-25
**Reference baselines:** v2.0.0: 5.52/10 | v3.0.0: 6.45/10 | v3.0.1: 7.36/10

---

## Scoring Table

| Dimension | v3.0.1 | v3.0.2 | Delta | Rationale |
|-----------|--------|--------|-------|-----------|
| Install and first-run UX | 9/10 | 9/10 | 0 | Clean install, immediate version confirm. No change. |
| CLI ergonomics | 7/10 | 7/10 | 0 | `workflow run --help` and `graph run --help` still broken (BUG-03, not in v3.0.2 scope). All other CLI unchanged. |
| Error message quality | 7/10 | 8/10 | **+1** | `1I` now gives a parse error with inline fix hint ("use 1i instead of 1I") — best-in-class message for this error category. `strings.split` arity no longer gives "Stack underflow" (undocumented improvement). Net +1. |
| Parser robustness | 8/10 | 9/10 | **+1** | `1I` and `42I` now correctly error at parse time. `1ii` edge case (LOW) is a new minor gap. All prior parser tests pass. +1. |
| Type system behavior | 7/10 | 7/10 | 0 | No changes. len() float, IEEE 754 division, has_key crash all unchanged. |
| Integer type (v3.0.0+) | 8/10 | 8/10 | 0 | Core arithmetic unchanged. `1I` fix improves the integer type experience slightly but not enough to move the score — the precision gap from json.parse is the bigger ceiling. |
| Standard library completeness | 7/10 | 7/10 | 0 | `math.log_base` removed (was broken, so net neutral). No new functions added. |
| Standard library correctness | 7/10 | 8/10 | **+1** | `math.log(n, base)` now correct. All prior correct functions unchanged. `math.log_base` removed rather than left broken. +1. |
| Python error replacement (v3) | 8/10 | 8/10 | 0 | Unchanged. All wrapped surfaces still work correctly. |
| err record shape (v3) | 7/10 | 7/10 | 0 | BUG-04 (missing location fields) not addressed. Unchanged. |
| Map/record disambiguation (v3) | 9/10 | 9/10 | 0 | Unchanged. Still excellent. |
| Module system | 8/10 | 8/10 | 0 | Unchanged. All v3.0.1 fixes still hold. |
| REPL | 5/10 | 5/10 | 0 | Not testable non-interactively. No changes. |
| Workflow / graph runner | 4/10 | 4/10 | 0 | BUG-03 and BUG-05 both unaddressed. Unchanged. |
| Tracing / observability | 8/10 | 8/10 | 0 | Unchanged. All trace flags work correctly. |
| Embedded / programmatic API | 8/10 | 8/10 | 0 | No regression. BUG-E12 fix means embedded `1I` now returns a proper syntax error dict instead of a runtime name error dict — minor implicit improvement, not enough to move score. |
| Documentation accuracy | 6/10 | 6/10 | 0 | LANGUAGE_SPEC err field gap (BUG-04) still present. CHANGELOG missing undocumented strings.split fix. No regression. |
| Documentation completeness | 7/10 | 7/10 | 0 | No new documentation added. CHANGELOG migration note for math.log_base is correct. |
| Migration guide quality | 7/10 | 7/10 | 0 | v3.0.2 adds a migration note for math.log_base → math.log. Adequate for the change. No other migration needed. |
| Stability under stress | 7/10 | 7/10 | 0 | 1I fix reduces runtime surprises. `1ii` edge case (new LOW) is minor. Net neutral. |
| Overall first-week usability | 7/10 | 7.5/10 | **+0.5** | `1I` fix closes a genuine "what is this error" moment for anyone learning the integer type. math.log fix makes math-heavy scripts correct. strings.split arity improvement reduces debugging friction. Accumulated small UX wins move the needle. |

---

## Composite Weighted Score

| Category | Weight | v3.0.1 Score | v3.0.2 Score | Weighted Change |
|----------|--------|-------------|-------------|-----------------|
| Core language (parser, type system, control flow) | 15% | 7.3 | 7.7 | +0.06 |
| New v3.0.0 features (int type, err replacement, err shape, map/record) | 20% | 7.8 | 7.9 | +0.02 |
| Standard library (completeness + correctness) | 15% | 7.0 | 7.5 | +0.08 |
| CLI and tooling | 10% | 7.5 | 7.5 | 0 |
| Embedding API | 10% | 8.0 | 8.0 | 0 |
| Documentation (accuracy + completeness + migration) | 15% | 6.7 | 6.7 | 0 |
| Error quality and observability | 10% | 7.5 | 8.0 | +0.05 |
| Stability under stress | 5% | 7.0 | 7.0 | 0 |

**v3.0.2 composite score: 7.57/10**

---

## Comparison to baselines

| Version | Score | vs Previous |
|---------|-------|-------------|
| v2.0.0 | 5.52/10 | — |
| v3.0.0 | 6.45/10 | +0.93 |
| v3.0.1 | 7.36/10 | +0.91 |
| **v3.0.2** | **7.57/10** | **+0.21** |

v3.0.2 delivers a modest but clean +0.21 improvement. This is the expected profile for a two-fix patch: it fully closes the outstanding CRITICAL and HIGH issues without touching the medium/low/cosmetic backlog.

---

## Dimensions where v3.0.2 moved vs v3.0.1

| Dimension | Direction | Driver |
|---|---|---|
| Error message quality | +1 | 1I parse error message excellent; strings.split arity improved |
| Parser robustness | +1 | 1I/42I correctly rejected at parse time |
| Standard library correctness | +1 | math.log two-arg correct |
| Overall first-week usability | +0.5 | Accumulated small UX wins |

## Dimensions where v3.0.2 stayed flat vs v3.0.1

All other dimensions unchanged. The four carried MEDIUM bugs (BUG-03, BUG-04, BUG-05, BUG-07) keep workflow runner at 4/10, err record shape at 7/10, and CLI ergonomics at 7/10.

---

## Score interpretation relative to 10/10

| Score band | Status |
|---|---|
| **7.57 — current** | Usable with known limitations. Core language reliable. |
| ~8.5 | Requires v3.1: len() int, string interpolation, err record spec fix, workflow correctness |
| ~9.2 | Requires v3.2: regex, datetime, env vars, test framework |
| ~9.5 | Requires v4.0: full stdlib, package ecosystem, IDE integration |
| 10.0 | Requires: production track record + community + stability policy |
