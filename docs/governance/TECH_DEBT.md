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

## Validated Findings

- ✅ VM builtin extraction complete: I/O, math, coroutine, and collection builtins extracted into `src/nodus/builtins/` category modules and registered at VM construction time via `BuiltinRegistry` (`src/nodus/builtins/__init__.py`).
- Compiler contains unreachable `For`/`ForEach` branches that return immediately (`src/nodus/compiler/compiler.py:513` and `src/nodus/compiler/compiler.py:515`), after already handling those node types earlier (`src/nodus/compiler/compiler.py:412` and `src/nodus/compiler/compiler.py:431`).
- ✅ VM execute() dispatch table implemented: if/elif chain replaced with dict dispatch (_dispatch) built at construction time; each opcode is handled by a _op_XXX method (src/nodus/vm/vm.py).
- Long `elif` dispatch chains remain in the compiler (compiler.py:327 for compile_stmt and compiler.py:540 for compile_expr). Consider dispatch tables for maintainability.
- AST node type hints are overly broad (`object`) in `src/nodus/frontend/ast/ast_nodes.py` (e.g., `Unary.expr`, `Bin.a`, `Bin.b`, `Call.callee`, `Let.expr`, `If.cond`).
- Deadline checking calls `time.monotonic()` on every instruction in `record_instruction` (`src/nodus/vm/vm.py:1731`). Consider batching the check to reduce hot-path overhead.
- ✅ Channel waiting queues converted to `collections.deque`: `waiting_receivers` and `waiting_senders` in `channel.py`; `pop(0)` replaced with `popleft()` in `builtins/coroutine.py`.
- try/catch error payload is flattened to a string (`src/nodus/vm/vm.py:288` in `handle_exception`), preventing structured error inspection in user code.
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
