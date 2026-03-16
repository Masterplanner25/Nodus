# Deprecations

This document tracks known deprecation warnings and suggested remediation steps.

## Product Deprecations

- Legacy `.tl` file extension is supported with warnings. See `docs/governance/COMPATIBILITY.md`.
- Legacy launchers `language.py` / `language.bat` are supported with warnings. See `docs/governance/COMPATIBILITY.md`.

## Test Runtime Warnings

- `starlette.formparsers` warns about `multipart` import deprecation.
  Remediation: update dependency usage to `python_multipart` or bump Starlette to a version that no longer imports the deprecated module.
- `websockets.legacy` deprecation warnings from the Starlette/Uvicorn WebSocket stack.
  Remediation: upgrade `websockets`/`uvicorn` (and any pinned transitive deps) to versions that avoid the legacy API.
- `websockets.server.WebSocketServerProtocol` deprecation warning (transitive from Uvicorn).
  Remediation: same as above.

## API Deprecations

### `compile_source()` in `src/nodus/tooling/loader.py`
- **Deprecated since:** v0.5.0
- **Internal callers removed:** v0.8.0 (runner.py, vm.py, dap/server.py all migrated to ModuleLoader)
- **Public stub (`nodus.__init__`) removed:** v0.9.0
- **Function body (`nodus.tooling.loader`) removed:** v1.0
- **Status:** Fully removed. Public re-export removed in v0.9.0. Function body removed
  in v1.0. All callers migrated. No remaining references in codebase.
- **Replacement:** `ModuleLoader(...).load_module_from_source(src)` or
  `NodusRuntime(...).run_source(src)` for embedding use cases.
- **Migration:** Replace `compile_source(src, source_path=p)` with
  `ModuleLoader(project_root=root, vm=vm).load_module_from_source(src)`. For tooling
  commands that need the AST/bytecode directly, use `ModuleLoader.compile_only(src, module_name=name)`.
- **Reason:** `compile_source` predates the `ModuleLoader` pipeline; keeping two
  pipelines creates divergence risk.
- **Warning discrepancy:** The `DeprecationWarning` emitted in v0.8.0 stated
  "will be removed in v1.0" but the public stub was removed one version early at v0.9.0.
  External users who received this warning should migrate to `NodusRuntime` or
  `ModuleLoader` immediately.

### `LOAD_LOCAL` opcode
- **Deprecated since:** v0.8.0 (superseded by `LOAD_LOCAL_IDX`)
- **Removed in:** v1.0
- **Status:** ⛔ Removed. The three compiler fallback paths at `compiler.py` lines 584,
  619, and 731 were audited in v1.0. All three were confirmed unreachable: `SymbolTable.define()`
  assigns `symbol.index` whenever `_current_function_scope()` is not None, which is exactly
  the same condition as `in_function_scope()`. The "local + in function scope + index is None"
  case is a logical contradiction. The fallback emissions were replaced with `assert` guards.
  `LOAD_LOCAL` was removed from the VM dispatch table (`_build_dispatch_table()`). The handler
  method (`_op_load_local`) was replaced with a `RuntimeError` tombstone. `BYTECODE_VERSION`
  bumped from 2 to 3, invalidating any cached bytecode containing `LOAD_LOCAL` instructions.
- **Migration:** Recompile source files. `BYTECODE_VERSION` 3 invalidates all version-2
  caches automatically on next load — no user action required.
- **If tombstone is encountered at runtime:** The error message directs the user to recompile.
  A `RuntimeError` is raised with the opcode name and instructions to recompile.
