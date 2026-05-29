<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Test Strategy

**Version:** 3.0.2
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## 1. Purpose

This document describes how the Nodus test suite is organized, what it covers, what it
explicitly excludes, and how different testing levels relate to each other.

---

## 2. Test suite overview

| Metric | Value (2026-05-23 baseline) |
|--------|-----|
| Overall coverage | 77% |
| Coverage gate | ≥60% |
| Total test files | ~40 (approximate) |
| Deselected timing-sensitive tests | 3 |

Run the full suite:
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

Run with coverage (deselecting timing-sensitive tests):
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=60 --ignore=tests/test_scheduler_fairness.py -q
```

---

## 3. Test categories

### 3.1 Unit tests (majority)

Unit tests exercise individual components in isolation:
- Lexer and parser correctness
- Compiler correctness (opcode emission for specific constructs)
- VM instruction semantics
- Builtin function behavior
- Module loader behavior
- Error record shape

### 3.2 Integration tests

Integration tests run complete `.nd` programs through the full pipeline:
- `NodusRuntime.run_source()` end-to-end
- Import resolution with multiple modules
- Workflow execution and checkpointing
- Coroutine and channel interaction

### 3.3 Regression tests

Regression tests are written for every closed GitHub issue. They verify that the specific
behavior described in the issue is fixed and does not regress. They live alongside unit
and integration tests, identified by their relation to an issue number in the test name
or docstring.

**Policy:** Every closed issue referenced in CHANGELOG.md must have at least one
regression test. See `docs/governance/RELEASE_GATES.md §Gate 4`.

### 3.4 Security boundary tests

Security-sensitive behavior (sandbox enforcement, path containment, max_frames) must
have tests in **both** CLI mode and `NodusRuntime` embedded mode. The enforcement
code path can differ between contexts.

Files: `tests/test_sandbox.py`, `tests/test_import_containment.py` (and any future
security-focused test files).

### 3.5 Timing-sensitive tests (deselected from coverage)

Three tests exercise scheduler behavior under real timing constraints. They pass reliably
in the normal pytest run but fail under coverage instrumentation overhead:

- `tests/test_scheduler_fairness.py::test_multiple_tasks_progress`
- `tests/test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`
- `tests/test_task_graph.py::TaskGraphTests::test_worker_death_detection`

These are excluded from the coverage run via `--ignore=tests/test_scheduler_fairness.py`.
They must pass in the non-coverage run.

---

## 4. Coverage baseline

Coverage is 77% overall. Below-60% modules:

| Module | Coverage | Notes |
|--------|----------|-------|
| `src/nodus/__main__.py` | 0% | Trivial entry point; not exercised by test suite |
| `src/nodus/tooling/loader.py` | 48% | Legacy pipeline; needs dedicated test pass |
| `src/nodus/tooling/tiny_vm_lang_functions.py` | 0% | Demo/wildcard helper; not production code |

The 60% gate covers the overall package. Individual module coverage below 60% is tracked
in `docs/governance/TECH_DEBT.md` and does not block release as long as the overall gate
passes.

---

## 5. What the test suite does NOT cover

Being explicit about test gaps is important for deciding what to rely on.

**Functional gaps (known):**
- LSP server behavior (no automated LSP protocol tests)
- DAP server behavior (no automated DAP protocol tests)
- Profiler correctness under concurrent coroutines
- REPL multiline continuation edge cases
- Workflow atomic write integrity (filesystem crash during rename)
- Package manager registry auth edge cases

**Non-functional gaps:**
- Performance regression tests (no benchmark suite; performance is validated informally)
- Memory usage under large programs
- Behavior under resource exhaustion (OOM, disk full)

---

## 6. Eval reports and the test suite

The eval reports (`docs/evals/`) are separate from the automated test suite. Evals
exercise a wide range of language behaviors via structured scenarios scored by a rubric.
They surface issues that unit tests miss (ambiguous semantics, user-visible rough edges,
documentation-code mismatches).

Eval findings that surface bugs get:
1. A GitHub issue with a `bug` label
2. A fix in the appropriate version
3. A regression test in the test suite
4. A CHANGELOG entry

The eval score (7.57/10 on v3.0.2) measures language quality, not just test coverage.

---

## 7. Doc-vs-code gate

The doc-vs-code gate (`tools/nodus_gate/`) is a separate test system that:
- Verifies documented symbols exist in source (`--static`)
- Runs all code blocks in guide docs and checks output (`--runtime`)
- Runs closed-issue regression tests (`--closed-issues`)

This gate is mandatory before every release. See `docs/governance/RELEASE_GATES.md §Gate 3`.

---

## 8. Test-writing standards

### For new features:
- Write tests that exercise the feature with expected inputs
- Write at least one error path test
- If the feature is security-relevant (sandbox, imports, resource limits): write both
  CLI mode and embedded mode tests

### For bug fixes:
- Write a regression test that reproduces the bug before the fix
- Confirm the test fails on the unfixed code, passes after the fix
- Name the test to reference the issue (e.g., `test_bug_046_allowed_paths`)

### For experimental surfaces:
- Test the happy path and basic error paths
- Do not over-invest in edge cases for experimental surfaces — the API may change

---

## 9. Companion library test standards

| Library | Test count | Coverage gate | Notes |
|---------|-----------|--------------|-------|
| nodus-mcp | 280 | None specified | All 14 phases tested |
| nodus-a2a | 169 | ≥80% | 93% achieved |

Companion library tests use the same PYTHONPATH approach as the core suite:
```powershell
PYTHONPATH="C:/dev/Coding Language/src" python -m pytest tests/ -q
```

---

## 10. Test gap backlog

Known test gaps that represent missing coverage of important invariants are tracked in
`docs/governance/TEST_GAP_BACKLOG.md`. Test gap items are filed as GitHub issues against
the appropriate milestone.

---

## Related documents

- `docs/governance/RELEASE_GATES.md` — release gate requirements
- `docs/governance/TECH_DEBT.md` — module coverage breakdown and open items
- `docs/governance/TEST_GAP_BACKLOG.md` — specific gap items
- `docs/governance/INVARIANT_TEST_MAPPING.md` — invariants mapped to tests
