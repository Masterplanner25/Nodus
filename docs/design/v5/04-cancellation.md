# Cancellation — design for #395

**Status: proposal, except §9 (done) and the handle, which is decided in
`06-task-handle.md` — read that first for the object `cancel` acts on, and for
why this issue and #157 were decided together.**

**Status of the rest: proposal.** No cancellation code has been
built; the documentation half landed first and §9 records what shipped. §3 is the
part to read first:
two of the four design questions #395 lists were answered by code that shipped
*after* the issue was filed, so the decision left is narrower than the issue
describes.

**Everything in §2 was verified against `main` at `5fab54e`** by reading the
code, not inferred from the issue. #395's own premise line is stale, and so is
the `TECH_DEBT.md` entry that repeats it — see §2.6.

---

## 1. What #395 asked

> *"Nodus has no way to stop work it started. A grep for `cancel` across
> `src/nodus/` returns **one** hit — `print("Login cancelled.")` in the CLI."*

It lists four questions to settle before implementing:

1. Is cancellation cooperative (a flag checked at yield points) or does it unwind
   via an injected `throw`?
2. Does a cancelled coroutine run its `finally` blocks?
3. Does cancelling a graph run cancel step coroutines, or only stop dispatching
   new steps?
4. Does this get a language surface (a scope construct) or only a builtin?

## 2. What already exists — measured, not assumed

### 2.1 The unwind mechanism exists, and it is the hard half

`VM.unwind_cancelled_coroutine` (`vm.py:2702`) landed with **#502**. It sets
`coroutine.cancelling = err`, loads the coroutine's context, and drives
`handle_exception(err)` — unwinding through the handler stack and running every
pending `finally`.

`handle_exception` (`vm.py:547`) reads that flag and **refuses to enter a
`catch`** while cancelling:

> *"A timeout that a `catch` could swallow would not be a timeout — the step
> would carry on past the deadline that was supposed to bound it."*

The unwind is bounded by the same `task_step_budget` as any other resume, so a
`finally` that loops forever cannot turn a cancellation into a hang.

This is the part that would have been expensive to build and easy to get wrong.
It is built, it is correct, and it is the reason this proposal is small.

### 2.2 Nothing can pull the trigger

The only caller is the scheduler's per-coroutine timeout check
(`runtime/scheduler.py:272`). There is:

- no `cancel` builtin — `grep '"cancel'` over `src/nodus/builtins/` and `vm.py`
  returns nothing;
- no host API on `NodusRuntime`;
- no CLI subcommand (`nodus workflow` has `run`, `list`, `resume`,
  `dead-letters`, `runs`, `inspect`, `replay`, `migrate-state`, `cleanup`);
- no HTTP route.

**Cancellation happens *to* a coroutine, on exactly one condition, and nothing
can request it.** That is the gap, and it is a much smaller one than "no
cancellation anywhere".

### 2.3 There is no tree, and `spawn` returns nothing to hold

The `Coroutine` dataclass (`runtime/coroutine.py`) carries `owner_vm`,
`module_ctx`, `blocked_on`, `blocked_reason`, `cancelling`, `step_authorized` —
and **no parent field**. `builtin_spawn` (`builtins/coroutine.py:110`) ends
`return None`: a program cannot name the thing it just started.

`scheduler._coroutine_errors` is a flat list appended to on failure and drained
by `run_loop`. It collects; there is nothing to propagate *to*.

### 2.4 `blocked_on` covers channels only

#395 says `blocked_on`/`blocked_reason` are "the state a cancellation mechanism
needs to know how to unblock a waiter". True, but partial: every assignment is in
`builtins/coroutine.py`, with reasons `channel_send` and `channel_recv`. A
coroutine sleeping is in the timer heap; a coroutine inside a host agent call is
blocked on a thread join with nothing recorded on the coroutine at all. §6.2
enumerates all five states, because a cancel that handles two of them is the
sibling-path shape.

### 2.5 Some work cannot be preempted, and that is settled doctrine

**#424 already decided this**, for host agent handlers
(`services/agent_runtime.py:55`):

> *"Recorded when a handler outlives its deadline and is left running. Never
> 'un-recorded', because there is no reliable moment to observe such a thread
> finishing — that is the whole reason it had to be abandoned."*

The deadline stops the **wait**, not the handler. Arbitrary Python cannot be
preempted, so the handler runs on a daemon thread and is abandoned at the
deadline, with `abandoned_agent_calls()` and `abandoned_agent_call_count()` for
the operator question "is something stuck?".

Cancellation inherits this answer rather than reopening it. Any design that
promises to *stop* a host call is promising something the runtime cannot deliver.

### 2.6 Two stale claims to fix while here

- **#395's premise.** `grep -ri cancel src/` now returns 23 hits across six
  files, not one. The issue was filed 2026-08-15; #502 landed after it.
- **`TECH_DEBT.md:588`** repeats *"One `cancel` hit in `src/nodus/`, a CLI
  print"* verbatim, and so understates what is built.
- **`task_graph.py:1497`** cites *"the open half of #475"*; #475 is closed.

## 3. Two of the four questions are already answered — by code

| # | Question | Answer | Where it was decided |
|---|---|---|---|
| 1 | Cooperative flag, or injected `throw`? | **Injected throw.** `unwind_cancelled_coroutine` drives `handle_exception`. | #502, shipped |
| 2 | Does a cancelled coroutine run its `finally` blocks? | **Yes** — and `catch` is refused, so it cannot swallow its own cancellation. | #502, shipped |

These are not open. Answering them differently now would mean **two unwind paths
for one question**, which is the defect shape `CLAUDE.md` documents twenty-three
instances of. Whatever gets built must route through
`unwind_cancelled_coroutine`.

Question 2's answer also fixes the invariant story: I-VM-06 (*`finally` blocks
always execute*) is what #502 was defending. A cancellation that skipped
`finally` would break a documented invariant, so "should a cancelled coroutine
run its finallys" was never really a free choice.

## 4. The remaining fork

**Given that the unwind path exists and only a timeout can reach it: what may
pull the trigger, and does cancellation need a *scope* or only a *handle*?**

| | A handle | A scope |
|---|---|---|
| Shape | `spawn` returns something; `cancel(it)` | nursery / task group; parent links; first failure cancels siblings |
| New concepts | one value type, one builtin | parent/child tree, scope lifetime rule, language surface |
| Reuses the #502 unwind | yes, unchanged | yes, plus propagation |
| Answers "abandon a coroutine blocked on a slow agent call" | yes | yes |
| Answers "cancel a workflow run in progress" | yes (§7) | not directly — a run is not a lexical scope |
| Answers "first failure stops the siblings" | no | yes |

### 4.1 Recommendation: the handle. No scope construct.

The scope's one distinctive win is *first failure stops the siblings* — and
**Nodus already has that, at the altitude where it actually expresses fan-out.**

A step failure stops the run from dispatching new work
(`task_graph.py:1225, 1496`), the un-dispatched steps are reported `cancelled`,
and #475 decided the opt-out: `with { allow_failure: true }` lets a branch fail
without taking the run down. #480 added dynamic fan-out (`step render each page
in discover`), so "bounded fan-out over a list computed at runtime, where the
first failure stops the rest" is expressible **today**, in the workflow DSL, with
declared failure semantics.

A nursery would therefore be a **second way to express bounded concurrent
fan-out**, competing with the workflow DSL, at a different altitude, with its own
failure vocabulary. That is precisely the "one question, two implementations"
shape this codebase treats as a defect class rather than a style preference.

Test it against the domain statement's two-part rule
(`00-domain-statement.md §3`) and the same answer falls out. A scope construct
passes test 2 — the compiler *could* enforce that no task outlives its scope. It
fails on the prior question the rule presupposes: the property is not
*forgotten* today, because the construct that carries it (`workflow`) is the one
users are already told to reach for.

**Residue, stated honestly:** raw `spawn` + `channel` concurrency stays
unscoped. A program that spawns coroutines directly gets a worker pool, not
structured concurrency. That is a real limitation, and §9 says so rather than
implying otherwise — which is what #395 asked the docs to do.

## 5. Surface

Three entry points, one mechanism.

### 5.1 Guest: `spawn` returns a task handle

```
let c = coroutine(fn() { ... })
let t = spawn(c)          // was: nil
cancel(t)                 // request cancellation
```

(Deliberately a bare fence rather than a `nodus`-tagged one: the gate executes
those, and this syntax does not exist yet. Same convention as the other v5
design docs.)

`spawn` returns `nil` today, so a program can already write `let t = spawn(c)`
and get nothing useful. Returning a handle changes that value — technically a
behaviour change, practically unobservable, since nothing can be done with `nil`.
It is additive in the sense that matters and should be called out in the
changelog anyway.

> **Withdrawn — superseded by `06-task-handle.md` D1/D2.** This section proposed
> a record handle, `{ id: 3i, name: "worker", state: "running" }`. That was
> wrong: a record is a *value*, so `state` would freeze at spawn time and read
> `"created"` for the life of the task. It was also unnecessary — the coroutine
> value is already a live handle (`coroutine_status(c)` tracks it across the
> spawn and the loop, measured) and is unforgeable, because `ensure_coroutine`
> is an identity check while a record can be constructed by any guest.
>
> **Decided: `cancel(c)` takes the coroutine.** `spawn(c)` returns `c` for
> convenience. No new value type, and no bare-id form — an id is exactly the
> forgeable handle the coroutine type avoids being.

### 5.2 Host: `NodusRuntime.cancel_run(graph_id)`

The embedding case #395 names. §7.

### 5.3 CLI: `nodus workflow cancel <graph_id>`

Alongside `resume` and `replay`, which already take a `graph_id`.

### 5.4 No new keyword

Question 4, answered: **builtin only.** A scope construct is the only thing that
would justify syntax, and §4.1 rejects it. This also keeps `cancel` usable as an
identifier, which a contextual keyword would too but a reserved one would not.

## 6. Semantics

### 6.1 The rule

> **`cancel` unwinds the target at its next yield point, running every pending
> `finally` and no `catch`. It never stops work already inside a host call.**

Delivered through `unwind_cancelled_coroutine`, unchanged. The `catch` refusal is
inherited deliberately: a program that could catch its own cancellation could
decline it, and a cancellation that can be declined is a suggestion.

### 6.2 What cancel does in each blocked state

The enumeration that makes this a design rather than a sketch. A cancel that
handles the first two rows and not the rest is the recurring shape.

| State | How it is woken today | On cancel |
|---|---|---|
| ready (in the scheduler deque) | next tick | remove from deque; resume once with `cancelling` set to unwind |
| sleeping (timer heap) | timer expiry | remove from heap; unwind immediately — do **not** wait out the sleep |
| blocked on `send`/`recv` (`blocked_on` set) | counterparty, or deadlock detection | clear `blocked_on`, drop it from the channel's waiter list, unwind |
| inside a host **agent** call | thread join, or `agent_timeout_ms` | **cannot preempt** (§2.5). Stop waiting, record the abandonment, unwind the coroutine. The handler keeps running. |
| inside any other blocking builtin (`http_get`, `subprocess.run`) | returns when it returns | same: cancellation takes effect at the next yield point |

The last two rows are the honest caveat. They are not new debt — they are #424's
already-shipped answer, applied to a second trigger.

**This table gains a sixth row if #157 is built** — a coroutine parked in
`join(t)`, woken when `t` settles. That is not a hypothetical: `05-async-library-
boundary.md §7` recommends the `join` verb on *this document's* task handle, and
a table written to prevent a cancel from handling some blocked states and not
others would be incomplete on the day `join` landed. The mitigation is the one
CLAUDE.md prescribes for the shape: **name the set once** — `blocked_reason`
becomes a named tuple that the cancel path and every blocking builtin drive off,
so a seventh state fails the suite rather than being silently unhandled. Decide
the two issues together; see §11.

### 6.3 Cancelling something already finished

A no-op returning `false`. Cancelling a coroutine that has finished, was never
spawned, or is already cancelling is not an error: the caller of a cancel usually
cannot know, and making it raise would push every call site into a
check-then-act race.

`cancel` returns `true` when it moved a live coroutine into unwinding.

### 6.4 What the canceller observes

Nothing is thrown at the canceller. The cancelled coroutine's error goes where a
timed-out coroutine's error goes today — `scheduler._coroutine_errors`, drained
by `run_loop`. **No change to error collection**, and no parent to propagate to,
per §4.1.

## 7. Run-level cancellation — **built**

Separable from §5.1 and, for an embedder, the more valuable half.

> **Status: shipped.** `WorkflowFrameworkRunner.cancel_run(run_id)`,
> `run_is_cancelled(run_id)`, and `nodus workflow cancel <graph_id>`.
> `RUN_STATUS_CANCELLED` is the eighth run state, terminal and not rehydratable.
>
> **One thing this section did not anticipate.** The run-status vocabulary was
> named *three* times: `REHYDRATABLE_RUN_STATUSES` in `store.py` and
> `_REHYDRATABLE_STATUSES` in `runner.py` were independent definitions of one
> equal set, with the members listed again as `_KNOWN_RUN_STATUSES`. Adding an
> eighth status is precisely when that costs something — four edits, and the one
> you miss is silent. The vocabulary now lives once in `models.py`
> (`RUN_STATUSES`, `TERMINAL_RUN_STATUSES`, `REHYDRATABLE_RUN_STATUSES`) and the
> other modules import it; `tests/test_run_cancellation.py` asserts the sets are
> the *same objects*, not merely equal, since equality is what they already had
> and is what let them sit unnoticed.
>
> `nodus_gate --shapes` did not flag it: its species-B detector looks for one
> literal collection being a strict *subset* of another, and these were equal.
> A real hole in the detector, recorded here rather than fixed.
>
> **§7.1 is built too.** `schedule_ready` asks at each dispatch pass, and on a
> cancellation it stops dispatching *and* unwinds the steps already in flight —
> through the `cancel` builtin, not a second unwind, so a step holding a lock
> still gets its `finally`.
>
> The predicate is **injected, never imported**: `TaskGraph.cancel_check` is set
> by the runner, because `task_graph` importing `nodus_lang_workflow` at module
> scope would reinstate CIRC-001 (#103), whose lazy-import fix `CLAUDE.md` says
> not to undo. A bare `run_graph` gets no predicate and is unaffected, which is
> correct — a run no store knows about cannot be cancelled through one.
>
> A predicate that *raises* counts as "not cancelled". A store read failing must
> not take down a run that is otherwise fine, and the next pass asks again.
>
> One consequence this section did not name: **the runner must not write the
> result status back over `cancelled`.** The graph stops mid-flight, so
> `_result_status` reads it as failed or completed depending on what had settled,
> and writing that back would un-cancel the run in the record — losing the one
> fact the operator asked for.

### 7.1 Both halves, not one

Question 3, answered: **stop dispatching *and* unwind in-flight step
coroutines.**

Stopping dispatch alone would let an in-flight step run to completion — and a
step blocked on a slow agent call is exactly what someone cancelling a run is
trying to stop. Unwinding without stopping dispatch would start new steps behind
the cancellation. #502's whole argument was that dropping a step without
unwinding loses its `finally`; the same argument applies here.

### 7.2 In-process is immediate; cross-process is cooperative

A run in flight lives in some process's scheduler. `cancel_run(graph_id)` in that
process can act at once. From another process — the CLI against a server's store
— all it can do is **mark the record**, and the owning runner must observe it.

Recommendation: mark in the store, and have the runner check at **step
boundaries**, where it already decides whether to dispatch. Cross-process
cancellation is therefore *eventually* effective, bounded by the current step's
duration. That is a real limit and should be documented as one rather than
papered over — a cancel that silently does nothing until a 40-minute agent call
returns is worse than a cancel that says so.

### 7.3 A cancelled run needs an eighth run state

`models.py` declares seven: `pending`, `running`, `waiting`, `retry_scheduled`,
`completed`, `failed`, `dead_lettered`. A cancelled run is not `failed` — it did
not fail, it was stopped — and reporting it as such would corrupt every failure
rate an operator computes.

Add `RUN_STATUS_CANCELLED`, terminal. Consequences to handle in the same change:

- `_REHYDRATABLE_STATUSES` (`runner.py:180`) must **not** include it, or a
  cancelled run resurrects on the next sweep;
- `nodus workflow cleanup`'s retention must treat it as terminal, or cancelled
  runs accumulate forever;
- `nodus workflow runs --status` gains a value;
- any consumer that enumerates run statuses exhaustively sees a new one. Additive
  for readers that switch on known values, breaking for readers that assert the
  set — `check_dependent_suites` is the gate that would catch it.

### 7.4 Do **not** add a task status

`TASK_STATUSES` already contains `cancelled`, and it means something else:
*never dispatched, because a sibling failed* (`task_graph.py:1496`). A step that
was actively cancelled mid-flight **did** run and was unwound.

Reusing the label would collapse a distinction an operator needs; adding
`cancelled_in_flight` would be an ugly seventh-and-a-half. Neither is necessary:
**an actively cancelled step reports `failed`, with a distinguishable error
kind** — exactly what a timed-out step does today. The task vocabulary is
untouched, and `tests/test_status_vocabulary.py` keeps passing unchanged.

## 8. What this does not do

- **Does not make Nodus structurally concurrent.** No parent/child links, no
  scope lifetime rule, no propagation. `spawn` remains a worker pool. §9.
- **Does not stop host work.** §2.5, §6.2.
- **Does not add error propagation to a parent.** There is no parent.
  `_coroutine_errors` keeps collecting.
- **Does not give cancellation a language surface.** §5.4.
- **Does not make cross-process cancellation immediate.** §7.2.

## 9. The documentation change #395 actually asked for — **done**

> *"What it provides is **asynchronous primitives, not structured concurrency** —
> and docs should say so rather than implying the stronger property."*

Separable from every line of code above, and landed first. What shipped:

1. **`FAILURE_AND_DEGRADATION_MODEL.md §9.0`** — the worker-pool model stated
   normatively, with the three consequences (a spawned coroutine outlives its
   scope, a failure does not stop siblings, there is nothing to wait on or
   cancel) and a pointer to the workflow DSL for the stronger property.
2. **`§9.1` rewritten — it was wrong**, and wrong in the direction this issue is
   about. It said the exception "is recorded on the coroutine object" and that
   "the spawning code receives the error when it resumes or waits on the
   coroutine" — implying a parent/child await that does not exist. Measured
   behaviour: the trace goes to stderr, the error goes to the *scheduler's* list,
   `coroutine_status()` reports plain `finished`, `run_loop()`'s **return value**
   is the only way a program can see it, and the run still exits `0`.
3. **`§9.4` added** — the timeout unwind is the one cancellation path, with
   #424's un-preemptable-host-work caveat.
4. **`LANGUAGE_SPEC.md`** — the same statement normatively, plus `run_loop()`'s
   return value, which the spec had never documented.
5. **`standard-library.md`** — a runnable two-coroutine example showing a sibling
   surviving a failure, with the four takeaways.
6. **`TECH_DEBT.md`** — the stale "one `cancel` hit" claim (§2.6) replaced with
   what is actually built and what is actually missing.
7. **`task_graph.py`** — the "open half of #475" comment; #475 closed in 5.4.0
   and `allow_failure` is the answer. Verified by running a→{b,c}, d after c with
   b failing: `d` is `cancelled` by default, `completed` when b is tolerated.

**Two stale claims were found while doing it**, neither of them in §2's list and
both in the same neighbourhood:

- `LANGUAGE_SPEC.md` still said *"`worker_pool` and `pipeline` are **currently
  non-functional**"* citing #339 — three releases after #339 was fixed
  (2026-08-15). `standard-library.md` had it correctly in the past tense, so the
  two documents contradicted each other and the **spec** was the wrong one. Both
  were verified working by running them.
- `FAILURE_AND_DEGRADATION_MODEL.md §9` had a duplicated `### 9.2` heading.

The lesson is the one #412 phase 2 had just finished teaching: the errors were
not in the prose that describes the *missing* feature, they were in prose
describing features that already **changed**. Nobody re-reads a document when the
code beneath it moves.

## 10. Open decisions, with recommendations

### 10.1 Does `cancel` accept a workflow step?

**Recommendation: no.** A step is cancelled by cancelling its run. A per-step
cancel would need a step-addressing scheme the DSL does not have, and the use
case ("stop this one branch") is `allow_failure` plus a failing step.

### 10.2 Should `cancel` be gated by the capability policy?

**Recommendation: no, and say why in the code.** Cancellation removes authority
rather than granting it; a guest that can cancel its own coroutines can already
achieve the same effect by returning. It is not in the class `CapabilityPolicy`
exists to bound. The host-facing `cancel_run` is a Python API and is not
guest-reachable at all.

### 10.3 Does cancelling a parent run cancel child runs? — **decided: yes**

This was the decision in this document with the least evidence behind it, held
open pending a read of the child-run mechanics rather than assumed from the
cleanup behaviour. That read has been done, and it **replaces the argument**
while keeping the answer.

What the mechanics actually are (`orchestration/task_graph.py:765-795`, #501):

- a child run is produced by a **nested `run_workflow` call inside a parent's
  step body**. It is not a peer run scheduled elsewhere — it is synchronously
  nested in the parent's step coroutine, which is blocked in `run_task_graph`
  for the child's duration;
- both directions of the link are durable: the child's metadata carries
  `parent_graph_id` / `parent_step` / `parent_task_id`, the parent's accumulates
  `child_graph_ids`;
- `nodus workflow cleanup` already walks parent→child over `parent_graph_id` in
  a fixpoint loop (`cli/cli.py:831-851`), so the traversal cancellation needs
  exists and is exercised.

**The cleanup analogy was the weak argument. The nesting is the strong one.**
§7.1 already unwinds in-flight step coroutines — and the step running a child
*is* one of them, so cancelling the parent stops the child's execution whether or
not anything is decided here. What is left to decide is only whether the child's
own **record** is marked, and the answer follows: if it is not, the unwind leaves
a non-terminal run record whose parent is terminal and whose executor is gone —
an orphan that `_REHYDRATABLE_STATUSES` may later resurrect. That is #476's
half-state shape (state without record, record without state) arriving from a new
direction.

So: **cascade, marking non-terminal children `cancelled` transitively.** Two
consequences to handle in the same change:

- **Only non-terminal children.** A parent typically has *several* children, most
  of them already `completed`: #486 re-entry means a resume re-enters the step
  from the top, so each resume produces a **new** child. Marking them all would
  rewrite finished history.
- **Cross-process children inherit §7.2.** A child owned by another process can
  only be marked and observed at its next step boundary.

### 10.4 A deadline for the unwind itself?

`task_step_budget` bounds it already (§2.1). **Recommendation: reuse it, add
nothing.** A second budget for the same question is the shape.

## 11. Relationship to other work

- **#502** built the unwind and decided questions 1 and 2. This proposal is a
  second trigger for it, not a second mechanism.
- **#424** decided that un-preemptable host work is abandoned, not stopped
  (§2.5, §6.2).
- **#475** decided fan-out failure semantics (`allow_failure`), which is most of
  the argument against a scope construct (§4.1).
- **#480** made fan-out dynamic, which is the rest of it.
- **#361/#370/#371** are why the `finally` guarantee under cancellation can be
  relied on rather than hoped for.
- **#157 / `05-async-library-boundary.md`** wants the **same task handle** §5.1
  proposes here, for a second verb (`join`) rather than a second mechanism. It
  should be decided alongside this document for two reasons: the handle is the
  prerequisite for both and neither is possible without it, and `join` adds the
  sixth blocked state §6.2 would otherwise be missing. If only one change is
  built, build the handle — `spawn` returning it is the part `cancel` and `join`
  share.

## 12. Success criterion

Not "Nodus has cancellation". Three concrete statements, each falsifiable:

1. A coroutine blocked on a slow agent call can be abandoned by the program that
   spawned it, with its `finally` blocks run and its `catch` blocks skipped.
2. A workflow run in flight can be stopped by its host, and reports a status that
   is neither `completed` nor `failed`.
3. The documentation states the worker-pool model plainly, and no document claims
   or implies structured concurrency.

(1) and (2) need a regression test that asserts on the *unwind path taken*, not
only on the observable result — a behavioural test passes if a second, parallel
cancellation mechanism is introduced, which is the outcome §3 exists to prevent.
