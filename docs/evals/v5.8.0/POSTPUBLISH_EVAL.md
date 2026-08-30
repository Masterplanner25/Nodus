# v5.8.0 — Stage 5 post-publish evaluation

**Date:** 2026-08-30
**Package:** `nodus-lang==5.8.0`, installed from PyPI into a fresh venv
**Verdict:** **published package works; one significant defect found, filed as #691**

Stage 5 asks a different question from Gate 10. Gate 10 asks *"what can I make
fail?"* against a local wheel. Stage 5 asks *"does this work as a new user would
expect?"* against the published one — and, since 5.7.0, it asks that by using the
release's features **together** rather than one probe per feature.

That is exactly what it caught this time.

---

## The install

`pip install nodus-lang==5.8.0` failed for several minutes after the upload:

```
ERROR: Could not find a version that satisfies the requirement nodus-lang==5.8.0
       (from versions: ..., 5.7.0, 5.7.1)
```

Index lag, not a failed upload — the documented behaviour, and the reason
CLAUDE.md says to verify a publish by installing it rather than by reading
`info.version`. It resolved on retry:

```
Name: nodus-lang
Version: 5.8.0
Summary: An orchestration DSL and embedded runtime for building agentic hosts
```

Resolution verified from a neutral CWD:

```
resolved: ...\.venv-stage5\Lib\site-packages\nodus\__init__.py
version:  5.8.0
```

## What works

| Surface | Result |
|---|---|
| `nodus --version` | `Nodus 5.8.0` |
| `nodus docs` | resolves `llms.txt` from inside the install |
| `nodus workflow --help` | documents `cancel <graph_id>` and what it does |
| `retry.until` at top level, both arities | carrier delivers, bound honoured |
| `cancel(t)` / `wait(t)` / `run_loop()` | `finally` runs, waiter released with `Task cancelled`, loop returns |

The cancellation half of the release works end-to-end in the published package,
including the cross-feature case (a supervisor waiting on a task another
coroutine cancels).

---

## The finding — #691

**A workflow step body that calls a function in an imported module stops
executing at that call, and the run is reported as successful.**

The Stage 5 script was written the way the README describes the release: a
planning step whose output has to pass a check before it is acted on
(`retry.until`), plus a worker that can be stopped mid-flight. The cancellation
half ran correctly. The workflow half did not:

```
Runtime error at agent_loop.nd:37:31: 'NoneType' object is not subscriptable
  at plan_is_complete (agent_loop.nd:37:31)
  called from until (.../nodus/stdlib/retry.nd:72:23)
failed: ["plan"]
```

Narrowing produced **four different symptoms from one construct**, which is the
signature of stack/dispatch corruption rather than a logic error:

| Symptom | Shape of the imported module |
|---|---|
| **step truncates, `failed: []`, run reports success** | one function |
| `Stack underflow` | two functions, one containing a `while` that calls the callback |
| `Cannot call non-function: nil` | callback is a **named** top-level `fn` |
| spurious `nodus-retry is required for @retry` | via `std:retry` |

The silent case is the severe one:

```
STEP RAN
failed: []
steps: {}
```

`print("got \(v)")` never ran. No error. The run reported **no failures**. The
control — the same file with `let v = 7i` in place of the module call — prints
`got 7`, so the truncation is caused by the module call and not by the step body.

The sharpest single piece of evidence: a module defining **only** `no_loop`
works, a module defining **only** `in_loop` works, and a module defining **both**
fails when `no_loop` is called. The callee is being resolved against the wrong
entry.

### It is not a regression

Both repros were run against clean venvs holding the published wheels, from
outside the repo:

| Repro | v5.7.1 | v5.8.0 |
|---|---|---|
| silent truncation | truncates, `failed: []` | truncates, `failed: []` |
| stack underflow | `Stack underflow` | `Stack underflow` |
| named fn value | `Cannot call non-function: nil` | `Cannot call non-function: nil` |

Identical. 5.8.0 introduced nothing here; it is where the defect starts to matter,
because `retry.until` is a module function whose documented home is a step body.

### Why nothing caught it

`tests/test_retry_until.py` and all eleven new Gate 10b probes run their code
inside `fn main()`. So does the guide example. **The full suite, nine gate phases
and 83 probes were all green on a feature that does not work in the position its
own documentation points at.**

This is the 5.7.0 lesson recurring in a new form. There, a probe per feature
missed the *product* of two features. Here every test exercised the feature in the
one context where the underlying bug is absent. The generalisation worth keeping:
**a construct documented for use inside a step body has to be tested inside a step
body**, because the step-body path and the top-level path are two paths, and a
test on one says nothing about the other — the recurring shape, again.

`examples/plan_then_act.nd` does not use `retry.until` and is unaffected.

---

## Verdict

The published 5.8.0 installs, resolves, and does what it claims **outside**
workflow step bodies. Cancellation works everywhere tested. `retry.until` inside a
step body does not, for a reason that predates this release and affects every
imported-module callback.

Filed as **#691** (`bug`, `severity:high`) with four minimal repros and the
not-a-regression evidence. No action taken against the published artifact: nothing
in 5.8.0 is worse than 5.7.1, so there is nothing here to supersede.
