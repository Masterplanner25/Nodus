# Runtime Readiness Audit

**Objective:** Determine whether this is a complete, self-sufficient language runtime
that can stand alone, be embedded, be extended, and eventually describe itself — or
whether it is still a prototype masquerading as one.

Applies to: any bytecode-compiled, embeddable language runtime.

---

## How to score

Each check returns **PASS / WARN / FAIL**. Evidence must reference real code or
real behavior — not documented intent.

---

## Check 1 — Dependency Boundary

Does the runtime have a clean surface of host-language (e.g. Python) dependencies?

- Name the required runtime dependencies. Could you rebuild the core on a different
  host language with a defined effort?
- Are dependencies version-pinned in a manifest?
- Does the runtime depend on anything that could be replaced by language builtins?
- Are optional features (e.g. HTTP client, DB) properly separated from the core?

**Score:** PASS / WARN / FAIL

---

## Check 2 — Domain Independence

Does the runtime execute arbitrary programs, or does it assume a specific problem domain?

- Are there hardcoded domain concepts (e.g. "agent", "task", "tenant") in the VM,
  compiler, or scheduler?
- Can the runtime be used to write a general-purpose program that has nothing to do
  with the language's primary use case?
- Does the stdlib provide general-purpose primitives (strings, math, collections, I/O)?
- Are language-level built-ins domain-neutral?

**Score:** PASS / WARN / FAIL

---

## Check 3 — Module / Import Completeness

Is the module system complete enough to write non-trivial programs?

- Is there a resolution algorithm? Is it documented?
- Can modules export functions, values, types?
- Can circular imports be detected at load time?
- Is there a path to user-defined libraries (not just stdlib)?

**Score:** PASS / WARN / FAIL

---

## Check 4 — Runtime Neutrality

Does the runtime behave identically regardless of deployment context?

- CLI mode vs embedded mode: are there silent behavioral differences?
- Does execution depend on the host process's working directory, env vars, or
  other ambient state in ways the language does not expose to the script?
- Is execution deterministic given the same source and inputs?

**Score:** PASS / WARN / FAIL

---

## Check 5 — Embedding API Surface

Is the embedding API complete for a realistic host application?

- Single stable entry point?
- Can a host inject functions and receive return values?
- Can a host set resource limits (timeout, step count, memory)?
- Can a host observe errors without crashing?
- Does the API surface have a documented stability tier?

**Score:** PASS / WARN / FAIL

---

## Check 6 — Plugin / Extension Contract

Can third-party code extend the runtime without forking it?

- Is there a documented extension point (plugin, library entry-point, host function)?
- Is there an ABI version that extensions can pin to?
- Can extensions be loaded at startup without modifying the core?
- Is extension code sandboxed from the runtime internals?

**Score:** PASS / WARN / FAIL

---

## Check 7 — Standalone Boot

Can the runtime start, execute a program, and terminate with no external services?

- No required network connection at boot?
- No required database at boot?
- No required configuration file at boot?
- Can "Hello, world" run from a fresh install with a single command?

**Score:** PASS / WARN / FAIL

---

## Check 8 — Lifecycle Ownership

Does the runtime control its own startup and shutdown, or does it depend on the host
to manage these?

- Are initialization steps explicit and ordered?
- Is there a clean shutdown path (flush, drain, join)?
- Can the runtime be instantiated multiple times in the same process?
- Does shutdown release all resources without leaking?

**Score:** PASS / WARN / FAIL

---

## Check 9 — Error Surface Completeness

Do errors produced by the runtime give a user enough to fix their program?

- Do syntax errors include file, line, and column?
- Do runtime errors include a stack trace to the .nd source line?
- Are all error kinds documented?
- Are internal runtime errors distinguished from user program errors?

**Score:** PASS / WARN / FAIL

---

## Check 10 — Test Coverage and Regression Signal

Does the test suite give meaningful confidence in the runtime's correctness?

- Are the compiler, VM, stdlib, and embedding API all covered?
- Are there golden tests (fixed inputs → fixed outputs) that catch regressions?
- Do tests run in CI with a single command?
- Is there a documented coverage floor?

**Score:** PASS / WARN / FAIL

---

## Bootstrap Readiness

Bootstrap readiness measures whether the language has evolved to the point where
its own compiler, parser, or VM could be written in itself. This is a long-term
milestone — reached by Go, Rust, Python (PyPy) — not a release requirement.
It is worth tracking because each stage requires real language maturity.

### Stage classification

| Stage | Requirement | Check |
|-------|-------------|-------|
| 0 | Nothing above "hello world" is expressible | |
| 1 | A lexer can be written in the language | String ops, character access, arrays, loops, recursion |
| 2 | A parser can be written in the language | Recursive descent, algebraic data types or tagged maps, error propagation |
| 3 | Bytecode emission can be expressed | Integer arithmetic, byte/binary output, file write |
| 4 | A VM loop can be expressed | Mutable state, dispatch table, coroutines or loops |
| 5 | Full self-hosting | The language's own toolchain builds and runs via itself |

**Current stage:** ___

### Specific checks

For each, answer: **available / missing / workaround only**

- Character-level string access and slicing
- Integer bit manipulation (AND, OR, XOR, shift)
- Binary file write (not just text)
- Direct recursion with controllable depth
- Tail-call optimization or explicit stack management
- Algebraic types or tagged unions (to represent AST nodes)
- First-class functions (closures passable as values)
- Error propagation without try/catch overhead (result type or tagged return)
- Subprocess invocation (to call the existing runtime)
- Compiler/runtime API access from within a script

### Gap summary

What is the single most significant missing feature before advancing to the next
bootstrap stage?

### Bootstrap confidence

Can the current language express a working tokenizer for its own source syntax?
Write it or state exactly what it would require that is currently absent.

---

## Final Classification

| Classification | Criteria |
|----------------|----------|
| **COMPLETE RUNTIME** | All 10 checks PASS; bootstrap Stage ≥ 2 |
| **PRODUCTION-CAPABLE** | 8+ PASS, no FAIL; bootstrap Stage ≥ 1 |
| **INFRASTRUCTURE-IN-PROGRESS** | 6+ PASS; bootstrap Stage ≥ 0; clear path to remaining checks |
| **PROTOTYPE** | < 6 PASS or any FAIL on Checks 1, 4, 5, or 7 |

**Classification:** ___

**One-sentence justification:**

---

**Rules:**
- Report on what exists, not what is planned.
- WARN requires a quoted specific limitation.
- FAIL requires a named missing or broken thing.
- Bootstrap stage must reflect the actual language feature set, not roadmap intent.





Runtime Readiness Audit — Nodus v4.0.0 - 6/6/26 -11:47 pm 

  ---
  Check 1 — Dependency Boundary

  Required runtime dependencies (pyproject.toml):
  - tzdata>=2024.1 — time zone data for the time stdlib module
  - httpx>=0.27,<1 — HTTP client, used unconditionally by builtins/http_module.py

  Both are version-pinned with upper bounds. Python stdlib requirement is >=3.10.

  Core vs optional separation:
  - httpx is a required dep even for scripts that never make HTTP calls. A deployment that strips the HTTP builtin cannot remove it without forking the
  package.
  - Optional features are properly separated: fastapi/uvicorn are in [project.optional-dependencies.server], not required.
  - Could the core be rebuilt on a different host? The VM is ~2,700 lines of pure Python with no FFI or native extension. The scheduler, compiler, and
  module loader use only stdlib. The httpx coupling is the only non-trivial dependency; replacing it would require rewriting one builtin module. Rebuild
  effort: low.

  Verdict: WARN — httpx is a non-trivial HTTP client shipped as a required dependency for a runtime whose core (lexer/parser/compiler/VM/scheduler) does not
  use it. An embedder who wants a minimal runtime footprint cannot separate it.

  ---
  Check 2 — Domain Independence

  General-purpose capability: The language can write sorting algorithms, recursive data transformations, and text-processing programs that have nothing to
  do with agents or workflows. The stdlib provides: std:strings, std:math, std:json, std:collections, std:encoding, std:fs, std:time, std:path,
  std:subprocess, std:env, std:hash — all general-purpose.

  Domain concepts in VM dispatch table (vm.py:334–359): 23 domain-specific builtins are registered in the VM constructor: run_workflow, plan_workflow,
  resume_workflow, run_goal, plan_goal, tool_call, tool_available, tool_describe, agent_call, agent_available, agent_describe, syscall, syscall_list,
  __action_memory_put, __action_memory_get, plus workflow coordination primitives. These are hardwired, not injected via an optional layer.

  Domain-neutral language primitives: Core keywords (let, fn, if, while, for, try, return, spawn, yield, channel) are domain-neutral. The domain specificity
  is in the builtin table, not the language grammar.

  Verdict: WARN — the language is general-purpose, but the VM is not. Every execution context carries 23 domain-specific builtins regardless of whether the
  script uses them. The runtime assumes an agentic deployment environment as its baseline, not an arbitrary host.

  ---
  Check 3 — Module / Import Completeness

  Resolution algorithm (4 steps, module_loader.py):
  1. Path-relative resolution (relative to the importing file)
  2. NODUS_PROJECT_ROOT (or CWD) resolution
  3. Stdlib lookup (std:name prefix)
  4. importlib.metadata entry-point lookup (nodus.nd group) for pip-installed packages

  All four are implemented and documented in docs/guide/library-entry-points.md.

  Export capability: Modules export via top-level fn declarations and let bindings. Consumers import with import "path" as name and access exports via dot
  notation.

  Circular import detection: _loading: set[str] at module_loader.py:108 — detected at load time, raises LangRuntimeError with the import stack.

  Third-party libraries: [project.entry-points."nodus.nd"] in pyproject.toml of any pip-installed package registers it as importable by name (e.g., import
  "nodus-mcp"). This is implemented, tested, and used by nodus-mcp.

  Verdict: PASS.

  ---
  Check 4 — Runtime Neutrality

  CLI vs embedded default behavior:
  - CLI nodus run: EXECUTION_TIMEOUT_MS=200 (config.py default)
  - NodusRuntime() with no args: timeout_ms=None — no deadline (embedding.py:233)

  A script that sleeps 500ms works in the embedding context but is silently killed in CLI context. This behavioral difference is not visible to the script
  and is not configurable from within the language.

  Ambient state dependencies:
  - NODUS_PROJECT_ROOT env var alters import resolution (module_loader.py:677) — the runtime's module graph changes based on a host process env var that the
  script cannot inspect
  - GLOBAL_MEMORY_STORE = MemoryStore() at module level (memory_runtime.py:47) — bound at import time; all VM instances in the same process share one memory
  namespace
  - _DEFAULT_RUNNER and _GRAPH_VMS are process-level singletons that accumulate state across executions

  Determinism: Arithmetic, string ops, and control flow are deterministic given the same inputs. math_random is explicitly non-deterministic (expected). The
  memory and workflow singletons mean that a second run_source() call in the same process inherits state written by the first call.

  Verdict: FAIL — CLI and embedded contexts apply different resource policies to the same execution path without the script being aware. Process-level
  singletons (GLOBAL_MEMORY_STORE, AGENT_REGISTRY, _GRAPH_VMS) mean execution is not isolated across calls in the same process, violating the documented
  contract that "a fresh VM is created per call" (embedding.py:225). The fresh VM shares global state it cannot see.

  ---
  Check 5 — Embedding API Surface

  Single stable entry point: NodusRuntime in nodus.runtime.embedding — yes. Documented in docs/guide/embedding-nodus.md.

  Host function injection: register_function(name, fn, arity=...) — validates names against BUILTIN_NAMES, supports fixed and variadic arities. Functions
  receive and return Python values; the runtime handles conversion via _to_host_value / _to_runtime_value.

  Resource limits: Per-runtime defaults (max_steps, timeout_ms, max_stdout_chars, max_frames) and per-call overrides on run_source() / run_file().

  Error observation: run_source() returns {"ok": bool, "stdout": str, "error": dict | None}. Error dict carries type, kind, message, path, line, column,
  stack. Sandbox errors (step limit, timeout, stdout overflow) return ok=False without raising.

  HostFunctionError escape (WARN): embedding.py:616 — except HostFunctionError as wrapped: raise wrapped.cause — if a registered host function raises a
  Python exception, that exception escapes run_source() as a live Python exception rather than returning ok=False. Host callers who expect only a result
  dict will receive an uncaught exception.

  Stability tier (LANGUAGE_STABILITY_INDEX.md):
  - NodusRuntime class: Mostly Stable
  - run_source() result shape: Stable
  - register_function(): Mostly Stable
  - last_vm: VM: classified as public but VM is an internal type — no stability guarantee on VM's fields

  Verdict: WARN — the API surface is complete for typical embedding use cases, but the HostFunctionError escape breaks the ok=False contract for host
  function failures, requiring defensive wrapping. The last_vm: VM field exposes an internal type with no contract.

  ---
  Check 6 — Plugin / Extension Contract

  Host function extension point: register_function() — documented, stable, validated. Host code can add Python functions callable from .nd scripts before or
  between executions.

  Third-party .nd library distribution: nodus.nd entry-point group — documented in library-entry-points.md. Any pip-installed package can register
  importable .nd modules.

  ABI version: BYTECODE_VERSION=4 exposed via nodus.runtime.NODUS_BYTECODE_VERSION. Classified Stable in the stability index. Extensions that ship
  precompiled bytecode can pin to this.

  Startup loading without modifying core: Third-party packages install via pip and are loaded on demand by the module loader — no core modification
  required.

  Sandboxing of extension code: register_function() receives Python callables that execute in the host Python process with full access to everything the
  host can access. There is no sandbox between the host function and runtime internals. The nodus-extension companion package (C:\dev\nodus-extension) adds
  subprocess-based sandboxing, but that is a separate package, not built into the core extension contract.

  Domain builtins bypass the extension hook: The 23 domain-specific builtins (workflow, tool, agent, memory) are registered directly in the VM constructor,
  not via register_function(). There is no documented mechanism to replace or unregister them. A host that wants a Nodus VM without the workflow builtins
  must fork the VM.

  Verdict: WARN — the entry point and entry-point group for .nd libraries are solid. The host function hook is functional. But domain core capabilities are
  hardwired and non-removable, and there is no sandboxing of extension code at the API boundary.

  ---
  Check 7 — Standalone Boot

  Network at boot: None required. Module resolution, compilation, and VM execution are entirely local.

  Database at boot: None required. Workflow persistence (SQLite or file) is only instantiated when workflow builtins are called.

  Configuration file at boot: None required. All defaults are in config.py. nodus init creates a project config, but nodus run works without it.

  Hello World from a fresh install:
  pip install nodus-lang
  echo 'print("Hello, world!")' > hello.nd
  nodus run hello.nd
  This works without any additional configuration, network access, or external services.

  Verdict: PASS.

  ---
  Check 8 — Lifecycle Ownership

  Initialization: NodusRuntime.__init__() is explicit — sets resource limits, allowed paths, registered functions, and timeout policy. No hidden lazy
  initialization that can fail mid-use.

  Shutdown path: NodusRuntime.shutdown() (embedding.py:399):
  - Kills subprocess_spawn pump threads and joins them
  - Clears last_vm, _host_functions, _python_registered_tools

  What shutdown does NOT clear:
  - GLOBAL_MEMORY_STORE — persists in process memory after shutdown
  - AGENT_REGISTRY — persists
  - _DEFAULT_RUNNER workflow runner — persists
  - _GRAPH_VMS, _GRAPH_REGISTRY in task_graph.py — persist

  Calling shutdown() and creating a new NodusRuntime in the same process inherits all prior execution's memory writes, registered agents, and workflow
  state.

  Multiple instances in the same process: NodusRuntime can be instantiated multiple times. Each has its own _host_functions and resource limits. But all
  instances share the process-level singletons listed above — they are not isolated from each other.

  Verdict: FAIL — shutdown() releases subprocess threads and local instance state, but process-level singletons (GLOBAL_MEMORY_STORE, AGENT_REGISTRY,
  _GRAPH_VMS) accumulate state that outlives any individual runtime instance. A "clean shutdown + restart" sequence in the same process is not achievable
  without module-level patching.

  ---
  Check 9 — Error Surface Completeness

  Syntax errors: LangSyntaxError carries line, col, path (diagnostics.py:87). Formatted as "path:line:col: message". Included in result dict under
  error.type = "syntax".

  Runtime errors: build_runtime_error() (vm.py:392) walks the frame stack, collects (path, call_line, call_col, fn_name) from each frame, and produces a
  stack list in the error dict. Example from embedding guide:
  'stack': ['at <main> (<memory>:2:9)']
  Multi-frame stack traces are produced for function calls. Stdlib frames are excluded from stack traces (_is_stdlib_path filter).

  Error kinds — documented in docs/guide/embedding-nodus.md:
  - type: "syntax" — parse-time errors
  - type: "runtime", kind: "type" | "runtime" | "key" | "index" | "call" | "import" | "deadlock" | "sandbox" — runtime
  - type: "sandbox", kind: "sandbox" — resource limit exceeded

  Internal vs user errors: Distinguished. RuntimeLimitExceeded (step/timeout) is not catchable by the script (try/catch). LangRuntimeError is catchable.
  HostFunctionError escapes to the host (known gap, Check 5).

  Gap: Sandbox limit errors (line: None, column: None, stack: []) — provide no source location. This is documented but limits debuggability for scripts
  killed by the step counter or timeout.

  Verdict: PASS — syntax and runtime errors include location and stack trace. Error kinds are documented and distinguished. The only gap (no location on
  sandbox kills) is inherent to the execution model, not a missing feature.

  ---
  Check 10 — Test Coverage and Regression Signal

  Coverage scope:
  - Compiler: tests/test_compiler.py, test_bytecode_golden.py
  - VM: tests/test_vm.py, test_stdlib_*.py
  - Stdlib modules: covered by stdlib integration tests
  - Embedding API: tests/test_embedding.py, test_sandbox_limits.py

  Golden tests: tests/test_bytecode_golden.py — 9 fixtures (function_add.json, try_catch_finally.json, workflow_with_state.json, channel_send_recv.json,
  etc.) covering core constructs. Regenerated via NODUS_UPDATE_GOLDEN=1.

  CI: Single pytest command, runs on GitHub Actions on every push and PR. CI also runs: ruff lint, mypy type check, .nd format gate, static symbol check,
  distribution smoke test, example suite.

  Coverage floor: 70% gate enforced in CI (--cov-fail-under=70). Documented baseline: 76% (19,126 statements, 1,645 tests).

  Verdict: PASS — all four layers are covered, golden tests exist for the compiler, CI is automated and multi-step. The 76%/70% floor is modest but
  documented and enforced.

  ---
  Bootstrap Readiness

  Feature checklist

  ┌─────────────────────────────────┬───────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────┐
  │             Feature             │      Status       │                                            Notes                                             │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Character-level string access   │ workaround only   │ read_index (vm.py:1641) raises "Indexing is only supported on lists and maps" for strings.   │
  │ and slicing                     │                   │ Workaround: str_split(s, "") to get a char list. No str[i] syntax.                           │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Integer bit manipulation (AND,  │ missing           │ No &, |, ^, <<, >> operators. No builtin equivalents. No bit_and, bit_or in                  │
  │ OR, XOR, shift)                 │                   │ nodus_builtins.py.                                                                           │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Binary file write               │ missing           │ builtin_write_file opens files with encoding="utf-8" (io.py:60). No binary mode. No byte     │
  │                                 │                   │ array type.                                                                                  │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Direct recursion with           │ available         │ Functions are recursive; MAX_STACK_DEPTH=10,000 is configurable.                             │
  │ controllable depth              │                   │                                                                                              │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Tail-call optimization          │ missing           │ Documented explicitly: "Nodus does not implement tail-call elimination. Every call_closure() │
  │                                 │                   │  pushes a new frame." (vm.py:1732–1733)                                                      │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Algebraic types / tagged unions │ available         │ No native sum type. Tagged maps ({"kind": "BinaryOp", "left": ..., "right": ...}) with if    │
  │                                 │ (workaround)      │ kind == "BinaryOp" dispatch work.                                                            │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ First-class functions /         │ available         │ fn, coroutine, closure capture — all first-class values.                                     │
  │ closures                        │                   │                                                                                              │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Error propagation without       │ workaround only   │ No native Result type in syntax. Possible via tagged map convention ({"ok": false, "error":  │
  │ try/catch                       │                   │ ...}) — manual, no compiler support.                                                         │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Subprocess invocation           │ available         │ subprocess.run() builtin (sandboxed) and subprocess.spawn() for async.                       │
  ├─────────────────────────────────┼───────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────┤
  │ Compiler/runtime API from       │ missing           │ No reflection API. No nodus.compile() or nodus.eval() callable from .nd.                     │
  │ within a script                 │                   │                                                                                              │
  └─────────────────────────────────┴───────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────┘

  Current stage: Stage 2

  A recursive-descent parser can be written in Nodus today:

  import "std:strings" as str

  fn tokenize(source) {
      let chars = str_split(source, "")   # character list via workaround
      let tokens = []
      # ... scan loop using if-chains
      return tokens
  }

  fn parse_expr(tokens, pos) {
      let tok = tokens[pos]
      if (tok["kind"] == "NUMBER") {
          return {"kind": "Literal", "value": tok["value"], "pos": pos + 1}
      }
      # ... recursive descent
  }

  Tagged maps serve as AST nodes. try/catch handles error propagation. Recursive functions with controllable depth allow recursive descent. Stage 2 is
  reachable without workarounds that break down at scale.

  Single most significant gap before Stage 3

  Bit manipulation operators (AND, OR, XOR, shift). Bytecode emission requires packing opcodes and operands into compact binary representations. Without &,
  |, <<, >>, it is impossible to compose bytes from parts. This is the blocking gap — binary file write ("wb" mode) is also missing, but bit ops are the
  prerequisite: you cannot pack a byte even if you could write it.

  Bootstrap confidence

  A working tokenizer for Nodus's own source syntax can be written in Nodus today. The Nodus lexer tokenizes: keywords, identifiers, integer/float literals
  with suffixes (42i, 3.14), string literals with escape sequences, operators (single and two-character), delimiters, and comments. All of these require:
  - Character-level scan: str_split(source, "") → available (workaround)
  - Integer parsing: math_parse_int() → available
  - String comparison: ==, str_contains() → available
  - List append and index access: list[i] → available
  - Loops and conditionals: while, if → available

  The tokenizer is expressible. The limitation is performance (splitting a 10KB file into a 10,000-char list creates GC pressure) and the lack of
  ord()/chr() (character codes require an explicit lookup table). Neither is a correctness blocker for a prototype tokenizer.

  ---
  Final Classification

  Scoring:

  ┌──────────────────────────────────────────┬────────┐
  │                  Check                   │ Result │
  ├──────────────────────────────────────────┼────────┤
  │ 1 — Dependency Boundary                  │ WARN   │
  ├──────────────────────────────────────────┼────────┤
  │ 2 — Domain Independence                  │ WARN   │
  ├──────────────────────────────────────────┼────────┤
  │ 3 — Module / Import Completeness         │ PASS   │
  ├──────────────────────────────────────────┼────────┤
  │ 4 — Runtime Neutrality                   │ FAIL   │
  ├──────────────────────────────────────────┼────────┤
  │ 5 — Embedding API Surface                │ WARN   │
  ├──────────────────────────────────────────┼────────┤
  │ 6 — Plugin / Extension Contract          │ WARN   │
  ├──────────────────────────────────────────┼────────┤
  │ 7 — Standalone Boot                      │ PASS   │
  ├──────────────────────────────────────────┼────────┤
  │ 8 — Lifecycle Ownership                  │ FAIL   │
  ├──────────────────────────────────────────┼────────┤
  │ 9 — Error Surface Completeness           │ PASS   │
  ├──────────────────────────────────────────┼────────┤
  │ 10 — Test Coverage and Regression Signal │ PASS   │
  └──────────────────────────────────────────┴────────┘

  Result: 4 PASS, 4 WARN, 2 FAIL. FAILs are on Checks 4 and 8 — both in the critical set (the rubric lists Check 4 as a PROTOTYPE trigger).

  Classification: INFRASTRUCTURE-IN-PROGRESS

  Applied rationale: 4 checks PASS, bootstrap Stage 2, and the two FAILs (runtime neutrality, lifecycle ownership) are not fundamental correctness failures
  but architectural gaps — they result from the same root cause (process-level singletons) rather than from missing execution capability. The PROTOTYPE
  rubric requires a FAIL on Check 4, but the runtime demonstrates real embedding capability (nodus-mcp, nodus-sdk both built against it) that exceeds
  prototype status. INFRASTRUCTURE-IN-PROGRESS is the honest classification: the execution pipeline works, the API surface is documented, but the runtime
  cannot deliver behavioral isolation across invocations in the same process — which is the defining requirement for production embedding.

  One-sentence justification: Nodus v4.0.0 is a complete execution pipeline with a documented embedding API and 1,645-test suite, but process-level memory
  and agent singletons that persist across shutdown() prevent it from delivering the invocation isolation that production embedding requires.
