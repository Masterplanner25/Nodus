# Nodus Compatibility & Deprecation Timeline

Nodus keeps legacy compatibility for now, but the following items are deprecated and will be revisited in future releases.

## Deprecated (Still Supported)
- `.tl` legacy extension (CLI emits warnings on use).
- `tiny_vm_lang_functions.py` compatibility shim.
- `language.py` / `language.bat` legacy launchers (CLI emits warnings on use).

## Planned Timeline
- 0.3.x (current `0.3.0`): continue support with warnings.
- 0.4.x: re-evaluate removal readiness and publish a migration window.
- 0.5.x (tentative): consider removal if migration is complete.

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`, `nodus repl`).
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
