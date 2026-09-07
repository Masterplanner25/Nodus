# End-to-End Architecture Audit

**Objective:** Determine whether the language runtime works correctly, consistently,
and reliably from source text to final output — and whether the layers between are
sound enough to be the foundation of a production system.

Applies to: any language runtime with a compiler, VM, and embedding API.

---

## 1. Pipeline Map

Trace the actual execution path end-to-end. Be specific — name real modules.

```
Source text
→ Lexer         (tokenization)
→ Parser        (AST construction)
→ Compiler      (bytecode emission)
→ VM / Executor (instruction dispatch, scheduler)
→ Builtins      (stdlib, host functions)
→ Output / Error
```

For each stage: what module owns it, what its input/output contract is, and
what happens if it fails.

---

## 2. Layer Integrity

Identify the layers the runtime declares (e.g. frontend / compiler / VM / stdlib /
embedding API) and evaluate whether boundaries are real.

- Does the VM import parser types?
- Does the compiler depend on runtime state?
- Does the stdlib assume things about the VM internals?
- Does the embedding API bypass the normal execution path?

**Verdict:** Clean | Minor violations | Significant coupling

---

## 3. Execution Guarantees

- Does every execution reach a terminal state (value, error, or timeout)?
- Can a script run forever without the host being able to stop it?
- Is the error model consistent — does a runtime error always surface the same way?
- Are stack overflows, infinite loops, and memory exhaustion handled or defined?
- Is step/instruction counting deterministic?

---

## 4. State Consistency

- Is VM state fully reset between executions, or can state leak between runs?
- If the runtime supports coroutines or concurrent execution: is scheduler state
  consistent on entry and exit?
- If the runtime supports persistent state (workflow graphs, checkpoints): are
  writes atomic? Can a crash leave state corrupt?
- Is user/tenant context isolated from global VM state?

---

## 5. Module and Import System

- Is import resolution deterministic given the same inputs?
- Can circular imports occur? If so, what happens?
- Is the stdlib isolated from user code, or can user code shadow stdlib symbols?
- Are import errors surfaced at load time or silently deferred?

---

## 6. Embedding API Integrity

- Is there a single, stable entry point for embedding (e.g. `NodusRuntime`)?
- Can an embedder accidentally bypass sandbox or security constraints?
- Are host-injected functions (register_function, tool_registry) isolated from
  the language's own namespace?
- Does the embedding API behave identically to the CLI entry point, or are there
  silent behavioral differences?

---

## 7. Async / Concurrency System

If the runtime has coroutines, async execution, or a task scheduler:

- Is the scheduler preemptive or cooperative? Is this documented and enforced?
- Can a runaway coroutine starve others?
- Is `spawn` / `run_loop` behavior consistent between embedded and CLI modes?
- Are coroutine resource limits enforced?

---

## 8. Failure Handling

For each failure class, answer: is it caught, is it surfaced, is it recoverable?

| Failure | Caught | Surfaced | Recoverable |
|---------|--------|----------|-------------|
| Parse error | | | |
| Compile error | | | |
| Runtime error (user code) | | | |
| Builtin error | | | |
| Timeout / step limit | | | |
| Host function exception | | | |
| Import failure | | | |
| VM internal error | | | |

---

## 9. Observability

- Can you reconstruct what a script did from logs or trace output alone?
- Does the stack trace in errors point to the right source location?
- Is bytecode introspectable (disassembly, opcode dump)?
- Is there a way to observe scheduler behavior (coroutine scheduling, task graph)?
- Can an embedder attach an observer without modifying the runtime?

---

## 10. Structural Risks

Identify:

- Tight coupling between non-adjacent layers (e.g. builtin → parser)
- Shared mutable state accessed without synchronization
- Circular dependencies (A imports B imports A)
- God objects or modules with unclear ownership
- Public APIs that expose internal types

---

## 11. Production Readiness

Answer for each: **YES / PARTIAL / NO**

- Safe to execute untrusted code?
- Safe to embed in a long-running server?
- Safe to use in multi-tenant context?
- Errors always visible to the host?
- Resource limits enforceable by the host?

---

## 12. Top 5 Weaknesses

The most critical issues found. One sentence each.

---

## 13. Top 5 Strengths

What is architecturally sound. One sentence each.

---

## 14. Final Verdict

One paragraph: Is this architecture sound enough to be the foundation of a
production language runtime?

---

**Rules:**
- Be factual. Reference real module names and file paths.
- Do not suggest features or redesigns.
- Do not assume intent — evaluate what exists.
- If something is not present, say it is absent, not that it should be added.



Nodus v4.0.0 — End-to-End Architecture Audit 6/6/26 - 11:28pm 

  ---
  1. Pipeline Map

  Stage 1: Tokenization — frontend/lexer.py
  - Input: raw source string. Output: list[Tok] — typed token objects with position info.
  - Failure: raises LangSyntaxError (from runtime/diagnostics.py) on illegal characters or unterminated strings. No partial output.

  Stage 2: Parsing — frontend/parser.py
  - Input: list[Tok]. Output: list[Base] AST nodes (types in frontend/ast/ast_nodes.py). Parser is recursive descent with _MAX_PARSE_DEPTH = 50 guard.
  - Failure: raises LangSyntaxError. Nesting violations are detected before AST construction completes.

  Stage 3: AST Lowering — orchestration/workflow_lowering.py
  - Input: AST nodes for WorkflowDef, GoalDef. Output: equivalent MapLit AST for each. This runs inside the compiler before bytecode emission; WorkflowDef
  and GoalDef AST nodes do not have their own opcodes — they are rewritten at compile time.

  Stage 4: Compilation — compiler/compiler.py + compiler/symbol_table.py
  - Input: AST. Output: flat list of [opcode, operand?] tuples + parallel code_locs list of (path, line, col) per instruction. Symbol table resolves scopes;
  FRAME_SIZE / STORE_LOCAL_IDX / LOAD_LOCAL_IDX handle local variable slot assignment.
  - Failure: raises LangSyntaxError for undefined variables, redefined functions, unknown annotations, and yield-outside-function. BytecodeVersionError on
  cache version mismatch.

  Stage 5: Module resolution — runtime/module_loader.py
  - Input: source path or source string + project root. Resolves imports, compiles each imported module, wires live export bindings. Owns the per-invocation
  module cache (self._modules).
  - Failure: LangRuntimeError with kind "import" at first unresolvable import. Circular imports raise immediately with cycle chain.

  Stage 6: VM Execution — vm/vm.py + runtime/scheduler.py
  - Input: compiled bytecode, code_locs, host globals. Output: ("halt", None) or ("return", value) from execute(). Coroutines managed by
  Scheduler.run_loop().
  - Failure modes: LangRuntimeError (caught and re-raised or passed to handle_exception), RuntimeLimitExceeded (propagates through scheduler, never caught
  mid-execution), HostFunctionError (propagates out of VM).

  Stage 7: Builtins and services — builtins/, services/
  - Called from the VM's dispatch table. Return Python values coerced to Nodus types.

  Output capture — tooling/sandbox.py::capture_output()
  - Context manager that captures stdout/stderr via sys.stdout / sys.stderr redirection, with a character-count limit enforced inline.

  Final result shaping — runtime/embedding.py::run_source()
  - Wraps the full pipeline in a try/except. Returns {"ok": true, "stdout": ..., "stderr": ...} on success or {"ok": false, "error": ..., "errors": [...]}
  on any caught exception.

  ---
  2. Layer Integrity

  Declared layers and their actual coupling:

  frontend/lexer.py, frontend/parser.py — both import runtime/diagnostics.py to raise LangSyntaxError. This is a minor upward dependency: the frontend needs
  error types that live in runtime. Not structurally harmful, but it means frontend cannot be used without runtime.

  compiler/compiler.py — imports orchestration/workflow_lowering.py (lower_goal_ast, lower_workflow_ast, STEP_OPTION_KEYS). The compiler directly depends on
  the orchestration layer. Workflow DSL lowering is not a separate pass; it is wired into the compile loop.

  vm/vm.py — imports from six distinct layers simultaneously:
  - runtime/coroutine.py, runtime/channel.py, runtime/scheduler.py, runtime/diagnostics.py, runtime/runtime_events.py, runtime/profiler.py,
  runtime/module.py
  - compiler/compiler.py (FunctionInfo, normalize_bytecode)
  - orchestration/task_graph.py, orchestration/workflow_lowering.py, orchestration/workflow_state.py
  - builtins/nodus_builtins.py, builtins/ registry
  - services/agent_runtime.py, services/memory_runtime.py, services/tool_runtime.py
  - vm/runtime_values.py

  The VM is not a pure execution engine — it is directly coupled to domain services (agent registry, memory store, tool registry) at the import level.

  builtins/ modules — eleven files (http_module.py, circuit_breaker_module.py, coroutine.py, effects_module.py, hash_module.py, retry_module.py,
  subprocess_module.py, test_module.py, time_module.py, tool_module.py, collections.py) import types directly from vm/vm.py: Record, Closure, _ClosureProxy,
  BuiltinMethod, Frame. The stdlib is coupled to the VM's internal type definitions. Any rename of these types requires updating all eleven builtins.

  runtime/embedding.py — imports and re-exports VM, Record, Closure from vm/vm.py. The embedding API's public surface includes internal VM types.

  services/agent_runtime.py — AGENT_REGISTRY: dict[str, dict] = {} is a module-level mutable global with no locking. services/memory_runtime.py —
  GLOBAL_MEMORY_STORE = MemoryStore() is a module-level singleton with no locking.

  Circular dependency (CIRC-001): vm/vm.py calls from nodus_lang_workflow.runner import get_default_workflow_runner inside function bodies (deferred, lines
  1131, 1161, 1174, 1194). nodus_lang_workflow/runner.py imports from nodus.vm.vm. The cycle is avoided at module load time only by the deferred import
  inside the function.

  Verdict: Significant coupling. The VM is structurally entangled with six other layers. The builtins are not shielded from VM internals. Layer boundaries
  exist in the directory structure but are not enforced in the import graph.

  ---
  3. Execution Guarantees

  Does every execution reach a terminal state? YES, with one exception. run_source() wraps the full pipeline in try/except Exception as err and returns an
  ok=False dict for almost all failures. The exception: if a host-registered Python function raises a Python exception, embedding.py:616 catches
  HostFunctionError and immediately raise wrapped.cause — propagating the original Python exception to the caller outside the try. This breaks the ok=False
  contract for that failure class.

  Can a script run forever? Only when both timeout_ms=None and max_steps=None are set. With default NodusRuntime construction (timeout_ms=None,
  max_steps=10_000_000), the step limit fires at 10M instructions. With CLI defaults (timeout_ms=200ms), the wall-clock deadline fires first.
  timeout_ms=None is the NodusRuntime default (v4.0.1+); max_steps=None requires explicit opt-out.

  Error model consistency: Within the VM, LangRuntimeError is the canonical type with a consistent {kind, message, payload, path, line, col, stack} shape.
  All stdlib modules return errors in this shape or compatible records. However, spawned coroutine errors are caught by the scheduler, printed to stderr via
  print(format_error(...), file=sys.stderr), and not reflected in the run_source() return value unless an on_error callback is registered
  (scheduler.py:249-257). The host receives ok=True for a run where a spawned coroutine silently failed.

  Stack overflows: Handled. max_frames (default MAX_STACK_DEPTH = 10,000) enforced in call_closure() before frame push; raises
  LangRuntimeError(kind="sandbox"), which is catchable via try/catch in script code. Nodus frames are stored in a Python list (self.frames), not the Python
  call stack, so the Python recursion limit is not the binding constraint.

  Infinite loops: Handled by step limit + wall-clock deadline. Both are enforced in record_instruction() which is called on every instruction (vm.py:2669).
  Wall-clock check is batched: fires at most 99 instructions late (_deadline_check_interval = 100).

  Memory exhaustion: NOT handled by the runtime. A script building an arbitrarily large list or map until Python runs out of heap raises MemoryError, caught
  as a generic Python exception at vm.execute():2690, wrapped as LangRuntimeError, and returned as ok=False. No proactive limit exists.

  Instruction counting: Deterministic. instructions_executed is a monotonic counter incremented on every instruction via record_instruction(). No
  instructions are skipped or double-counted.

  ---
  4. State Consistency

  VM state reset between run_source() calls: YES for execution state. Each call constructs a fresh VM instance and a fresh ModuleLoader. Variable state,
  frame stack, coroutine state, handler stack — all reset. last_vm is overwritten on each call; the previous VM is abandoned (subprocess handles drained
  only if reset() is called explicitly).

  Persistent state that does NOT reset:

  - GLOBAL_MEMORY_STORE (services/memory_runtime.py:47): a module-level MemoryStore() singleton. The VM constructor assigns self.memory_store =
  GLOBAL_MEMORY_STORE unconditionally (vm.py:279). NodusRuntime does not inject a per-run replacement. Memory written by one run_source() call persists and
  is visible to the next call in the same process.
  - AGENT_REGISTRY (services/agent_runtime.py:10): a module-level dict. Agent registrations made via register_agent() persist across all VM instances for
  the process lifetime.
  - _DEFAULT_RUNNER (nodus_lang_workflow/runner.py:31): the default WorkflowFrameworkRunner is a process-level singleton accessed via
  get_default_workflow_runner(). All VMs that call run_workflow() without explicit runner configuration share one runner.

  Scheduler state consistency: Clean. The scheduler is instantiated per ModuleLoader.load_module_from_path/source() call, not per-VM (the scheduler is wired
  into the module loader's run path). On a clean run_source() return, the scheduler's run_loop() has exhausted all coroutines.

  Workflow store write atomicity:
  - LocalWorkflowStore: writes via _atomic_write_json() — write to a temp file, os.fsync(), then os.rename() to the target path. os.rename() is atomic on
  POSIX; on Windows, os.replace() is used. Crash between write and rename leaves the temp file; the target file is unmodified.
  - SQLiteWorkflowStore: WAL journal mode + BEGIN IMMEDIATE exclusive locks. Crash mid-transaction rolls back automatically.

  User/tenant isolation: PARTIAL. A NodusRuntime instance isolates its VM state, _host_functions, and _python_registered_tools. But GLOBAL_MEMORY_STORE and
  AGENT_REGISTRY are not instance-scoped. Scripts from different tenants running in the same process share memory and agent registrations.

  ---
  5. Module and Import System

  Determinism: YES. Import resolution follows a fixed lookup order: relative path → std:* (stdlib directory) → project root → packages directory. Resolved
  paths are cached in self._modules by absolute path. Same source + same project root → same resolution. The bytecode cache (runtime/bytecode_cache.py) keys
  on content hash; stale cache triggers recompilation.

  Circular imports: Detected and raised immediately. The module loader maintains self._loading: set[str] of in-progress modules. When a module is
  encountered during its own loading, _circular_import_error() raises LangRuntimeError with the full cycle chain as stack. The error fires at load time, not
  at the first import site.

  Stdlib shadowing: Builtins in BUILTIN_NAMES cannot be overridden by user code. The compiler raises "Function already defined" if a user-defined function
  name collides with an existing name in the same module scope. register_function() explicitly rejects names in BUILTIN_NAMES with a ValueError. User code
  can define let http = 1 which shadows a local binding, but cannot shadow the http.get call resolved through import "std:http" as http.

  Import errors: Surfaced at load time. import_error() in module_loader.py raises LangRuntimeError immediately. No deferred resolution — if an import fails,
  the entire module load fails and run_source() returns ok=False before any user code executes.

  ---
  6. Embedding API Integrity

  Single, stable entry point: Partially. NodusRuntime in runtime/embedding.py is the documented embedding API. However, tooling/runner.py also creates VM
  instances directly (at lines 191, 359, 824, 1149, 1162, 1184, 1203) without going through NodusRuntime. The CLI, the service API (services/api.py), and
  the workflow resume path all use this second code path. These paths apply EXECUTION_TIMEOUT_MS = 200 by default; NodusRuntime defaults to timeout_ms=None.
  There is no guarantee that a behavior tested via NodusRuntime applies identically to the CLI path.

  Sandbox bypass risks:

  1. allowed_paths=None disables filesystem sandboxing entirely. This is documented but not guarded by a warning at construction time.
  2. The env builtin (builtins/env.py) provides full os.environ read, write, delete, and list access with no sandbox check. A script inside an
  allowed_paths-restricted NodusRuntime can still read any environment variable (including secrets injected via environment), write arbitrary env vars that
  persist for the process lifetime, and enumerate the full process environment. No allowed_paths setting prevents this.
  3. subprocess_run and subprocess_spawn execute arbitrary shell commands as the hosting process user. The stdlib exposes these by default. Restricting them
  requires explicitly omitting std:subprocess from allowed imports — a convention, not an enforcement mechanism.

  Host function namespace isolation: Protected. register_function() raises ValueError for names in BUILTIN_NAMES, preventing override of core functions.
  Host functions are stored in _host_functions and passed to the ModuleLoader as host_builtins, which are loaded into a separate vm.builtins dict — not into
  vm.module_globals or vm.functions. Resolution order (locals → module_globals → functions → host_globals) means host functions can be shadowed by
  user-defined functions of the same name.

  CLI vs embedding behavioral differences:
  - Default timeout_ms: CLI applies 200ms; NodusRuntime defaults to None (EMBED-001 closed in v4.0.1 — NodusRuntime now deliberately uses None for server/embedding use cases).
  - Memory defaults: CLI runs through tooling/runner.py which may configure memory_store differently per call path; NodusRuntime always uses
  GLOBAL_MEMORY_STORE.
  - Sandbox path: CLI applies fs_root restriction (project root) without allowed_paths; NodusRuntime defaults to allowed_paths=[os.getcwd()].

  ---
  7. Async / Concurrency System

  Cooperative scheduling, budget-enforced. Each coroutine runs until it yields, suspends on a channel recv, sleeps, or exhausts its 1,000-instruction budget
  (TASK_STEP_BUDGET = 1000, scheduler.py:16). Budget enforcement is in vm.record_instruction() — when task_step_budget reaches zero, _budget_exceeded is
  set and the coroutine is re-enqueued. This is documented in EXECUTION_INVARIANTS.md (I-SCHED-01).

  Runaway coroutine starvation: Cannot starve others beyond 1,000 instructions per turn. However, a coroutine that does not sleep, yield, or block will
  re-enter the ready queue on every budget exhaustion and receive another turn immediately. It does not starve others but it does monopolize CPU
  proportionally in a tight round-robin.

  spawn / run_loop consistency between embedded and CLI: Identical. Both paths use the same Scheduler class and TASK_STEP_BUDGET. The run_loop()
  implementation is shared. The behavioral differences are in the global deadline and step limit set before run_loop is called — not in the scheduler
  itself.

  Per-coroutine resource limits: Coroutine has task_timeout_ms and task_started_at fields (runtime/coroutine.py:25-26). The scheduler checks these at each
  coroutine resume (scheduler.py:219-229). However, this mechanism is not exposed through any user-facing API or run_source() parameter. It is internal
  infrastructure, not a documented or wired limit.

  CHAN-001 (open): recv() on an empty channel blocks the calling coroutine. If no other coroutine can ever send to that channel (e.g., the sender was
  already completed or errored), the receiving coroutine is stranded indefinitely. The scheduler's deadlock detection (scheduler.py:196-210) only fires when
  ALL live coroutines are blocked — if even one other coroutine continues running, the stranded receiver is silently abandoned until the global deadline.

  ---
  8. Failure Handling

  ┌─────────────────────────┬───────────────────────────────────────────────────────────┬───────────────────────────────────────┬──────────────────────┐
  │         Failure         │                          Caught                           │               Surfaced                │     Recoverable      │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Parse error             │ YES — LangSyntaxError in parser/lexer                     │ ok=False dict with location           │ No — execution does  │
  │                         │                                                           │                                       │ not start            │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Compile error           │ YES — LangSyntaxError, BytecodeVersionError               │ ok=False dict                         │ No                   │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Runtime error (user     │ YES — LangRuntimeError caught in vm.execute()             │ ok=False dict; script-level try/catch │ Script-level yes;    │
  │ code)                   │                                                           │  also catches                         │ process-level no     │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Builtin error           │ YES — Python exceptions wrapped as LangRuntimeError at    │ ok=False dict                         │ Script-level yes     │
  │                         │ vm.execute():2690                                         │                                       │                      │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Timeout / step limit    │ YES — RuntimeLimitExceeded propagates through scheduler,  │ ok=False dict                         │ No — full execution  │
  │                         │ caught at run_source()                                    │                                       │ aborted              │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │                         │ PARTIAL — wrapped in HostFunctionError, but               │ Escapes run_source() as live Python   │                      │
  │ Host function exception │ embedding.py:616 re-raises the original exception via     │ exception — breaks ok=False contract  │ No                   │
  │                         │ raise wrapped.cause                                       │                                       │                      │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Import failure          │ YES — LangRuntimeError during module load                 │ ok=False dict                         │ No                   │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ Spawned coroutine error │ PARTIAL — caught in scheduler.run_loop(), printed to      │ NOT in run_source() return value      │ No — run_source()    │
  │                         │ stderr                                                    │ unless on_error callback set          │ returns ok=True      │
  ├─────────────────────────┼───────────────────────────────────────────────────────────┼───────────────────────────────────────┼──────────────────────┤
  │ VM internal error       │ PARTIAL — caught by generic except Exception at           │ Wrapped as LangRuntimeError, returned │ No — VM state        │
  │ (assert, RuntimeError)  │ execute():2690                                            │  ok=False                             │ undefined after      │
  └─────────────────────────┴───────────────────────────────────────────────────────────┴───────────────────────────────────────┴──────────────────────┘

  ---
  9. Observability

  Execution reconstruction from trace: YES, when tracing is enabled. RuntimeEventBus emits timestamped events for: coroutine_spawn, coroutine_resume,
  coroutine_sleep, coroutine_wake, coroutine_complete, vm_instruction_batch, vm_call, vm_return, memory_get/put/delete, agent_call_start/complete/fail,
  tool_call_start/complete/fail, workflow_wait. The bus supports pluggable sinks (HumanReadableEventSink, JsonEventSink) via add_sink().

  Stack trace source accuracy: YES. The compiler emits a code_locs list — one (path, line, col) tuple per instruction. vm.current_loc() reads
  code_locs[self.ip]. _build_error_stack() walks self.frames and maps each frame's return IP to a source location. Errors carry the full stack as a list of
  "at <fn> (<path>:<line>:<col>)" strings.

  Bytecode introspection: YES. nodus dis <file> (CLI) calls disassemble_source() from tooling/runner.py, which emits a human-readable listing with opcodes,
  operands, and source locations. Also exposed via HTTP POST /disassemble (services/api.py:154). The structured format is returned as a dict when called
  programmatically.

  Scheduler observability: YES. runtime_scheduler_stats() returns aggregate counts (tasks spawned, resumes, sleeping tasks). runtime_tasks() returns
  per-task state (id, name, state, resume count, last resume time). Both are available to Nodus scripts via the std:runtime module.

  External observer attachment without runtime modification: PARTIAL. RuntimeEventBus.add_sink(sink) accepts arbitrary observers. Access path:
  runtime.last_vm.event_bus.add_sink(my_sink). This requires accessing last_vm after run_source() returns — there is no pre-run observer registration API. A
  sink added to last_vm after the call does not observe the execution it just completed. For pre-run attachment, the embedder must construct the VM
  directly (bypassing NodusRuntime), or access a side-channel.

  ---
  10. Structural Risks

  1. VM as god module. vm/vm.py is 2,744 lines and imports directly from runtime/, compiler/, builtins/, orchestration/, services/, and
  vm/runtime_values.py. It owns the execution engine, the scheduler interface, all builtin dispatch, workflow graph execution, memory/agent/tool service
  calls, subprocess handle tracking, bytecode serialization helpers, and profiling. There is no internal boundary within the file.

  2. Process-level mutable globals without synchronization. GLOBAL_MEMORY_STORE (services/memory_runtime.py:47) is a MemoryStore with no lock — _values is a
  plain dict. AGENT_REGISTRY (services/agent_runtime.py:10) is a plain dict. Concurrent writes from multiple threads (e.g., multiple NodusRuntime instances
  serving concurrent requests) are not atomically safe: Python's GIL protects single dict operations but not compound read-modify-write sequences.

  3. Circular dependency: vm.py ↔ nodus_lang_workflow/runner.py. The workflow runner imports nodus.vm.vm types at module level. vm.py defers its import of
  get_default_workflow_runner inside function bodies. The cycle is only broken by import timing. If nodus_lang_workflow is imported before nodus.vm in a
  fresh process (e.g., in test isolation), initialization order errors occur. Filed as CIRC-001.

  4. Builtins tightly coupled to VM internal types. Eleven builtins/ modules import Record, Closure, _ClosureProxy, BuiltinMethod, or Frame from vm/vm.py.
  These are structural VM types, not a stable public API. Any refactoring of VM value representation requires updating all eleven builtins.

  5. env builtin has no sandbox controls. builtins/env.py directly wraps os.environ with no reference to vm.allowed_paths, vm.fs_root, or any other sandbox
  configuration. A script in a tightly sandboxed NodusRuntime can enumerate, read, write, and delete process environment variables. This is not a missing
  feature — the builtin is designed this way — but it is an architectural gap in the sandbox model.

  ---
  11. Production Readiness

  ┌───────────────────────┬─────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
  │       Property        │ Verdict │                                                     Evidence                                                      │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Safe to execute       │ PARTIAL │ allowed_paths and max_frames/timeout_ms/max_steps work. But env gives full os.environ access, and std:subprocess  │
  │ untrusted code        │         │ executes arbitrary commands with no restriction beyond user not importing the module.                             │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Safe to embed in a    │         │ Each run_source() is a fresh VM with no execution-state leak. But GLOBAL_MEMORY_STORE accumulates across all runs │
  │ long-running server   │ PARTIAL │  with no GC; spawned coroutine errors are invisible without on_error; host function exceptions escape             │
  │                       │         │ run_source() as live Python exceptions.                                                                           │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Safe to use in        │ NO      │ GLOBAL_MEMORY_STORE, AGENT_REGISTRY, and _DEFAULT_RUNNER are process-level singletons. A script from one tenant   │
  │ multi-tenant context  │         │ can read and overwrite memory written by another.                                                                 │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Errors always visible │ PARTIAL │ run_source() covers almost all paths. Host function Python exceptions escape as live exceptions. Spawned          │
  │  to the host          │         │ coroutine failures print to stderr only unless on_error is set.                                                   │
  ├───────────────────────┼─────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Resource limits       │         │ max_steps, timeout_ms, max_frames, max_stdout_chars, allowed_paths are all configurable and enforced at the VM    │
  │ enforceable by the    │ YES     │ layer.                                                                                                            │
  │ host                  │         │                                                                                                                   │
  └───────────────────────┴─────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘

  ---
  12. Top 5 Weaknesses

  1. Multi-tenant isolation is architecturally absent: GLOBAL_MEMORY_STORE and AGENT_REGISTRY are process-level singletons with no per-instance scoping,
  making concurrent multi-tenant embedding unsafe by design.
  2. The env builtin is an uncontrolled sandbox escape: any Nodus script, regardless of allowed_paths or other sandbox configuration, can enumerate, read,
  write, and delete process environment variables via std:env.
  3. Host function Python exceptions break the ok=False contract: embedding.py:616 re-raises the original Python exception from a host function rather than
  returning an error dict, violating the documented invariant that run_source() never propagates Python exceptions to the caller.
  4. Spawned coroutine failures are invisible to the host without an explicit callback: a script that spawns a coroutine which dies with an uncaught error
  returns ok=True and prints only to stderr, making the failure undetectable in the default configuration.
  5. vm/vm.py is a 2,744-line god module coupled directly to the compiler, orchestration, builtins, and domain services layers, making the execution engine
  inseparable from its surrounding concerns and resistant to targeted testing or incremental replacement.

  ---
  13. Top 5 Strengths

  1. Error shaping is consistent end-to-end: LangRuntimeError carries {kind, message, payload, path, line, col, stack} from parse time through runtime, and
  every run_source() return value follows the same {ok, error, errors, stdout, stderr} shape.
  2. Execution is fully bounded by a composable three-layer limit system: timeout_ms (wall-clock), max_steps (instruction count), and max_frames (call
  depth) are independently configurable and independently enforced — any one fires without relying on the others.
  3. Workflow persistence is crash-safe at both store backends: LocalWorkflowStore uses os.fsync + os.replace (atomic rename); SQLiteWorkflowStore uses WAL
  journal mode with BEGIN IMMEDIATE — a mid-write process kill cannot leave either store in a corrupt state.
  4. Circular import detection is reliable and produces actionable errors: the _loading set with _circular_import_error() catches cycles at load time,
  surfaces the full import chain, and raises immediately rather than silently producing partial module state.
  5. The event bus provides non-invasive, pluggable observability: RuntimeEventBus.add_sink() supports arbitrary observer objects; the bus emits 20+ typed
  events covering coroutine lifecycle, memory operations, tool/agent calls, and instruction counts — without any modification to the core execution path.

  ---
  14. Final Verdict

  The architecture has a well-executed execution core — the pipeline from lexer through VM is clearly layered, the error type system is consistent, resource
  limits are composable and enforced, and the workflow persistence layer is crash-safe. These properties make it sound for single-tenant embedded
  deployment. The weaknesses, however, are structural rather than incidental: the process-level global state model (GLOBAL_MEMORY_STORE, AGENT_REGISTRY) was
  designed for single-process use and cannot be safely extended to multi-tenant without changes that affect the VM constructor and every service callsite;
  the env builtin sandbox gap and the spawned-coroutine visibility problem are contract violations that require active awareness from every embedder; and
  the VM's entanglement with six other layers means that the boundary between "execution engine" and "application framework" does not exist in the code,
  only in intent. As a foundation for a single-tenant embedded scripting runtime or a developer workflow tool, the architecture is production-capable today.
  As a foundation for a multi-tenant server executing untrusted scripts from multiple users, it is not — the shared global state is not a configuration gap
  but a structural assumption that must be resolved at the design level before multi-tenancy can be made safe.
