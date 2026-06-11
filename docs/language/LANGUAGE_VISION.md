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

## Current Release (v4.0.2)

Shipped 2026-06-10 on PyPI (`pip install nodus-lang`).

v4.0 cycle highlights:
- v4.0.0: AI-native stdlib (std:tool, std:identity, std:effects, std:sys, std:memory, std:retry, std:circuit_breaker), HandlerContract infrastructure, full ecosystem of 29 companion packages
- v4.0.1: NodusRuntime sandbox defaults hardened (SCHED-001 fixed, timeout_ms → None, allowed_paths → CWD), httpx optional, integer division returns int, div/zero raises error, compound assignment operators, multiline expressions, @annotation syntax
- v4.0.2: Bug fixes for @exactly_once, allowed_commands, @retry, event_sinks, trailing commas

Previous: v3.0.2 (shipped 2026-05-25; eval score 7.57/10).

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
