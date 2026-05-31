Graduate the Goal DSL from Experimental to Mostly Stable.

Phase C — depends on Phase B (nodus-scheduler-freeze) being complete.
Coroutines and channels must be Mostly Stable before goals can graduate
because goal execution uses the same scheduler and coroutine machinery.

GitHub issues: #108 (WorkflowFrameworkRunner registration), #109 (path unification)

Arguments: $ARGUMENTS
(Omit to run all steps. Pass "check" to read current state without making changes.)

---

## Pre-flight

1. Confirm Phase B (nodus-scheduler-freeze) is complete:
   - SCHED-001 (#94) closed
   - SCHED-002 (#95) closed
   - CHAN-001 (#107) closed
   If any are open, stop and complete Phase B first.

2. Run goal-related tests to establish baseline:
   ```powershell
   cd "C:\dev\Coding Language"
   PYTHONPATH="C:/dev/Coding Language/src" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest `
     tests/test_goal_dsl.py -v
   ```

3. Read `src/nodus/vm/vm.py` — `builtin_run_goal` and `builtin_resume_goal`.
   Understand the current direct-path flow.

4. Read `src/nodus_workflow/runner.py` — `WorkflowFrameworkRunner.start_workflow()`
   to understand the registration pattern that `run_goal` needs to adopt.

---

## Step 1 — Register run_goal with WorkflowFrameworkRunner (#108)

**Root cause:** `run_goal()` calls `run_task_graph()` directly without registering
the run in the `WorkflowFrameworkRunner` store. Goals are invisible to the
framework's claim/resume/dead-letter machinery.

**Fix in `src/nodus/vm/vm.py` — `builtin_run_goal`:**

The fix mirrors how `WorkflowFrameworkRunner.start_workflow()` works:
before calling `run_task_graph()`, register the run in the default runner's store.

```python
def builtin_run_goal(self, goal):
    if not is_goal_value(goal):
        self.runtime_error("type", "run_goal(goal) expects a goal")
    graph = workflow_to_graph(self, goal, init_state=True)
    # Register with framework runner so resume/dead-letter works
    from nodus_workflow.runner import get_default_workflow_runner
    runner = get_default_workflow_runner()
    runner.register_run(graph.graph_id, execution_kind="goal")  # or equivalent
    return run_task_graph(self, graph)
```

Check what `runner.register_run` or equivalent looks like in
`WorkflowFrameworkRunner` — it may need a new method or use an existing
registration path.

After this fix, `resume_goal()` CAN delegate to `builtin_resume_workflow()` for
the framework path. The 'already claimed' error (#108) was caused by the missing
registration, not by the delegation itself.

---

## Step 2 — Unify workflow/goal execution paths (#109)

**Root cause:** Goals and workflows use diverging paths. As the
`WorkflowFrameworkRunner` gains capabilities, goals silently miss them.

**Fix:** After Step 1, goals run through the framework runner.
`builtin_run_goal` becomes a thin wrapper that sets `execution_kind="goal"`
and delegates to the shared execution path:

```python
def builtin_run_goal(self, goal):
    if not is_goal_value(goal):
        self.runtime_error("type", "run_goal(goal) expects a goal")
    graph = workflow_to_graph(self, goal, init_state=True)
    # Route through framework runner with goal kind
    return get_default_workflow_runner().start_run(
        self, graph, execution_kind="goal"
    )
```

The `execution_kind` discriminator is already stored in graph metadata and
handled by `workflow_result_payload()` in `task_graph.py`. The primary change
is the entry point.

**Verify:** After unification, `resume_goal()` with checkpoint should work
identically to `resume_workflow()` with checkpoint, just with `"goal"` in the
result payload.

---

## Step 3 — Goal-specific edge case tests

Add to `tests/test_goal_dsl.py` or a new `tests/test_goal_graduation.py`:

1. **Goal registered in framework store** — after `run_goal(g)`, verify the
   `WorkflowFrameworkRunner` store has a record for `result["graph_id"]`.

2. **resume_goal via framework** — run a goal to a checkpoint, clear the graph
   registry, resume via the framework path; verify result is correct.

3. **Goal dead-lettering** — a goal with a failing step should create a
   dead-letter entry in the framework store (not silently fail).

4. **Goal with retry** — a step configured with retry policy should retry
   correctly through the framework runner.

5. **Multi-step goal state** — goal with 3 steps and shared state; verify
   each step sees the state written by the previous step.

---

## Graduation criteria

After Steps 1–3 complete, the Goal DSL qualifies for **Mostly Stable**:
- ✅ `run_goal`, `resume_goal`, `plan_goal` API frozen
- ✅ WorkflowFrameworkRunner integration (claim/resume/dead-letter)
- ✅ Path unified with workflow DSL
- ✅ Edge cases tested

Update `docs/governance/LANGUAGE_STABILITY_INDEX.md`:
- `workflow`, `goal`, `step`: Experimental → Mostly Stable (goal section)

Note: The full Workflow DSL graduation (Phase D) may happen separately — the Goal
DSL can graduate independently because it is the simpler surface.

## Dev environment

```powershell
cd "C:\dev\Coding Language"
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest `
  tests/test_goal_dsl.py -v

PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q --tb=no
```

## Commit format

```powershell
git commit -m @'
feat(goal): register run_goal with WorkflowFrameworkRunner — Phase C graduation

Closes #108 and #109.
Phase C of experimental surface graduation (depends on Phase B).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
'@
```
