# Nodus Compatibility & Deprecation Timeline

Nodus keeps legacy compatibility for now, but the following items are deprecated and will be revisited in future releases.

## Deprecated (Still Supported)
- `.tl` legacy extension (CLI emits warnings on use).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers (CLI emits warnings on use).

## Timeline

- v0.9.x: continued support with warnings.
- **v1.0.0 (2026-03-15, current):** `compile_source()` loader body removed.
  Legacy launchers (`.tl`, `language.py`, `language.bat`) are still supported with
  warnings pending migration verification. Re-evaluation deferred to v1.1.x.

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`) and the REPL via `python -m nodus.tooling.repl`.
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
