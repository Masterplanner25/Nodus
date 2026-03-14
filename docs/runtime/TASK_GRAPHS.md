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

- `nodus graph <script.nd>` (plan a task graph from a script)
- `nodus run <script.nd>` (execute a script; workflows/goals may create graphs)
- `nodus resume <graph_id>` (resume a persisted graph)

## Notes
- Task graphs are the execution substrate for workflows and goals.
- In server mode, tasks can be dispatched to external workers when `worker` is set.
