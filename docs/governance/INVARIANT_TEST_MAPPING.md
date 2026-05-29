<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Invariant Test Mapping

**Version:** 3.0.2
**Status:** Working document — update as tests are added/removed
**Maintainer:** Shawn Knight (Masterplanner25)

This document maps each runtime invariant from `docs/runtime/EXECUTION_INVARIANTS.md`
to the tests that verify it, and notes where coverage is absent or weak.

---

## Coverage legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Covered — test(s) exist that would fail on violation |
| ⚠️ | Partially covered — some paths tested, edge cases missing |
| ❌ | Not covered — no test would catch a violation |
| 🔍 | Needs verification — test may exist, not confirmed |

---

## 1. VM correctness invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| Stack balanced across instructions | I-VM-01 | ⚠️ | VM execution tests (various) | Stack underflow is caught at runtime; no systematic stack-effect test |
| IP advances are explicit | I-VM-02 | 🔍 | Opcode tests | Checked implicitly by execution correctness tests |
| Call frames balanced | I-VM-03 | ✅ | `test_functions.py`, `test_recursion.py` | Deep recursion and nested calls tested |
| Local variables are slot-indexed | I-VM-04 | ✅ | `test_closures.py`, compiler emit tests | LOAD_LOCAL_IDX emitted; confirmed by benchmarks |
| Exception handler stack consistent with frame depth | I-VM-05 | ⚠️ | `test_try_catch.py` | Basic cases tested; deeply nested try-in-function edge cases unclear |
| `finally` always executes | I-VM-06 | ⚠️ | `test_finally.py` | Happy path and basic exception path tested; return-inside-try and exception-inside-finally may have gaps |
| Structured throw values preserved | I-VM-07 | ✅ | `test_try_catch.py` (post-v1.0 fix) | Record/list payload preservation tested |
| Dispatch is O(1) | I-VM-08 | ❌ | No performance regression test | Verified by code inspection and manual benchmark; no automated guard |

---

## 2. Scheduler invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| Round-robin with budget enforcement | I-SCHED-01 | ✅* | `test_scheduler_fairness.py` | *Deselected from coverage run (timing-sensitive) |
| No execution after deadline | I-SCHED-02 | ⚠️ | Embedding tests with `timeout_ms` | Deadline fires correctly; check interval is batched, not exact |
| `max_steps` is hard ceiling | I-SCHED-03 | ✅ | Embedding limit tests | Verified via `NodusRuntime(max_steps=N)` tests |

---

## 3. Module system invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| Each module executed at most once | I-MOD-01 | 🔍 | `test_imports.py` | Module caching is tested; once-only guarantee may not be explicitly asserted |
| Relative imports cannot escape root | I-MOD-02 | ✅ | `tests/test_import_containment.py` | Containment enforced and tested for project mode, single-file mode, REPL |
| Named imports bind live | I-MOD-03 | 🔍 | Import tests | Live binding semantics may not be explicitly tested |

---

## 4. Error handling invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| `run_source()` never propagates Python exceptions | I-ERR-01 | ✅ | Embedding tests | BUG-005 regression test exists |
| Err records have canonical shape | I-ERR-02 | ⚠️ | Various error tests | Shape tested for common cases; field completeness not systematically checked |

---

## 5. Sandbox invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| `allowed_paths` restricts filesystem | I-SAND-01 | ✅* | `test_sandbox.py` | *Requires both CLI and embedded mode coverage; verify both paths are tested |
| `allow_input=False` blocks `input()` | I-SAND-02 | 🔍 | Sandbox tests | Likely tested; confirm explicitly |
| `max_frames` caps call stack | I-SAND-03 | 🔍 | Sandbox/recursion tests | May be tested via stack overflow tests |
| Bytecode cache checksum verified | I-SAND-04 | 🔍 | Cache tests | Checksum mechanism tested; tamper case may not be |

---

## 6. Workflow invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| Workflow state writes are atomic | I-WFLOW-01 | ❌ | No test | Relies on filesystem semantics; atomic write not tested |
| Lowering produces no workflow-specific opcodes | I-WFLOW-02 | ✅ | `test_workflows.py`, `FREEZE_PROPOSAL.md` | Opcode freeze tests indirectly verify this |
| Step execution isolated per coroutine | I-WFLOW-03 | ✅* | `test_task_graph.py` | *`test_worker_death_detection` is timing-sensitive and deselected from coverage |

---

## 7. Coroutine and channel invariants

| Invariant | ID | Coverage | Test file(s) | Notes |
|-----------|-----|----------|-------------|-------|
| Channel operations are FIFO | I-CORO-01 | 🔍 | Coroutine tests | FIFO ordering may be tested implicitly but not explicitly asserted |
| `yield` suspends, not terminates | I-CORO-02 | ✅ | `test_coroutines.py` | Yield/resume semantics tested |

---

## Gap summary

Invariants with no coverage or weak coverage that represent real risk:

| Gap | Invariant | Priority | Notes |
|-----|-----------|----------|-------|
| Stack effect invariant | I-VM-01 | Medium | Add a test that verifies stack depth after each instruction category |
| `finally` edge cases | I-VM-06 | High | return-inside-try, exception-inside-finally, nested finally |
| O(1) dispatch guard | I-VM-08 | Low | Manual verification; hard to auto-test |
| Module once-only guarantee | I-MOD-01 | Medium | Add explicit test that side effects run once |
| Live binding semantics | I-MOD-03 | Low | Edge case; add explicit assertion |
| `allowed_paths` CLI mode | I-SAND-01 | High | Security boundary; must have CLI-mode test |
| `allow_input` test | I-SAND-02 | Medium | Confirm test exists |
| `max_frames` test | I-SAND-03 | Medium | Confirm test exists |
| Bytecode tamper test | I-SAND-04 | Low | Optional; relies on filesystem |
| Atomic workflow write | I-WFLOW-01 | Low | Hard to test; document as untested |
| FIFO channel ordering | I-CORO-01 | Medium | Add explicit ordering assertion |

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — invariant definitions
- `docs/governance/TEST_GAP_BACKLOG.md` — gap tracking and prioritization
- `docs/governance/TEST_STRATEGY.md` — test standards
