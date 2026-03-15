# Nodus Compatibility & Deprecation Timeline

Nodus keeps legacy compatibility for now, but the following items are deprecated and will be revisited in future releases.

## Deprecated (Still Supported)
- `.tl` legacy extension (CLI emits warnings on use).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers (CLI emits warnings on use).

## Planned Timeline
- 0.9.x (current `0.9.0`): continue support with warnings.
- 1.0.0: re-evaluate removal readiness. If migration is complete, legacy launchers
  and `.tl` extension support will be removed. `compile_source()` loader body removal
  also targeted for v1.0 (public stub already removed in v0.9.0).

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`) and the REPL via `python -m nodus.tooling.repl`.
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
