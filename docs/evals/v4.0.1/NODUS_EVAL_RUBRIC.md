# Nodus v4.0.1 — Eval Rubric

**Eval date:** 2026-06-10  
**Version:** v4.0.1 (PyPI, POST-PUBLISH)

---

## Scoring table

Dimension                                | Score | Rationale
-----------------------------------------|-------|----------
Install and first-run UX                 | 9/10  | `pip install nodus-lang==4.0.1` → immediate, correct version. Minor: pip upgrade notice noise.
CLI ergonomics                           | 8/10  | `run`, `fmt`, `check` all work. `--help` complete. No regressions.
Error message quality                    | 7/10  | Good on known paths (undefined var, unknown annotation, sandbox). Poor on new paths (BUG-401-001, BUG-401-004 silent failure).
Parser robustness                        | 7/10  | Multiline expressions work. Trailing comma regression (BUG-401-003). Named arg syntax not supported.
Annotation syntax (@retry/@exactly_once) | 2/10  | `@retry` silently skips function body (HIGH). `@exactly_once` broken on idempotency AND return value (2× CRITICAL). Unknown annotation gives good compile error.
Compound assignment operators            | 9/10  | All 7 forms correct. Division truncates to int for int/int. Good error for undefined target.
Multiline expressions                    | 7/10  | Basic cases work. Trailing comma in list is a regression (BUG-401-003).
std:math bit operations                  | 10/10 | All 9 test cases return correct values. Clean implementation.
Sandbox allowlists (allowed_commands)    | 1/10  | CRITICAL: `allowed_commands` not enforced at all. Blocked binaries run freely. `allow_env=False` works correctly.
Embedding API additions                  | 5/10  | `get_execution_stats()` ✅, `clear_shared_state()` ✅. `event_sinks` never fires (MEDIUM). `coroutine_timeout_ms` functional but silent. `_last_vm` still public (LOW).
Bounded channels                         | 6/10  | Positional API works, good error on overflow. Named-arg form silently broken (docs gap, BUG-401-008). `channel(0i)` behavior undocumented.
Security fix verification (PR #197)     | 3/10  | `allow_env=False` confirmed working. `allowed_commands` confirmed NOT working. Child-VM propagation untestable in eval environment. Partial credit only.
v4.0.0 regression coverage              | 9/10  | Integer/float model, maps/records, channels, spawn, closures — all preserved. No regressions found in core language.
Documentation accuracy                  | 6/10  | `channel(maxsize=N)` notation wrong. `_last_vm` claim inaccurate. `allowed_commands` claim shipped broken.
AI-authorability                         | 6/10  | New features predictable in principle but 2 CRITICAL bugs in `@exactly_once` mean AI-generated code using it will silently fail. `allowed_commands` also untrustworthy.
Overall patch quality                    | 5/10  | Bit ops, compound assignment, multiline: excellent. Annotations and sandbox: shipped with critical defects. The net effect is a patch that adds reliable features and unreliable ones in the same release.

---

## Composite score

**Weighted average: 6.1 / 10**

Weights applied: security-critical dimensions (sandbox, annotations) ×1.5;
regression coverage ×1.2; all others ×1.0.

**Compared to v4.0.0 baseline:** v4.0.0 scored 7.2 composite in its eval.
v4.0.1 is lower primarily because two of the headline advertised features
(`@exactly_once`, `allowed_commands`) shipped broken.

---

## Summary verdict

The patch is **half-shipped**. The mechanical additions (bit ops, compound
assignment, multiline, bounded channels) work correctly and add real value.
The higher-level features (`@exactly_once`, `@retry` fallback, `allowed_commands`
enforcement) are non-functional or critically broken and should not be used in
production code until fixed. The `event_sinks` API is wired but silent.

The three CRITICAL findings (BUG-401-002a, BUG-401-002b, BUG-401-004) are
strong candidates for a v4.0.2 patch. The two MEDIUM annotation bugs
(BUG-401-001, BUG-401-006) should accompany them.
