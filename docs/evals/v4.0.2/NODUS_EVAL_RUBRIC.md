# Nodus v4.0.2 — Eval Rubric

**Eval date:** 2026-06-10  
**Version:** v4.0.2 (PyPI, POST-PUBLISH)  
**Evaluator:** Claude Fable 5 (independent)

---

## Scoring table

Dimension                                    | Score | Rationale
---------------------------------------------|-------|----------
Install and first-run UX                     | 9/10  | `pip install nodus-lang` → immediate, correct version. Missing-extra error gave exact install command.
CLI ergonomics                               | 7/10  | `run`, `fmt`, `check`, `ast`, `dis` all work. `test` not in `--help` (B17); `--trace` shows bytecode not step events.
Error message quality                        | 5/10  | Excellent on known paths (undefined var, import not found). Disastrous on B1: wrong-file traces, recursion errors pointing nowhere near the cause.
Parser robustness                            | 7/10  | Syntax is minimal and regular. Single-line expression rule is the main ergonomic constraint.
Workflow / goal DSL                          | 7/10  | `step after dep`, parallel levels, `plan_workflow()`, `state`, `checkpoint` all work. B2 (step retries) and B3 (state in interpolation) are serious gaps.
Coroutine / channel runtime                  | 6/10  | Nested schedulers work. Fatal: coroutine errors swallowed (B5); `recv()` on empty channel orphans silently.
`@exactly_once` annotation                   | 8/10  | **Verified working in Sentinel.** Duplicate page suppressed; audit log shows correct single execution. (Fixed from v4.0.1 breakage.)
`@retry` annotation                          | 7/10  | **Verified working in Sentinel.** 2 failures then success confirmed. Step-level `retries:` is a separate non-working path (B2).
`std:effects` manual protocol               | 5/10  | Works once you read the runtime source; documented API does not exist (B15).
`std:circuit_breaker`                        | 5/10  | State transitions work (`closed → open` verified). Real signature differs from docs (B10); failures indistinguishable from success (B11).
`std:tool` registry                          | 5/10  | Works only with inline registration (B1) and simple-form schema (B6). Failure modes are catastrophic and undocumented.
`std:memory` (kv + namespaces)               | 9/10  | Clean cross-workflow handoff verified. No issues encountered.
`std:identity`                               | 5/10  | `execution_unit_id()` works; `trace_id()`/`session_id()` nil under CLI (B12).
`std:test` framework                         | 7/10  | Good assertion library (12/12 passing in Sentinel). Windows crash (B8); import-rooting defect (B9).
stdlib quality (fs/json/strings/hash/col)    | 8/10  | Mostly solid. `time.format` broken (B7).
Documentation accuracy                       | 4/10  | Volume and structure excellent. AI-primitives guide is wrong about nearly every API it shows (B6/B13/B14/B15). Verified-example sections are accurate; prose guides drift.
AI-authorability                             | 6/10  | Syntax high (LLM can generate near-correct code). Failure modes low (wrong-file traces, storm symptoms defeat LLM debugger).
Production readiness                         | 3/10  | B1 (execution storm), B2 (retry silent no-op), B18 (unbounded state accumulation). `nodus stability` correctly labels orchestration as Experimental.
Overall release quality                      | 5/10  | Strongest AI-native feature set of any comparable language. P0 bugs in CLI-facing orchestration prevent recommendation for production use.

---

## Verdict

**5.2 / 10** — The language design and AI-native primitives justify the project's
existence. Runtime trustworthiness for the orchestration tier (the reason to use Nodus)
is not yet there. Fix B1, B2, and bring `ai-primitives.md` under the doc-testing gate;
re-eval at that point.
