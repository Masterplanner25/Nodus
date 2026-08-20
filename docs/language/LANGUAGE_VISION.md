# LANGUAGE_VISION.md

## Overview

Nodus is a small, high-level scripting language built around a bytecode compiler and stack-based virtual machine. It is designed for automation and orchestration: readable scripts, predictable execution, and a runtime that can schedule work, track events, and integrate with tools.

The language favors a compact core with extensible runtime services (tools, agents, memory, task graphs) rather than a large surface area of syntax.

---

# Core Purpose

Nodus exists to provide:

- A lightweight scripting environment
- Readable and predictable control flow
- A compact execution runtime
- A practical orchestration layer (task graphs, workflows, events)

---

# Design Philosophy

### 1. Simplicity
Keep the core language small and learnable. Add power through libraries and runtime services rather than syntax bloat.

### 2. Explicit Control Flow
Control flow should be obvious. No hidden magic, no implicit behavior.

### 3. Small Core Language
The core stays compact. Features that can be libraries should be libraries.

### 4. Extensible Runtime
The runtime should allow new capabilities through:
- Bytecode instruction extensions
- Built-in functions and stdlib
- External tool adapters and event sinks

### 5. Predictable Behavior
Evaluation and scoping rules should be consistent. Errors should be explainable and localized.

### 6. Orchestration Composes; Capabilities Don't

Capabilities (HTTP, subprocess, file I/O, hashing, datetime) provide
narrow, focused operations. Orchestration concerns (retry, backoff,
parallelism, sequencing, error recovery, rate limiting, circuit breaking)
compose those operations through workflow primitives.

Nodus orchestrates retries via workflows; it doesn't bake them into every
call. This principle extends to all orchestration concerns: per-call
retry options, built-in backoff schedules, automatic fallback chains, and
rate-limiting decorators all belong to workflow code, not to the
capability's option surface.

The language's job is to make composition expressive. The capabilities'
job is to do one thing well.

---

# Language Architecture

Source Code
-> Tokenizer / Lexer
-> Parser
-> AST
-> Bytecode Compiler
-> Stack-based VM

---

# Current Capabilities

- Integers and floats as distinct types (`int` and `float`); integer arithmetic is exact
- Booleans, strings, nil
- Lists, maps, and records (map/record literal disambiguation shipped in v3.0)
- Error records as the standard error pattern (err records with `kind`, `message`, location fields)
- Functions, closures, and recursion
- If/else, while, for, for item in list
- Imports/exports with namespaced imports
- Deterministic formatter and static validation
- REPL and CLI tooling
- Coroutines, scheduler, and channels
- Task graph runtime with persistence and resume
- Workflows and goals (compiled to task graphs)
- Runtime events and trace tooling

---

# Near-Term Direction

All v1.0 near-term goals are complete as of v2.1.0:
- Runtime module objects and per-module bytecode caching ✅
- Stable bytecode versioning (`BYTECODE_VERSION = 4`, frozen) ✅
- Stable embedding API (`NodusRuntime` in `nodus.__all__`) ✅
- Debugger (DAP), profiler, and LSP tooling ✅
- Package management (`nodus install`, `nodus publish`, registry auth) ✅
- Stability policy published (`docs/governance/STABILITY.md`) ✅

## Current Release (v4.1.1)

Shipped 2026-08-05 on PyPI (`pip install nodus-lang`).

v4.0 cycle highlights:
- v4.0.0: AI-native stdlib (std:tool, std:identity, std:effects, std:sys, std:memory, std:retry, std:circuit_breaker), HandlerContract infrastructure, full ecosystem of 35 companion packages
- v4.0.1: NodusRuntime sandbox defaults hardened (SCHED-001 fixed, timeout_ms → None, allowed_paths → CWD), httpx optional, integer division returns int, div/zero raises error, compound assignment operators, multiline expressions, @annotation syntax
- v4.0.2: Bug fixes for @exactly_once, allowed_commands, @retry, event_sinks, trailing commas
- v4.0.3: All 18 Sentinel evaluation bugs fixed; stdlib contract test suite added
- v4.0.4: session_id propagation fix (#254), retry error trace suppression on eventual success (#255)
- v4.0.5: spawn/coroutine/channel and workflow/goal promoted to Mostly Stable; yield promoted to Stable; nodus-vscode v0.1.0, nodus-jupyter v0.1.0, nodus-mcp-server, nodus-adapter-base published
- v4.0.6: @retry annotation no-op fixed (COMPILER-001, #267), spurious "spawned task never executed" warning fixed (WARN-001, #268), `nodus serve`/`worker --help` print usage
- v4.0.7: cross-process workflow resume re-binds module imports (REHYDRATE-001, #285)
- v4.0.8: stdlib async wrappers (`http.get_async`, `subprocess.run_async`) overlap concurrently instead of falling back to sync (ASYNC-MOD-001, #105)

v4.1 cycle highlights:
- v4.1.0: `match` expression for value dispatch (#308) and `break`/`continue` loop control (#309) — the first new language syntax since v4.0; async agent calls (#294); workflow resume fixes (#322, #328)
- v4.1.1: closures passed to a module function inside a list, map, or record now run against the caller's bytecode instead of the module's (ASYNC-MOD-003, #339). This affected every `.nd` library taking callbacks in a container, not just the stdlib; `std:async.parallel`/`series` work as a result

Previous: v3.0.2 (shipped 2026-05-25; eval score 7.57/10).

## v5.0 (planned)

Long-term roadmap for Tier 2 infrastructure libraries and Tier 3 agent
runtime libraries. 10 deferred items tracked on the v5.0 milestone. See
`docs/governance/LIBRARY_ECOSYSTEM.md` for the three-tier library
ecosystem architecture.

## Bootstrapping (long-term goal)

Nodus is going to bootstrap itself — to compile itself in itself. The compiler
and core runtime get rewritten in Nodus: lexer, parser, AST lowering, bytecode
generation, and VM evaluation.

This is a long-term goal, not a near-term one, and the distinction matters in
only one direction: it is far off, not undecided. It is a direction the language
is being built toward, and it already constrains design today. A feature that
would make bootstrapping impossible, or that would need a separate "systems"
subset to work around, is treated as a signal that the abstraction level is
wrong — that is a rule with teeth, not a preference.

**Where it stands.** `examples/expr_compiler.nd` is a working lexer,
recursive-descent parser and evaluator written entirely in Nodus, so the shape
of the task is already expressible. What is not yet in place:

- **Throughput.** Roughly **400K instructions/sec** on CPython 3.11 (1,000,000
  loop iterations = 17,000,021 instructions; best of three trials). Self-hosting
  means the compiler compiling itself, and the pipeline is ~2,300 lines of
  lexer/parser/AST plus ~1,900 lines of compiler.

  **Under PyPy the same probe runs ~23× faster — about 9.4M instr/sec — and Nodus
  needs no changes to run there** (its only dependency is `tzdata`). One bug
  blocks the suite on PyPy, and it is a latent CPython defect rather than an
  incompatibility: the SQLite workflow store relies on refcounting to close
  cursors ([#516](https://github.com/Masterplanner25/Nodus/issues/516)).

  So throughput is still the blocker, but the question has moved from *can this
  ever be fast enough* to *which runtime*. See
  [#173](https://github.com/Masterplanner25/Nodus/issues/173). CPython 3.14 is
  within noise of 3.11 on this workload — there is no free win from upgrading.
- **String slicing.** `std:strings` has no substring or slice, so a lexer must
  index character by character. `expr_compiler.nd` does exactly that and says so.
- **Closure upvalue mutation** ([#156](https://github.com/Masterplanner25/Nodus/issues/156)).
  Compiler state threads through the map-mutation workaround instead of being
  written directly.
- **Module privacy** ([#158](https://github.com/Masterplanner25/Nodus/issues/158)).
  Every top-level function is public, so a self-hosted compiler cannot keep
  helpers internal.

What *is* in place is the part usually hardest to retrofit: the semantics are
stable, and the 49-opcode instruction set has been frozen at
`BYTECODE_VERSION` 4 since v1.0.

---

# What Nodus Is Not

- A general-purpose ecosystem language like Python or JavaScript
- A low-level systems runtime
- A heavy type-first language

Nodus is an automation scripting and orchestration runtime with a small, clear core.
