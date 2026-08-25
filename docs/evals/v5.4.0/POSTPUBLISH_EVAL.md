# Stage 5 — Post-publish evaluation, v5.4.0

**Against the published package**, installed as a new user would install it.
Answers *"does this work as a new user would expect?"* — as distinct from Gate 10,
which asked *"what can I make fail?"* against a local wheel before the upload.

| | |
|---|---|
| Published | <https://pypi.org/project/nodus-lang/5.4.0/> |
| Install | `pip install nodus-lang` into a fresh venv, no cache |
| Resolved | `nodus --version` → `Nodus 5.4.0` |
| Verdict | **Pass.** Every 5.4.0 claim reachable from a clean install; one UX observation, no defects |

---

## The post-upload resolution lag, again

The first `pip install nodus-lang` after the upload resolved **5.3.0**. This is
the behaviour recorded at 5.3.0 and it repeated exactly: PyPI's index takes a few
minutes to serve a new release as *latest*, while the simple index already
carries the artifacts. An explicit `nodus-lang==5.4.0` resolved on the first
attempt.

Not a defect, and worth keeping in the record for the same reason as last time:
**a version check run immediately after upload is not evidence.** Same shape as
the nodus-vscode marketplace lag.

---

## What a new user can do with it

A single script exercising three things this release added, run through the
published CLI:

```
workflow deploy {
    state log = "" with { merge: "append" }
    step build { return "artifact" }
    step notify after build with { allow_failure: true } { throw "pager down" }
    step ship after build { return "shipped" }
}
```

```
steps={"build": "artifact", "ship": "shipped"}
failed=[] tolerated=["notify"]
cleanup pattern
released
```

- **`allow_failure`** — the run completes, `failed` is empty, the tolerated step
  is named separately, and the independent branch shipped.
- **`try { } finally { }`** with no `catch` — parses and runs.
- **`nodus graph show`** on the same file renders the diagram **without executing
  it** (the fan-out is drawn: `build → notify`, `build → ship`).

Backpressure, from the published binary:

```
sent a
got a
got b
sent b
```

`sent b` lands *after* both receives — the producer blocked on the size-1 channel
rather than raising, which is the claim.

`nodus check` enters step bodies:

```
Type error at badcheck.nd:2:36: expected string but got int
```

`nodus workflow cleanup` reports the new default rather than silently doing
nothing: `{"removed": [], "run_records_removed": [], "retention_seconds": 2592000,
"force": false}` — 30 days, where unset previously meant *forever*.

`nodus check --help` states the contract, including the half it deliberately does
not check and why (#489).

---

## Upgrade paths

**In place, over a warm bytecode cache.** A 5.3.0 venv ran a checkpointing
workflow (writing `.nodus/cache/*.nbc`), was upgraded in place to 5.4.0, and ran
the same file again — same correct result. The cache keys on the nodus-lang
version (#449), so no stale bytecode is served across the boundary.

**Cross-version resume — the one this release had to get right.** A workflow
started on **5.3.0** and left `waiting` was resumed on **5.4.0**:

```
persisted by 5.3.0 -> has workflow_topology? False
STEPS={"q": nil, "act": "ok"} STATE={"log": "qa"}
```

The run resumed, delivered its payload and carried its state. This is the
compatibility question 5.4.0's topology validation (#470) created: a run
persisted before this release records no `workflow_topology`, and the validator
falls back to comparing step names from `step_to_task`. The fallback works, and
the limit it carries is stated on the issue — an *edge-only* rewire of a
pre-5.4.0 run is not detectable, because the edges were never recorded.

---

## One observation, not a defect

A **tolerated** failure still prints the step's error and a full stack trace to
stderr, while the run succeeds and exits 0:

```
Thrown error at hello.nd:4:66: pager down
Stack trace: …
```

That is defensible — the throw genuinely happened, and suppressing it would hide
a real event behind a declaration. But a user who declares `allow_failure: true`
for a best-effort notification will see stack-trace noise on every run and may
reasonably read it as a failure. Worth a decision at some point: quieter
reporting for a declared-tolerable failure (the event is already on the event bus
as `task_failure_tolerated`), or leave it loud and document that the trace is
expected. Recorded here rather than filed, since either answer is defensible and
neither is urgent.

---

## Not covered here

- **Stage 6** — downstream ranges, publish drift, non-PyPI consumers, checkout
  cleanliness. Separate document. `nodus-run-action` is known to need
  republishing (its README pins the previous version).
- **Throughput.** Unmeasured this cycle; see the note in `CREATOR_VALIDATION.md`.
