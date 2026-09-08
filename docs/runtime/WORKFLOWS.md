# Workflow Runtime Internals

**Last reviewed:** 2026-09-07, against 5.12.0

Workflows and goals are orchestration primitives that compile to task graphs.
This document covers the **runtime layer**: how a workflow becomes bytecode, and
what a run leaves on disk.

> **The language surface is documented elsewhere and is deliberately not
> repeated here.** `step` / `state` / `checkpoint` syntax, `each` fan-out, `when`
> guards, `compensates`, barrier and merge cells, and the `goal … over …`
> stopping condition all live in
> [`docs/guide/workflows-and-tasks.md`](../guide/workflows-and-tasks.md) and
> [`LANGUAGE_SPEC.md`](../language/LANGUAGE_SPEC.md). The option vocabularies are
> `STEP_OPTION_KEYS` and `STATE_OPTION_KEYS` in
> `src/nodus/orchestration/workflow_lowering.py`; the CLI surface is
> `nodus workflow --help`.
>
> An earlier revision of this file re-listed all four, and every list had
> drifted: 7 of the 10 step options, 3 of the 12 `workflow` subcommands, and none
> of the five constructs added since v5.0.0. Enumerating them here a second time
> is what produced that.

## Compilation pipeline

A `WorkflowDef` or `GoalDef` never reaches the bytecode compiler as itself. It is
lowered to a plain map literal first:

```
WorkflowDef / GoalDef AST node
    ↓  compiler.compile_stmt
    ↓  lower_workflow_ast / lower_goal_ast   (orchestration/workflow_lowering.py)
    ↓  _StateRewriter                        (same module)
    ↓  MapLit AST node
    ↓  bytecode compiler (compile_expr)
    ↓  bytecode instructions
```

`_StateRewriter` walks each step body and rewrites every reference to a `state`
variable into an index expression on a hidden `__state` map. This happens
entirely at compile time, so the bytecode emitted for a step function uses
ordinary map-index opcodes — **the VM has no special awareness of workflow
state.**

The resulting `MapLit` encodes the whole workflow structure — step functions,
dependency lists, state initialisers — as a plain map that the VM evaluates into
a workflow record at run time.

> Because the rewrite is syntactic, `_StateRewriter` has to know every assignment
> form the language has, and that is where this design has bitten. It knew `=`,
> `x[i] =` and `x.f =` but not `+=`, so a folded cell read `nil`
> ([#518](https://github.com/Masterplanner25/Nodus/issues/518)). Adding an
> assignment form to the language means teaching it here too.

## Persisted state — two files per run

A run writes under `.nodus/graphs/`, resolved relative to the working directory
unless `NODUS_RUN_STATE_ROOT` is set.

| File | Written | Holds |
|---|---|---|
| `<graph_id>.json` | continuously | the graph snapshot |
| `<graph_id>.checkpoint.json` | on each `checkpoint` | the resume point |

Both writes are atomic: a uuid-suffixed temp file is written and `fsync`ed, then
`os.replace`d over the target, then the containing directory is `fsync`ed. A
killed process leaves a readable previous version rather than a truncated file.

### The graph snapshot

Top-level keys, read off a run of the example below:

```
checkpoints          engine_checkpoints   execution_kind    graph_id
metadata             pending              results           scheduler_queue
status               task_outputs         tasks             updated_at
workflow_name        workflow_state
```

Each entry under `tasks` carries `step_name`, `state`, `attempts`, `result`,
`started_at` and `finished_at`.

> **Do not derive an ordering from `started_at` / `finished_at`.** They are host
> clock readings and the clock ticks in ~15.6 ms steps on Windows, so a task's
> own two stamps are routinely equal and so are two tasks in a strict causal
> chain. The ordering does exist — tasks settle one at a time on one scheduler —
> it is simply not what these fields record. A duration measured across a fast
> step is `0.0` and means nothing.

### The checkpoint file

The same shape minus the run-level fields, plus `label` and `timestamp`:

```
checkpoints          engine_checkpoints   graph_id          label
metadata             pending              results           scheduler_queue
status               task_outputs         tasks             timestamp
workflow_state
```

`engine_checkpoints` is the field that makes resume correct for folded state
([#486](https://github.com/Masterplanner25/Nodus/issues/486)): each entry records
the workflow state *as of* that checkpoint, so a resume re-derives folded cells
instead of adding pre-checkpoint contributions again on every pass.

> **A `checkpoint` is a re-entry label for its whole step, not a position marker
> within it.** A resume re-enters the step from the top, so effects before the
> checkpoint run again. Split the step at the checkpoint to skip completed work.

Reproduce both files with:

```nd
workflow build {
    state version = "0.1.0"
    step compile {
        checkpoint "after-compile"
        return "compiled"
    }
    step package after compile with { retries: 2 } {
        return "packaged"
    }
}
print(run_workflow(build)["steps"]["package"])
```

## Resume

Resuming loads the latest snapshot, rehydrates task outputs and workflow state,
and skips already-completed steps before scheduling the remainder. Without an
explicit label the loader prefers the latest checkpoint file, applies its pending
queue, and continues from there; `--checkpoint <label>` rolls downstream work
back to that label first.

> **A run is both files, and removing one without the other breaks it.** Deleting
> the run records while the graph state survives leaves a waiting run
> unresumable — the resume says so now rather than reporting "not found"
> ([#476](https://github.com/Masterplanner25/Nodus/issues/476)). Use
> `nodus workflow cleanup`, which removes both halves.

## Cleanup

`nodus workflow cleanup` removes terminal runs and their snapshots; retention
defaults to 30 days and `NODUS_WORKFLOW_RETENTION_SECONDS` overrides it (`0`
disables retention, leaving only `--force`). `running` and `failed` records
survive `--force` by design.

There is no dry run. `--dry-run` belongs to `migrate-store` and is **refused**
here — through v5.11.0 it was accepted, ignored, and the deletion proceeded while
the JSON output read like a preview
([#791](https://github.com/Masterplanner25/Nodus/issues/791)). To preview, count
first and compare after.

## Related

- [`TASK_GRAPHS.md`](TASK_GRAPHS.md) — the task graph runtime underneath
- [`EXECUTION_INVARIANTS.md`](EXECUTION_INVARIANTS.md) — guarantees the runtime upholds
- `docs/design/workflow-framework/00-framework-plan.md` — the framework layer
  (`nodus_lang_workflow`), its 7-state lifecycle and store backends
