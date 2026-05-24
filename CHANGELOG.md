# Changelog

## [Unreleased]

## [2.0.1] - 2026-05-23

### Security
- **BUG-016 — path traversal in `fs.*` builtins (CRITICAL):** `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, and `exists` now enforce a filesystem root in CLI mode. When no `allowed_paths` sandbox is active, scripts are restricted to the process working directory (or the `nodus.toml` project root when one is discovered). Paths that resolve outside this root raise a `sandbox` runtime error. Previously, any script could read or write arbitrary files on the host machine regardless of where `nodus run` was invoked.

### Fixed
- **BUG-017 — Python traceback on UTF-8 BOM files (CRITICAL):** Source files that begin with a UTF-8 BOM (`\xef\xbb\xbf`) — commonly produced by Windows editors — previously caused a raw Python `SyntaxError` or `UnicodeDecodeError` crash rather than a clean Nodus error. All file-read paths (`cli.py`, `module_loader.py`, `embedding.py`, `builtins/io.py`) now open files with `encoding="utf-8-sig"`, which transparently strips the BOM before parsing. `read_file()` also strips BOMs from data files read at runtime.
- **BUG-007 — `RecursionError` on 100+ nested parentheses (CRITICAL):** Deeply nested expressions (e.g. `((((…))))` with 100+ levels) caused Python's recursion limit to be exceeded, surfacing as an unhandled `RecursionError` traceback. The parser now tracks expression nesting depth and raises a `LangSyntaxError("Expression too deeply nested")` at depth 50, well before Python's stack limit is reached.

### Changed
- **PyPI classifier downgrade:** `Development Status :: 5 - Production/Stable` → `Development Status :: 4 - Beta`. The v2.0.0 stress-test evaluation revealed three CRITICAL bugs that disqualify a Production/Stable rating.

## [2.0.0] - 2026-05-23

### Fixed
- **CI lint regression (Phase 5A):** Two ruff errors introduced in Phase 6 test additions (commit `0568185`) caused the `ruff check .` CI gate to exit 1. Fixed `tests/test_run_trace.py:64` (E741: renamed ambiguous loop variable `l` -> `line`) and `tests/test_workflow_unification.py:56` (F841: removed unused `exit_code` assignment from `test_workflow_no_args_shows_usage`). `ruff check .` now exits 0.
- **`--trace-imports` Windows encoding crash (Phase 5B):** `src/nodus/runtime/module_loader.py` used the Unicode arrow `→` (U+2192) in the `[import] Resolved` output line and an em dash `—` (U+2014) in the `[import] Failed` line. Both characters are non-ASCII; the arrow is not encodable in Windows CP1252, causing `UnicodeEncodeError` when `--trace-imports` wrote to a CP1252 terminal. Replaced `→` with `->` and `—` with `--` (ASCII equivalents). Existing tests were unaffected because they redirect stderr to `io.StringIO()`.
- **CHANGELOG.md E402 count discrepancy (Phase 5B):** Corrected the E402 fix count in the Refactoring section from 8 to 11. The actual count resolved in commit `b9e6418` was 11, matching the git commit message and AUDIT_REPORT_2.md baseline.
- **TECH_DEBT.md vm.py line count stale (Phase 5B):** Updated from "2,418 lines as of v1.1.2" to "2,438 lines as of v1.1.2 (post-Phase 6)" to reflect the +20 lines added for `builtin_memory_has` in Phase 6.

### Documentation
- **README.md: JSON-LD structured metadata (Phase 5C):** Added a `<script type="application/ld+json">` block at the end of `README.md` with `schema.org/SoftwareApplication` metadata (name, description, author, category, language, OS, URLs, license, version, Python requirement). Improves discoverability by AI indexers and search engines.
- **LANGUAGE_SPEC.md: `--strict` flag and `nodus status` added (Phase 5B):** Added a "Run mode flags" entry documenting `--strict` (disables project auto-discovery, requires explicit file path) and `--trace-imports` (ASCII format). Added `nodus status` to the CLI commands section describing its three-field output and always-zero exit behavior.

### Added
- **AUTHORS file (Phase 5C):** Added `AUTHORS` at the project root listing Shawn Knight as the sole author with a GitHub profile link. Standard file for PyPI/GitHub attribution.
- **Cross-platform documentation (Task 7.2):** Audited `CONTRIBUTING.md` and `docs/onboarding/DEVELOPMENT.md` for shell commands that differ between bash and PowerShell. All three bash-only constructs in `CONTRIBUTING.md` now have adjacent PowerShell equivalents: `source .venv/bin/activate` ↔ `.venv\Scripts\Activate.ps1` (pre-existing), `pip install dist/*.whl` ↔ `pip install (Get-Item dist\*.whl).FullName` (added by Task 7.1), and `NODUS_RUN_DIST_SMOKE=1 python -m pytest ...` ↔ `$env:NODUS_RUN_DIST_SMOKE = "1"; python -m pytest ...` (added by Task 7.1). `DEVELOPMENT.md` contains no platform-diverging shell commands (all invocations use `nodus <tool> file.nd` or `python` forms that are identical across platforms); no changes required.
- **CI distribution validation (Task 7.1):** CI pipeline now has an explicit `Build wheel` step (`python -m build --wheel`) that runs after `Install build tooling` and before the smoke test, making the wheel build visible as its own CI step. The `Installed wheel smoke test` step was already gated by `NODUS_RUN_DIST_SMOKE: "1"` and creates an isolated venv for clean-install verification. Added `nodus --help` smoke check to `tests/test_distribution_smoke.py` (verifies exit 0 and "Usage" in stdout). Updated `_build_wheel` to reuse a pre-built wheel from `dist/` when available (avoids a redundant second build in CI). `CONTRIBUTING.md` updated with a new "Distribution Testing" section documenting the wheel build and smoke-test commands.
- **Execution trace format update (Task 6.2):** `nodus run --trace` now writes opcode trace lines to **stderr** (previously stdout) with the format `[trace] <OPCODE padded to 14 chars>  line N  <context>`. Opcode-specific context: `CALL` shows `fn=<name>`, `LOAD`/`STORE` show `name=<var>`, `LOAD_FIELD`/`STORE_FIELD` show `field=<name>`, `PUSH_CONST` shows `val=<repr>`, `JUMP` shows `target=<ip>`. `--trace-no-loc` omits the `line N` field. Existing `--trace-filter` and `--trace-limit` flags are unchanged. Three existing tests in `tests/test_nodus.py` updated to capture stderr; 6 new tests added in `tests/test_run_trace.py`. `_COMMAND_HELP["run"]` updated to note high-volume stderr output.
- **Memory API stabilization (Task 6.1):** Added `memory_has(key)` top-level builtin and `has(key)` method to `std:memory`. The previous `has` implementation incorrectly used `value != nil` and returned `false` when `nil` was stored under a key; it now calls `memory_has` which checks key existence directly. `memory_has` is registered in `BUILTIN_NAMES`, the VM builtin dispatch, and `memory_runtime.py`. All four stable methods (`put`, `get`, `delete`, `has`) and their top-level counterparts are now fully tested. Non-string keys raise a runtime `TypeError` across all methods. `LANGUAGE_SPEC.md` updated with a dedicated Memory API section. Tests added in `tests/test_memory_api.py` (19 tests).
- **Path traversal error message improvement (Task 5.1):** The error raised when a relative import would escape the project root now names the offending path: `Invalid import: path '../outside.nd' escapes the project root.` Previously the message did not include the path. The check continues to fire before any filesystem access, in both project mode (explicit `nodus.toml`) and single-file mode (no manifest, root defaults to entry file's directory). Tests added in `tests/test_path_traversal.py` (6 tests covering: project-mode rejection, error message names the path, in-tree relative import accepted, double-dot chain blocked, single-file-mode rejection, single-file in-tree accepted). `LANGUAGE_SPEC.md` and `docs/governance/TECH_DEBT.md` updated.
- **REPL import parity verified and tested (Task 5.2):** The REPL uses the same `ModuleLoader` and `resolve_import_path` code path as CLI execution. Automated tests in `tests/test_repl_import_parity.py` confirm: (1) bare project-root-relative imports resolve from project root in the REPL, (2) path traversal (`../outside.nd`) is blocked in the REPL with the same error as CLI, (3) `lib/index.nd` fallback resolution works in the REPL. No separate REPL import code path exists or was introduced.
- **CLI help system (Task 1.1):** Every primary subcommand now has a per-command `--help` that shows usage, a one-sentence description, all options with descriptions, and at least two examples. Commands covered: `run`, `repl`, `init`, `check`, `fmt`. Implemented via a `_COMMAND_HELP` dict in `src/nodus/cli/cli.py`; `--help` after a command no longer falls through to the global help.
- **Execution transparency (Task 1.3):** `nodus run` now prints two lines to stderr when auto-discovering a project (no file argument, or a directory argument): `Running project from: <absolute path>` and `Entry: <relative path>`. Single-file invocations (`nodus run script.nd`) are unchanged. Tests added in `tests/test_project_run_header.py`.
- **Project-root-relative imports (Task 3.1):** Bare import paths (no leading `./`) resolve against the project root first, then `.nodus/modules/`, then stdlib. When all fail, the error message now names all paths tried including stdlib candidates. Tests added in `tests/test_bare_imports.py`.
- **Index module support (Task 3.2):** When a bare or relative import path has no extension and no exact file match, Nodus now checks `<path>/index.nd` and `<path>/index.tl` as fallbacks. Resolution order: `path.nd` → `path.tl` → `path/index.nd` → `path/index.tl`. Tests added in `tests/test_bare_imports.py`.
- **`nodus run --trace-imports` flag (Task 3.3):** When set, prints one `[import] Resolved "path" → /abs/path` line to stderr for each import resolved at module-load time. Failed imports print `[import] Failed "path" — <reason>` before the error is raised. No effect on execution behavior. Tests added in `tests/test_trace_imports.py`.
- **Strict run mode (Task 2.2):** `nodus run --strict` disables project auto-discovery and requires an explicit file path. Without a file argument it prints `Error: --strict mode requires an explicit file path.` and exits non-zero. The flag is documented in `nodus run --help`. Tests added in `tests/test_strict_mode.py`.
- **`nodus status` command (Task 2.3):** New command that reports the project root, entry file, and working directory that would be used if `nodus run` were called from the current directory. Prints `No project found in current directory` when no `nodus.toml` is reachable; always exits 0. Appears in `nodus --help`. Help text available via `nodus status --help`. Tests added in `tests/test_status_command.py`.
- **Context-aware REPL prompt (Task 4.2):** `run_repl()` now calls `load_project_from(os.getcwd())` at startup. When a project is found the prompt becomes `nodus (<name>)> `; without a project it shows `nodus> `. The `ModuleLoader` is also initialised with the project root rather than raw cwd when a project is detected, so bare imports resolve correctly inside the REPL.
- **REPL error deduplication verified (Task 4.3):** Investigation confirmed the REPL prints exactly one error message per failed user action; `_execute_source` raises exceptions rather than printing them, and the `run_repl` loop prints exactly once via `format_error`. Two regression tests added to `tests/test_repl_commands.py` (`ReplErrorDeduplicationTests`) to lock this behaviour in place.
- **REPL `:modules` and `:reload` commands (Task 4.1):** `:modules` lists all modules imported in the current REPL session (paths from `import_state["loaded"]`), or prints `No modules imported.` when the session is clean. `:reload` clears session state and recreates the VM and loader, then prints `REPL session restarted.`. Unknown colon-commands now print `Unknown REPL command ':xyz'. Type :help for available commands.` instead of raising an exception. `:help` output updated to include all seven commands. `execute_repl_command` return type extended to a 4-tuple `(handled, output, should_exit, should_reload)`. Tests updated in `tests/test_repl_commands.py`; 5 new tests added.
- `llms.txt` at project root: machine-readable AI crawler index with project name, tagline, creator attribution, key concept definitions, and links to 8 key documents.

### Changed
- **CLI command visibility (Task 1.2):** `nodus --help` now shows `nodus init` instead of the internal `package-init` alias. `login`, `logout`, and `publish` added to the known-commands dispatch table (they were listed in help but silently failed at runtime). `nodus --help` now requires `--help` to be the first argument; `--help` after a command routes to per-command help.
- **Parser error messages (Task 1.4):** Parser errors no longer expose raw token kind names (`ID`, `COLON`, `RBRACE`, etc.). All error messages in `eat()`, `parse_pattern()`, and `parse_primary()` now use human-readable terms: `identifier` for `ID`, `end of file` for `EOF`, `end of statement` for `SEP`, `'{'`/`'}'` for brace tokens, etc. Context-specific hints added for `Unexpected '}'` and `Unexpected end of file` in expression position.

### Changed
- `pyproject.toml` `[server]` optional extras now pin `fastapi>=0.136.0,<1` and `uvicorn>=0.30.0,<1`; lower bound raised to the tested 0.136 series after a clean upgrade from 0.111.0.
- CI: `permissions: contents` downgraded from `write` to `read`; the job no longer requires write access now that the auto-format commit step has been removed.
- `pyproject.toml` `filterwarnings`: removed `ignore::PendingDeprecationWarning:starlette` suppression — starlette 1.0.1 no longer emits the python_multipart `PendingDeprecationWarning`.

### Security
- Updated `certifi` 2026.2.25 → 2026.5.20 (security certificate bundle; pinned in `requirements.txt`).
- Updated `idna` 3.11 → 3.16 (IDNA protocol library; pinned in `requirements.txt`).
- Updated `fastapi` 0.111.0 → 0.136.1 and `starlette` 0.37.2 → 1.0.1; both pinned in `requirements.txt`. The `services/server.py` FastAPI code (`FastAPI()`, `@app.middleware("http")`, `@app.get/post/delete` decorators, `Request`, `JSONResponse`, `request.json()`) is compatible with starlette 1.0 — no `on_startup`/`on_shutdown`, no bare `@app.route()`, no removed Starlette-level decorators are used. All 413 pytest tests pass against the upgraded versions.

### Fixed
- CI: `test_formatter_foreach.py` was silently excluded from the CI `unittest` runner. Added a `Pytest` step (`python -m pytest -q`) so pytest-style tests are covered.
- CI: Auto-format step that committed `.nd` changes directly to the branch on every push has been removed. Format enforcement is now check-only via the existing `nodus fmt --check` step.
- `nodus.py` shim: `main` was referenced in the `__main__` block without an explicit import (ruff F821). Added `from nodus.cli.cli import main` inside the block so the name is unconditionally resolved.
- `src/nodus/frontend/types.py`: replaced `exec(compile(...))` pattern with explicit `from types import ...` statements. No behavior change; removes exec() risk and makes the module statically analysable.
- `src/nodus/runtime/project.py`: removed 9 unused imports (`DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, `parse_dependencies`, `read_lockfile`, `write_lockfile`). None were referenced in the file body or consumed via re-export from this module.

### Improved
- None.

### Documentation
- `README.md`: added Shawn Knight creator attribution and Masterplan Infinite Weave / Infinity Algorithm canonical definition in the opening paragraph; added CI, PyPI, and license badges; added Documentation section with links to language spec, architecture, changelog, contributing guide, and llms.txt.
- `CONTRIBUTING.md`: updated repository structure diagram from stale flat layout to current `src/nodus/` package structure; fixed `requirements-dev.txt` reference to `requirements.txt`; fixed `LANGUAGE_SPEC.md` bare reference to `docs/language/LANGUAGE_SPEC.md`.
- `docs/onboarding/DEVELOPMENT.md`: updated all core component file references from bare filenames to full `src/nodus/` paths (`src/nodus/frontend/lexer.py`, `src/nodus/frontend/parser.py`, `src/nodus/frontend/ast/ast_nodes.py`, `src/nodus/compiler/compiler.py`, `src/nodus/vm/vm.py`, `src/nodus/orchestration/task_graph.py`, `src/nodus/orchestration/workflow_lowering.py`).

### Tests
- **CI: Coverage gate added (Phase 5C):** Added a `Coverage` step to CI running `pytest --cov=src/nodus --cov-report=term-missing --cov-fail-under=60`. Three timing-sensitive tests are deselected from the coverage run (they pass in the regular `Pytest` step but fail under instrumentation overhead): `test_scheduler_fairness.py::test_multiple_tasks_progress`, `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`, `test_task_graph.py::TaskGraphTests::test_worker_death_detection`. Overall baseline: 77% (14,232 stmts). `pytest-cov==7.1.0` added to `requirements.txt`.
- **CI: GitHub Actions SHA pinning (Phase 5C):** Both `actions/checkout` and `actions/setup-python` are now pinned to 40-character commit SHAs with inline version comments. `actions/checkout v4.3.1` → `34e114876b0b11c390a56381ad16ebd13914f8d5`; `actions/setup-python v5.6.0` → `a26af69be951a213d495a4c3e4e4022e16d87065`. Prevents supply-chain attacks via tag mutation.
- **CI: mypy non-blocking baseline (Phase 5C):** Added a `Type check` step with `continue-on-error: true` running `mypy src/nodus/ --ignore-missing-imports --no-error-summary`. Current baseline: 208 errors across 29 modules (top offenders: `cli/cli.py` 49, `vm/vm.py` 24, `formatter.py` 18, `task_graph.py` 18). Baseline recorded in `TECH_DEBT.md`. `mypy==2.1.0` added to `requirements.txt`; `[tool.mypy]` section added to `pyproject.toml`.
- CI: Added `Lint` step (`ruff check .`) positioned immediately after `Set up Python`, before all test and format steps. The step fails the build on any lint error, surfacing the existing backlog of 77 errors.

### Refactoring
- **`BuiltinRegistry` extracted to `builtins/registry.py` (Phase 5C):** Moved `BuiltinRegistry` class from `src/nodus/builtins/__init__.py` to `src/nodus/builtins/registry.py`. `__init__.py` now re-exports it with `# noqa: F401`. `register_all()` moved to the class body; all four category-module registrations (`io`, `math`, `coroutine`, `collections`) are performed there. Only `vm.py` imported `BuiltinRegistry` from `nodus.builtins`; no consumer changes required.
- **`src/nodus/__init__.py` function-body imports removed (Phase 5C):** Three wrapper functions (`resolve_imports`, `run_source`, `main`) that existed only to provide lazy-import deferred loading were replaced with `__getattr__` handlers plus `globals()` caching. Startup cost unchanged (imports still deferred); module-body wrapper definitions eliminated. `if __name__ == "__main__"` updated to use `__getattr__("main")()`.
- **Lint cleanup — ruff error count 66 → 0** (Phase 4A): resolved all outstanding ruff errors so CI passes on every push.
  - F811: removed duplicate `import threading` at `services/server.py:48`; kept the import at line 12.
  - F401 (46): removed 45 unused imports across `builtins/collections.py`, `lsp/server.py`, `orchestration/workflow_lowering.py`, `runtime/errors.py`, `services/server.py`, `tooling/analyzer.py`, `tooling/loader.py`, `tooling/registry_client.py`, `tooling/runner.py`, `tooling/user_config.py`, `vm/vm.py`, and test files; `runtime/semver.py` re-exports protected with `# noqa: F401`.
  - E402 (11): moved `TASK_STEP_BUDGET` constant in `runtime/scheduler.py` to after imports; moved `from nodus.support.version import VERSION` in `services/server.py` to top-level import block; added `# noqa: E402` to `cli.py`, `language.py`, and `task_graph.py` shims where imports must follow `sys.path` manipulation.
  - E401 (2): split multi-import lines in `tmp_demo/` (auto-fixed).
  - F841 (6): removed `scheduler_hint` initial declaration and intermediate assignment in `orchestration/task_graph.py`; removed unused `by_id` dict in `orchestration/task_graph.py`; removed dead `else_header` in `tooling/formatter.py`; narrowed `except Exception as err:` to `except Exception:` in `lsp/server.py`; dropped unused assignment targets in `tests/test_incremental_compilation.py` and `tests/test_registry_client.py`.

## [1.1.2] - 2026-04-27

### Added
- `nodus repl` CLI command.

### Fixed
- duplicate execution when both `main.nd` and `src/main.nd` exist.
- circular import detection with full chain reporting.
- stdlib packaging issues.

### Changed
- clarified execution behavior for `nodus run`.

### Notes
- runtime behavior is now consistent between development and installed environments.

## 1.1.1 - 2026-04-26

### Added
- Optional `server` install extra for FastAPI/Uvicorn: `pip install "nodus-lang[server]"`.

### Changed
- `nodus check` now mirrors `nodus run` project resolution and can validate the default project entry file when invoked with no explicit file from a project directory.
- HTTP server docs now identify canonical route names and compatibility aliases for overlapping endpoint names.

### Improved
- Added installed-wheel smoke coverage for the packaged `nodus` CLI, including `run`, `init`, `repl`, `serve`, and stdlib import resolution.

### Documentation
- Clarified that `nodus serve` is the canonical user-facing HTTP API surface.
- Documented optional server dependency behavior for plain installs versus `nodus-lang[server]`.

### Tests
- Added installed-wheel distribution smoke validation.
- Added CLI coverage for `nodus check` project-root and project-directory resolution.

## 1.1.0

* Added automatic `main()` execution
* Introduced installable PyPI package (`nodus-lang`)
* Cleaned repository boundary (removed A.I.N.D.Y. concepts)
* Clarified execution model

## [0.9.0] - 2026-03-15 — Registry Auth, Publish & Ecosystem Completeness

### Added
- **Registry authentication**: Bearer token support via `--registry-token` flag, `NODUS_REGISTRY_TOKEN` env var, and `~/.nodus/config.toml` user config file. Three-tier resolution: flag > env > config.
- **`nodus login` / `nodus logout`** commands: write and clear the registry token in `~/.nodus/config.toml`.
- **`nodus publish`**: uploads a package archive to the registry via POST with SHA-256 digest sent as `X-SHA256` header. 409 Conflict returns a clear error. Implemented via `create_package_archive()` and `publish_package()`.

### Changed
- `compile_source()` public re-export removed from `nodus.__init__`; loader body retained in `nodus.tooling.loader` for internal use until v1.0.

### Fixed
- CI: `tests/test_formatter_coverage.py` was using `import pytest`, causing `ModuleNotFoundError` in the unittest-based CI runner. Converted to `unittest.TestCase`.

### Documentation
- `CONTRIBUTING.md`: replaced stale `pytest` commands in the Running Tests section with `python -m unittest` equivalents.
- `docs/tooling/TESTING.md`: added `test_formatter_coverage.py` entry to the Formatter Test Files section; updated Known Flaky Tests run command from `python -m pytest` to `python -m unittest`; removed stale `pytest` alternative from Running Tests.

### Tests
- 11 new tests covering registry authentication: token resolution priority (flag > env > config), `nodus login`/`nodus logout`, and Bearer token header injection.
- 9 new tests covering publish: archive creation, POST upload, `X-SHA256` header, and 409 Conflict handling.
- Converted `tests/test_formatter_coverage.py` from pytest to `unittest.TestCase` (CI fix).

### Provisional Opcodes
- `GET_ITER`/`ITER_NEXT` `pending_get_iter` cleanup deferred to v1.0 by design; behavior documented in `INSTRUCTION_SEMANTICS.md`.
- Exception model: `finally` blocks and typed catches deferred to v1.0. `SETUP_TRY`, `POP_TRY`, and `THROW` remain provisional.

## [0.8.0] - 2026-03-15 — Stability and Package Ecosystem

### Added
- **Registry-backed package resolution**: new `RegistryClient` (`src/nodus/tooling/registry_client.py`) fetches package index, resolves semver constraints, downloads archives with SHA-256 verification, and extracts to `.nodus/_staging/`. Registry URL resolved from `--registry` flag, `NODUS_REGISTRY_URL` env var, or `registry_url` in `nodus.toml`. 12 new tests in `tests/test_registry_client.py`.
- **FRAME_SIZE opcode**: pre-allocates `frame.locals_array` (list of N slots) at function entry. First instruction of every compiled function body. Bytecode version bumped to `BYTECODE_VERSION = 2`.
- **LOAD_LOCAL_IDX opcode**: slot-indexed read from `frame.locals_array[slot]`; replaces name-keyed `LOAD_LOCAL` for all function-scope locals. ~40%+ hot-loop improvement over name-keyed dict lookup.
- **STORE_LOCAL_IDX opcode**: slot-indexed write to `frame.locals_array[slot]`; handles Cell boxing in-place for closure capture. Emitted for all let-bindings, assignments, loop variables, catch variables, and destructuring targets.
- **Opcode freeze proposal**: `docs/governance/FREEZE_PROPOSAL.md` — formal stability table for all 47 opcodes (39 stable, 7 provisional, 1 deprecated), freeze prerequisites, post-freeze extension process, and version history.
- **Formatter coverage complete**: handlers added for `Yield`, `Throw`, `TryCatch`, `DestructureLet`, `VarPattern`, `ListPattern`, `RecordPattern`. New `format_pattern()` helper. All 48 AST node types now covered. See `tests/test_formatter_coverage.py`.

### Changed
- `Frame` dataclass extended with `locals_array: list | None` and `locals_name_to_slot: dict[str, int] | None`. `STORE_ARG` syncs to both `locals` dict and `locals_array`.
- `SymbolTable.define()` now assigns `Symbol.index` (local slot) for function-scope symbols. `Upvalue.index` carries the local slot when `is_local=True`.
- `FunctionInfo` gains `local_slots: dict[str, int]` field; serialized to/from bytecode cache.
- `capture_local()` prefers `locals_array` path when available; Cell boxing goes through array slot.
- `ProjectConfig` gains optional `registry_url` field; written to `nodus.toml` when set.
- LSP server `serverInfo.version` bumped to `0.8.0`.

### Fixed
- LSP `_uri_to_path` now uses `os.path.realpath` instead of `os.path.abspath`, normalising double-slash paths (`//tmp/…`) that arise from 4-slash `file:////…` URIs on Linux.
- LSP `_publish_diagnostics` echoes back the exact URI registered via `textDocument/didOpen` instead of reconstructing one, preventing URI mismatches on Linux.

### Deprecated / Removed
- `compile_source()` internal callers fully migrated to `ModuleLoader` in v0.8. Public stub in `nodus.__init__` retained with `DeprecationWarning` until v1.0. All 24 test files migrated to `ModuleLoader.compile_only()`.
- `LOAD_LOCAL` opcode classified **deprecated**; retained as fallback only. Removal target: v1.0 after full bytecode migration.

### Documentation
- `docs/governance/FREEZE_PROPOSAL.md`: new — opcode stability classifications and v1.0 freeze process.
- `docs/runtime/BYTECODE_REFERENCE.md`: added FRAME_SIZE, LOAD_LOCAL_IDX, STORE_LOCAL_IDX entries; opcode count updated to 47; reference to FREEZE_PROPOSAL.md added.
- `docs/governance/TECH_DEBT.md`: GET_ITER/pending_get_iter cleanup and Exception model finalization sections added; all v0.8 items marked complete.
- `docs/governance/ROADMAP.md`: all five v0.8 goals marked ✅.
- `docs/language/FORMAT.md`: formatting rules for Yield, Throw, TryCatch, DestructureLet.
- `docs/tooling/PACKAGE_MANAGER.md`: Registry Installation section added.
- `docs/tooling/TESTING.md`: corrected CI step description; updated formatter test authoring guidance.

### Tests
- `tests/test_formatter_coverage.py`: 7 new tests covering all previously-missing AST formatter nodes.
- `tests/test_registry_client.py`: 12 new tests covering HTTP fetch, semver resolution, checksum verification, install/extract, and full integration flow.
- Rewrote `tests/test_formatter_fnexpr.py` as a `unittest.TestCase` class.

## [0.7.0] - 2026-03-15 — Runtime Orchestration, Diagnostics, Debugging, and Sprint Fixes

### Added
- Incremental module compilation backed by a persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache for compiled modules (`.nodus/cache/*.nbc`).
- DAP debug adapter over stdio with `nodus dap`.
- LSP server with completion, hover, go-to-definition, and diagnostics.
- Workflow persistence snapshots and checkpoint files under `.nodus/graphs/`.
- Workflow management CLI commands: `nodus workflow list`, `nodus workflow resume`, `nodus workflow cleanup`.
- `NodeVisitor` base class (`src/nodus/frontend/visitor.py`) — automatic `visit_<ClassName>` dispatch for all AST walkers.
- `BuiltinRegistry` class (`src/nodus/builtins/__init__.py`) — category modules (`io`, `math`, `coroutine`, `collections`) register builtins at VM construction time.
- String escape sequences: `\r`, `\0`, `\xHH`, `\uXXXX` now supported in the lexer.
- Import chain depth limit: configurable via `NODUS_MAX_IMPORT_DEPTH` env var (default 100); raises `LangSyntaxError` instead of `RecursionError`.
- Formatter handlers for `FnExpr` (anonymous functions), `FieldAssign` (`obj.field = val`), and `RecordLiteral` (`record { ... }`).
- CI auto-formats `examples/*.nd` before the format check and commits back with `[skip ci]`.

### Changed
- Runtime module loader now skips recompilation when dependency mtimes are unchanged.
- Workflow resume logic rehydrates persisted task state and scheduler order.
- `nodus deps` now reports the incremental compilation dependency graph.
- `compile_source()` marked deprecated since v0.5.0; `ModuleLoader(...).load_source(src)` is the canonical pipeline. Removal target: v1.0.
- AST `Base` dataclass carries explicit `_tok` and `_module` fields (excluded from `__repr__`/`__eq__`) on all node types.
- Bytecode cache format changed from `pickle` to `marshal` with `NDSC` magic header + format version byte + SHA-256 integrity check. Eliminates pickle's arbitrary-code-execution risk.
- Channel `waiting_receivers` / `waiting_senders` converted from `list` to `collections.deque`; `pop(0)` replaced with `popleft()` (O(1)).
- Optimizer `collect_jump_targets()` hoisted to once per outer fixed-point iteration; O(n) list-equality dirty-detection fallback removed in favour of a boolean `changed` flag.
- Legacy `.tl` files removed from `examples/`; `examples/` now contains only `.nd` files.

### Fixed
- `decode_string_literal` now raises `LangSyntaxError` directly with line/col rather than bare `SyntaxError`; tokenize() re-raise workaround removed.
- Optimizer bool constant folding normalised: arithmetic ops convert bool operands to int before folding to match VM runtime semantics.
- `builtin_close` now guards receiver wake-up with `state == "suspended"` check to prevent waking non-suspended coroutines.

### Improved
- VM `execute()` dispatch replaced `if/elif` chain with a dict dispatch table (`_build_dispatch_table()`). Benchmark: 388 ms → 260 ms (~33% throughput improvement).
- `LOAD_LOCAL` opcode: compiler emits `LOAD_LOCAL name` instead of `LOAD name` for confirmed function-local variables, bypassing the 4-scope probe in `load_name()`. Benchmark: ~21% additional improvement on tight loops.
- Scheduler fairness via round-robin execution and `TASK_STEP_BUDGET` enforcement.
- LSP diagnostics are dependency-aware with cross-module publishing and incremental refresh.
- Debugger integration reused by both interactive debugger and DAP server.
- Workflow checkpoint handling preserves upstream task outputs while rolling back downstream steps.

### Documentation
- Added/updated docs for LSP, DAP, debugging entrypoints, workflow persistence, and scheduler fairness.
- Documentation synchronisation pass: FORMAT.md, TESTING.md, BYTECODE_REFERENCE.md, RELEASE_CHECKLIST.md, TECH_DEBT.md, GETTING_STARTED.md updated to reflect Phases 1–4.

### Tests
- Added coverage for bytecode cache, incremental compilation, scheduler fairness, workflow persistence, LSP diagnostics, and DAP server behavior.
- Added/expanded tests for module isolation and runtime module objects.
- Added `tests/test_formatter_fnexpr.py` covering FnExpr, FieldAssign, RecordLiteral formatting.

### Refactoring
- `_StateRewriter` documented in `src/nodus/runtime/workflow_lowering.py`.

## [0.5.0] - 2026-03-14 — Interactive Shell and Inspection

### Added
- REPL multiline editing with `... ` continuation for brace-delimited blocks.
- Persistent REPL history via `~/.nodus_history` when Python `readline` is available.
- REPL inspection commands: `:ast <expr>`, `:dis <expr>`, `:type <expr>`, `:help`, and `:quit`.
- Dedicated REPL documentation in `docs/tooling/REPL.md`.
- Profiler documentation and runtime integration for the 0.5.0 tooling milestone.

### Changed
- REPL inspection output now supports compact expression AST views and expression bytecode inspection.
- Onboarding and runtime docs now describe the interactive shell workflow and inspection commands.
- Project metadata now aligns on version `0.5.0`.

### Fixed
- None.

### Removed
- None.

## [0.4.x Tracking]
- Module bytecode unit format and bytecode version headers.
- Minimal runtime module objects and debugger MVP.
- Semver parsing and lockfile format groundwork.

## [0.4.0] - 2026-03-14 — Runtime Architecture & Packaging

### Added
- Bytecode version headers in compiled modules.
- Runtime sandbox limits (steps/time/stdout).
- Embedding API for host execution and host function registration.
- Runtime module system with module objects and caching.
- Per-module bytecode units and per-module global namespaces.
- Project manifest parsing (`nodus.toml`) and dependency resolution.
- `nodus.lock` lockfile generation with resolved metadata.
- Debugger MVP with breakpoints, stepping, stack inspection, and variable inspection.
- Tooling-side package management modules for project parsing, semver, dependency resolution, installation, and registry metadata.
- Deterministic `[[package]]` lockfile entries with `name`, `version`, `source`, and `hash`.
- Test coverage for installer behavior, lockfile generation, runtime loading from `.nodus/modules`, and manifest/resolution flows.

### Changed
- Imports now resolve through the runtime module loader with dependency-first resolution.
- Module execution is isolated per module with cached module objects.
- Tooling execution flows updated for module-based runtime execution.
- CLI includes `nodus update` for dependency refresh.
- Refactored package management so runtime execution no longer performs manifest parsing, dependency resolution, registry access, or network operations.
- Installed dependencies now live under `.nodus/modules/` instead of `deps/`.
- Runtime module loading now resolves imports in the order: local project modules, `.nodus/modules/`, then standard library.
- `nodus install` and `nodus update` now route through tooling-side resolution and installation.

### Internal
- Module loader integrates project manifests, lockfile resolution, and dependency paths.
- VM supports module-bound function wrappers for module exports.
- Package manager routes through the runtime project system and lockfile format.

### Tests
- Added coverage for manifest parsing, semver ranges, and dependency resolution.
- Updated package tests for the new lockfile format and module execution behavior.

### Fixed
- Worker-required tasks always dispatch through the worker manager.

### Removed
- Package-management responsibilities from the runtime project/loading path.

## [0.3.0] - 2026-03-13

### Added
- Workflow and goal syntax with task graph planning, execution, resume, and checkpoints.
- Cooperative coroutines, scheduler, and channels (`coroutine`, `resume`, `spawn`, `run_loop`, `sleep`, `channel`, `send`, `recv`, `close`).
- Runtime event bus with human/JSON sinks and CLI flags `--trace-events`, `--trace-json`, `--trace-file`.
- Service mode `nodus serve`, session snapshots (`nodus snapshot`, `nodus snapshots`, `nodus restore`), and worker registration (`nodus worker`).
- Orchestration CLI commands: `nodus graph`, `workflow-*`, `goal-*`.
- Runtime service CLI commands: `tool-call`, `agent-call`, `memory-get`, `memory-put`, `memory-keys`.
- Package management commands: `nodus init`, `nodus install`, `nodus deps` with `nodus.toml`/`nodus.lock`.
- Stdlib modules: `std:json`, `std:math`, `std:runtime`, `std:tools`, `std:memory`, `std:agent`, `std:async`, `std:utils`.
- Editor support: TextMate grammar, VS Code config, and snippets under `tools/vscode/`.
- Inspection tooling: `nodus ast`, `nodus dis`, `nodus ast --compact`, `nodus dis --loc`.
- Debug command: `nodus debug`.
- Example smoke test command: `nodus test-examples`.
- Added `examples/project_layout_demo/` as a small multi-file onboarding example.

### Changed
- Formatter preserves integer-looking numeric literals and uses a dedicated unary minus AST node.
- Trailing comment behavior clarified and `--keep-trailing` option added.
- `nodus run` adds `--no-opt`, `--project-root`, scheduler tracing, and trace filters/limits.
- Bytecode reference updated to document the `NEG` opcode explicitly.

### Fixed
- Expire polling workers after heartbeat timeout to ensure dead workers are removed promptly.

### Removed
- None.

## [0.2.0] - 2026-03-11

### Added
- Module system (imports/exports, selective imports, re-exports, `std:` aliases).
- Deterministic import resolution with package/index support and project-root overrides.
- Standard library modules: `std:strings`, `std:collections`, `std:fs`, `std:path`.
- `nodus fmt` (formatter) with `--check` and comment handling controls.
- `nodus check` for syntax/import/compile validation without execution.
- Debug flags: `--dump-bytecode` and `--trace` with controls.
- CI workflow via GitHub Actions.
- Release discipline docs: `RELEASE_CHECKLIST.md`, `VERSIONING.md`, `COMPATIBILITY.md`.

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).
- Centralized version metadata in `version.py`.
- Compatibility: `.tl` extension still supported with warnings; legacy launchers remain available.

### Fixed
- None.

### Removed
- None.

## [0.1.0] - 2026-03-09

### Added
- Modular runtime architecture (lexer, parser/AST, compiler, VM, loader).
- Imports/exports with selective and namespaced imports.
- Deterministic import resolution with `std:` aliases.
- Stack traces with source mapping.
- Debugging flags: `--dump-bytecode` and `--trace`.
- Package/index resolution and project-root overrides.
- Re-export support (`export { name } from "./mod.nd"`).

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).

### Fixed
- None.

### Removed
- None.
