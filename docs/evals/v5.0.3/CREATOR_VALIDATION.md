# Gate 10 — creator validation, v5.0.3

**Date:** 2026-08-17 · **Verdict: clean, no findings.**

Run against the wheel built from the tagged tree (`v5.0.3` → `889d8b1`), installed
into a clean venv with no dev source on the path, from a directory outside any
Nodus project:

```
nodus_lang-5.0.3-py3-none-any.whl
$ nodus --version
Nodus 5.0.3
```

5.0.3 is seven fixes, six of which share one shape: **a guarantee that held on one
path and not its sibling.** The probes are weighted to that.

---

## 1. Standard eval scripts

| Script | 5.0.2 | 5.0.3 |
|---|---|---|
| `quirk_probe.nd` | 45 lines | 45 lines |
| `language_exerciser.nd` | 52 lines | 52 lines |
| `framework_capabilities.nd` | 39 lines | 39 lines |

Identical, all exit 0. These are the corrected single-execution counts established
in the 5.0.2 eval; #453 — fixed in this release — is the reason earlier Gate 10s
read them doubled.

## 2. Adversarial probes

**32 checks across 10 probes. All pass.**

| # | Probe | What it would have caught |
|---|---|---|
| P1 | a cached module runs `main()` once — three consecutive runs | #453, which only appeared from the *second* run onward |
| P2 | bare `VM` caps call depth; `max_steps` stays unbounded; runaway recursion raises | #387, and over-applying it to limits that are host policy |
| P3 | a 4 s handler bounded to **0.34 s**, reported as a failure, abandonment recorded | #424 |
| P4 | two runtimes cannot share memory; `share_process_state=True` still can | #185, and the escape hatch silently not working |
| P5 | a bare VM falls back to the global runner; an owned runner wins | #390, and the fallback breaking embedded use |
| P6 | `check` catches a cycle, acyclic still passes; resume says "not found" | #396 / #425 |
| P7 | 31 gated builtins, `active_vm()`, denial `kind` + flag, override refused, `@exactly_once` not forgeable | regressions in 5.0.1 / 5.0.2 promises |
| P8 | the CLI is **still** not deny-by-default | the deliberate exemption being "tidied" into consistency |
| P9 | the Floor blocks `.nodus/` writes, **with a control write that must succeed** | a probe passing for the wrong reason |
| P10 | `nodus <cmd> --help` exits 0 without executing | #353, which recurred four times |

P9 keeps its control because at 5.0.1 the same probe was a false pass — it
asserted only `ok == False`, which was true because the script never imported
`std:fs`, and would have passed against a runtime with no Floor at all.

## 3. Gates

| Gate | Result |
|---|---|
| Full suite | **2,214 passed, 3 skipped, 0 failures** in 7m47s |
| `ruff check src/ tests/ tools/` | clean |
| `nodus_gate --static` | PASS — 135/135 symbols |
| `nodus_gate --runtime` | PASS — 239/239 blocks |
| `nodus_gate --contracts` | PASS — 6/6 |
| `nodus_gate --opcodes` | PASS — 26/26, 49 opcodes, `BYTECODE_VERSION` 4 |
| `nodus_gate --closed-issues --section 5.0.3` | PASS — **7/7** |
| CI on PR #461 | both test jobs pass on a clean runner |

**The suite was run alone, and that mattered.** Several failures earlier in this
cycle — `WinError 5` on `.nodus/graphs` renames, a different test each run — were
caused by a *second* suite running concurrently against the same repo-root
workflow store. With nothing alongside it the suite is completely clean, including
`test_scheduler_fairness`, which `CLAUDE.md` lists as a known flake and which
failed in isolation earlier the same day. Worth carrying forward: some of what
this project records as machine flakiness is self-inflicted concurrency.

## 4. Known issues shipping with this release

- **#452** — `test_task_yield` asserts stderr is empty, so an unrelated
  `ResourceWarning` can fail it; and there are genuinely unclosed file handles
  behind it.
- **#457** — `ModuleLoader.compile_only` silently returns the first source's
  bytecode when `module_name` is reused. Found during the #387 work, where it made
  the fix briefly look like it had broken legitimate deep recursion.
- **#400** — `nodus graph` executes the file it is asked to inspect. Re-verified
  still reproducing on `main`; **not** the same defect as #453, checked
  specifically because they are adjacent.
- **#401** — `nodus check` does not enter step bodies for symbol resolution.
  Adjacent to #396, which was fixed here; the cycle fix does not touch it.
- **#334** — timing flakes. Its title says "under the coverage run"; that scope is
  too narrow, corrected on the issue after a plain `unittest discover` failure on a
  clean CI runner.

## 5. Not covered

- **Coverage was not re-measured.** The 76.82% baseline dates from 2026-08-07 at
  1,878 tests and is now 336 tests stale. A floor, not a reading.
- **Windows only.** The wheel is `py3-none-any`, so platform risk is low, but
  nothing here ran on Linux or macOS.
- **Upgrade-in-place from 5.0.x** was not exercised; every venv was fresh. Note
  that #449 (5.0.2) means the first run after upgrading recompiles cached modules,
  and that is what makes this release's compiler-level fixes actually apply.
