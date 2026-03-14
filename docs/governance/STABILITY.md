# Nodus Stability Policy

This document summarizes which parts of the language are considered stable, mostly stable, or experimental. It is intended to guide a future 1.0 syntax freeze.

## Stability Levels

- Stable: behavior and syntax are expected to remain compatible.
- Mostly stable: minor refinements may occur; avoid breaking changes when possible.
- Experimental: semantics or syntax may change; do not rely on long-term compatibility.

## Stable

- Core declarations: `let`, `fn`
- Blocks and statement separators
- Control flow: `if`, `while`, `for (init; cond; inc)`, `return`, `try/catch`, `throw`
- Literals: numbers, strings, booleans, `nil`
- Operators: arithmetic, comparisons, `&&`, `||`, `!`, unary `-`
- Lists and maps (literals, indexing, assignment)
- Basic import/export syntax

## Mostly Stable

- `for name in iterable` iteration protocol
- Record value model (field access and methods)
- Module visibility rules (exports vs legacy behavior)

## Experimental

- Workflows and goals (`workflow`, `goal`, `step`, `checkpoint`)
- `action` expressions inside steps
- Task graph runtime and persistence semantics
- Coroutines, scheduler, and channels
- Runtime service APIs (tools/agents/memory/events)
- Optional type annotations and static analysis
- Package manager behavior and lockfile semantics

## Notes

- The current module system uses compile-time flattening and alias rewriting. The syntax is stable, but the runtime model is expected to change before 1.0.
- Records vs maps may be clarified or retyped in the type system before a syntax freeze.
