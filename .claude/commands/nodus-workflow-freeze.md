Graduate the Workflow DSL from Experimental to Mostly Stable.

Phase D — depends on Phase C (nodus-goal-freeze) being complete.
Goals must be graduated and the path unification must be in place before
the full Workflow DSL can follow.

Also requires NAME-COL-001 (#104) to be decided (rename standalone packages
or move in-tree modules) — this is a design decision, not just an implementation.

GitHub issues: #102 (WF-SCAN-001), #104 (NAME-COL-001), #110 (checkpoint API)

Arguments: $ARGUMENTS
(Omit to run all steps. Pass "check" to read current state without making changes.)

---

## Pre-flight

1. Confirm Phase C (nodus-goal-freeze) is complete:
   - #108 (WorkflowFrameworkRunner registration) closed
   - #109 (path unification) closed
   If open, complete Phase C first.

2. Confirm NAME-COL-001 (#104) has a decision:
   - Option A: rename standalone PyPI packages (`nodus-schema-sdk`, `nodus-workflow-sdk`)
   - Option B: move in-tree modules under `nodus.nodus_schema` / `nodus.nodus_workflow`
   - Option C: consolidate (standalone replaces in-tree at publish time)
   This is a design decision — stop and ask the user if it has not been made.

3. Run workflow-related tests to establish baseline:
   ```powershell
   cd "C:\dev\Coding Language"
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest `
     tests/test_workflow_dsl.py tests/test_nodus_workflow_framework.py -v
   ```

---

## Step 1 — WF-SCAN-001: fix LocalWorkflowStore scan (#102)

**File:** `src/nodus_workflow/store.py`

`LocalWorkflowStore._list_runs()` scans all `*.json` files in the runs directory
on every sweeper iteration. At 670+ accumulated test artifacts, this takes >2s,
breaking the `test_worker_death_detected_by_sweeper` 500ms deadline.

**Two-part fix:**

Part A — cap the scan to active statuses only (quick win):
```python
def _list_runs(self) -> list[WorkflowRunRecord]:
    # Only load non-terminal runs — completed/failed/dead-lettered
    # don't need to be swept
    results = []
    for path in Path(self._runs_dir).glob("*.json"):
        record = self._load_run_unlocked_path(path)
        if record and record.status not in TERMINAL_STATUSES:
            results.append(record)
    return results
```

Part B — make `SQLiteWorkflowStore` the default in tests:
In any test that creates a `LocalWorkflowStore` or uses the default runner,
switch to an in-memory SQLite store:
```python
from nodus_workflow.store import SQLiteWorkflowStore
store = SQLiteWorkflowStore("sqlite:///:memory:")
runner = WorkflowFrameworkRunner(store)
```

**Tests:** `test_worker_death_detected_by_sweeper` must pass within 500ms.

---

## Step 2 — Implement NAME-COL-001 decision (#104)

Implement whichever option was decided in pre-flight:

**Option A — rename standalone packages:**
Update `pyproject.toml` in `C:\dev\nodus-schema` and `C:\dev\nodus-workflow` to
use new names. Update all references in CLAUDE.md, CHANGELOG.md, pyproject.toml
`dependencies` lists.

**Option B — move in-tree modules under `nodus.*`:**
Rename `src/nodus_schema` → `src/nodus/nodus_schema` and
`src/nodus_workflow` → `src/nodus/nodus_workflow`. Update all imports.
This is a larger refactor — check with `grep -r "nodus_schema\|nodus_workflow" src/`.

**Option C — consolidate:**
Remove the in-tree modules; add the standalone packages as dependencies of
`nodus-lang`. Requires the standalone packages to be on PyPI first.

---

## Step 3 — Checkpoint API completeness (#110)

**Part A — Document the checkpoint semantics:**

Add a `## Checkpoint API` section to `docs/runtime/WORKFLOWS.md`:
1. The `checkpoints` list (user-visible public checkpoints, labeled with `checkpoint "name"`)
2. The `engine_checkpoints` list (internal snapshots, one per step completion)
3. Resume behavior: search `engine_checkpoints` in reverse for the label, fall back to `checkpoints`
4. Rollback scope: what task states are reset, what state is preserved
5. Duplicate labels: the most recent checkpoint with the given label is used (reverse search)

**Part B — Dedicated checkpoint tests:**

Create `tests/test_workflow_checkpoints.py`:

1. **Checkpoint creation** — after a step completes, verify the checkpoint entry
   exists in `engine_checkpoints` with correct state snapshot.

2. **Resume from named checkpoint** — run workflow to checkpoint "mid", clear
   graph registry, resume from "mid"; verify step results are correct.

3. **Duplicate checkpoint label** — workflow with two steps both writing checkpoint
   "done"; resume from "done" should use the most recent one.

4. **Checkpoint with state mutation** — verify that state written in step A is
   visible when resuming from A's checkpoint and running step B.

5. **Resume without checkpoint** — resume from no-checkpoint path (state only)
   still runs correctly.

---

## Step 4 — Workflow graduation test sweep

Review `tests/test_workflow_dsl.py` and `tests/test_nodus_workflow_framework.py`
for any edge cases the checkpoint work exposed. Add tests for:

- Workflow with 5+ steps and multiple checkpoints
- Workflow retry after failure (if retry_on_failure is supported)
- Workflow dead-letter creation on max retries exceeded
- `resume_workflow` via HTTP endpoint returns correct result shape

---

## Graduation criteria

After all steps complete, the Workflow DSL qualifies for **Mostly Stable**:
- ✅ WorkflowFrameworkRunner path (unified with goal path from Phase C)
- ✅ WF-SCAN-001 fixed (no performance cliff in store)
- ✅ NAME-COL-001 resolved (no namespace collision risk)
- ✅ Checkpoint semantics documented and tested
- ✅ `workflow`, `step`, `state`, `checkpoint`, `run_workflow`, `resume_workflow` API frozen

Update `docs/governance/LANGUAGE_STABILITY_INDEX.md`:
- Workflow DSL tier: Experimental → Mostly Stable

The path to **Stable** (not just Mostly Stable) requires real production usage
to surface corners that tests don't find — this can only be earned post-publish.

## Dev environment

```powershell
cd "C:\dev\Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest `
  tests/test_workflow_dsl.py tests/test_nodus_workflow_framework.py `
  tests/test_workflow_checkpoints.py -v

PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no
```

## Commit format

```powershell
git commit -m @'
feat(workflow): <description> — Phase D graduation

Closes #102 / #104 / #110 as applicable.
Phase D of experimental surface graduation (depends on Phase C).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```
