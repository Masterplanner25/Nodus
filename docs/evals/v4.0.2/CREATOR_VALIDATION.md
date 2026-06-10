# Nodus v4.0.2 — Creator Validation (Gate 10)

**Date:** 2026-06-10
**Wheel:** `nodus_lang-4.0.2-py3-none-any.whl`
**Installed version:** `Nodus 4.0.2` (confirmed via `nodus --version`)

---

## Standard eval scripts

All three run against the installed wheel (not dev source).

| Script | Result |
|--------|--------|
| `tests/eval/quirk_probe.nd` | ALL QUIRKS CONFIRMED |
| `tests/eval/language_exerciser.nd` | ALL EXERCISES PASSED |
| `tests/eval/framework_capabilities.nd` | ALL FRAMEWORK PROBES PASSED |

No regressions observed.

---

## Release scope

Patch release — bug fixes from the v4.0.1 stress eval:

- **#207/#208** — `@exactly_once` idempotency and nil return (compiler `_lower_exactly_once`)
- **#209** — `allowed_commands` not enforced via module import (`module.py invoke_function`)
- **#210** — `@retry` silently skips body when nodus-retry missing (now raises dependency error)
- **#211** — Trailing comma in list literals and function call argument lists
- **#212** — `event_sinks` callable (lambda) support in `RuntimeEventBus.emit`
- **#213** — `channel()` docs corrected to positional API
- **#214** — CHANGELOG/docs corrections

No new opcodes. BYTECODE_VERSION unchanged at 4.

---

## Test suite

1798 passed, 2 skipped (expected: nodus_retry skip, timing-sensitive flaky test excluded).
