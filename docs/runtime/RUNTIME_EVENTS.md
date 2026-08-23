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
- Workflows/goals: `workflow_start`, `workflow_step_start`, `workflow_step_complete`, `workflow_step_fail`, `workflow_retry_scheduled`, `workflow_complete`, `workflow_fail`, `goal_start`, `goal_step_start`, `goal_step_complete`, `goal_step_fail`, `goal_retry_scheduled`, `goal_complete`, `goal_fail`
- Actions: `goal_action_start`, `goal_action_complete`, `goal_action_fail`

The two flow kinds emit the same events under their own prefix. `*_retry_scheduled`
fires only when a step retry is *deferred* to a sweeper — see
[FAILURE_AND_DEGRADATION_MODEL.md](FAILURE_AND_DEGRADATION_MODEL.md). A retry taken
in-process emits `task_retry` alone (#392, #393).

## Retention

The bus keeps a **bounded window** of events — the most recent 50,000 by default.
`runtime_events()` and the HTTP `/runtime/events` endpoint read that window, so a
program that emits more than the limit sees the newest ones, not the oldest.

Set `NODUS_EVENT_HISTORY` to change it. `0` keeps nothing while still dispatching
to sinks, which is what a streaming consumer wants; an embedder that genuinely
needs everything can construct the bus with `history=None`.

## VM bookkeeping events are opt-in

Three high-volume types — `vm_call`, `vm_return`, `vm_instruction_batch` — are
emitted **only when something can observe them**: a sink is attached (which is what
`--trace-events`, `--trace-json`, `--trace-file` and the DAP debugger do), or a host
asks for them explicitly.

They are one event per function call, per return, and per 100 instructions. On a
compiler workload that was 206,382 retained objects for a run that printed one line
— 58% of everything it allocated, and roughly half its CPU — with nothing reading
them (#522).

To turn them on:

```bash
NODUS_TRACE_VM_EVENTS=1 nodus run script.nd
```

or from Python:

```python
RuntimeEventBus(record_vm_events=True)     # at construction
bus.enable_vm_events()                     # or later
```

**The aggregate does not depend on them.** `function_calls`, `returns` and
`instructions_executed` are counters maintained independently of the bus, and are
what `get_execution_stats()` reports. Suppressing the per-event detail changes what
is *kept*, never what happened.

`RuntimeEventBus.wants(event_type)` is the single place this decision lives. Code
that emits a high-volume event should ask it rather than deciding for itself.

## Notes
- Event payloads are normalized for JSON safety.
- Event schemas may evolve between releases.
