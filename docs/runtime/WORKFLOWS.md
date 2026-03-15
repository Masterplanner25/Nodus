# Workflows and Goals

Workflows and goals are orchestration primitives that compile to task graphs. They provide step dependencies, persistent state, and checkpointing.

## Syntax

```nd
workflow build {
    state version = "0.1.0"

    step compile {
        print("compile")
    }

    step package after compile with { retries: 2 } {
        checkpoint "after-package"
        print("package")
    }
}
```

Goals use the same syntax:

```nd
goal release {
    step tag {
        print("tag")
    }
}
```

## Step Dependencies
- `step name` defines a step.
- `step deploy after build, test { ... }` declares dependencies.

## State
- `state name = expr` defines workflow state.
- Inside steps, `workflow_state()` returns the current state map.
- Workflow state is persisted with the task graph and returned in results.

## Checkpoints
Inside a step, you can record checkpoints:

```nd
checkpoint "label"
```

Checkpoints can be used with `workflow-resume` and `goal-resume`.

## Persistent Graph Snapshots
Workflow and goal runs now persist richer snapshots under `.nodus/graphs/<graph_id>.json`. Each snapshot records the graph status, task metadata (status, attempts, errors, worker hints), completed outputs, the pending task queue, scheduler-ready task ordering, workflow metadata, checkpoint history, and an `updated_at` timestamp. The write path is atomic (temp file -> fsync -> rename), keeping persisted graphs inspectable and crash-resistant.

Snapshots are used whenever a workflow or goal is resumed: the runtime loads the latest snapshot, rehydrates task outputs and workflow state, and skips already completed steps before scheduling remaining work.

## Checkpoint Recovery
When a step calls `checkpoint`, the runtime writes `.nodus/graphs/<graph_id>.checkpoint.json`, which stores:

- the checkpoint label + timestamp
- completed tasks + intermediate outputs
- pending tasks that still need to run
- the scheduler-ready queue order at the time of the checkpoint
- workflow state + metadata (workflow/goal names, execution kind)

When `resume_workflow` or `resume_goal` runs without an explicit label, the loader prefers the latest checkpoint file, applies its pending queue, and continues scheduling from the saved state. Passing `--checkpoint <label>` rolls back downstream work to that label before resuming.

Cleanup of completed graphs is controlled by `nodus workflow cleanup` and the `NODUS_WORKFLOW_RETENTION_SECONDS` environment variable. The cleanup command can remove old snapshots/checkpoints while leaving active runs untouched.

## Step Options
Supported `with { ... }` options:
- `timeout_ms`
- `retries`
- `retry_delay_ms`
- `cache`
- `cache_key`
- `worker`
- `worker_timeout_ms`

## Action Expressions
Action expressions are only valid inside steps and are converted into runtime actions:

- `action tool "name" with { ... }`
- `action agent "name" with { ... }`
- `action memory_put "key" expr`
- `action memory_get "key"`
- `action emit "event" with { ... }`

The last action expression in a step is automatically returned.

## Builtins
- `run_workflow(workflow)` / `plan_workflow(workflow)` / `resume_workflow(graph_id, checkpoint=nil)`
- `run_goal(goal)` / `plan_goal(goal)` / `resume_goal(graph_id, checkpoint=nil)`
- `workflow_state()`
- `workflow_checkpoints(graph_id)`
- `current_workflow_id()`

## CLI Commands

- `nodus workflow-run <script.nd> [--workflow <name>]`
- `nodus workflow-plan <script.nd> [--workflow <name>]`
- `nodus workflow-resume <graph_id> [--checkpoint <label>]`
- `nodus workflow-checkpoints <graph_id>`
- `nodus workflow list [--project-root <path>]`
- `nodus workflow resume <graph_id> [--checkpoint <label>] [--project-root <path>]`
- `nodus workflow cleanup [--project-root <path> --retention-seconds N --force]`
- `nodus goal-run <script.nd> [--goal <name>]`
- `nodus goal-plan <script.nd> [--goal <name>]`
- `nodus goal-resume <graph_id> [--checkpoint <label>]`

## Output Shape
Workflow/goal runs return a task-graph-style payload with `steps`, `tasks`, `timings`, and `graph_id`. Workflow runs also include:
- `workflow` and/or `goal` names
- `state` (workflow state map)
- `checkpoints` (checkpoint metadata)
