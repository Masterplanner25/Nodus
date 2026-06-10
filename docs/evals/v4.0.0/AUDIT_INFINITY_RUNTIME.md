# Infinity Runtime Audit — Nodus 4.0.0

**Version:** 4.0.0
**Date:** 2026-06-08
**Auditor:** Claude Sonnet 4.6
**Prompt:** `docs/governance/AUDIT_INFINITY_RUNTIME.md`

---

## Check 1 — Entry Point Unification

**Result: PASS**

All seven execution modes converge on a single `VM.execute()` call:

| Entry point | Path to VM |
|-------------|-----------|
| `nodus run` | `ModuleLoader.load_module_from_source()` → `vm.run()` → `vm.execute()` |
| `nodus repl` | same ModuleLoader path |
| `nodus serve /execute` | `runner.run_source()` → `ModuleLoader` → `vm.run()` |
| `workflow run` | `builtin_run_workflow()` → `get_default_workflow_runner().start_graph()` → VM |
| `graph run` | `builtin_run_graph()` → `run_task_graph()` → VM |
| `goal run` | `builtin_run_goal()` → workflow pipeline → VM |
| `NodusRuntime.run_source()` | fresh VM with host builtins → `ModuleLoader` → `vm.run()` |

**One gap:** `/runtime/events` on the server returns `self.last_vm.event_bus.events()` —
the most recently created VM instance only. A second request overwrites the first run's
event reference. Per-run event isolation requires capturing events into the result before
the VM is GC'd.

---

## Check 2 — Execution Event Coverage

**Result: PARTIAL PASS**

The event bus (`RuntimeEventBus`, `src/nodus/runtime/runtime_events.py`) exists, is wired
to every VM instance, and is exposed to embedders via `event_sinks` on `NodusRuntime`.

Events emitted in 4.0.0:

| Event | Source | Payload |
|-------|--------|---------|
| `vm_call` | vm.py:1760 | call_type, total |
| `vm_return` | vm.py:1768 | total |
| `vm_exception` | vm.py:1782 | total, kind, message |
| `runtime_error` | vm.py:390 | coroutine_id, name, kind, message, path, line, column |
| `capability_use` | vm.py | kind, method, url (for http) |
| `vm_instruction_batch` | vm.py:1751 | count, total |
| `graph_plan_created` | vm.py:1032 | node count |
| `goal_action_start` | vm.py:1351 | goal, workflow, graph_id, step, action_kind, target |
| `goal_action_complete` | vm.py:1362 | same |
| `goal_action_fail` | vm.py:1358 | same + message |
| `memory_get/put/delete` | memory_runtime.py | key, found |
| `memory_recall_from/all` | memory_runtime.py | key, found |
| `memory_share` | memory_runtime.py | key |

**Actual event output from a failing network request** (`--trace-events`):
```
[875ms]  vm_call          get           call_type=call_method
[875ms]  vm_call          http_get      call_type=call
[875ms]  capability_use   kind=http_request  method=GET  url=https://...
[1235ms] vm_return        get           total=1.0
[1235ms] runtime_error    kind=key      message="Missing record field: ok"  line=4  col=7
[1235ms] vm_exception     total=1.0     kind=key
```

You can reconstruct what happened from this stream. What is missing:

- No `ExecutionStarted` / `ExecutionCompleted` envelope events — start and end are
  inferred from the stream boundary, not explicit
- No `StepStarted` / `StepCompleted` per workflow step — only goal-level action events
- Events are buffered in-memory on the VM instance; they are lost when the VM is
  garbage-collected unless captured via `event_sinks` or read via `/runtime/events`
  before the next execution

`--trace-events` and `--trace-file` (CLI) and `event_sinks` (embedding) all work
as documented.

---

## Check 3 — Execution Memory

**Result: FAIL**

After a run exits, Nodus has written exactly one artifact: compiled bytecode to
`.nodus/cache/` (keyed by `SHA-256(path + mtime_ns)`). No execution record is created.

The result dict is structured and correct:

```json
{
  "ok": false,
  "stage": "execute",
  "filename": "<memory>",
  "stdout": "",
  "stderr": "",
  "result": null,
  "errors": [
    {
      "type": "RuntimeError",
      "message": "Missing record field: ok",
      "line": 4,
      "column": 7,
      "details": { "kind": "key" }
    }
  ]
}
```

But it is returned to the caller and discarded. There is no:

- `run_id` generated per execution
- Execution record written to `.nodus/runs/` or any store
- Duration captured or stored
- Event stream persisted alongside the result

The substrate to build this exists: `nodus-store-sql` (`RunStore` with optimistic
locking) and `nodus-memory` (`MemoryNode`) are both live on PyPI. Nothing wires them
to the execution pipeline.

---

## Check 4 — Recall

**Result: FAIL**

`memory_recall_from(namespace, key)` and `memory_recall_all(namespace)` exist as
builtins (`src/nodus/builtins/memory_module.py`). They access shared in-process
memory — values that scripts explicitly stored with `memory_put()` during the same
server session. This is runtime state sharing, not execution history recall.

There is no:
- `nodus recall` CLI command
- `--with-recall` run flag
- Pre-run history lookup against past execution records

The absence follows directly from Check 3: you cannot recall what was never stored.

---

## Check 5 — Execution Scoring

**Result: FAIL**

No execution scoring exists. No success score, reliability score, latency percentile,
or warning count is computed or stored per run.

`std:circuit-breaker` tracks call-site failure rates but is a resilience primitive for
individual function calls, not an overall execution quality signal.

---

## Check 6 — Next-Action Recommendation

**Result: FAIL (one minor exception)**

The runtime does not recommend a next action after failure. Error output names the type,
line, and column. No systematic mapping from error kind to recommended action exists.

Exception: the lexer recognizes integer literals missing the `i` suffix and suggests
`did you mean 42i?` at the parse stage. This is the entire extent of recommendation
intelligence in 4.0.0.

The `capability_use` event and typed `kind` field on errors are machine-readable enough
that a next-action layer could consume them. The runtime does not have one.

---

## Audit Table

| Area | Question | Result | Notes |
|------|----------|--------|-------|
| CLI | Do commands produce structured run records? | ❌ | Result dict is ephemeral; no run_id |
| VM | Does execution emit lifecycle events? | ✅ Partial | Event bus works; no Start/Complete envelope |
| REPL | Are sessions remembered? | ❌ | No session history |
| Server | Are API executions tracked? | ✅ Partial | `/runtime/events` returns last VM's events only |
| Workflows | Are graph steps observable? | ✅ Partial | Goal-level action events; no per-step events |
| Errors | Are failures classified? | ✅ | Typed errors: key, name, type, runtime, parse |
| Memory | Are runs stored? | ❌ | No run log; bytecode cache only |
| Recall | Can past runs influence new runs? | ❌ | In-process memory only, not execution history |
| Scoring | Are runs evaluated? | ❌ | Not implemented |
| Next Action | Does runtime recommend what to do? | ❌ | Not implemented |

---

## Verdict

**Classification: Execution-Event-Aware Runtime**

Checks 1 and 2 pass (with partial caveats). Checks 3–6 fail.

Nodus 4.0.0 has a unified execution pipeline, a real event bus, typed errors, and
structured result dicts. It is observable at the point of execution. It is not
self-remembering: runs leave no trace once the VM is collected.

---

## Gap Analysis — Path to Persistent Runtime (Check 3)

Three changes close most of the gap without requiring new infrastructure:

**1. Generate a `run_id` per execution.**
One UUID in `VM.__init__`, threaded through the result dict and all events. No
behavior change; pure observability scaffolding.

**2. Write an execution record on exit.**
Hook into `run_source()` after the VM returns. Write
`{run_id, script, status, duration_ms, errors, events}` to `RunStore`
(`nodus-store-sql`, already on PyPI) or a `.nodus/runs/` JSON file.
The event bus already produces everything needed.

**3. Add `nodus runs` CLI command.**
A reader over the run store. Makes recall possible without any further runtime changes —
just a lookup.

Scoring (Check 5) and next-action (Check 6) are a layer above this and depend on
items 1–3 existing first.

**Relevant packages already on PyPI:** `nodus-store-sql 0.1.0` (RunStore, EventStore),
`nodus-memory 0.1.0` (MemoryNode, recall/score primitives).
