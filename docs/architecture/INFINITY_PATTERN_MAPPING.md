# Infinity Pattern Mapping

**Status:** Reference document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document records a verified structural finding: the Nodus runtime naturally
implements, at the execution layer, the same abstract pattern that the Infinity
Algorithm implements at the decision layer. The finding is architectural, not
incidental — the same mathematical structure governs both systems.

This is not a design constraint. It is a verified post-hoc observation. The
runtime was not built to implement the Infinity Algorithm; it happens to embody
the same structure because that structure is the correct shape for a
feedback-driven, stateful execution engine.

---

## The Infinity Algorithm (canonical form)

The Infinity Algorithm, as defined in Masterplan Infinit Weave's canonical spec,
is a feedback control loop over evolving system state:

```
Initialize S_0
For each time step t:
    I_t  ← external + internal signals
    S_t' ← T(S_t, I_t)       [Transformation]
    S_t'' ← C(S_t')           [Constraint enforcement]
    S_{t+1} ← R(S_t'')        [Recurrence / feedback]
    O_t  ← Output(S_{t+1})
End loop
```

With state space:
```
S_t = (Tasks_t, Memory_t, MasterplanState_t, Metrics_t, ExternalSignals_t)
```

And transformation decomposed as:
```
T = E_t ∘ Q_t ∘ U_t
  where U_t = deterministic update
        Q_t = model-based inference
        E_t = metric evaluation
```

At the decision layer (AINDY), this loop evaluates KPI scores, generates
`next_action` decisions, and routes execution based on prior outcomes. The loop
is explicit, named, and runs as an orchestrated service.

---

## The Nodus execution model

The Nodus runtime runs the same abstract loop at the execution layer. The
correspondence is exact at the structural level:

### State S(t)

Nodus maintains five co-evolving state surfaces:

| State surface | What it holds | Location |
|---|---|---|
| VM state | `ip`, `stack`, `frames`, `handler_stack`, `module_globals`, `host_globals` | `vm/vm.py:194` |
| Scheduler state | `ready_queue`, `timers`, `sleeping_tasks`, `tasks`, anti-starvation counters | `runtime/scheduler.py:24` |
| Coroutine state | Per-coroutine `ip`, `stack`, `frames`, `state`, `blocked_on`, `last_result` | `runtime/coroutine.py:7` |
| Workflow / task graph state | `pending`, `results`, `workflow_state`, `checkpoints`, persisted graph snapshots | `orchestration/task_graph.py:489` |
| Memory state | `MemoryStore._values` (namespace-scoped KV), `InMemoryEffectStore` (EXACTLY_ONCE ledger) | `services/memory_runtime.py` |

All five surfaces advance together on every execution step. This is S(t): a
tuple of five continuously mutating objects that co-evolve through time.

### Input

Input enters at multiple levels, not only at source-parse time:

| Layer | What enters |
|---|---|
| Frontend | Source text (.nd files), CLI arguments |
| Compiler | AST nodes, module bytecode |
| VM | Bytecode instruction stream, initial globals dict |
| Scheduler | Coroutine objects, timer events, channel messages |
| Workflow | Resume payloads, `workflow_wait()` signals |
| Runtime | `emit()` events, `syscall()` arguments, `tool_call()` results |
| Memory | `put_value()` / `share()` writes, `recall_from()` queries |
| Effects | `effect_pending()` / `effect_complete()` lifecycle signals |

The key observation: at the workflow and scheduler layers, runtime events and
resume payloads are first-class inputs that arrive *during* execution, not only
before it. This mirrors the Infinity Algorithm's distinction between
`I_t^{ext}` (external signals) and `I_t^{int}` (internally generated triggers).

### Transformation

Five staged passes:

1. **Lexer** (`frontend/lexer.py`) — source text → token stream
2. **Parser** (`frontend/parser.py`) — token stream → typed AST
3. **Workflow lowering** (`orchestration/workflow_lowering.py`) — `WorkflowDef`/`GoalDef` AST → desugared map literals with step closures
4. **Compiler** (`compiler/compiler.py`) — AST → bytecode (BYTECODE_VERSION 4)
5. **Optimizer** (`compiler/optimizer.py`) — bytecode → optimized bytecode (fixed-point loop)
6. **VM execution** (`vm/vm.py`) — bytecode → values via O(1) dispatch table
7. **TaskGraph execution** (`orchestration/task_graph.py`) — workflow value → dependency-ordered coroutine spawns → accumulated result dict

Note that step 7 can re-invoke steps 4–6 at runtime: `_rebuild_workflow_graph()`
re-compiles source, resets the VM, and re-extracts the workflow definition when
a persisted graph is resumed and its function table needs reconstruction. The
pipeline is not strictly linear — the compiler is a runtime-callable transform.

### Constraint (C operator)

Nodus enforces constraints at every layer:

| Layer | Constraint |
|---|---|
| Lexer/Parser | `LangSyntaxError`; interpolation depth cap (32) |
| Compiler | Upvalue resolution at compile time; undefined names fail at compile time |
| Type system | `ensure_string`, `ensure_number`, `ensure_function`, etc. — type mismatches raise immediately (`vm.py:648–769`) |
| Sandbox | `_ensure_path_allowed()` on every filesystem access; `kind="sandbox"` on violation (`vm.py:493–523`) |
| Scheduler | Per-task `task_timeout_ms`; `TASK_STEP_BUDGET=1000` instruction limit per quantum |
| Execution limits | `max_steps`, `max_frames`, `deadline` — checked during dispatch; `RuntimeLimitExceeded` does not cross coroutine handlers |
| Module | `BYTECODE_VERSION` header check on load; function arity validated before invocation |
| Workflow | Cycle detection before deadlock report; `event_type` must be non-empty; checkpoint label must be a string |
| Effects | `effect_resolve()` EXACTLY_ONCE gate; `is_json_safe()` on all memory writes and `emit()` payloads |

### Recurrence (R operator)

This is where the correspondence is strongest. Multiple independent recurrence
structures exist in parallel:

**Scheduler run_loop** (`scheduler.py:165`):
```
while ready_queue or timers or _io_channels:
    drain timers
    drain io channels
    pick coroutine from ready_queue
    resume coroutine (TASK_STEP_BUDGET instructions)
    match result:
        sleep     → push to timer heap
        channel   → leave suspended
        yield     → re-enqueue (cooperative round-robin)
        finished  → mark complete, trigger callbacks
```
This is `R = R_sched ∘ R_trigger ∘ R_time` in the Infinity canonical form.

**TaskGraph on_complete loop** (`task_graph.py:709`):
```
spawn ready_tasks()
  → on_complete(coroutine):
      record result
      spawn new ready_tasks()    ← recurrence: each completion re-evaluates
      persist state
  → on_error:
      if retryable: re-mark pending + spawn_task(delay_ms)  ← re-enters
      else: mark failed
```

**Workflow resume**: `resume_graph()` → `run_task_graph(resume_state=...)` reloads
persisted state and re-derives which tasks are pending. Recurrence crosses process
boundaries.

**Coroutine yield**: A yielding coroutine is re-appended to `ready_queue`. Any
user program with a `while` or `for` loop is a tight instruction-level recurrence
over VM state.

### Output

| Type | What it contains | Location |
|---|---|---|
| Task results | Accumulated output dict from each step closure | `task_graph.py:1271` |
| Workflow state snapshot | `workflow_state` dict at completion | `task_graph.py:537` |
| Emitted events | `RuntimeEvent` objects from `emit()` calls | `runtime/runtime_events.py` |
| Checkpoint records | Labeled state snapshots written during execution | `task_graph.py:394` |

### Feedback

Prior execution affects future execution through six documented channels:

| Channel | Mechanism | Location |
|---|---|---|
| Task output → downstream input | `results[task.task_id]` passed as args to dependent tasks | `task_graph.py:996` |
| `workflow_state` | Mutable shared map; any step writes, later steps read | `task_graph.py:537`, `vm.py:1251` |
| Checkpoint + resume | Prior `workflow_state` loaded and merged on `resume_graph()` | `task_graph.py:394–430` |
| Memory store | `put_value()` / `recall_from()` — cross-coroutine, cross-invocation | `services/memory_runtime.py` |
| Circuit breaker | State transitions (closed → open → half-open) from failure history; `cb_call()` consults current state before executing | `builtins/circuit_breaker_module.py` |
| Effect store | `effect_resolve()` returns the cached result on re-execution of a completed action | `builtins/effects_module.py` |
| Retry counter | `task.attempts` governs whether and when re-execution occurs | `task_graph.py:1058` |

---

## Verified mapping table

| Infinity concept | Nodus equivalent | Strength |
|---|---|---|
| S(t) — evolving state | VM + Scheduler + Coroutine + TaskGraph + MemoryStore | Exact |
| Input (I_t^ext + I_t^int) | Source files, bytecode, runtime events, resume payloads, syscall args, channel messages | Exact |
| T (transform) | Lexer → Parser → Lowering → Compiler → Optimizer → VM dispatch → TaskGraph | Exact |
| U_t (deterministic update) | Compiler, sandbox enforcement, type guards, rule-based routing | Exact |
| Q_t (inference) | LLM tool calls via `std:tool`; `syscall()` to external AI services | Partial (external, not internal) |
| E_t (metric evaluation) | No explicit KPI scoring in the runtime — this is the decision-layer gap | Not present (by design) |
| C (constraint) | Type guards, sandbox, step budgets, deadlines, arity validation, cycle detection, JSON-safety, EXACTLY_ONCE gate | Exact |
| R (recurrence) | `scheduler.run_loop()`, TaskGraph `on_complete → spawn_ready`, coroutine yield, retry re-spawn, `resume_graph()` | Exact |
| O_t (output) | Task results, workflow_state snapshot, emitted RuntimeEvents, checkpoint records | Exact |
| Feedback | `results[]` → dependent tasks, `workflow_state`, MemoryStore, circuit breaker state, effect store cache, retry counter | Exact |

---

## The gap: execution layer vs. decision layer

The Infinity Algorithm at the decision layer (AINDY) owns one component Nodus
deliberately does not implement: **E_t (metric evaluation) and the adjustment loop**.

AINDY evaluates `execution_speed`, `decision_efficiency`, `ai_productivity_boost`,
`focus_quality`, and `masterplan_progress` — domain KPIs — and uses them to generate
`next_action` and `LoopAdjustment`. This is a feedback loop over *business meaning*.

Nodus operates at the layer below: it is the execution substrate that AINDY's
`next_action` will eventually invoke. Nodus tracks whether a coroutine is alive,
whether a task succeeded, whether a channel has messages. It does not evaluate
whether that work was strategically correct.

One additional gap relative to a "pure" Infinity implementation: Nodus does not
self-modify its transformation rules based on feedback. The circuit breaker and
retry mechanisms adapt *routing* (which coroutine runs next, whether a circuit is
open), but the compiler and VM dispatch table remain fixed for the lifetime of an
execution unit. Nodus adapts execution paths, not opcode semantics. This is correct
behavior for a language runtime.

The two layers are complementary:

```
Decision layer (AINDY / Infinity Algorithm)
  → evaluates KPI state
  → generates next_action / execution intent

Execution layer (Nodus runtime)
  → receives execution intent as input
  → runs the feedback-driven execution loop
  → returns task results, workflow_state, emitted events

         ↑ output feeds back as input to decision layer ↑
```

This is why Nodus is the correct execution substrate for the Infinity Algorithm,
not merely a convenient one: both layers implement the same underlying structure.
The decision layer evaluates meaning; the execution layer evaluates correctness.
Together they form a nested Infinity loop — the runtime's recurrence is one step
in the decision layer's outer recurrence.

---

## Related documents

- `docs/runtime/EXECUTION_INVARIANTS.md` — the runtime guarantees that hold across each step of the execution loop
- `docs/runtime/ARCHITECTURE.md` — full compilation and execution pipeline
- `docs/runtime/WORKFLOWS.md` — workflow and task graph reference
- `docs/governance/LIBRARY_ECOSYSTEM.md` — companion libraries that extend the execution layer
