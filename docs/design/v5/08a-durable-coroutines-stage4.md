# Durable coroutines, stage 4 — decisions (addendum to 08)

**Status: proposal for review, not built.** Drafted 2026-11-10 after stages
0–3 shipped (#900, #901, #902). On four questions the maintainer accepted the
defaults proposed before this was written: D1 and D2 (how durability is
declared, and what `checkpoint` becomes), D3 (the store), D4 (what resumes it)
and D6 (blocked and sleeping coroutines, which turned into a clock question).
D3's release timing was left open, and this file recommends an answer.
**D5 is new and has not been reviewed.** It came out of writing the rest down.
Nothing in this file is implemented yet.

[`08-durable-coroutines.md`](08-durable-coroutines.md) decided what a checkpoint
in a bare coroutine *means* (a position, §4) and staged the work (§8). It left
five questions open (§7). Stage 3 answered the one that could have killed the
design: a continuation captured in one process resumed in another
(`tests/test_continuation_roundtrip.py`). This file answers the rest, and adds
two the original did not ask, which turned out to be load-bearing (D5, D6).

Every claim about the current tree below was checked against `main` at
`af45a9c`.

---

## D1. Durability is declared by a builtin: `durable_spawn`

```
fn worker(job_id) {
    let rows = fetch(job_id)
    checkpoint "fetched"
    for_each_row_upload(rows)
    checkpoint "uploaded"
    return len(rows)
}

durable_spawn("ingest-\(job_id)", worker, [job_id])
run_loop()
```

**A builtin, not syntax.** §5 recommended a `durable spawn` declaration and §7
asked whether it earns surface syntax. It does not, yet. #336 proposed a
`spawn { }` keyword and it was rejected because the grammar position it needs
is the one `match` occupies (#717). A builtin needs no grammar change, and
adding a keyword later stays a compatible extension. Removing one would not be.

**The entry is checked when `durable_spawn` is called**, not at the first
checkpoint. It must be a named top-level function of the calling module with no
captured variables: stage 2's `unnamed_entry` and `captured_cell` checks, run on
the entry alone. That moves the diagnostic §5 worried about ("arrives at the
checkpoint, deep inside a program that already ran") to the line that made the
mistake. It is a run-time check, so `nodus check` does not see it. A static
version, the way `goal_validation.py` checks `reached("label")`, is possible
later when the first argument is a literal function name.

**Arguments are a list of data**, arity-checked against the entry and walked by
stage 2's value check. `coroutine()` takes only zero-argument functions, and the
idiomatic way around that is a closure (`coroutine(fn() { worker(5i) })`),
which is the anonymous entry stage 2 refuses. The arguments are what replaces
that closure, and they are persisted with the run.

**Considered and not taken: a `durable fn` modifier.** It would let the parser
allow `checkpoint` only inside durable functions and keep stage 1's error at
compile time everywhere else. But a checkpoint in a helper that a durable worker
calls is legitimate (stage 3 restores a suspend inside a nested call), and the
modifier would forbid it. That is a second syntax position for less
expressiveness. Revisit if the run-time error in D2 proves too late in practice.

## D2. `checkpoint "label"` in a function compiles to a suspend

**Where it is allowed.** Stage 1 made `checkpoint "x"` outside a step body a
parse error. Stage 4 narrows that:

- **At module top level it stays a parse error.** No function is running there,
  so it can never be inside a durable coroutine.
- **Inside a function body it compiles**, and checks at run time whether it is
  in a durable coroutine. If it is not, the error keeps stage 1's wording and
  pointer, and adds "spawn it with `durable_spawn`". Whether a function runs
  durably is a run-time fact, the same function can be called both ways, and D1
  rejected the modifier that would have made it static.
- **Inside a step body it is unchanged**: a workflow checkpoint, re-entry
  semantics (#486).

The word stays contextual. Every allowed shape in
`tests/test_checkpoint_outside_step.py` must keep compiling.

**What it does at run time.** It lowers through `builtin_call()` (compiler
guarantee forgery, #411/#449: every lowering goes through it) to a builtin that
returns a suspend request, the way `sleep` returns a `SleepRequest`. Stage 3
established that capture must happen at a suspend, because a running
coroutine's `ip` is in the VM's registers until a suspend writes it out.

The scheduler, seeing the request:

1. **Captures.** It runs `capture_continuation` on the parked coroutine.
2. **Persists.** It writes the continuation to the run record, and the write
   completes before anything else happens.
3. **Reschedules.** It puts the coroutine back on the ready queue.

**The guarantee is precisely this:** no work after a checkpoint begins until
that checkpoint is in the store.

**If capture refuses**, the refusal is raised into the coroutine *at the
checkpoint*, as a catchable error carrying stage 2's report: §4.1, "fails loudly
at the moment it cannot honour its promise". A `checkpoint` inside a `for` body
is the case users will hit first (stage 2's §3.2 correction). Until the loop
iterator has a written form, the error has to say so plainly and suggest the
workaround: a `while` loop over an index, which holds plain data.

**Semantics to document: at-least-once between checkpoints.** A crash re-runs
everything after the last checkpoint. That is the same contract a workflow step
has between its re-entries, at a finer grain. "Exactly once" is not on offer and
must not be implied.

## D3. The store's claims must be exclusive across processes, and that does not wait for 6.0.0

**`durable_spawn` refuses a store whose claims are not exclusive across
processes.** The refusal names the fix: `NODUS_WORKFLOW_STORE_BACKEND=sqlite`,
or `nodus workflow migrate-store --to sqlite`. The store declares the property
(`EXCLUSIVE_CLAIMS_ACROSS_PROCESSES`), so a third-party store can opt in. The
base class says False, because a wrong True costs a run resumed twice.

**Corrected by stage 4a: the property is not "crash safety".** This section
first said `LocalWorkflowStore` is refused because it is "documented as not
crash-safe", following #174, which says a process kill mid-cycle can corrupt run
state. On reading the code, that is not the difference. Both stores write each
record atomically: the JSON store with fsync and rename, SQLite with a
transaction. The real difference is the one D4 and D5 depend on.
`LocalWorkflowStore.claim_run` guards its check-then-write with a
`threading.Lock`, which is invisible to another process. SQLite's runs inside
`BEGIN IMMEDIATE`, which is not.

`tests/test_store_claim_exclusivity.py` races two handles on one backing, the
second inside the first's window. Two claimants win on the JSON store and one on
SQLite, and each store's declaration is checked against that result.

SQLite here runs WAL with `synchronous=NORMAL`. A power loss can lose the newest
commits, but it cannot tear a record. Under D2's at-least-once contract, losing
the newest checkpoint means re-running more work, never skipping any.

**The 6.0.0 question.** The maintainer offered to bring 6.0.0 forward if this
needs it. **It does not need it to be correct.** The refusal makes durable
coroutines correct on 5.x as soon as SQLite is chosen, and wrong nowhere.

What 6.0.0 changes is only the default: the staged `default-store-sqlite` flip
(`src/nodus/support/staged_flips.json`) makes SQLite what an unconfigured
program gets, so durable coroutines would work with no setup at all.
**Recommendation:** ship stage 4 in a 5.x minor as opt-in, and let the 6.0.0
flip remove the opt-in step when it lands. Neither release then waits on the
other. If 6.0.0 is cut for its own reasons first, nothing here changes.

## D4. A durable coroutine is a run in the workflow store

The design suspected (§7, question 4) that what resumes a durable coroutine is
"the same store and the same sweeper", and asked whether that collapses into a
one-step workflow. **It shares the record and the machinery, not the
semantics**:

- **Record.** A `WorkflowRunRecord` with `execution_kind = "coroutine"`. The
  field already exists and holds `"workflow"` or `"goal"` (`models.py`,
  filtered by `execution_kind` in `runner.py`). The continuation, the entry,
  the arguments, the program source and the clock reading (D6) go in
  `metadata`. `current_checkpoint` holds the label.
- **Claiming.** `claim_run` returns a claim or `None` against the run's
  expected statuses, so exactly one claimant wins and two processes cannot
  resume the same coroutine.
- **Resume.** `rehydrate_runs(vm_factory)` already builds one VM per record.
  That is exactly what D6 needs, and it is the path an embedder or the server
  uses. The CLI path is D5.
- **Not a one-step workflow.** A step resumes by re-entering from the top
  (#486), and its record holds graph state, not a frame. Wrapping a coroutine as
  a one-step workflow would either inherit re-entry, which is the wrong
  semantics, or special-case the step runner, which is two meanings of
  `checkpoint` under one roof. A new kind in an existing record is cleaner.

**The risk this creates is this codebase's recurring bug shape** (one
vocabulary, N enumerations, one site missing a member). Every consumer that
branches on `execution_kind` must be found and told about `"coroutine"`,
including `nodus workflow list`, `resume`, `cleanup` and `migrate-store`, the
server's endpoints, and the staged-readiness check. Stage 4a starts by naming
the kinds once, beside `BLOCKED_REASONS`-style vocabularies, with a test that
fails on any literal kind outside it, *before* adding the new member.

**Program identity on resume.** The record persists the program source, as
workflows do (`workflow_source_code`, #469/#497), and resume compiles *that*
source rather than whatever is on disk now. Stage 3's fingerprint check stays
as the second line. Imported modules are not pinned: a resumed coroutine that
calls into one gets its current version, as a resumed workflow does. Frames
running *inside* another module are still refused at capture.

## D5. `durable_spawn` takes a required key, and the key makes it resumable

This is the question §7 did not ask, and the one most likely to cause the
failure the feature exists to prevent.

**The program that calls `durable_spawn` is not itself durable.** Run a script
that durably spawns a job, kill the process, run the script again: the second
run calls `durable_spawn` again. Without a key, the job then runs twice, once
from the store and once fresh. That is a silent double execution, and it comes
from a durability feature.

**So the first argument is a key, and it is required.** If a run with that key
already exists in the store:

- **still in progress** → this call *adopts* it: claims it, restores its
  continuation into this process, and returns its run id. Nothing new starts.
- **finished** → returns its run id and result; nothing runs.
- **failed** → returns its run id; nothing reruns. Retrying is an explicit,
  separate act (`nodus workflow cleanup`, or a new key). It is not a side
  effect of restarting a script.

**This answers "what resumes it" for the CLI**: running the program again does.
For a long-lived host, `rehydrate_runs` does (D4). Both go through the same
claim, so a script restarted while a server is rehydrating cannot resume the
same coroutine twice.

A key that is optional would be the one that gets left out, so the default
would be the double-execution case. That is why it is required, and why it is
the first argument rather than an option.

## D6. Clock-derived values survive a resume because the clock does

§7's third question was what happens to a remaining sleep on resume. **Stage 3
shows there is none to handle.** A checkpoint's own suspend has zero length,
and capture only happens there, so no in-progress sleep is ever captured. A
crash while sleeping *after* the last checkpoint re-runs from that checkpoint,
and the sleep is reissued (D2, at-least-once).

**The real problem is different, and stage 2 cannot see it.** The scheduler's
clock is milliseconds since *this process* started (`runtime_time_ms`,
`time.monotonic() - _START`). A local holding a deadline, from
`runtime.time_ms()`, `loop.deadline` or a `sleep_until` target, is a plain
number, so it is durable by stage 2's rules. After a resume it means something
else: the new process's clock started near zero, so the coroutine waits roughly
as long as the old process had been running before the deadline is reached.
That is #778's mistake (comparing readings from two clocks) recreated by a
restore.

**Default: persist the clock, and continue it.** At each checkpoint, record the
scheduler-clock reading and the wall-clock time. The VM that resumes the run
(one per record, D4) gets a `TimeSource`, the seam #182 made, offset so that
`now_ms()` continues from the captured reading plus the wall-clock time elapsed
since. Deadlines held in locals then keep their meaning. One that has passed
yields once, which is existing `sleep_until` behaviour, and does not hang.

Consequences, stated so they are not rediscovered:

- **A host's clock jump moves deadlines by the same amount.** Wall-clock
  elapsed is the best estimate available across a restart. The offset is
  clamped at zero, so a clock that runs backwards cannot make time run
  backwards for the coroutine.
- **The offset is per resumed run, not per process.** That is why D4's
  one-VM-per-record matters. Two resumed coroutines checkpointed at different
  times each continue their own timeline.
- **Channels are not resumed.** Stage 2 already refuses a channel held in a
  local. A channel reached through a module global is a *new* channel after a
  resume (module state is rebuilt from source), so its counterparty must be
  re-established by the program. The guide must say so.

---

## Staging stage 4

| step | what | worth having if the next step never ships |
|---|---|---|
| 4a | the `execution_kind` vocabulary, named once and pinned; then `"coroutine"` added to it. the store's cross-process claim declaration and refusal | the enumeration guard is useful on its own; the refusal is the foundation |
| 4b | `durable_spawn(key, fn, args)` with entry and argument checks, adoption by key; `checkpoint` lowering, capture to the store, refusal raised at the checkpoint | the feature, resumable by re-running the program |
| 4c | clock continuity (D6); `rehydrate_runs` for the coroutine kind; `nodus workflow list/resume/cleanup` | resumable by a long-lived host, and deadlines that survive |
| 4d | guide chapter; `OPERATOR_OR_EMBEDDER_RUNBOOK.md` §6.2, whose title *"A bare coroutine is transient — only a workflow survives a crash"* stops being true; stability index entry as experimental; `llms.txt` | the claim is published |

**Progress:** 4a shipped 2026-11-10 (#904). 4b shipped 2026-11-10 (#905); its one
addition beyond this file is an atomic `renew_claim` on the stores, because
nothing renewed a claim before and a durable coroutine outlives the 30 s
default. 4c is built. Three points settled in building it:

- **The clock offset is per coroutine, applied at one reader** (`VM.guest_clock_ms`,
  which `runtime.time_ms()` and `sleep_until` both use, with a source test
  pinning that). A scheduler-wide offset could not serve two adopted runs
  checkpointed at different times, and it would shift every other coroutine's
  clock.
- **The sweep *resumes* a coroutine run; it does not adopt it.** That is
  consistent with how the sweep already runs due retries and released
  schedules. `rehydrate_runs` stays adoption-only and skips coroutine runs.
- **One rebuild from stored source** (`VM.reexecute_source_for_resume`), shared
  by the workflow graph rebuild and the coroutine resume, so the two cannot
  drift. It suppresses `print`, `run_workflow`, `run_goal` and `durable_spawn`.
  It does **not** suppress a top-level `spawn` + `run_loop` or a top-level host
  call, which run again during any rebuild. That was already true of workflow
  rebuilds before this (measured 2026-11-10), and is reported separately rather
  than changed here.

**4b and 4c are not separable in a release.** A release with 4b and without the
clock continuity in 4c would let a deadline loop misbehave after a resume. They
can be separate PRs, but not separate releases.

**What each step must be tested against**, from the lessons of 1–3:

- **Inside a step body as well as outside.** A construct is tested where it is
  documented for use (5.8.0's `retry.until` lesson). The step-body `checkpoint`
  must be shown unchanged in the same suite as the coroutine one.
- **Under both test runners.** CI runs `unittest` and `pytest`, and the
  source-scanning tests are what caught stages 2 and 3, so run all of them.
- **Across two processes for anything persisted**, with different hash seeds.
- **A real kill.** Stage 3 discarded a coroutine politely. Stage 4 needs a test
  that kills the process (`os._exit` or a subprocess `kill`) between a
  checkpoint and the next one, then shows the work after the checkpoint re-runs
  and the work before it does not.

## What stays open

- **The `for` iterator's written form.** A list and an index would cover
  iteration over a list; a user-defined `__next__` iterator holds a closure and
  may never have one. Until then a checkpoint in a `for` body is refused (D2).
- **Cancelling a durable coroutine** from outside, and what its record says.
  #395's `cancel` covers the in-process half only.
- **Retention.** Finished coroutine runs accumulate like finished workflow runs,
  and `nodus workflow cleanup` is where that already lives. That only works once
  4a has given `cleanup` the new kind.
