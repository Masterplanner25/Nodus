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
- `nodus goal-run <script.nd> [--goal <name>]`
- `nodus goal-plan <script.nd> [--goal <name>]`
- `nodus goal-resume <graph_id> [--checkpoint <label>]`

## Output Shape
Workflow/goal runs return a task-graph-style payload with `steps`, `tasks`, `timings`, and `graph_id`. Workflow runs also include:
- `workflow` and/or `goal` names
- `state` (workflow state map)
- `checkpoints` (checkpoint metadata)
