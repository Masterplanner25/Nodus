# The task handle — joint decision for #395 and #157

**Status: DECIDED.** This document decides the part `04-cancellation.md` and
`05-async-library-boundary.md` share. Both remain the design record for their own
issue; where either describes the handle, **this document supersedes it** — see
§6.

The two issues could not be decided separately. #395 needs something to cancel,
#157 needs something to wait on, and both proposed inventing it. Deciding them in
sequence would have shipped the second one's blocked state into the first one's
already-frozen enumeration — the recurring shape arriving by scheduling rather
than by oversight (`04 §6.2`, `05 §7`).

**The decision is smaller than either proposal, because the handle already
exists.** §2.

---

## 1. What had to be decided

| | #395 wanted | #157 wanted |
|---|---|---|
| An object | something to name a running task | something to wait on |
| A verb | `cancel` | `join` |
| Proposed shape | a record `{ id, name, state }` (`04 §5.1`) | the same record (`05 §6.1`) |

One object, two verbs, two documents each proposing the object. That is the
decision.

## 2. The finding: the handle already exists, and the proposed one was wrong

Measured against `main` at `4e8f528`:

```
let c = coroutine(fn() { sleep(5i); return 77i })
print("before spawn: \(coroutine_status(c))")   // created
spawn(c)
print("after spawn:  \(coroutine_status(c))")   // created
run_loop()
print("after loop:   \(coroutine_status(c))")   // finished
```

**`c` is a live handle already.** It tracks state across the spawn and across the
loop, and `coroutine_status` reads it. The program is *already required* to hold
it — CLAUDE.md's own idiom is `let c = coroutine(fn() {...})` then `spawn(c)`,
because `spawn` takes a coroutine value and not a function literal.

The record both documents proposed was wrong on two counts, and the first would
have shipped:

1. **A record is a value, so `state` would freeze at spawn time.** `{ id: 3i,
   name: "worker", state: "running" }` handed back by `spawn` is a snapshot;
   `t.state` would read `"created"` forever while the task ran and finished. A
   handle whose most-read field is permanently stale is worse than no handle.
2. **It is unnecessary, and it would have been forgeable.** `ensure_coroutine`
   (`vm/vm.py:979`) is an identity check — `isinstance(value, Coroutine)` — so a
   coroutine value cannot be counterfeited by a guest, while a record trivially
   can: `coroutine_status({id: 1i, ...})` is refused today with a type error. The
   record proposal would have *created* the forgery question that `05 §10.4`
   then had to answer.

So the object does not need designing. It needs two verbs and one exposure.

## 3. Decisions

### D1 — No new value type. The coroutine value is the task handle.

`cancel(c)` and `join(c)` take a coroutine, validated by the existing
`ensure_coroutine`. No record, no opaque wrapper, no new type.

Consequences: `04 §5.1`'s record shape is withdrawn. `05 §10.4` (is the handle
guest-forgeable?) is **dissolved rather than answered** — unforgeability is a
property of the type that already exists.

### D2 — `spawn(c)` returns `c`.

Today it returns `None` (`builtins/coroutine.py:134`). It returns its argument
instead, so the one-line form composes:

```
let t = spawn(coroutine(fn() { return expensive() }))
let v = join(t)
```

This is **convenience, not mechanism** — D1 means every program can already reach
its handle. That makes D2 severable and low-risk, and it is the only
externally-visible behaviour change in this decision: `nil` → a coroutine.
Practically unobservable (nothing can be done with `nil`), but it is a change to
a returned value and gets a CHANGELOG entry saying so.

### D3 — Two verbs on one object, and no third.

`cancel(c)` — #395. `join(c)` — #157. Both route through machinery that exists:
`cancel` through `unwind_cancelled_coroutine` (#502), `join` through
`Coroutine.last_result`, which is already set on return
(`builtins/coroutine.py:102`) and already read by the graph runner
(`orchestration/task_graph.py:2180`) but is not reachable from a program.

**`last_result` gets no separate accessor.** `join` is the only way to read it —
a `task_result(c)` alongside `join(c)` would be two answers to "what did this
produce", differing only in whether they drive the scheduler, which is the shape.

### D4 — `blocked_reason` becomes a named set, in whichever change lands first.

This is the anti-drift mechanism and the reason the two issues are one decision.
`04 §6.2` enumerates five blocked states; `join` adds a sixth (`task_join`).
Rather than let the second change edit the first change's table, the set is named
once and both the cancel path and every blocking builtin drive off it, so a
seventh state fails the suite instead of being silently unhandled.

**D4 is not optional and not deferrable.** It ships with the first of the two
verbs even if the other is months later. It is the entire reason this document
exists.

### D5 — Both verbs ship in one change.

Not sequenced. The handle (D1/D2) plus `cancel` plus `join` plus the named set,
as one unit.

Splitting them re-creates exactly the hazard that made the joint decision
necessary. If external pressure forces a split, the only permitted order is
**handle + D4's named set first**, then either verb — never a verb before the
set.

### D6 — `join` raises the task's failure into the joiner.

The one decision here with language-identity weight, so it is stated as such:
**this is the first error-propagation path in Nodus.**

It does not contradict `04 §6.4`'s "no propagation, there is no parent". Nothing
propagates from a `spawn`. Propagation happens only where a program explicitly
asked for an outcome, and only to the code that asked. A joined failure is
reported **once** — to the joiner, not also into `scheduler._coroutine_errors`.
An unjoined failure keeps today's behaviour exactly: stderr trace, scheduler
list, `run_loop()`'s return value, siblings unaffected, exit 0.

This does not make Nodus structurally concurrent. There is still no parent link,
no scope, and no automatic propagation — cancelling a joiner does not cancel the
joined.

### D7 — No language surface for either verb.

Builtins only. `04 §5.4` decided this for `cancel` (a scope construct was the
only thing that would justify syntax, and `04 §4.1` rejected it); `05 §5.1`
decided it for `join` (`async fn` fails the domain statement's test 2, because
`spawn` is a runtime act and marking it means colouring every function that
might transitively spawn). Restated jointly so neither is reopened alone.

### D8 — `join`'s two contexts stand as `05 §6.3` specifies, residue included.

Inside a coroutine, `join` **suspends** (parks on `t`, `blocked_reason =
"task_join"`). At top level it **drives** the scheduler until `t` settles.

The residue is accepted, not fixed: top-level `join` is a *bounded* drive, not an
isolated one — it must run other coroutines, since a task can depend on its
siblings. What it fixes is the stopping condition. That is strictly better than
today's scheduler theft (`05 §4`) and it is not isolation, and the documentation
says the second half.

## 4. What is rejected

| Rejected | Where argued | One-line reason |
|---|---|---|
| A record handle | §2 | `state` freezes at spawn; creates a forgery question the coroutine type does not have |
| A separate `task_result(c)` | D3 | two answers to one question |
| `async fn` / function colouring | `05 §5.1` | the compiler cannot know a call spawns; `_spawned_without_loop` already measures it exactly |
| A nursery / scope construct | `04 §4.1` | competes with the workflow DSL, which already has bounded fan-out and `allow_failure` |
| Automatic child→parent propagation | D6 | there is no parent; `join` is a request, not adoption |
| Sequencing the two issues | D4, D5 | the second's blocked state lands in the first's frozen table |

## 5. What must be true when this is built

Falsifiable, and assert on the source where a behavioural test would pass on a
partial implementation:

1. `cancel(c)` and `join(c)` accept the value `coroutine(...)` returned, and
   refuse a record — one test, both verbs.
2. A coroutine parked in `join` is cancellable, and the test reads the **named
   set** of blocked reasons rather than enumerating states by hand. A test that
   checks five of six passes today and is the thing D4 exists to prevent.
3. A library function starts background work, returns a handle, never calls
   `run_loop()`, and does not run the caller's unrelated coroutines to
   completion.
4. An unjoined failure's observable behaviour is byte-identical to today's;
   a joined failure is reported once.
5. `spawn` returns its argument, and no caller depends on the old `nil`.

## 6. Precedence

Where `04-cancellation.md` or `05-async-library-boundary.md` describes the handle
object, its shape, or the sequencing of the two changes, **this document wins**.
Each of those keeps sole authority over its own issue's semantics: `04` for what
cancellation means in each blocked state, run-level cancellation, and the eighth
run state; `05` for `join`'s contexts, its failed/finished/twice cases, and the
library rule.

Both are otherwise unchanged and remain proposals for the code that implements
them.
