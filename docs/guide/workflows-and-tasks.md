# Workflows and Tasks

Workflows let you declare named steps with explicit dependencies and run
them as a graph. Nodus schedules independent steps in parallel, enforces
ordering for dependent steps, and provides persistent state, checkpoints,
and retries. For the full DSL grammar, see
[docs/runtime/WORKFLOWS.md](../runtime/WORKFLOWS.md).

---

## 1. When to use workflows

Reach for a workflow when you have multiple independent steps that benefit
from parallel execution, a pipeline where ordering must be explicit, or
long-running work that needs retries, timeouts, or checkpoints.

Don't reach for a workflow when simple sequential logic is fine — a chain
of function calls is clearer and faster. Workflows compile through an extra
AST rewrite, spin up a task graph scheduler, and persist snapshots to
`.nodus/graphs/`. That overhead pays off when you need the runtime
guarantees; it doesn't pay off for one-off scripts.

---

## 2. A minimal workflow

```nd
// hello_workflow.nd
workflow hello {
    step greet {
        print("hello from the workflow")
    }
}

run_workflow(hello)
```

```
$ nodus run hello_workflow.nd
hello from the workflow
```

`workflow hello { ... }` declares the workflow. `step greet { ... }` declares
one step whose body is a function that runs when scheduled. `run_workflow(hello)`
builds the task graph, executes it, and returns a result dict.

---

## 3. Steps and dependencies

```nd
workflow build {
    step compile { print("compile") }

    step test after compile { print("test") }
    step package after compile { print("package") }

    step deploy after test, package { print("deploy") }
}

run_workflow(build)
```

```
compile
test
package
deploy
```

- `step name { ... }` — no dependencies; eligible immediately
- `step name after dep1 { ... }` — runs after `dep1` completes
- `step name after dep1, dep2 { ... }` — runs after both complete

Nodus computes a topological sort and schedules steps level by level. Steps
in the same level have no dependency on each other and can run in parallel.
`test` and `package` above are in the same level.

To see the execution plan before running:

```nd
let plan = plan_workflow(build)
print(plan["levels"])
// [["compile"], ["test", "package"], ["deploy"]]
```

The plan is exact for a workflow with no guards. Once any step carries a
`when` (§4.2) the levels become a **superset** — every step that *could* run,
not every step that will.

**Unknown dependency name** — caught at compile time:

```
Syntax error at bad.nd:2:5: Unknown workflow dependency: nonexistent
```

**Cyclic dependency** — caught at runtime. `run_workflow()` returns an err
record with `kind = "workflow_error"`. Check with `type(r) == "error"`.
`nodus workflow run` exits 1.

---

## 4. State and data flow

Steps share a mutable state map declared at the workflow level.

```nd
// etl.nd
workflow etl {
    state records = []
    state summary = ""

    step extract {
        records = ["alice", "bob", "carol"]
        print("extracted " + str(len(records)) + " records")
    }

    step transform after extract {
        records = [records[0] + "@example.com", records[1] + "@example.com", records[2] + "@example.com"]
        print("transformed")
    }

    step load after transform {
        let s = workflow_state()
        let i = 0
        while (i < len(s["records"])) {
            print("load: " + s["records"][i])
            i = i + 1
        }
        summary = "loaded " + str(len(s["records"])) + " records"
    }
}

let r = run_workflow(etl)
print(r["state"])
```

```
extracted 3.0 records
transformed
load: alice@example.com
load: bob@example.com
load: carol@example.com
{"records": ["alice@example.com", "bob@example.com", "carol@example.com"], "summary": "loaded 3.0 records"}
```

- `state name = expr` declares an initial value
- In a step body, assigning `records = new_value` writes to state
- `workflow_state()` returns the current state as a plain map
- Final state is in `r["state"]`; step return values are in `r["steps"]`

Steps don't receive prior steps' return values as arguments — use state
variables to pass data between steps.

### 4.0 State policies — `merge` and `durable`

A cell can declare how concurrent writes combine and whether it is checkpointed,
using the same `with { ... }` form steps take:

```nd-expect=output
workflow deployment {
    state attempts = 0i with { merge: "once" }
    state client = nil with { durable: false }

    step connect {
        client = "live-handle"
        attempts = 1i
        return "connected"
    }
}

let r = run_workflow(deployment)
print(r["state"])
```

Output:

```
{"attempts": 1, "client": "live-handle"}
```

**`merge`** — what happens when two steps that the graph does not order both
write the same cell:

| value | meaning |
|---|---|
| *(undeclared)* | last write wins; **warns if an update was lost** |
| `"any"` | last write wins, and the warning is silenced |
| `"once"` | a second concurrent writer is an **error** |
| `"sum"` | concurrent writes **add** |
| `"append"` | concurrent writes **concatenate** |
| `"union"` | concurrent writes concatenate, **dropping duplicates** |

Declaring `"any"` changes no behaviour — it says *I know these branches agree*,
and silencing the warning by stating that is the point.

An undeclared cell warns only when something was actually lost, which is either:

- the two branches wrote **different values** — one was overwritten; or
- a branch **read the cell before writing it** — a read-modify-write, which loses
  an update whatever the values are.

Two branches writing the same constant, neither reading first, lose nothing and
are silent.

> The remaining warning **becomes an error in 6.0.0**. Declare a fold to combine
> the writes, or `merge: "any"` if last-write-wins is what you meant.

The read-before-write case is worth understanding, because it is the one that
looks fine in testing:

```nd-no-run
step a { let seen = counter; sleep(20i); counter = seen + 1i }
step b { let seen = counter; sleep(20i); counter = seen + 1i }
```

Both branches write `1`, so the *values* agree — and that is exactly when an
update was lost. Comparing what was written cannot detect this; only noticing
that each branch read the cell first can.

#### Folding — `sum` and `append`

Without a fold, two branches that read a cell, do something slow, and write it
back lose one of the writes:

```nd-no-run
step a { let seen = counter; sleep(20i); counter = seen + 1i }
step b { let seen = counter; sleep(20i); counter = seen + 1i }
// counter is 1, not 2 — one increment is gone
```

Nothing atomic about the assignment can fix that: the read and the write are
separated by arbitrary code, so the window is opened by the *step*, not by the
statement. A fold closes it by changing what a write is.

```nd-expect=output
workflow tally {
    state counter = 0i with { merge: "sum" }
    state log = [] with { merge: "append" }

    step a { sleep(10i); counter += 1i; log += ["a"]; return "a" }
    step b { sleep(10i); counter += 1i; log += ["b"]; return "b" }
    step done after a, b { return "done" }
}

let r = run_workflow(tally)
print(r["state"]["counter"])
print(len(r["state"]["log"]))
```

Output:

```
2
2
```

**Under a fold policy, `+=` contributes and `=` is refused.**

`counter += 1i` means *contribute one*, folded at the join. It never reads the
cell, which is what removes the window. Both branches contribute, both land.

`counter = 5i` is a **compile-time error** — `nodus check` catches it. A plain
assignment names a *final value*, and two final values cannot be combined:
folding them would double-count. There is no reading of `counter = seen + 1i`
that means "add one", so the form is rejected rather than reinterpreted.

Two consequences worth knowing:

- A contribution is not visible to a plain read of the same cell inside the same
  step — it lands at the join, not at the statement. Read the value you
  contributed from your own local, not from the cell.
- The contribution must match the policy: a number for `sum`, a list for
  `append`. Anything else fails the step with a message naming both.

#### `union` and what counts as the same element

`union` is `append` minus elements already present:

```nd-expect=output
workflow scan {
    state seen = [] with { merge: "union" }

    step a { sleep(10i); seen += ["x", "y"]; return "a" }
    step b { sleep(10i); seen += ["y", "z"]; return "b" }
    step done after a, b { return "done" }
}

let r = run_workflow(scan)
print(len(r["state"]["seen"]))
```

Output:

```
3
```

Sameness is ordinary Nodus `==`, which is **structural** for numbers, strings,
booleans, `nil`, lists and maps, however deeply nested — so `{"id": 1i}`
contributed twice deduplicates to one.

**Records are refused in a union contribution.** Records compare by *identity*,
not by value — `record {x: 1i} == record {x: 1i}` is `false` — so a list of them
would deduplicate nothing and `union` would silently behave as `append`. Rather
than accept a policy it cannot honour, the contribution fails and says so:

```
state 'seen' is declared merge: "union", but records compare by identity, not by
value, so a list containing one can never be deduplicated (#545). Use a map
instead of a record, or `merge: "append"` if duplicates are acceptable.
```

Use a map for the element, or `append` if duplicates are fine. The underlying
record-equality question is
[#545](https://github.com/Masterplanner25/Nodus/issues/545).

Note that the *order* of a folded list depends on which branch finished first,
for `append` and `union` alike. Membership is deterministic; position is not.

**`durable: false`** keeps a cell out of the checkpoint. A cell holding a live
handle — a connection, a channel — has no meaning after a resume, and every cell
was previously persisted, so a value that cannot be serialised failed the run at
the first checkpoint. A non-durable cell is **absent** from restored state rather
than restored as `nil`, so a resumed step re-derives it instead of reading a
value that looks set.

---

## 5. Failure and recovery

**Unhandled step error** — prints to stderr, stops dependent downstream
steps, independent siblings continue, exit code is 0:

```nd
workflow with_failure {
    step good { print("good ran") }

    step will_fail after good {
        let x = 1 / 0
    }

    step downstream after will_fail {
        print("this does not run")
    }
}

let r = run_workflow(with_failure)
print(r["error"])   // "Division by zero"
print(r["failed"])  // ["task_2"]
```

**Catching expected failures** — `try/catch` inside a step body prevents
the error from reaching the scheduler:

```nd
step risky {
    try {
        let x = 1 / 0
    } catch err {
        print("caught: " + err.message)
    }
    print("risky completed")
}
```

Downstream steps run normally when the step completes without re-throwing.

**Retries** — `with { retries: N }` retries the step on any throw. State
mutations from failing attempts persist into the next attempt — design retry
logic with this in mind.

One `run_workflow()` call exhausts the retries. The step below fails twice and
succeeds on the third attempt, all inside the one call:

```nd
workflow with_retries {
    state attempt = 0

    step flaky with { retries: 2, retry_delay_ms: 1 } {
        attempt = attempt + 1
        let s = workflow_state()
        if (s["attempt"] < 3) {
            throw "not ready"
        }
        print("succeeded on attempt " + str(s["attempt"]))
    }
}

let r = run_workflow(with_retries)
print(r["steps"])
print(r["failed"])
```

Output:

```
succeeded on attempt 3.0
{"flaky": nil}
[]
```

When the attempts run out, the run fails: `r["failed"]` names the step and
`r["retry"]["classification"]` is `"exhausted"`, and the last error is also
printed to stderr with a stack trace. A retry that eventually succeeds writes
nothing to stderr — measured, both streams, 2026-08-16.

`goal` behaves identically here — `run_goal()` retries the same way
`run_workflow()` does (#393).

> **One exception: under a running service, retries are deferred, not immediate.**
> `nodus serve` runs a sweeper, and a step retry is handed to it rather than
> taken in-process: `run_workflow()` returns straight away with
> `status = "retry_scheduled"` and a `graph_id`, the step's result is not yet in
> `r["steps"]`, and the sweeper resumes the run when the delay is up (or you call
> `resume_workflow(graph_id)` yourself). Nowhere else — `nodus run`,
> `nodus workflow-run`, `NodusRuntime`, in-language `run_workflow`/`run_goal` —
> does this happen, because nothing there would resume the run. Nor does a bare
> `run_graph([...])` ever defer, in a service or out of one: task graphs built
> that way are not registered in the workflow store, so there would be no record
> for a sweeper to find.
>
> The trap if you do embed in a service: on that deferred return `r["failed"]` is
> `[]` and `r["steps"]` is `{}`, so a caller that only checks `failed` sees a
> *clean* result and never learns the step has not finished. Check `r["status"]`
> too. Before #392 this deferral happened on every entry point and nothing
> resumed it, so the retry was simply dropped.

**Step options** (`with { ... }`): `retries` (max retry count), `retry_delay_ms`
(ms between retries), `timeout_ms` (per-step timeout), `cache` (skip on re-run
if result is cached), `cache_key` (override the cache key), `on` (which
dependency outcomes satisfy this step's join — see below).

### 4.1 `on` — running a step when something failed

`step b after a` means *run b once a has produced a value*. `on` is how a step
says otherwise:

```nd-expect=output
workflow deployment {
    step deploy { throw "rollout rejected" }
    step rollback after deploy with { on: ["completed", "failed"] } {
        print("rolling back")
        return "rolled back"
    }
    step announce after deploy { return "announced" }
}

let r = run_workflow(deployment)
print(r["statuses"])
```

Output:

```
rolling back
{"deploy": "failed", "rollback": "completed", "announce": "upstream_failed"}
```

`rollback` ran because it declared that a failed dependency satisfies it.
`announce` did not, because it did not.

The valid outcomes are **`completed`**, **`failed`** and **`skipped`** — the three
states a dependency can reach while the run is still going. The default is
`["completed"]`, which is what `after` has always meant, so existing workflows are
unchanged. An outcome that is not one of those is refused at the point of
declaration rather than quietly never matching.

`skipped` pairs with [`when`](#42-when--running-a-step-only-under-a-condition):
`step cleanup after ship with { on: ["skipped"] }` runs exactly when `ship`'s guard
was not met.

`upstream_failed`, `omitted`, `cancelled` and `abandoned` are **not** admissible
here, and the distinction is not arbitrary — they are conclusions drawn by walking
the finished graph, so a step waiting on one could never become ready and the option
would be a knob that never fires.

**A step whose condition is not met is `omitted`, not failed.** If `deploy`
above had succeeded and `rollback` declared `on: ["failed"]`, the run would
complete normally with `"rollback": "omitted"`. That is different from
`upstream_failed`, which means something above the step broke — the distinction
is the point of declaring a policy at all.

**A failure stops the run scheduling new work**, but a step that declared it
tolerates failure is exempt — otherwise the option would be unreachable in
exactly the situation it exists for.

A dependency that failed passes `nil` to the step, since it produced no value.
The step is not told *why*; see
[#468](https://github.com/Masterplanner25/Nodus/issues/468).

### 4.2 `when` — running a step only under a condition

`on` is about *how a dependency finished*. `when` is about whether the step
should run at all:

```nd-expect=output
workflow deployment {
    state score = 0
    step review {
        score = 92
        let s = workflow_state()
        if (s["score"] > 80) { checkpoint "approved" }
        return s["score"]
    }
    step ship after review when reached("approved") { return "shipped" }
    step escalate after review when !reached("approved") { return "escalated" }
}

let r = run_workflow(deployment)
print(r["statuses"])
```

Output:

```
{"review": "completed", "ship": "completed", "escalate": "skipped"}
```

The guard goes between `after` and `with`, and takes the **same restricted
predicate grammar** as a goal's `until`: `reached("label")`, composed with
`&&`, `||`, `!` and parentheses. Not a general expression — for the same
reason `until` is not one. Because the labels are literals, a guard naming a
checkpoint its workflow never records is a **compile error**:

```
Syntax error at w.nd:4:35: step 'deploy' waits on checkpoint "aproved", which
'deployment' never records. It records "approved".
```

A step whose guard does not hold is **`skipped`**, and the skip **cascades** —
a step whose dependency was skipped is skipped too, because `after` reads as
*needs*. Say `on: ["completed", "skipped"]` to run anyway.

**`plan_workflow` is now a superset, not an exact prediction.** Levels list
every step that *could* run; guards are evaluated during the run, so which of
them actually will is not known beforehand. The plan is still exact about
structure — nothing appears or disappears — and every step reaches a reported
status, so the result map tells you what happened.

`when` is contextual, so it remains usable as an identifier.

---

## 6. Print, logging, and observability

`print()` inside a workflow step works as in any other function:

```nd
workflow observable {
    step a { print("a: starting") }
    step b after a { print("b: done") }
}
run_workflow(observable)
// a: starting
// b: done
```

**`--trace` with workflows** shows VM bytecode instructions, not step-level
events. For following execution order, `print()` is more useful.

**`--step-limit` applies globally** across the entire workflow run — not
per-step. A multi-step workflow burns through the limit faster than a
single-file script.

**Execution levels** from `plan_workflow()` show which steps run in parallel:

```nd
let plan = plan_workflow(build)
print(plan["levels"])
// [["compile"], ["test", "package"], ["deploy"]]
```

---

## 7. workflow vs goal

`goal` has two forms. The **stopping-condition** form (§7.1) is a genuinely
different construct: it declares *when you are done* and runs a workflow until
that holds. The original form, below, is the same feature as `workflow` with a
different name.

### The original form — a naming convention

`workflow` and `goal NAME { step … }` use identical syntax and have identical
runtime behavior. They are the same feature with two names:

```nd
goal release {
    step tag { print("tagging") }
    step publish after tag { print("publishing") }
}
run_goal(release)
```

`goal` is a naming convention for "desired end states" rather than
pipelines. The distinction is semantic, not technical.

As a convention: reach for `goal` when the emphasis is on the **outcome**
— the steps are implementation details of achieving something (`goal summarize`,
`goal release`, `goal validate`). Reach for `workflow` when the emphasis is on
the **process** — the pipeline itself is the point, and callers care about the
step sequence and dependencies (`workflow research`, `workflow build_and_deploy`,
`workflow ingest_and_index`).

Code that follows this convention reads like the problem it solves: a
`goal release` communicates intent differently from a `workflow release`,
even though the runtime treats them identically.

CLI commands mirror the keyword: `nodus workflow run` / `nodus workflow plan` /
`nodus workflow resume` for workflows; `nodus goal run` / `nodus goal plan` /
`nodus goal resume` for goals. `nodus workflow run` prints step stdout then
a JSON result payload. Using `nodus run` with `run_workflow()` in the script
gives you control over what to print.

### 7.1 `goal … over …` — a stopping condition (Experimental)

A workflow finishes when **every step has run**. A goal finishes when **its
condition holds**, or its budget runs out. It does not contain steps: it names a
workflow, and the checkpoints that workflow records are the waypoints it watches.

```nd
workflow tune {
    state score = 0
    step adjust {
        score = score + 40
        let s = workflow_state()
        print("score is now " + str(s["score"]))
        checkpoint "adjusted"
        if (s["score"] >= 100) { checkpoint "good_enough" }
        return s["score"]
    }
}

goal reach_quality over tune {
    until reached("good_enough")
    budget { max_iterations: 5, deadline_ms: 30000 }
}

let r = run_goal(reach_quality)
print(r["goal_satisfied"])
print(r["iterations"])
print(r["reached"])
```

Output:

```
score is now 40.0
score is now 80.0
score is now 120.0
true
3.0
["adjusted", "good_enough"]
```

Each pass resumes the workflow from the last checkpoint it reached, so `state`
carries forward and successive passes differ — that is what stops the loop
repeating itself. Run it with `nodus run --time-limit`, since several passes
exceed the 200 ms default.

**`until` takes `reached("label")`**, composed with `&&`, `||`, `!` and
parentheses. The label is a string literal, like `checkpoint`'s own.

**The compiler checks your waypoints exist.** Naming a checkpoint the workflow
never records is a compile error, not a goal that quietly never finishes:

```
Syntax error at g.nd:12:11: goal 'ship' waits on checkpoint "verifed", which
'deploy' never records. It records "attempted", "verified".
```

That check is exact rather than best-effort, because neither `checkpoint` nor
`reached` accepts a computed label. It is also the thing a library cannot do for
you — a planner can watch checkpoints as they happen, but it cannot refuse to
start.

**`budget` is mandatory** — `max_iterations` and `deadline_ms` both. An unbounded
goal is a hang.

**Running out of budget is a failure.** The goal returns an err record rather
than a result, so it cannot be mistaken for success:

```nd
workflow probe {
    state tries = 0
    step look {
        tries = tries + 1
        let s = workflow_state()
        checkpoint "looked"
        if (s["tries"] > 99) { checkpoint "found" }
        return s["tries"]
    }
}

goal find_it over probe {
    until reached("found")
    budget { max_iterations: 2, deadline_ms: 5000 }
}

let r = run_goal(find_it)
if (type(r) == "error") {
    print(r.message)
    print(r.payload["category"])
    print(r.payload["reached"])
}
```

Output:

```
goal 'find_it' exhausted its budget after 2 iteration(s) without satisfying its condition
budget_exhausted
["looked"]
```

Note that `probe` still has to *contain* `checkpoint "found"` even though this
run never reaches it — the compile-time check is about what the workflow can
record, not what it did.

**`retry from "label"`** pins where each pass re-enters. The default is the last
checkpoint reached, which keeps progress monotonic; pin it earlier when a failed
pass leaves work that must be redone.

Current limits, all of which would extend the surface and so are not yet
implemented: the workflow must be declared in the same file as the goal; `until`
reads *which* checkpoints were reached, not the state at them, and not their
order; and there is no cost bound. See
[`docs/design/v5/01-goal-stopping-condition.md`](../design/v5/01-goal-stopping-condition.md).

---

## 8. Checkpoints

`checkpoint "label"` inside a step records a named recovery point. The
runtime writes a snapshot to `.nodus/graphs/<graph_id>.checkpoint.json`:

```nd
workflow long_job {
    step phase1 {
        print("phase1 done")
        checkpoint "after-phase1"
    }

    step phase2 after phase1 {
        print("phase2 done")
        checkpoint "after-phase2"
    }
}

let r = run_workflow(long_job)
print(r["checkpoints"])
// [{"label": "after-phase1", "step": "phase1", "task_id": "task_1", ...}, ...]
```

To resume after a partial failure, completed steps are skipped:

```
$ nodus workflow resume <graph_id>
$ nodus workflow resume <graph_id> --checkpoint after-phase1
```

> **Keep module top level side-effect-free in a script you intend to resume.**
> A resume in a *different process* has nothing in memory, so it rebuilds the
> graph by **re-executing your module** to re-bind the workflow and function
> definitions. `run_workflow`, `run_goal` and `print` are suppressed during that
> rebuild — nothing else is. An `fs.write`, `http.post` or `subprocess.run` at
> module top level therefore runs again, **once per resume**, on completed runs
> as well:
>
> ```
> after the run:      X
> after one resume:   XX
> after two resumes:  XXX
> ```
>
> Put effects inside steps, where the graph tracks whether they already ran, or
> behind `@exactly_once`. Definitions, imports and pure setup at top level are
> fine — that is what the re-execution is for.
>
> If the rebuild fails, the resume now tells you why
> (`Could not rebuild run '<id>': …`). Before #399 every rebuild failure was
> reported as `Unknown graph`, including for runs that plainly existed.

---

## 9. Common patterns

**Fan-out / fan-in:** One setup step, parallel processors, one aggregator.
Declare `proc_a`, `proc_b`, `proc_c` all `after input` with no dependency
on each other, then `aggregate after proc_a, proc_b, proc_c`. Use a state
list to collect results; each processor appends to it.

**Step caching:** Add `with { cache: true, cache_key: "v1-label" }` to any
expensive step. On re-runs, the step is skipped and the cached result is
used. The result dict shows which steps were skipped: `r["cache_hits"]`.

**Low-level task graph:** Use `task()` / `run_graph()` for programmatic
graph construction — tasks built in a loop, dynamic dependency wiring:

```nd
fn process() { print("processing") }
fn report()  { print("reporting") }

let t1 = task(process, nil)
let t2 = task(report, t1)
let r  = run_graph([t1, t2])
```

When a step needs multiple dependencies via the options map, use **quoted
string keys** to create a map — bare identifier keys create a record, not
a map, and `task()` expects a map:

```nd
// WRONG: {deps: ...} is a record literal in v3.0, not a map
let t3 = task(my_fn, {deps: [t1, t2]})

// RIGHT: quoted key creates a map
let opts = {"deps": [t1, t2]}
let t3 = task(my_fn, opts)
```

**Conditional routing and iteration via composition:** A single workflow is a
static, acyclic DAG — every declared step runs, and `after` deps cannot form a
cycle (§11). To *route* to one of several multi-step pipelines, or to *loop* a
pipeline, compose: call `run_workflow` (or `run_goal`) on a sub-workflow from
inside a step, chosen by ordinary control flow. Only the selected sub-workflow
runs, and each is a real DAG with its own steps.

```nd
import "std:memory" as memory

workflow billing_pipeline {
    step validate {
        return "ok"
    }
    step refund after validate {
        return "refunded"
    }
}
workflow technical_pipeline {
    step reproduce {
        return "ok"
    }
    step escalate after reproduce {
        return "escalated"
    }
}
workflow router {
    step classify {
        memory.put("kind", "billing")
        return memory.get("kind")
    }
    step dispatch after classify {
        // conditional subgraph selection — only ONE pipeline runs
        let sub = match memory.get("kind") {
            "billing" => run_workflow(billing_pipeline),
            _ => run_workflow(technical_pipeline),
        }
        return sub["steps"]
    }
}
let r = run_workflow(router)
print("ran: \(r["steps"]["dispatch"])")
```

```
ran: {"validate": "ok", "refund": "refunded"}
```

The same shape iterates a sub-workflow with a `while` — each pass is a real
sub-DAG (this is how you express a "loop back to an earlier node" that the acyclic
`after` graph cannot):

```nd
import "std:memory" as memory

workflow revise_pass {
    step revise {
        memory.put("n", memory.get("n") + 1i)
        return "revised"
    }
}
workflow refine {
    step start {
        memory.put("n", 0i)
        return 0i
    }
    step loop after start {
        while (memory.get("n") < 3i) {
            run_workflow(revise_pass)
        }
        return memory.get("n")
    }
}
let r = run_workflow(refine)
print("passes: \(r["steps"]["loop"])")
```

```
passes: 3
```

> **Durability caveat.** Composition is safe for *execution* and each sub-workflow
> checkpoints independently, but a composed flow does **not** resume from a
> checkpoint cleanly today: resuming the outer workflow re-executes its source
> module, which re-runs the nested `run_workflow` and **duplicates its side
> effects** (see #322). Use composition for control flow and per-sub-workflow
> checkpointing; do not rely on whole-flow crash-resume with exactly-once nested
> execution until #322 is fixed.

---

## 10. Embedding workflows

Workflows run normally under `NodusRuntime`. Step print output appears in
`result["stdout"]`:

```python
from nodus import NodusRuntime
rt = NodusRuntime(timeout_ms=None, max_steps=None)
result = rt.run_source('''
workflow hello {
    state name = "world"
    step greet {
        let s = workflow_state()
        print("hello " + s["name"])
    }
}
run_workflow(hello)
''')
print(result["ok"])      # True
print(result["stdout"])  # "hello world\n"
```

There is no separate workflow mode. `run_source()` compiles and runs the
script including the `run_workflow()` call.

---

## 11. Known limits

**A single workflow is a static, acyclic DAG** — every declared step runs (there
is no per-step `when`/guard clause), and `after` deps cannot form a cycle. This is
not a routing/iteration limit: express **conditional routing** and **iteration** by
*composition* — control flow (`match`/`while`) selecting nested `run_workflow`
calls (see §9). Within a single step body you can also branch/loop with plain
`if`/`while`, but that only changes what that one step computes; it cannot skip a
sibling step or re-run an upstream one. For a graph whose *shape* is built at
runtime, drop to `task()` / `run_graph()`.

**Cyclic dependency returns an err record** — a cyclic `after` graph is rejected
when the graph is built (before the scheduler runs); `run_workflow()` returns an
err record with `kind = "workflow_error"`. Check `type(r) == "error"`.
`nodus workflow run` exits 1.

**Retry state is not isolated** — state mutations from a failed attempt
persist into the next retry. See section 5.

---

## 12. See also

- [docs/runtime/WORKFLOWS.md](../runtime/WORKFLOWS.md) — full DSL grammar,
  CLI reference, action expressions, checkpoint recovery
- [docs/runtime/TASK_GRAPHS.md](../runtime/TASK_GRAPHS.md) — `task()` /
  `run_graph()` API and all task options
- [docs/guide/error-handling.md](error-handling.md) — `try/catch` and
  `throw` patterns for use inside step bodies
- [docs/guide/debugging.md](debugging.md) — `--trace`, `--step-limit`,
  print-based debugging applicable to workflow execution
- [docs/guide/embedding-nodus.md](embedding-nodus.md) — `NodusRuntime` API
  and sandbox configuration

---

<!--
TESTED SCRIPTS (originally run against nodus-lang v2.1.1; reviewed for v3.0 —
23 workflow test files in /tmp/workflow-tests/):

01: wf01_minimal.nd         → "hello from step"  BUG-022 confirmed fixed
02: wf02_sequential.nd      → 3 steps in declared order
03: wf03_parallel.nd        → 3 independent steps + join step
04: wf04_state.nd           → workflow_state() returns initial declared values
05: wf04b_state_write.nd    → assignment in step updates state; next step sees it
06: wf05_data_flow.nd       → ETL via state; final state in r["state"]
07: wf06_cycle.nd           → exit 0, no stderr, r["error"]="Dependency cycle or missing tasks"
08: wf07_missing_dep.nd     → Syntax error at compile time: Unknown workflow dependency
09: wf08_diamond.nd         → A→B, A→C, B+C→D; correct order
10: wf09_step_failure.nd    → stderr runtime error; downstream skipped; r["failed"]=["task_2"]; exit 0
11: wf10_try_catch_step.nd  → try/catch inside step; downstream continues
12: wf11_goal.nd            → goal DSL identical to workflow; run_goal() works
13: wf12_cli_workflow_run   → nodus workflow-run: step stdout then JSON result
14: wf13_step_options.nd    → retries:2; each failed attempt logs to stderr; state accumulates
15: wf14_checkpoint.nd      → checkpoint recorded in r["checkpoints"] with label/step/task_id
16: wf15_trace.nd           → --trace shows VM bytecode for lowered workflow, not step-level events
17: wf16b_task_graph.nd     → task()/run_graph() API; bare {deps:...} creates a record in v3.0, use {"deps":...} map
18: embedded (python3)      → NodusRuntime.run_source() captures step stdout in result["stdout"]
19: wf17_fan_out.nd         → fan-out/fan-in via state accumulation
20: wf18_limits.nd          → --step-limit global across all steps; Sandbox error fires
21: wf19_plan.nd / wf20     → workflow-plan CLI and plan_workflow() builtin both work
22: wf21_cache.nd           → cache:true skips on re-run; r["cache_hits"]=["task_N"]
23: wf22_result_shape.nd    → r["steps"] maps step names to return values
24: wf23_retry_state.nd     → state mutations from failed attempts persist into next retry

BEHAVIORAL FINDINGS:
F34: OBSOLETE as of v4.1.0 (#323) — do not follow this entry. It described the
     pre-4.1.0 behavior: exit 0 with r["error"]="Dependency cycle or missing
     tasks". That guidance is now actively WRONG: run_workflow() returns an
     **err record**, so `r["error"]` raises "Indexing is only supported on
     lists, maps, and strings". Re-verified 2026-08-05 on 4.1.1: a cyclic
     `after` graph is rejected when the graph is built, and run_workflow()
     returns an err record with kind="workflow_error" and
     message="Dependency cycle detected: a -> b -> a". Detect it with
     `type(r) == "error"`. Sections 3 and 11 already document this correctly.

F36 (2026-08-05, DOC FIXED — then SUPERSEDED 2026-08-16 by the #392 fix): The
     §5 retry example originally claimed a single run_workflow() call prints
     "succeeded on attempt 3.0". At the time it did not: the first
     run_workflow() returned status="retry_scheduled" with a graph_id and each
     retry needed an explicit resume_workflow(graph_id) — so §5 was rewritten
     as a three-call sequence.

     That deferral turned out to be the #392 bug, not the design: nothing on
     those entry points ever resumed the run, so a caller who did NOT make the
     extra resume calls silently lost the retries and got ok:True. Deferral now
     happens only under a running service, which has a sweeper to resume it.
     §5 is back to a single run_workflow() call, re-measured verbatim.

     The trap the finding names still holds wherever deferral does happen: on a
     deferred return r["failed"] is [] and r["steps"] is {}, so a caller
     checking only `failed` sees a clean result while the step has not run to
     completion. Check r["status"].

F35: State mutations in a failed retry attempt persist into the next attempt.
     Undocumented; can cause surprising counter accumulation in retry loops.
     Documented in section 5 and known limits. Recommend adding to WORKFLOWS.md.

WORKFLOW DSL READINESS VERDICT:
Operationally ready for sequential and parallel step pipelines. BUG-022 print fix,
retry/cache/checkpoint features all work correctly. Two gaps before production use:
(1) cyclic dependency detection is silent, and (2) retry state is not isolated per
attempt. Both are documented above and workable with care.
-->
