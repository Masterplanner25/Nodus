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
