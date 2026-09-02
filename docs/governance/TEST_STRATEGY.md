# Test Strategy

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## 1. Purpose

This document describes how the Nodus test suite is organized, what it covers, what it
explicitly excludes, and how different testing levels relate to each other.

---

## 2. Test suite overview

| Metric | Value | Measured |
|--------|-------|----------|
| Coverage gate | **≥70%** (`--cov-fail-under=70`, `.github/workflows/ci.yml`) | current |
| Test files | 243 | 2026-09-01 |
| Tests collected | 3,360 | 2026-09-01 |
| Deselected in CI's coverage run | **1** (`test_worker_death_detection`) | current |
| Overall coverage | 76.82% | **2026-08-07, at 1,878 tests** — a floor, not a reading |

**Do not quote the coverage figure as current.** It was measured at roughly half the
present suite and has not been re-measured. The gate was raised from 60% to 70% on
2026-05-31; this table said 60% until 2026-09-01, and said "~40 (approximate)" test
files when there were 243.

Run the full suite:
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

Run with coverage (deselecting timing-sensitive tests):
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=70 --ignore=tests/test_scheduler_fairness.py -q
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
behavior described in the issue is fixed and does not regress.

**Mark each one with a `# closes: #N` comment immediately before the test function.**

```python
# closes: #99
def test_spawn_threads_joined_on_reset(self):
    ...
```

That marker is how `nodus_gate --closed-issues` finds the test. **A test named after an
issue but not marked is invisible to the gate**, which reports the issue as "no test
found" — this section described the convention as "their relation to an issue number in
the test name or docstring" until 2026-09-01, which is not what the scanner reads.

**Policy:** every closed issue referenced in `CHANGELOG.md` must have at least one
marked regression test. The gate reads issue numbers from CHANGELOG **entry lines
only**, so a `#N` inside an entry's prose is a free cross-reference and does not demand
a test.

### 3.4 Security boundary tests

Security-sensitive behavior (sandbox enforcement, path containment, max_frames) must
have tests in **both** CLI mode and `NodusRuntime` embedded mode. The enforcement
code path can differ between contexts.

Files: `tests/test_cli_allowed_paths.py`, `tests/test_sandbox_filesystem.py`,
`tests/test_sandbox_allowlists.py`, `tests/test_sandbox_limits.py`,
`tests/test_subprocess_sandbox.py`, `tests/test_env_sandbox.py`,
`tests/test_fs_path_traversal.py`, `tests/test_path_traversal.py`,
`tests/test_import_containment.py`.

(This line named `tests/test_sandbox.py` until 2026-09-01. That file does not exist and
never did — the same phantom citation `INVARIANT_TEST_MAPPING.md` carried under a ✅.)

### 3.5 Timing-sensitive tests

**CI deselects exactly one test** from the coverage run:
`tests/test_task_graph.py::TaskGraphTests::test_worker_death_detection`.

`tests/test_scheduler_fairness.py` was deselected too until #631 was fixed on
2026-08-28, and the diagnosis is the part worth keeping: **it was never a fairness
failure and never coverage overhead.** The run was killed by the 200 ms wall-clock
`EXECUTION_TIMEOUT_MS` before the ordering assertion was reached — so the test was
asserting the box could run 8,000 iterations in 200 ms. The harness sets its own
generous deadline now, in one helper so a test added later cannot forget it;
`EXECUTION_TIMEOUT_MS` is untouched. **Both** tests in that file were affected, not
the one earlier notes named.

Two rules this left:

- **A test does not have to sleep to be racing something.** Ask what deadline the code
  under test carries *by default*, not only what the test itself waits for. A test that
  shells out to `nodus run` races the 200 ms budget with nothing in the test mentioning
  it (#711), and an `import` is charged to that budget.
- **To reproduce this class of failure, load the machine; do not re-run the test.**
  Neither of these ever failed from repetition. Burn every core but one, then run the
  file — and keep the control inside the same load window, or the comparison measures
  nothing.

If a test sleeps N ms and the code times out at M ms, ensure **M ≥ 5N**. Under parallel
load a 20 ms sleep takes longer than 20 ms of wall clock.

---

## 4. Coverage baseline

Per-module figures below are from the 2026-05-29 sweep and have **not** been
re-measured. Treat them as a starting point for a measurement, not as a reading. The
current per-module breakdown belongs in `docs/governance/TECH_DEBT.md`.

| Module | Coverage | Notes |
|--------|----------|-------|
| `src/nodus/__main__.py` | 0% | Trivial entry point; not exercised by test suite |
| `src/nodus/tooling/loader.py` | 48% | Legacy pipeline; needs dedicated test pass |
| `src/nodus/tooling/tiny_vm_lang_functions.py` | 0% | Demo/wildcard helper; not production code |

The **70%** gate covers the overall package. An individual module below it is tracked in
`docs/governance/TECH_DEBT.md` and does not block a release as long as the overall gate
passes.

---

## 5. What the test suite does NOT cover

Being explicit about test gaps is important for deciding what to rely on.

**Functional gaps (known), re-checked 2026-09-01:**
- Profiler correctness under concurrent coroutines
- REPL multiline continuation edge cases
- Workflow atomic write integrity (filesystem crash during rename) — I-WFLOW-01
- Package manager registry auth edge cases
- Bytecode cache **tamper** case — a valid file with a corrupt SHA-256 (TG-008)

**Two entries came off this list on 2026-09-01**: "LSP server behavior (no automated
LSP protocol tests)" and the same for DAP. There are 21 LSP tests and 9 DAP tests. Both
had been listed as uncovered since 2026-05-29.

**Non-functional gaps:**
- Performance regression tests (no benchmark suite; performance is validated
  informally). One exception: `tests/test_vm_attribute_budget.py` fails if a bare `VM`
  or a `NodusRuntime`-built VM reaches PyPy's 80-instance-attribute cliff (#702). It is
  the only thing in the tree that can see that cliff — do not raise the number, shed an
  attribute.
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

The doc-vs-code gate (`tools/nodus_gate/`) is a separate test system with **nine**
phases — this section listed four until 2026-09-01:

| Phase | Checks | Fails the gate? |
|---|---|---|
| `--static` | documented symbols exist in source | yes |
| `--runtime` | every ` ```nodus ` block in the docs runs | yes |
| `--closed-issues` | CHANGELOG-referenced issues have a `# closes: #N` test | yes |
| `--contracts` | `HandlerContract` infrastructure is wired | yes |
| `--opcodes` | the frozen set, its documents, and a semantic spec per opcode | yes |
| `--versions` | prose still agrees with the version files | yes |
| `--invariants` | the invariant-to-test ledger is honest | yes |
| `--consumers` | non-PyPI consumers a release has left behind | advisory |
| `--shapes` | new instances of the recurring bug shape | advisory |

`--all` runs every phase. Mandatory before every release; see
`docs/governance/RELEASE_GATES.md`.

**Two phases exist because a check stayed quiet when it should have moved**, which is a
worse signal to read than a failure: `--consumers` reported "in step" on a release that
added the `each` keyword, because the fingerprint it hashes is `lexer.ALL_KEYWORDS` and
`each` was matched by a bare literal in `parser.py` (#480). And what `--shapes` looks
for is *places where one question is answered in more than one voice* — its first run
produced #597 and #598.

**Never run the gate alongside the test suite.** `--runtime` executes 270 blocks and
writes to the same repo-root `.nodus/` the suite uses; concurrent runs corrupt each
other and look exactly like a real race.

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

**Do not transcribe companion test counts here** — they went stale every cycle. The
roster and per-repo test commands are in `docs/ecosystem/COMPANION_REPOS.md`; what each
has published is printed by `tools/check_publish_drift.py`.

**The companion suites are a release gate, not a courtesy.**
`tools/check_dependent_suites.py` runs them **before** any PyPI upload (Gate 10 step 0),
because nodus-lang validated against itself cannot see what it breaks in a dependent —
5.0.3 passed 32 green probes and was broken at construction for `nodus-sdk`. Exit **2**
(a suite was missing or timed out) and exit **3** (every failure matched a recorded
flake) are **both** "do not publish"; a recorded flake changes the advice, never the
verdict.

Companion library tests use the same PYTHONPATH approach as the core suite:
```powershell
PYTHONPATH="C:/dev/Coding Language/src" python -m pytest tests/ -q
```

---

## 10. Test gap backlog

Known test gaps are tracked in `docs/governance/TEST_GAP_BACKLOG.md` and filed as GitHub
issues. **Milestones are not used** — they were abandoned 2026-08-26 and all eleven are
closed; release scope is tracked by `CHANGELOG.md`'s `[Unreleased]` section, which the
release process and `--closed-issues` both already read.

Note what a review of that backlog found on 2026-09-01: **eight of eleven open gaps had
already been closed**, because nothing links a gap to the test that closes it. Prefer an
issue for anything you need to stay current.

---

## Related documents

- `docs/governance/RELEASE_GATES.md` — release gate requirements
- `docs/governance/TECH_DEBT.md` — module coverage breakdown and open items
- `docs/governance/TEST_GAP_BACKLOG.md` — specific gap items
- `tools/invariant_coverage.json` — invariants mapped to tests, checked by
  `nodus_gate --invariants` (`INVARIANT_TEST_MAPPING.md` is superseded)
