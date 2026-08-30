# v5.8.0 — Gate 10 creator validation

**Date:** 2026-08-30
**Wheel:** `nodus_lang-5.8.0-py3-none-any.whl`, built from the tagged tree
**Tag:** `v5.8.0` → `a09d046f855d69813db05692117070abdb396bd3` (equal to `HEAD` at build time)
**Verdict:** pass — cleared for upload

5.8.0 is a minor: cancellation (#395, #157), `retry.until` (#466), a worked
plan-then-act example (#465), named steps on runtime-built graphs (#679), and an
`extern` diagnostic (#664).

---

## Gate 10a — dependent suites, before the upload

First run:

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      FAIL      1 failed, 362 passed in 51.63s
nodus-mcp-server               PASS       25 passed in  1.56s
nodus-extension                PASS      126 passed in 40.42s
nodus-sdk                      PASS       99 passed in  7.35s
nodus-native-memory-engine     PASS       76 passed in  0.58s
nodus-jupyter                  PASS       32 passed in  2.41s

nodus-mcp:
    known  tests/test_phase_m.py::test_m2_bearer_wrong_returns_401  (recorded flake)

1 suite(s) red, and every failure matches a recorded flake.   exit 3
```

**Exit 3 is not a pass, and was not treated as one.** The gate classifies the
failure; it does not clear it. `test_phase_m.py` holds two port-binding tests that
CLAUDE.md already records as sensitive to a busy box, so the recorded flake
changed *what to check next* and nothing else.

Three serial re-runs, nothing else running:

| Run | Result |
|---|---|
| full `nodus-mcp` suite | **363 passed** in 45.96s |
| `tests/test_phase_m.py` | **15 passed** in 31.02s |
| `tests/test_phase_m.py` | **15 passed** in 31.43s |

**721 companion tests green.** Cleared.

---

## Gate 10b — adversarial validation against the wheel

### The wrong-tree trap fired again — fourth cycle running

Installing the wheel into `.venv-validation` and importing from the repo root:

```
resolved: C:\dev\Coding Language\nodus.py
version: 5.8.0
```

That is the repo-root shim, which inserts `src/` on `sys.path` and re-execs from
the **source tree**. The version string agrees, `pip list` shows the wheel, and
the probes would have validated the wrong tree — which is exactly how 5.0.3
shipped past 32 green probes, and it has now recurred at 5.5.0, 5.6.0 and here.

**The header is what catches it, every time.** From a neutral CWD with
`--require-installed`:

```
========================================================================
  package   ...\.venv-validation\Lib\site-packages\nodus
  version   5.8.0
  import    ...\.venv-validation\Lib\site-packages\nodus\__init__.py
  repo      C:\dev\Coding Language
========================================================================

83/83 probes passed
```

### The eleven new probes

Written **before** the tag, per the 5.1.0 lesson: they read the release's
*claims*, and after the tag a wrong claim in `README.md` — the permanent PyPI
page — cannot be corrected.

| Probe | What it holds |
|---|---|
| `retry.until` carries the failing result | `seen=[nil, 1, 2]`; stops at the first satisfying value |
| `retry.until` is bounded with no policy | 10,000 attempts, `satisfied=false`; step limit set high enough that a step limit firing could not be mistaken for the bound |
| `cancel(t)` runs `finally`, not `catch` | and the body does not resume past the cancel |
| **cancel and wait compose** | a waiter on a cancelled task is woken and told why |
| `cancelled` is one vocabulary | run status, terminal, and `task_wait` a named blocked reason |
| `nodus workflow cancel` | in the command table and in `nodus workflow --help` |
| #671 top-level assignment | the write reaches the module global |
| #680 builtin import refused | names the collision *and* the namespace form that works |
| #679 named runtime steps | declared names key the result map |
| #465 plan-then-act example | runs clean and the plan reaches the acting step |
| prose sweep | no artifact calls 5.7.1 current |

**The fourth is the one 5.7.1 taught us to write.** #395 and #157 each pass alone
on an implementation where a cancelled task's waiters are simply never woken —
the cancel works, the wait works, and the *pair* hangs. A probe per feature would
have missed it.

---

## Two defects the probe work found

Both were found by running the probes, not by reading them.

### 1. A new probe of mine was unfalsifiable

```python
code, out = cli(["workflow", "--help"])     # WRONG
```

`cli()` takes argv **including the program name**, so `"workflow"` was consumed
as `argv[0]` and the probe read the general usage. It asserted `"cancel" in out`
against a string that never contained the workflow help at all — and would have
passed against a CLI with no such verb. Now `cli(["nodus", "workflow", "--help"])`
asserting on `"cancel <graph_id>"`, cross-checked against `command_help`.

This is the third cycle running in which a probe written this session could not
fail. The discipline that catches them is running every new probe against a tree
where the claim is false, and it is cheaper than it sounds.

### 2. The 5.4.0 stale-prose pattern cried wolf on a *true* sentence

It fired on:

> `| 5.4.0 | `nodus graph` no longer executes the file it inspects (#400) | ... |`

— a correct historical row in CLAUDE.md's "what stopped working" table, added
2026-08-29, **after** 5.7.1's Gate 10b had already run 72/72. A regex steps
straight over the negation, the same blindness that makes GitHub close an issue
on `Filed, not fixed: #N`.

**Its self-check could not have caught this.** The pattern was written out
**twice** — once in the probe, once in `probe_5_4_pattern_selfcheck`, which
exists precisely to hold the probe honest — so the self-check was validating a
*copy*. Tightening either one would have left the other green. That is the
recurring shape of this codebase, sitting inside a detector built for it.

Fixed as one constant read by both, with a negation guard, and both the stale and
the true forms pinned in `must_ignore`. Verified in both directions before the
probe was re-run:

```
OK   catch  | `nodus graph` executes the file it is asked to inspect
OK   catch  | `nodus graph` runs the file it inspects
OK   ignore | | 5.4.0 | `nodus graph` no longer executes the file it inspects (#400)
OK   ignore | `nodus graph` does not execute the file it is asked to inspect
OK   ignore | `nodus graph` never runs the file
```

A guard, not an exemption for that file: the table gains a row every release.

---

## Supporting gates

| Gate | Result |
|---|---|
| `nodus_gate --all` (9 phases) | PASS — static 138/138, runtime 268/268, closed-issues 11/11, contracts 6/6, opcodes 28/28, consumers 2/2, shapes 0 new, versions 15/15, invariants 4/4 |
| `--closed-issues --section 5.8.0` | 11/11 — re-run against the named section, since after the cut the default scans an empty `[Unreleased]` |
| `--versions` **after** the bump | 15/15 — **13 were stale across 8 files** before the fix; before the bump this check passes by definition |
| ruff `src/ tests/` | clean |
| mypy `src/nodus/` | clean |
| `.nd` format check | clean |
| keyword coverage, `llms.txt` shipped | pass |
| `check_downstream_constraints` | all 6 published companions admit 5.8.0; `nodus-workflow-ai` floor `>=5.8.0` now satisfiable |
| Full suite | 3,124 passed, 8 skipped; 1 failure in `test_len_returns_int.py`, named in CLAUDE.md as this box's known class, **20/20 in isolation** and green on CI |

## Verdict

**Cleared for upload.** Gate 10a green after serial re-run; Gate 10b 83/83 against
the installed wheel, resolution verified.

Stage 5 (against the published package) and Stage 6 (downstream sweep) follow.
