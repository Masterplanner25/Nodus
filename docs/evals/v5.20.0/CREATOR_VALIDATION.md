# v5.20.0 — Gate 10 creator validation (pre-publish)

**Artifact:** `nodus_lang-5.20.0-py3-none-any.whl` and `nodus_lang-5.20.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.20.0` → `77c7b87`)

**Date:** 2026-11-27

5.20.0 is a minor with two entries:

- **#976 follow-up (PR #1013): compile-to-Python is on by default for
  `nodus serve`, `nodus test` and the tools layer too.** 5.19.0 turned it on
  for `nodus run` and `NodusRuntime`. All of them now go through
  `pycompile.enabled_for`. `NODUS_COMPILE_FUNCTIONS=0` still turns it off for
  the whole process. An observer keeps it off: `nodus profile`, and
  `nodus test --coverage`.
- **#1015: `nodus test --coverage` counts lines.** It had reported
  `0.0% (0/0 lines)` since 4.0.0, because the collector listened for an event
  that nothing emitted. The VM now calls a line observer from its instrumented
  loop, and child VMs inherit it, so the module under test is counted.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run with nothing else going. **Exit 0 on the first round**, with no timeouts and
no recorded flakes matched.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 46.71s |
| nodus-mcp-server | PASS | 78 passed, 2 warnings in 8.59s |
| nodus-extension | PASS | 126 passed in 19.78s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 15.30s |
| nodus-native-memory-engine | PASS | 76 passed in 1.85s |
| nodus-jupyter | PASS | 32 passed in 1.43s |
| nodus-workflow-ai | PASS | 28 passed in 0.39s |
| nodus-a2a-wire | PASS | 188 passed in 14.22s |

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation`, upgraded in place from 5.19.0
with `--force-reinstall --no-deps`. The probes ran from `%TEMP%`, outside the
repo, with `--require-installed`:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.20.0
```

**173/173 probes passed. Exit code 0.** Five are new this cycle, written before
the tag. CI's `probes` job also ran them against its own wheel on PR #1017.

- **#976, the runner:** `runner.run_source`, which `nodus test`'s siblings and
  the tools layer use, compiles by default. It runs interpreted under
  `NODUS_COMPILE_FUNCTIONS=0`, with the same output.
- **#976, `nodus serve`:** the service's VM has compilation on.
- **#1015:** `nodus test --coverage` on a module and its test file reports only
  the module: 4/6 lines, 66.67%. The called function's lines are covered and
  the uncalled one's are uncovered. The test file and the `std:` modules are
  left out.
- **The README names the 5.20.0 surface.**
- **No document still calls 5.19.0 current.**

## Found while preparing the release

**The doc gate failed one block when run from PowerShell.** The `std:subprocess`
example in `standard-library.md` runs `sp.run(["echo", "hello"])`. PowerShell's
`PATH` has no `echo` executable, so `sp.run` returned its not-found error
record, which has no `stdout`. From Git Bash the same tree passed 303/303. This
is the shell, not the code. It is recorded as `AGENT_EXPERIENCE.md` EXP-013.

**A probe's expectation was wrong, not the feature.** The coverage probe first
expected the uncalled function's `return y` line among the uncovered lines. The
optimizer folds `let y = ...; return y`, so that line has no instruction of its
own and is not executable. The probe now asserts on the body line.

**One behaviour change** has a row in the release sequence's "What is not
additive" table: the wider compile default. #1015 was checked and is not a row.
A coverage run is slower now, since it runs the instrumented loop, but nothing
that worked stops working.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` after the bump, from Git Bash: every phase PASS (runtime
  303/303, opcodes 39/39, shapes 0 new, versions 13/13 against 5.20.0)
- `nodus_gate --open-claims --strict` PASS after `tools.refresh_issue_states`
- `nodus_gate --closed-issues --section 5.20.0` → 2/2
- `tests/test_keyword_coverage.py` 15 passed
- `twine check` PASSED on both artifacts
- CI on PR #1017 (merged as `77c7b87`): `compiled`, `probes`, `py310-floor`,
  `pypy`, `security`, `test` all green on both runs
