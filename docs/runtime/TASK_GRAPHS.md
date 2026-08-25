# Task Graph Runtime

This document describes the task graph runtime used by Nodus for orchestration.

## Overview
Task graphs are built from task nodes and executed by the runtime scheduler. A task is a function plus dependency metadata; a graph is a list of tasks. Execution produces a result payload and persists state to disk for resume.

Task graph state is persisted under `.nodus/graphs/<graph_id>.json`.

## Core Builtins

- `task(fn, deps)`
  - `fn` must be a function value.
  - `deps` can be:
    - `nil`
    - a single task
    - a list of tasks
    - a map with options (see below)

- `graph(tasks)`
  - `tasks` must be a list of task values.
  - Returns a graph value.

- `run_graph(graph_or_tasks)`
  - Executes a graph or list of tasks.
  - Returns a payload with `tasks`, `steps`, `timings`, `attempts`, `failed`, `cache_hits`, and `graph_id`.

- `plan_graph(graph_or_tasks)`
  - Returns a plan structure with `nodes`, `edges`, `levels`, `parallel_groups`, and `graph_id`.

- `resume_graph(graph_id)`
  - Resumes a persisted graph by id.

## Task Options
When `deps` is a map, the following keys are supported:

- `deps`: task or list of tasks
- `timeout_ms`: per-task timeout
- `retries`: max retries
- `retry_delay_ms`: delay between retries
- `cache`: enable task result caching
- `cache_key`: cache key override
- `worker`: worker capability name (for server mode)
- `worker_timeout_ms`: how long to wait for a matching worker

Example:

```nd
let t1 = task(fn() { return 1 }, nil)
let t2 = task(fn() { return 2 }, { deps: t1, retries: 2, timeout_ms: 500 })
let t3 = task(fn() { return 3 }, { deps: [t1, t2], cache: true })

let result = run_graph([t1, t2, t3])
print(result)
```

## CLI Commands

- `nodus graph <script.nd>` (plan a task graph from a script; `nodus graph run <script.nd>`
  is the equivalent explicit form)
- `nodus graph show <script.nd> [--format mermaid|dot] [--output FILE]` (render the same
  plan as a diagram instead of JSON — see below)
- `nodus run <script.nd>` (execute a script; workflows/goals may create graphs)
- `nodus workflow resume <graph_id>` (resume a persisted graph). There is no top-level
  `nodus resume` command — because bare `nodus <file>` is accepted for backward
  compatibility, typing `nodus resume <id>` is interpreted as a *filename* and fails with
  a file-not-found error rather than an unknown-command message.

## Rendering a plan

`nodus graph show` projects the plan object into a diagram format. It adds no
information — the nodes, edges and parallel levels are the same ones
`plan_workflow()` / `plan_graph()` already return — so anything `graph run` can
plan, `graph show` can draw.

Given a script that ends in `plan_workflow(build)` for a four-step workflow
where `compile` and `lint` both follow `fetch`:

```
$ nodus graph show pipeline.nd
flowchart TD
    %% build
    n0["fetch"]
    n1["compile"]
    n2["lint"]
    n3["package"]
    n0 --> n1
    n0 --> n2
    n1 --> n3
    n2 --> n3
```

`--format dot` emits Graphviz instead, and pins each parallel level with
`rank=same` so the steps the scheduler runs concurrently line up:

```
$ nodus graph show pipeline.nd --format dot
digraph "build" {
    rankdir=TB;
    node [shape=box, style="rounded,filled", fillcolor="#f5f5f5", fontname="sans-serif"];
    edge [fontname="sans-serif"];
    n0 [label="fetch"];
    n1 [label="compile"];
    n2 [label="lint"];
    n3 [label="package"];
    n0 -> n1;
    n0 -> n2;
    n1 -> n3;
    n2 -> n3;
    { rank=same; n2 n1 }
}
```

`--output FILE` writes to a file rather than stdout.

**What an edge means.** An edge is a *dependency*: `n0 --> n1` reads "compile
depends on fetch". Whether `compile` will actually run is shown too, when the
plan knows — two different things make an edge conditional, and they render
differently:

| Written | Plan key | Mermaid | DOT |
|---|---|---|---|
| `with { on: ["failed"] }` | `edge_conditions` | `n0 -->\|failed\| n1` | `n0 -> n1 [label="failed"]` |
| `when reached("x")` | `conditional_edges` | `n0 -.-> n1` | `n0 -> n1 [style=dashed]` |
| neither | — | `n0 --> n1` | `n0 -> n1` |

**A plain solid arrow means the default**, `on: ["completed"]`. Labelling every
edge `completed` would be noise, so absence carries meaning here — which is
worth knowing before reading a diagram as "unconditional".

Both were drawn as plain arrows through v5.2.0, because the plan object recorded
neither (#471, #537). The renderer never guessed: an unconditional arrow for a
conditional edge is a lie a diagram tells convincingly, so it stayed silent until
the plan carried the answer.

**`levels` is a superset once guards are involved.** It is the topological
partition, not a prediction: a `when`-guarded step appears in it whether or not
its guard will hold. Read `conditional_edges` alongside it.

Node identifiers in the output (`n0`, `n1`, …) are generated. Step names appear
only inside quoted labels, so a name containing quotes or brackets cannot alter
the structure of the emitted diagram.

## Notes
- Task graphs are the execution substrate for workflows and goals.
- In server mode, tasks can be dispatched to external workers when `worker` is set.
