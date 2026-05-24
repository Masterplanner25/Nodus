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

**Unknown dependency name** — caught at compile time:

```
Syntax error at bad.nd:2:5: Unknown workflow dependency: nonexistent
```

**Cyclic dependency** — caught at runtime, silent. The result dict has
`error: "Dependency cycle or missing tasks"` and an empty `tasks` map;
exit code is 0. Check `r["error"]` programmatically.

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

**Retries** — `with { retries: N }` retries the step on any throw. Each
failed attempt prints to stderr; state mutations from failing attempts
persist into the next attempt — design retry logic with this in mind:

```nd
workflow with_retries {
    state attempt = 0

    step flaky with { retries: 2, retry_delay_ms: 100 } {
        attempt = attempt + 1
        let s = workflow_state()
        if (s["attempt"] < 3) {
            throw "not ready"
        }
        print("succeeded on attempt " + str(s["attempt"]))
    }
}
run_workflow(with_retries)
// succeeded on attempt 3.0
```

**Step options** (`with { ... }`): `retries` (max retry count), `retry_delay_ms`
(ms between retries), `timeout_ms` (per-step timeout), `cache` (skip on re-run
if result is cached), `cache_key` (override the cache key).

---

## 6. Print, logging, and observability

In Nodus v2.0.x, `print()` inside a workflow step produced no output —
step stdout was silently discarded. **This was fixed in v2.1.0 (BUG-022).**
If you used workflows in v2.0.x and saw nothing, upgrade to v2.1.x.

In v2.1.1, `print()` inside a step works as in any other function:

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

`workflow` and `goal` use identical syntax and have identical runtime
behavior. They are the same feature with two names:

```nd
goal release {
    step tag { print("tagging") }
    step publish after tag { print("publishing") }
}
run_goal(release)
```

`goal` is a naming convention for "desired end states" rather than
pipelines. The distinction is semantic, not technical.

CLI commands mirror the keyword: `nodus workflow-run` / `nodus workflow-plan` /
`nodus workflow-resume` for workflows; `nodus goal-run` / `nodus goal-plan` /
`nodus goal-resume` for goals. `nodus workflow-run` prints step stdout then
a JSON result payload. Using `nodus run` with `run_workflow()` in the script
gives you control over what to print.

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
$ nodus workflow-resume <graph_id>
$ nodus workflow-resume <graph_id> --checkpoint after-phase1
```

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

When a step needs multiple dependencies via the options map, use string
keys — bare identifiers cause a name error:

```nd
// WRONG: Name error: Undefined variable: deps
let t3 = task(my_fn, {deps: [t1, t2]})

// RIGHT:
let opts = {"deps": [t1, t2]}
let t3 = task(my_fn, opts)
```

---

## 10. Embedding workflows

Workflows run normally under `NodusRuntime`. Step print output appears in
`result["stdout"]`:

```python
from nodus import NodusRuntime
rt = NodusRuntime()
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

**No conditional steps** — use `try/catch` or state guards in the step body.

**No dynamic graph structure** — steps are fixed at compile time. Use
`task()` / `run_graph()` for graphs built at runtime.

**Cyclic dependency is silent** — no stderr, exit 0, `r["error"]` has the
message. Check `r["error"]` programmatically; a zero exit doesn't mean all
steps ran.

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
TESTED SCRIPTS (all run against nodus-lang v2.1.1 dev source,
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
17: wf16b_task_graph.nd     → task()/run_graph() API; bare {deps:...} causes name error
18: embedded (python3)      → NodusRuntime.run_source() captures step stdout in result["stdout"]
19: wf17_fan_out.nd         → fan-out/fan-in via state accumulation
20: wf18_limits.nd          → --step-limit global across all steps; Sandbox error fires
21: wf19_plan.nd / wf20     → workflow-plan CLI and plan_workflow() builtin both work
22: wf21_cache.nd           → cache:true skips on re-run; r["cache_hits"]=["task_N"]
23: wf22_result_shape.nd    → r["steps"] maps step names to return values
24: wf23_retry_state.nd     → state mutations from failed attempts persist into next retry

BEHAVIORAL FINDINGS:
F34: Cyclic dependency detected at runtime, not compile time. Returns exit 0 with
     r["error"]="Dependency cycle or missing tasks", no stderr output. Callers must
     inspect r["error"] to detect failure. Should exit 1 or print stderr warning.
     Filed as BUG-049.

F35: State mutations in a failed retry attempt persist into the next attempt.
     Undocumented; can cause surprising counter accumulation in retry loops.
     Documented in section 5 and known limits. Recommend adding to WORKFLOWS.md.

WORKFLOW DSL READINESS VERDICT:
Operationally ready for sequential and parallel step pipelines. BUG-022 print fix,
retry/cache/checkpoint features all work correctly. Two gaps before production use:
(1) cyclic dependency detection is silent, and (2) retry state is not isolated per
attempt. Both are documented above and workable with care.
-->
