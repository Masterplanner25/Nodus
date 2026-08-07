# v4.1.1 — Creator Validation

**Date:** 2026-08-06
**Variant:** Standard (patch release — one runtime fix plus documentation).
**Artifact under test:** `nodus-lang==4.1.1` installed from **PyPI** into a clean
virtualenv (not the dev venv, not the local wheel).
**Scope:** ASYNC-MOD-003 (#339) — closures passed to a module function inside a
list, map, or record.

---

## Process note — this ran AFTER publish, not before

Gate 10 specifies "after the wheel is built, before `twine upload`." That is not
what happened. v4.1.1 was published first, and this validation was run
afterwards, during the documentation sweep that reached `docs/evals/`.

What *was* done before publish: full test suite (1865 passed), all four
doc-gate phases, ruff, version-sync check, tag-to-commit verification, a clean
virtualenv install of the built wheel, and a functional check that the
ASYNC-MOD-003 fix worked from the installed package.

What was skipped: the adversarial program sweep below — the part of Gate 10
that actually tries to break the language rather than confirm the fix.

That skip was not free. The sweep found a shipped correctness bug (#361) that
the pre-publish checks did not, because those checks confirmed the intended fix
rather than probing unrelated surfaces. Recording this so the sequencing failure
is visible rather than implied by a clean-looking report.

---

## Programs run

Eight programs against the PyPI-installed 4.1.1, covering the required
categories.

| # | Category | Result |
|---|----------|--------|
| 01 | Closures and upvalue capture | pass |
| 02 | Coroutines and channels | pass |
| 03 | Error handling — try/catch/finally, rethrow | **FAIL — #361** |
| 04 | Operator and type edge cases | pass |
| 05 | Import system — alias, missing export | pass |
| 06 | Import system — circular detection | pass |
| 07 | Documented quirks from `CLAUDE.md` | pass |
| 08 | Workflow execution | pass |

### 01 — Closures

Map-mutation closure counter returns `2`; nested closure reads the outer `let`
(`10`); assigning an outer `let` from inside a closure leaves the outer value
unchanged (`1`), matching the documented shadowing quirk.

### 02 — Coroutines and channels

Producer/consumer over a channel with `close()` and a `recv() != nil` drain
loop: `got a`, `got b`, `done`. No stranding.

### 03 — Error handling — FAILED

`finally` does not run when `catch` rethrows.

```nd
fn f() {
    try { throw "boom" }
    catch e { print("A caught"); throw e }
    finally { print("B finally") }
}
try { f() } catch e2 { print("C outer") }
```

Prints `A caught` then `C outer`; `B finally` never appears. The other exit
paths (catch without rethrow, `return` from `try`, no exception) all run
`finally` correctly.

Filed as **#361**, severity high. Contradicts `error-handling.md`, which claims
all five exit paths run `finally`.

The same investigation found *why* it shipped:
`tests/test_finally_after_catch_return.py::test_finally_runs_when_inner_error_propagates`
covers this exact path, but its `catch` block prints the **same string** as its
`finally` block and the test asserts only membership — so the catch's output
satisfies the assertion and the test cannot fail. Also captured in #361.

### 04 — Operators and types

`1i / 0i`, `1.0 / 0.0`, and `5i % 0i` all raise `kind = "math"` (correct
post-v4.0.1 behavior, not the IEEE 754 `inf`/`nan` of design doc 09).
`1i + 1` yields `2.0` of type `float`. `0 == false` and `nil == false` are both
`false`, matching design doc 11.

### 05 / 06 — Imports

Alias import resolves (`pong`). A missing export raises
`Key error: Missing module export: nope`. A → B → A is detected at load with
the full cycle path printed. All messages are Nodus-voice; no Python internals
leaked.

### 07 — Documented quirks

Map bracket vs record dot access, `len()` returning an `int`, `spawn` +
`run_loop`, compound assignment `+=`, and `match` all behave exactly as
`CLAUDE.md` documents.

### 08 — Workflow

Two-step workflow with an `after` dependency: `{"one": 1, "two": 2}`, empty
`failed`.

---

## Disposition

| Finding | Disposition |
|---------|-------------|
| #361 — `finally` skipped on rethrow from `catch` | Not fixable before publish (already published). Filed with full repro and severity label. Affects the currently published release. |
| Vacuous regression test for the above | Captured in #361 with a suggested fix (distinct markers per block, assert on ordered sequence rather than membership). |

**Gate 10 passing criteria — "no unfiled bugs":** met. The one failure is filed.

**Honest verdict:** the release itself is sound for its stated scope — the
ASYNC-MOD-003 fix works from the published artifact, and every other surface
probed behaved correctly. But #361 is a pre-existing correctness bug in a core
language feature that this gate would have caught before publish had it been run
in the specified order.
