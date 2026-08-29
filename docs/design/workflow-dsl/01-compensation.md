# Compensation: the spec (#577)

**Status: decided 2026-08-28.** D7 in [`00-cluster-decisions.md`](00-cluster-decisions.md)
settled the *direction* — compensation is declared per step, not as a workflow
exit hook — and answered the four sub-questions #577 asks. It did not describe a
buildable surface. This document does.

D7's ordering prerequisite is discharged: it says "after D5", and D5 (#480,
mapped nodes) shipped in **5.6.0**.

Everything below was measured against `src/` at 5.6.0. Outputs are pasted from
those runs, not from the issues.

## What D7 settled, and what it left open

Settled, and unchanged here:

- compensation is declared on a step, not as a workflow-level exit hook;
- it runs for **completed** work when the run ends failed, in reverse completion
  order;
- a **tolerated** failure (`allow_failure`) does not unwind — the run completes,
  and a completed run has nothing to undo;
- a failing compensation handler is recorded, does not cascade, and does not
  change the run's verdict, which is already `failed`;
- a compensated run is **terminal** and cannot be resumed.

Left open, and decided below: how the handler is declared and kept out of the
forward graph; what it receives; what "reverse completion order" means when the
runtime cannot order two completions; what happens to a mapped node's surviving
instances; where the trigger hooks; and what the result carries.

## Re-verification at 5.6.0

| Claim | Source | Verified |
|---|---|---|
| `run_workflow` returns rather than throws | #577 | `failed=["ship"]`, `steps={"reserve": "res-1", "charge": "ch-1"}`, `ok: True` |
| `steps` holds exactly completed work with its values | #577 | as above — `ship` absent |
| `after DEP` binds `DEP` to its value in the body | D7 précis | `"charged-on-\(reserve)"` → `charged-on-res-1` |
| a mapped node exposes per-instance addressing | #480 | `tasks={"task_1": [...], "task_2[0]": "rendered-p1", "task_2[1]": ..., "task_2[2]": ...}` |
| `#502` (`finally` on an abandoned step) is closed | #577 prerequisite | closed 2026-08-20 |

Three things the issue and D7 do not record, all measured:

**1 — reverse completion order is not derivable from what the runtime records.**
This is the blocker, and it has its own section below.

**2 — a partially-failed mapped node hides its survivors.** One bad item of three:

```
step render each n in discover { if (n == 2i) { throw "bad item" } return n * 10i }

failed=["render"]
statuses={"discover": "completed", "render": "failed"}
tasks={"task_1": [1, 2, 3], "task_2[0]": 10, "task_2[2]": 30}
steps={"discover": [1, 2, 3], "render": [10, 30]}
```

Instances 0 and 2 completed and their effects are real. At node granularity the
node is `failed`; `steps.render` collapses to `[10, 30]` with the failed index
silently dropped, so the only surviving addressing is `tasks`.

**3 — a goal can report `goal_satisfied: true` on a run that ended failed.** A
checkpoint recorded before a throw satisfies `until`:

```
workflow tune { step attempt { checkpoint "good_enough"; throw "nope" } }
goal reach over tune { until reached("good_enough") budget { max_iterations: 3 } }

failed=["attempt"]  iterations=1.0  satisfied=true
```

Filed separately (#642) — it is a goal-semantics question, not a compensation
one, and the trigger below is stated in terms of the run's verdict so it does not
depend on the answer.

### Two suspicions that measurement killed

Recorded because both would have changed the design, and both were wrong.

**Resuming a failed run does not re-execute completed steps.** The checkpoint
list of a resumed run carries two entries for one label with different
timestamps, which reads exactly like re-execution. A state counter says
otherwise — `reserve_calls` stays `1` across two resumes, and the failed step is
not re-attempted either. The resume returns the recorded failure.

**The third failed-run exit is not observably divergent.** `run_task_graph` has
three: two return through `_finalize_failed`, and the resume-rebuild path at
`task_graph.py:2318` does not. `_finalize_failed` is what adds `tolerated`, so
the path looked like it would drop that key. It does not — both a direct failure
and a resumed one carry `tolerated`. The caution survives even though the bug
did not: **do not assume `_finalize_failed` is the chokepoint for "the run ended
failed"**, because it is not the only one.

## The blocker D7 did not see: there is no completion order to reverse

D7's rule is BPMN's: unwind completed work in **reverse completion order**. That
needs a total order over completed steps. The only order the runtime records is
`finished_at`, and it is too coarse to supply one.

A strict causal chain — `a → b → c → d → e`, no concurrency, order unambiguous:

```
timings={"task_1": {"finished_at": 265.00000001396984},
         "task_2": {"finished_at": 265.00000001396984},
         "task_3": {"finished_at": 281.00000001722947},
         "task_4": {"finished_at": 297.0000000204891},
         "task_5": {"finished_at": 297.0000000204891}}
```

Two ties, in a chain that has no ambiguity at all. `runtime_time_ms()` is
`(time.monotonic() - _START) * 1000.0` (`runtime/runtime_stats.py`), and
`time.monotonic()` ticks at ~15.6 ms on this platform — measured deltas between
consecutive distinct readings: `[16.0, 16.0, 15.0, 16.0, 15.0, 16.0]`. Every
step that does no I/O finishes inside one tick.

Sorting by `finished_at` would therefore unwind `charge` before `reserve` — or
after it, depending on nothing — which is the precise failure compensation
exists to prevent: refund before uncharge, release the reservation before
cancelling the order that holds it.

The order exists. It is simply not written down: tasks settle one at a time on
one scheduler, so there is a true sequence, and the wall clock is the wrong
instrument for recording it. This is a finer-grained instance of the timing
lesson already in `CLAUDE.md` — a wall-clock reading is not an ordering.

### D7.1 — order compensation by a recorded completion sequence, not by a clock

**Decision: `TaskNode` gains `completion_seq: int | None`, assigned from a
monotonic per-run counter at the moment a task settles `completed`. Compensation
unwinds in descending `completion_seq`.**

- Exact by construction: the counter increments where completion is already
  serialized, so ties are impossible rather than unlikely.
- Platform-independent. `time.monotonic()` is nanosecond-resolution on Linux, so
  a timestamp rule would be *mostly* right there and wrong here — the worst
  shape a correctness rule can have, and invisible to CI on a Linux runner.
- It survives persistence: `completion_seq` is written with the rest of the task
  record, so a run rebuilt from the store keeps its order.
- `finished_at` stays exactly as it is. It is a timing measurement and remains
  one; this adds an ordering, and does not overload the timing to carry it.

The counter is per-run, not global — two runs in a process must not interleave
sequence numbers, which is the module-scope-state shape (#185/#390).

**Ordering for mapped instances falls out of the same counter**: an instance
settles like any other task, so reverse order across a mapped node's instances
and its siblings is one sort, not two rules.

## The surface

### D7.2 — the handler declares what it undoes

**Decision: a new contextual step-header clause, `compensates NAME`, on the
handler. Not `compensate_with` on the forward step, which is what D7 sketched.**

```
workflow saga {
    step reserve { return "res-1" }
    step charge after reserve { return "ch-1" }
    step ship after charge { throw "carrier down" }

    step release compensates reserve { cancel(reserve) }
    step refund  compensates charge  { refund_card(charge) }
}
```

Why this direction:

- **The declaration is locally readable.** `step refund { ... }` under D7's
  sketch is a step that never runs forward, with nothing at its own declaration
  saying so. Reading it in isolation tells you the opposite of the truth.
- **One reference site.** The pair is named once. `compensate_with` on the
  forward step plus a handler elsewhere is two places that can disagree; both
  spellings accepted would be two ways to say one thing, which is this
  codebase's most common defect shape.
- **The binding rule already exists.** `after DEP` binds `DEP` to its value in
  the body — verified above. `compensates DEP` binds it the same way, so the
  handler reads `charge` to get `"ch-1"` with no new scoping concept.
- **It is the same AST node.** `WorkflowStep` gains a `compensates` field beside
  `each_var` / `each_source` / `when`, and lowering emits it as data on the step
  map the way `each` and `when` already are. No new declaration form — which
  matters, because a new one is exactly what #487 caught four walkers failing to
  learn.

Diverging from the issue's own sketch is the norm for this cluster, not an
exception: four of the eight decisions in D1–D9 do it.

Grammar, with the clause in the position that reads correctly — what it is
before what it depends on:

```
step NAME [compensates DEP] [each VAR in SRC] [after DEP, ...] [when PRED] [with { ... }] { body }
```

`compensates` joins `STEP_MAP_KEYWORDS` and `STEP_GUARD_KEYWORDS` as a
**contextual** keyword in `lexer.py`, so it stays usable as an identifier — and
it is named in a set there rather than matched as a literal in `parser.py`,
which is #480's lesson and what `--consumers` and the VS Code grammar read.

### D7.3 — a compensation handler is excluded from the forward graph, statically

**Decision: a step carrying `compensates` is not a node in the forward graph. It
is reachable only as a handler.** The exclusion is derivable at declaration, so
`plan_workflow` and `nodus graph` can show it before anything runs — the
property the task graph exists for, and the reason D7 preferred per-step
declaration in the first place.

Refused at declaration, each because it could only ever be inert or ambiguous —
the pattern this cluster has been applying throughout:

| Written | Refused because |
|---|---|
| `compensates` naming an unknown step | same rule `after` already enforces (`Unknown workflow dependency`) |
| two handlers compensating one step | no rule would say which runs, or in what order |
| `compensates` on a step that also has `after` | a handler has no place in the forward graph to depend on |
| a forward step declaring `after <handler>` | it would wait on a node that never runs forward |
| `compensates` on a handler that is itself compensated | an undo of an undo has no trigger — the run is already failed |
| `when` on a handler | the trigger is fixed; a guard could only ever suppress it silently |
| `with { on: ..., allow_failure: ..., cache: ..., returns: ... }` | no join to satisfy, no verdict to change, nothing reads the value, and caching an undo is a hazard |

Allowed, and useful: `with { timeout_ms, retries, retry_delay_ms, worker,
worker_timeout_ms }`. Compensation is I/O against a remote that has just proven
it can fail, so the run-shaping options are the ones that earn their place.

**A handler compensating a mapped node** binds one instance at a time, so it
needs no `each` of its own — it inherits the node's fan-out. `each` written on a
handler is refused for that reason.

### D7.4 — what runs, and when

**Trigger: the run's verdict, at the transition to failed — not at a failure
payload's return.** There are three failed-run exits and only one transition; a
rule attached to the payload would fire again on the resume-rebuild path, which
returns a recorded failure for a run that already unwound.

Compensated: every task that reached `completed`, whose step declares a handler,
in descending `completion_seq`.

- **A mapped node's surviving instances are compensated individually.** Measured
  above: instances 0 and 2 completed while the node reports `failed`. Node
  granularity would leave real effects standing, which is the situation
  compensation exists for. The handler binds that instance's value, exactly as
  the mapped step's own body binds the item.
- **A tolerated failure does not unwind** (D7, unchanged). It is a *failure*, not
  completed work, and the run it belongs to completes.
- **A run that ends `waiting` or `retry_scheduled` does not unwind.** Neither is
  a verdict; the run has not ended.
- Ends no step caused — budget exhaustion, cancellation — reach the caller with
  the result map, as D7 records. Unchanged here, and the reason the exit hook was
  not needed.

### D7.5 — the result carries a `compensation` list, in execution order

**Decision: a `compensation` key, a list of records in the order the handlers
ran.** A list, not a map: the ordering *is* the semantics, and a map would
discard it.

```
"compensation": [
    {"step": "refund",  "of": "charge",  "status": "completed", "result": "refund-99"},
    {"step": "release", "of": "reserve", "status": "failed",    "error": "gateway down"}
]
```

For a mapped instance, `of` carries the instance address the run already uses —
`"of": "render[2]"` — so the key needs no new addressing vocabulary.

Handlers do **not** appear in `steps`, `statuses`, or `failed`. Those three
describe the forward run, they are a published surface, and a handler is not a
forward step. This also keeps `TASK_STATUSES` untouched: no eighth status, the
same constraint that shaped D5/D6.

### D7.6 — a compensated run is terminal, and says so

D7 decides terminality. Today a failed run *can* be resumed and returns its
recorded failure without re-running anything (measured above), so "cannot be
resumed" needs a refusal rather than an absence.

**Decision: the run is recorded `compensated`, and a resume of it is refused
naming that** — the shape #482 used for a checkpoint resume of a waiting run,
and #476's lesson that a run is two stores and both halves must agree.

## What was rejected

- **Ordering by `finished_at`.** Measured wrong on this platform, and worse:
  right often enough on Linux to pass CI while being wrong in production.
- **`compensate_with` on the forward step** (D7's own sketch) — see D7.2.
- **Accepting both spellings.** Two ways to say one thing, with a rule needed for
  when they disagree.
- **A workflow-level exit hook.** D7's reasoning stands and is not re-litigated:
  it needs run-status visibility inside a step body, and the case only it covers
  already reaches the caller.
- **Compensating a mapped node at node granularity.** Leaves the survivors'
  effects standing.
- **Handlers in `statuses` / `steps`.** Pollutes a published surface, and invites
  an eighth task status.

## Build order

1. **`completion_seq` on `TaskNode`** (D7.1). Independent of the surface, and
   useful on its own — it is the first exact ordering the run record has.
2. **Grammar and validation** (D7.2, D7.3): the contextual keyword in
   `lexer.py`, the header clause, the refusal table, lowering to step-map data.
3. **The unwind pass and the result key** (D7.4, D7.5), hooked at the transition
   to failed.
4. **Terminality** (D7.6), across both halves of a run's state.

Steps 1 and 2 are separable and testable alone; nothing before step 3 changes
observable behaviour.

Two tests this needs by construction, both in the "assert on the source" style
the recurring-shape section prescribes, because a behaviour-only test passes on
whichever path is already correct:

- the unwind order test must use a **causal chain of trivial steps** — the exact
  shape that ties on the clock — or it cannot fail for the bug D7.1 fixes;
- the trigger test must cover the **resume-rebuild exit**, or a hook attached to
  the wrong place passes on two paths out of three.

## Open, deliberately

- **#642** — a goal reporting `goal_satisfied: true` on a failed run. The trigger
  above reads the run's verdict, so compensation is well-defined either way.
- **Compensation for a run that ends by budget exhaustion or cancellation.** D7
  routes this to the caller. Revisit only if a case appears where the caller
  genuinely cannot do it, which neither #577 nor #475 has produced.
