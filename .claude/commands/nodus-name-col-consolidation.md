Full Option C consolidation for NAME-COL-001: make standalone nodus-schema and
nodus-workflow the canonical packages, remove in-tree nodus_lang_schema and
nodus_lang_workflow, and have nodus-lang depend on them.

**Context:** In-tree `nodus_lang_schema` and `nodus_lang_workflow` were renamed
from `nodus_schema` / `nodus_workflow` to avoid install-order collisions before
the v4.0.0 launch (NAME-COL-001 Option A, completed 2026-05-31). This skill
implements the full Option C consolidation as a post-launch migration.

GitHub: #104 (NAME-COL-001)

Arguments: $ARGUMENTS
(Omit to run all steps. Pass "audit" to read current state without changes.)

---

## Pre-flight

1. nodus-lang v4.0.0 must be published to PyPI.
2. The standalone `nodus-schema` and `nodus-workflow` packages must be published
   to PyPI (they're in the publish sequence; check that they're live).
3. Run current tests to confirm baseline:
   ```powershell
   cd "C:\dev\Coding Language"
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no
   ```

---

## Step 1 — Audit and reconcile functionality gaps

Before removing the in-tree modules, confirm that the standalone packages
provide everything the in-tree versions provide.

**nodus_lang_schema vs standalone nodus-schema:**
- In-tree (`src/nodus_lang_schema/`): `SyscallSpec`, `parse_syscall_name`,
  `validate_input`, `validate_output`, `HandlerContract`, `VALID_EFFECTS`,
  extension ABI models
- Standalone (`C:\dev\nodus-schema`): `SchemaRegistry`, `validate_payload`,
  `parse_versioned_name`, `resolve_version`, `SchemaEntry`

These are different APIs. The standalone does NOT contain the in-tree ABI
contracts. Resolution options:
  A. Merge ABI contracts into standalone (add SyscallSpec etc. to nodus-schema)
  B. Keep ABI contracts in nodus-lang as internal-only (not nodus-schema) and
     only move the general validation parts
  C. Accept that nodus-schema standalone stays separate from ABI contracts

For v1.0 consolidation, **Option B is recommended**: the ABI contracts are
nodus-lang-specific and shouldn't pollute a general validation library.
Move the ABI contracts to `src/nodus/runtime/schema.py` (internal to nodus-lang)
and remove `src/nodus_lang_schema/` entirely. The general validation functions
the standalone provides are different and stay at `nodus-schema`.

**nodus_lang_workflow vs standalone nodus-workflow:**
- In-tree: full orchestration framework (7-state lifecycle, HTTP/CLI, SQLite store)
- Standalone: lightweight workflow primitives (FlowDefinition, SchedulerEngine)

Resolution: The in-tree version IS the definitive nodus-workflow. The standalone
is a subset. **Replace the standalone with the in-tree version** — publish what's
in `src/nodus_lang_workflow/` as `nodus-workflow` on PyPI, and add it as a
dependency of nodus-lang.

---

## Step 2 — Move ABI contracts to nodus-lang internal

Create `src/nodus/runtime/abi_schema.py` containing the content of:
- `src/nodus_lang_schema/syscalls.py`
- `src/nodus_lang_schema/validation.py`
- `src/nodus_lang_schema/__init__.py` exports

Update internal callers:
- `src/nodus/services/syscall_runtime.py`: `from nodus.runtime.abi_schema import ...`

After updating, delete `src/nodus_lang_schema/` and its tests.

---

## Step 3 — Extract nodus_lang_workflow as a standalone package

The in-tree `src/nodus_lang_workflow/` should become the published `nodus-workflow`:

1. Copy `src/nodus_lang_workflow/` → `C:\dev\nodus-workflow\src\nodus_workflow\`
   (renaming the module from `nodus_lang_workflow` back to `nodus_workflow`)
2. Update `C:\dev\nodus-workflow\pyproject.toml` — this is now the full framework
3. Add `nodus-workflow>=4.0.0` to nodus-lang's `pyproject.toml` dependencies
4. Update internal callers to use `from nodus_workflow.runner import ...`
   (back to the original name, now from the standalone package)
5. Delete `src/nodus_lang_workflow/`

---

## Step 4 — Update all references

After Steps 2-3:
- `src/nodus/cli/cli.py`: `from nodus_lang_workflow.runner` → `from nodus_workflow.runner`
- `src/nodus/services/server.py`: same
- `src/nodus/vm/vm.py`: same
- `src/nodus/tooling/runner.py`: same
- All test files that import from `nodus_lang_workflow` or `nodus_lang_schema`
- CLAUDE.md: update the "Dual-implementation names" section to show the consolidation
- `docs/governance/TECH_DEBT.md`: close NAME-COL-001

---

## Step 5 — Publish and verify

1. Publish `nodus-workflow` (from in-tree content) to PyPI
2. Add `nodus-workflow>=4.x.y` to nodus-lang dependencies
3. Build and install nodus-lang in a clean venv
4. Verify: `from nodus_workflow.runner import get_default_workflow_runner` works
5. Verify: `pip install nodus-lang nodus-workflow` doesn't collide
6. Verify: `pip install nodus-lang nodus-schema` doesn't collide

---

## Exit criteria

- `import nodus_schema` unambiguously refers to the standalone general validation package
- `import nodus_workflow` unambiguously refers to the full orchestration framework
- No in-tree `nodus_lang_schema` or `nodus_lang_workflow` directories remain
- nodus-lang's `pyproject.toml` lists `nodus-workflow` as a dependency
- `#104 NAME-COL-001` closed

## Dev environment

```powershell
cd "C:\dev\Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no
```
