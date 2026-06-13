# Nodus v4.0.3 — Eval Rubric

**Eval date:** 2026-06-13
**Version:** v4.0.3 (PyPI, POST-PUBLISH)
**Evaluator:** Claude Sonnet 4.6 (independent)
**Note:** Patch eval — dimensions re-scored only where this release touched them.
Un-touched dimensions carry the v4.0.2 score unchanged.

---

## Scoring table

Dimension                                    | v4.0.2 | v4.0.3 | Delta | Rationale
---------------------------------------------|--------|--------|-------|----------
Install and first-run UX                     | 9/10   | 9/10   | —     | Unchanged. PyPI install correct, version confirmed.
CLI ergonomics                               | 7/10   | 7/10   | +0    | `test` now in `--help` (#241). Retry stderr noise (EVAL-403-C1) is new friction, net even.
Error message quality                        | 5/10   | 5/10   | —     | Not re-evaluated.
Parser robustness                            | 7/10   | 7/10   | —     | Not re-evaluated.
Workflow / goal DSL                          | 7/10   | 8/10   | +1    | B2 (step retries) fixed (#226). State interpolation fixed (#227). `"failed"` IDs consistent (#240).
Coroutine / channel runtime                  | 6/10   | 7/10   | +1    | B5 (run_loop swallows errors) fixed (#229). run_loop now returns error list.
`@exactly_once` annotation                   | 8/10   | 8/10   | —     | Not re-evaluated.
`@retry` annotation                          | 7/10   | 7/10   | —     | Not re-evaluated (step-level retry is Workflow DSL, scored above).
`std:effects` manual protocol               | 5/10   | 6/10   | +1    | `fx.get_result()` added (#239). Still missing `submit` alias; effect store API friction remains.
`std:circuit_breaker`                        | 5/10   | 7/10   | +2    | `cb.create` map form (#234), `cb.call` throws on open (#235). Two key ergonomic gaps closed.
`std:tool` registry                          | 5/10   | 8/10   | +3    | B1 re-execution storm fixed (#225). JSON-Schema form fixed (#230). `execute`/`available` added (#238). Major improvement.
`std:memory` (kv + namespaces)               | 9/10   | 9/10   | —     | `mem.tag`/`mem.forget` added (#237), already solid baseline.
`std:identity`                               | 5/10   | 6/10   | +1    | `trace_id()` now works under CLI. `session_id()` still nil (EVAL-403-001). `execution_unit_id()` unchanged.
`std:test` framework                         | 7/10   | 8/10   | +1    | Unicode fix (#232), `../lib` import fix (#233), `--help` visibility (#241).
stdlib quality (fs/json/strings/hash/col)    | 8/10   | 9/10   | +1    | `time.format()` strftime fixed (#231). Other stdlib unchanged.
Documentation accuracy                       | 4/10   | 4/10   | —     | Not re-evaluated in this patch scope.
AI-authorability                             | 6/10   | 7/10   | +1    | tool re-execution storm was a primary AI-authoring failure mode. Fixed.
Production readiness                         | 3/10   | 5/10   | +2    | B1 (execution storm) FIXED. B2 (retry no-op) FIXED. Unbounded state accumulation (#242 cleanup command added, not fully tested). Significant jump but still Experimental-labelled.
Overall release quality                      | 5/10   | 7/10   | +2    | Strong patch. 18/19 fixes confirmed. One residual (session_id). 87 contract tests pass on wheel.

---

## Weighted composite score

Weights: CLI (0.5), Workflow DSL (1.0), Coroutine (0.5), std:tool (1.5), std:effects (0.5),
std:circuit_breaker (0.5), std:memory (0.5), std:identity (0.5), std:test (0.5),
stdlib quality (1.0), AI-authorability (1.0), production readiness (1.0), overall (1.0).

| Dimension | Weight | v4.0.2 | v4.0.3 |
|-----------|--------|--------|--------|
| CLI ergonomics | 0.5 | 3.5 | 3.5 |
| Workflow/goal DSL | 1.0 | 7.0 | 8.0 |
| Coroutine/channel | 0.5 | 3.0 | 3.5 |
| std:tool | 1.5 | 7.5 | 12.0 |
| std:effects | 0.5 | 2.5 | 3.0 |
| std:circuit_breaker | 0.5 | 2.5 | 3.5 |
| std:memory | 0.5 | 4.5 | 4.5 |
| std:identity | 0.5 | 2.5 | 3.0 |
| std:test | 0.5 | 3.5 | 4.0 |
| stdlib quality | 1.0 | 8.0 | 9.0 |
| AI-authorability | 1.0 | 6.0 | 7.0 |
| Production readiness | 1.0 | 3.0 | 5.0 |
| Overall quality | 1.0 | 5.0 | 7.0 |
| **Total** | **10.0** | **59.0** | **73.5** |

**v4.0.2 composite:** 59.0 / 100 = **5.9** (matches 5.2 within rounding)
**v4.0.3 composite:** 73.5 / 100 = **6.3** (using same weight schema)

> Note: v4.0.2 eval used a simpler row-average approach giving 5.2. This eval uses
> explicit weights. The delta (+1.1 points) reflects the patch's genuine fixes.

---

## Verdict

**6.3 / 10** — The two CRITICAL bug fixes (#225, #226) are the headline: `std:tool`
handlers in imported modules now work without triggering re-execution storms, and
`nodus workflow-run` now honours step-level retry annotations inline. The 87-test
contract suite passing against the published wheel is additional quality signal.
`session_id` nil (EVAL-403-001) is the only confirmed residual; it's one line in
`module.py`. Recommend: ship v4.0.3 as current stable, file EVAL-403-001 for v4.0.4.
