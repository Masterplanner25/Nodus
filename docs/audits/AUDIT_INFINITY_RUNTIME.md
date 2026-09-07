# Infinity Runtime Audit

**Objective:** Determine whether this runtime has self-improving execution capabilities —
not just whether it can run code, but whether each run makes the next run better.

Applies to: any language runtime at a point where the core execution pipeline is stable
and the question shifts from "does it run?" to "does it learn?"

---

## The core question

For each capability below, ask:

> Does this only execute code, or does it help the next execution become better?

A runtime that only executes is a **language runtime**.
A runtime that observes, stores, and recalls is an **Infinity Runtime**.

---

## Check 1 — Entry Point Unification

Find every way the runtime can execute code:

- CLI run
- REPL
- HTTP server execute endpoint
- Workflow / graph / goal execution
- Scheduler / async task dispatch
- Embedded runtime call

Ask: **Do all entry points go through one execution pipeline?**

If there are divergent paths, each one is a separate observability gap. Failures on
path B are invisible if your monitoring only covers path A.

**Pass signal:** A single VM or executor that all paths converge on.
**Fail signal:** Separate execution paths for CLI vs server vs embedded.

---

## Check 2 — Execution Event Coverage

For every run, confirm the runtime emits lifecycle events covering at minimum:

- Execution started
- Plan / graph created (for workflow/goal runs)
- Step started / completed / failed
- Execution completed or failed

**Test method:** Run a failing script with trace/event output enabled. Check whether
you can reconstruct the full causal chain of what happened from the event stream alone.

**Pass signal:** Structured event stream with timestamps, typed events, and enough
context to replay the failure in your head.
**Fail signal:** Only a final error message; no intermediate events.

---

## Check 3 — Execution Memory

After a run completes, ask: **did the runtime store anything useful?**

Minimum viable execution record:
- script / source identifier
- inputs
- outputs
- errors (typed, with location)
- duration
- event stream reference
- tool calls made

Infinity-level:
- what succeeded in this run
- what pattern was established
- what should change next time
- cross-run correlation

**Test method:** Run a script, exit, restart the runtime. Can you retrieve anything
about the previous run without having captured it yourself?

**Pass signal:** A run record persisted to disk or a store, retrievable by run ID.
**Fail signal:** Runtime exits clean — no record exists.

---

## Check 4 — Recall

Before or during a run, can the runtime consult prior execution history?

Example: can it answer any of these before starting?
- Have I run something like this before?
- Did it fail last time?
- What fixed it?
- What context should I carry forward?

**Test method:** Run a script that fails. Fix it. Run again. Ask whether the second
run had any awareness of the first.

**Pass signal:** A `--with-recall` flag, or pre-run history lookup, that can surface
relevant past failures.
**Fail signal:** Each run starts from zero.

---

## Check 5 — Execution Scoring

After a run, does the runtime produce a quality signal?

Minimum viable score:
```json
{
  "run_id": "...",
  "status": "success|failure",
  "duration_ms": 182,
  "warnings": 0,
  "errors": 0,
  "score": 0.97
}
```

**Pass signal:** A numeric or categorical quality assessment stored alongside the
execution record.
**Fail signal:** Only binary pass/fail.

---

## Check 6 — Next-Action Recommendation

After a failure, does the runtime do more than emit an error message?

Possible next actions:
- retry
- debug (with trace)
- suggest a fix
- run tests
- write memory
- generate report
- schedule follow-up

**Pass signal:** The runtime classifies the failure type and maps it to a recommended
action. Example: "Module not found — install/enable X."
**Fail signal:** Raw error text only; the user must decide what to do.

---

## Verdict Rubric

| Checks passed | Classification |
|---------------|----------------|
| 1 only | Language runtime — executes, no observability |
| 1–2 | Execution-event-aware runtime — observable but amnesiac |
| 1–3 | Persistent runtime — runs are recorded; no intelligence |
| 1–4 | Recall-capable runtime — history informs execution |
| 1–5 | Scored runtime — quality is tracked over time |
| All 6 | Infinity Runtime — execution loop is closed |

---

## Audit Table

| Area | Question | Pass Signal |
|------|----------|-------------|
| CLI | Do all commands produce structured run records? | run_id, status, events in persistent store |
| VM | Does execution emit lifecycle events? | Typed event stream, start/complete envelope |
| REPL | Are sessions remembered? | Session history and context available |
| Server | Are API executions tracked? | `/runtime/events` per-run, not last-run-only |
| Workflows | Are graph steps observable? | Step-level events, not just goal-level |
| Errors | Are failures classified? | Typed error kind, not just message string |
| Memory | Are runs stored? | Persistent run log retrievable by run_id |
| Recall | Can past runs influence new runs? | `--with-recall` or equivalent |
| Scoring | Are runs evaluated? | Success/reliability score per run |
| Next Action | Does runtime recommend what to do? | Post-failure recommendation engine |

---

## Stored results

Completed audit results: `docs/evals/vX.Y.Z/AUDIT_INFINITY_RUNTIME.md`
