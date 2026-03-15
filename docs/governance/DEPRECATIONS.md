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
- **Deprecated since:** v0.5
- **Internal callers removed:** v0.8 (runner.py, vm.py, dap/server.py all migrated to ModuleLoader)
- **Removal target:** v1.0
- **Status:** Public stub retained in `nodus.__init__` until v1.0; emits `DeprecationWarning`.
- **Replacement:** `ModuleLoader(...).load_module_from_source(src)` or `ModuleLoader(...).load_module_from_path(path)`
- **Migration:** Replace `compile_source(src, source_path=p)` with `ModuleLoader(project_root=root, vm=vm).load_module_from_source(src)`. For tooling commands that need the AST/bytecode directly, construct a `ModuleLoader` and call `compile_only(src, module_name=name)`.
- **Reason:** `compile_source` predates the `ModuleLoader` pipeline; keeping two pipelines creates divergence risk.

### `LOAD_LOCAL` opcode
- **Deprecated since:** v0.8.0 (superseded by `LOAD_LOCAL_IDX`)
- **Removal target:** v1.0 (after bytecode cache invalidation window closes)
- **Status:** Retained as a compatibility fallback in the VM dispatch table (`_op_load_local`). The compiler no longer emits `LOAD_LOCAL` for any new compilation; all function-scope locals use `LOAD_LOCAL_IDX slot` instead.
- **Migration:** Recompile source files. The compiler automatically emits `LOAD_LOCAL_IDX` for all new bytecode. The bytecode cache version bump (0x01 → 0x02 in v0.8.0) triggers automatic recompilation of any cached modules on next load — no user action required.
- **Note:** Bytecode compiled before v0.8.0 (cache version 0x01) is silently invalidated on load and recompiled with `LOAD_LOCAL_IDX`. The `LOAD_LOCAL` fallback handler exists only for in-memory bytecode constructed outside the compiler (e.g., tests that hand-craft instruction lists).
