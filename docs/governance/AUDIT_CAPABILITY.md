# System Capability Audit

**Objective:** Classify this language runtime along five axes to produce an accurate,
evidence-based picture of what it actually is — not what it aspires to be.

Applies to: any language runtime at a point where the feature set is substantially
defined.

---

## Classification Axes

Score each axis on a 1–5 scale. Evidence must be specific.

---

### Axis 1 — Execution Capability

What class of programs can be expressed and executed?

| Level | Description |
|-------|-------------|
| 1 | Expression evaluation only; no control flow, no state |
| 2 | Scripting: sequential execution, conditionals, loops, functions |
| 3 | Structured programming: modules, imports, error handling, closures |
| 4 | Concurrent / async: coroutines, channels, task scheduling |
| 5 | Distributed / orchestrated: persistent workflows, event-driven resumption, cross-process coordination |

**Score:** ___ / 5

**Evidence:** Name the specific features that justify this score. If the score is
limited by a missing feature, name it.

---

### Axis 2 — Reliability

What are the guarantees around correctness and predictability?

| Level | Description |
|-------|-------------|
| 1 | No guarantees; errors may be silent or cause undefined behavior |
| 2 | Errors surface predictably; no undefined behavior in user code |
| 3 | Resource limits enforceable; execution is bounded; cleanup on error |
| 4 | Persistent execution with durability guarantees; crash recovery |
| 5 | Formal correctness properties; verified invariants; audit trail |

**Score:** ___ / 5

**Evidence:** What is the highest reliability guarantee the runtime makes? What breaks it?

---

### Axis 3 — Autonomy

Can the runtime drive execution with minimal host involvement after setup?

| Level | Description |
|-------|-------------|
| 1 | The host must drive every step |
| 2 | The runtime drives execution of a single script to completion |
| 3 | The runtime manages concurrent tasks and their scheduling |
| 4 | The runtime can suspend, persist, and resume across process restarts |
| 5 | The runtime can orchestrate long-horizon workflows with external event triggers |

**Score:** ___ / 5

**Evidence:**

---

### Axis 4 — Developer Leverage

What is the ratio of capability to complexity for a developer using this runtime?

| Level | Description |
|-------|-------------|
| 1 | High complexity; limited capability over writing host-language code directly |
| 2 | Useful shorthand for simple cases; breaks down at moderate complexity |
| 3 | Clear advantage for its target use case; onboarding friction is low |
| 4 | Significantly reduces time-to-working-system for non-trivial programs |
| 5 | Enables programs that would be substantially harder in the host language |

**Score:** ___ / 5

**Evidence:**

---

### Axis 5 — Bootstrap Readiness

Can the language describe its own toolchain? (See also: `AUDIT_RUNTIME_READINESS.md §Bootstrap Readiness`)

| Level | Description |
|-------|-------------|
| 1 | Cannot yet express a tokenizer for its own syntax |
| 2 | Can express a tokenizer; parser would require missing features |
| 3 | Can express a parser; compiler output requires missing primitives |
| 4 | Can express a compiler; VM loop requires missing features |
| 5 | Full self-hosting is feasible with current feature set |

**Score:** ___ / 5

**Evidence:** Name the one feature that is the hard gate on the next stage.

---

## Overall Capability Profile

```
Execution:    [1][2][3][4][5]
Reliability:  [1][2][3][4][5]
Autonomy:     [1][2][3][4][5]
Dev Leverage: [1][2][3][4][5]
Bootstrap:    [1][2][3][4][5]
```

---

## Ceiling

What is the most complex real program that can be written in this language today?
Describe it in terms of lines of code, concurrency, data complexity, and external
integrations. This is the current ceiling, not the intended ceiling.

---

## Constraint

The single bottleneck limiting capability growth. One sentence. Name the specific
missing feature, behavioral gap, or design decision that, if fixed, would raise the
most axes simultaneously.

---

## System Class

Given the profile above, what is this system most accurately described as?

Pick one:

- **Expression evaluator** — Axes 1–2 only; not a general-purpose language
- **Scripting language** — Axes 1–3; suitable for automation and glue code
- **Embedded DSL** — Optimized for a specific domain; limited general use
- **Orchestration runtime** — Axes 1–4; suitable for agent/workflow coordination
- **General-purpose runtime** — All five axes ≥ 3; usable for arbitrary programs

**Classification:** ___

---

**Rules:**
- Scores must be supported by a specific named feature, file, or behavior.
- A score of 5 requires evidence of the level, not just the absence of obvious gaps.
- Do not score based on roadmap. Score what exists.



Nodus v4.0.0 — System Capability Audit --6/6/26-10:39pm 

  ---
  Axis 1 — Execution Capability: 5 / 5

  Every level is covered with direct code evidence:

  - Level 2: If, While, For, ForEach, FnDef, FnExpr, string interpolation — all in ast_nodes.py and compiled by compiler.py.
  - Level 3: Import, ExportList, ModuleAlias (module system), Closure type in vm.py, TryCatch/Throw AST nodes, finally blocks with guaranteed execution
  (I-VM-06).
  - Level 4: coroutine(), spawn(), channel(), send(), recv(), close() as first-class VM builtins; round-robin Scheduler in runtime/scheduler.py with
  1000-instruction budget per coroutine and timer-heap for sleep.
  - Level 5: WorkflowDef / GoalDef AST nodes; builtin_workflow_wait() suspends on external events; builtin_resume_workflow() re-enters from an external
  caller; SQLiteWorkflowStore provides cross-process coordination; WorkflowFrameworkRunner.rehydrate_runs() recovers after crash.

  Limiting note: true distributed coordination across physical nodes requires the companion nodus-a2a library. Within a single host, all Level 5 features
  are present in-tree.

  ---
  Axis 2 — Reliability: 4 / 5

  Highest guarantee: durable workflow persistence with crash recovery via SQLiteWorkflowStore + rehydrate_runs().

  Confirmed guarantees:
  - No undefined behavior in user code — I-VM-01 through I-VM-08 (stack balance, frame balance, structured throw values preserved, O(1) dispatch).
  - Resource limits: timeout_ms (wall-clock deadline), max_steps (instruction count), max_frames (call depth), MAX_STDOUT_CHARS — all enforced in
  vm.py::record_instruction and tooling/sandbox.py.
  - finally always executes across return, throw, and normal exit (I-VM-06; verified by test suite).
  - Deadlock detection: scheduler.py raises LangRuntimeError("deadlock", ...) when all live coroutines are blocked on recv() with no possible sender.
  - Subprocess cleanup: _drain_spawned() kills child processes and joins pump threads on reset() / shutdown() (EMBED-003).

  What breaks Level 5: The invariants doc is authored documentation, not machine-checked proofs; TEST_GAP_BACKLOG.md acknowledges gaps. A VM crash
  mid-coroutine outside a registered workflow run cannot be recovered — only workflow runs tracked by WorkflowFrameworkRunner and backed by SQLite survive
  process restart. The 200ms default deadline trap (EMBED-001) is a known footgun for embedders.

  ---
  Axis 3 — Autonomy: 4 / 5

  - Level 2: NodusRuntime.run_source() drives a script to completion, returns ok/error/stdout.
  - Level 3: Scheduler.run_loop() manages N concurrent coroutines autonomously — spawn, sleep, channel-block, wake, complete — with no host involvement
  after the initial call.
  - Level 4: SQLiteWorkflowStore persists workflow run state durably; rehydrate_runs() resumes across process restarts.
  - Level 5 boundary: workflow_wait(event_type, ...) suspends a workflow step pending an external event; resume_workflow(run_id, checkpoint, payload)
  re-enters it from an external caller. The mechanism for Level 5 is present.

  What keeps it at 4: WorkflowFrameworkRunner.sweep() must be driven by a host-side timer or daemon thread — the runtime has no self-starting heartbeat.
  External event delivery requires the host to call resume_workflow; there is no built-in event listener or polling loop.

  ---
  Axis 4 — Developer Leverage: 3 / 5

  Strong case for the target use case:
  - Workflow DSL (step b after a { ... }, checkpoint) collapses dependency-ordered execution into declarative syntax.
  - Goal DSL (action tool "name", action agent "name") abstracts AI-native orchestration.
  - 24-module stdlib: std:http, std:subprocess, std:hash, std:json, std:retry, std:circuit_breaker, std:effects, std:collections, std:identity, std:memory,
  std:tool, std:agent and more.
  - Tool registry (tool.register with dotted names, schema, versioning) abstracts plugin integration.
  - NodusRuntime embedding API with on_error hooks and ToolRegistry is a clean host integration point.

  What keeps it at 3 — the CLAUDE.md "quirks" section names 15+ non-obvious footguns that burn time on every non-trivial program:
  - No multiline expressions ([1,\n2] is a syntax error).
  - No += operator; closure mutation requires {"count": 0i} map workaround.
  - print() is single-argument only; channel() is a builtin, not a module (import fails silently with wrong error).
  - run_workflow() returns maps, not records — bracket notation required.
  - 200ms default timeout kills any workflow sleeping cumulatively over 200ms.

  Onboarding friction is real, not low. Leverage is strong within the orchestration domain but friction-heavy for general-purpose programs.

  ---
  Axis 5 — Bootstrap Readiness: 3 / 5

  - Level 1 (tokenizer): Expressible. str_split, str_contains, index_of, last_index_of, loops, conditionals are all present. Index AST node and opcode
  exist, so s[i] string character access is likely available. A character-stream tokenizer can be written.
  - Level 2 (parser): Expressible. Recursive functions, lists as stacks, maps for symbol table state (via quoted-key mutation workaround). A recursive
  descent parser is plausible.
  - Level 3 (compiler): Expressible. The bytecode format is JSON-serializable (list of [opcode, operand?] maps), not binary. write_file exists. A compiler
  that emits the Nodus bytecode format as a list of maps can be written entirely in Nodus.

  Hard gate at Level 3 → 4: No access to OS-level timer primitives. The Scheduler depends on Python's time.sleep(), heapq, and deque — these are injected
  Python primitives, not things a Nodus-hosted VM can call for its own scheduler. A Nodus-in-Nodus tree-walk interpreter can handle synchronous execution
  but cannot implement the coroutine scheduler's sleep/wake model without host backing. A VM that omits concurrency could reach Level 4, but it would not be
  a faithful self-host.

  One feature that is the hard gate: no host-independent async timer — sleep() is a Python-backed syscall, so a Nodus-authored scheduler cannot yield
  control to real OS timers.

  ---
  Overall Capability Profile

  Execution:    [1][2][3][4][5]   ████████████████████  5
  Reliability:  [1][2][3][4][5]   ████████████████░░░░  4
  Autonomy:     [1][2][3][4][5]   ████████████████░░░░  4
  Dev Leverage: [1][2][3][4][5]   ████████████░░░░░░░░  3
  Bootstrap:    [1][2][3][4][5]   ████████████░░░░░░░░  3

  ---
  Ceiling

  The most complex real program expressible today: a 200–500 line multi-file agent orchestration system with 10–20 concurrent coroutines, SQLite-backed
  durable workflow state, per-step retry and circuit_breaker policies, outbound HTTP and subprocess calls, a versioned tool registry, goal-driven planning
  with a persistent memory namespace, event-driven resumption from external triggers (workflow_wait), and embedded as a Python FastAPI service via
  NodusRuntime. External integrations are real (HTTP, subprocesses, SQLite). Concurrency is cooperative and bounded. Checkpoint/resume across process
  restarts is functional.

  The ceiling on non-orchestration tasks is lower: a data-processing script of more than ~50 lines hits the multiline restriction and the closure-mutation
  workaround, making the code awkward relative to equivalent Python.

  ---
  Constraint

  The multiline expression restriction — the parser treats newlines as statement terminators, preventing any list literal, function argument list, or
  chained call from spanning multiple lines — is the single design decision that, if lifted, would simultaneously raise Dev Leverage (cleaner complex
  programs), Bootstrap (compiler output expressions become natural to write), and general program size ceiling, at no cost to Execution or Reliability.

  ---
  System Class

  Orchestration runtime

  All five axes score ≥ 3, which meets the letter of "General-purpose runtime," but the system is demonstrably designed for and excels at agent/workflow
  coordination. Its general-purpose surface (text processing, algorithms, data transformation) carries enough ergonomic friction that calling it
  general-purpose in practice overstates the developer experience. The correct classification is Orchestration runtime — Axes 1–4 are the load-bearing
  structure; Bootstrap (3) and Dev Leverage (3) are present but not the design goal.
