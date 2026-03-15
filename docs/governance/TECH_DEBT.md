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

- VM is a "god class" that bundles opcode dispatch, builtins, coroutine handling, workflow/task graph logic, and runtime I/O in a single 2.3k-line file (`src/nodus/vm/vm.py`). The builtin registry alone spans ~90 entries near the class initializer. Consider extracting builtin groups into separate modules and registering them at VM construction time.
- Compiler contains unreachable `For`/`ForEach` branches that return immediately (`src/nodus/compiler/compiler.py:513` and `src/nodus/compiler/compiler.py:515`), after already handling those node types earlier (`src/nodus/compiler/compiler.py:412` and `src/nodus/compiler/compiler.py:431`).
- Long `elif` dispatch chains are used in the compiler and VM (`src/nodus/compiler/compiler.py:327` for `compile_stmt` and `src/nodus/compiler/compiler.py:540` for `compile_expr`; `src/nodus/vm/vm.py:1777` for `execute`). Consider dispatch tables for maintainability.
- AST node type hints are overly broad (`object`) in `src/nodus/frontend/ast/ast_nodes.py` (e.g., `Unary.expr`, `Bin.a`, `Bin.b`, `Call.callee`, `Let.expr`, `If.cond`).
- Deadline checking calls `time.monotonic()` on every instruction in `record_instruction` (`src/nodus/vm/vm.py:1731`). Consider batching the check to reduce hot-path overhead.
- Channel queues use list `pop(0)` for dequeue and list storage (`src/nodus/runtime/channel.py` and `src/nodus/vm/vm.py:845`), which is O(n). Consider `collections.deque`.
- try/catch error payload is flattened to a string (`src/nodus/vm/vm.py:288` in `handle_exception`), preventing structured error inspection in user code.
- Anonymous functions share the same display name (`src/nodus/compiler/compiler.py:722` uses `__anon` for all function expressions). Consider unique names for traceability.
- File I/O builtins are unrestricted by default (`src/nodus/vm/vm.py:1464-1510`). An allowlist hook is available (`VM.allowed_paths`) and now wired into CLI/server; it remains opt-in.
- Relative import containment for non-std, non-package relative paths (`src/nodus/tooling/loader.py:150-170` and `src/nodus/runtime/module_loader.py:500-525`) is now guarded by project-root containment checks.
- HTTP server endpoints now support bearer-token auth (`src/nodus/services/server.py:780-920` and `src/nodus/services/server.py:960-1120`). It remains opt-in, but non-local binding requires a token.
- VM call stack has no explicit max depth check (e.g., `src/nodus/vm/vm.py:1652` `call_closure` and `src/nodus/vm/vm.py:2067` `CALL` opcode paths). Consider a max frame depth for sandbox safety.
- `input()` uses `input_fn` defaulting to Python `input()` (`src/nodus/vm/vm.py:76` and `src/nodus/vm/vm.py:1360`). Server mode now blocks `input()` by default, but embedding still uses the default unless configured.

## Additional Validated Items

- Optimizer uses list equality checks per pass (`src/nodus/compiler/optimizer.py:43`) instead of a dirty-flag, which is O(n) per pass.
- Module qualification uses `__modN__` prefixes (`src/nodus/tooling/loader.py:70`), but there is no documentation in code or docs explaining the scheme.
