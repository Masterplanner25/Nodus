# Gate 10 — creator validation, v5.0.2

**Date:** 2026-08-17 · **Verdict: clean for this release. One pre-existing
finding, filed as [#453](https://github.com/Masterplanner25/Nodus/issues/453),
which changes how every previous Gate 10 should be read.**

Run against the wheel built from the tagged tree (`v5.0.2` → `477ffff`), installed
into a clean venv with no dev source on the path:

```
nodus_lang-5.0.2-py3-none-any.whl
$ nodus --version
Nodus 5.0.2
```

5.0.2 fixes two correctness holes — #411 (`@exactly_once`, `@retry` and the
workflow lowering were forgeable) and #449 (the bytecode cache silently withheld
compiler fixes on upgrade). The probes are weighted accordingly.

---

## 1. Standard eval scripts

| Script | 5.0.1 | 5.0.2 |
|---|---|---|
| `quirk_probe.nd` | 45 lines | 45 lines |
| `language_exerciser.nd` | 52 lines | 52 lines |
| `framework_capabilities.nd` | 39 lines | 39 lines |

Identical, in matched conditions, both exit 0.

### Those line counts do not match the ones in v5.0.1's Gate 10, and that is the finding

`docs/evals/v5.0.1/CREATOR_VALIDATION.md` records **90 / 104 / 78** for the same
three scripts. Both readings are real. The difference is *where the script is run
from*:

```
$ nodus run quirk_probe.nd                              # copied outside any project
45 lines
$ nodus run "…/Coding Language/tests/eval/quirk_probe.nd"    # in-repo path
90 lines  — the same 45-line block twice
```

`quirk_probe.nd` calls `main()` exactly once. The 90-line output is a **double
execution**, confirmed by diffing the halves and by `sort -u` returning exactly 45
distinct lines. Filed as #453 (severity: high — doubled side effects are precisely
what `@exactly_once` exists to prevent).

**It is not a 5.0.2 regression**: 5.0.1 and 5.0.2 produce identical output in
matched conditions, 45/52/39 outside a project and 90/104/78 for in-repo paths.

The uncomfortable part is that this has been true for every previous Gate 10. Those
runs compared the wheel against dev source and found them byte-identical, which was
true — and useless for catching this, because **both sides doubled equally**. A
comparison between two things that are wrong in the same way proves only that they
agree. Future evals should run the scripts from a location that is not inside a
Nodus project, as this one now does.

## 2. Adversarial probes

**31 checks across 11 probes. All pass.**

| # | Probe | What it would have caught |
|---|---|---|
| P1 | `@exactly_once` survives shadowing `effect_resolve` | the #411 forgery |
| P2 | a **parameter** cannot forge the envelope | the local-binding vector, which a reserved-names fix would have missed |
| P3 | the workflow lowering survives shadowing `workflow_state()` | the second #411 instance |
| P4 | **positive controls** — dedup still short-circuits, workflow state still flows between steps | a lowering that stopped calling the builtins altogether, which would pass every negative probe |
| P5 | the reserved namespace is rejected in source (`fn` / `let` / param), and ordinary `__nodus_` names still work | over- or under-reserving |
| P6 | **no lowering emits an unbound builtin call** — asserted on the source of both annotation lowerings and the workflow lowering | a *future* lowering reintroducing the bug before anything exploits it |
| P7 | #449 — cache hit at the same version, **miss** at a bumped version, hit again when restored | the cache silently serving old-compiler bytecode |
| P8 | 5.0.1 surfaces intact: 31 gated builtins, `active_vm()`, `kind="sandbox"`, denial names the flag, builtin override refused | regressions in last release's promises |
| P9 | the CLI is still **not** deny-by-default | the deliberate CLI exemption being "tidied" into consistency |
| P10 | the Floor still blocks writes into `.nodus/`, **with a control write that must succeed first** | a probe that passes for the wrong reason (see below) |
| P11 | `nodus <cmd> --help` exits 0 without executing | #353, which recurred four times |

P10 carries its control because at 5.0.1 the same probe was a **false pass**: it
asserted only `ok == False`, which was true because the script never imported
`std:fs`. It would have passed against a runtime with no Floor at all. The control
is now permanent.

## 3. Gates

| Gate | Result |
|---|---|
| `ruff check src/ tests/ tools/` | clean |
| `nodus_gate --static` | PASS — 135/135 symbols |
| `nodus_gate --runtime` | PASS — 239/239 blocks |
| `nodus_gate --contracts` | PASS — 6/6 |
| `nodus_gate --opcodes` | PASS — 26/26, 49 opcodes, `BYTECODE_VERSION` 4 |
| `nodus_gate --closed-issues --section 5.0.2` | PASS — **2/2** (#411, #449) |
| CI on PR #451 | both test jobs pass on a clean runner |

Re-run scoped to `5.0.2` rather than trusting the default, which after the section
cut scans an empty `[Unreleased]` and passes vacuously.

### CI flake, investigated rather than waved through

The first CI run failed `test_task_yield`, which asserts `stderr == ""`. The
content was a `ResourceWarning: unclosed file` — process-wide stderr, so a warning
about objects allocated by unrelated tests fails it whenever the collector runs at
the wrong moment. The **same commit** passed the other run; the test passes locally
3/3 in isolation and 3/3 for its whole module; `runtime/module.py` is unchanged
since #431. Filed as #452, covering both the over-broad assertion and the genuinely
leaked handles. Green on re-run.

## 4. Local suite

Not used as a gate, deliberately. Three full-suite runs were killed partway on this
machine and a targeted run produced failures that did not reproduce in isolation —
see `CLAUDE.md`. Targeted runs stand in: **394 passed** across
workflow/goal/effect/retry/compiler/module/capability/action/step, 19 forgery
cases, 7 cache cases. CI arbitrated the full suite.

## 5. Known issues shipping with this release

- **#453** — double execution for in-project script paths (above). Pre-existing,
  found by this eval, not fixed here.
- **#452** — `test_task_yield`'s stderr assertion, and the unclosed handles behind it.
- **#387** — a directly constructed `VM()` has no limits; every guard lives in a
  wrapper. Structural twin of #411 and unaddressed by it.
- **#380** — bounding the local workflow store's scan cost.
- 19 governance docs still carry the self-contradicting "needs review before repo
  commit and push" marker.

## 6. Not covered

- **Coverage not re-measured.** The 76.82% baseline dates from 2026-08-07 at 1,878
  tests and is now well over 200 tests stale. A floor, not a reading.
- **Windows only.** The wheel is `py3-none-any`, so platform risk is low, but
  nothing here ran on Linux or macOS.
- **No upgrade-in-place test from 4.x.** Every venv was fresh. Note that #449 makes
  the *first* run after any upgrade recompile every cached module, which is the
  intended cost.
