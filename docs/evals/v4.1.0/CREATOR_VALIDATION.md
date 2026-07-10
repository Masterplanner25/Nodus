# v4.1.0 — Pre-publish Creator Validation

**Date:** 2026-07-10
**Variant:** Standard (minor release — new language features + fixes).
**Release candidate wheel:** `dist/nodus_lang-4.1.0-py3-none-any.whl`
**Scope:** `match` expression (#308), `break`/`continue` (#309), `agent_call_async` /
`agent.call_async` (#294), workflow/goal build-time cycle rejection (#323),
resume no longer re-executes or clobbers the caller (#322, #328), async fan-out
shares one HTTP client (#295), doc-vs-code gate runs in CI (#302).

This is a backward-compatible minor release (no bytecode break, BYTECODE_VERSION
unchanged). Validation runs the full standard sweep against the built wheel.

---

## Build

```
python -m build
# -> nodus_lang-4.1.0-py3-none-any.whl, nodus_lang-4.1.0.tar.gz
python -m twine check dist/*
# -> PASSED (both sdist and wheel)
```

Installed into a clean venv:

```
python -m venv .venv-validation
.venv-validation/Scripts/pip install dist/nodus_lang-4.1.0-py3-none-any.whl
.venv-validation/Scripts/nodus --version   # -> Nodus 4.1.0
```

---

## Gate 10 — Standard eval scripts (against the built wheel)

All three standard eval scripts run against the **installed wheel** (not dev source):

```
.venv-validation/Scripts/nodus run tests/eval/quirk_probe.nd
# -> ALL QUIRKS CONFIRMED

.venv-validation/Scripts/nodus run tests/eval/language_exerciser.nd
# -> ALL EXERCISES PASSED

.venv-validation/Scripts/nodus run tests/eval/framework_capabilities.nd
# -> ALL FRAMEWORK PROBES PASSED
```

Result: **PASS** — no regressions in language quirks, core exercises, or
framework-capability probes on the packaged artifact.

---

## Pre-publish gates (dev source)

- **Full test suite:** `pytest tests/ -q` → 1856 passed, 3 skipped.
- **Doc-vs-code gate:** `tools.nodus_gate.cli --all` → exit 0
  (Static 132/132, Runtime 229/229, Closed-issues 0/0, Contracts 6/6).
- **Version sync:** `src/nodus/support/version.py` and `pyproject.toml` both `4.1.0`;
  `from nodus.support.version import __version__` → `4.1.0`.

---

## Verdict

**Cleared for publish.** All Gate 10 wheel checks pass, the full suite is green,
and the doc-vs-code gate is clean. No CRITICAL findings.
