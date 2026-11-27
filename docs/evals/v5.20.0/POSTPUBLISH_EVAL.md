# v5.20.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.20.0` installed from **PyPI**
**Date:** 2026-11-27
**Index page:** https://pypi.org/project/nodus-lang/5.20.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir --upgrade "nodus-lang==5.20.0"
```

The venv was upgraded in place, not recreated, because Application Control
blocks unseen native DLLs on this machine. It installed on the first attempt.

## Checks

These ran from `%TEMP%`, outside the repo, with neither `PYTHONPATH` nor
`NODUS_COMPILE_FUNCTIONS` set unless a row says so. The project under test was
a new user's: `calc.nd` (two exported functions, one of them never called), and
`tests/calc_test.nd`, which imports `../calc.nd` and tests `add`.

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus` |
| 2 | `nodus test` with no `nodus.toml` | exit 1: "Invalid import: path '../calc.nd' escapes the project root." See the note below |
| 3 | `nodus test` with a `nodus.toml` at the root | `Tests: 1 total, 1 passed`, exit 0 |
| 4 | #1015: `nodus test --coverage` | `calc.nd 57.1% (4/7 lines)`, uncovered `6, 7, 8`; `coverage.json` and `coverage.html` written; only `calc.nd` in the report |
| 5 | `--coverage-min 50` / `--coverage-min 90` | exit 0 / exit 1, "Coverage 57.1% below minimum 90.0%" |
| 6 | `NODUS_COMPILE_FUNCTIONS=always nodus test --coverage` | the same 57.1% (4/7): coverage keeps functions interpreted |
| 7 | #976: `runner.run_source` | `4950`, compiled; under `NODUS_COMPILE_FUNCTIONS=0` `4950`, not compiled |
| 8 | #976: `RuntimeService().execute` (`nodus serve`'s path) | `4950`, compiled |
| 9 | `nodus profile` still runs | `499500`, then the profiling report |
| 10 | the release probes against the PyPI install (`--require-installed`) | **173/173** |

**Row 2 is not a 5.20.0 change.** With no `nodus.toml`, `nodus test` takes the
test file's directory as the project root, so `tests/x_test.nd` cannot import
`../x.nd`. The message says what is wrong, and adding `nodus.toml` (row 3) is
the documented layout.

## Found: #1018, the last line of a module counts as covered

Row 4's report has 4 lines covered, and one of them is wrong.
`coverage.json` reads executable `[1, 2, 3, 6, 7, 8, 10]` and covered
`{1, 2, 3, 10}`. Line 10 is `return "neg"` in `unused`, which never ran.
`nodus dis` shows why: the program's closing `HALT` carries the location
`calc.nd:10:12`, the last one emitted, and loading the module runs it. The true
figure is 3/7.

Filed as **#1018** (severity low). It overstates coverage by at most one line per
module, and only when that line is in code the tests do not reach.

**Decision: 5.20.0 keeps its GitHub release.** The release sequence's rule for a
defect found between upload and GitHub release is to roll forward only when a
fix will supersede the version. This one does not make 5.20.0 worse than what it
replaces: 5.19.0's coverage reported `0/0` for everything, and nothing that
worked stops working. The release notes name #1018 as a known issue.

The #1015 test and probe did not catch it. Both modules' last lines happened to
be in code the tests ran (`return a + b + t` in one, the uncalled function's
body in the probe, which the optimizer folded into an earlier line). A test for
#1018 should end a module inside an uncalled function.

## Verdict

**Pass, with one known issue (#1018).** The published artifact installs, reports
5.20.0, and does what the release claims: `nodus serve` and the shared runner
compile by default and yield to `NODUS_COMPILE_FUNCTIONS=0`, and
`nodus test --coverage` reports real figures that `--coverage-min` judges.
