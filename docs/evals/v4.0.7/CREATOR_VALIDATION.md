# v4.0.7 — Pre-publish Creator Validation

**Date:** 2026-06-21
**Variant:** Abbreviated (targeted bug-fix patch) — scoped to the patched code path per `PLAYBOOK_PATCH_MINOR.md` Stage 3.
**Release candidate wheel:** `dist/nodus_lang-4.0.7-py3-none-any.whl`
**Scope:** REHYDRATE-001 (#285) — cross-process workflow resume re-binds module imports.

This release contains a single behavioral fix. Per the abbreviated variant, the
full quirk/category sweep is skipped; validation targets the patched path
(workflow graph rebuild / import re-binding in `VM._rebuild_workflow_graph`) and
the adjacent in-process resume fast path.

---

## Build

```
python -m build
# -> nodus_lang-4.0.7-py3-none-any.whl, nodus_lang-4.0.7.tar.gz
```

Installed into a clean venv:

```
python -m venv .venv-validation
.venv-validation/Scripts/pip install dist/nodus_lang-4.0.7-py3-none-any.whl
.venv-validation/Scripts/python -m nodus --version   # -> Nodus 4.0.7
```

---

## Stage 3a — Closed-issues gate (dev source)

```
python -m tools.nodus_gate.cli --closed-issues --section 4.0.7
```

Result:

```
Scanning CHANGELOG [4.0.7] section
Found 1 issue reference(s)
  PASS #285: tests\test_nodus_workflow_framework.py
Closed-issues: PASS — 1 passed, 0 failed, 0 missing (of 1 referenced issues)
```

The regression test `test_resume_on_rebuilt_vm_rebinds_module_imports` carries
the `# closes: #285` marker the gate scans for.

> Note: the entry was promoted from `[Unreleased]` into `[4.0.7]`, so the gate
> must be run with `--section 4.0.7` (the default section is `Unreleased`).

---

## Stage 3b — Wheel smoke test (installed artifact, not dev source)

**Isolation requirement:** the repo-root `nodus.py` is a shim that force-inserts
`src/` onto `sys.path` whenever the repo root is importable. Running a validation
script from the repo root therefore silently tests **dev source**, not the wheel
— the exact gap that shipped BUG-E12 / #75 broken in v3.0.1. The validation
script is run from a directory **outside** the repo, and asserts
`"site-packages" in nodus.vm.vm.__file__` before doing anything else.

Resolution confirmed:

```
nodus pkg:  ...\.venv-validation\Lib\site-packages\nodus\__init__.py
vm module:  ...\.venv-validation\Lib\site-packages\nodus\vm\vm.py
```

Script: [`validate_rehydrate_285.py`](./validate_rehydrate_285.py). Three
adversarial programs against the patched path:

| # | Program | Targets | Result |
|---|---------|---------|--------|
| 1 | Aliased import (`std:json as json`) used in a post-wait step; live graph + VM evicted before resume → forces graph rebuild | The fix: rebuilt VM re-binds the import | PASS — `finish -> {"status": "ok"}` |
| 2 | Same shape, but graph/VM **not** evicted → in-process resume reuses the registered VM | Regression guard on the fast path | PASS — `finish -> {"ok": true}` |
| 3 | Different aliased module (`std:strings as strings`) used in a post-wait step after rebuild | Confirms the fix is not json-specific | PASS — `finish -> DONE` |

```
REHYDRATE-001 wheel validation (nodus 4.0.7)
  PASS  program_1_aliased_import_after_rebuild: finish -> {"status": "ok"}
  PASS  program_2_inprocess_fast_path: finish -> {"ok": true}
  PASS  program_3_different_module_after_rebuild: finish -> DONE
ALL WHEEL VALIDATION PROGRAMS PASSED
```

Before the fix, programs 1 and 3 fail with `Undefined variable: <name>` recorded
in the run's `failed`/`error` fields while the outer resume still reports
`ok: True` (the silent no-op this release fixes).

---

## Disposition

- No new failures found. The fix is present in the wheel artifact, not just dev source.
- No issues to file from this validation.

## Exit condition

- [x] Closure verification (3a) passes against dev source.
- [x] Closed-issue regression test passes against the installed wheel (3b).
- [x] ≥3 adversarial programs executed (abbreviated-variant minimum).
- [x] Full test suite green prior to this stage (workflow framework + module loader: 40 passed; workflow/goal/resume/import sweep: 253 passed).

**Verdict: PASS — clear to publish v4.0.7.**
