# Gate 10 Creator Validation — v4.0.1

**Date:** 2026-06-10
**Wheel:** `nodus_lang-4.0.1-py3-none-any.whl`
**Validator:** Maintainer (Masterplanner25)
**Validation venv:** `.venv-validation` (clean install from built wheel)

## Version check

```
$ nodus --version
Nodus 4.0.1
```

## Eval results

### quirk_probe.nd — ALL QUIRKS CONFIRMED

All 10 quirk probes passed. No regressions from v4.0.0.

### language_exerciser.nd — ALL EXERCISES PASSED

All 7 exercise categories passed (functions/recursion, math, strings, lists,
maps, records, JSON round-trip).

### framework_capabilities.nd — ALL FRAMEWORK PROBES PASSED

All 10 framework probes passed (router, event bus, middleware, service registry,
state machine, plugin registry, pipeline, rule engine, closure state,
coroutines + channels).

## New features spot-checked

- `@retry` and `@exactly_once` decorator syntax: lowered at compile time, no new opcodes.
- `+=`, `-=`, `*=`, `/=` compound assignment: parser desugaring confirmed.
- Multiline expressions inside delimiters: confirmed spans lines in `(`, `[`, `{`.
- `NodusRuntime(allowed_commands=[...])` / `allowed_hosts`: sandbox gating confirmed.
- `NodusRuntime(event_sinks=[...])` / `coroutine_timeout_ms` / `get_execution_stats()`: embedding API additions confirmed.
- Bounded `channel(maxsize=N)`: capacity enforcement confirmed.

## Verdict

**PASS — cleared for PyPI upload.**

No regressions. All three standard eval scripts print their success message
from the built wheel. New features behave as documented in the changelog.
