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

Or with pytest:

```bash
pytest
```

Run a single test module:

```bash
python -m unittest tests.test_task_graph -v
```

Run a single test case:

```bash
python -m unittest tests.test_task_graph.TaskGraphTests.test_task_retry_success -v
```

## Warnings During Tests

Some optional dependencies may emit deprecation warnings during the test run (for example, Starlette multipart parsing or legacy websockets APIs). These warnings do not indicate test failures and can be safely ignored unless the warnings become errors in CI. If warnings become noisy, consider pinning or upgrading the related dependency in the test environment.

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

1. Compile with `ModuleLoader` (canonical) or `compiler.Compiler`.
2. Validate opcode sequences in the emitted bytecode.
3. Optionally execute with `vm.VM` and assert results.

Example:

```python
from loader import compile_source  # deprecated since v0.5; prefer ModuleLoader

src = "let x = 1 + 2"
_ast, code, functions, code_locs = compile_source(src)
assert code[0][0] == "PUSH_CONST"
```

Note: `compile_source()` is deprecated since v0.5 and will be removed in v1.0. New
tests should use `ModuleLoader(...).load_source(src)` instead. See `DEPRECATIONS.md`
for the migration guide.

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

## CI Format Check and Auto-format

The CI pipeline (`ci.yml`) runs a format check across all `.nd` files. The workflow
steps run in this order:

1. **Checkout** — fetch the repository.
2. **Setup Python** — install the required Python version.
3. **Install dependencies** — install package and test dependencies.
4. **Auto-format all .nd files** — runs `python nodus.py fmt` on every `.nd` file in the repo
   (in-place, no `--check` flag), excluding `.git/`, `.venv/`, `tmp_demo/`, and
   `tests/fixtures/fmt/` (formatter test fixtures that are intentionally non-canonical).
5. **Commit formatted files** — if any file was changed by the formatter, CI commits it back
   with the message `style: auto-format .nd files [skip ci]`. The `[skip ci]` tag prevents the
   commit from re-triggering the workflow. The commit step is a no-op when files are already
   correctly formatted — `git diff --quiet` exits 0 and nothing is committed.
6. **Format check** — runs `python nodus.py fmt --check` across all `.nd` files in the repo.
7. **Run tests** — runs the full unittest suite (`python -m unittest discover -s tests -v`).

The auto-format commit only appears when a contributor adds or edits a `.nd` file without
running the formatter locally first. To avoid these auto-commits, format before pushing:

```bash
find . -name "*.nd" \
  -not -path "./.git/*" \
  -not -path "./.venv/*" \
  -not -path "./tmp_demo/*" \
  -not -path "./tests/fixtures/fmt/*" \
  | xargs -I {} python nodus.py fmt {}
```

If the format check fails locally, fix the file and re-check:

```bash
python nodus.py fmt <file>          # rewrite in-place
python nodus.py fmt --check <file>  # confirm it now passes
```

Or check all .nd files at once (matching CI scope):

```bash
find . -name "*.nd" \
  -not -path "./.git/*" \
  -not -path "./.venv/*" \
  -not -path "./tmp_demo/*" \
  -not -path "./tests/fixtures/fmt/*" \
  | xargs -I {} python nodus.py fmt --check {}
```

Note: only `.nd` files are checked. `tests/fixtures/fmt/` is excluded because it contains
formatter test fixtures that are intentionally non-canonical (e.g. `--keep-trailing` mode
inputs and outputs).

## Formatter Test Files

Formatter behaviour is covered by several test modules:

- `tests/test_formatter_fixtures.py` — fixture-based round-trip tests for comment handling,
  import/export layout, unary expressions, and numeric literals. Fixtures live under
  `tests/fixtures/fmt/`.
- `tests/test_formatter_foreach.py` — inline test for `for … in` statement formatting.
- `tests/test_formatter_fnexpr.py` — tests for anonymous function expression (`FnExpr`)
  formatting, including empty bodies, single-statement inline bodies, return-type annotations,
  multi-statement block bodies, and use as call arguments (`spawn(fn() { … })`).

To add a formatter regression test, either add a new fixture pair to `tests/fixtures/fmt/`
and reference it in `test_formatter_fixtures.py`, or add a `unittest.TestCase` test method in the relevant
`test_formatter_*.py` module.
