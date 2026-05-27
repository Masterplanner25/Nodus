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

## Current Release (v3.0.2)

Shipped 2026-05-25. Three patches in the v3.0 cycle:
- v3.0.0: Integer type, error replacement, map/record disambiguation
- v3.0.1: 21 of 22 v3.0.0 eval bugs fixed
- v3.0.2: BUG-V31E-01 (1I parse error) and BUG-V31E-02 (math.log arg swap)

Current eval score: 7.57/10 (composite weighted, 21 dimensions).

## v4.0 (in progress)

Theme: Production-Ready Orchestration DSL.

Three coordinated release artifacts:
- `nodus-lang` 4.0.0 (PyPI)
- `nodus-mcp` v0.1 (registry; MCP 2025-11-25 spec)
- `nodus-a2a` v0.1 (registry; A2A v1.0.0 spec)

Phase 0 (17 design decisions) and Phase 1 (13 design docs) complete.
Phase 2 (non-breaking fixes), Phase 3 (breaking changes + new stdlib),
Phase 4 (docs sweep), Phase 5 (coordinated release) in progress.

Target eval score: ≥8.0/10 with stretch goal toward 9.5/10
"production-ready architecturally."

See `docs/governance/V4_0_PLAN.md` for the cycle plan and
`docs/design/v4/` for the 13 design docs.

## v5.0 (planned)

Long-term roadmap for Tier 2 infrastructure libraries and Tier 3 agent
runtime libraries. 10 deferred items tracked on the v5.0 milestone. See
`docs/governance/LIBRARY_ECOSYSTEM.md` for the three-tier library
ecosystem architecture.

---

# What Nodus Is Not

- A general-purpose ecosystem language like Python or JavaScript
- A low-level systems runtime
- A heavy type-first language

Nodus is an automation scripting and orchestration runtime with a small, clear core.
