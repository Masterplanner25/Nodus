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

v0.7.0 shipped 2026-03-15. Active work is v0.8 planning; see the v0.8 milestone section below.
[Unreleased] documentation updates are tracked in CHANGELOG.md.

## Released Versions

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
Partial. Package manager CLI exists (`package_manager.py`): `nodus.toml` / `nodus.lock`,
semver resolution, local dependency layout under `.nodus/modules/`, and `nodus install` /
`nodus update` commands are implemented.
Registry-backed package resolution and publishing: NOT YET STARTED.
Registry resolution is the primary blocker for this milestone.

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

Version 0.8 — Stability & Package Ecosystem

Theme: Close the gap between working language and distributable ecosystem.

Goals:

- [ ] Registry-backed package resolution
      The single most overdue item. Package manager CLI exists but cannot
      resolve or publish from a registry. This is required before v1.0.
      Owner: package_manager.py + new registry client module.

- [ ] compile_source() removal
      Deprecated since v0.5.0. Tracked in TECH_DEBT.md.
      All internal callers must migrate to ModuleLoader before removal.
      Removal unblocks a cleaner public API surface for v1.0.
      ~220 deprecation warnings remain in the test suite.

- [ ] Opcode set stabilization plan
      The opcode set must be frozen before v1.0 can be declared.
      v0.8 deliverable: produce a formal opcode freeze proposal —
      a documented list of all 44 current opcodes with a stability
      classification (stable / provisional / deprecated) and a process
      for adding new opcodes post-freeze.
      Actual freeze happens at v1.0.

- [ ] LOAD_LOCAL_IDX full VM slot-indexed path
      Compiler emits LOAD_LOCAL (name-keyed, shipped in v0.7). The next
      step is LOAD_LOCAL_IDX (slot-indexed list access), bypassing the
      dict lookup entirely. Requires Frame refactoring to fixed-size
      locals array. Tracked in TECH_DEBT.md.

- [ ] Formatter AST coverage audit
      FnExpr, FieldAssign, and RecordLiteral were missing from the
      formatter and would crash on valid source (fixed in v0.7). Audit
      all remaining AST nodes against format_expr() and format_stmt()
      before v1.0 to ensure no other nodes are missing handlers.

Not in v0.8 (deferred to v1.0 or later):
- Type System Evolution — no version target assigned yet
- Stable embedding API freeze — v1.0 goal
- Production hardened sandboxing — v1.0 goal

Version 1.0

Goals:

stable module system

frozen opcode set

stable embedding API

hardened sandboxing

production debugger and profiler

stable package manager

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
