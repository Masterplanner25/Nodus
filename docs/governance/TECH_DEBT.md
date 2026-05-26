# Technical Debt / Follow-ups

This document tracks known follow-ups and cleanup items that are not blocking current work.

## Future Improvements

- Add coroutine-aware profiler attribution (per-coroutine stacks and timing).
- Offer exclusive timing mode (subtracting callee time from caller).
- Aggregate profiling across module VM invocations when `ModuleFunction` spins up a new VM.
- Improve REPL multiline completeness beyond raw brace counting so braces inside strings/comments do not affect continuation.
- Expand REPL inspection commands beyond single-expression input and smooth over top-level map-literal parsing ergonomics.

## Review Backlog (Needs Validation)

Items below were raised in a third-party review and are now validated with concrete references.

## Phase 2 Fixes Applied (architecture)

- ✅ Builtin registry extracted from VM: `BuiltinRegistry` class in `src/nodus/builtins/__init__.py`; category modules (`io`, `math`, `coroutine`, `collections`) each expose a `register(vm, registry)` function called at VM construction time.
- ✅ `compile_source()` deprecated: marked `@deprecated` since v0.5; canonical path is `ModuleLoader(...).load_source(src)`. Internal src/ callers migrated in v0.8; public stub removed from `nodus.__init__` in v0.9.0. Loader body retained for internal use; removal target v1.0.
- ✅ AST `Base` dataclass: all AST node classes inherit from `Base` (`src/nodus/frontend/ast/ast_nodes.py`), which carries `_tok` (source token for error location) and `_module` (module path set by loader), both excluded from `__repr__` and `__eq__`.
- ✅ `NodeVisitor` base class: `src/nodus/frontend/visitor.py` provides automatic `visit_<ClassName>` dispatch. Missing visitor methods raise `NotImplementedError` at runtime to surface coverage gaps early.
- ✅ `_StateRewriter` documented: workflow lowering pass documented in `src/nodus/runtime/workflow_lowering.py`; rewrites workflow/goal ASTs into scheduler-compatible coroutine form.

## Validated Findings

- ✅ VM builtin extraction complete: I/O, math, coroutine, and collection builtins extracted into `src/nodus/builtins/` category modules and registered at VM construction time via `BuiltinRegistry` (`src/nodus/builtins/__init__.py`).
- ✅ Compiler unreachable `For`/`ForEach` branches: the duplicate `return`-only handlers at the old compiler.py:513/515 have been removed. A single handler per node type now exists: `For` at compiler.py:435, `ForEach` at compiler.py:454. Confirmed resolved in v0.9 code hygiene pass.
- ✅ VM execute() dispatch table implemented: if/elif chain replaced with dict dispatch (_dispatch) built at construction time; each opcode is handled by a _op_XXX method (src/nodus/vm/vm.py).
- Long `elif` dispatch chains remain in the compiler (compiler.py:327 for compile_stmt and compiler.py:540 for compile_expr). Consider dispatch tables for maintainability.
- AST node type hints are overly broad (`object`) in `src/nodus/frontend/ast/ast_nodes.py` (e.g., `Unary.expr`, `Bin.a`, `Bin.b`, `Call.callee`, `Let.expr`, `If.cond`).
- ✅ Deadline checking batched in `record_instruction`: `time.monotonic()` is now called only every `_deadline_check_interval` instructions, not on every step. Check interval logic at `src/nodus/vm/vm.py` in `record_instruction`.
- ✅ Channel waiting queues converted to `collections.deque`: `waiting_receivers` and `waiting_senders` in `channel.py`; `pop(0)` replaced with `popleft()` in `builtins/coroutine.py`.
- ✅ `_op_throw` (`src/nodus/vm/vm.py:2142`) now preserves structured thrown values; fixed in v1.0. `handle_exception` (vm.py:310) is also correct. See Open Items for full resolution notes.
- ✅ Anonymous functions now have unique display names: `src/nodus/compiler/compiler.py:791` emits `f"__anon_{self.fn_counter}"`, giving each anonymous function expression a distinct, traceable name.
- File I/O builtins are unrestricted by default (`src/nodus/vm/vm.py:1464-1510`). An allowlist hook is available (`VM.allowed_paths`) and now wired into CLI/server; it remains opt-in.
- ✅ Relative import containment implemented: non-std, non-package relative paths are guarded by project-root containment checks in `src/nodus/tooling/loader.py` and `src/nodus/runtime/module_loader.py`. Error messages now name the offending path (`"Invalid import: path '../outside.nd' escapes the project root."`). Check applies in project mode, single-file mode, and the REPL — all using the same `resolve_import_path` code path (Phase 5, 2026-05-23).
- ✅ HTTP bearer-token auth implemented: `src/nodus/services/server.py` enforces token authentication. Non-local binding requires a token; local-only binding remains opt-in.
- ✅ VM call stack max depth check: enforced in `call_closure` (`src/nodus/vm/vm.py:1518`) and the `CALL` opcode path (`src/nodus/vm/vm.py:2071`). `self.max_frames` guard raises `sandbox / Call stack overflow` if exceeded. Remains opt-in (`max_frames` defaults to `None`).
- `input()` uses `input_fn` defaulting to Python `input()` (`src/nodus/vm/vm.py:137` and `src/nodus/vm/vm.py:162`). Server mode now blocks `input()` by default, but embedding still uses the default unless configured.

## Additional Validated Items

- ✅ Optimizer fixed-point loop: `collect_jump_targets()` hoisted to once per outer iteration; O(n) list equality dirty-detection fallback removed from `fold_constants` and `remove_useless_stack_ops` (`src/nodus/compiler/optimizer.py`).
- Module qualification uses `__modN__` prefixes (`src/nodus/tooling/loader.py:70`), but there is no documentation in code or docs explaining the scheme.

## Phase 3 Fixes Applied (performance)

- ✅ Fix 12 — `LOAD_LOCAL` opcode: compiler now emits `LOAD_LOCAL name` instead of `LOAD name` for known function-local variables (both `Name` load expressions and the post-assign reload in `Assign` expressions), bypassing the 4-dict probe in `load_name()` (locals → module_globals → functions → host_globals). VM handler reads directly from `frame.locals[name]`. Measured VM-only improvement: ~21% on a tight integer loop benchmark (`examples/benchmark.nd`). Affects `src/nodus/compiler/compiler.py` and `src/nodus/vm/vm.py`. — Future: `LOAD_LOCAL_IDX idx` (slot-indexed list access) would reduce constant further at cost of Frame refactoring.
- ✅ Fix 13 — Channel waiting queues converted to `collections.deque`: `waiting_receivers` and `waiting_senders` in `src/nodus/runtime/channel.py`; all `pop(0)` (O(n)) replaced with `popleft()` (O(1)) in `src/nodus/builtins/coroutine.py`.
- ✅ Fix 14 — Bytecode cache migrated from `pickle` to `marshal`: `src/nodus/runtime/bytecode_cache.py` now writes `NDSC` magic (4 bytes) + format version byte + SHA-256 checksum (32 bytes) + `marshal.dumps()` payload. Eliminates pickle's arbitrary-code-execution risk and is faster for primitive-type payloads. Checksum verified on load; any mismatch silently invalidates the cache.
- ✅ Fix 15 — Optimizer `collect_jump_targets()` hoisted: previously called once inside `fold_constants()` and once inside `remove_useless_stack_ops()` per outer fixed-point iteration (2× O(n) scans). Now computed once per outer iteration and passed as a parameter; recomputed only if `fold_constants` changes code (address compaction). Also removed the O(n) list equality dirty-detection fallback from both functions — the boolean `changed` flag is sufficient.

## ✅ GET_ITER pending_get_iter cleanup

**Resolved at v1.0.** The `pending_get_iter` / `pending_iter_next` VM flags and all
associated RETURN handler post-processing were removed. A first-class `Iterator` class
(in `vm.py`) wraps an `advance_fn: () → (value, exhausted)` callable. All GET_ITER
paths (list, `__iter__` closure, `__next__` closure) produce an `Iterator` synchronously
using `run_closure()`. `_op_return` pending-flag blocks removed. `_NO_PENDING` sentinel
and dead dispatch branch removed. `Coroutine` dataclass fields `pending_get_iter` and
`pending_iter_next` removed. 14 flag sites removed across `vm.py`. All 379 tests pass.
Coroutine + iteration interaction tests added.

`GET_ITER` and `ITER_NEXT` are now **stable**. See `FREEZE_PROPOSAL.md §
"v1.0 GET_ITER/ITER_NEXT Decision"` and `INSTRUCTION_SEMANTICS.md § 14`.

## Exception model finalization

✅ `finally` block support implemented at v1.0. `SETUP_TRY` extended to two operands
(`handler_ip`, `finally_ip`). `POP_TRY` updated to redirect to `finally_ip` on normal
exit. New `FINALLY_END` opcode added. Handler stack extended to 4-tuple
`(handler_ip, finally_ip, stack_depth, frame_depth)`. Deferred-return mechanism added
to `_op_return`. `BYTECODE_VERSION` bumped to 4.

`SETUP_TRY` / `POP_TRY` / `FINALLY_END` / `THROW` promoted to **stable** at v1.0
freeze declaration (2026-03-15). See `FREEZE_PROPOSAL.md § "FREEZE DECLARED"`.

## Open Items (not yet complete)

- ✅ compile_source() fully removed in v1.0. Internal callers migrated to ModuleLoader in v0.8. Public stub removed from nodus.__init__ in v0.9.0. Loader body and last test caller (test_import_containment.py) removed in v1.0. 0 remaining references.
- ✅ `LOAD_LOCAL_IDX` slot-indexed fast path: Implemented in v0.8. Compiler now emits `FRAME_SIZE n`, `STORE_LOCAL_IDX slot`, and `LOAD_LOCAL_IDX slot` for all function-scope locals. Frame carries a pre-allocated `locals_array` (list) and `locals_name_to_slot` mapping. `capture_local` updated for Cell boxing via array. Cache serialization updated (`local_slots` in FunctionInfo). Bytecode version bumped to 2.
- ✅ compile_source() public stub removed in v0.9 from nodus.__init__. Loader body retained for internal use; removal target v1.0. test_import_containment.py uses loader directly and will need updating at v1.0.
- ✅ `LOAD_LOCAL` deprecated opcode: removed from VM dispatch table in v1.0. `_op_load_local` replaced with `RuntimeError` tombstone. `BYTECODE_VERSION` bumped from 2 to 3 to invalidate version-2 caches. See DEPRECATIONS.md.
- ✅ Registry publish and auth: `nodus publish` command and token management implemented in v0.9. `RegistryClient` now supports Bearer token auth. `get_registry_token()` in `package_manager.py` resolves tokens via CLI flag, `NODUS_REGISTRY_TOKEN` env var, or `~/.nodus/config.toml`. `nodus login`/`nodus logout` CLI commands added. See `docs/tooling/PACKAGE_MANAGER.md` Authentication section.
- ✅ Provisional opcode resolution: all 7 opcodes promoted to stable. `GET_ITER`, `ITER_NEXT`, `BUILD_MODULE`, `YIELD` promoted first; `SETUP_TRY`, `POP_TRY`, `FINALLY_END`, `THROW` promoted at v1.0 freeze declaration (2026-03-15). Zero provisional opcodes remain. See `FREEZE_PROPOSAL.md`.
- ✅ `GET_ITER`/`ITER_NEXT` Iterator protocol cleanup: complete at v1.0. `pending_get_iter`/`pending_iter_next` flags replaced by first-class `Iterator` protocol object. VM-only change; no compiler or `.nd` source impact. See section above and FREEZE_PROPOSAL.md v1.0 decisions.
- ✅ `finally` block implementation: complete at v1.0. `SETUP_TRY` extended to 2 operands; `POP_TRY` updated; `FINALLY_END` added; handler_stack to 4-tuple; `BYTECODE_VERSION` bumped to 4. See Exception model section above.
- ✅ `_op_throw` structured value preservation: `_op_throw` (vm.py:2142) now preserves structured values (Records, lists) as `err.payload` in the catch block rather than stringifying. Strings use the message directly; primitives are stringified; Records/lists are passed as `payload` with `kind="thrown"`. `LangRuntimeError` now carries an optional `payload` field. `handle_exception` includes `payload` in the error Record when present. Fixed in v1.0.
- ✅ `YIELD_VALUE`/`SEND` opcode evaluation: decision made. YIELD frozen as-is. No new opcode needed — no user-facing send-value use cases in `.nd` source. Recorded in FREEZE_PROPOSAL.md.
- ✅ `BUILD_MODULE` stability declaration: promoted to stable as part of v1.0 module system freeze. Module system feature-complete. Recorded in FREEZE_PROPOSAL.md and ROADMAP.md.
- ✅ `NodusRuntime` added to `__all__`: `src/nodus/__init__.py` now imports and exports `NodusRuntime` directly. `from nodus import NodusRuntime` works as of v1.0. EMBEDDING.md updated. Fixed in v1.0.
- ✅ `LOAD_LOCAL` compiler fallbacks: audited and fixed in v1.0. All three paths (compiler.py lines 584, 619, 731) confirmed unreachable — `SymbolTable.define()` always assigns `symbol.index` when `in_function_scope()` is True, making "local + in_function + index is None" a logical contradiction. Fallback emissions replaced with `assert symbol.index is not None` guards. See DEPRECATIONS.md.
- `vm.py` line count: 2,438 lines as of v1.1.2 (post-Phase 6). Further extraction of workflow/goal builtins and scheduler helpers is possible.

- **Coverage baseline (pytest-cov 7.1.0, 2026-05-23):** Overall: 77% (14,232 stmts). Gate: `--cov-fail-under=60`. Three timing-sensitive tests deselected from the coverage run (they pass in the regular pytest step but fail under instrumentation overhead: `test_scheduler_fairness.py::test_multiple_tasks_progress`, `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`, `test_task_graph.py::TaskGraphTests::test_worker_death_detection`). Modules below 60%:
  - `src/nodus/__main__.py`: 0% (3 stmts — trivial entry point, not exercised by test suite)
  - `src/nodus/tooling/loader.py`: 48% (370 stmts — legacy pipeline; modern tests use ModuleLoader. Needs dedicated test pass.)
  - `src/nodus/tooling/tiny_vm_lang_functions.py`: 0% (4 stmts — demo/wildcard re-export helper, not a production code path)

- **mypy baseline (mypy 2.1.0, 2026-05-23):** Non-blocking step added to CI (`continue-on-error: true`). Total: 208 errors across 29 modules. Per-module counts:

  | Module | Errors |
  |--------|--------|
  | `cli/cli.py` | 49 |
  | `vm/vm.py` | 24 |
  | `frontend/formatter.py` | 18 |
  | `runtime/task_graph.py` | 18 |
  | `dap/server.py` | 14 |
  | `tooling/loader.py` | 12 |
  | `repl/repl.py` | 8 |
  | `services/server.py` | 8 |
  | `runtime/module_loader.py` | 7 |
  | `lsp/server.py` | 7 |
  | `runtime/scheduler.py` | 6 |
  | `services/api.py` | 5 |
  | `runtime/module.py` | 5 |
  | `compiler/optimizer.py` | 5 |
  | `orchestration/workflow_lowering.py` | 4 |
  | `tooling/diagnostics.py` | 2 |
  | `tooling/analyzer.py` | 2 |
  | `tooling/user_config.py` | 1 |
  | `tooling/tiny_vm_lang_functions.py` | 1 |
  | `tooling/runner.py` | 1 |
  | `runtime/snapshots.py` | 1 |
  | `runtime/runtime_events.py` | 1 |
  | `runtime/profiler.py` | 1 |
  | `runtime/errors.py` | 1 |
  | `runtime/debugger.py` | 1 |
  | `main/nodus.py` | 1 |
  | `frontend/parser.py` | 1 |
  | `frontend/lexer.py` | 1 |
  | `frontend/ast/ast_printer.py` | 1 |
  | `__main__.py` | 1 |

## Patch closure verification gap (surfaced 2026-05-25 by v3.0.1 eval)

**Status:** OPEN — process gap to address in playbook

The v3.0.1 cycle closed #64 (BUG-E12, 1I uppercase suffix parse error) in the
CHANGELOG and on GitHub, but the fix did not land in the distributed wheel. The
v3.0.1 eval (`docs/evals/v3.0.1/`) caught this; it was not caught pre-release.

**Root cause** (determined during v3.0.2 fix work):
The lexer fix for `1I` was present in `src/nodus/frontend/lexer.py` at the time
the v3.0.2 regression tests were written. Running the new tests against the dev
source confirmed ALL six BUG-V31E-01 tests passed without any code change. This
means the fix was committed to source before the v3.0.1 wheel was built, but
the wheel was built from a state that did not include the commit — most likely
a missing `git push` before the PyPI upload step, or the wheel was built from a
stale local clone rather than from the pushed tag. No regression test for the
`1I` → parse error behavior existed in the test suite at the time of the v3.0.1
release, so CI did not catch the gap between source state and wheel contents.

**Process gap:**
The Playbook A Stage 3 (PyPI publish) procedure includes a "smoke test after
install" that runs `nodus --version`. It does not run the closed-issue regression
tests against the installed wheel. A closed issue's regression test should be
exercised against the installed artifact before the wheel is considered shipped.

**Proposed mitigation for Playbook A Stage 3:**
Add a "closure verification" sub-step between TestPyPI install and real PyPI
publish: for each issue closed in the release, run its regression test against
the installed wheel. If any test fails, the issue's CHANGELOG entry is wrong and
the release must be held.

Mechanical implementation: a script that reads the CHANGELOG section for the
release, extracts referenced issue numbers, locates each issue's regression test
by convention (`grep -r "issue #NN"` or `grep -r "BUG-V31E-NN"` in tests/), and
runs them against `pip install`'d package in a temp venv. Failing tests block
the release.

This will be incorporated into `docs/governance/PLAYBOOK_PATCH_MINOR.md` Stage 3
in the next playbook revision. See GitHub issue filed as follow-up in v3.1
milestone.

  Top priority: `cli/cli.py` (49), `vm/vm.py` (24), `frontend/formatter.py` (18), `runtime/task_graph.py` (18). Goal: zero errors before promoting mypy to blocking. See `pyproject.toml [tool.mypy]` for configuration.

- `.ndignore` support: `nodus publish` currently excludes a hardcoded list (`.nodus/`, `__pycache__/`, `.git/`, `*.pyc`, `nodus.lock`, `.gitignore`). A `.ndignore` file would give package authors control over what is included in the published archive. Target: post-v0.9.

## Testing Methodology

### Security boundary cross-context test requirement

All security boundary tests (path traversal, sandbox escapes, allowed_paths
enforcement, resource limits) must exercise BOTH CLI mode and NodusRuntime
embedded mode. The same bug class can exist in one context and not the
other if the enforcement code path differs.

**Precedent:** BUG-016 (v2.0.1) was a path traversal vulnerability in CLI
mode. BUG-046 (v2.1.1) was the same vulnerability class in embedded mode,
discovered six weeks later. The v2.0.1 fix correctly built a shared
validation function but the embedded mode's module VM did not invoke it.
Two-line fix once located, but the gap existed in a shipped release.

**Rule:** Any test added for a security-boundary fix must include at least
one CLI mode case and one NodusRuntime case, even if the underlying
validation function is shared. The test exercises the call path, not
just the validator.

## Untracked Items (surfaced in v0.9 assessment, 2026-03-15)

- ✅ `compile_source()` removal-target doc contradiction: resolved in v0.9.0. Public stub removed from `nodus.__init__` at v0.9 (one version earlier than the `DeprecationWarning` message indicated). ROADMAP.md, DEPRECATIONS.md, TECH_DEBT.md, and CHANGELOG.md all updated to reflect v0.9.0 removal. The warning message discrepancy is noted in DEPRECATIONS.md and CHANGELOG.md.

- ✅ Stale `loader.py` header comment: resolved. The `compile_source()` function body was removed in v1.0. The file no longer claims the function is used by `nodus check`, `nodus ast`, or `nodus dis` (those use `ModuleLoader`).

- ✅ `INSTRUCTION_SEMANTICS.md` GET_ITER / ITER_NEXT documentation: updated at v1.0. Entries now document the `Iterator` protocol object, `run_closure()` synchronous resolution, and stable classification. The previous `pending_get_iter` / `pending_iter_next` descriptions were replaced. See `docs/runtime/INSTRUCTION_SEMANTICS.md` §14.

- ✅ `NODUS_SERVER_TOKEN` vs. `NODUS_REGISTRY_TOKEN` naming split: now documented in `docs/tooling/PACKAGE_MANAGER.md` (Authentication section, "NODUS_SERVER_TOKEN vs NODUS_REGISTRY_TOKEN" subsection). The two tokens are independent: `NODUS_SERVER_TOKEN` authenticates requests to a running Nodus server process; `NODUS_REGISTRY_TOKEN` authenticates package registry requests.

- ✅ `--registry` CLI flag wired: `nodus install` now accepts `--registry <url>` and `--registry-token <token>` flags. Both are parsed and passed to `install_dependencies_for_project()`. Closed as part of v0.9 registry auth work.

- ✅ `test_task_reassignment_after_worker_failure` flaky test: fixed in v0.9.1. Root cause: `_poll_job` was spinning on `WorkerManager.poll()` every 10ms with a 2-second window; under concurrency the VM thread occasionally missed the window. Fix: added `WorkerManager.wait_for_job()` which blocks on the existing `_cond` condition variable (already notified by `submit()`). `_poll_job` now delegates to `wait_for_job()`. No polling, no race. Test runtime: ~20ms (was up to 2s). See `src/nodus/services/server.py`.

- ✅ Formatter AST coverage audit complete: all 48 AST node types handled in format_stmt()/format_expr(). Added Yield, Throw, TryCatch, DestructureLet, VarPattern, ListPattern, RecordPattern handlers. See tests/test_formatter_coverage.py.
- ✅ Opcode set frozen: freeze declared 2026-03-15. 48 opcodes (47 active + 1 removed); **47 stable, 0 provisional, 1 removed** (`LOAD_LOCAL`). `BYTECODE_VERSION = 4`. See `FREEZE_PROPOSAL.md` for the formal declaration and post-freeze extension process.

## Phase 2 Code Hygiene Fixes Applied (2026-05-22)

- ✅ `nodus.py:23` F821 undefined name `main`: added `from nodus.cli.cli import main` inside the `if __name__ == "__main__":` block. Previously relied on `spec.loader.exec_module()` populating the namespace implicitly; now unconditionally resolved.
- ✅ `src/nodus/frontend/types.py` exec() pattern: replaced `exec(compile(_f.read(), _stdlib_types_path, "exec"), _stdlib_namespace)` block with explicit `from types import ...` statements covering all names in `types.__all__`. `FunctionType` from stdlib is intentionally omitted since the subsequent `from nodus.frontend.type_system import FunctionType` always overwrote it. `__all__` converted from dynamic construction to a static list. Module is now statically analysable.
- ✅ `src/nodus/runtime/project.py` unused imports: removed 9 unused imports from `nodus.tooling.project` (`DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, `parse_dependencies`, `read_lockfile`, `write_lockfile`). Confirmed no consumer imports these names via `nodus.runtime.project`; all callers use `nodus.tooling.project` directly.

## Phase 1 CI & Safety Fixes Applied (2026-05-22)

- ✅ CI: Added `Pytest` step (`python -m pytest -q`) after `Unit tests`, before `Install build tooling`. `tests/test_formatter_foreach.py` was silently excluded from the `python -m unittest discover` runner because it uses bare pytest function style. Now run in CI.
- ✅ CI: Added `Lint` step (`pip install ruff && ruff check .`) as the first substantive step after `Set up Python`. The step fails the build on any lint error. No `--fix` flag; lint is check-only. Legacy backlog of 66 errors resolved in Phase 4A (2026-05-22); `ruff check .` now exits 0.
- ✅ CI: Removed auto-format + git-commit step pair (`Auto-format all .nd files` + `Commit formatted files`). These steps mutated branch history on every push with `permissions: contents: write`. Format enforcement is now check-only via the existing `nodus fmt --check` step.
- ✅ CI: `permissions: contents` downgraded from `write` to `read` now that the auto-commit step is gone.
- ✅ `pyproject.toml` `[server]` extras: `fastapi` and `uvicorn` now carry explicit version bounds (`>=0.111.0,<1` and `>=0.30.0,<1` respectively). Previously fully unpinned; a `pip install "nodus-lang[server]"` could pull `fastapi 0.136` or `uvicorn 0.47` against tested `0.111`/`0.30`.

## Phase 4 Fixes Applied (documentation completeness)

- ✅ Fix 16 — ARCHITECTURE.md completeness audit: added AST attribute convention
  (_tok/_module), workflow lowering (_StateRewriter) reference, and VM dispatch
  model (dict-based, how to add new opcodes).
- ✅ Fix 17 — VM execution model docstrings: added docstrings to VM.execute()
  (stack discipline, frame layout, coroutine protocol, pending flags, dispatch
  table), VM.load_name() (lookup order, why 4 scopes), VM.builtin_coroutine_resume()
  (pre-conditions, stack behavior, error propagation), VM.call_closure() (upvalue
  capture, Cell boxing, frame stack behavior).
- ✅ Fix 18 — SymbolTable documentation: added module-level docstring (scope types,
  two-pass design), docstrings for resolve_upvalue() (algorithm, Cell boxing, is_local
  semantics) and current_function_upvalues() (what it returns, runtime index relation).
- ✅ Fix 19 — Public API docstrings: full docstrings on NodusRuntime.__init__(),
  run_source(), run_file(), register_function(), reset(). Updated EMBEDDING.md to
  correct the initialization example (NodusRuntime vs. vm.register_builtin) and
  add module docstring to __init__.py public functions.
- ✅ Fix 20 — Bytecode reference completeness: added BUILD_MODULE opcode entry to
  BYTECODE_REFERENCE.md (was in dispatch table but missing from docs); updated
  opcode count from 42 to 43; added BUILD_MODULE semantics to INSTRUCTION_SEMANTICS.md.
  LOAD_LOCAL was already documented; LOAD_LOCAL_IDX is a future optimization not yet
  implemented (noted in TECH_DEBT).

## Phase 1 Fixes Applied (correctness)

- ✅ `decode_string_literal` now raises `LangSyntaxError` directly with line/col instead of bare `SyntaxError`; tokenize() re-raise workaround removed (`src/nodus/frontend/lexer.py`).
- ✅ String escape sequences expanded: `\r`, `\0`, `\xHH`, `\uXXXX` now supported. Column tracking corrected for strings containing literal newlines (`src/nodus/frontend/lexer.py`).
- ✅ Optimizer bool constant folding normalised: arithmetic ops convert bool operands to int before folding to prevent semantic divergence from VM runtime semantics (`src/nodus/compiler/optimizer.py`).
- ✅ `builtin_close` guards receiver wake-up with `state == "suspended"` check to prevent waking non-suspended coroutines (`src/nodus/vm/vm.py`).
- ✅ `resolve_imports` now enforces a configurable import chain depth limit (default 100, env `NODUS_MAX_IMPORT_DEPTH`) and raises `LangSyntaxError` instead of `RecursionError` (`src/nodus/tooling/loader.py`).

## Process Gaps (surfaced during v3.0 Phase 0, 2026-05-25)

- **Duplicate BUG-NNN:** BUG-029 was filed twice — [#27](https://github.com/Masterplanner25/Nodus/issues/27) (CLI `--help` grouping, no milestone, not in v3.0 scope) and [#30](https://github.com/Masterplanner25/Nodus/issues/30) (else-if syntax, v3.0 `phase:2-fix`). Root cause: the v2.1.1 handoff assigned the number from a running counter without checking existing issues. **Playbook action:** bug filing checklist must include a uniqueness check against open+closed issues before assigning a BUG-NNN. Capture in `RELEASE_PLAYBOOK.md` Phase 5.

- **Missing rubric eval for v2.1.0:** v2.1.0 shipped without a formal rubric eval. Guide-writing surfaced 23 issues but produced no composite score, leaving v2.0.0 (5.52) as the only comparable data point going into v3.0. **Playbook action:** every major/minor release must run the formal rubric eval and record the composite score before close. Guide-writing is supplementary, not a substitute. Capture in `RELEASE_PLAYBOOK.md` Phase 5.

## Phase 4 Deferred Content: STDLIB_PHILOSOPHY.md

The following principles surfaced during v4.0 Phase 1 design and need to
be captured in `docs/governance/STDLIB_PHILOSOPHY.md` when it is created
in Phase 4. The principles are already captured in
`docs/language/LANGUAGE_VISION.md` (positioning),
`docs/language/DESIGN.md` (architectural rationale),
`docs/language/STYLE_GUIDE.md` (idiomatic-code pattern), and
`docs/governance/LIBRARY_ECOSYSTEM.md` (ecosystem cross-reference); the
Phase 4 STDLIB_PHILOSOPHY.md draft consolidates them as one of the
foundational stdlib-design rules.

### Capabilities, not orchestration (principle)

Stdlib functions provide capabilities. They do not provide orchestration.
The boundary:

- **Capability:** make one HTTP call, run one subprocess, parse one JSON
  document, read one file.
- **Orchestration:** retry on failure, parallelize across inputs,
  sequence with conditional branches, recover from partial failure, rate
  limiting, circuit breaking, fan-out/fan-in patterns.

Orchestration concerns are workflow concerns. They compose capabilities;
they do not extend them. This means:

1. No `retries` option on capability functions
2. No automatic backoff schedules embedded in capability options
3. No fallback chains baked into stdlib calls
4. No rate-limiting decorators on stdlib functions

The orchestration layer (workflows, channels, future stdlib helpers in a
`std:retry` namespace if real demand surfaces) handles these concerns.
The capability layer stays narrow.

**Cross-references for STDLIB_PHILOSOPHY.md:**

- `docs/language/LANGUAGE_VISION.md` principle #6 — positioning framing
- `docs/language/DESIGN.md` § "Capability Surfaces Stay Narrow" — architectural rationale
- `docs/language/STYLE_GUIDE.md` § 18 "Retry, Backoff, and Recovery" — idiomatic pattern
- `docs/governance/LIBRARY_ECOSYSTEM.md` § "Not pursued: per-call orchestration options in stdlib" — ecosystem scope

**Source:** v4.0 Phase 1 design conversation for `01-http-api.md`,
specifically the rejection of per-request retry options in `std:http`.
The principle generalizes beyond HTTP; it applies to every stdlib
capability namespace (subprocess, future namespaces).

---

## v4.1 Candidates

### std:server (HTTP server namespace)

Surfaced by `nodus-a2a` v0.1 (webhook reception for push notifications)
and `nodus-mcp` v0.1 (server-side HTTP and Streamable HTTP transports).
Both libraries bundle their own HTTP servers in v0.1; the shared pattern
becomes visible once they ship.

`std:http` is a client. `std:server` would provide the listening side:
bind a port, handle incoming requests, dispatch to Nodus handlers, return
responses. Not in v4.0 scope. v4.1 candidate pending post-launch
evaluation of nodus-mcp and nodus-a2a server implementations.

**Source:** `docs/design/v4/01-http-api.md` § "Scope ceiling" and
§ "MCP and A2A consumer validation".

---

## Phase 3B Open Implementation Questions: std:http

From `docs/design/v4/01-http-api.md` § "Open implementation questions
for Phase 3B". These are resolved during Phase 3B execution; they do
not affect the API surface (which is locked by 01-http-api.md).

1. **Asyncio loop strategy.** One loop per VM instance vs shared global
   loop. Tentative direction: per-VM loop, lazy start on first `_async`
   call.

2. **Thread-safety between Nodus VM and asyncio loop.** Tentative
   direction: document single-threaded usage as the supported model;
   multi-threaded embedding requires user-provided synchronization.

3. **Connection pool lifecycle.** Tentative direction: lazy creation,
   per-VM lifetime, closed on VM shutdown.

4. **Channel implementation for streaming.** Verify the existing channel
   primitive supports cancellation that maps to httpx stream cancellation;
   if gaps exist, file as a Phase 3B work item at that time.

5. **Memory bounds on buffered responses.** Tentative direction: no
   implicit limit (matches httpx default); users who care use `timeout_ms`
   and `http.stream` for large bodies.

6. **UTF-8 boundary buffering implementation.** httpx provides
   line-buffered iteration but not character-boundary-buffered iteration.
   Tentative direction: incremental decoder pattern
   (`codecs.getincrementaldecoder`).
