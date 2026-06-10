<!-- Reconciled 2026-05-29. Needs review before repo commit and push. -->

# Nodus Compatibility & Deprecation Timeline

> **This document is a deprecation timeline record, not a compatibility policy.**
> For the compatibility policy (what counts as breaking, semver rules, bytecode
> compatibility, embedding API commitment), see:
> **`docs/governance/COMPATIBILITY_MODEL.md`**



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
- **v2.1.0 (2026-05-24):** `json.parse` now returns maps (BREAKING from v2.0.0).
  Legacy `.tl` extension and `language.py` / `language.bat` launchers remain supported with warnings; no removal date set.
- **v2.1.1 (2026-05-24):** `allowed_paths` sandbox now enforced for `std:fs` module calls (security fix, BUG-046). No deprecation or compatibility impact — scripts relying on the bypass were relying on a bug.
- **v3.0.2 (2026-05-25):** `math.log_base` export removed; use `math.log(n, base)` instead. Patch release fixing BUG-V31E-01 (1I parse error) and BUG-V31E-02 (math.log argument order).
- **v4.0.0 (2026-06-04):** Major release. BYTECODE_VERSION 4. New opcodes, annotation syntax, compound assignment, multiline expressions, AI-native primitives, full security sandbox, coroutine scheduler, goals/workflows DSL. See CHANGELOG for full scope.
- **v4.0.1 (2026-06-10):** Patch release. `@exactly_once`/`@retry` decorators, `+=`/`-=`/`*=`/`/=` operators, multiline expressions, `std:math` bit ops, `allowed_commands`/`allowed_hosts` sandbox allowlists, `event_sinks`/`coroutine_timeout_ms`/`get_execution_stats` embedding API additions, `clear_shared_state()`, bounded channels. No bytecode break.
- **v4.0.2 (2026-06-10, current):** Patch release. Bug fixes: `@exactly_once` idempotency and nil-return (#207/#208), `allowed_commands` not enforced via module import (#209), `@retry` silent skip when dependency missing (#210), `event_sinks` callable support (#212). Trailing comma in list/call syntax (#211). No bytecode break.

## Migration Path
- Use `.nd` files for new code.
- Use the `nodus` CLI (`nodus run`, `nodus check`, `nodus fmt`, `nodus repl`).
- Keep legacy `.tl` only for compatibility; the stdlib still ships `.tl` mirrors for now.
