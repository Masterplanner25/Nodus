# Nodus Formatting Guide

This document defines the official formatting style for Nodus and the scope of `nodus fmt`.

## Style Rules

- Indentation: 4 spaces per block level.
- Operators: single spaces around binary operators (`+ - * / == != < > <= >= && || =`).
- Commas: single space after commas.
- Braces: opening brace on the same line as `if/while/for/fn`; closing brace on its own line.
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

The following AST expression node types are handled by `format_expr()`:
`Num`, `Bool`, `Str`, `Nil`, `Var`, `Assign`, `Unary`, `Bin`, `Call`, `Attr`,
`Index`, `IndexAssign`, `ListLit`, `MapLit`, `FnExpr`, `FieldAssign`,
`RecordLiteral`, `ActionStmt`.

The following node types are intentionally **not** handled in `format_expr()`
because they are statement-level constructs, not expression values:
- `Yield`, `TryCatch`, `Throw` — parsed by `stmt()`, never appear as sub-expressions.
- `DestructureLet` — a destructuring `let` binding, statement-level only.
- `VarPattern`, `ListPattern`, `RecordPattern` — pattern nodes used inside
  `DestructureLet`; not standalone expressions.

## Scope and Limitations

The formatter focuses on Nodus features currently supported by the parser/AST. It does not attempt to preserve original layout, spacing, or comments beyond the formatting rules above. Trailing comments remain best-effort rather than a full comment layout engine. The formatter is deterministic and idempotent.
