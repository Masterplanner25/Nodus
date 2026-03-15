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
- Used by `nodus run` and all new code
- Entry point: `ModuleLoader(...).load_source(src)` or `.load_module_from_path(path)`

### `compile_source()` — Legacy (deprecated since v0.5, removal target v1.0)
- Used internally by `nodus check`, `nodus ast`, `nodus dis`
- Emits `DeprecationWarning` at runtime
- Migration: replace `compile_source(src)` with `ModuleLoader(...).load_source(src)`

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
