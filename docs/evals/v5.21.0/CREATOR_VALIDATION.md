# v5.21.0 — Gate 10 creator validation (pre-publish)

**Artifacts:** `nodus_lang-5.21.0-py3-none-any.whl` and `nodus_lang-5.21.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.21.0` → `22ec6c5`)

**Date:** 2026-11-27

5.21.0 is the last 5.x release, by decision (D4 of `docs/governance/V6_0_PLAN.md`,
2026-11-27). It has three entries:

- **#1021 (Changed): a `run_loop()` call from library code warns, and becomes
  an error at 6.0.0.** This is the seventh staged flip. "Library code" is any
  module but the program's entry file, on three routes: a module function
  called outside a coroutine (a child VM), one called inside a coroutine (a
  context swap on the same VM), and an imported module's top level.
  `std:async.parallel` and `series` stopped calling `run_loop()` and keep their
  contract, driven by the new internal builtin `__settle(task)`.
- **#1022 (Fixes): `nodus check --staged` scans the files the entry imports.**
  It said it did, and scanned only the entry.
- **#1018 (Fixes): coverage no longer counts a line that never ran.** The
  closing `HALT`, an implicit `return nil`, and jumps emitted after a nested
  block carried the location of the block's last line.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

It ran with nothing else going and **exited 0 on the first round**: no timeouts,
and no matches against recorded flakes.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 53.80s |
| nodus-mcp-server | PASS | 78 passed, 2 warnings in 11.20s |
| nodus-extension | PASS | 126 passed in 21.09s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 17.14s |
| nodus-native-memory-engine | PASS | 76 passed in 2.70s |
| nodus-jupyter | PASS | 32 passed in 1.29s |
| nodus-workflow-ai | PASS | 28 passed in 0.37s |
| nodus-a2a-wire | PASS | 188 passed in 14.87s |

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation`, upgraded in place with
`--force-reinstall --no-deps`. The probes ran from `%TEMP%`, outside the repo,
with `--require-installed`:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.21.0
```

**180/180 probes passed. Exit code 0.** Seven are new this cycle, written before
the tag. CI's `probes` job also ran them, against its own wheel, on PR #1024.

- **#1021:** a project whose import calls `run_loop()` at its top level and in a
  module function produces exactly two warnings, both naming `lib.nd` and
  `wait(task)`. The entry file's three calls, one of them inside a coroutine,
  produce none.
- **#1021:** `async.parallel` with a failing task in the middle prints the other
  two tasks' output, returns nil and raises no staged-flip warning.
- **#1022:** `nodus check --staged` on that project reports "and 1 file(s) it
  imports" and finds both library calls.
- **#1021:** the packaged register stages seven flips for 6.0.0, with
  `library-run-loop` among them. The existing probe that the register ships
  inside the package also read seven flips from the installed copy.
- **#1018:** compiled with the optimizer, `HALT` has no line, and `sign`'s
  implicit return is on its `fn` line.
- **The README names the 5.21.0 surface.**
- **No document still calls 5.20.0 current.**

## Found while preparing the release

**PR #1023 went red on its first push, on every job that runs the suite.** Two
new VM instance attributes took a `NodusRuntime`-built VM to 81, past the PyPy
map-storage budget that `tests/test_vm_attribute_budget.py` guards (#702). My
local run of 92 files had been chosen by name and skipped that test. The program
marking moved onto the scheduler, which is the better owner anyway: it is the
queue `run_loop()` drains, and a child VM shares its caller's.

**The first contract test for `__settle` could not fail.** It passed with
`__settle` mutated to claim the outcome, because `parallel` settles its tasks in
order, and the failing task had already finished before `parallel` reached it,
so nothing ever parked on a failure. The test now puts a failing task first,
still sleeping when `parallel` parks, and the mutation turns it red.

**`--staged` initially missed imports on a warm cache.** I first read the import
list off `loader._metadata`. A module whose metadata comes from the bytecode
cache returns without visiting its imports, so on the second run that table held
only the entry file. The scan walks each module's recorded import specs instead,
and the #1021 and #1022 tests check both a cold and a warm cache.

**`llms.txt` had given 5.20.0's publish date as 2026-11-26.** It was 2026-11-27.
This was corrected in the release PR.

**One behaviour change** has a row in the release sequence's "What is not
additive" table: `std:async.parallel` and `series` no longer guarantee the
caller's other coroutines have finished when they return. The library warning is
not a row, since nothing stops working until 6.0.0.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` after the bump, from Git Bash: every phase PASS (runtime
  304/304, flips 7 staged with 34 sites, versions 13/13 against 5.21.0).
  `--consumers` is advisory and stale 1/3, as expected after a bump.
- `nodus_gate --open-claims --strict` PASS after `tools.refresh_issue_states`
- `nodus_gate --closed-issues --section 5.21.0` → 3/3
- `tests/test_keyword_coverage.py`, `test_llms_txt_shipped.py` and
  `test_release_probe_flags.py`: 37 passed
- `twine check` PASSED on both artifacts
- CI on PR #1024 (merged as `22ec6c5`): `compiled`, `probes`, `py310-floor`,
  `pypy`, `security` and `test` all green on both runs
