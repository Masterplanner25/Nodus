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
- **Removal target:** v1.0 (after bytecode cache invalidation window closes)
- **Status:** Retained as a compatibility fallback in the VM dispatch table (`_op_load_local`). The compiler emits `LOAD_LOCAL_IDX` for all normal local variable access. Three fallback paths (`compiler.py` lines 584, 619, 731) still emit name-keyed `LOAD_LOCAL` when slot index is unavailable (`symbol.index is None`). These fallback paths must be audited and fixed before `LOAD_LOCAL` can be removed from the VM dispatch table.
- **Migration:** Recompile source files. The compiler automatically emits `LOAD_LOCAL_IDX` for all new bytecode. The bytecode cache version bump (0x01 → 0x02 in v0.8.0) triggers automatic recompilation of any cached modules on next load — no user action required.
- **Note:** Bytecode compiled before v0.8.0 (cache version 0x01) is silently invalidated on load and recompiled with `LOAD_LOCAL_IDX`. The `LOAD_LOCAL` fallback handler exists only for in-memory bytecode constructed outside the compiler (e.g., tests that hand-craft instruction lists).
- **Prerequisite for removal:** Audit and fix the three compiler fallback paths (compiler.py lines 584, 619, 731). See TECH_DEBT.md.
