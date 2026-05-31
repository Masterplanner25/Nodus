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

## Embedding API known limitations (v4.0.0, filed issues)

These were identified by a raw-path readiness probe before the MCP/A2A launch.
The nodus-mcp Phase 1 design decisions in `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`
describe the workaround patterns used until these are fixed.

- **EMBED-001** (documented, workaround in EMBEDDING.md): `NodusRuntime()` defaults
  to a 200ms wall-clock deadline (`EXECUTION_TIMEOUT_MS=200`). Every long-lived
  embedder (MCP servers, A2A servers, workflow hosts, any coroutine that sleeps >
  200ms cumulatively) must pass `timeout_ms=None, max_steps=None` explicitly. The
  default matches `nodus run` (sandboxed scripts), not server embedding. GitHub: #97.

- **EMBED-002** (FIXED): `NodusRuntime` now exposes `on_error` as an `__init__`
  parameter and a `run_source()` per-call override. The callback is wired to
  `Scheduler.run_loop(on_error=...)` via `builtin_run_loop` and the VM's new
  `on_error` attribute. Callers can now detect and stop on coroutine errors.
  GitHub: #98.

- **EMBED-003** (FIXED — minimal): `NodusRuntime.shutdown()` added; clears
  `last_vm`, host functions, and registered tools. Daemon pump threads from
  `subprocess_spawn` still accumulate until their subprocesses exit (process
  tracking not yet implemented), but the public API surface now exists.
  GitHub: #99.

- **EMBED-004** (FIXED for direct builtin path): `http_get_async`, `http_post_async`
  and all `http_*_async` variants now run the HTTP request in a daemon thread and
  suspend the calling coroutine via the `_io_channels` mechanism (same pattern as
  `subprocess_spawn`). `subprocess_run_async` and `subprocess_shell_async` use the
  same thread+channel approach. Verified 3.3x speedup for 3 parallel 1s subprocesses
  (sequential: ~4.3s, async: ~1.3s).
  **Remaining limitation (ASYNC-MOD-001, GitHub #105):** when called via the stdlib
  module wrapper (`subprocess.run_async(...)`, `http.get_async(...)` via
  `import "std:subprocess"`), the `invoke_function` path doesn't support yield —
  falls back to sync. Direct builtin calls (`subprocess_run_async(...)`) within
  spawned coroutines are fully async. Workaround: use direct builtin names.
  Fix direction: add `_code_stack` to VM; in `_op_call_method` for module functions
  in scheduler context, push current code, swap to module code, use `call_closure`,
  pop on RETURN. Skill: `/nodus-async-module-yield`.
  GitHub: #100 (EMBED-004 parent), #105 (ASYNC-MOD-001 tracking issue).

- **DAP-001** (open, severity: high, GitHub #106): The DAP server does not implement
  the `evaluate` command. When paused at a breakpoint, users cannot evaluate
  expressions in the debug console — VS Code and other DAP clients show an error.
  `evaluate` is the most-used debugger feature in interactive sessions. Fix direction:
  compile the expression string as a Nodus expression (via `Parser` + compiler),
  execute in the current frame's local/global context, return DAP `EvaluateResponse`.
  Skill: `/nodus-dap-evaluate`. GitHub: #106.

- **CHAN-001** (open, related to EMBED-003): A coroutine blocked on `recv()` of an
  empty channel is silently orphaned — `run_loop` exits when it sees no pending work,
  even if the host intends to feed data later. The only scheduler mechanism that
  prevents this exit (`scheduler._io_channels`) is a private internal attribute with
  no public API. Workaround: pre-populate the channel before `run_loop`, or use the
  subprocess-pipe pattern (daemon thread writes continuously). No GitHub issue yet —
  fix tracked under EMBED-003.

## Scheduler / coroutine execution-limit behavior (v4.0.0 known limitations)

These items are deferred to 4.0.1. They affect the experimental coroutine/scheduler
tier — the stable embedding API contract is not violated (limit breaches now correctly
surface as ok=False after the SCHED-002 fix).

- **SCHED-001** (deferred to 4.0.1, experimental scheduler timing): The execution
  deadline (`timeout_ms`) counts wall-clock time including time a coroutine spends
  cooperatively suspended in the scheduler timer heap (sleeping). A coroutine that
  calls `sleep(1000)` four times will be killed after 200ms total wall time even
  though it consumed no CPU. Workaround: `nodus run --time-limit N` (documented
  in `nodus run --help`). GitHub: #94.

- **SCHED-002 session-scope** (deferred to 4.0.1, experimental scheduler): A limit
  breach kills only the coroutine that tripped it; other coroutines continue running.
  The host correctly sees ok=False (fixed in 4.0.0 via `except RuntimeLimitExceeded:
  raise` in scheduler.py), but the session is not fully terminated — other coroutines
  drain. Full session termination on limit breach is a 4.0.1 fix. GitHub: #95.

- **SCHED-003** (covered in 4.0.0): Tests added in `test_scheduler.py::SchedulerSandboxLimitTests`
  to cover the `run_source` (sandbox-active) path. Pre-existing tests used raw VM
  with no limits. GitHub: #96.

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
- `vm.py` line count: ~2,500 lines as of v4.0.0 (Phase 6 added `secrets` import,
  `execution_unit_id`/`trace_id` attrs, `effect_store`, `circuit_breakers`, `builtin_syscall`,
  `builtin_syscall_list`, `_dict_to_record()`, and inlined 5 memory builtins were moved
  to `memory_module.py`). Further extraction of workflow/goal builtins and scheduler
  helpers is possible.

- **Phase 6 module.py propagation pattern:** `NodusModule.invoke_function` now propagates
  `trace_id`, `execution_unit_id`, `event_bus`, `effect_store`, `memory_store`, and
  `circuit_breakers` from caller_vm to each fresh module VM. Any new VM-level shared
  state added in future phases must also be added to this propagation block
  (`src/nodus/runtime/module.py:206-220`).

- **Phase 6 bridge return type:** `webhook_send` and `sql_query` host functions (in
  nodus-sdk) return Python dicts (maps), not Records. `.nd` code must use `r["key"]`
  not `r.key`. This is because `NodusRuntime._to_runtime_value()` converts dicts to
  dicts-of-dicts (maps), not Records. Intentional: Records are for host-constructed typed
  values, maps are for arbitrary JSON-shape returns.

- **@annotation syntax deferred to Phase 7:** `@exactly_once` and `@retry(...)` as
  language-level function annotations are the highest-DX gap remaining after Phase 6.
  Requires: lexer (`@` token), parser (annotation-before-fn), AST field, compiler lowering
  (emit EffectStore wrapper code). Estimated 4-5 days of frontend work.
  `effects.nd` provides the runtime primitives; the sugar is the outstanding piece.

- **Coverage baseline (pytest-cov 7.1.0, 2026-05-31):** Overall: 76% (19,126 stmts, 1638 tests). Gate raised to `--cov-fail-under=70` (was 60%; actual coverage 76% makes 70% a meaningful safety net). Three timing-sensitive tests deselected from the coverage run (they pass in the regular pytest step but fail under instrumentation overhead: `test_scheduler_fairness.py::test_multiple_tasks_progress`, `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`, `test_task_graph.py::TaskGraphTests::test_worker_death_detection`). Modules below 60%:
  - `src/nodus/__main__.py`: 0% (3 stmts — trivial entry point, not exercised by test suite)
  - `src/nodus/tooling/loader.py`: 48% (370 stmts — legacy pipeline; modern tests use ModuleLoader. Needs dedicated test pass.)
  - `src/nodus/tooling/tiny_vm_lang_functions.py`: 0% (4 stmts — demo/wildcard re-export helper, not a production code path)

- **mypy baseline (mypy 2.1.0, 2026-05-31 — Phase A+B+C+D: ZERO ERRORS):** CI gate is **blocking** (`continue-on-error` removed from ci.yml). Total: **0 errors across 114 source files** (down from 260 over 4 phases). Phase breakdown: A −70 (except-as-err, module-callable), B −42 (task_graph.py), C −60 (AST nodes, formatter, loader, dap, vm), D −88 (scatter across 37 files: scheduler, server/api, repl, lsp, optimizer, module_loader, module, workflow_lowering, testing/cli, ast_printer, 13 small files).

  | Module | Errors |
  |--------|--------|
  | `services/server.py` | 9 |
  | `tooling/repl.py` | 8 |
  | `runtime/module_loader.py` | 7 |
  | `lsp/server.py` | 7 |
  | `runtime/scheduler.py` | 6 |
  | `compiler/optimizer.py` | 5 |
  | `runtime/module.py` | 5 |
  | `services/api.py` | 5 |
  | `testing/cli.py` | 5 |
  | `orchestration/workflow_lowering.py` | 4 |
  | `tooling/analyzer.py` | 2 |
  | `frontend/ast/ast_printer.py` | 2 |
  | `frontend/lexer.py` | 2 |
  | `builtins/test_module.py` | 2 |
  | `builtins/http_module.py` | 2 |
  | `tooling/runner.py` | 2 |
  | `tooling/diagnostics.py` | 2 |
  | `cli/cli.py` | 2 |
  | (11 files with 1 error each) | 11 |

  **Phase A (2026-05-31):** except-as-err renames + module-callable fixes, −70 errors.
  **Phase B (2026-05-31):** `task_graph.py` — dict[str,Any] + checkpoint types + assert graph_id, −42 errors, now 0.
  **Phase C (2026-05-31):** formatter/dap/loader/vm/ast_nodes — AST `body: Block`, `_tok: Tok|None`, `import_error: NoReturn`, `BuiltinInfo.fn: Callable`, dict narrowing. −60 errors. All these modules now 0.
  **Next:** `services/server.py` (9), `tooling/repl.py` (8), `lsp/server.py`+`runtime/module_loader.py` (7 each). Goal: zero errors before promoting mypy to blocking. See `pyproject.toml [tool.mypy]` for configuration.

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

## Release Process Methodology (v4.0 additions)

Two new process documents address the class of problems where a bug either
reaches users before the maintainer knows about it, or sits unresolved:

- **`docs/governance/RELEASE_GATES.md §Gate 10`** — Pre-publish creator validation.
  Before every PyPI upload, the maintainer runs an adversarial validation session
  against the built wheel: writes programs targeting known complexity areas, triggers
  error categories, verifies every language quirk from `CLAUDE.md`. Any fixable bug
  gets fixed before the upload; any non-fixable bug gets filed immediately.
  This replaces the prior model where language bugs were discovered post-publish by
  the independent eval (Stage 5 / Playbook A).

- **`docs/governance/ISSUE_RESPONSE_POLICY.md`** — Issue response commitment.
  CRITICAL/HIGH bugs: response within 24h–1 week, fix within 1–2 weeks.
  AI-assisted development makes these timelines realistic (most clear-repro fixes
  take a single session). This policy is public and applies to all filed issues.

The specific incident that informed Gate 4 (closed-issue regression test gate) —
v3.0.1 shipping without a fix that was in source but not in the wheel — is already
documented in `RELEASE_GATES.md §Gate 4`. Gate 10 addresses the broader pattern
beyond that specific incident: catching unknown bugs before users encounter them,
not just verifying known fixes are present.

---

## Process Gaps (surfaced during v3.0 Phase 0, 2026-05-25)

- **Duplicate BUG-NNN:** BUG-029 was filed twice — [#27](https://github.com/Masterplanner25/Nodus/issues/27) (CLI `--help` grouping, no milestone, not in v3.0 scope) and [#30](https://github.com/Masterplanner25/Nodus/issues/30) (else-if syntax, v3.0 `phase:2-fix`). Root cause: the v2.1.1 handoff assigned the number from a running counter without checking existing issues. **Playbook action:** bug filing checklist must include a uniqueness check against open+closed issues before assigning a BUG-NNN. Capture in `RELEASE_PLAYBOOK.md` Phase 5.

- **Missing rubric eval for v2.1.0:** v2.1.0 shipped without a formal rubric eval. Guide-writing surfaced 23 issues but produced no composite score, leaving v2.0.0 (5.52) as the only comparable data point going into v3.0. **Playbook action:** every major/minor release must run the formal rubric eval and record the composite score before close. Guide-writing is supplementary, not a substitute. Capture in `RELEASE_PLAYBOOK.md` Phase 5.

## v4.0 Pre-publish Decisions (must resolve before shipping)

These items were surfaced during the 2026-05-30 ecosystem verification pass and are
not blocking current development but **must be decided before v4.0.0 publishes**.
Each has a GitHub issue for scope discussion.

- **WF-SCAN-001** (open, severity: medium, GitHub: #102): `LocalWorkflowStore` scans
  all `.nodus/workflow_framework/runs/*.json` on every sweeper iteration — O(n) over
  total historical runs. At 670+ accumulated test artifacts the sweep takes >2s,
  breaking the `test_worker_death_detected_by_sweeper` 500ms deadline. Short-term
  fix: default tests to `SQLiteWorkflowStore`. Medium-term fix: cap `_list_runs()` to
  a time-window or add a run-count ceiling. Affects `src/nodus_workflow/store.py`.

- **CIRC-001** (open, severity: medium, GitHub: #103): `nodus.vm.vm` imports
  `get_default_workflow_runner` from `nodus_workflow.runner` at module level
  (unconditional top-level import). Works at runtime because nodus initialises first,
  but any embedder or test that imports `nodus_workflow` before `nodus` in a fresh
  process hits a circular import. Fix: lazy import inside the function body (low risk),
  or dependency-inversion registry pattern (architecturally correct). Affects
  `src/nodus/vm/vm.py`.

- **NAME-COL-001** (open, severity: high, GitHub: #104): `nodus_schema` and
  `nodus_workflow` each exist as both an in-tree `src/` module (part of nodus-lang)
  and a separate standalone package in the publish sequence. Once both are on PyPI,
  install order silently determines which is imported. Must be resolved before publish:
  rename the standalone packages, move the in-tree modules under `nodus.*` namespace,
  or consolidate. Decision required before v4.0.0 tag.

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

---

## Phase 3B Open Implementation Questions: std:subprocess

From `docs/design/v4/04-subprocess-api.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 04-subprocess-api.md).

1. **Asyncio loop sharing with HTTP.** Both `std:http` and
   `std:subprocess` use the asyncio bridge. Tentative direction: shared
   per-VM loop; subprocess and HTTP asyncio tasks coexist on the same
   loop.

2. **Stream pump task lifecycle.** If the consumer doesn't read from
   `p.stdout`, the pump task keeps buffering. Tentative direction:
   bounded channel with backpressure; pump blocks when buffer fills,
   providing automatic backpressure into the OS pipe.

3. **Line buffer size limits.** A pathological process can emit a
   gigabyte-long line. Tentative direction: 1MB line limit; lines longer
   than that get split with a `line_truncated` flag on the channel
   record. Reconsider if real demand surfaces.

4. **Process group cleanup on VM shutdown.** Tentative direction: VM
   shutdown terminates all process groups it spawned with
   `process_group: true`, leaves others. Document explicitly.

5. **Windows job object inheritance.** Nested job objects have complex
   rules on Windows. Tentative direction: each spawn creates its own
   job; child jobs nest per Windows rules if Nodus itself is in a job.

6. **stdin write backpressure.** If user calls `p.stdin.send(...)`
   faster than the process consumes. Tentative direction: bounded write
   buffer; `send()` blocks (or yields in async context) when full.

---

## Phase 3B Open Implementation Questions: std:time

From `docs/design/v4/02-datetime-api.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 02-datetime-api.md).

1. **Year range support.** DST rules for years before 1900 or after
   2100 may be undefined for specific zones. Tentative direction:
   support 1900-2099 explicitly; outside that range return err with
   `category: "out_of_range"`.

2. **Zone lookup performance.** zoneinfo creates ZoneInfo objects on
   demand; the C implementation caches them. Verify caching behavior
   is sufficient for workloads that repeatedly create datetimes in the
   same zone.

3. **Thread safety of zoneinfo cache.** ZoneInfo objects are thread-safe
   to read but not to construct. The Nodus VM is single-threaded by
   default; verify no issues when embedded in a multi-threaded host.

4. **Format string caching.** Format strings should be tokenized once
   per unique string. Tentative direction: LRU cache or weakref dict,
   capped at ~100 entries to bound memory.

5. **Leap second handling.** Unix epoch ms assumes 86400 seconds per
   day always; leap seconds are not represented. Document the
   limitation; reconsider only if a concrete use case surfaces.

6. **`time.from_iso8601` sub-millisecond precision.** The spec allows
   arbitrary fractional-second precision. Tentative direction: truncate
   (don't round) to milliseconds. Document explicitly.

---

## Phase 3B Open Implementation Questions: std:hash / std:encoding / std:secrets

From `docs/design/v4/03-crypto-hashing-api.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 03-crypto-hashing-api.md).

1. **Builder state representation.** Internal flag or sentinel for
   "consumed" state. Tentative direction: boolean flag; subsequent
   update/finalize calls return err with `kind: "state_error"`.

2. **Streaming HMAC user demand.** Not in v4.0 scope. Track issues
   requesting it; reconsider for v4.x if 10+ distinct use cases surface.

3. **UUIDv7 entropy quality.** Verify Python `secrets` module provides
   sufficient entropy for the 74-bit random portion. Tentative direction:
   yes, `secrets.token_bytes(10)` provides 80 bits from the OS CSPRNG.

4. **`random_int` rejection sampling.** For uniform distribution without
   modulo bias. Tentative direction: use Python `secrets.randbelow()`
   pattern; well-tested.

5. **Hash record garbage collection.** Hash records hold a small bytes
   value (<=64 bytes for SHA-512). No special handling needed; standard
   Python GC suffices.

6. **`binascii` vs manual hex.** Tentative direction: use Python's
   `binascii.hexlify` (fast C code); manual implementation is ~3x slower.

---

## Phase 1 process improvement: bytecode-impact sections — RESOLVED 2026-05-27

**Surfaced by:** v4.0 Phase 1 design conversation for `05-string-
interpolation.md`. The frozen-bytecode constraint (`BYTECODE_VERSION = 4`
since v1.0, per LANGUAGE_VISION.md principle #4 which lists bytecode
instruction extensions as allowed but architecturally significant) was
not explicitly addressed in the first four Phase 1 design docs (HTTP,
subprocess, time, crypto). The omission was caught when string
interpolation surfaced the question.

**Process improvement:** every Phase 1 design doc going forward includes
a "Bytecode impact" section. The section states explicitly:

- Whether the feature requires new opcodes
- If yes: which opcodes, why they're needed, what `BYTECODE_VERSION`
  becomes, and what compatibility handling is required for older `.ndbc`
  files
- If no: explicitly state that `BYTECODE_VERSION` stays at 4 and the
  feature uses existing opcodes (typically `CALL_BUILTIN` for new
  stdlib functions)

The four prior docs (01-http-api, 02-datetime-api, 03-crypto-hashing-api,
04-subprocess-api) had bytecode-impact sections added retroactively in
the same commit that introduced `05-string-interpolation.md`.

**Rationale:** explicit bytecode-impact analysis forces every Phase 1
design to confront the frozen-bytecode contract rather than implicitly
assuming new opcodes are free. The four prior docs happened to not
require opcodes, but the omission was lucky rather than designed.

**Follow-up:** RESOLVED. PLAYBOOK_MAJOR.md Phase 1 guidance updated in
Phase 2 Session 2B (2026-05-27). The "Required sections in every Phase 1
design doc" block is now in the playbook's Phase 1 section. Requirement
enforced for all future Phase 1 design docs.

---

## Phase 3B Open Implementation Questions: string interpolation

From `docs/design/v4/05-string-interpolation.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 05-string-interpolation.md).

1. **Mode stack data structure.** Lightweight (list of mode enums) or
   richer structure (mode + per-mode state like paren_depth)? Tentative
   direction: richer structure for cleaner code; bounded memory cost
   (max 32 entries x constant per-entry).

2. **Recovery from unclosed forms.** When the lexer hits EOF inside a
   string or interpolation, recover for LSP or abort? Tentative
   direction: emit an error token with the partial content; LSP can use
   this for highlighting up to the error point.

3. **Multiline string interpolation.** Resolve via LANGUAGE_SPEC reading
   before lexer work begins; the mode-stack lexer handles multiline
   naturally if the feature exists.

4. **Empty interpolation diagnostic precision.** `"\()"` is a hard
   error; users who want a template placeholder write `"\(\"\")"`.

5. **Source position recording overhead.** Tentative direction: piggyback
   on existing source-position infrastructure; verify `.ndbc` file size
   impact is under ~5% for interpolation-heavy scripts.

6. **Migration tooling.** Tentative direction: not in v4.0; migration
   guide documents the manual `\(` -> `\\(` change. Reconsider if real
   users hit the breaking change frequently.

---

## Phase 3B Open Implementation Questions: IEEE 754 float division (doc 09)

From `docs/design/v4/09-ieee-754-division.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 09-ieee-754-division.md).

1. **Current integer division throw vs err.** Verify current v3.x
   integer div-by-zero behavior. If it throws, this doc's spec converts
   it to err record (consistent with v4.0 patterns). If it already errs,
   no change needed for integer path.

2. **Performance regression check.** Removing the zero-check in float
   division saves a comparison per division. Verify no performance
   regression elsewhere (Python's IEEE 754 path is implemented in C and
   should be as fast or faster than the explicit check).

3. **Bytecode disassembly output.** The disassembler should print `DIV`
   the same way; no opcode change. Verify disassembly tests don't need
   updates.

4. **Embedding API impact.** Python host code that catches Nodus's
   division-by-zero exception via the embedding API no longer sees it
   (because the exception isn't thrown). Document this in the embedding
   API migration notes.

---

## Phase 3B Open Implementation Questions: type() naming reconciliation (doc 10)

From `docs/design/v4/10-type-naming-reconciliation.md` § "Open
implementation questions for Phase 3B". These are resolved during Phase
3B execution; they do not affect the API surface (which is locked by
10-type-naming-reconciliation.md).

1. **Integer literals without suffix.** Verify that unadorned integer
   literals (e.g., `1`, `42`) are represented as Python `int` in the VM
   and that `type(42)` returns `"int"` and `type(42.0)` returns `"float"`.
   The type dispatch must be clean between the two.

2. **nan and infinity type.** Verify `type(math.nan)` returns `"float"`
   and `type(math.infinity)` returns `"float"`. These are Python floats;
   the type() implementation should naturally return `"float"` without
   special-casing.

3. **Grep tooling for migration.** Decide whether the migration guide
   should include a recommended `rg`/grep pattern for user codebases, or
   whether a `nodus migrate` subcommand is in scope for Phase 4. The
   grep pattern is low-effort; the subcommand is out of scope for v4.0.

4. **Type string stability contract.** Decide whether type() return
   strings are part of the stable public API (i.e., will never change
   again). If yes, document this in `LANGUAGE_SPEC.md` as a stability
   guarantee. Recommendation: yes, lock them as stable with v4.0.

---

## Phase 3B Open Implementation Questions: equality coercion narrowing (doc 11)

From `docs/design/v4/11-equality-coercion.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by 11-equality-coercion.md).

1. **Python bool/int subclass guard.** Verify the bool exclusion in the
   equality opcode handles all cases: `True`, `False`, bool variables,
   and bool results of expressions. Python's `isinstance(True, int)` is
   `True` — the guard must be in place or the coercion check fires.

2. **Current v3.x coercion implementation.** Audit `coerce_equal` (or
   equivalent) in the current VM to understand all active cross-type
   coercions. Only number↔number coercion survives; all others are
   removed. Create a test for each removed coercion to verify it's gone.

3. **`!=` operator consistency.** Verify `!=` is implemented as
   `not (a == b)` using the same narrowed equality logic — not as a
   separate coercion path. `0 != false` must return `true` in v4.0.

4. **List and record equality.** List equality (`[1, 2] == [1, 2]`) uses
   element-wise comparison. Verify that element comparisons within a list
   also use the narrowed equality — i.e., `[0] == [false]` is `false` in
   v4.0. The narrowing must propagate into recursive equality checks.

5. **Truthiness unchanged.** Confirm that narrowing `==` does not affect
   the `if` condition evaluation path. `if 0 { ... }` behavior is governed
   by truthiness rules, not the `==` opcode. These are separate code paths;
   verify they don't share the coercion logic being changed.

---

## Phase 3B Open Implementation Questions: err record location fields (doc 13)

From `docs/design/v4/13-err-record-location-fields.md` § "Open
implementation questions for Phase 3B". These are resolved during Phase
3B execution; they do not affect the API surface (which is locked by
13-err-record-location-fields.md).

1. **Source map completeness.** Verify that the compiler emits source map
   entries for every `CALL_BUILTIN` instruction — not just for some
   expressions. If the source map has gaps (no entry for a given PC), the
   augmentation produces `path: nil, line: nil, column: nil`. A gap
   analysis is needed during Phase 3B.

2. **REPL source map.** In REPL sessions, the `path` is not a real file
   path. Decide on the convention: `nil`, `"<repl>"`, or `"<stdin>"`.
   The `nil` convention is simplest; `"<repl>"` is more readable in
   error output.

3. **Performance of stack trace collection.** `build_stack_trace` walks
   the call stack on every err return. For deeply nested calls this may
   be non-trivial. Profile with a 100-deep call stack. If it's a
   regression, consider lazy stack collection (build on first access).

4. **User err literal — BUILD_ERR_RECORD opcode.** Verify the existing
   `BUILD_ERR_RECORD` opcode is the right place to hook augmentation.
   If user errs are built via a different path (e.g., via dict
   construction and a cast), find the correct interception point.

5. **Embedding API.** Python host code that creates Nodus err records
   directly (via the embedding API) should also have location fields.
   Decide whether the embedding API fills location fields or leaves them
   nil. Nil is acceptable for embedding; document the behavior.

6. **Err records in async context.** Verify that async builtin calls
   (e.g., `http.get_async`) go through the same `CALL_BUILTIN`
   interceptor and get location fields. If async builtins have a separate
   dispatch path, hook it separately.

---

## Phase 3B Open Implementation Questions: tool registry (doc 06)

From `docs/design/v4/06-tool-registry-library-handlers.md` § "Open
implementation questions for Phase 3B". These are resolved during Phase
3B execution; they do not affect the API surface (which is locked by
06-tool-registry-library-handlers.md).

1. **JSON Schema validator dependency.** Use Python's `jsonschema`
   package or implement a minimal validator? Tentative: `jsonschema`
   package; add to `pyproject.toml` if not already present.

2. **Warning emission mechanism.** Stderr write, or a more structured
   warning channel? Tentative: stderr write with library-overridable
   sink. Aligns with Python's `warnings` module pattern.

3. **Deprecated-warning state storage.** Per-VM dict of warned-tool
   names. Tentative: simple set; clears on VM shutdown.

4. **Registry capacity limit.** Should there be a maximum number of
   registered tools? Tentative: no hard limit; very large registries
   (10000+ tools) are unusual but not problematic.

5. **Thread-safety primitive.** RLock is the conservative choice; verify
   whether actual usage patterns warrant lighter-weight synchronization.
   Tentative: RLock initially; optimize if profiling shows contention.

6. **Function-value handler representation.** When a Nodus function value
   is registered as a handler, the registry stores a reference. Verify
   the reference doesn't prevent garbage collection of un-registered
   tools. Tentative: weak reference where possible; strong reference for
   tools currently invocable.

---

## Phase 3B Open Implementation Questions: test framework API (doc 07)

From `docs/design/v4/07-test-framework-api.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by
07-test-framework-api.md).

1. **Virtual clock semantics for nested async operations.** Tests that
   spawn coroutines that themselves spawn coroutines can have complex
   timing. Tentative: depth-first virtual time advancement when
   `test.advance_clock` is called.

2. **Filesystem watcher implementation.** Use `watchdog` Python package
   or implement minimal polling-based watcher? Tentative: `watchdog` for
   production; falls back to polling if not installed.

3. **Diff algorithm performance on very large values.** Records or lists
   with thousands of elements could produce huge diffs. Tentative:
   truncate diff to ~100 lines; show "N more changes omitted" indicator.

4. **Parallel execution thread safety.** Each worker runs in its own
   context, but shared resources (tool registry, env vars) need
   synchronization. Tentative: workers get independent VM instances;
   tests in parallel can't easily share state by design.

5. **Test discovery for nested suite-only files.** Files with
   `test.suite` but no `test.case` at top level (suites that group
   children). Tentative: recurse into nested suites; warn on suites with
   no test cases at all (likely a bug).

6. **Coverage integration point.** Connects to
   `08-test-framework-coverage.md`. Tentative: `--coverage` enables the
   line-execution event stream; the coverage collector subscribes and
   aggregates.

---

## Phase 3B Open Implementation Questions: test framework coverage (doc 08)

From `docs/design/v4/08-test-framework-coverage.md` § "Open
implementation questions for Phase 3B". These are resolved during Phase
3B execution; they do not affect the API surface (which is locked by
08-test-framework-coverage.md).

1. **Event bus implementation.** Does Nodus's existing event
   infrastructure (`--trace-errors`, debugger) support efficient per-line
   events? Tentative: extend existing event bus; profile overhead before
   committing.

2. **Source-position table size.** Adding executable_lines and
   excluded_lines per file to compiled modules adds memory. Tentative:
   small overhead; verify with realistic test suites.

3. **HTML report size for large codebases.** A project with 100K lines
   of source would produce a large coverage.html. Tentative: single file
   for v4.0; split into per-file pages if size becomes a problem.

4. **Coverage data merging across test runs.** Some workflows run tests
   multiple times with different configurations and want combined
   coverage. Tentative: not in v4.0; users merge JSON files externally.
   Add `--coverage-merge` flag in v4.x if demand surfaces.

5. **Line attribution for nested function definitions.** Anonymous
   functions defined inside other functions span multiple lines.
   Tentative: count the `fn` keyword line as executable; nested function
   body lines counted separately.

6. **Skip-comment parsing performance.** Parsing comments during
   compilation adds time. Tentative: only parse coverage comments when
   the compiler is invoked with coverage support enabled; falls back to
   non-coverage mode for production compilation.

---

## Phase 3B Open Implementation Questions: doc-vs-code gate (doc 12)

From `docs/design/v4/12-doc-vs-code-gate.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by
12-doc-vs-code-gate.md).

1. **Markdown parser choice.** `mistune` is fast and well-maintained;
   `markdown-it-py` is more spec-compliant. Tentative: start with
   `mistune`; switch if compliance issues surface.

2. **Symbol extractor sophistication.** Initial implementation uses
   regex-based patterns. May surface false positives or miss valid
   symbols. Tentative: ship with simple patterns; iterate based on
   real-world feedback in Phase 3B and beyond.

3. **Sandbox implementation.** Disabling network and subprocess in the
   Nodus VM during runtime-phase execution requires sandbox support that
   doesn't fully exist in v3.x. Tentative: use process-level isolation
   (run the example in a subprocess with restricted permissions)
   initially; in-process sandbox in v4.x.

4. **Wheel cache invalidation precision.** Git tree hash is coarse —
   any source change invalidates cache, even changes that don't affect
   the wheel. More precise tracking is possible but complex. Tentative:
   coarse invalidation initially; optimize if cache misses become a
   bottleneck.

5. **Output matching for non-deterministic outputs.** Some examples
   print timestamps, UUIDs, or other variable values. Tentative: gate
   supports a `nondeterministic` annotation that lets expected output
   include placeholders like `<TIMESTAMP>` that match any value.

6. **Parallel phase execution.** Static and runtime can run in parallel;
   closed-issues requires the wheel to be built first. Tentative:
   parallelize static + runtime; gate closed-issues on wheel
   availability.

---

## Phase 2 verification results

### finally-after-catch-return (verified 2026-05-26)

All 5 verification tests pass against v3.0.2 source. The v3.0.1 eval's
suggestion that this behavior works correctly is confirmed. No Phase 3
work required. Test file at `tests/test_finally_after_catch_return.py`
serves as a regression guard.

**Syntax observations recorded during verification (not bugs):**
- `try` is a statement, not an expression; `let r = try {...}` is a
  syntax error ("Unexpected 'try' in expression")
- `try { } finally { }` without a `catch` clause is a syntax error
  ("Expected 'catch', got 'finally'"); catch is required with finally
- `catch (e)` with parentheses is invalid; `catch e` is the correct form

All three are consistent with the language spec. The test file was
corrected to use valid syntax (try/catch/finally inside functions).

The existing `tests/test_finally.py` `FinallyCatchReturnTests` class
already covers this behavior comprehensively via the `run_program` API.

---

## Phase 3B Open Implementation Questions: len() returns int (doc 14)

From `docs/design/v4/14-len-returns-int.md` § "Open implementation
questions for Phase 3B". These are resolved during Phase 3B execution;
they do not affect the API surface (which is locked by
14-len-returns-int.md).

1. **Existing v3.x tests assuming float return.** Audit the test
   suite for tests that compare `len(x) == 5.0` (using float
   equality) versus `len(x) == 5i`. Update test assertions to use
   int.

2. **`range` boundary behavior with negative steps.** `range(10, 0,
   -1)` should produce ints 10, 9, ..., 1. Verify Python's `range`
   produces this naturally; if not, adjust the Nodus wrapper.

3. **`index_of` and `last_index_of` consistency.** Both should
   return `nil` for "not found"; verify no current code returns -1
   from one and nil from the other.

4. **`count(s, "")` edge case.** Counting empty substring in a
   string. Python's `str.count("")` returns `len(s) + 1` for non-
   empty strings and 1 for empty strings. Document this; users
   sometimes find it surprising.

5. **`range(0)` and `range(5, 5)`.** Both should produce empty
   iterables. Verify.

6. **Performance impact.** Returning `NodusInt` instead of `float`
   has a marginally different value-translation path. Verify no
   regression in hot loops using `len()` heavily.

---

## Phase 3B Open Implementation Questions: cyclic workflow err record (doc 15)

From `docs/design/v4/15-cyclic-workflow-err-record.md` § "Open
implementation questions for Phase 3B". These are resolved during
Phase 3B execution; they do not affect the API surface (which is
locked by 15-cyclic-workflow-err-record.md).

1. **Cycle detection algorithm.** Verify the current Python-side
   detection produces deterministic step ordering within a cycle.
   If non-deterministic, fix to ensure same output across runs.

2. **Self-cycle detection.** A step depending on itself (`step A
   after A`). Verify this is detected and reported with
   `cycle = ["A"]`.

3. **`workflow_name` for anonymous workflows.** What goes in the
   `workflow_name` field for workflows without explicit names?
   Tentative: `"<unnamed>"` string. Verify v3.x has a way to
   identify the workflow (file path? line number?) and include that.

4. **CALL_BUILTIN wrapping verification.** Ensure the err record
   returned by `run_workflow` properly receives location fields from
   the CALL_BUILTIN wrapper. This depends on
   `13-err-record-location-fields.md` being implemented first.

5. **Test for multi-cycle workflows.** Construct a workflow with
   two independent cycles; verify first cycle is reported, second
   is not.

6. **Migration audit.** Check the v3.x test suite and docs for any
   examples using the map-with-error-key pattern. Update to the
   err record pattern; ensure `nodus_gate --runtime` catches any
   examples in docs.
