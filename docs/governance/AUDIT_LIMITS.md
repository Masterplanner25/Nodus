# System Limits and Leverage Boundary Audit

**Objective:** Define the precise boundary where this language runtime stops being
useful — in terms of workload size, program complexity, concurrent users, and
automation depth — and identify the single most actionable path to extending it.

Applies to: any language runtime where real workloads are being considered.

---

## Rules

- Every limit must be either measured or derivable from source code inspection.
- "It depends" is acceptable only when followed by: depends on what, and what are the two extremes.
- Each section ends with: **hard boundary**, **root cause**, and **upgrade path**.

---

## 1. Maximum Workload

What is the largest single program execution the runtime can handle before it
degrades or fails?

Measure or estimate:
- Maximum source file size before the compiler slows meaningfully
- Maximum number of instructions before timeout mechanisms fire
- Maximum data structure size (list, map) before the VM slows
- Maximum recursion depth before stack overflow

| Metric | Measured value or estimate | Failure mode |
|--------|---------------------------|--------------|
| Source file size | | |
| Instruction count | | |
| Max list/map size | | |
| Max recursion depth | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 2. Maximum Program Complexity

At what point does program structure become unmanageable in this language?

- Maximum number of modules before import resolution degrades
- Maximum number of functions before symbol resolution becomes a bottleneck
- Are there syntax or semantic limits on program structure (e.g. max nesting depth,
  max function parameters, max closure capture count)?
- Is there a maximum number of workflow steps? Workflow graph size?

| Metric | Limit | Behavior at limit |
|--------|-------|------------------|
| Module count | | |
| Functions per module | | |
| Nesting depth | | |
| Workflow step count | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 3. Maximum Concurrent Users / Scripts

What is the concurrency ceiling, both within a single runtime instance and across
multiple instances?

- Maximum coroutines schedulable concurrently in a single runtime
- Maximum concurrent runtime instances in a single process
- What happens when concurrency exceeds the limit — silent degradation, error, crash?
- Is the runtime thread-safe across multiple instances? (e.g. shared global state)

| Metric | Limit | Behavior at limit |
|--------|-------|------------------|
| Coroutines per runtime | | |
| Runtime instances per process | | |
| Thread safety | Thread-safe / Unsafe / Not tested | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 4. Maximum Automation Depth

How far can automation go before it requires the host to take over?

- Can a script run, complete, and trigger a follow-on script without host involvement?
- Can the runtime self-schedule work across time (e.g. "run this in 30 minutes")?
- Can the runtime persist state across process restarts without application code?
- Is there a durable event queue, or does event handling require the host?
- What is the maximum duration of a single workflow from start to completion?

| Capability | Available in language | Requires host code |
|------------|----------------------|-------------------|
| Self-scheduling | | |
| Cross-restart persistence | | |
| Event-driven resumption | | |
| Long-duration workflows | | |
| Autonomous retry on failure | | |

**Hard boundary:** ___  
**Root cause:** ___  
**Upgrade path:** ___

---

## 5. Leverage Boundary

At what point does using this language stop saving time compared to writing the
equivalent in the host language directly?

Consider:
- Simple scripting: what is the minimum program complexity where the language adds value?
- Moderate complexity: does the language continue to add value as program complexity grows?
- High complexity: at what point is the language overhead (learning, debugging, tooling)
  greater than the benefit?

**Where the language adds the most leverage:** (one sentence)

**Where the language stops adding leverage:** (one sentence)

**The program type that is hardest to write in this language despite being within its
stated scope:** (one sentence)

---

## Summary: Hard Limits Table

| Dimension | Hard Limit | Root Cause | Upgrade Path |
|-----------|-----------|------------|--------------|
| Workload | | | |
| Complexity | | | |
| Concurrency | | | |
| Automation depth | | | |
| Leverage ceiling | | | |

---

## Single Most Actionable Upgrade

If one change could raise the most limits simultaneously, what is it?

Name: the specific limit it removes, the specific mechanism that currently causes
the limit, and the specific change that would remove it.

Do not list multiple options. Identify the one highest-leverage change.

---

**Rules:**
- All limits must be grounded in code, measurement, or a specific design decision —
  not general expectations for this class of system.
- If a limit has not been measured, say "estimated from inspection of [file/mechanism]."
- If a limit is configurable, state the default and the maximum configurable value.





Nodus v4.0.0 — System Limits and Leverage Boundary Audit - 6/6/26-10:50pm 

  ---
  1. Maximum Workload

  Source file size before compiler slows: No explicit limit exists. The compiler processes source via parser.py → compiler.py as a single pass with no
  file-size check. The practical ceiling is expression nesting depth (_MAX_PARSE_DEPTH = 50, parser.py:109) — a deeply nested literal or call chain at depth
  51 raises a parse error. Linear code of any length compiles without degradation from file size. Estimated from inspection: a 10,000-line flat script
  compiles fine; a 51-deep nested expression fails immediately.

  Maximum instructions before timeout fires: Two independent limits apply.

  - CLI mode: EXECUTION_TIMEOUT_MS = 200 (wall-clock, config.py:8) fires first. From benchmark.nd, 5,000 iterations of a tight while loop ("comfortably
  fits" in 200ms). Estimating ~8 instructions/iteration: ~40,000 instructions/200ms = ~200,000 instructions/second throughput on a hot local loop. At that
  rate, 200ms allows ~40,000 compute instructions; I/O waits don't count against the clock when the scheduler sleeps (vm.deadline paused during
  time.sleep(), scheduler.py:186).
  - NodusRuntime (embedded): timeout_ms=None by default, max_steps=10,000,000 (config.py:5). At ~200,000 instructions/second, max_steps fires after ~50
  seconds of pure compute. Both limits are configurable to None for long-lived services.

  Maximum data structure size: No VM-enforced limit on list or map size. Python heap is the practical bound. Channel queues (deque, channel.py:10) are
  unbounded. No size check exists in _op_list_build, _op_map_build, or _op_push.

  Maximum recursion depth: MAX_STACK_DEPTH = 10,000 (config.py:7), wired to vm.max_frames in sandbox.py:37 and as an optional NodusRuntime constructor
  parameter. Enforced in vm.py::call_closure (line 1761) and _op_call (line 2378) as a sandbox error before the frame is pushed. Nodus frames are stored in
  a Python list (self.frames), not the Python call stack, so the 10,000 limit is a Nodus-level policy, not a CPython recursion limit.

  ┌───────────────────────────────────────┬────────────────────────────────────────────────────┬──────────────────────────────────────────────────────┐
  │                Metric                 │                       Value                        │                     Failure mode                     │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Source file size                      │ Unbounded (expression nesting limited to depth 50) │ ParseError: Expression too deeply nested at depth 51 │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Instruction count (CLI)               │ ~40,000 meaningful instructions/200ms              │ RuntimeLimitExceeded: Execution timed out            │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Instruction count (embedded, default) │ 10,000,000 total                                   │ RuntimeLimitExceeded: Execution step limit exceeded  │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Max list/map size                     │ Unbounded (Python heap)                            │ MemoryError from Python                              │
  ├───────────────────────────────────────┼────────────────────────────────────────────────────┼──────────────────────────────────────────────────────┤
  │ Max recursion depth                   │ 10,000 frames (configurable)                       │ SandboxError (catchable)                             │
  └───────────────────────────────────────┴────────────────────────────────────────────────────┴──────────────────────────────────────────────────────┘

  Hard boundary: Wall-clock timeout for the CLI; step limit for embedded. Any computation-heavy program — tight loops, recursive algorithms, large data
  transforms — hits these before any data structure limit.

  Root cause: The 200ms CLI deadline was calibrated for sandboxed single-shot scripts, not for algorithmic programs. The VM has no JIT, no loop-invariant
  hoisting, and no escape from the ~200,000 instruction/second throughput ceiling imposed by the Python interpreter.

  Upgrade path: nodus run --time-limit N extends the wall-clock deadline. For embedded use, NodusRuntime(timeout_ms=None, max_steps=None) removes both
  limits. The instruction throughput ceiling can only be raised by a PyPy backend or a native VM loop (Rust/C extension) — a known deferred item, not
  planned for v4.x.

  ---
  2. Maximum Program Complexity

  Module count: No limit. The module loader caches loaded modules in self._modules: dict[str, NodusModule] (per-loader instance, module_loader.py:105).
  Resolution is O(1) per cache hit. Cycle detection uses self._loading: set[str] to prevent infinite recursion. The stdlib has 24 .nd modules — all load
  without degradation. Practical ceiling: filesystem I/O during initial load for large module graphs; compile time grows linearly.

  Functions per module: No limit. The compiler stores all functions in self.functions: dict[str, FunctionInfo] (unbounded dict). Symbol resolution at call
  sites is O(1) by name. No documented upper bound.

  Nesting depth: _MAX_PARSE_DEPTH = 50 expressions deep (parser.py:109). This applies only to expression nesting (nested calls, brackets), not block nesting
  (if/while/fn statements). Block nesting follows Python's own stack depth, which is effectively unlimited at these scales.

  Local variables per function: No explicit limit. local_slot_counter in symbol_table.py:61 increments per local and has no cap. The Frame.locals_array is a
  pre-allocated Python list of that size.

  Workflow step count: No explicit cap. workflow_to_graph() raises a runtime error for zero steps and for dependency cycles (_detect_cycle_task_ids,
  task_graph.py:463). A graph with 100 steps, 500 edges would resolve topologically without hitting any coded limit.

  ┌──────────────────────────────┬──────────────────────────────────────┬─────────────────────────────┐
  │            Metric            │                Limit                 │      Behavior at limit      │
  ├──────────────────────────────┼──────────────────────────────────────┼─────────────────────────────┤
  │ Module count                 │ Unbounded (per-instance loader dict) │ Linear compile time growth  │
  ├──────────────────────────────┼──────────────────────────────────────┼─────────────────────────────┤
  │ Functions per module         │ Unbounded                            │ None                        │
  ├──────────────────────────────┼──────────────────────────────────────┼─────────────────────────────┤
  │ Expression nesting depth     │ 50 (hard, _MAX_PARSE_DEPTH)          │ ParseError at depth 51      │
  ├──────────────────────────────┼──────────────────────────────────────┼─────────────────────────────┤
  │ Local variables per function │ Unbounded                            │ None                        │
  ├──────────────────────────────┼──────────────────────────────────────┼─────────────────────────────┤
  │ Workflow step count          │ Unbounded (cycle detected)           │ Runtime error only on cycle │
  └──────────────────────────────┴──────────────────────────────────────┴─────────────────────────────┘

  Hard boundary: Expression nesting depth of 50. Everything else scales with Python memory.

  Root cause: _MAX_PARSE_DEPTH is a guard against parser stack overflows on pathological inputs, set conservatively. Real programs rarely hit it; generated
  code might.

  Upgrade path: Raise _MAX_PARSE_DEPTH in parser.py:109. No other complexity limit requires a design change.

  ---
  3. Maximum Concurrent Users / Scripts

  Coroutines per runtime instance: No enforced limit. The scheduler's ready_queue is an unbounded deque; tasks: dict[int, object] grows without bound. All
  coroutines run cooperatively in a single thread — the GIL is never released during Nodus execution. Each coroutine gets a 1,000-instruction budget per
  turn (TASK_STEP_BUDGET = 1000, scheduler.py:16), so throughput per coroutine degrades linearly as count increases: 100 concurrent coroutines each get
  1/100th of the CPU.

  Concurrent run_source() calls on the same NodusRuntime instance: Unsafe. NodusRuntime has no lock around run_source(). Each call overwrites self.last_vm
  (race condition). _host_functions and _python_registered_tools are read-only after construction (safe), but ToolRegistry._lock (an RLock) only protects
  tool-level operations. Concurrent executions that spawn subprocesses will accumulate handles in vm._spawned_handles, but only the last call's last_vm gets
  drained on reset. The documented model is: one run_source() at a time per instance.

  Multiple separate NodusRuntime instances: Independent. Each instance creates a fresh VM and ModuleLoader per call. No process-level global state in the
  core VM. Exception: get_default_workflow_runner() is a process-level singleton (_DEFAULT_RUNNER, runner.py:31), shared by all VM instances that call
  run_workflow() / resume_workflow() without explicit runner configuration. Multiple concurrent runtimes using the default runner share one
  WorkflowFrameworkRunner, protected by a single threading.Lock.

  Thread safety verdict:
  - Same NodusRuntime instance: Not safe for concurrent run_source().
  - Separate NodusRuntime instances: Safe for parallel execution, except for the shared default workflow runner.

  ┌─────────────────────────────────────────┬──────────────────────────────────┬────────────────────────────────────────────┐
  │                 Metric                  │              Limit               │             Behavior at limit              │
  ├─────────────────────────────────────────┼──────────────────────────────────┼────────────────────────────────────────────┤
  │ Coroutines per runtime                  │ Unbounded (deque)                │ Throughput per coroutine degrades linearly │
  ├─────────────────────────────────────────┼──────────────────────────────────┼────────────────────────────────────────────┤
  │ Concurrent run_source() on one instance │ 1 (no lock)                      │ last_vm race; undefined state              │
  ├─────────────────────────────────────────┼──────────────────────────────────┼────────────────────────────────────────────┤
  │ Runtime instances per process           │ Unbounded                        │ Parallel-safe (independent VMs)            │
  ├─────────────────────────────────────────┼──────────────────────────────────┼────────────────────────────────────────────┤
  │ Shared workflow runner                  │ 1 per process (global singleton) │ Thread-safe (Lock), but serialized         │
  └─────────────────────────────────────────┴──────────────────────────────────┴────────────────────────────────────────────┘

  Hard boundary: Single-threaded scheduler — coroutine throughput halves for every doubling of concurrent coroutine count. This is the binding limit, not
  coroutine count per se.

  Root cause: Python's GIL plus cooperative scheduling in a single thread means the runtime is inherently single-threaded for Nodus code. This is a design
  choice, not an implementation gap — concurrent I/O happens through subprocess_spawn (thread-backed) and channel drain, not by releasing the GIL during
  script execution.

  Upgrade path: For concurrent script execution across separate users, run one NodusRuntime instance per request (already the recommended pattern per the
  runbook). For compute parallelism within one script, subprocess_spawn escapes the GIL. True multi-threaded coroutine execution would require a fundamental
  scheduler redesign.

  ---
  4. Maximum Automation Depth

  Can a script run and trigger a follow-on script without host involvement? No. A script can call run_workflow() which executes steps sequentially within
  the same process and runtime. But scheduling a follow-on execution (starting a new runtime call after the current one finishes) requires host code. There
  is no exec_after() or script-spawned-script primitive.

  Can the runtime self-schedule work across time (e.g., "run this in 30 minutes")? No built-in self-scheduling. sleep(ms) suspends a coroutine cooperatively
  but requires the scheduler to stay alive — the process cannot exit and re-wake. workflow_wait(event_type, deadline_ms=...) can mark a run as "waiting"
  and a timeout will dead-letter it after the deadline, but this requires the host to run WorkflowFrameworkRunner.sweep() periodically. There is no
  schedule_at() or cron primitive inside the language.

  Can the runtime persist state across process restarts without application code? Conditionally. SQLiteWorkflowStore persists workflow run state durably;
  rehydrate_runs() recovers it. However, the get_default_workflow_runner() (the default used by run_workflow() in scripts) uses LocalWorkflowStore
  (file-backed JSON), not SQLite. The embedder must explicitly call configure_default_workflow_runner(backend="sqlite", ...) to get durable persistence.
  With that in place, state survives restarts without further application code.

  Is there a durable event queue? No. workflow_wait() records the waiting state in the store, but there is no queue that buffers incoming events between
  restarts. An event that arrives while the process is down is not captured anywhere by the runtime.

  Maximum duration of a single workflow: Bounded by storage policy, not by the runtime. LocalWorkflowStore has terminal_max_age_days = 30.0 (days after
  which old completed runs are ignored during scans). For SQLiteWorkflowStore there is no age limit. A workflow that workflow_wait()s for months will remain
  in waiting status indefinitely as long as the store is intact and the sweeper runs.

  ┌──────────────────────────────────┬───────────────────────────────────────────┬──────────────────────────────────────┐
  │            Capability            │           Available in language           │          Requires host code          │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Coroutine sleep (cooperative)    │ YES — sleep(ms)                           │ No                                   │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Multi-step workflow execution    │ YES — run_workflow()                      │ No (uses default runner)             │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Cross-restart persistence        │ Conditional — needs SQLite runner         │ configure_default_workflow_runner()  │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Event-driven resumption          │ YES — workflow_wait() + resume_workflow() │ Host must dispatch resume_workflow() │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Autonomous retry on step failure │ YES — @retry + sweeper                    │ Host must call sweep()               │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Self-scheduling across time      │ NO                                        │ Host must schedule sweep + trigger   │
  ├──────────────────────────────────┼───────────────────────────────────────────┼──────────────────────────────────────┤
  │ Triggering follow-on scripts     │ NO                                        │ Host must call run_source() again    │
  └──────────────────────────────────┴───────────────────────────────────────────┴──────────────────────────────────────┘

  Hard boundary: The runtime cannot trigger its own re-invocation. Everything beyond the current process lifetime requires the host to act — there is no
  built-in daemon, no event listener, no cron integration.

  Root cause: Deliberate design: Nodus is an embedded runtime, not a standalone daemon. The workflow framework provides the hooks for long-running
  automation (workflow_wait, sweep, rehydrate_runs), but wiring them into a persistent service is the host's responsibility. This keeps the core runtime
  small and embeddable.

  Upgrade path: nodus_lang_workflow's WorkflowFrameworkRunner is ready to be driven by a host service loop. The missing piece is a built-in service runner
  (a thread or asyncio task that calls sweep() on a timer) that starts automatically when the first run_workflow() call is made. This is a ~100-line
  addition with no design change required.

  ---
  5. Leverage Boundary

  Where the language adds the most leverage: Multi-step dependency-ordered agent workflows — the workflow/step/after/checkpoint DSL, @retry annotation,
  action tool / action agent in goals, and the tool registry compress what would be 200+ lines of Python orchestration boilerplate into 20–30 lines of
  declarative Nodus.

  Where the language stops adding leverage: Any program whose logic is primarily data transformation, text processing, or numerical computation at scale —
  the multiline expression restriction forces complex operations onto single lines, the absence of += and list comprehensions forces verbose manual
  accumulation, and the closure mutation workaround (quoted-key map for shared mutable state) adds cognitive overhead that erases the language's benefit
  over Python.

  The program type hardest to write despite being within stated scope: A stateful recursive data processor — for example, a JSON path evaluator or a schema
  validator — because it requires character-level string access (no ord()/chr() builtin, no confirmed s[i] indexing), mutable accumulated state across
  recursive calls (closure mutation blocked), and expressions that naturally span multiple lines (single-line restriction).

  ---
  Summary: Hard Limits Table

  ┌──────────────┬────────────────────────────────────────────┬─────────────────────────────────┬─────────────────────────────────────────────────────┐
  │  Dimension   │                 Hard Limit                 │           Root Cause            │                    Upgrade Path                     │
  ├──────────────┼────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Workload     │ 200ms wall-clock (CLI) / 10M instructions  │ Python interpreter throughput   │ --time-limit N (CLI) or timeout_ms=None,            │
  │              │ (embedded, default)                        │ ~200K instr/sec; no JIT         │ max_steps=None (embedded)                           │
  ├──────────────┼────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Complexity   │ Expression nesting depth 50                │ _MAX_PARSE_DEPTH guard in       │ Raise constant; no design change needed             │
  │              │                                            │ parser.py:109                   │                                                     │
  ├──────────────┼────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Concurrency  │ Single-threaded scheduler; one             │ GIL + cooperative scheduler; no │ One instance per concurrent user; subprocess_spawn  │
  │              │ run_source() at a time per instance        │  lock on run_source()           │ for compute parallelism                             │
  ├──────────────┼────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Automation   │ Cannot self-schedule across process        │ Embedded design; no built-in    │ Add auto-starting sweep thread on first             │
  │ depth        │ lifetime; default runner uses non-durable  │ daemon or event listener        │ run_workflow(); change default runner to SQLite     │
  │              │ local store                                │                                 │                                                     │
  ├──────────────┼────────────────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────────────────────────┤
  │ Leverage     │ Stops at stateful text/data processing     │ Multiline restriction + no += + │ Lift newline-as-statement-terminator from parser;   │
  │ ceiling      │ programs                                   │  closure mutation workaround    │ allow closures to assign outer let                  │
  └──────────────┴────────────────────────────────────────────┴─────────────────────────────────┴─────────────────────────────────────────────────────┘

  ---
  Single Most Actionable Upgrade

  Lift the newline-as-statement-terminator restriction in the parser.

  The specific limit it removes: the inability to write multi-line expressions prevents any function call, list literal, or method chain from spanning more
  than one line. This forces complex data construction into unreadable single lines and is the primary reason non-trivial programs (>50 lines of logic)
  become harder to maintain than equivalent Python — eliminating the leverage advantage that justifies using the language at all.

  The specific mechanism: parser.py's expression parser treats a newline as the end of a statement unless the parser is inside parentheses, brackets, or
  braces at parse depth > 0. A partially-parsed argument list or binary expression that reaches a newline emits UnexpectedEndOfStatement rather than
  consuming the newline as whitespace.

  The specific change: track a counter of unclosed (, [, { delimiters in the lexer or parser. While that counter is > 0, emit newline tokens as whitespace
  (skip them) rather than as statement terminators. This is how Python, JavaScript, and Go handle the same problem. It would simultaneously fix: multi-line
  function arguments, multi-line list/map literals, multi-line binary expressions, and multi-line method chains — raising Dev Leverage from 3 toward 4,
  raising the practical program complexity ceiling, and making the closure mutation workaround (a multi-line map update) ergonomically viable.
