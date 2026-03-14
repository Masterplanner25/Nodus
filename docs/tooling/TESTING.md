# Testing Nodus

This document describes testing philosophy and how to run and write tests for the Nodus language.

## Testing Philosophy

- Prefer fast, deterministic tests that exercise the compiler/VM end-to-end.
- Use unit tests for isolated parser/compiler behavior and regression coverage.
- Use golden and snapshot tests for outputs that must remain stable (IR/bytecode and diagnostics).
- Avoid tests that depend on real time, network, or external services.

## Running Tests

Run the full suite:

```bash
python -m unittest discover -s tests -v
```

Run a single test module:

```bash
python -m unittest tests.test_task_graph -v
```

Run a single test case:

```bash
python -m unittest tests.test_task_graph.TaskGraphTests.test_task_retry_success -v
```

## Writing Parser Tests

Parser tests should focus on AST structure and syntax errors.

Recommended pattern:

1. Tokenize and parse source with `lexer.tokenize` and `parser.Parser`.
2. Assert the AST node types and key fields.
3. For syntax errors, assert error message, line, and column.

Example:

```python
from lexer import tokenize
from parser import Parser
from ast_nodes import Let, Num

src = "let x = 1"
ast = Parser(tokenize(src)).parse()
assert isinstance(ast[0], Let)
assert isinstance(ast[0].expr, Num)
```

Prefer minimal sources and explicit assertions over snapshotting the entire AST unless you are testing a broad grammar change.

## Writing Compiler Tests

Compiler tests should validate bytecode structure and runtime behavior.

Recommended pattern:

1. Compile with `loader.compile_source` or `compiler.Compiler`.
2. Validate opcode sequences in the emitted bytecode.
3. Optionally execute with `vm.VM` and assert results.

Example:

```python
from loader import compile_source

src = "let x = 1 + 2"
_ast, code, functions, code_locs = compile_source(src)
assert code[0][0] == "PUSH_CONST"
```

Keep compiler tests focused on specific lowering behavior (e.g., short-circuiting, destructuring, closures).

## Golden File Tests for IR/Bytecode

Use golden tests when the exact emitted IR/bytecode must remain stable.

Suggested workflow:

1. Generate disassembly using `compiler.build_disassembly` or `nodus dis`.
2. Write output to a fixture file under `tests/fixtures/`.
3. Compare current output to the fixture in the test.

Guidelines:
- Keep fixtures small and focused.
- Update golden files only when semantics intentionally change.
- Include a brief comment in the test explaining the expected change.

## Snapshot Tests for Error Messages

Use snapshot tests for diagnostics where exact wording and formatting are part of the contract.

Suggested workflow:

1. Run code that triggers a specific error.
2. Capture `diagnostics.format_error` output or structured error dicts from `runner`.
3. Compare against a stored snapshot string or JSON fixture.

Guidelines:
- Snapshots should include line/column and file context when applicable.
- Keep snapshots small and avoid volatile data (timestamps, ids).
- If changing error text, update snapshots and note the reason in the test.

## Test Structure Conventions

- Tests live under `tests/`.
- Formatter fixtures live under `tests/fixtures/fmt`.
- Prefer one concept per test for clarity and maintainability.
