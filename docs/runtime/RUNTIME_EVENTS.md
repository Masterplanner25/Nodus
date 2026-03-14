# Runtime Events and Tracing

Nodus includes a runtime event bus used by the scheduler, task graph engine, and workflow/goal execution.

## Enabling Event Tracing
Use CLI flags with `nodus run`:

- `--trace-events` output human-readable events to stdout
- `--trace-json` output JSON event objects to stdout
- `--trace-file <path>` write events to a file (human or JSON depending on flags)

Examples:

```bash
nodus run script.nd --trace-events
nodus run script.nd --trace-json --trace-file trace.json
```

## Event Access From Code
Builtins:
- `emit(name, payload={})`
- `runtime_events()`
- `runtime_clear_events()`
- `runtime_event_count()`

Stdlib wrapper:

```nd
import "std:runtime" as runtime
let events = runtime.events()
```

## Common Event Types
The event stream is not yet a stable contract, but commonly includes:

- Scheduler: `coroutine_spawn`, `coroutine_resume`, `coroutine_wake`, `coroutine_complete`
- Channels: `channel_send`, `channel_recv`, `channel_close`, `channel_wake`
- Task graphs: `task_graph_start`, `graph_persist`, `graph_resume`, `task_start`, `task_success`, `task_fail`, `task_retry`
- Workflows/goals: `workflow_start`, `workflow_step_start`, `workflow_step_complete`, `workflow_complete`, `goal_start`, `goal_step_start`, `goal_step_complete`, `goal_complete`
- Actions: `goal_action_start`, `goal_action_complete`, `goal_action_fail`

## Notes
- Event payloads are normalized for JSON safety.
- Event schemas may evolve between releases.
