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
- Compiler contains unreachable `For`/`ForEach` branches that return immediately (`src/nodus/compiler/compiler.py:513` and `src/nodus/compiler/compiler.py:515`), after already handling those node types earlier (`src/nodus/compiler/compiler.py:412` and `src/nodus/compiler/compiler.py:431`).
- ✅ VM execute() dispatch table implemented: if/elif chain replaced with dict dispatch (_dispatch) built at construction time; each opcode is handled by a _op_XXX method (src/nodus/vm/vm.py).
- Long `elif` dispatch chains remain in the compiler (compiler.py:327 for compile_stmt and compiler.py:540 for compile_expr). Consider dispatch tables for maintainability.
- AST node type hints are overly broad (`object`) in `src/nodus/frontend/ast/ast_nodes.py` (e.g., `Unary.expr`, `Bin.a`, `Bin.b`, `Call.callee`, `Let.expr`, `If.cond`).
- Deadline checking calls `time.monotonic()` on every instruction in `record_instruction` (`src/nodus/vm/vm.py:1731`). Consider batching the check to reduce hot-path overhead.
- ✅ Channel waiting queues converted to `collections.deque`: `waiting_receivers` and `waiting_senders` in `channel.py`; `pop(0)` replaced with `popleft()` in `builtins/coroutine.py`.
- ⚠️ `_op_throw` (`src/nodus/vm/vm.py:~2092`) stringifies non-string thrown values via `value_to_string()`. `handle_exception` (vm.py:281) is already correct — it pushes a structured `Record(kind='error')` with all fields. Only the `_op_throw` path needs fixing (tracked in Open Items).
- Anonymous functions share the same display name (`src/nodus/compiler/compiler.py:722` uses `__anon` for all function expressions). Consider unique names for traceability.
- File I/O builtins are unrestricted by default (`src/nodus/vm/vm.py:1464-1510`). An allowlist hook is available (`VM.allowed_paths`) and now wired into CLI/server; it remains opt-in.
- Relative import containment for non-std, non-package relative paths (`src/nodus/tooling/loader.py:150-170` and `src/nodus/runtime/module_loader.py:500-525`) is now guarded by project-root containment checks.
- HTTP server endpoints now support bearer-token auth (`src/nodus/services/server.py:780-920` and `src/nodus/services/server.py:960-1120`). It remains opt-in, but non-local binding requires a token.
- VM call stack has no explicit max depth check (e.g., `src/nodus/vm/vm.py:1652` `call_closure` and `src/nodus/vm/vm.py:2067` `CALL` opcode paths). Consider a max frame depth for sandbox safety.
- `input()` uses `input_fn` defaulting to Python `input()` (`src/nodus/vm/vm.py:76` and `src/nodus/vm/vm.py:1360`). Server mode now blocks `input()` by default, but embedding still uses the default unless configured.

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
`pending_iter_next` removed. 14 flag sites removed across `vm.py`. All 377 tests pass.
Coroutine + iteration interaction tests added.

`GET_ITER` and `ITER_NEXT` are now **stable**. See `FREEZE_PROPOSAL.md §
"v1.0 GET_ITER/ITER_NEXT Decision"` and `INSTRUCTION_SEMANTICS.md § 14`.

## Exception model finalization

`SETUP_TRY` / `POP_TRY` / `THROW` are provisional pending a decision on `finally` blocks
and typed catches. If either feature is added before v1.0, these opcodes need new operands
or companion opcodes.

**v0.9 decision:** `finally` blocks deferred to v1.0. Exception opcodes remain provisional.
See `FREEZE_PROPOSAL.md § "v0.9 Opcode Decisions"` for rationale.

## Open Items (not yet complete)

- ✅ compile_source() fully removed in v1.0. Internal callers migrated to ModuleLoader in v0.8. Public stub removed from nodus.__init__ in v0.9.0. Loader body and last test caller (test_import_containment.py) removed in v1.0. 0 remaining references.
- ✅ `LOAD_LOCAL_IDX` slot-indexed fast path: Implemented in v0.8. Compiler now emits `FRAME_SIZE n`, `STORE_LOCAL_IDX slot`, and `LOAD_LOCAL_IDX slot` for all function-scope locals. Frame carries a pre-allocated `locals_array` (list) and `locals_name_to_slot` mapping. `capture_local` updated for Cell boxing via array. Cache serialization updated (`local_slots` in FunctionInfo). Bytecode version bumped to 2.
- ✅ compile_source() public stub removed in v0.9 from nodus.__init__. Loader body retained for internal use; removal target v1.0. test_import_containment.py uses loader directly and will need updating at v1.0.
- `LOAD_LOCAL` deprecated opcode: superseded by `LOAD_LOCAL_IDX` in v0.8; retained as fallback for bytecode compiled before version 2. Remove at v1.0 once all caches have been invalidated by the version bump. Also remove `_op_load_local` handler from VM dispatch table.
- ✅ Registry publish and auth: `nodus publish` command and token management implemented in v0.9. `RegistryClient` now supports Bearer token auth. `get_registry_token()` in `package_manager.py` resolves tokens via CLI flag, `NODUS_REGISTRY_TOKEN` env var, or `~/.nodus/config.toml`. `nodus login`/`nodus logout` CLI commands added. See `docs/tooling/PACKAGE_MANAGER.md` Authentication section.
- ✅ Provisional opcode resolution (partial): `GET_ITER`, `ITER_NEXT`, `BUILD_MODULE`, `YIELD` promoted to stable at v1.0. 3 opcodes remain provisional: `SETUP_TRY`, `POP_TRY`, `THROW` (all blocked on `finally` implementation). See `FREEZE_PROPOSAL.md` for details.
- ✅ `GET_ITER`/`ITER_NEXT` Iterator protocol cleanup: complete at v1.0. `pending_get_iter`/`pending_iter_next` flags replaced by first-class `Iterator` protocol object. VM-only change; no compiler or `.nd` source impact. See section above and FREEZE_PROPOSAL.md v1.0 decisions.
- `finally` block implementation: requires new opcode or extended `SETUP_TRY` operand. See FREEZE_PROPOSAL.md v0.9 decisions.
- ✅ `_op_throw` structured value preservation: `_op_throw` (vm.py:~2092) now preserves structured values (Records, lists) as `err.payload` in the catch block rather than stringifying. Strings use the message directly; primitives are stringified; Records/lists are passed as `payload` with `kind="thrown"`. `LangRuntimeError` now carries an optional `payload` field. `handle_exception` includes `payload` in the error Record when present. Fixed in v1.0.
- ✅ `YIELD_VALUE`/`SEND` opcode evaluation: decision made. YIELD frozen as-is. No new opcode needed — no user-facing send-value use cases in `.nd` source. Recorded in FREEZE_PROPOSAL.md.
- ✅ `BUILD_MODULE` stability declaration: promoted to stable as part of v1.0 module system freeze. Module system feature-complete. Recorded in FREEZE_PROPOSAL.md and ROADMAP.md.
- ✅ `NodusRuntime` added to `__all__`: `src/nodus/__init__.py` now imports and exports `NodusRuntime` directly. `from nodus import NodusRuntime` works as of v1.0. EMBEDDING.md updated. Fixed in v1.0.
- `LOAD_LOCAL` compiler fallbacks: `DEPRECATIONS.md` claimed the compiler no longer emits `LOAD_LOCAL` — this is false. Three fallback paths at `compiler.py` lines 584, 619, 731 still emit name-keyed `LOAD_LOCAL` instructions when `symbol.index is None`. These paths must be audited and fixed (or confirmed unreachable) before `LOAD_LOCAL` can be removed from the VM dispatch table. Target: v1.0.
- `vm.py` line count: ~2,052 lines after Phase 2 extraction. Further extraction of workflow/goal builtins and scheduler helpers is possible.

- `.ndignore` support: `nodus publish` currently excludes a hardcoded list (`.nodus/`, `__pycache__/`, `.git/`, `*.pyc`, `nodus.lock`, `.gitignore`). A `.ndignore` file would give package authors control over what is included in the published archive. Target: post-v0.9.

## Untracked Items (surfaced in v0.9 assessment, 2026-03-15)

- ✅ `compile_source()` removal-target doc contradiction: resolved in v0.9.0. Public stub removed from `nodus.__init__` at v0.9 (one version earlier than the `DeprecationWarning` message indicated). ROADMAP.md, DEPRECATIONS.md, TECH_DEBT.md, and CHANGELOG.md all updated to reflect v0.9.0 removal. The warning message discrepancy is noted in DEPRECATIONS.md and CHANGELOG.md.

- ✅ Stale `loader.py` header comment: resolved. The header comment in `src/nodus/tooling/loader.py` no longer claims `compile_source()` is used by `nodus check`, `nodus ast`, or `nodus dis` commands. Those commands use `ModuleLoader`. The comment now correctly notes that the function body is retained for internal tooling use only until v1.0.

- ✅ `INSTRUCTION_SEMANTICS.md` missing `pending_get_iter` / `pending_iter_next` documentation: resolved. GET_ITER and ITER_NEXT entries now fully document the closure-callback mechanism, the pending flags, and the RETURN handler post-processing. See `docs/runtime/INSTRUCTION_SEMANTICS.md` §14.

- ✅ `NODUS_SERVER_TOKEN` vs. `NODUS_REGISTRY_TOKEN` naming split: now documented in `docs/tooling/PACKAGE_MANAGER.md` (Authentication section, "NODUS_SERVER_TOKEN vs NODUS_REGISTRY_TOKEN" subsection). The two tokens are independent: `NODUS_SERVER_TOKEN` authenticates requests to a running Nodus server process; `NODUS_REGISTRY_TOKEN` authenticates package registry requests.

- ✅ `--registry` CLI flag wired: `nodus install` now accepts `--registry <url>` and `--registry-token <token>` flags. Both are parsed and passed to `install_dependencies_for_project()`. Closed as part of v0.9 registry auth work.

- ✅ `test_task_reassignment_after_worker_failure` flaky test: fixed in v0.9.1. Root cause: `_poll_job` was spinning on `WorkerManager.poll()` every 10ms with a 2-second window; under concurrency the VM thread occasionally missed the window. Fix: added `WorkerManager.wait_for_job()` which blocks on the existing `_cond` condition variable (already notified by `submit()`). `_poll_job` now delegates to `wait_for_job()`. No polling, no race. Test runtime: ~20ms (was up to 2s). See `src/nodus/services/server.py`.

- ✅ Formatter AST coverage audit complete: all 48 AST node types handled in format_stmt()/format_expr(). Added Yield, Throw, TryCatch, DestructureLet, VarPattern, ListPattern, RecordPattern handlers. See tests/test_formatter_coverage.py.
- ✅ Opcode set stabilization plan: formal freeze proposal published at docs/governance/FREEZE_PROPOSAL.md. 47 opcodes classified (39 stable, 7 provisional, 1 deprecated). Freeze prerequisites, post-freeze extension process, and version history documented. See GET_ITER/Exception model sections above for provisional opcode cleanup items.

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
