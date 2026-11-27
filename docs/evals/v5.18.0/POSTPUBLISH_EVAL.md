# v5.18.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.18.0` installed from **PyPI**
**Date:** 2026-11-26
**Index page:** https://pypi.org/project/nodus-lang/5.18.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir "nodus-lang[http]==5.18.0"
```

The venv was upgraded in place, not recreated, because Application Control
blocks unseen native DLLs on this machine. The first attempt, right after the
upload, failed with `No matching distribution found`: the usual index lag. The
second attempt, 30 s later, installed it.

## Checks

These ran from `%TEMP%`, outside the repo, with no `PYTHONPATH` unless a row says
so. The 5.17.0 comparisons use a worktree of the `v5.17.0` tag on `PYTHONPATH`,
which reported `Nodus 5.17.0`.

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus` |
| 2 | the CLI reports 5.18.0 | `Nodus 5.18.0` |
| 3 | a program runs | `fn main() { print(6i * 7i) }` → `42` |
| 4 | the README's `join` claim: 300,000 items under `nodus run` | **5.18.0: 0.47 s** (best of 3, whole process, with the default budget); **5.17.0: 20.67 s**, which needed `--time-limit 120 --step-limit 100000000` to finish at all |
| 5 | `repeat` under `nodus run`'s default budget | `s.repeat("ab", 2000000i)` → `4000000`, exit 0. On 5.17.0, two million characters took 536 s (#992) |
| 6 | #975: `nodus dis`, `nodus ast`, `nodus run --dump-bytecode` with stdout redirected to a pipe, on a program holding `→` | all three exit 0 with the arrow in the output. Python reported the pipe as `cp1252`, with neither `PYTHONUTF8` nor `PYTHONIOENCODING` set. **5.17.0's `nodus dis`, run the same way, exits 1 with `UnicodeEncodeError`**, so this is the real failure, not a staged one |
| 7 | the new builtin | `str_join(["a", 1i, true], "-")` → `a-1-true` |
| 8 | the README's `max_memory_mb` claim, embedded | `max_memory_mb=50` and one 200 MB string, then the end of the program: `ok=False`, kind `sandbox`. The control, `max_memory_mb=1024` with 64 MB, runs and prints `64000000` |
| 9 | the release probes against the PyPI install (`--require-installed`) | **160/160** |

**On row 4: the README's figure is the loop, not the process.** The README says
300,000 items "now take 0.07 s". That is the time inside the runtime. A whole
`nodus run` process adds about 0.4 s of startup, as 5.17.0's Stage 5 measured.
Either way, it's about 44× faster end to end.

## Found: the memory-limit message reports an absolute ceiling

```
max_memory_mb=50
Memory limit exceeded: this run grew the process to 221 MB, past its 76 MB ceiling
```

`max_memory_mb` bounds **growth** since the run started. The message reports the
absolute figure: the process's RSS at the start, about 26 MB here, plus the limit.
That is accurate, but a reader who passed 50 sees 76 and has to work out why.

This predates 5.18.0. The wording dates from #160, and #999 only added a place
where the check runs. Filed as #1004.

## Verdict

**Pass.** The published artifact installs, reports the right version, runs a
program, and does what the README says 5.18.0 does:
- `join` and `repeat` are linear, and fit the default budget;
- the three CLI commands survive a cp1252 stdout that crashes 5.17.0;
- the memory ceiling stops a run that ends within one sampling interval.

Nothing found is grounds to supersede 5.18.0.
