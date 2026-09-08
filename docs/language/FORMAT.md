# Nodus Formatting Guide

**Last reviewed:** 2026-09-08, against 5.12.0. Written 2026-03-15 for v1.0 and
unreviewed until now, so the style rules had not heard of `match`, `break`,
`continue`, compound assignment or the orchestration blocks, and the node-coverage
section named 45 of the 66 AST nodes. Both corrected; the rules below were
checked by running `nodus fmt` rather than by reading it.

This document defines the official formatting style for Nodus and the scope of `nodus fmt`.

## Style Rules

- Indentation: 4 spaces per block level.
- Operators: single spaces around binary operators (`+ - * / == != < > <= >= && || =`).
- Commas: single space after commas.
- Braces: opening brace on the same line as `if/while/for/fn`; closing brace on its own line.
- Block bodies are **always expanded**, even for a single statement. `if (x) { return 1i }`
  formats to three lines. This is deterministic rather than a judgement call, so
  two people hand-formatting the same code land in the same place.
- The one exception is a **function expression**: `let g = fn(a) { a + 1i }` keeps
  its single-statement body inline, because expanding it would break the
  expression it sits inside out over four lines for no gain.
- Blank lines: one blank line between top-level function declarations and after import groups.
- Imports:
  - `import "path"`
  - `import "path" as alias`
  - `import { a, b } from "path"`
- Exports:
  - `export let name = expr`
  - `export fn name(...) { ... }`
  - `export { a, b }`
  - `export { a, b } from "path"`
- Lists: `[a, b, c]`
- Maps: `{key: value, other: value}`
- Control flow:
  - `if (cond) { ... } else { ... }`
  - `while (cond) { ... }`
  - `for (init; cond; inc) { ... }`
  - `for x in items { ... }`
  - `break` / `continue` (v4.1.0)
  - `match value { ... }` — an expression, so it also formats in `let` position (v4.1.0)
  - `try { ... } catch e { ... } finally { ... }` — the parser accepts
    `catch (e)` too, and `fmt` normalises both to the unparenthesised form
- Compound assignment: `x += 1i`, and likewise `-=`, `*=`, `/=` (v4.0.1)
- Orchestration blocks — `workflow`, `goal`, `step`, `state`, and the goal
  `until` / `budget` clauses — format as nested blocks like any other. The
  step-level modifiers `after`, `each … in …`, `when`, `compensates` and
  `with { … }` stay on the declaration line.
- Function calls: `name(arg1, arg2)`
- Anonymous functions (FnExpr):
  - No params, empty body: `fn() {}`
  - Single-statement body: `fn(a, b) { a + b }` (inline)
  - With return type: `fn(a) -> Int { return a + 1 }` (inline)
  - Multi-statement body formatted as a block:
    ```
    fn(a, b) {
        stmt1
        stmt2
    }
    ```
  - As a call argument: `spawn(fn() { work() })`, `coroutine(fn(x) { x + 1 })`
- Field assignment (FieldAssign): `obj.field = value`
- Record literals (RecordLiteral): `record {name: "alice", age: 30}`
- Trailing newline: files always end with a single newline.

## Comment Policy

`nodus fmt` preserves line comments (`# ...` and `// ...`) by attaching them to the next statement. Trailing end-of-line comments are preserved and, by default, moved to their own line after the statement for deterministic output. Use `--keep-trailing` to keep them inline when possible.

## Formatter Regression Policy

Nodus protects formatting stability with fixture-based formatter tests. Complex cases such as unary expressions, comment-heavy blocks, trailing comments, and import/export layouts are covered by dedicated fixtures to reduce regressions across releases. Fixture cases live under `tests/fixtures/fmt` and are exercised by the unittest suite.

## Numeric Literals

- Integer-looking numeric literals remain integer-looking after formatting when the formatter is working from parsed source tokens.
- Float literals keep their decimal spelling (for example, `1.0` stays `1.0`).
- Unary minus is formatted from a dedicated AST node, so negative literals and grouped unary expressions such as `-5` and `-(a + 1)` round-trip cleanly.
- The formatter does not infer richer numeric types; it preserves the original token spelling where available and otherwise falls back to canonical numeric rendering.

## Formatter Node Coverage

**This is checked, not listed.** `tests/test_formatter_completeness.py` walks the
AST node set in `nodus/frontend/ast/ast_nodes.py` and fails when a node type has
no formatter case, so the coverage question is answered by the suite rather than
by a paragraph here.

That is deliberate. A hand-written list of node types is a second copy of
something the code already knows, and this one rotted exactly as you would
expect: it named 45 nodes against the 66 the module defines, and the 21 it never
learned about included `Match`, `Break`, `Continue`, `CompoundAssign`, `Int`,
`InterpolatedString` and the whole `GoalPursuit` / `Reached` / `budget` family —
seven releases of language surface. Nothing was wrong with the formatter; the
list was simply not the thing being maintained.

`GoalPursuit` (#409) is why the test exists: it parsed, compiled and ran
correctly with a green suite, and `nodus fmt` died on it with a raw traceback,
because the per-node formatter tests are *examples* and a node with no example
has no test.

### Node coverage is not field coverage

The completeness test walks node **types**. It cannot see a new **field** on an
existing node, and 5.6.0 shipped two defects underneath it (#656, #657).

`each_var` / `each_source` were added to `WorkflowStep`, and `budget { limits: … }`
to a goal. Every node still had a formatter case, so the test stayed green while
`fmt` rewrote `each page in discover` as `after discover` — dropping the loop
variable — and lost a goal's budget bounds. Not a refusal and not a parse error:
valid output, a different program, in a published release.

`tests/test_formatter_round_trip.py` is what covers that. It formats, reparses,
and compares the AST field by field; it found #657 on its first run.

**When you add a field to an AST node, the round-trip test is what protects it.**
The node walker cannot.

### Yield

```
yield
yield <expr>
```

Used inside generator functions. The expression is optional.

### Throw

```
throw <expr>
```

Raises an exception with the given expression as the error value.

### TryCatch

```
try {
    <body>
} catch <var> {
    <handler>
}
```

With an optional finally clause:

```
try {
    <body>
} catch <var> {
    <handler>
} finally {
    <cleanup>
}
```

The `catch` clause binds the caught error to `<var>` for use in the handler
block. The `finally` clause, when present, always executes after the try or
catch block — including when a `return` statement executes inside the try block.

### DestructureLet (pattern bindings)

```
let <pattern> = <expr>
```

Patterns may be:
- A variable name: `let a = expr`
- A list pattern: `let [a, b] = expr`
- A record pattern: `let {key: varname, ...} = expr`
- Nested: `let [a, [b, c]] = expr`

## Scope and Limitations

The formatter focuses on Nodus features currently supported by the parser/AST. It does not attempt to preserve original layout, spacing, or comments beyond the formatting rules above. Trailing comments remain best-effort rather than a full comment layout engine. The formatter is deterministic and idempotent.
