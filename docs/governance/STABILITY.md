# Nodus Stability Policy

> **v1.0 (2026-03-15): The Nodus opcode set is frozen. All 47 active opcodes are stable.**
> This document reflects stability classifications as of the v1.0 release.

This document summarizes which parts of the language are considered stable, mostly stable, or experimental.

## Stability Levels

- Stable: behavior and syntax are expected to remain compatible.
- Mostly stable: minor refinements may occur; avoid breaking changes when possible.
- Experimental: semantics or syntax may change; do not rely on long-term compatibility.

## Stable

- Core declarations: `let`, `fn`
- Blocks and statement separators
- Control flow: `if`, `while`, `for (init; cond; inc)`, `return`, `try/catch/finally`, `throw`
- Literals: numbers, strings, booleans, `nil`
- Operators: arithmetic, comparisons, `&&`, `||`, `!`, unary `-`
- Lists and maps (literals, indexing, assignment)
- Basic import/export syntax
- VM execution model

## Mostly Stable

- `for name in iterable` iteration protocol
- Record value model (field access and methods)
- Module visibility rules (exports vs legacy behavior)
- Runtime module system (module loader, module objects, per-module bytecode units)
- Package manager behavior and lockfile semantics

## Experimental

- Workflows and goals (`workflow`, `goal`, `step`, `checkpoint`)
- `action` expressions inside steps
- Task graph runtime and persistence semantics
- Coroutines, scheduler, and channels
- Runtime service APIs (tools/agents/memory/events)
- Optional type annotations and static analysis

## Notes

- The module system uses runtime module loading and per-module bytecode units. Import syntax remains stable.
- Records vs maps may be clarified or retyped in the type system before a syntax freeze.
