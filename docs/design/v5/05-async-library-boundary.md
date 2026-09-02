# The async library boundary — design for #157

> **The verb is `wait`, not `join`.** Renamed during the build: `join`
> collides with `std:strings.join` and `std:path.join`, and a builtin
> silently shadows an explicit named import (#680). Substitute `wait` for
> `join` throughout this document; the semantics are unchanged. See
> `06-task-handle.md` §2a.

**Status: proposal, except the handle — decided in `06-task-handle.md`.**
Nothing is built. Written in the shape `04-cancellation.md` uses, and **jointly
decided with it**: the object `join` acts on is the one #395 also needs, and the
two issues were decided together rather than sequenced (§7). Read
`06-task-handle.md` for that decision; this document is the design record for
`join`'s own semantics.

**Everything in §2 was measured by running it** against `main` at `4e8f528`
(5.7.1 dev source), not read out of the issue. That matters more than usual here,
because **three of #157's factual claims are now false** — §3. The gap is real,
but it is not the gap the issue describes, and the fix that follows from the
measured behaviour is not the fix the issue proposes.

---

## 1. What #157 asked

> *"A library function cannot start a background task and return a value from it
> in one call. The library can `spawn()` internally and return a channel, but the
> caller must then call `run_loop()` before `recv()`-ing the result. There is no
> way for the library to signal 'this call requires the scheduler to run,' and
> calling `run_loop()` inside the library function itself doesn't help — the
> spawned coroutine needs the caller's scheduler turn."*

Three options are floated: a `run_until(ch)` helper, a task record with an
`.await()` method, or first-class `async fn` syntax.

## 2. What actually happens now — nine programs, run

Every row was executed. `L` marks a real cross-module `import`, not a same-file
function.

| # | Program | Result |
|---|---|---|
| 1 | the issue's repro verbatim, top level | **fails fast** — `recv(channel) outside coroutine — wrap your code in spawn(coroutine(fn() { ... })) and call run_loop()` |
| 2 | `let ch = start_worker(); run_loop(); recv(ch)` | **works** → `42` |
| 3 | caller wraps its `recv` in a coroutine, then `run_loop()` | **works** → `42` |
| 4 | `L` caller drives: `lib.start_worker()`, `run_loop()`, `recv(ch)` | **works** → `42` |
| 5 | `L` **library drives its own loop and returns the value in one call** | **works** → `99` |
| 6 | the issue's repro verbatim, **inside a workflow step** | **works** → `{"a": 42}` |
| 7 | inside a step, worker `sleep`s, step calls `run_loop()` | **works** → `{"a": 7}` |
| 8 | `L` library's internal `run_loop()` while the caller has an undriven coroutine | **works, and runs the caller's unrelated coroutine** — §4 |
| 9 | `L` caller never drives at all | **silent** — exit 0, no output, no warning, work dropped |

Row 2 is the one that reframes the issue. `builtin_recv`
(`builtins/coroutine.py:267`) returns from a non-empty queue **before** it checks
for a current coroutine — the "outside coroutine" error at line 290 is reachable
only when the channel is empty and open. So a top-level `recv` on a channel a
completed worker already sent to is legal today.

Row 6 is the second. A step body is itself a coroutine (I-WFLOW-03) driven by the
graph runner, so **the issue's exact repro, unmodified, works inside a workflow
step.** It fails only at module top level, which is the one context where nothing
drives the scheduler.

Row 5 is the third, and it contradicts the issue directly. §3.

## 3. Three claims in #157 that are no longer true

Stated plainly, because the issue is the register and a design built on its
premises would be designing for a runtime we do not have.

| #157 says | Measured |
|---|---|
| *"calling `run_loop()` inside the library function itself doesn't help — the spawned coroutine needs the caller's scheduler turn"* | **False.** Row 5 returns `99`. #339's `owner_vm` (`builtins/coroutine.py:132`) resumes a coroutine on the VM that spawned it, and the module VM shares the caller's scheduler, so a library's own `run_loop()` drives its own spawn. |
| *"blocks forever outside coroutine, or never runs"* | **Neither.** It raises immediately, and the message names the fix. |
| *"A library function cannot start a background task and return a value from it in one call"* | **False as written** — row 5 is exactly that call. It is *unsafe* rather than impossible, which is a different problem with a different fix (§4). |

A fourth, from the issue's most recent comment (2026-08-30): the repro *"now
fails fast with `Task yielded during graph execution`."* At top level it does
not — it fails with the `recv` message in row 1. That error is raised by
`run_closure` (`vm/vm.py:3072`) when a closure entered through a **nested execute
loop** yields, which is a third context: not top level, not a scheduled
coroutine. I could not reach it from the issue's repro in any of the six
arrangements above, so I am recording the discrepancy rather than resolving it —
the comment's exact script is not in the issue.

**None of this makes #157 invalid.** It relocates it.

## 4. The real gap: a library cannot require the scheduler without taking it

Row 8 is the defect, and it is worse than the one the issue describes because it
is silent.

```
spawn(coroutine(fn() { print("unrelated caller coroutine ran") }))
print("before lib call")
let v = lib.start_and_drive()      // library calls run_loop() internally
print("lib returned \(v)")
run_loop()                          // the caller's own, deliberate, later
```

```
before lib call
unrelated caller coroutine ran      <- ran here, inside the library call
lib returned 99
```

`run_loop` (`builtins/coroutine.py:136`) drains the scheduler's entire ready
deque. It is not "the library's loop" — there is one scheduler per VM chain, and
a library that calls `run_loop()` **runs every coroutine the caller has spawned
and not yet driven**, at a point the caller did not choose, with no diagnostic.

So the honest statement of the gap is not *"a library cannot return a value"*. It
is:

> **A library that needs the scheduler has only one way to get it, and that way
> takes the whole scheduler and runs the caller's unrelated work. The caller
> cannot tell that it happened, and the library cannot ask for less.**

There is also no reentrancy guard: `run_loop` has no `_in_run_loop` flag, and a
nested `run_loop()` called from inside a coroutine that the outer `run_loop()` is
currently driving returns normally (measured). That is unguarded reentrancy into
the scheduler, not a designed nesting.

And row 9 is the other half: forgetting to drive is **silent at the CLI**. §6.

## 5. The fork

| | A: convention only | B: a task handle with `join` | C: `async fn` syntax |
|---|---|---|---|
| Shape | document "libraries return channels, never call `run_loop`" | `spawn` returns a handle; `join(t)` drives until *that* task settles | a keyword marking functions that need the scheduler |
| New concepts | none | one verb on the value `coroutine(...)` already returns | a colour in the type system |
| Fixes row 8 (scheduler theft) | no — it asks people to remember | **partly** — bounded drive, honest residue in §6.3 | no, by itself |
| Fixes row 9 (silent drop) | no | no | **yes** — the compiler could reject an undriven `async` call |
| Returns a value without a channel | no | **yes** — `last_result` already exists | yes |
| Cost | zero | one builtin | function colouring, everywhere, forever |

### 5.1 Recommendation: B. Not C, and not A alone.

**C is rejected on the domain statement's own two-part rule**
(`00-domain-statement.md §3`). Test 1 passes: forgetting to drive the scheduler
breaks *bounded* — the work silently does not happen (row 9). Test 2 is where it
fails, and it fails on a detail worth stating: the compiler cannot know whether a
call needs the scheduler, because **`spawn` is a runtime act inside an ordinary
function**, reachable through a value, a container, a conditional, or another
module. Marking it would mean colouring every function that transitively might
spawn — which is the `async` colouring problem, imported into a language whose
concurrency is otherwise uncoloured, to enforce a property the runtime can
already observe *exactly* at the moment it matters (`_spawned_without_loop` is
that observation, and it is already counted — `runtime/scheduler.py:53, 109`).

A property the runtime measures precisely does not need a type-system
approximation. That is the argument, and it is the same one `04-cancellation.md
§4.1` used to reject a nursery: not "this is too big" but "the thing it would
enforce is already enforced somewhere better".

**A is necessary but insufficient** — it is a rule with nothing behind it, and
this codebase's own history is that a convention with no mechanism is a defect
waiting for its first new consumer. Ship it *with* B, as the documented use of B.

## 6. What B looks like

### 6.1 One handle, two verbs

**Decided (`06-task-handle.md` D1): the handle is the coroutine value the
program already holds.** Both this document and `04 §5.1` originally proposed a
record `{ id, name, state }`; that was withdrawn, because a record is a *value*
and `state` would freeze at spawn time, and because `coroutine_status(c)` was
measured tracking a live coroutine across the spawn and the loop. So **no new
value type** — one more verb on the object `coroutine(...)` already returns:

```
let t = spawn(coroutine(fn() { return expensive() }))
let v = join(t)        // drive until t settles; return its value
```

`join` needs no new runtime state: `Coroutine.last_result`
(`runtime/coroutine.py:43`) is already set on return
(`builtins/coroutine.py:102`) and already read by the graph runner
(`orchestration/task_graph.py:2180`). **The value channel that #157 works around
already exists** — it is just not reachable from a program, because `spawn`
returns `None` (`builtins/coroutine.py:134`).

That is the finding that makes this small: `spawn` throwing away its handle is
the whole of #157's mechanical cause. A channel is the workaround for a missing
return value, and it is why the issue is phrased in terms of channels at all.

### 6.2 The library rule this makes enforceable-in-review

> **A library function returns a handle. It does not call `run_loop()`.**

With `join` available, this rule costs the library nothing — it hands back
something the caller can drive at a moment of the caller's choosing. Without
`join`, the rule is unaffordable, which is why row 5 exists and why people write
it.

### 6.3 `join`'s two contexts, and the residue

| Caller is | `join(t)` should | Why |
|---|---|---|
| inside a coroutine | **suspend**, like `recv` — park on `t`, resume when it settles | there is a coroutine to suspend; no reentrancy, no theft |
| at top level | **drive** the scheduler until `t` settles, then return | there is nothing to suspend; this is the only option |

The top-level case still runs other coroutines — a task can depend on its
siblings, so refusing to run them would deadlock `join` on a queue it declined to
drain. **The residue, stated rather than hidden: top-level `join` is a bounded
drive, not an isolated one.** What it fixes is the *stopping* condition — it
returns when `t` settles instead of when the entire deque empties, so the
caller's unrelated long-running work is no longer run to completion inside
someone else's function call. That is strictly better than row 8 and it is not a
guarantee of isolation, and the docs should say the second part.

### 6.4 What `join` does with a failed task

The one genuinely new semantic question, and the place this touches #395's
deliberate non-goal.

`04-cancellation.md §6.4` says there is no propagation because there is no
parent. That stays true for `spawn`. But **`join` is an explicit request for the
outcome**, which is exactly the condition under which propagation is
well-defined.

**Recommendation: `join` raises the task's error into the joiner**, and that
error is then *not* also drained into `scheduler._coroutine_errors` — a joined
failure is reported once, to the code that asked. An unjoined failure keeps
today's behaviour exactly (stderr trace, scheduler list, `run_loop()`'s return
value, siblings unaffected, exit 0).

This would be the **first error-propagation path in the language**, so it needs
saying out loud rather than arriving as a side effect: it does not make Nodus
structurally concurrent, because it propagates only where a program explicitly
asked, and only to the asker.

### 6.5 Joining twice, joining a finished task, joining a cancelled one

- **finished** — returns `last_result` immediately, drives nothing. Cheap and
  useful: it makes `join` safe in a loop.
- **twice** — same value again. `last_result` persists; there is no consumption.
- **cancelled** (#395) — raises the cancellation error, on the §6.4 rule. A
  cancelled task did not produce a value and must not appear to.
- **never spawned** — an error, unlike `cancel`'s no-op (`04-cancellation.md
  §6.3`). The asymmetry is deliberate: a cancel usually cannot know the target's
  state, but a `join` is asking for a value and there is no value to invent.

## 7. Why this had to be decided with #395, not after it — **and was**

The #157 comment that prompted this doc said the two issues want the same handle.
They do, and there is a sharper reason not to sequence them. **This is settled:
`06-task-handle.md` decides both, and D4/D5 are the mechanism.** The argument is
kept here because it is the reason that decision exists:

**`join` adds a sixth blocked state, and `04-cancellation.md §6.2` enumerates
five.** That table — ready deque, timer heap, channel waiter, host agent call,
other blocking builtin — is the part of the cancellation design that exists
specifically to stop a cancel from handling some blocked states and not others.
A coroutine parked in `join` (§6.3, row 1) is a sixth:

| State | How it is woken | On cancel |
|---|---|---|
| blocked on `join(t)` (`blocked_reason = "task_join"`) | `t` settles | clear `blocked_on`, drop from `t`'s joiner list, unwind. **Cancelling a joiner does not cancel `t`** — no parent link is created by joining. |

If `join` ships after `cancel`, that table is incomplete on the day it lands, and
it is incomplete in precisely the way `04-cancellation.md §2.4` and §6.2 were
written to prevent. **This is the recurring shape arriving by scheduling rather
than by oversight** — the enumeration is correct when written and a later feature
adds a member. The mitigation is the one CLAUDE.md prescribes: name the set once.
`blocked_reason` should become a named tuple that both the cancel path and any
new blocking builtin drive off, so a seventh state fails the suite.

**Recommended sequencing:** decide both now; if only one is built, build the
handle (`spawn` returns it) as its own change, since `cancel` and `join` both
sit on it and neither is possible without it.

## 8. A one-path diagnostic, found while measuring

Row 9 — spawn, never drive — behaves differently depending on which door the
program came through. Same file, same runtime:

```
$ nodus run drop.nd
caller forgot to drive the scheduler
=== exit: 0 ===                                   <- no warning

>>> NodusRuntime().run_file("drop.nd")
stderr: 'Warning: 1 spawned task never executed — call run_loop() after spawn() to run them.'
```

> **Fixed (#675).** The transcript above is the pre-fix behaviour, kept because
> it is the evidence. `Scheduler.unrun_task_warning()` is now the one place that
> decides, and both doors ask it — `nodus run` prints the identical sentence, and
> a test asserts the two are *equal* rather than merely both non-empty. Row 9's
> silence is closed.

The warning used to be built in `runtime/embedding.py` and read
`scheduler._spawned_without_loop`. The CLI builds a `VM` directly and never
constructs a `NodusRuntime`, so it never reached that code — the same structural
split CLAUDE.md documents for deny-by-default, but here it was a **diagnostic**,
where the split has no justification. The deny-by-default asymmetry is a decision
about authority over unauthored work; a warning that the work you spawned never
ran is useful to exactly the same degree in both.

This was the recurring bug shape, found by running one program two ways, and it
was **not** part of this proposal — it was worth fixing whether or not any of §6
is built, because it was the only thing standing between a user and row 9's
silence.

## 9. What this does not do

- **Does not add `async fn` or any keyword.** §5.1.
- **Does not make top-level `join` isolated.** It bounds when the drive stops,
  not what it runs. §6.3.
- **Does not create a parent/child relationship.** Joining is a read, not
  adoption; cancelling a joiner does not cancel the joined. §7.
- **Does not add automatic error propagation.** Only `join` propagates, only to
  the caller that asked. §6.4.
- **Does not guard scheduler reentrancy.** A library that ignores §6.2 and calls
  `run_loop()` anyway still can. Making that an error is a separate decision
  (§10.2).
- **Does not change channels.** They remain the right tool for streams; `join` is
  for the single-value case they were being conscripted into.

## 10. Open decisions, with recommendations

### 10.1 Does `join` take a timeout?

**Recommendation: no, not in the first change.** `coroutine_timeout_ms` already
bounds the joined task, so a join cannot outlive it. A second bound on the same
question is the shape `04-cancellation.md §10.4` rejected for the unwind budget.

### 10.2 Should `run_loop()` inside a library become an error?

**Recommendation: no — a warning, and only once `join` exists.** It is legal
today, row 5 works, and code in the wild does it. Deprecating a working pattern
before its replacement ships is how a convention becomes a broken promise.
Revisit at 6.0.0, alongside the staging cohort.

### 10.3 Does `join` accept a list of handles?

**Recommendation: yes, and it is the shape most callers want** — `join([t1, t2])`
returning a list drives once to a joint settle instead of serialising two drives.
It also removes the last honest reason to reach for `run_loop()` directly. Low
cost given §6.3's mechanics, but it should be specified explicitly rather than
falling out, because the failure semantics of a partial failure (§6.4) need
deciding for the list case: **recommendation, raise on the first failure, after
all of them have settled** — not first-failure-stops, which would be a nursery,
which §4.1 of the cancellation doc rejects.

### 10.4 Is the handle guest-forgeable? — **dissolved, not answered**

This asked how to stop `join({id: 3i})` reading a task the program never
spawned. The question existed **only because the handle was proposed as a
record**, and records are constructible by any guest.

With `06-task-handle.md` D1 the handle is the coroutine value, and
`ensure_coroutine` (`vm/vm.py:979`) is an identity check — `isinstance(value,
Coroutine)`. Measured: `coroutine_status({id: 1i, name: "worker", state:
"running"})` is refused today with *"expects a coroutine"*. A guest cannot
manufacture a coroutine it does not own.

Worth keeping as a record of the near-miss: the rejected design would have
**created** a forgery surface that the type it replaced did not have — the #411
lesson (a guarantee that trusts a name rather than a binding) arriving through a
convenience choice about handle shape.

## 11. Relationship to other work

- **#395 / `04-cancellation.md`** — supplies the handle. §7 is the coupling, and
  the sixth blocked state is the concrete reason to decide them together.
- **#339** (fixed 2026-08-15) built `owner_vm`, which is why row 5 works and why
  the issue's third claim is stale.
- **#502** built the unwind that a cancelled joiner would travel through.
- **#411** is the precedent for §10.4.
- **#424** bounds what any of this can promise about host work.

## 12. Success criterion

Not "Nodus has `join`". Four statements, each falsifiable:

1. A library function can start background work and hand back something the
   caller can wait on, **without calling `run_loop()`**, and a review can state
   that rule as a rule.
2. Calling that library function does not run the caller's unrelated coroutines
   to completion.
3. A coroutine parked in `join` is cancellable, and appears in the same
   enumeration every other blocked state does — asserted on the *set*, not on one
   member.
4. `nodus run` and `NodusRuntime.run_file` say the same thing about a spawned
   task that never ran (§8).

(3) needs a test that reads the named `blocked_reason` set, not a behavioural
test per state — a behavioural test passes with five of six handled, which is the
outcome §7 exists to prevent.
