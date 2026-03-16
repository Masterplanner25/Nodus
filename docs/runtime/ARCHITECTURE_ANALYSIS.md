# Nodus Architecture Analysis

## 1. Executive Summary
Nodus is a bytecode-compiled, stack-based scripting runtime implemented in Python. It targets automation and orchestration use cases with real language features (control flow, functions, closures, lists/maps/records, imports/exports), plus runtime services (task graphs, workflows/goals, coroutines/channels, event tracing). The system is beyond a toy VM and sits in an early practical runtime stage with strong tooling but a compile-time module model that will limit scale until redesigned.

## 2. Current Architecture
Execution pipeline:
- `tokenize -> Parser.parse (AST) -> resolve_imports (module graph + alias map) -> Compiler.compile_program (bytecode + locs) -> optimize -> VM.run`

Source-to-runtime flow:
1. Tokenizer emits tokens with kind/val/line/col.
2. Recursive-descent parser builds AST dataclasses.
3. Import resolver loads modules, enforces exports, rewrites names to module-qualified globals, and flattens imported AST into one compilation unit.
4. Compiler lowers AST to tuple bytecode with parallel source-location table.
5. Optimizer performs constant folding, dead code removal, and jump simplification.
6. VM executes instructions with a value stack, call frames, globals, closures, and builtin registry.

Key subsystems:
- Front-end: `lexer.py`, `parser.py`, `ast_nodes.py`, `ast_printer.py`, `ast_serializer.py`
- Compilation: `compiler.py`, `optimizer.py`, `symbol_table.py`
- Runtime: `vm.py`, `runtime_values.py`, `diagnostics.py`, `errors.py`
- Orchestration: `coroutine.py`, `scheduler.py`, `channel.py`, `task_graph.py`, `workflow_lowering.py`, `workflow_state.py`, `runtime_events.py`
- Tooling: `cli.py`, `repl.py`, `formatter.py`, `debugger.py`, `runner.py`, `server.py`
- Packages: `project.py`, `package_manager.py`

## 2.1 Module Model (Current)
```
source.nd
  -> parse AST
  -> resolve_imports
     -> ModuleInfo(defs, exports, imports, qualified)
     -> flatten imported AST into compile unit
  -> compile
     -> rewrite names to module-qualified globals
     -> resolve mod.member via ModuleAlias
  -> VM.run (no module opcodes; module objects are snapshot records)
```

## 3. VM / Bytecode Assessment
Opcode families (from VM dispatch):
- Constants and stack: `PUSH_CONST`, `POP`
- Variable access: `LOAD`, `STORE`, `STORE_ARG`, `LOAD_UPVALUE`, `STORE_UPVALUE`
- Arithmetic/logic: `ADD`, `SUB`, `MUL`, `DIV`, `EQ`, `NE`, `LT`, `GT`, `LE`, `GE`, `NOT`, `NEG`, `TO_BOOL`
- Control flow: `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_TRUE`, `HALT`
- Iteration: `GET_ITER`, `ITER_NEXT`
- Exceptions: `SETUP_TRY`, `POP_TRY`, `FINALLY_END`, `THROW`
- Calls/closures: `CALL`, `CALL_VALUE`, `CALL_METHOD`, `MAKE_CLOSURE`, `RETURN`, `YIELD`
- Collections/records: `BUILD_LIST`, `BUILD_MAP`, `BUILD_RECORD`, `BUILD_MODULE`, `INDEX`, `INDEX_SET`, `LOAD_FIELD`, `STORE_FIELD`

Notes:
- Imports are handled at compile time; the VM does not execute module load opcodes.
- Bytecode is versioned: `BYTECODE_VERSION = 4` (frozen at v1.0). All 47 active opcodes
  are stable. `LOAD_LOCAL` was removed in v1.0; `LOAD_LOCAL_IDX`, `STORE_LOCAL_IDX`,
  and `FRAME_SIZE` are the canonical slot-indexed local variable opcodes. `FINALLY_END`
  was added at v1.0 for `try/catch/finally` support.
- Variable access fast path (v0.8.0+): `FRAME_SIZE`, `LOAD_LOCAL_IDX`, `STORE_LOCAL_IDX`.

## 4. Parser / Compiler Assessment
Strengths:
- Clear statement/expression separation with a direct lowering path.
- Closure/upvalue handling is explicit and easy to follow.
- Source locations flow through to bytecode for accurate diagnostics.

Complexity hot spots:
- Module aliasing and compile-time name rewriting.
- Import flattening, which couples parsing, loading, and compilation tightly.
- Workflow/goal lowering and task graph integration increase compiler surface area.

## 5. Runtime / Usability Assessment
- REPL: persistent state, multiline support.
- Imports/modules: plain, selective, namespaced; explicit exports; legacy modules export all top-level names.
- Stdlib: expanded `std:` modules (strings, collections, fs, path, json, math, runtime, tools, memory, agent, async, utils).
- Orchestration: task graphs with persistence and resume, workflow/goal syntax lowering, event tracing, coroutines/channels.
- Tooling integration: AST viewer, disassembler, deterministic formatter, debug runner, server mode, snapshots.

Biggest usability gaps:
- Compile-time module flattening limits isolation and incremental compilation.
- ✅ Stable embedding API: `NodusRuntime` in `nodus.__all__` since v1.0. Constructor
  parameters, `run_source()`, `run_file()`, `register_function()`, and `reset()` are stable.

## 6. Testing / Reliability Signals
- Unit tests cover core semantics and loader behaviors.
- Formatter has fixture-based regression tests.
- Examples cover imports, stdlib, and project layout.

## 7. Architectural Risks
1. Module flattening and alias mapping will become a scaling bottleneck.
2. Compile-time module alias records are snapshots, not live module objects.
3. Orchestration features increase VM/runtime coupling without a clear interface boundary.
4. Python VM limits performance headroom for heavy workloads.
5. ✅ `NodusRuntime` formalizes the embedding boundary (v1.0). Multiple lower-level
   subsystems (server, runner, scheduler) still share runtime state internally, but
   external embedders should use `NodusRuntime` exclusively.

## 8. Recommended Next Moves (Aligned With Current Code)
1. Define a runtime module object model and stop flattening imports into a single compile unit.
2. ✅ Bytecode versioning and stable opcode reference: complete at v1.0. `BYTECODE_VERSION = 4`,
   47 stable opcodes, `docs/runtime/BYTECODE_REFERENCE.md` is the authoritative reference.
3. ✅ Embedding API formalized: `NodusRuntime` in `nodus.__all__` as of v1.0.
4. Clarify runtime service contracts (tools/agents/memory/events) with structured results.
5. Expand orchestration tests: workflows/goals, resume, checkpoints, and worker dispatch.

## 9. Lifecycle Placement
Nodus is a stable practical scripting runtime (v1.0, 2026-03-15) with a strong automation/orchestration tilt.

Justification:
- Stable: bytecode VM frozen (47 opcodes, BYTECODE_VERSION=4), embedding API stable (`NodusRuntime`),
  package registry with auth/publish, finally blocks, Iterator protocol, LSP/DAP.
- Still maturing: module isolation (compile-time flattening), runtime service contracts,
  orchestration test coverage.

## 10. Final Verdict
Nodus is a credible automation scripting runtime with a clean compiler/VM core and a distinctive orchestration layer. The highest-leverage architectural shift for maturity is moving from compile-time module flattening to runtime module objects with per-module bytecode units.
