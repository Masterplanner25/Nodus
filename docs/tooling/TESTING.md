# Testing Nodus

**Last reviewed:** 2026-09-07, against 5.12.0

This document describes testing philosophy and how to run and write tests for the Nodus language.

## Testing Philosophy

- Prefer fast, deterministic tests that exercise the compiler/VM end-to-end.
- Use unit tests for isolated parser/compiler behavior and regression coverage.
- Use golden and snapshot tests for outputs that must remain stable (IR/bytecode and diagnostics).
- Avoid tests that depend on real time, network, or external services.

## Running Tests

Run the full suite (preferred — matches CI):

```bash
PYTHONPATH="C:/dev/Coding Language/src" python -m pytest tests/ -q
```

Run a single test module:

```bash
PYTHONPATH="C:/dev/Coding Language/src" python -m pytest tests/test_task_graph.py -v
```

Run a single test case:

```bash
PYTHONPATH="C:/dev/Coding Language/src" python -m pytest tests/test_task_graph.py::TaskGraphTests::test_task_retry_success -v
```

The suite also supports `python -m unittest discover -s tests -v` — CI runs both runners. Use pytest for coverage reporting and selective deselection of timing-sensitive tests.

Run the installed-wheel smoke validation:

```bash
NODUS_RUN_DIST_SMOKE=1 python -m unittest tests.test_distribution_smoke -v
```

This builds a wheel, installs it into a fresh virtual environment, and validates the
installed `nodus` CLI without relying on repo-local `src/` imports.

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
from nodus.frontend.lexer import tokenize
from nodus.frontend.parser import Parser
from nodus.frontend.ast.ast_nodes import Let, Num

src = "let x = 1"
ast = Parser(tokenize(src)).parse()
assert isinstance(ast[0], Let)
assert isinstance(ast[0].expr, Num)
```

Note the module paths. Bare `lexer` / `parser` / `ast_nodes` do not resolve —
an earlier revision of this page used them, and `parser` in particular is the
name of a long-removed Python stdlib module, so the failure reads oddly. The AST
nodes are one level deeper than the rest of the frontend:
`nodus.frontend.ast.ast_nodes`.

Prefer minimal sources and explicit assertions over snapshotting the entire AST unless you are testing a broad grammar change.

## Writing Compiler Tests

Compiler tests should validate bytecode structure and runtime behavior.

Recommended pattern:

1. Compile with `ModuleLoader` (canonical) or `compiler.Compiler`.
2. Validate opcode sequences in the emitted bytecode.
3. Optionally execute with `vm.VM` and assert results.

Example:

```python
# Preferred: use ModuleLoader directly
from nodus.runtime.module_loader import ModuleLoader

loader = ModuleLoader(project_root=None)
code, functions, code_locs = loader.compile_only("let x = 1i", module_name="<memory>")

# `code` is a dict, not a list of instructions -- index it by key first.
assert code["instructions"][1][0] == "PUSH_CONST"

# For embedding use cases: use NodusRuntime
from nodus.runtime.embedding import NodusRuntime

runtime = NodusRuntime()
result = runtime.run_source("let x = 1i")
assert result["ok"] is True          # run_source returns a dict; it does not raise
```

`compile_only` returns `(code, functions, code_locs)` where `code` carries
`bytecode_version`, `module_name`, `instructions`, `constants`, `exports` and
`metadata`. An earlier revision asserted `code[0][0] == "PUSH_CONST"`, which
raises `KeyError: 0`. Instruction `0` is the module prologue `("JUMP", 1)`, so
the first instruction of the program itself is at index 1.

Note: `compile_source()` is fully removed as of v1.0 (public re-export in v0.9.0,
function body in v1.0). New tests must use `ModuleLoader` or `NodusRuntime`. See
`DEPRECATIONS.md` for the migration guide.

Keep compiler tests focused on specific lowering behavior (e.g., short-circuiting, destructuring, closures).

## Golden File Tests for IR/Bytecode

Use golden tests when the exact emitted IR/bytecode must remain stable.

`tests/test_bytecode_golden.py` already does this for the core constructs, with
fixtures under `tests/fixtures/bytecode/`. After an intentional compiler change,
regenerate rather than hand-editing:

```bash
NODUS_UPDATE_GOLDEN=1 python -m pytest tests/test_bytecode_golden.py -q
```

For a new golden test of your own:

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

## CI Pipeline

`ci.yml` runs **three** parallel jobs: `security`, `probes` and `test`.

**Security job** — the sandbox and path-traversal files only:

```bash
python -m pytest -q \
  tests/test_cli_allowed_paths.py tests/test_fs_path_traversal.py \
  tests/test_path_traversal.py tests/test_sandbox_filesystem.py \
  tests/test_sandbox_limits.py tests/test_subprocess_sandbox.py
```

**Probes job** — the Gate 10b release-claims probes, run against a wheel it
builds, from a temp directory, with `--require-installed`. About 18s, and off
the `test` job's critical path. It does not replace Gate 10b at release time; it
removes the window where a probe could go stale unnoticed.

**Test job** — fifteen steps, in order:

1. Set up Python
2. Install dependencies
3. Install completion shells (`zsh`, `fish` — the completion tests need them)
4. **Lint** — `ruff check .`, with `ruff` pinned to an exact version on purpose
5. **Type check** — `mypy src/nodus/ --ignore-missing-imports --no-error-summary`
6. **Check .nd formatting** — `python -m tools.check_nd_format`
7. **Static checks** — `python nodus.py check` on the example files
8. **Doc-vs-code gate** — `python -m tools.nodus_gate.cli --all`
9. **Unit tests** — `python -m unittest discover -s tests -v`
10. **Pytest** — `python -m pytest -q`
11. **Coverage** — `--cov=src/nodus --cov-fail-under=70`, timing-sensitive tests deselected
12. Install build tooling
13. **Build wheel** — `python -m build --wheel`
14. **Installed wheel smoke test** — `python -m unittest tests.test_distribution_smoke -v`
15. **Example suite** — `python nodus.py test-examples`

Steps 9 and 10 are not redundant: the two runners have caught different
failures. During the #411 work CI's unittest step failed on two tests pytest
passed locally, because of an optional extra present in the dev environment and
absent on a clean runner. **A local pytest run substitutes for neither.**

### Checking `.nd` formatting

Run the same thing CI runs:

```bash
python -m tools.check_nd_format
```

`tools/check_nd_format.py` answers both halves of the question — which files are
in scope, and whether each is formatted — so CI, the pre-commit hook and you all
call one thing and there is nothing to keep in step. It delegates the second half
to `nodus fmt --check`'s own code path, so the gate cannot disagree with the
command it gates. One process rather than one per file: roughly 4s.

> **Do not reconstruct the file list by hand.** An earlier revision of this page
> gave a `find … | xargs python nodus.py fmt --check` recipe with the exclusions
> spelled out. That is the same mistake the old pre-commit hook made — it
> restated CI's list in its own words, got the exclusions wrong, and blocked
> commits on `tests/fixtures/fmt/`, where inputs are unformatted on purpose.

To rewrite a file in place, and to confirm it:

```bash
python nodus.py fmt <file>
python nodus.py fmt --check <file>
```

**Always `python nodus.py fmt`, never `nodus.exe fmt`.** CI loads the formatter
from `src/`; `nodus.exe` in `.venv` is whatever release was last installed there.
Using the wrong one writes a format that diverges from what CI checks, which is
the writer-vs-checker split that broke the format gate repeatedly.

## Formatter Test Files

Eleven modules cover the formatter. **Two of them are the ones that make new
work fail loudly, and they are the two to understand:**

- `tests/test_formatter_completeness.py` — walks the AST node list, so a **new
  node type** with no formatter case fails the suite. This is the guard added
  after `nodus fmt` was found writing output that no longer parsed.
- `tests/test_formatter_round_trip.py` — formats, reparses, and compares the AST
  field by field. **A completeness guard at node granularity does not cover
  field granularity**, and 5.6.0 shipped two defects underneath one: `each` and
  `budget { limits: … }` are new *fields* on existing nodes, so every node still
  had a formatter case, the suite stayed green, and `fmt` silently dropped them.
  Not a crash and not a refusal — valid output, different program. When you add
  a field to an AST node, this is the test that protects it.

The rest cover specific behaviours:

- `test_formatter_fixtures.py` — fixture round-trips for comments, import/export
  layout, unary expressions and numeric literals. Fixtures live under
  `tests/fixtures/fmt/`.
- `test_formatter_foreach.py` — `for … in` statement formatting.
- `test_formatter_fnexpr.py` — anonymous function expressions: empty bodies,
  single-statement inline bodies, return-type annotations, multi-statement
  blocks, and use as a call argument (`spawn(fn() { … })`).
- `test_formatter_coverage.py` — node handlers that once lacked coverage:
  `yield` (with and without an expression), `throw`, `try`/`catch`, and
  list/record/nested destructuring patterns.
- `test_formatter_comment_placement.py`, `test_formatter_header_comments.py`,
  `test_formatter_keep_trailing.py` — comment handling, including
  `--keep-trailing`.
- `test_formatter_idempotence.py` — formatting twice changes nothing.
- `test_formatter_nested_indent.py` — indentation of nested constructs.

To add a formatter regression test, add a fixture pair under
`tests/fixtures/fmt/` and reference it in `test_formatter_fixtures.py`, or add a
`unittest.TestCase` method in the relevant `test_formatter_*.py` module.

## Known Flaky Tests

**None outstanding.** Three tests were flaky here and all three are fixed. What
is worth keeping is how to reproduce this class of failure, because the obvious
method does not work.

**Neither ever failed from repetition — only under load.** So *"it passed when I
ran it again"* was never evidence about any of them, and an idle box passes
indefinitely. An earlier revision of this page recommended re-running the test in
isolation as the diagnostic; that is the one thing guaranteed to tell you
nothing.

**To reproduce: load the machine, do not re-run the test.** Burn every core but
one in a background process, then run the file. And keep the control inside the
same load window — a first attempt at one of these showed the *unfixed* tests
passing 5 of 6 with runtimes falling from 1.75s to 0.49s, because the load
generator had expired partway and the comparison measured nothing. Run both
variants inside one window and check the durations stayed up.

| Test | What it actually was |
|---|---|
| `test_scheduler_fairness.py` | Never a fairness failure. The run was killed by the 200 ms wall-clock `EXECUTION_TIMEOUT_MS` before the ordering assertion was reached, so the test was asserting the box could run 8000 iterations in 200 ms. The harness sets its own generous deadline now, in one helper so a later test cannot forget it. **Both** tests in the file were affected. |
| `test_server.py::…test_workflow_run_uses_sqlite_store_when_configured` | Read as a tempdir race and was not one: the store was still open when the directory was removed, and `SQLiteWorkflowStore` had no `close()`. `RuntimeService.close()` waits for its sweeper now. |
| `test_task_graph.py::test_task_reassignment_after_worker_failure` | The tightest budget in the tree. `_worker_heartbeat_timeout_ms` was **20 ms** and had to cover a thread starting, compiling, and reaching `submit()`. `wait_for_job` marks the worker *seen*, which cancels the 250 ms `_startup_grace_ms` that would otherwise have covered it — so the worker was evicted and the first assertion saw `{"job_id": None}`. The death the test simulates is the *backdating*, not this timeout, so the timeout is large now (2 s) and the backdate far past it (60 s). |

The last one had been declared fixed once before, in a much earlier release, by a
change that made `_poll_job` block on a condition variable instead of polling.
That change was real and did not cover this; a symptom recurring after a genuine
fix is a reason to ask **how many things do that**, not whether the fix regressed.

Do not re-harden `test_async_concurrency_timing.py`, `test_ieee754_division.py`
or `test_workflow_dsl.py` — those were fixed separately and are not on this list.

### A local full-suite run is not a gate

This box's timing has been intermittently bad in ways that have never been fully
explained: subprocess tests with 10s timeouts failing intermittently with a
different test named each run, and wall-clock drifting from ~7 to ~18 minutes
with nothing else running, while CI on a clean runner passed every PR in 5–6
minutes. It comes and goes within a single day, so **one clean measurement does
not clear it.**

Prefer targeted runs over the areas you touched, then push and let CI arbitrate.
If you see failures that move between runs and a suite that is suddenly twice as
slow, re-run the failing test alone and push — do not start bisecting your own
change.

**And check nothing else is running first.** The workflow store, graph registry
and bytecode cache all live under the repo-root `.nodus/`, resolved
CWD-relative, so two suites at once corrupt each other. The symptom looks exactly
like a real race — `PermissionError: [WinError 5]` on `.nodus/graphs/*.tmp`
renames, and a different test failing each run. This extends past `pytest`: the
doc gate (`nodus_gate --runtime`) executes every documented block and writes to
the same store, and the dependent-suite gate runs full companion suites that bind
ports. One thing at a time when a verdict is going to be believed.
