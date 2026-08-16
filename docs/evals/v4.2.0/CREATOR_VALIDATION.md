# Creator validation — v4.2.0 (Gate 10)

**Date:** 2026-08-15
**Artifact under test:** `dist/nodus_lang-4.2.0-py3-none-any.whl`
**Environment:** clean `.venv-validation`, wheel-installed, `nodus --version` → `Nodus 4.2.0`
**Not dev source.** No `PYTHONPATH`; every program run through the installed `nodus.exe`.

Gate 10 asks "what can I personally make fail?" — adversarial by design, and
distinct from the post-publish independent eval.

## Result

**11 programs, 2 findings, both filed, neither release-blocking.**

Both are pre-existing limitations rather than regressions, and both fail **at
compile time** — no silent wrong answers.

| # | Category | Programs | Result |
|---|---|---|---|
| 1 | Error handling — try/catch/finally, throw-in-finally, re-throw | 1 | **finding — #415** |
| 2 | Closures and upvalue capture | 4 | **finding — #416** |
| 3 | Coroutines and channels | 1 | pass |
| 4 | Operator and type edge cases | 1 | pass |
| 5 | Import system — chain, alias, circular | 2 | pass |
| 6 | Error messages | 3 | pass |
| 7 | Documented quirks (`CLAUDE.md`) | 1 | pass |
| 8 | Workflow and goal execution *(required — release touches orchestration)* | 1 | pass |
| 9 | CLI `--help` safety (#353) | 4 commands | pass |

## Findings

### #415 — `try/finally` without `catch` is a syntax error

```
Syntax error at p01.nd:14:5: Expected 'catch', got 'finally'
```

`parser.py:310` eats `CATCH` unconditionally. The consequence is worth stating:
the only expressible form of try/finally is `catch e { throw e }` + `finally`,
which routes every cleanup-without-handling site through the **catch-re-throws**
path — the exact path that was broken until this release (#361). Through v4.1.1,
the only way to write try/finally ran the one path where `finally` did not run.

**Disposition:** not fixable before publish (grammar change, release-eve). Filed.

### #416 — closures in a top-level loop body cannot capture that body's variables

```nodus
while (n < 3i) { let snap = n
    acc = acc + [fn() { return snap }] }     // Undefined variable: snap
```

The identical loop **inside a function** works, and gives correct per-iteration
binding (`0 1 2`, not `2 2 2`). Measured across seven forms; independent of how
the closure is consumed. `stdlib/async.nd` is unaffected because its loops live
in `fn` bodies.

The error message is the sharp edge: *"Undefined variable: snap"* when `snap` is
declared on the line above, with no hint that moving the loop into a function
fixes it.

**Disposition:** not fixable before publish (scoping/compiler change). Filed.

## Release fixes verified on the wheel

Confirming this release's own claims against the built artifact, not dev source:

| Issue | Check | Result |
|---|---|---|
| #361/#370/#371 | `finally` runs when `catch` re-throws; deferred return not applied by a later unrelated `finally` | pass |
| #49 | stack-overflow trace capped | exactly **20 frames** + `... (9981 more frames)` |
| #350 | `NodusRuntime(max_steps=None, timeout_ms=None)` on runaway recursion | `Call stack overflow`, not a hang |
| EMBED-001 | `NodusRuntime().timeout_ms` | `None` |
| #353/#345 | `logout` / `publish` / `test` / `deps` `--help` | all print usage; **`logout --help` did not delete the token** |
| #342 | error paths | absolute and resolved, across Key/Name/Sandbox/Import errors |
| #357 | `match` / `break` / `continue` | all execute |
| — | workflow: deps, state, checkpoints, dep values as params | `a:r\|v:r`, state `{"total": 11}`, 1 checkpoint, `failed: []` |
| — | goal: execution and result shape | `2`, `goal: ship` |

## Notes for the next release

**Gate 4 goes vacuous the moment the CHANGELOG is cut.** After `[Unreleased]` is
moved to `[X.Y.Z]`, `--closed-issues` scans an empty section and reports
`Found 0 issue reference(s)` — a *pass* that checked nothing. It must be run as
`--closed-issues --section X.Y.Z` at release time. Run that way here: **16
passed, 0 failed, 0 missing.**

A green `--all` after the version cut is not evidence that the regression tests
were checked. This belongs in `RELEASE_PLAYBOOK.md`.

## Gate summary

| Gate | Result |
|---|---|
| 1 — test suite | 2,012 passed, 3 skipped, **0 failed** (incl. `test_scheduler_fairness`, the documented flake) |
| 2 — ruff | clean across `src/ tests/ tools/` |
| 3 — doc gate `--all` | static 135/135 · runtime **236/236 blocks** · contracts 6/6 · opcodes 26/26 |
| 3b — editor grammar | keyword coverage passes; no keyword added, so no VS Code republish |
| 4 — closed-issue regression | **16/16** against `--section 4.2.0` |
| 5 — version sync | `version.py` and `pyproject.toml` both 4.2.0 |
| 6 — CHANGELOG | `[4.2.0] - 2026-08-15` present |
| 7 — README | updated (not required for minor; the README states the published version as fact) |
| 10 — creator validation | **this document** — 11 programs, 2 findings filed, no unfiled bugs |

**Gate 10 passing criteria met:** no unfiled bugs; 11 programs (≥8) executed to
completion or expected failure; no fixes made during this stage, so no
regressions introduced.
