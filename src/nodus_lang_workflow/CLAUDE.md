# nodus-workflow (in-tree framework)

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

- **Status:** Near-runtime-complete. Core semantics complete; production hardening
  and packaging documented in `docs/design/workflow-framework/00-framework-plan.md`
  — moved there from a top-level `plans/` directory that held it alone, and given
  a `Last reviewed:` header. It was written 2026-05-30 and pointed at
  `src/nodus_workflow` for three months, a path the NAME-COL-001 rename removed
  the day after it was written. Its remaining-work items are still open; two have
  moved underneath it (#174 answered part of the SQLite question, #380 part of
  the scan-cost one) and the header says which.

**Operational gotcha — local store scan performance:**
`LocalWorkflowStore.list_runs()` reads every `.nodus/workflow_framework/runs/*.json`
on every sweep, so **cost is linear in the number of accumulated runs**. #380 made it
roughly 4× cheaper — the cost was never parsing, it was `nt.mkdir` (the store re-created
its own directory once per record) and an `os.path.exists` before every `open` — but
linear it remains.

**Do not quote a file-count threshold here.** Two earlier revisions did and both were
wrong in the same direction; the numbers are cheap to regenerate and have moved twice.
Measure if you need one. The bound itself is still open in #380.

The default store root is **CWD-relative**, so anything running a workflow from
the repo root writes there. As of #380 the suite and the doc gate clean up after
themselves (`tests/conftest.py`, `tools/nodus_gate/runtime_phase.py`) — check this
before blaming a flake on timing:

```powershell
ls .nodus/workflow_framework/runs | Measure-Object -Line
ls .nodus/graphs | Measure-Object -Line
```

**Both halves are covered as of #585.** They were not: the gate redirected
`NODUS_WORKFLOW_STORE_ROOT`, which moved the run records only, so one
`nodus_gate --runtime` run added **0** run records and **67** graph-state files, every
time. `_GRAPH_ROOT` was a hardcoded module constant and had no override at all.

`NODUS_RUN_STATE_ROOT` now relocates **both halves together**. The gate does **not**
set it yet, so a `--runtime` run still leaves ~67 graph-state files here: pointing it at
the new variable works locally (measured: 5,799 graphs before and after a full runtime
phase) and reproducibly turns
`test_agent_handler_timeout.py::test_a_step_timeout_bounds_a_blocking_handler` red on CI
— 6/6 with the change, 0/9 without, across five bisect branches. **#596** carries the
evidence; do not re-apply that two-line change without reading it.
`NODUS_WORKFLOW_STORE_ROOT` still works and still moves the records only; that is the
half-relocated state #585 is about, so prefer the former. There is deliberately **no**
graphs-only variable: a second knob would re-enable exactly what this fixed.

`conftest.py` still cleans up rather than redirecting, because several tests chdir into
a project directory and assert the default runner wrote under *that* root (26 failures
when redirection was tried) — but it now sweeps both halves off one list rather than
growing a second hand-maintained sweep.

Two things not moved by that variable, on purpose. `.nodus/{cache,modules,deps.json}`
are **project**-scoped, resolved against `find_project_root()`, and have nothing to do
with which run wrote them. And historic accumulation is not cleared by the fix —
`nodus workflow cleanup --force` does that (the 30-day default retention will not touch
anything from this week).

**The Floor follows the roots now, and did not before.** `DEFAULT_FLOOR` forbids a
program writing into the runtime's own state by matching a literal `.nodus` path
segment — so the *supported* way to relocate the store also moved it outside the
Floor's reach. Demonstrated, not inferred: with `NODUS_WORKFLOW_STORE_ROOT` set, a
guest's `fs.write("../relocated/pwned.txt", "x")` landed in the live run store while
the identical write to the default location was denied. Any new state directory must go
through `nodus/runtime/state_paths.py`, or it is unprotected.

**There is still no dry run of this command**, but asking for one is no longer
destructive. `nodus workflow cleanup --dry-run --force` **deleted** through
5.11.0 (#791): `--dry-run` belongs to `workflow migrate-store`, no `nodus`
command rejected an unknown flag, so it was dropped in silence and the deletion
proceeded while the JSON output read exactly like a preview. Reproduced twice
then — 4 graphs and 4 run records, `(4, 4)` "would remove", and they were gone.

Fixed on `main`: an undeclared flag is refused before any command body runs, so
that exact line now exits 1 and touches nothing (re-verified against a
throwaway project). **Against 5.11.0 or earlier, the old behaviour is live** —
and the fix does not give `cleanup` a preview. To see what it would take, count
first (`ls .nodus/graphs | wc -l`) and compare after.

Measured at the 5.11.0 cut, clearing a checkout: **56M → 7.0M**, 11,851 graph
files → 5. What it keeps is deliberate — `running` and `failed` records survive
`--force`, so the 273 that remained are not a failure of the command.

`rm -rf .nodus/workflow_framework/runs` is safe **in this repo's root** (test
artifacts only) — but it is not a general cleanup: a run is split across that
directory and `.nodus/graphs/`, and deleting only the records makes any live
waiting run unresumable while its state survives (#476; the resume now says so
instead of "not found"). Use `nodus workflow cleanup`, which removes both
halves.
`NODUS_RUN_STATE_ROOT` relocates both halves of a run's state for a process
(`NODUS_WORKFLOW_STORE_ROOT` moves the records alone). Bounding
the store's cost — pruning by count, or an index instead of a full rescan —
is still open in #380.

**Circular import (CIRC-001, #103) — FIXED** 2026-06-01. `nodus.vm.vm` no longer imports
`get_default_workflow_runner` at module level; the imports are lazy, inside
`builtin_run_workflow` / `builtin_resume_workflow` (`vm.py:1077`, `:1139`, `:1154`).
Importing `nodus_lang_workflow` before `nodus` in a fresh process is safe. Do not
"fix" this again by hoisting the import.
