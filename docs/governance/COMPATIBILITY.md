# Nodus Compatibility & Deprecation Timeline

Nodus keeps legacy compatibility for now, but the following items are deprecated and will be revisited in future releases.

## Deprecated (Still Supported)
- `.tl` legacy extension (CLI emits warnings on use).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers (CLI emits warnings on use).

## Timeline

- v0.9.x: continued support with warnings.
- **v1.0.0 (2026-03-15):** `compile_source()` loader body removed.
  Legacy launchers (`.tl`, `language.py`, `language.bat`) are still supported with
  warnings pending migration verification. Re-evaluation deferred to v1.1.x.
- **v2.1.0 (2026-05-24, current):** `json.parse` now returns maps (BREAKING from v2.0.0).
  Legacy `.tl` extension and `language.py` / `language.bat` launchers remain supported with warnings; no removal date set.

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`, `nodus repl`).
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
