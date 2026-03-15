# Changelog

## [Unreleased]

### Added
- None.

### Changed
- None.

### Fixed
- None.

### Improved
- None.

### Documentation
- Documentation synchronization pass for runtime architecture, workflows, tooling, and CLI references.
- Updated REPL invocation to `python -m nodus.tooling.repl` across docs.
- Roadmap status refreshed for completed milestones.

### Tests
- None.

### Refactoring
- None.

## [0.7.0] - 2026-03-14 — Runtime Orchestration, Diagnostics, and Debugging

### Added
- Incremental module compilation backed by a persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache for compiled modules (`.nodus/cache/*.nbc`).
- DAP debug adapter over stdio with `nodus dap`.
- LSP server with completion, hover, go-to-definition, and diagnostics.
- Workflow persistence snapshots and checkpoint files under `.nodus/graphs/`.
- Workflow management CLI commands: `nodus workflow list`, `nodus workflow resume`, `nodus workflow cleanup`.

### Changed
- Runtime module loader now skips recompilation when dependency mtimes are unchanged.
- Workflow resume logic rehydrates persisted task state and scheduler order.
- `nodus deps` now reports the incremental compilation dependency graph.

### Fixed
- None.

### Improved
- Scheduler fairness via round-robin execution and `TASK_STEP_BUDGET` enforcement.
- LSP diagnostics are dependency-aware with cross-module publishing and incremental refresh.
- Debugger integration reused by both interactive debugger and DAP server.
- Workflow checkpoint handling preserves upstream task outputs while rolling back downstream steps.

### Documentation
- Added/updated docs for LSP, DAP, debugging entrypoints, workflow persistence, and scheduler fairness.

### Tests
- Added coverage for bytecode cache, incremental compilation, scheduler fairness, workflow persistence, LSP diagnostics, and DAP server behavior.
- Added/expanded tests for module isolation and runtime module objects.

### Refactoring
- None.

## [0.5.0] - 2026-03-14 — Interactive Shell and Inspection

### Added
- REPL multiline editing with `... ` continuation for brace-delimited blocks.
- Persistent REPL history via `~/.nodus_history` when Python `readline` is available.
- REPL inspection commands: `:ast <expr>`, `:dis <expr>`, `:type <expr>`, `:help`, and `:quit`.
- Dedicated REPL documentation in `docs/tooling/REPL.md`.
- Profiler documentation and runtime integration for the 0.5.0 tooling milestone.

### Changed
- REPL inspection output now supports compact expression AST views and expression bytecode inspection.
- Onboarding and runtime docs now describe the interactive shell workflow and inspection commands.
- Project metadata now aligns on version `0.5.0`.

### Fixed
- None.

### Removed
- None.

## [0.4.x Tracking]
- Module bytecode unit format and bytecode version headers.
- Minimal runtime module objects and debugger MVP.
- Semver parsing and lockfile format groundwork.

## [0.4.0] - 2026-03-14 — Runtime Architecture & Packaging

### Added
- Bytecode version headers in compiled modules.
- Runtime sandbox limits (steps/time/stdout).
- Embedding API for host execution and host function registration.
- Runtime module system with module objects and caching.
- Per-module bytecode units and per-module global namespaces.
- Project manifest parsing (`nodus.toml`) and dependency resolution.
- `nodus.lock` lockfile generation with resolved metadata.
- Debugger MVP with breakpoints, stepping, stack inspection, and variable inspection.
- Tooling-side package management modules for project parsing, semver, dependency resolution, installation, and registry metadata.
- Deterministic `[[package]]` lockfile entries with `name`, `version`, `source`, and `hash`.
- Test coverage for installer behavior, lockfile generation, runtime loading from `.nodus/modules`, and manifest/resolution flows.

### Changed
- Imports now resolve through the runtime module loader with dependency-first resolution.
- Module execution is isolated per module with cached module objects.
- Tooling execution flows updated for module-based runtime execution.
- CLI includes `nodus update` for dependency refresh.
- Refactored package management so runtime execution no longer performs manifest parsing, dependency resolution, registry access, or network operations.
- Installed dependencies now live under `.nodus/modules/` instead of `deps/`.
- Runtime module loading now resolves imports in the order: local project modules, `.nodus/modules/`, then standard library.
- `nodus install` and `nodus update` now route through tooling-side resolution and installation.

### Internal
- Module loader integrates project manifests, lockfile resolution, and dependency paths.
- VM supports module-bound function wrappers for module exports.
- Package manager routes through the runtime project system and lockfile format.

### Tests
- Added coverage for manifest parsing, semver ranges, and dependency resolution.
- Updated package tests for the new lockfile format and module execution behavior.

### Fixed
- Worker-required tasks always dispatch through the worker manager.

### Removed
- Package-management responsibilities from the runtime project/loading path.

## [0.3.0] - 2026-03-13

### Added
- Workflow and goal syntax with task graph planning, execution, resume, and checkpoints.
- Cooperative coroutines, scheduler, and channels (`coroutine`, `resume`, `spawn`, `run_loop`, `sleep`, `channel`, `send`, `recv`, `close`).
- Runtime event bus with human/JSON sinks and CLI flags `--trace-events`, `--trace-json`, `--trace-file`.
- Service mode `nodus serve`, session snapshots (`nodus snapshot`, `nodus snapshots`, `nodus restore`), and worker registration (`nodus worker`).
- Orchestration CLI commands: `nodus graph`, `workflow-*`, `goal-*`.
- Runtime service CLI commands: `tool-call`, `agent-call`, `memory-get`, `memory-put`, `memory-keys`.
- Package management commands: `nodus init`, `nodus install`, `nodus deps` with `nodus.toml`/`nodus.lock`.
- Stdlib modules: `std:json`, `std:math`, `std:runtime`, `std:tools`, `std:memory`, `std:agent`, `std:async`, `std:utils`.
- Editor support: TextMate grammar, VS Code config, and snippets under `tools/vscode/`.
- Inspection tooling: `nodus ast`, `nodus dis`, `nodus ast --compact`, `nodus dis --loc`.
- Debug command: `nodus debug`.
- Example smoke test command: `nodus test-examples`.
- Added `examples/project_layout_demo/` as a small multi-file onboarding example.

### Changed
- Formatter preserves integer-looking numeric literals and uses a dedicated unary minus AST node.
- Trailing comment behavior clarified and `--keep-trailing` option added.
- `nodus run` adds `--no-opt`, `--project-root`, scheduler tracing, and trace filters/limits.
- Bytecode reference updated to document the `NEG` opcode explicitly.

### Fixed
- Expire polling workers after heartbeat timeout to ensure dead workers are removed promptly.

### Removed
- None.

## [0.2.0] - 2026-03-11

### Added
- Module system (imports/exports, selective imports, re-exports, `std:` aliases).
- Deterministic import resolution with package/index support and project-root overrides.
- Standard library modules: `std:strings`, `std:collections`, `std:fs`, `std:path`.
- `nodus fmt` (formatter) with `--check` and comment handling controls.
- `nodus check` for syntax/import/compile validation without execution.
- Debug flags: `--dump-bytecode` and `--trace` with controls.
- CI workflow via GitHub Actions.
- Release discipline docs: `RELEASE_CHECKLIST.md`, `VERSIONING.md`, `COMPATIBILITY.md`.

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).
- Centralized version metadata in `version.py`.
- Compatibility: `.tl` extension still supported with warnings; legacy launchers remain available.

### Fixed
- None.

### Removed
- None.

## [0.1.0] - 2026-03-09

### Added
- Modular runtime architecture (lexer, parser/AST, compiler, VM, loader).
- Imports/exports with selective and namespaced imports.
- Deterministic import resolution with `std:` aliases.
- Stack traces with source mapping.
- Debugging flags: `--dump-bytecode` and `--trace`.
- Package/index resolution and project-root overrides.
- Re-export support (`export { name } from "./mod.nd"`).

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).

### Fixed
- None.

### Removed
- None.
