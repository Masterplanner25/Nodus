# v5.7.1 — Stage 5 post-publish eval

**Date:** 2026-08-29
**Package under test:** `nodus-lang==5.7.1`, installed from PyPI into a fresh venv
**Install:** `pip install --no-cache-dir nodus-lang==5.7.1` — clean, `nodus 5.7.1`
**Verdict:** pass, with one finding filed (#664)

Stage 5 asks a different question from Gate 10. Gate 10 asks *"what can I make
fail?"* against a locally built wheel. Stage 5 asks *"does this work as a new user
would expect?"* against the **published** one.

That distinction is not academic this cycle: **Stage 5 is what caught the defect
that made 5.7.0 superseded.** Gate 10 went 71/71 on 5.7.0 and missed it, because
every probe exercised one feature at a time and the defect only appeared when two
were used together.

---

## The 5.7.0 defect, verified fixed

The exact program 5.7.0 rejected:

```nodus
extern notify(who: string) -> string

workflow saga {
    step reserve { return "res-1" }
    step charge after reserve { return "ch-1" }
    step ship after charge { throw "carrier down" }

    step release compensates reserve { return "released \(reserve)" }
    step refund compensates charge { return "refunded \(charge)" }
}
```

| | 5.7.0 | 5.7.1 |
|---|---|---|
| `nodus check saga.nd` | `Undefined variable: reserve` | **`saga.nd: OK`** |

---

## New-user pass over the release's surfaces

**Compensation runs, in reverse completion order:**

```
failed       = ["ship"]
compensation = [{"step": "refund",  "of": "charge",  "result": "refunded ch-1", "status": "completed"},
                {"step": "release", "of": "reserve", "result": "released res-1", "status": "completed"}]
```

`charge` completed after `reserve`, so `refund` unwinds first — the ordering the
recorded `completion_seq` exists to guarantee, holding in the published package.

**`fmt` no longer corrupts a mapped step** (the #656 defect shipped in 5.6.0):

```nd
step render each page in discover {
    return page * 10i
}
```

survives formatting, `fmt --check` is idempotent afterwards, and the program
produces `{"discover": [1, 2], "render": [10, 20]}` before and after — identical.

**`extern` pre-flight, embedded:**

```
this program declares extern 'notify', which this runtime has not registered.
Register it with `register_function(...)` before running, or remove the declaration.
```

Refused before execution, as designed.

---

## Finding: `nodus run` has no extern pre-flight (#664)

The CLI does not refuse a program declaring an unregistered `extern`; it runs and
fails at the call site with `Undefined function: notify`.

**This is probably correct behaviour** and is recorded rather than treated as a
bug. The CLI has no mechanism to register host functions, so pre-flighting there
would refuse *every* program declaring an `extern` — making the feature unusable
for the person it is for, someone developing a program destined for embedding who
wants to run and check it locally.

What is genuinely wrong is the **message**: the program declares `notify`,
`nodus check` accepts it, and then the runtime calls it undefined with no
reference to the declaration. Filed as #664 with the fix direction — teach the
call-site error which names were declared `extern`, rather than adding a
pre-flight that would break the workflow.

Not a blocker: the failure is still a failure, and no incorrect program succeeds.

---

## Checks

| | |
|---|---|
| install | `pip install --no-cache-dir nodus-lang==5.7.1` — clean |
| `nodus --version` | `Nodus 5.7.1` |
| `nodus check` | clean on compensation, mapped-step and extern programs |
| `nodus run` | compensation unwinds correctly; mapped fan-out correct |
| `nodus fmt` | round-trips `each`; idempotent |
| Gate 10a (pre-upload) | 6/6 dependent suites, 721 tests, exit 0 |
| Gate 10b (pre-upload) | 72/72 against the wheel, from a neutral CWD |

## Known and carried forward

- **5.7.0 is superseded** and was deliberately given **no GitHub release** — one
  superseded artifact beats two published records disagreeing. The rule is in
  `CLAUDE.md`.
- **`nodus-run-action` is stale**; its README pins the version. Stage 6.
- **Throughput unmeasured.** The fix is a scope binding in the analyzer, which is
  not on any execution path — but that is not a measurement, and this says so.
