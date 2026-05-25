# Nodus Examples — Retired

This file has been retired. The examples it contained were outdated and
contained several syntax errors against Nodus v2.1.x (wrong import syntax,
bare-identifier map keys, missing `while` parentheses, obsolete DSL forms).

The content has been superseded by the `docs/guide/` directory, which
contains tested, operational guides with verified code examples:

- [getting-started.md](../guide/getting-started.md) — install, first script, REPL, two-file project
- [types-and-values.md](../guide/types-and-values.md) — numbers, strings, lists, maps, records, nil
- [error-handling.md](../guide/error-handling.md) — try/catch/finally, throw, err fields
- [modules-and-imports.md](../guide/modules-and-imports.md) — imports, exports, stdlib, resolution
- [standard-library.md](../guide/standard-library.md) — all std: modules, function reference
- [working-with-maps.md](../guide/working-with-maps.md) — map creation, has_key, accumulation
- [working-with-json.md](../guide/working-with-json.md) — json.parse, stringify, nested access
- [debugging.md](../guide/debugging.md) — --trace, nodus check, interactive debugger
- [embedding-nodus.md](../guide/embedding-nodus.md) — NodusRuntime, sandbox, register_function
- [workflows-and-tasks.md](../guide/workflows-and-tasks.md) — workflow/goal DSL, steps, state

All examples in those files were tested against nodus-lang v3.0.
