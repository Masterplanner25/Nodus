# Nodus Architecture

Nodus is a bytecode-compiled scripting runtime implemented in Python for automation and orchestration workloads.

The architecture is split into two layers:

runtime
- execution engine and VM
- module loader and module objects
- scheduler and coroutines/channels
- orchestration (task graphs, workflows, goals)
- runtime services (tools, agents, memory, event bus)

tooling
- project manifest parsing
- dependency resolution and installation
- formatter, AST tooling, disassembler
- LSP and DAP servers

The runtime never performs manifest parsing, registry access, or package resolution. Those actions live in tooling.

## Execution Pipeline

Source
  -> Lexer (`frontend/lexer.py`)
  -> Parser (`frontend/parser.py`)
  -> AST (`frontend/ast/ast_nodes.py`)
  -> Module Loader + Import Resolution (`runtime/module_loader.py`)
  -> Bytecode Compiler (`compiler/compiler.py`)
  -> Optimizer (`compiler/optimizer.py`)
  -> VM (`vm/vm.py`)
  -> Scheduler (`runtime/scheduler.py`)
  -> Orchestration (task graphs + workflows/goals)
  -> Tooling / Services / Adapters (formatter, AST printer, disassembler, LSP, DAP)

The runtime executes bytecode instructions on a stack-based VM. Workflows and goals lower to task graphs that are executed by the scheduler.

## Module System

Each module is compiled into its own bytecode unit and executed once per process. Imports resolve through the runtime module loader, which:

- resolves module paths (project root, `.nodus/modules/`, stdlib)
- compiles or reuses cached bytecode units
- executes modules once and caches module objects
- links imports via live bindings or module objects

Modules have isolated globals, and named imports bind to live export bindings so updates are shared across importers.

## Bytecode Cache

Compiled module bytecode is cached under `.nodus/cache/` in the active project root.

Cache entries are keyed by:
- absolute module path
- source file modification time (ns)

Cache invalidation happens when the source mtime changes or the bytecode version changes.

## Incremental Compilation

The runtime maintains a dependency graph in `.nodus/deps.json` to skip reprocessing unchanged modules.

Each node stores:
- module path
- imported module paths
- last compiled source mtime

During module loading, the loader:
1. resolves the module path
2. consults the dependency graph
3. compares module and dependency mtimes
4. reuses cached bytecode and cached loader metadata if unchanged
5. recompiles and updates `.nodus/cache/` and `.nodus/deps.json` if changed

## Scheduler Fairness

The scheduler is round-robin and enforces a per-task instruction budget:

- `TASK_STEP_BUDGET = 1000` (`runtime/scheduler.py`)
- each coroutine runs until it yields, suspends, or consumes its budget
- when the budget is exhausted, the VM suspends and re-enqueues the task

This prevents CPU-heavy tasks from starving other coroutines or workflow steps.

## Workflow Orchestration

Workflows and goals are lowered to task graphs (`orchestration/workflow_lowering.py`) and executed by the runtime scheduler.

Graph persistence:
- `.nodus/graphs/<graph_id>.json` stores task status, outputs, pending queue, scheduler order, workflow/goal metadata, checkpoints, and `updated_at`
- `.nodus/graphs/<graph_id>.checkpoint.json` stores the latest checkpoint snapshot

Snapshots are written atomically (temp file -> fsync -> rename) and are used by `resume_workflow` / `resume_goal`.

## AST Attribute Convention

Every AST node class inherits from `Base` (defined in `src/nodus/frontend/ast/ast_nodes.py`),
which declares two optional metadata fields:

| Field     | Type            | Set by                   | Purpose                                              |
|-----------|-----------------|--------------------------|------------------------------------------------------|
| `_tok`    | `Tok \| None`   | `Parser.mark()` in parser.py | Source token for error location (line/col)       |
| `_module` | `str \| None`   | `set_module_on_tree()` in loader.py during import resolution | Absolute file path or `"<memory>"` of the defining module |

Both fields are excluded from `__repr__` and `__eq__` so that structural AST equality
checks (used in tests and the optimizer) are not affected by metadata.

When the compiler or analyzer needs the source location of a node, it reads `node._tok`.
When it needs the originating module (for name qualification and diagnostics), it reads
`node._module`.

## Workflow Lowering (_StateRewriter)

Workflows and goals are lowered to task graphs at compile time inside `compile_stmt`
(`compiler/compiler.py`). The lowering path is:

```
WorkflowDef / GoalDef AST node
  → lower_workflow_ast / lower_goal_ast  (orchestration/workflow_lowering.py)
  → _StateRewriter                       (orchestration/workflow_lowering.py)
  → MapLit AST node
  → Bytecode compiler (compile_expr)
  → Bytecode instructions
```

`_StateRewriter` rewrites `state`-variable references in step bodies to map-index
expressions on a hidden `__state` variable.  The VM therefore executes only
ordinary map-index opcodes — there are no workflow-specific VM instructions.

This is why workflow lowering does not appear as an explicit pipeline stage between
the compiler and VM in the execution pipeline diagram above: it is an internal
phase of `compile_stmt`, triggered by the node type.

See `docs/runtime/WORKFLOWS.md` for the full workflow language reference.

## VM Dispatch Model

`VM.execute()` uses a **dict-based dispatch table** (`self._dispatch`) built once
at construction time by `VM._build_dispatch_table()`.

```python
handler = self._dispatch.get(op)
rv = handler(instr)
```

This is O(1) per instruction.  The previous if/elif chain was O(n) across ~42 opcodes
and was replaced in Phase 3 (2026-03-15) with a 33% throughput improvement measured
on a tight integer loop benchmark (388 ms → 260 ms).

**To add a new opcode:**
1. Add a method `_op_OPNAME(self, instr)` on the `VM` class.
   - Advance `self.ip` explicitly before returning (most ops do `self.ip += 1`).
   - Return `None` for normal continuation, `_NO_PENDING` if ip was redirected
     (e.g., into a function body), or a `(status, value)` tuple to signal
     YIELD / HALT to the scheduler.
2. Add `"OPNAME": self._op_OPNAME` to the dict returned by `_build_dispatch_table()`.
3. Add the opcode to `BYTECODE_REFERENCE.md` using the standard template.

## Tooling + Developer Interfaces

Tooling modules in `src/nodus/tooling/` provide:

- formatter (`tooling/formatter.py`)
- AST printer/serializer (`frontend/ast/`)
- bytecode disassembler (`compiler/compiler.py`)
- REPL (`tooling/repl.py`)
- diagnostics engine (`tooling/diagnostics.py`)

## LSP

The LSP server (`lsp/server.py`) provides:

- diagnostics (syntax, import/export, and semantic warnings)
- completion, hover, and go-to-definition
- dependency-aware incremental refresh based on `.nodus/deps.json`

## DAP

The DAP server (`dap/server.py`) reuses the runtime debugger and provides:

- breakpoints and stepping
- stack traces
- variable inspection
- stdout/stderr forwarding

## Runtime Services

The runtime exposes builtins and adapters for:

- tools (`tool_call`, `tool_available`, `tool_describe`)
- agents (`agent_call`, `agent_available`, `agent_describe`)
- memory (`memory_get`, `memory_put`, `memory_delete`, `memory_keys`)
- events (`emit`, runtime event bus)

These services are explicit, JSON-safe, and kept separate from the core VM.

## Builtin Registry

Builtin functions are organised into category modules under `src/nodus/builtins/`:

| Module          | Contents                                               |
|-----------------|--------------------------------------------------------|
| `io.py`         | `print`, `input`, filesystem ops, path helpers         |
| `math.py`       | `math_abs/min/max/floor/ceil/sqrt/random`               |
| `coroutine.py`  | `coroutine`, `resume`, `spawn`, `channel`, `send`, `recv`, `close`, `sleep` |
| `collections.py`| `len`, string ops, `keys`/`values`, `list_push/pop`, `json_parse/stringify` |

`BuiltinRegistry` (in `src/nodus/builtins/__init__.py`) is the aggregation point.

`VM.__init__` creates a `BuiltinRegistry`, calls `registry.register_all(self)`, then merges
the result into `self.builtins`.

**To add a new builtin:**
1. Implement it in the appropriate category module as a closure over `vm`.
2. Call `registry.add(name, arity, fn)` in that module's `register(vm, registry)` function.
3. Add the name to `BUILTIN_NAMES` in `nodus_builtins.py`.
4. If creating a new category, call `module.register(vm, self)` inside `BuiltinRegistry.register_all`.

## Compilation Pipelines

Two compilation pipelines exist in `src/nodus/tooling/loader.py`:

### `ModuleLoader` — Canonical (preferred)
- Located in `src/nodus/runtime/module_loader.py`
- Used by `nodus run` and all new code; also used by `nodus check`, `nodus ast`, `nodus dis` since v0.8.0
- Entry point: `ModuleLoader(...).load_module_from_source(src)` or `.load_module_from_path(path)`
- For tooling commands that only need AST/bytecode: `ModuleLoader(...).compile_only(src, module_name=name)`

### `compile_source()` — Legacy (deprecated since v0.5, removal target v1.0)
- **All internal callers migrated to `ModuleLoader` in v0.8.0** (runner.py, vm.py, dap/server.py, all test files).
- Public stub retained in `nodus.__init__` with `DeprecationWarning` until v1.0.
- Migration: replace `compile_source(src)` with `ModuleLoader(...).load_module_from_source(src)`

## Local Variable Access (v0.8.0+)

As of v0.8.0, local variable access inside functions uses slot-indexed list lookup
rather than name-keyed dict lookup.

**Compiler side:**
- `SymbolTable.define()` assigns `Symbol.index` (an integer slot) to every local variable.
- `FunctionInfo.local_slots: dict[str, int]` maps each local name to its slot.
- Compiler emits `FRAME_SIZE <n>` as the first instruction of every function.
- Local variable loads emit `LOAD_LOCAL_IDX <slot>`; stores emit `STORE_LOCAL_IDX <slot>`.
- Applies to: let-bindings, assignments, parameters, loop variables, catch variables, destructuring targets, nested function definitions.

**VM side:**
- `FRAME_SIZE n` pre-allocates `frame.locals_array = [None] * n` at function entry.
- `LOAD_LOCAL_IDX slot` reads `locals_array[slot]` directly (no dict lookup; O(1), no hashing).
- `STORE_LOCAL_IDX slot` writes `locals_array[slot]`; if the slot holds a `Cell` (captured by a closure), updates `Cell.value` in-place so the closure sees the new value.
- `frame.locals_name_to_slot: dict[str, int]` is set from `FunctionInfo.local_slots` at call time; used by `STORE_ARG` to sync parameters and by the debugger/DAP for variable inspection.
- `frame.locals: dict` is still written for compatibility; DAP and debugger merge both views.

**Performance note:**
- Before v0.8.0: every local access was a dict lookup (hash + collision probe).
- After v0.8.0: every local access is a list index — significantly lower overhead in tight loops.

## NodeVisitor Pattern

`NodeVisitor` (`src/nodus/frontend/visitor.py`) is the base class for all AST
walkers.  It provides a `visit(node)` method that dispatches to
`visit_<ClassName>` based on the node's runtime type.  If no specific method
exists, `visit_default()` is called, which raises `NotImplementedError` by
default.

**Requirement for new AST nodes:** Any new node type added to `ast_nodes.py`
must have a corresponding `visit_<ClassName>` method added to every
`NodeVisitor` subclass that needs to handle it.  Failing to do so raises
`NotImplementedError` at runtime, surfacing the gap early.

Current NodeVisitor subclasses:
- `ModuleStamper` (loader.py) — recursively stamps `_module` on all nodes
- `InfoCollector` (loader.py) — collects module definition/export info
- `Analyzer` (tooling/analyzer.py) — optional static type inference
