# Test Gap Backlog

**Last reviewed:** 2026-09-01, against 5.9.0
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

### TG-001: `finally` edge cases -- CLOSED (verified 2026-09-01)

**Priority:** High
**Invariant:** I-VM-06 (`finally` always executes)
**Gap:** The basic `try/catch/finally` happy path is tested. Missing:
- `return` inside a `try` block (deferred-return path)
- Exception thrown inside a `finally` block (secondary exception handling)
- Nested `try/finally` with exception propagation through multiple frames

**Closed:** all three named cases are covered in `tests/test_finally.py` (24 tests) --
`test_finally_runs_on_return_from_try` and `test_deferred_return_value_is_preserved`
(return inside try), `test_throw_in_finally_overrides_deferred_return` /
`test_throw_in_finally_after_catch_return_overrides` /
`test_throw_in_finally_is_catchable_by_outer_try` (exception inside finally), and
`test_nested_finally_with_exception` / `test_nested_finally_both_run_on_exception`
(nested propagation). Plus `tests/test_finally_rethrow.py`, `tests/test_try_finally.py`
and `tests/test_finally_after_catch_return.py`.

---

### TG-002: `allowed_paths` in CLI mode -- CLOSED (verified 2026-09-01)

**Priority:** Critical
**Invariant:** I-SAND-01 (`allowed_paths` restricts filesystem builtins)
**Gap:** The security boundary rule (TECH_DEBT.md) requires CLI mode AND embedded mode tests.
It's unclear whether CLI-mode tests exist for `allowed_paths` enforcement. The embedded
mode test (`NodusRuntime(allowed_paths=[...])`) likely exists. The CLI-mode enforcement
(how `allowed_paths` is wired in the CLI runner) may not be tested.

**Closed:** `tests/test_cli_allowed_paths.py` covers the CLI path, including
`test_cli_run_allow_paths_flag`. Embedded mode is covered by
`tests/test_sandbox_filesystem.py` and `tests/test_sandbox_allowlists.py`; traversal by
`tests/test_fs_path_traversal.py` and `tests/test_path_traversal.py`. Note the flag is
`--allow-paths`, not `--allowed-paths`.

**It stayed open as Critical for three months because nothing linked it to the test
that closed it.** The gap was real when filed; the test arrived; the entry did not
move. A Critical item nobody can trust is worse than none -- see the note at the
bottom of this file.

---

### TG-003: Module executed at most once -- CLOSED (verified 2026-09-01)

**Priority:** Medium
**Invariant:** I-MOD-01 (each module executed once per process)
**Gap:** Module caching is tested implicitly by import tests. No test explicitly verifies
that module-level side effects (e.g., `print()` at module top level) execute exactly once
even when the module is imported from multiple files.

**Closed:** `tests/test_module_runtime_objects.py::test_module_executes_once_when_imported_multiple_times`
is exactly this assertion. (`tests/test_imports.py` does not exist and never did.)

---

### TG-004: FIFO ordering in channels -- CLOSED (verified 2026-09-01)

**Priority:** Medium
**Invariant:** I-CORO-01 (channel operations are FIFO)
**Gap:** Channel behavior is tested through coroutine communication tests. No test
explicitly sends N messages in a known order and asserts they are received in that order.

**Closed:** `tests/test_channels.py::test_channel_queue_order` and
`::test_multiple_senders_one_receiver_fifo`.

---

### TG-005: Stack depth balance after instructions -- CLOSED (verified 2026-09-01)

**Priority:** Medium
**Invariant:** I-VM-01 (stack balanced across instructions)
**Gap:** Stack underflow is caught at runtime but there is no systematic test that
exercises stack depth after each instruction category. An incorrectly implemented opcode
that leaks or under-consumes the stack would be caught only when a larger program fails.

**Closed by a better approach than the one proposed.** `tests/test_stack_discipline.py`
(14 tests, #412 phase 3) checks at run time whether an opcode's actual behaviour matches
what the compiler assumed when it sized frames and patched jumps, and
`tests/test_opcode_semantics*.py` specifies each opcode against a hand-built VM state --
required for every dispatched opcode by `nodus_gate --opcodes`.

The proposed static check was tried and **does not work**, which is worth keeping:
attributing each `*_LOCAL_IDX` instruction to the nearest preceding `FRAME_SIZE` credits
a parent's instructions to a nested closure emitted inside it, and reports legal slots as
violations. A compiled function has no recorded end, so there is no sound span.

---

### TG-006: `allow_input=False` in embedded mode -- CLOSED (verified 2026-09-01)

**Priority:** Medium
**Invariant:** I-SAND-02
**Gap:** May be tested; needs confirmation. If not tested, add a test that calls `input()`
in a `NodusRuntime(allow_input=False)` context and asserts a sandbox error.

**Closed:** `tests/test_embedding_input.py`.

---

### TG-007: `max_frames` call stack cap — ✅ CLOSED (2026-08-14)

**Priority:** Medium
**Invariant:** I-SAND-03
**Gap:** It was not tested, and the gap hid a real defect: the embedded default applied
no cap at all (#350). Closed by `tests/test_max_frames_default.py` — 9 tests covering the
embedded default, an explicit override, a per-call override, a large cap allowing deeper
recursion than the default, and the two CLI paths that already behaved correctly.

**Test file:** `tests/test_max_frames_default.py`
**Effort:** Small (as estimated)

---

### TG-008: Bytecode cache checksum rejection -- STILL OPEN (verified 2026-09-01)

**Priority:** Low
**Invariant:** I-SAND-04
**Gap:** `tests/test_bytecode_cache.py` covers invalidation on **source change**,
**cache-format version change** and **nodus-lang version change**, and
`tests/test_bytecode_cache_content_key.py` covers the content key (#704). None of them
writes a cache file with a deliberately corrupt SHA-256 and asserts it is rejected and
recompiled -- which is the tamper case this entry names.

**Test file to extend:** `tests/test_bytecode_cache.py`
**Effort:** Small

---

### TG-009: LSP server correctness -- CLOSED (verified 2026-09-01)

**Priority:** Low (experimental feature)
**Closed:** 21 tests across `tests/test_lsp_server.py` (4), `tests/test_lsp_diagnostics.py`
(4) and `tests/test_lsp_step_bodies.py` (13). The last of those exists because the
diagnostics engine was one of the two walkers that did not enter a step body (#401).

---

### TG-010: DAP server correctness -- CLOSED (verified 2026-09-01)

**Priority:** Low (experimental feature)
**Closed:** `tests/test_dap_server.py` (9 tests). The `evaluate` command remains
unimplemented -- tracked as #106, not as a test gap.

---

### TG-011: `tooling/loader.py` coverage -- OPEN, figure unverified

**Priority:** Medium
**Gap:** This module contains legacy pipeline code that modern tests bypass via
`ModuleLoader`. A dedicated test pass should cover the remaining paths or confirm they
are dead and removable. #598 already removed two of its exports
(`resolve_with_extensions` / `try_resolve_with_extensions`) after nothing outside the
runtime turned out to consume them, which is evidence for the dead-code reading.

**The 48% figure is from 2026-05-29 and has not been re-measured.** Do not quote it;
measure. The coverage gate is **70%** (raised from 60% on 2026-05-31, `--cov-fail-under=70`
in `.github/workflows/ci.yml`) and covers the overall package -- a single module below it
does not block a release.

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

## Why eight of eleven entries were stale

Reviewed 2026-09-01: **eight of the eleven open gaps had been closed**, including the
one Critical (TG-002, a security boundary) and the one High (TG-001). Two of them were
closed by tests written for an entirely different purpose.

Nothing here is anyone's oversight. **The gap and the test that closes it are linked by
nothing** — no marker, no manifest, no gate — so a test that happens to close a gap
closes it silently, and the entry survives. That is the same defect `# closes: #N` was
introduced to fix for issues, and the same one `tools/invariant_coverage.json` fixes for
invariants; this file has neither mechanism.

The practical consequence is worse than the staleness: **a Critical entry that has been
wrong for three months teaches a reader to discount the list**, which is the one thing a
gap backlog cannot survive. If an entry here matters, file it as a GitHub issue — the
tracker is what this project actually keeps current — and leave this file for the
detail an issue body would not carry.

---

## Related documents

- `docs/governance/INVARIANT_TEST_MAPPING.md` — superseded; the mapping is
  `tools/invariant_coverage.json`, checked by `nodus_gate --invariants`
- `docs/governance/TEST_STRATEGY.md` — test standards and organization
- `docs/governance/TECH_DEBT.md` — broader open items
