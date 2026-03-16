# Nodus Roadmap

Nodus Roadmap

This document outlines the development direction of the Nodus language and runtime.

The roadmap is divided into:

completed releases

near-term releases

architectural milestones

long-term evolution

Nodus is evolving as a bytecode-based scripting runtime designed for automation and orchestration systems.


## In Progress / Release Pending

v0.9.0 shipped 2026-03-15. See CHANGELOG.md for the full entry.
[Unreleased] documentation updates are tracked in CHANGELOG.md.

## Released Versions

### 0.9.0 — Registry Auth, Publish & Ecosystem Completeness (2026-03-15)
- `compile_source()` public re-export removed from `nodus.__init__`; loader body
  retained for internal use until v1.0.
- Registry authentication: Bearer token support, `NODUS_REGISTRY_TOKEN` env var,
  `~/.nodus/config.toml` user config, `nodus login` / `nodus logout` commands,
  three-tier token resolution (flag > env > config).
- Registry publish: `nodus publish` command, `create_package_archive()`,
  `publish_package()` POST method, SHA-256 + `X-SHA256` header, 409 Conflict
  handling, publish protocol documented.
- Provisional opcode decisions documented in `FREEZE_PROPOSAL.md`: all 7 provisional
  opcodes remain provisional; GET_ITER/ITER_NEXT cleanup, finally blocks, and
  YIELD send-value formalization all deferred to v1.0.
- 20 new tests (11 auth + 9 publish).

### 0.8.0 — Stability & Package Ecosystem (2026-03-15)
- Registry-backed package resolution: `RegistryClient` with semver, SHA-256 verification, archive extraction.
- `compile_source()` internal callers migrated to `ModuleLoader`; 0 DeprecationWarnings from `src/`.
- `LOAD_LOCAL_IDX` / `STORE_LOCAL_IDX` / `FRAME_SIZE` opcodes: slot-indexed local variable access.
- All 48 AST node types covered in the formatter; `format_pattern()` helper added.
- Opcode freeze proposal published: `docs/governance/FREEZE_PROPOSAL.md` (39 stable / 7 provisional / 1 deprecated).
- Bytecode cache version bumped to 0x02. LSP version field updated to 0.8.0.

### 0.7.0 — Runtime Orchestration, Diagnostics, Debugging, and Sprint Fixes (2026-03-15)
- Incremental module compilation with persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache: `marshal` + `NDSC` magic + SHA-256 integrity, replacing `pickle`.
- DAP debug adapter (`nodus dap`) and LSP server (completion, hover, go-to-definition, diagnostics).
- Workflow persistence snapshots, checkpoint files, and workflow management CLI commands.
- Scheduler fairness: round-robin execution with `TASK_STEP_BUDGET` enforcement.
- VM dispatch table (`_build_dispatch_table()`): replaced `if/elif` chain — ~33% throughput improvement.
- `LOAD_LOCAL` opcode for confirmed function-local variables — ~21% additional loop improvement.
- Bytecode cache hardened: `pickle` → `marshal` + NDSC magic + SHA-256 integrity check.
- Channel queues converted to `collections.deque` (O(1) pop).
- Builtin registry (`BuiltinRegistry`) extracted from VM into `src/nodus/builtins/`.
- `compile_source()` deprecated; `ModuleLoader` is the canonical pipeline.
- AST `Base` dataclass with explicit `_tok` / `_module` fields.
- `NodeVisitor` base class (`src/nodus/frontend/visitor.py`).
- Correctness fixes: `LangSyntaxError` from lexer, extended escape sequences, bool constant folding, coroutine close guard, import depth limit.
- Formatter: `FnExpr`, `FieldAssign`, `RecordLiteral` handlers added.
- CI: auto-format examples/ before format check.

### 0.3.0 — Tooling and Orchestration
- Richer stdlib: `std:json`, `std:math`, `std:runtime`, `std:tools`, `std:memory`, `std:agent`, `std:async`, and expanded collections helpers.
- Editor integration: TextMate grammar, VS Code config, and snippets under `tools/vscode/`.
- Tooling polish: formatter trailing-comment controls (`--keep-trailing`) and unary minus formatting stability.
- Inspection tooling: `nodus ast`, `nodus dis`, compact AST view, and disassembly with locations.
- Debugging UX improvements: trace filters/limits, scheduler tracing, trace events/JSON, and `nodus debug`.
- Orchestration runtime: workflows/goals, task graph planning/resume, runtime event bus, server mode, and snapshots.

### 0.4.0 — Runtime Architecture & Packaging
- Bytecode version headers and validation.
- Disk bytecode caching for compiled modules with timestamp/version invalidation and `nodus cache clear`.
- Incremental compilation with persisted module dependency graph invalidation in `.nodus/deps.json`.
- Sandbox execution limits (steps/time/stdout).
- Embedding API for host integration.
- Runtime module system with per-module bytecode units, runtime module objects, isolated globals, live import bindings, and module caching.
- Project manifests (`nodus.toml`) and lockfiles (`nodus.lock`) with dependency resolution.
- Tooling-side package resolution/installation and `.nodus/modules/` dependency layout.
- Debugger MVP (breakpoints, step/next/continue, locals/stack).

### 0.5.0 — Interactive Shell and Inspection
- REPL multiline editing with brace-aware continuation prompts.
- Persistent REPL history via `~/.nodus_history` when `readline` is available.
- REPL shell commands `:ast`, `:dis`, `:type`, `:help`, and `:quit`.
- Expression inspection workflows for AST, bytecode, and basic runtime type display.
- REPL documentation and README/onboarding examples for interactive development.

### 0.2.0 — Stdlib Maturity and Project Ergonomics
- Coherent stdlib modules (`std:strings`, `std:collections`, `std:fs`, `std:path`).
- Expanded examples for real-world scripts.
- Documentation for project layout, imports, and stdlib usage.
- Validation tooling (`nodus check`) and trace controls for daily debugging.
- Deterministic formatter (`nodus fmt`) and style guide.
- CI workflow and release discipline docs.

## Future Targets

### 0.4.x — Packaging and Tooling (Planned)
- Registry-backed package resolution and publishing.
- ✅ Debugger improvements and profiler MVP.
- ✅ Module bytecode unit format and bytecode version headers — Shipped in v0.7.0 — marshal format with NDSC magic bytes (b'NDSC'), version byte, and SHA-256 source integrity header. See src/nodus/runtime/bytecode_cache.py and test_bytecode_version_mismatch.
- ✅ Minimal runtime module objects and debugger MVP — Shipped in v0.4.x as planned. DAP stdio server, breakpoints, stepping, stack traces, and variable scopes are all implemented and tested. See docs/tooling/DAP.md and test_dap_server.
- ⚠️ Semver parsing and lockfile format groundwork — Groundwork shipped — semver parsing, lockfile format, and local package resolution are implemented and tested (test_packages). Registry-backed remote resolution and publishing remain open. Tracked as primary v0.8 blocker in the v0.8 milestone section.

## Compatibility / Deprecations
- `.tl` legacy extension (primary is `.nd`).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers.
- See `COMPATIBILITY.md` for timeline details.


Near-Term Architecture Milestones

These are the most important structural improvements planned for the runtime.

1. Module System Redesign

Current model:

runtime module loader with per-module bytecode units, runtime module objects, and live import bindings

Future model:

runtime module loader with bytecode caching and incremental compilation

Benefits:

proper namespace isolation

incremental compilation

better tooling compatibility

cleaner import semantics

Status:
✅ Completed (per-module bytecode units, bytecode caching, incremental compilation, live bindings).

2. Bytecode Stability and Versioning

Introduce:

frozen opcode set

bytecode version headers

compatibility validation

Benefits:

stable tooling

bytecode caching

forward-compatible loaders

Status:
✅ Completed (bytecode version headers validated at load time).

3. Runtime Architecture Split

Formalize runtime subsystems:

vm
module_loader
scheduler
runtime_services

Benefits:

clearer system boundaries

easier embedding

safer experimentation

Status:
✅ Implemented in code layout (`runtime/`, `tooling/`, `services/`), boundaries still evolving.

4. Embedding API

Define a stable host API for:

running code

loading modules

exposing host functions

hooking runtime events

Embedding support is necessary for integrating Nodus into automation systems.

Status:
✅ Implemented (`nodus.runtime.embedding.NodusRuntime`).

5. Package Management 1.0

Introduce:

registry specification

registry-backed dependency resolution

This enables reproducible automation deployments.

Status:
✅ Complete as of v0.9.0. Package manager CLI: `nodus.toml` / `nodus.lock`, semver
resolution, local and HTTP-registry dependency resolution, archive download with
SHA-256 verification, `nodus install` / `nodus update`, registry authentication
(Bearer token, `NODUS_REGISTRY_TOKEN`, `~/.nodus/config.toml`), `nodus login` /
`nodus logout`, and `nodus publish` commands are all implemented.

Runtime Evolution

Key runtime improvements.

Module Isolation

Per-module globals, runtime module objects, live import bindings, execute-once module caching, disk bytecode caching, incremental compilation, and scheduler fairness improvements are now implemented. Next steps focus on broader compiler and diagnostics improvements.

Runtime Namespaces

Separate:

module globals

host globals

runtime services

This prevents accidental name leakage.

Memory Model Clarification

Formalize value semantics for:

records

maps

lists

Add helper utilities for cloning workflow state safely.

Sandboxing

Standardize execution limits:

time limits

step limits

output limits

Expose configurable runtime limits for embedded environments.

Coroutine Scheduler Improvements

Planned improvements:

cooperative fairness

basic priority queues

bounded message queues

Runtime Service APIs

Formalize service interfaces for:

tools

agents

memory

event streams

Use structured payload schemas.

Compiler Improvements
Symbol Resolution Improvements

Reduce complexity in module alias rewriting.

Module-qualified names should become first-class identifiers.

Incremental Compilation

Modules now compile independently, persist a dependency graph, and reuse cached bytecode and loader metadata when dependency mtimes are unchanged.

Benefits:

faster rebuilds

faster REPL startup

improved tooling performance

Module-Level Bytecode

Each module will compile to a separate bytecode segment.

Benefits:

isolation

caching

faster load times

Optimizer Improvements

Potential passes:

dead store elimination

constant propagation

branch simplification

These optimizations will remain conservative.

Diagnostics

Improve error reporting by preserving:

file

line

column

for every instruction.

This enables better debugging tools and LSP integration.

Virtual Machine Improvements

Planned improvements ranked by feasibility.

1. ✅ Handler Table Dispatch (shipped v0.7.0)

Replaced `if/elif` opcode switch with dict dispatch table (`_build_dispatch_table()`).
Benchmark: 388 ms → 260 ms (~33% throughput improvement).

2. Opcode Specialization

Examples:

ADD_NUM
ADD_STR

Improves hot execution paths.

3. Superinstructions

Combine common instruction sequences into single instructions.

Example:

LOAD_CONST + STORE
4. Register VM Conversion (Long-Term)

Large architectural rewrite with uncertain gains in Python.

Not planned before 1.0.

Type System Evolution

The type system is intended primarily for tooling and diagnostics, not strict safety.

Planned features:

optional typing

record shape types

function signatures

type-aware linting in nodus check

simple inference for literals and record shapes

By default:

types produce warnings, not errors.

Tooling Roadmap

Order of implementation:

✅ Debugger with breakpoints and step control

✅ Profiler with opcode counts and function timing

✅ Runtime metrics for scheduler and task execution

REPL improvements:
- completed in 0.5.0:
- multiline editing
- command history
- :ast
- :dis
- :type

Language Server Protocol (LSP)

✅ LSP server with diagnostics, completion, hover, and go-to-definition

IDE integration via VS Code extension

Packaging and Ecosystem

Package structure will use a minimal manifest format.

Example:

nodus.toml

Fields:

name

version

dependencies

Dependency resolution:

semver ranges

git fallback

local dependency support

Lockfile:

nodus.lock

Includes pinned versions and source hashes.

Performance Strategy

The runtime is implemented in Python.

Performance goals prioritize automation workloads, not CPU-bound computation.

Planned improvements:

threaded opcode dispatch

bytecode caching

precompiled stdlib bytecode

reduced name resolution in loops

scheduler optimizations

Bootstrapping Milestone

A long-term milestone for the language is self-hosting.

Bootstrapping means rewriting the Nodus compiler in the Nodus language itself.

Prerequisites:

stable language semantics

stable bytecode instruction set

reliable module system

sufficiently expressive standard library

Bootstrapping provides several benefits:

validates the language design

strengthens compiler stability

proves the language can support complex systems

The initial bootstrap compiler does not need to be optimized; correctness and clarity are the primary goals.

Version Timeline

Version 0.4

Focus:

✅ bytecode caching

✅ debugger MVP

registry package resolution

Version 0.5

Focus:

improved module error reporting

profiler MVP

improved REPL

Version 0.7 ✅ Released 2026-03-15

Focus:

- ✅ incremental compilation (`.nodus/deps.json` dependency graph, mtime-based invalidation)
- ✅ bytecode caching hardened (marshal + NDSC magic + SHA-256 integrity, replacing pickle)
- ✅ scheduler fairness improvements (round-robin queue plus per-task instruction budgets)
- ✅ task graph persistence improvements (resilient snapshots + checkpoint resume, workflow CLI)
- ✅ LSP diagnostics (cross-module publishing, dependency-aware incremental refresh, richer locations, warnings)
- ✅ debug adapter (DAP stdio server, runtime-debugger-backed breakpoints/stepping, stack traces, variable scopes, CLI entrypoint)

Version 0.8 ✅ Released 2026-03-15 — Stability & Package Ecosystem

Theme: Close the gap between working language and distributable ecosystem.

Goals:

- ✅ Registry-backed package resolution
      HTTP registry client (`registry_client.py`) implemented. `RegistryClient`
      fetches package index, resolves semver constraints, downloads archives with
      SHA-256 verification, and extracts to `.nodus/_staging/` before the
      installer copies to `.nodus/modules/`. Registry URL resolved from
      `--registry` flag, `NODUS_REGISTRY_URL` env var, or `registry_url` in
      `[package]` nodus.toml; falls back to local registry when none set.
      Lockfile records `source = "registry"`. 12 new tests in
      `tests/test_registry_client.py`. Note: publish and auth deferred to v0.9.

- ✅ compile_source() internal callers removed
      Deprecated since v0.5.0. All internal callers (runner.py, vm.py,
      dap/server.py) migrated to ModuleLoader in v0.8. Public stub
      subsequently removed in v0.9.0. Loader body retained for internal
      tooling use until v1.0. 0 DeprecationWarnings from internal src/
      callers.

- ✅ Opcode set stabilization plan
      Formal freeze proposal published at docs/governance/FREEZE_PROPOSAL.md.
      47 opcodes classified: 39 stable, 7 provisional, 1 deprecated (LOAD_LOCAL).
      Freeze prerequisites, post-freeze extension process, and version history
      documented. Actual opcode freeze happens at v1.0.

- ✅ LOAD_LOCAL_IDX full VM slot-indexed path
      Compiler now emits FRAME_SIZE (pre-allocates locals array),
      STORE_LOCAL_IDX (slot-indexed store for let/assign/loop/catch vars),
      and LOAD_LOCAL_IDX (slot-indexed load) for all function-scope locals.
      Frame carries locals_array (list) + locals_name_to_slot (name→slot map
      set at call time from FunctionInfo.local_slots). capture_local updated
      to box Cells via array path for correct closure semantics. Cache
      serialization updated (local_slots field). Bytecode version bumped to 2.
      NODUS_BYTECODE_VERSION = 2, BYTECODE_VERSION = 2.

- ✅ Formatter AST coverage audit
      FnExpr, FieldAssign, and RecordLiteral were missing from the
      formatter and would crash on valid source (fixed in v0.7). Audit
      complete in v0.8: Yield, Throw, TryCatch, DestructureLet,
      VarPattern, ListPattern, RecordPattern handlers added. All 48 AST
      node types are now covered. See tests/test_formatter_coverage.py.

Not in v0.8 (deferred to v0.9 or later):
- Registry publish (`nodus publish`) and auth — v0.9 goal ✅ completed in v0.9
- `compile_source()` public stub removal — originally v1.0 goal; moved up and completed in v0.9
- `LOAD_LOCAL` deprecated opcode removal — v1.0 goal
- Provisional opcode finalization (GET_ITER, ITER_NEXT, exception model) — v0.9 decision target
- Type System Evolution — no version target assigned yet
- Stable embedding API freeze — v1.0 goal
- Production hardened sandboxing — v1.0 goal

Version 0.9 — Registry Publishing & Auth

Theme: Complete the package ecosystem.

Goals:
- [x] Registry publish (`nodus publish` command)
- [x] Registry authentication and token management
- [x] compile_source() public stub removal (deprecated since v0.5, internal callers removed v0.8)
- [x] Provisional opcode finalization: GET_ITER/ITER_NEXT (`pending_get_iter` cleanup) and exception model (finally/typed catches decision)
    - GET_ITER/ITER_NEXT: pending_get_iter cleanup deferred to v1.0 (by design — behavior documented in INSTRUCTION_SEMANTICS.md)
    - Exception model: finally deferred to v1.0; SETUP_TRY/POP_TRY/THROW remain provisional

## v0.9.x (patch — planned)
- Fix pre-existing timing sensitivity in `test_task_reassignment_after_worker_failure`
  (background thread polling window occasionally missed under full-suite concurrency).

Version 1.0

**Critical path:** `finally` implementation (Large) → opcode freeze.
All other goals can proceed in parallel and are expected to complete before `finally` is done.

Goals:

- Frozen opcode set — all provisional opcodes resolved. YIELD, BUILD_MODULE, GET_ITER,
  and ITER_NEXT decided (stable). 3 opcodes remain provisional: `SETUP_TRY`, `POP_TRY`,
  `THROW`. Freeze proposal at `docs/governance/FREEZE_PROPOSAL.md`.
  **Status:** ⏳ Blocked by finally implementation and `_op_throw` final decision.

- ✅ Stable module system — `BUILD_MODULE` promoted to stable in `FREEZE_PROPOSAL.md`.
  Module system (live bindings, re-exports, circular detection) is feature-complete and frozen.
  **Status:** ✅ Declared stable at v1.0 planning.

- ✅ Stable embedding API freeze — `NodusRuntime` added to `nodus.__all__`. `max_frames`
  documented in `EMBEDDING.md` constructor parameters section. API declared frozen.
  **Status:** ✅ Complete.

- ✅ `compile_source()` loader body removal — function body removed from
  `nodus.tooling.loader`. Last test caller (`test_import_containment.py`) migrated to
  `ModuleLoader`. Tombstone comment left in `loader.py`. See `DEPRECATIONS.md`.
  **Status:** ✅ Complete.

- ✅ Iterator protocol cleanup — `pending_get_iter` / `pending_iter_next` flags replaced
  with a first-class `Iterator` protocol object. VM-only change; no compiler or `.nd`
  source impact. 14 pending-flag sites removed from `vm.py`. `GET_ITER` and `ITER_NEXT`
  promoted to stable. All 377 tests pass. Coroutine+iteration interaction tests added.
  **Status:** ✅ Complete at v1.0.

- `finally` block implementation — new opcode or extended `SETUP_TRY` operand. Requires
  lexer, AST, parser, compiler, and VM changes. `BYTECODE_VERSION` bump to 3 required.
  **Status:** ⏳ Not started. Critical path item — longest chain to v1.0.

- `_op_throw` structured value preservation — fix `_op_throw` (vm.py:~2092) which
  stringifies non-string thrown values. `handle_exception` is already correct.
  **Status:** ⏳ Small fix. See TECH_DEBT.md.

- ✅ `YIELD_VALUE` / `SEND` opcode evaluation — decision made. YIELD frozen as-is.
  No new opcode needed. No user-facing send-value use cases exist in `.nd` source.
  **Status:** ✅ Decision recorded in `FREEZE_PROPOSAL.md`.

- Production hardened sandboxing — 6 limit types implemented (steps, timeout, stdout,
  file paths, input, call stack). Memory limits are the only gap — deferred post-v1.0.
  **Status:** ✅ Sufficient for v1.0. Memory limits post-v1.0.

- ✅ Stable package manager — package manager feature-complete as of v0.9.0.
  `.ndignore` deferred to v1.0.x.
  **Status:** ✅ Declared stable.

- `LOAD_LOCAL` deprecated opcode removal — remove `_op_load_local` handler from VM
  dispatch table. Prerequisite: audit and fix three compiler fallback paths
  (`compiler.py` lines 584, 619, 731) that still emit name-keyed `LOAD_LOCAL`.
  **Status:** ⚠️ Compiler still emits `LOAD_LOCAL` at 3 fallback paths.
  `DEPRECATIONS.md` claim was inaccurate — corrected. Audit required before removal.

Long-Term Vision (3–5 Years)

Nodus is expected to evolve in several realistic directions.

AI Orchestration Language

Strong alignment with:

workflows

task graphs

runtime services

event tracing

Embedded Automation Engine

Applications may embed Nodus to provide:

scripting

automation logic

task orchestration

Distributed Task Runtime (Experimental)

Possible but requires significant runtime changes.

Strategic Identity

Nodus is primarily an automation scripting and orchestration runtime, not a general-purpose application language.

The language is designed to coordinate systems rather than replace full application frameworks.
