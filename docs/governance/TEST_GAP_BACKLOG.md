<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Test Gap Backlog

**Version:** 3.0.2
**Status:** Working document — triage and update at each release cycle
**Maintainer:** Shawn Knight (Masterplanner25)

This document tracks known gaps in the test suite. Each item notes the invariant
or behavior that is not covered, the risk of the gap, and the path to closing it.

See `docs/governance/INVARIANT_TEST_MAPPING.md` for the full invariant-to-test mapping.

---

## Priority key

| Priority | Meaning |
|----------|---------|
| **Critical** | A security boundary or a correctness guarantee that has no test coverage |
| **High** | A documented invariant with no test; violation would be a noticeable user-facing bug |
| **Medium** | Partial coverage; edge cases uncovered |
| **Low** | Nice-to-have; failure mode is detectable through other means |

---

## Open gaps

### TG-001: `finally` edge cases

**Priority:** High
**Invariant:** I-VM-06 (`finally` always executes)
**Gap:** The basic `try/catch/finally` happy path is tested. Missing:
- `return` inside a `try` block (deferred-return path)
- Exception thrown inside a `finally` block (secondary exception handling)
- Nested `try/finally` with exception propagation through multiple frames

**Test file to add/extend:** `tests/test_finally.py`
**Effort:** Medium

---

### TG-002: `allowed_paths` in CLI mode

**Priority:** Critical
**Invariant:** I-SAND-01 (`allowed_paths` restricts filesystem builtins)
**Gap:** The security boundary rule (TECH_DEBT.md) requires CLI mode AND embedded mode tests.
It's unclear whether CLI-mode tests exist for `allowed_paths` enforcement. The embedded
mode test (`NodusRuntime(allowed_paths=[...])`) likely exists. The CLI-mode enforcement
(how `allowed_paths` is wired in the CLI runner) may not be tested.

**Test file to add:** Add CLI-mode tests to `tests/test_sandbox.py`
**Effort:** Small (confirm the CLI wires `allowed_paths` and test it)

---

### TG-003: Module executed at most once

**Priority:** Medium
**Invariant:** I-MOD-01 (each module executed once per process)
**Gap:** Module caching is tested implicitly by import tests. No test explicitly verifies
that module-level side effects (e.g., `print()` at module top level) execute exactly once
even when the module is imported from multiple files.

**Test file to add/extend:** `tests/test_imports.py`
**Effort:** Small

---

### TG-004: FIFO ordering in channels

**Priority:** Medium
**Invariant:** I-CORO-01 (channel operations are FIFO)
**Gap:** Channel behavior is tested through coroutine communication tests. No test
explicitly sends N messages in a known order and asserts they are received in that order.

**Test file to add/extend:** `tests/test_channels.py` or `tests/test_coroutines.py`
**Effort:** Small

---

### TG-005: Stack depth balance after instructions

**Priority:** Medium
**Invariant:** I-VM-01 (stack balanced across instructions)
**Gap:** Stack underflow is caught at runtime but there is no systematic test that
exercises stack depth after each instruction category. An incorrectly implemented opcode
that leaks or under-consumes the stack would be caught only when a larger program fails.

**Approach:** Add an assertion mode to the VM that checks stack depth after each instruction
in test mode, or add post-execution stack-depth assertions to key test cases.
**Effort:** Large (VM instrumentation) or Medium (selected test assertions)

---

### TG-006: `allow_input=False` in embedded mode

**Priority:** Medium
**Invariant:** I-SAND-02
**Gap:** May be tested; needs confirmation. If not tested, add a test that calls `input()`
in a `NodusRuntime(allow_input=False)` context and asserts a sandbox error.

**Test file to add/extend:** `tests/test_sandbox.py`
**Effort:** Trivial

---

### TG-007: `max_frames` call stack cap

**Priority:** Medium
**Invariant:** I-SAND-03
**Gap:** May be tested. Confirm by running recursive scripts against `NodusRuntime(max_frames=N)`
and asserting the sandbox error fires at the right depth.

**Test file to add/extend:** `tests/test_sandbox.py`
**Effort:** Small

---

### TG-008: Bytecode cache checksum rejection

**Priority:** Low
**Invariant:** I-SAND-04
**Gap:** The cache checksum mechanism is implemented but may not be tested for the tamper case
(write a valid cache file with a corrupt SHA-256 and verify it is rejected and recompiled).

**Test file to add/extend:** `tests/test_bytecode_cache.py`
**Effort:** Small

---

### TG-009: LSP server correctness

**Priority:** Low (experimental feature)
**Gap:** No automated tests for LSP protocol behavior. The LSP server is experimental, but
its completions, hover, and go-to-definition behavior have no automated tests. Manual
testing only.

**Test file to add:** `tests/test_lsp.py`
**Effort:** Large (requires LSP protocol harness)

---

### TG-010: DAP server correctness

**Priority:** Low (experimental feature)
**Gap:** No automated tests for DAP protocol behavior. Breakpoints, stepping, and variable
inspection are manual-test only.

**Test file to add:** `tests/test_dap.py`
**Effort:** Large (requires DAP protocol harness)

---

### TG-011: `tooling/loader.py` coverage (48%)

**Priority:** Medium
**Gap:** `tooling/loader.py` is at 48% coverage (below the 60% gate; the overall package
passes the gate). This module contains legacy pipeline code that modern tests bypass via
`ModuleLoader`. A dedicated test pass should cover the remaining paths or confirm they are
truly dead code paths that can be removed.

**Effort:** Medium

---

## Closed gaps (resolved)

| Gap | Resolved in | Notes |
|-----|------------|-------|
| Import containment escape | v0.9 / Phase 5 | `tests/test_import_containment.py` |
| `_op_throw` structured value | v1.0 | Regression test added |
| BUG-005 `run_source()` exception propagation | v2.1.0 | Regression test via embedding tests |
| BUG-046 `allowed_paths` enforcement | v2.1.1 | Regression test added |
| BUG-V31E-01 `1I` parse error | v3.0.2 | 6 regression tests added |
| BUG-V31E-02 `math.log` arg order | v3.0.2 | Regression test added |

---

## Related documents

- `docs/governance/INVARIANT_TEST_MAPPING.md` — invariant-to-test mapping
- `docs/governance/TEST_STRATEGY.md` — test standards and organization
- `docs/governance/TECH_DEBT.md` — broader open items
