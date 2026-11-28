# v5.21.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.21.0` installed from **PyPI**
**Date:** 2026-11-27
**Index page:** https://pypi.org/project/nodus-lang/5.21.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir --upgrade "nodus-lang==5.21.0"
```

The venv was upgraded in place, not recreated, because Application Control
blocks native DLLs it has not seen on this machine. The first attempt found no
5.21.0 on the index, which lags after an upload. The second, 30 s later,
installed it.

## Checks

These ran from `%TEMP%`, outside the repo, with neither `PYTHONPATH` nor
`NODUS_COMPILE_FUNCTIONS` set. The project is a new user's, with a
`nodus.toml`:
- `fetcher.nd`, a library whose `fetch_all` spawns work and calls `run_loop()`;
- `app.nd`, which spawns a background job of its own and then calls it;
- `calc.nd`, the module from #1018's reproduction, with a test for `add` only.

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus`, 5.21.0 |
| 2 | #1021: `nodus run app.nd` | exit 0. One warning, `run_loop() was called from library code at fetcher.nd:7:5`, naming `wait(task)`. The user's background job printed inside `fetch_all`, before its tasks, which is the defect the warning describes |
| 3 | #1021/#1022: `nodus check --staged app.nd` | "checked app.nd and 1 file(s) it imports", `[ 1 found] library-run-loop (#1021)` |
| 4 | the fix the warning names: `fetch_all` waits on each of its tasks | no warning, exit 0. The background job still runs during the wait, which the migration guide says to expect: `wait` stops when its task settles and does not skip other work |
| 5 | `nodus check --staged` after the fix | "nothing found in the 6 flip(s) checked; 1 could not be checked from source" |
| 6 | #1018: `nodus test --coverage`, the issue's reproduction | `calc.nd 42.9% (3/7 lines)`, uncovered `6, 7, 8, 10`. Line 10 (`return "neg"`, never run) is uncovered now, which is the issue's expected result. 5.20.0 reported 4/7 |
| 7 | #1021: `std:async.parallel` with a failing task, then `series` | `a`, the error for `boom`, `c`, `parallel returned nil`, `s1`, `s2`; exit 0; no warning. The contract holds |
| 8 | #1021 embedded: `NodusRuntime.run_file` on a library that calls `run_loop()` | `ok` true, one `StagedFlipWarning` |
| 9 | the release probes against the PyPI install (`--require-installed`) | **180/180** |

## Found

Nothing. Every check gave the documented result on the first run.

Row 7's first line is the caller's unrelated coroutine. It ran before `a`
because it was first in the queue, and `parallel` still runs queued work while
it drives its own tasks. What changed in 5.21.0 is when `parallel` stops, not
what it runs while waiting, and the stdlib guide says so.

## Verdict

**Pass.** The published artifact installs and reports 5.21.0, and it does what
the release claims:
- a library's `run_loop()` warns on every route and names its replacement;
- `nodus check --staged` finds it, and finds it in imports, from source;
- `std:async` keeps its contract;
- coverage stops counting a borrowed line.
