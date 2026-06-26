# Execution Invariants

**Version:** 4.0.8
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This document states the invariants the Nodus runtime maintains during execution.
Each invariant is grounded in a specific code area or test. An invariant is a guarantee
the runtime makes to scripts and host applications; if an invariant is violated, that
is a bug, not a design decision.

---

## 1. VM correctness invariants

### I-VM-01: Value stack is balanced across any instruction

After every instruction completes, the net stack depth change matches the instruction's
defined stack effect. Stack underflow (popping from an empty stack) is a runtime error,
not undefined behavior.

**Code:** `vm.py` — each `_op_*` handler.

### I-VM-02: Instruction pointer advances are explicit

No instruction silently advances `self.ip` by more than its documented operand count.
Every opcode handler either: (a) does `self.ip += 1` for a 0-operand opcode, (b) does
`self.ip += 2` for a 1-operand opcode, or (c) explicitly sets `self.ip` for jumps.
There is no implicit IP advance outside the handler.

**Code:** `vm.py` — all `_op_*` methods.

### I-VM-03: Call frames are balanced

Every `CALL` instruction that pushes a new frame has exactly one corresponding `RETURN`
that pops it. Uncaught exceptions unwind frames deterministically via the handler stack.
There are no orphaned frames.

**Code:** `vm.py::call_closure`, `_op_return`.

### I-VM-04: Local variables are slot-indexed after v0.8.0

All local variable accesses in functions use `LOAD_LOCAL_IDX <slot>` and
`STORE_LOCAL_IDX <slot>`, which index directly into `frame.locals_array`. The old
`LOAD name` / `STORE name` dict-based path for locals is removed from the compiler
(the opcode `LOAD_LOCAL` was tombstoned in the dispatch table at v1.0). No function-scope
local access goes through the 4-dict probe path.

**Code:** `compiler.py` (LOAD_LOCAL_IDX emission), `vm.py::_op_load_local_idx`,
`_op_store_local_idx`.

### I-VM-05: Exception handler stack is consistent with call frame depth

When `SETUP_TRY` pushes a `(handler_ip, finally_ip, stack_depth, frame_depth)` tuple,
`frame_depth` matches the current call depth. On an exception, the VM unwinds to
exactly `frame_depth` before jumping to `handler_ip`. No frames between the try-block
entry and the handler are left alive.

**Code:** `vm.py::handle_exception`, `vm.py::_op_setup_try`.

### I-VM-06: `finally` blocks always execute

If a `try/finally` block is entered and control leaves (via `return`, `throw`, normal
exit, or exception), the `finally` block executes exactly once. The deferred-return
mechanism ensures `return` inside a `try` does not skip `finally`.

**Code:** `vm.py::_op_pop_try` (normal exit → `finally_ip`), `vm.py::_op_return`
(deferred-return path), `vm.py::handle_exception` (exception path → `finally_ip`).

### I-VM-07: Structured throw values are preserved

When a script throws a structured value (record, list), the catch block receives
the full structured value as `err.payload`, not a stringified version. Strings are
passed as `err.message`; primitives are stringified. No throw value is silently lost.

**Code:** `vm.py::_op_throw`, `vm.py::handle_exception`.

### I-VM-08: Dispatch table is O(1) per instruction

The VM uses a dict-based dispatch table `self._dispatch` built once at construction.
Instruction dispatch is O(1). There is no if/elif chain in the hot path.

**Code:** `vm.py::_build_dispatch_table`, `vm.py::execute`.

---

## 2. Scheduler invariants

### I-SCHED-01: Round-robin fairness with budget enforcement

The scheduler is round-robin. Each coroutine runs until it yields, suspends, or
exhausts its instruction budget (`TASK_STEP_BUDGET = 1000`). Budget exhaustion suspends
the coroutine and re-enqueues it. No coroutine can starve others by running indefinitely.

**Code:** `runtime/scheduler.py`.

### I-SCHED-02: Scheduler does not execute after deadline

If `timeout_ms` is set, the VM checks the deadline every
`_deadline_check_interval` instructions (batched, not on every step). When the deadline
fires, execution stops with `RuntimeLimitExceeded`. The check is bounded-late, not
exact, but the VM will not run indefinitely past the deadline.

**Code:** `vm.py::record_instruction`.

### I-SCHED-03: `max_steps` is a hard ceiling on total instructions

When `max_steps` is set, the VM counts total instructions across all coroutines.
When the count exceeds `max_steps`, execution stops with `RuntimeLimitExceeded`.
This prevents runaway programs from consuming unbounded compute in embedded use.

**Code:** `vm.py::record_instruction`.

---

## 3. Module system invariants

### I-MOD-01: Each module is executed at most once per process

The module loader caches module objects by resolved path. If two imports resolve to the
same path, the second import receives the cached module object without re-executing the
module. Module-level side effects run at most once.

**Code:** `runtime/module_loader.py`.

### I-MOD-02: Relative imports cannot escape the project root

Relative import paths (non-std, non-package) are resolved relative to the importing
file's directory. The resolver checks that the resolved path remains inside the project
root. Paths that escape (e.g., `../outside.nd`) raise a parse/load error naming the
offending path.

**Code:** `runtime/module_loader.py::resolve_import_path`, `tooling/loader.py`.
**Test:** `tests/test_import_containment.py`.

### I-MOD-03: Named imports bind live export bindings

A named import (`import "mod" as m; m.x`) binds to the live export binding of `x`.
If the module updates its export, the importing module sees the updated value.
(In practice, modules rarely update exports after initialization, but the semantics
are live-binding, not value-copy.)

**Code:** `runtime/module_loader.py`.

---

## 4. Error handling invariants

### I-ERR-01: `run_source()` never propagates Python exceptions to the caller

Since v2.1.0 (BUG-005), `NodusRuntime.run_source()` catches all runtime and syntax
errors and returns `{"ok": false, "error": "...", "stdout": "...", "stderr": "..."}`.
Python exceptions do not propagate to the caller. The only failure modes the caller
sees are the `ok=false` result dict.

**Code:** `runtime/embedding.py::run_source`.

### I-ERR-02: Err records have a canonical shape

All err records produced by the runtime have the same shape:
`{kind, message, payload, path, line, column, stack}`. Some fields may be `nil` when
unavailable. Error records produced by the stdlib and companion libraries follow the same
shape (by convention; not enforced by the VM).

**Code:** `vm.py::handle_exception`, `runtime/errors.py`.

---

## 5. Sandbox invariants

### I-SAND-01: `allowed_paths` restricts filesystem builtins

When `allowed_paths` is set on `NodusRuntime`, all filesystem builtins (`read_file`,
`write_file`, `append_file`, `mkdir`, `list_dir`, `exists`) check that the requested path
is inside an allowed directory. Access outside the allowlist raises a sandbox error with
`kind="sandbox"`. This applies in both CLI mode and embedded mode.

**Code:** `vm.py` filesystem builtin handlers; `runtime/embedding.py`.
**Security test rule:** Any fix to `allowed_paths` enforcement must have tests for both
CLI mode and `NodusRuntime` embedded mode. See TECH_DEBT.md §Security boundary test rule.

### I-SAND-02: `allow_input=False` blocks `input()` in embedded mode

When `allow_input=False` (the default in embedded mode), calling `input()` from a script
raises a sandbox error rather than blocking on stdin. Host applications that do not control
stdin must use the default.

**Code:** `vm.py` input builtin.

### I-SAND-03: `max_frames` caps call stack depth

When `max_frames` is set, any function call that would exceed the limit raises a sandbox
error with `kind="sandbox"` before executing. The VM does not crash or overflow Python's
call stack; the sandbox error is catchable via `try/catch` in script code.

**Code:** `vm.py::call_closure`, `vm.py::_op_call`.

### I-SAND-04: Bytecode cache is checksum-validated

The bytecode cache format (`NDSC` magic + format version + SHA-256 + marshal payload)
verifies the checksum on load. A corrupt or tampered cache file is silently invalidated
and recompiled from source. The cache does not execute unvalidated bytecode.

**Code:** `runtime/bytecode_cache.py`.

---

## 6. Workflow and task graph invariants

### I-WFLOW-01: Workflow state writes are atomic

Workflow graph snapshots (`.nodus/graphs/<id>.json`) are written atomically via:
temp file → `fsync` → rename. Readers never see a partially-written snapshot.

**Code:** `runtime/snapshots.py`.

### I-WFLOW-02: Workflow lowering produces no workflow-specific VM instructions

Workflows and goals are lowered to ordinary map operations during compilation
(`_StateRewriter`). The VM executes only ordinary opcodes when running workflow steps.
There are no workflow-specific VM instructions.

**Code:** `orchestration/workflow_lowering.py`, `compiler/compiler.py::compile_stmt`.

### I-WFLOW-03: Task graph step execution is isolated per coroutine

Each workflow step runs in its own coroutine scheduled by the round-robin scheduler.
Step failures do not crash the scheduler. The task graph tracks per-step status
independently.

**Code:** `runtime/task_graph.py`, `runtime/scheduler.py`.

### I-WFLOW-04: Steps do not execute until all declared dependencies are completed

A step is eligible to run only when every step listed in its `after` clause has reached
`completed` (or `done`) state, meaning its result has been recorded in the `results` map.
The `ready_tasks()` predicate enforces this:

```
task in pending AND all(dep.task_id in results for dep in task.dependencies)
```

No partial satisfaction is accepted. If a dependency fails, the dependent step is never
spawned and the workflow returns a failure result immediately.

**Code:** `orchestration/task_graph.py::ready_tasks` (~line 719), `spawn_task`.

### I-WFLOW-05: A checkpoint snapshot captures the full workflow state at the moment of the `checkpoint` call

When a step executes `checkpoint "label"`, the runtime records an engine-side entry
containing: `label`, `step` (step name), `task_id`, `timestamp`, and a deep copy of the
current `workflow_state` map at that instant. The public API surface
(`workflow_checkpoints()`) returns the same entry with the internal `state` field stripped.
The snapshot is atomic: `_record_checkpoint` calls `_persist_graph_state` and
`persist_checkpoint_snapshot` before returning.

**Code:** `orchestration/task_graph.py::_record_checkpoint` (~line 749),
`orchestration/workflow_state.py::checkpoint_public`.

### I-WFLOW-06: Resume from a checkpoint does not re-execute already-completed steps

When a workflow is resumed (via `resume_workflow(id)` or `resume_workflow(id, "label")`),
the engine loads the persisted graph state and marks any step whose saved status is
`completed` or `done` as already finished — populating `results[task_id]` and removing
the step from `pending`. Those steps are never spawned again. Only steps still `pending`
(or not recorded at all) are eligible to run. This guarantees exactly-once execution of
completed steps across a resume.

**Code:** `orchestration/task_graph.py` (~line 1185–1221), `_normalize_workflow_snapshot`.

---

## 7. Coroutine and channel invariants

### I-CORO-01: Channel operations are FIFO

Sends and receives on a channel are ordered FIFO. `waiting_senders` and
`waiting_receivers` are `collections.deque` (not lists), and enqueue/dequeue at the
correct ends. No message is reordered within a channel.

**Code:** `runtime/channel.py`, `builtins/coroutine.py`.

### I-CORO-02: `yield` suspends, not terminates

`yield expr` suspends the current coroutine and returns the yielded value to the
`resume(coro)` caller. The coroutine retains all local state and resumes from the
instruction after `YIELD`. The coroutine is not terminated by `yield`.

**Code:** `vm.py::_op_yield`, `vm.py::_op_resume`.

---

## 8. Invariant coverage status

Most of these invariants have direct test coverage. Known test gaps:

- I-VM-06 (finally always runs): partially covered; edge cases (return inside try, exception
  inside finally) may have gaps. See `docs/governance/TEST_GAP_BACKLOG.md`.
- I-MOD-02 (import containment): covered by `tests/test_import_containment.py`.
- I-SAND-01 (allowed_paths): requires CLI-mode and embedded-mode tests. See
  TECH_DEBT.md §Security boundary test rule.
- I-WFLOW-01 (atomic writes): not unit-tested; relies on filesystem semantics.
- I-WFLOW-03 (step isolation): covered by task graph tests.
- I-WFLOW-04 (dependency ordering): covered by task graph integration tests.
- I-WFLOW-05 (checkpoint snapshot): partially covered; state-copy depth not explicitly asserted.
- I-WFLOW-06 (resume skips completed): covered by workflow resume tests; see also #110.

---

## Related documents

- `docs/governance/LANGUAGE_STABILITY_INDEX.md` — stability classifications
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — what happens when invariants are violated
- `docs/governance/TECH_DEBT.md` — open items that may affect invariants
- `docs/governance/TEST_GAP_BACKLOG.md` — invariant test gaps
- `docs/architecture/INFINITY_PATTERN_MAPPING.md` — structural analysis: `scheduler.run_loop()` is the execution-layer instantiation of the Infinity recurrence operator R; the full runtime maps to I→T→C→R→O→Feedback
