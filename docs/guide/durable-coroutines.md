# Durable Coroutines

A durable coroutine is a coroutine whose progress survives the process. You
start it with `durable_spawn`, mark points in it with `checkpoint "label"`, and
if the process dies, the next run picks the work up **at the last checkpoint**:
what came before is not done again.

> **Experimental.** New in the release after 5.15.1. The behaviour below is
> tested, but the API may still change. Design and reasoning:
> [`docs/design/v5/08-durable-coroutines.md`](../design/v5/08-durable-coroutines.md)
> and its [stage 4 addendum](../design/v5/08a-durable-coroutines-stage4.md).

---

## 1. Which one do you need?

Nodus has three ways to run concurrent work. They differ in what survives a
crash:

| | `spawn(fn)` | `durable_spawn(key, fn, args)` | a `workflow` step |
|---|---|---|---|
| Survives the process dying | no | yes, from the last checkpoint | yes, from the start of the step |
| `checkpoint "label"` means | an error | *resume from here* | *this step got this far* (the step re-runs from its top) |
| Unit of recovery | none | a position in one function | a named step in a graph |
| Needs a store | no | yes, SQLite (§2) | yes |

Use **`spawn`** for concurrency inside one run: fan-out, overlapping I/O,
anything that ends when the program does. Use a **workflow** when the work
has named stages with dependencies between them. Use a **durable coroutine**
when one piece of work runs long enough that losing it to a crash costs you,
and the natural shape is a function with a few points worth saving: "fetched",
"uploaded", "notified".

**The contract is at-least-once between checkpoints.** Everything before the
last checkpoint happens exactly once. Everything after it may happen again
after a crash. Put a checkpoint after each step you must not repeat, and make
the code between checkpoints safe to run twice.

---

## 2. Setting up the store

A durable coroutine is a run record in the workflow store, and it needs a
store whose claims are exclusive across processes. Otherwise a restarted
program and a host that resumes runs could both pick up the same run. Today
that store is SQLite:

```
$ export NODUS_WORKFLOW_STORE_BACKEND=sqlite
```

SQLite becomes the default store at 6.0.0, and from then this step is not
needed. Without it, `durable_spawn` refuses to start and says how to fix it:

```
$ nodus run --time-limit 60 ingest.nd
Runtime error at /abs/path/ingest.nd:13:14: durable_spawn needs a workflow store whose claims are exclusive across processes, so that two processes cannot both resume the same run. LocalWorkflowStore is not: its claims are exclusive only within one process. Set NODUS_WORKFLOW_STORE_BACKEND=sqlite (and move existing runs with `nodus workflow migrate-store --to sqlite`).
Stack trace:
  at <main> (/abs/path/ingest.nd:13:14)
```

If you already have workflow runs in the JSON store, move them with `nodus
workflow migrate-store --to sqlite` before switching.

---

## 3. A first durable job

```nd-no-run
// ingest.nd
fn ingest(batch) {
    print("fetching \(batch)")
    sleep(500i)
    checkpoint "fetched"
    print("uploading \(batch)")
    sleep(3000i)
    checkpoint "uploaded"
    print("done \(batch)")
    return batch
}

let run_id = durable_spawn("ingest-batch-7", ingest, ["batch-7"])
run_loop()
```

`durable_spawn` takes three things:

- **a key**, which names the run: `"ingest-batch-7"`. Calling `durable_spawn`
  with the same key again is how a restarted program finds its unfinished work
  (§3.2).
- **the function** to run, which must be a named, top-level function (§4).
- **its arguments**, as a list.

It returns the run's id. Each `checkpoint` is written to the store *before*
the function continues, so no work after a checkpoint starts until that
checkpoint is saved.

### 3.1 The process dies

Run it and kill the process during the upload, after `fetched` was reached
and before `uploaded`:

```
$ nodus run --time-limit 60 ingest.nd &
$ sleep 4; kill -9 $!
fetching batch-7
uploading batch-7
```

It printed both lines and died before `done`. The store shows where it got to.
An excerpt from `nodus workflow runs --execution-kind coroutine`:

```
"workflow_name": "ingest", "execution_kind": "coroutine", "status": "running", "current_checkpoint": "fetched", ...
"metadata": {"durable_key": "ingest-batch-7", "entry": "ingest", "args": {"values": ["batch-7"], "heap": []}, ...
```

### 3.2 Running it again

Run the same program again straight away:

```
$ nodus run --time-limit 60 ingest.nd
durable_spawn: run 'ingest-batch-7' is held by another process (nodus:24384:222b071b3d0), so it is not started here; its claim expires in 28.3s if that process has gone

```

The run is still held by the process that died. A claim cannot tell a dead
process from a busy one, so it waits for the claim to expire (30 seconds by
default) rather than risk two copies running at once. Once it has expired:

```
$ nodus run --time-limit 60 ingest.nd
uploading batch-7
done batch-7
```

It resumed at `fetched`. `fetching batch-7` did not run again. Run it once
more and nothing happens, because the run with that key is finished:

```
$ nodus run --time-limit 60 ingest.nd
$
```

A finished run never runs again under its key. Neither does a failed one:
retrying is a deliberate act, not a side effect of restarting a script, so use
a new key.

---

## 4. Rules for the function

Everything here is checked when you call `durable_spawn`, at the line that made
the mistake, not later at a checkpoint.

**A named, top-level function.** A resumed run has to find the function again by
name. An anonymous function (`fn() { ... }`), a function defined inside another
function, and a closure that captures a variable are all refused. For the
closure, the reason is that a captured variable can be shared, and a resume
could rebuild its value but not the sharing.

**Arguments that are data.** Numbers, strings, `nil`, booleans, and lists,
maps and records of them. A channel, a function or a task is refused. The
arguments are copied when the run starts, and the coroutine always sees the
stored copy, so a first run and a resumed run see the same thing.

**One key, one run.** The same key with different arguments is refused:

```
$ nodus run --time-limit 60 rekey.nd
Runtime error at /abs/path/rekey.nd:3:1: durable_spawn(key, fn, args): a run with key 'ingest-batch-7' was started as `ingest` with different arguments. A key names one run; use a new key for different work.
Stack trace:
  at <main> (/abs/path/rekey.nd:3:1)
```

### 4.1 What a checkpoint can save

At a checkpoint, the function's local variables are written down: everything
in every function call between `durable_spawn` and the checkpoint. A
checkpoint may sit in a helper the durable function calls. Shared lists and
maps stay shared, and a list that contains itself is fine.

A checkpoint inside a `for` loop over a list is saved with the loop: the list
and how far through it the loop had got. A resume carries on with the next
element:

```nd-no-run
fn upload_all(batches) {
    for batch in batches {
        print("uploading \(batch)")
        checkpoint "uploaded"
    }
    return len(batches)
}

durable_spawn("upload-for", upload_all, [["a", "b"]])
run_loop()
```

```
$ nodus run --time-limit 60 loop.nd
uploading a
uploading b
```

If the process dies after `uploading b` is printed but before its checkpoint,
the resumed run prints `uploading b` again and carries on, because `a` was
checkpointed and `b` was not. Put the checkpoint at the end of the loop body, as
here, so a finished item is never redone.

What cannot be written down is refused *at the checkpoint*, as an error the
coroutine can catch:

- a local holding a **channel, function, task or host object**;
- a local, or a `for` loop's list, that is the **same list or map as a
  module-level variable**. A resume rebuilds module state from source, so the
  two would come back as separate copies;
- a checkpoint inside a **`for` over a user-defined iterator**, a record with a
  `__next__` function. Its position is kept by its own code.

```nd-no-run
fn pages(n) {
    let st = {next: 1i}
    return {__next__: fn(r) {
        if (st.next > n) { return nil }
        st.next = st.next + 1i
        return st.next - 1i
    }}
}

fn fetch_all() {
    for page in pages(2i) {
        print("fetching page \(page)")
        checkpoint "fetched"
    }
    return 1i
}

durable_spawn("fetch-pages", fetch_all, [])
run_loop()
```

```
$ nodus run --time-limit 60 custom.nd
fetching page 1
Runtime error at /abs/path/custom.nd:13:9: checkpoint 'fetched' cannot be made durable:
not durable (1 obstacle):
  - [live_value] operand stack slot 0: a `for` loop over a user-defined iterator (`__next__`), whose position is kept by its own code and cannot be written down
A checkpoint inside a `for` over a list is fine; one over a user-defined iterator is not. Iterate a list of its items instead.
```

### 4.2 `checkpoint` outside a durable coroutine

Inside any function, `checkpoint "label"` compiles. Whether that function is
running durably is only known when it runs. If it isn't, and it isn't a
workflow step either, the checkpoint fails:

```
$ nodus run plain.nd
Runtime error at /abs/path/plain.nd:2:5: `checkpoint` ran outside a workflow step and outside a durable coroutine, so there is nothing to record it in. Start the function with `durable_spawn(key, fn, args)` to make its checkpoints persist (docs/design/v5/08a-durable-coroutines-stage4.md), or run the work as a step of a `workflow`.
Stack trace:
  at summarize (/abs/path/plain.nd:2:5)
  called from <main> (/abs/path/plain.nd:6:7)
```

At module level, outside any function, it is a syntax error, because it can
never mean anything there. `checkpoint` is not a reserved word: a variable,
field or parameter of that name works as before.

---

## 5. Deadlines across a restart

The clock that `runtime.time_ms()` and `sleep_until` use counts from when the
process started. A durable coroutine carries its clock across a restart, so a
deadline it computed before a crash still means the same moment after one:

```nd-no-run
import "std:runtime" as runtime

fn poll(feed) {
    let deadline = runtime.time_ms() + 2000.0
    checkpoint "armed"
    sleep_until(deadline)
    print("polled \(feed)")
    return 1i
}

durable_spawn("poll-feed-1", poll, ["feed-1"])
run_loop()
```

```
$ nodus run --time-limit 60 poll.nd
polled feed-1
```

If this process dies after `armed` and the run is resumed half a second later,
the resumed coroutine still wakes two seconds after it armed the deadline, in
wall time, not two seconds after the new process's clock reaches the old
number. The clock resumes from where it stood plus the real time that passed.
Each durable coroutine has its own clock, so ordinary coroutines in the same
program are not affected. `tests/test_durable_clock.py` kills a real process to
check this.

A deadline that has already passed when the run resumes fires straight away.

---

## 6. Resuming without re-running the program

Re-running the program is one way to resume a run. The other is **`nodus
workflow sweep`**, the command a cron job or an operator runs to carry on work
whose program is not going to be started again. It resumes unfinished durable
coroutines alongside the workflow work it already handles:

```
$ nodus workflow sweep
{"expired_waits": [], "released_schedules": [], "resumed_retries": [], "rehydrated_runs": [], "resumed_coroutines": [{"run_id": "co_b20f9e00402019cf0965700e15c342cf", "key": "ingest-batch-7", "workflow_name": "ingest", "ok": true, "status": "completed"}], "stdout": "uploading batch-7\ndone batch-7\n"}
```

The sweep rebuilds the program from the copy of its source stored with the
run, not from the file on disk, and the run continues *in the sweeping
process*. Its output is collected into the report's `stdout`. The same claim
decides between a sweep and a restarted program, so they never both resume one
run. `nodus serve` runs the same `sweep()` in the background.

Two things to know when a sweep rebuilds a program:

- **Put the program's work in `fn main()`.** The sweep re-runs the module's top
  level to rebind its functions. While it does, it skips `main` (whether it
  runs automatically or the program calls `main()` itself), `print`,
  `run_workflow`, `run_goal`, `durable_spawn`, and the scheduling builtins
  `spawn`, `spawn_after`, `run_loop` and `wait`. Anything else at the top level
  outside `main` that reaches outside the program, such as a file write, a
  request or a host function, runs again and is reported with its line. At
  6.0.0 it is refused (#917). Reads (`read_file`, `env_get`) are fine at the top
  level, and so is a host function registered `rebuild_safe=True`. A run stored
  before you fixed its program is resumed with `rebuild_effects="allow"`
  (migration guide §6).
- **Host functions are not in the stored source.** `nodus workflow sweep` has
  none of your registered functions. A durable coroutine that calls one is
  resumed by a host that registers it, with `runtime.sweep()` (§7.1), or by
  re-running the program.

`nodus workflow resume <run_id>` is for workflows. Given a durable coroutine's
id, it says where that run is resumed instead:

```
$ nodus workflow resume co_971bbc5577ff87195a37471d058e6b50
{"ok": false, "error": "run 'co_971bbc5577ff87195a37471d058e6b50' is a durable coroutine, not a workflow. It resumes when its program runs `durable_spawn` with its key again, or from `nodus workflow sweep`.", "graph_id": "co_971bbc5577ff87195a37471d058e6b50", "category": "not_a_graph_run"}
```

---

### 6.1 Cancelling a run

`nodus workflow cancel` stops a durable run by its key (or its run id). The run
becomes `cancelled`, which is final: neither re-running the program nor a sweep
will resume it.

```nd-no-run
fn export_all(batches) {
    let sent = 0i
    try {
        for batch in batches {
            sleep(1000i)
            sent += 1i
            checkpoint "sent"
        }
    } finally {
        print("closing export after \(sent) batches")
    }
    return sent
}

durable_spawn("export-2026-11", export_all, [["b1", "b2", "b3", "b4", "b5", "b6"]])
run_loop()
```

With that running in one terminal, from another:

```
$ nodus workflow cancel --key export-2026-11
Cancelled co_e07100b12c29fdf0b79b29b4419bc199 (was running)
A durable coroutine running in another process stops at its next checkpoint or claim renewal, after running its finally blocks.
```

The running program noticed at its next checkpoint, ran its `finally`, and
stopped:

```
durable coroutine 'export-2026-11' (run co_e07100b12c29fdf0b79b29b4419bc199) was cancelled; its finally blocks ran and it has stopped
closing export after 5 batches
```

A cancel is **cooperative**. The running process notices at its next
checkpoint, or at its next claim renewal if it has not checkpointed for a while
(every third of the claim's lifetime, so within about ten seconds by default).
Work done between the cancel and that point is not undone: here, the cancel
arrived during the fifth batch. A `catch` cannot swallow the cancellation, and a
`checkpoint` reached inside `finally` does nothing. From Python, the same thing
is `runner.cancel_run(run_id_for(key))`.

## 7. From Python

An embedding host chooses the store in code:

```python
from nodus.runtime.embedding import NodusRuntime
from nodus_lang_workflow.runner import (
    WorkflowFrameworkRunner,
    configure_default_workflow_runner,
)
from nodus_lang_workflow.store import SQLiteWorkflowStore

store = SQLiteWorkflowStore("jobs.sqlite3")
configure_default_workflow_runner(runner=WorkflowFrameworkRunner(store))

uploaded = []

runtime = NodusRuntime(timeout_ms=None)
runtime.register_function("upload", lambda rows: uploaded.append(rows))

result = runtime.run_source("""
fn job(rows) {
    checkpoint "received"
    upload(rows)
    checkpoint "uploaded"
    return len(rows)
}

print(durable_spawn("job-42", job, [[1, 2, 3]]))
run_loop()
""")

print(result["ok"], result["stdout"].strip())
print(uploaded)
print(store.get_run(result["stdout"].strip()).status)
```

```
True co_5359ae12ca11e5d628161c38de88522b
[[1, 2, 3]]
completed
```

The run id is derived from the key, so a host can find a run's record with
`nodus.runtime.durable.run_id_for(key)`. Once the run completes, the record's
`metadata["result"]` holds the return value in the store's encoding (a value
that cannot be written down is noted in `metadata["result_unrecorded"]`
instead).

### 7.1 Sweeping from your own host

A host that registers functions resumes durable runs with `runtime.sweep()`. It
sweeps on VMs built the way the runtime builds every VM: with the host's
functions, and held to the same confinement and policy as `run_source`. A run
the worker below left behind, when its process died after `received`:

```python
import os
from nodus.runtime.embedding import NodusRuntime
from nodus_lang_workflow.runner import WorkflowFrameworkRunner
from nodus_lang_workflow.store import SQLiteWorkflowStore

runner = WorkflowFrameworkRunner(SQLiteWorkflowStore("jobs.sqlite3"))
runtime = NodusRuntime(timeout_ms=None, workflow_runner=runner)
runtime.register_function("upload", lambda rows: None)
runtime.register_function("crash", lambda: os._exit(3))

runtime.run_source("""
fn job(rows) {
    checkpoint "received"
    crash()
    upload(rows)
    print("uploaded \\(len(rows)) rows")
    return len(rows)
}

durable_spawn("job-42", job, [[1, 2, 3]])
run_loop()
""")
```

is carried on by a second process:

```python
from nodus.runtime.embedding import NodusRuntime
from nodus_lang_workflow.runner import WorkflowFrameworkRunner
from nodus_lang_workflow.store import SQLiteWorkflowStore

runner = WorkflowFrameworkRunner(SQLiteWorkflowStore("jobs.sqlite3"))
runtime = NodusRuntime(timeout_ms=None, workflow_runner=runner)
uploaded = []
runtime.register_function("upload", lambda rows: uploaded.append(rows))
runtime.register_function("crash", lambda: None)

report = runtime.sweep()
print(report["resumed_coroutines"])
print(repr(report["stdout"]))
print(uploaded)
```

```
$ python worker.py
$ python sweeper.py
[{'run_id': 'co_5359ae12ca11e5d628161c38de88522b', 'key': 'job-42', 'workflow_name': 'job', 'ok': True, 'status': 'completed'}]
'uploaded 3 rows\n'
[[1, 2, 3]]
```

(`sweeper.py` ran 31 seconds after `worker.py` died, once the dead process's
claim had expired.) What the resumed program prints is collected into
`report["stdout"]`, as `run_source` returns it, and that includes anything a host
function prints while it runs. `runtime.new_vm()` gives the same VM directly,
for the other workflow calls that take a VM factory.

Do not sweep with a bare `VM([], {})`. It has none of your functions, and it is
permissive by default, so a resumed program could do what your runtime would
have refused (#908).

---

## 8. Limits

- **A restart straight after a crash waits for the claim.** Up to the store's
  claim lifetime, 30 seconds by default. `durable_spawn` tells you how long is
  left (§3.2).
- **No checkpoint inside a `for` over a user-defined iterator.** A `for` over a
  list is fine (§4.1).
- **A frame running inside an imported module's function** cannot be saved. A
  checkpoint reached through a call into another module is refused.
- **A cancel takes effect at the next checkpoint or claim renewal**, not
  instantly (§6.1).
- **A failed run is not retried under its key.** Start it again with a new key.

<!-- TESTED
Every example above was run on 2026-11-10 against main, with
NODUS_WORKFLOW_STORE_BACKEND=sqlite unless the example shows the default store,
in a scratch directory outside the repo. Output is pasted verbatim, with the
absolute directory replaced by /abs/path/ as in debugging.md. The killed run in
§3.1 was `kill -9` four seconds in. §3.2's second run followed 31 s later. §6's
sweep ran 31 s after a separate killed run.

The blocks are `nd-no-run` because the gate runs examples against the default
JSON store, which `durable_spawn` refuses (§2). The same behaviour is pinned by
tests/test_durable_spawn.py, test_durable_clock.py and test_durable_sweep.py,
each of which kills a real process.

Findings:
F1 `nodus run` held all program output until exit: a killed run showed
   nothing, and stdout appeared after stderr regardless of order. Filed as #907
   and fixed: §3.1, §4.1 and §6.1 were re-run on 2026-11-11 after the fix and
   their outputs replaced verbatim.
F2 The for-loop refusal carried no line:col (it is raised by the scheduler, not
   by an instruction). Fixed in the PR that added this guide.
F3 The "checkpoint outside a durable coroutine" error pointed at the label
   (2:16), not at `checkpoint` (2:5). Fixed in the same PR.
F4 An embedder could not build a sweep VM that carries its registered host
   functions, or its confinement. Filed as #908 and fixed: NodusRuntime.sweep()
   and new_vm(). §7.1 (worker.py then sweeper.py, 31 s apart) run 2026-11-11.
F5 A rebuild re-ran a top-level spawn + run_loop and top-level host calls.
   Older than durable coroutines (workflow rebuilds since #322). Filed as #909;
   main() and the scheduling builtins are now skipped, and the remaining
   top-level effects are #917.

Revised 2026-11-11 for #921: an error raised by a call now points at the start of
the callee, so ingest.nd 13:55 -> 13:14, rekey.nd 3:42 -> 3:1 and plain.nd's
"called from" 6:24 -> 6:7 (each re-run on main and with the fix).

Revised 2026-11-11 for #912: §6.1 is new. export.nd was started with `nodus run`,
cancelled by key from a second shell 4.5 s in, and both outputs pasted verbatim.

Revised 2026-11-11 for #911: a checkpoint inside a `for` over a list is now
captured, so §4.1's first example runs to completion (re-run, verbatim) and the
`while` workaround is gone. The refusal example uses a user-defined iterator
instead (custom.nd, run the same day).
-->
