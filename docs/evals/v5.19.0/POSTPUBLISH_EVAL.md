# v5.19.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.19.0` installed from **PyPI**
**Date:** 2026-11-26
**Index page:** https://pypi.org/project/nodus-lang/5.19.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir "nodus-lang[http]==5.19.0"
```

The venv was upgraded in place, not recreated, because Application Control
blocks unseen native DLLs on this machine. The first attempt, right after the
upload, found no matching distribution: the usual index lag. The second
attempt, 30 s later, installed it.

## Checks

These ran from `%TEMP%`, outside the repo, with neither `PYTHONPATH` nor
`NODUS_COMPILE_FUNCTIONS` set unless a row says so. What is under test is the
default a new user gets.

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus` |
| 2 | the CLI reports 5.19.0 | `Nodus 5.19.0` |
| 3 | a program runs | `fn main() { print(6i * 7i) }` → `42` |
| 4 | the README's claim: a 300,000-iteration loop under `nodus run`, whole process, best of 5, alternating | **default 0.71 s**; `--no-compile` 1.94 s; `NODUS_COMPILE_FUNCTIONS=0` 1.87 s. The output (`899997`, exit 0) is identical all three ways |
| 5 | `nodus run --compile --no-compile` | exit 2: "Error: --compile and --no-compile contradict each other; give one." |
| 6 | `nodus run --help` | lists `--no-compile` |
| 7 | `NodusRuntime()` with no argument, against `compile_functions=False` | the same output (`4950`) and the same 716 instructions; 1 function compiled against 0 |
| 8 | `NODUS_COMPILE_FUNCTIONS=0`, embedded | 0 compiled by default, and 0 with `compile_functions=True`: the variable wins |
| 9 | #1007: `run_source(..., optimize=False)` | 1 function compiled, the same as with the optimizer |
| 10 | #1004: `max_memory_mb=50` and one 200 MB string | kind `sandbox`, "this run grew the process by 194.9 MB, past its 50 MB limit (222 MB resident)" |
| 11 | the release probes against the PyPI install (`--require-installed`) | **168/168** |

**On row 4: the README says 0.91 s; a new user sees 0.71 s.** The README's figure
came from a run against the source tree on a busier box. The ratio is what
matters, and it holds: about 2.7× faster here against 2.3× in the README. The
README understates the gain, which is the safe direction for a permanent page.

## Verdict

**Pass.** The published artifact installs, reports the right version, runs a
program, and does what the README says 5.19.0 does:
- it compiles by default, with identical results;
- each of the three opt-outs turns compilation off, and the variable overrides
  the code;
- the contradictory flag pair is refused;
- `--no-opt` compiles;
- the memory error quotes the limit that was set.

Nothing found is grounds to supersede 5.19.0.
