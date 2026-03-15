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
- **Removal target:** v1.0
- **Replacement:** `ModuleLoader(...).load_source(src)` or `ModuleLoader(...).load_module_from_path(path)`
- **Migration:** Replace `compile_source(src, source_path=p)` with `ModuleLoader(project_root=root, vm=vm).load_module_from_source(src)`. For tooling commands that need the AST/bytecode directly, construct a `ModuleLoader` with a dedicated VM instance.
- **Reason:** `compile_source` predates the `ModuleLoader` pipeline; keeping two pipelines creates divergence risk.
