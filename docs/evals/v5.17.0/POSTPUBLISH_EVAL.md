# v5.17.0 — Stage 5 post-publish eval

**Artifact:** `nodus-lang==5.17.0` installed from **PyPI**
**Date:** 2026-11-22
**Index page:** https://pypi.org/project/nodus-lang/5.17.0/

## Install

```
.venv-postpublish/Scripts/python -m pip install --no-cache-dir "nodus-lang[http]==5.17.0"
```

The venv was upgraded in place, not recreated, because Application Control
blocks unseen native DLLs on this machine. The install resolved on the **first
attempt**, with no index lag this cycle.

## Checks

These ran from `%TEMP%`, outside the repo, with no `PYTHONPATH` unless a row says
so.

| # | Check | Result |
|---|---|---|
| 1 | `nodus` resolves to the installed package | `…\.venv-postpublish\Lib\site-packages\nodus` |
| 2 | the CLI reports 5.17.0 | `Nodus 5.17.0` |
| 3 | a program runs | `fn main() { print(6i * 7i) }` → `42` |
| 4 | `nodus run --compile`, the README's switch, on an integer loop of `*`, `/`, `%` and minus | the same output both ways (`-6665766675`); **2.84 s interpreted, 0.77 s compiled**, whole `nodus run` process, best of 3 |
| 5 | `NodusRuntime(compile_functions=True)`, the README's other switch | the same output (`9900`); 0 functions compiled with it off, 1 with it on |
| 6 | the new string builtins | `substring("hello", 1i, 3i)` → `el`, `str_span` → `2`, `str_span_until` → `2` |
| 7 | the README's module-call claim: 2,000 `s.starts_with` calls under `nodus run` | **5.17.0: 0.58 s; 5.16.0: 2.40 s**, best of 3, interleaved. The 5.16.0 side is the tag's source on `PYTHONPATH`, and reported `nodus 5.16.0` |
| 8 | module code within `nodus run`'s default deadline | `s.repeat("a", 2000000i)` → `Execution timed out` |
| 9 | the release probes against the PyPI install (`--require-installed`) | **153/153** |

**On row 7: 4× end to end, about 8× or more for the loop.** The README says the
loop "runs about 8× faster". Measured as a whole `nodus run` process, it's 4.1×,
because each run includes 0.41 s of process startup (the best of 5 for a
one-line program). Without that startup, the 5.16.0 run is about 2.0 s against
0.17 s, so the loop itself meets the README's figure. A user timing `nodus run`
on a short program will see the smaller number.

## Found: the release notes named one of two bounds

**Module code now counts against `nodus run`'s step budget as well as its
deadline.** The release notes, and the "What is not additive" row, gave
`--time-limit N` as the way back for a program that relied on stdlib calls going
uncounted. That isn't enough on its own:

```
s.repeat("a", 800000i)          # about 10.4 million instructions
5.17.0, --time-limit 120                         -> Execution step limit exceeded
5.17.0, --time-limit 120 --step-limit 20000000   -> 800000
5.16.0, --time-limit 120                         -> 800000
```

The default budget is 10,000,000 instructions (`MAX_STEPS`). Before 5.17.0 none
of a module call's instructions counted toward it. The behaviour is intended,
and it's the fix: a guest could otherwise escape the budget through any stdlib
loop. But the notes have to name both flags. The `[5.17.0]` CHANGELOG entry and
the release-sequence row were corrected in the post-release PR, before the
GitHub release, whose body is that section.

This is not grounds to supersede 5.17.0. The code does what was intended; the
notes were incomplete, and the CHANGELOG is not immutable.

## Also found

**`std:strings.repeat` is quadratic in time.** It's not a 5.17.0 change.
`s.repeat("a", 700000i)` runs 9.1M instructions in 14 s, and `2000000i` runs 26M
instructions in **536 s**. Instruction count grows linearly and time
quadratically, which points at building the result by repeated concatenation.
Filed as #992: `repeat` builds its result with `out = out + s` in a loop.

## Verdict

**Pass.** The published artifact installs, reports the right version, runs a
program, and does what the README says 5.17.0 does:
- both compile switches work, and give the same results;
- the new builtins work;
- module calls are several times faster;
- module code is held to the run's bounds.

The one gap was in the release notes, not the code. It was corrected before the
GitHub release was created.
