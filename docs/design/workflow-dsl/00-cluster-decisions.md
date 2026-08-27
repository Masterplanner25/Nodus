# The workflow DSL cluster: eight decisions

**Status: decided 2026-08-26.** Covers #468, #472, #479, #480, #481, #488, #577,
#578 — every open design question against the workflow DSL. Each was filed
separately, from a different corpus, against v5.0.4. Read side by side at 5.5.0
they constrain each other, and three of them stop being independent.

This directory is not version-pinned because the cluster is not: most of what
follows is additive and lands across 5.x minors, and exactly one member joins
the 6.0.0 cohort already holding #545 and #547.

## Re-verification first

The eight issues were written against v5.0.4 and cite line numbers from it. Every
claim below was re-executed against `src/` at 5.5.0 before any decision was made.
Outputs in this document are pasted from those runs.

Still true, unchanged:

| # | Claim | Verified at 5.5.0 |
|---|---|---|
| 481 | `workflow build(mode) { ... }` is a syntax error | `Expected '{', got '('` |
| 488 | `budget` vocabulary is closed, both keys required | `Unsupported budget option: max_cost_usd`; `goal budget must set 'deadline_ms'` |
| 479 | a step declares no output type | `Unsupported workflow step option: returns` |
| 479 | the compiler discards type annotations | no `type_hint` reaches bytecode; the four `compiler.py` hits are AST→AST annotation lowerings that merely preserve the field |
| 479 | `after` carries the dependency's value, with correct scoping | `dep value -> {"rows": 42}`; an undeclared read is `Undefined variable: a` |
| 577 | `run_workflow` returns rather than throws, `steps` holds completed work | `steps: {"reserve": "res-1"}`, `statuses: {..., "charge": "failed", "ship": "upstream_failed"}` |
| 468 | there is no status between `completed` and `failed` | 7 run statuses, 7 task statuses, still disjoint vocabularies |

Two corrections to the issues as filed:

- **#472 says `workflow_wait` "already takes up to 4 arguments, so there is a slot
  for an options map without a signature break."** All four slots are occupied —
  `builtin_workflow_wait(event_type, correlation_key, payload, deadline_ms)`
  (`vm.py:1962`). There is no free slot. See D3 for what to do instead.
- **#480's prerequisite is discharged.** It says "ordering suggestion: #470 first";
  #470 shipped in PR #563, so every run now records `workflow_topology` and a
  resume refuses a rebuilt graph whose structure drifted. That mechanism is the
  one D5 rides.

And one new fact that no issue records, found while probing #479:

**A skipped dependency binds as `nil`, indistinguishable from a step that returned
`nil`.**

```
a -> nil
statuses: {"gate": "completed", "a": "skipped", "b": "completed"}
steps:    {"gate": 1, "b": 0}
```

`steps` omits the skipped step entirely; only `statuses` can tell the two apart.
This is the concrete form of the question Dagster's `Nothing` type exists to
answer, and it bears on D2.

## The finding that re-orders the cluster

**The static type vocabulary is unsound, and three of the eight issues want to
build on it.**

`parse_type_name` (`frontend/parser.py:1282`) is `return self.eat("ID").val` — it
accepts any identifier. `type_system.parse_type_name` then does
`TYPE_NAMES.get(name, ANY)`. So an unrecognised type name silently means `any`,
with no diagnostic at any altitude:

```
fn a(name: string) -> string { return name }
fn b(name: strng)  -> string { return name }
fn main() { print(a(42i)); print(b(42i)) }
```
```
$ nodus check typo.nd
Type error at typo.nd:3:21: expected string but got int
```

One error, for `a`. The call to `b` passes, because one transposed letter turned
its parameter into `any`. Three consequences:

1. **A typo silently disables checking on that parameter**, forever, with nothing
   reporting it.
2. **`map` is unnameable and looks nameable.** It is not in `TYPE_NAMES`, so
   `fn g(y: map) -> map` checks clean and means `any` — and `map` is what
   `run_workflow`, `plan_workflow` and most step bodies actually return.
3. **`record` is in `TYPE_NAMES` but is unspellable.** It is a keyword, so
   `fn h() -> record` is `Expected identifier, got 'record'`. A dead entry.

This is the codebase's own "declared but not enforced" shape — the family of
#467 (`FS_READ` unattached), #473, #478 (`SyscallSpec.capability` inert) and #492
(`worker:` a label) — sitting at the annotation surface, which is the one surface
three of these issues propose to route the DSL through.

**Nothing typed should be added to the workflow DSL until this is fixed.** A
`returns: "recrod"` that silently means "any type at all" would be a new instance
of the shape the last three releases were spent removing. Filed as **#609**;
see D1.

## The three groups

Sorting the eight by what they are actually about:

**A — the DSL cannot say what a thing is.** #479 (step output, tool schema), #472
(resume payload), #481 (workflow entry). Three boundaries, one missing
vocabulary. #479's own closing comment says the vocabulary question "is now the
*only* one" left in it.

**B — the graph does not know what it ran.** #480 (runtime fan-out), #468
(partial success), #578 (barrier cells). All three want the run record to carry
structure the source does not have, and all three cite #470's `workflow_topology`
as the precedent.

**C — the run has no declared end.** #577 (compensation). #488 (budget) sits
beside it: both are about bounding or unwinding a run from outside its steps.

The interesting collapse is in group B, and it is D6.

---

## D1 — Prerequisite: make the type vocabulary sound (#609) — **SHIPPED**

**Decision: an unrecognised type name becomes an error. `map` is added.
`record` is either made spellable or removed from the table.**

**Built 2026-08-26.** Warning in `nodus check` and inline in the editor;
error at 6.0.0. `map` and `nil` added, `record` made spellable — both are
keywords and never reached the lookup. `map` and `record` are mutually
assignable, because the analyzer infers `record` for both literal forms.
Validation lives in `parser.parse_type_name`, and both consumers read its
list rather than each deciding; `tests/closed_issues/issue_609.py` asserts
they agree. **D2's step half, D3 and D4's typed parameters are unblocked.**

Staged the way #545 and #547 are staged: a one-time warning in the next 5.x
release, an error at 6.0.0. It is breaking — code that checks clean today would
stop — so it joins the 6.0.0 cohort, which currently has two members.

`nodus check` gains the diagnostic, with the close-match suggestion `nodus.toml`
already produces for an unknown key (#490): `unknown type name 'strng' — did you
mean 'string'?`

Why this and not "just document it": every other member of the declared-but-inert
family was fixed by making the declaration bind, not by writing the gap down. And
this one is the load-bearing prerequisite for D2, D3 and D4's typed halves.

**Not decided here:** whether the vocabulary grows structure (`list<T>`, record
shapes). It stays flat. Everything below works at the flat altitude, and anything
finer is a separate and much larger decision — #479's own comment says so.

## D2 — #479: split. Schema-from-signature ships first; `returns:` waits for D1 — **BOTH RESOLVED**

**Built 2026-08-26, and the split was right for a reason neither half predicted.**

`returns:` shipped as decided: checked by setting the analyzer's `current_return`
for the step body walk, unknown type names refused outright (an error, not #609's
warning, since the option is new). The sub-decision below is answered — **it
describes the step, not the edge**: a skipped producer still binds `nil`, because
that is the edge's behaviour and `on: ["skipped"]` is how a dependent opts into
it. `returns:` does not imply nullable.

**The schema half is not implementable as specified**, and building it is what
showed why. A tool handler takes exactly one argument — the args record — so the
`schema` names *that record's keys*, which a signature cannot carry. #479's own
example registered fine and died on invoke; that is #624. What the signature
genuinely says is **arity**, and that was the field going unchecked, so
`tool.register` refuses a handler it could never invoke. The issue's premise held
exactly; the field was different.

**Decision: `tool.register` derives its `schema`/`returns_schema` from the
handler's signature when none is given, and reports a mismatch when one is. A
step's `returns:` is deferred until D1 lands.**

The two halves of #479 have different prerequisites, and separating them is the
whole value of looking at it now:

- **The tool half needs only the derivation.** Its target dialect already exists,
  is already enforced, and already has good errors — `tool.register` normalises a
  declaration into `{"type": "object", "properties": {…}, "required": [...]}` and
  rejects a wrong-typed argument with `Tool 'app.edit': schema validation failed:
  argument 'path' must be a string`. Nothing about it is hypothetical. The gap is
  only that the declaration and the handler are independent artifacts.
- **The step half needs D1**, because `returns:` is a bare type name and a bare
  type name currently means nothing when misspelled.

And the derivation is the forcing function for D1: **deriving a schema from an
unknown type name must refuse, because a schema has no honest way to say
"any".** So `tool.register(handler: f)` where `f` takes `x: strng` fails at
registration with the type-name diagnostic — which surfaces the D1 defect at the
one surface that cannot paper over it. That is why this half goes first rather
than waiting.

**Sub-decision: two vocabularies, one bridge — deliberately not unified.** The
static annotations are the *source*; the schema map is the *derived artifact* at
boundaries that cross a process. They are different things: one is flat and
compile-time, the other structural and runtime, and `nodus_lang_schema` already
implements the second. Collapsing them into one vocabulary is the trap in this
cluster — it reads as tidiness and would force either the annotations to grow a
structural type system or the schemas to shrink to eight flat names.

**Sub-decision: `returns:` must say what a skipped step carries.** Given the
finding above, a typed edge whose producer was skipped delivers `nil`. Either
`returns:` implies nullable, or a skipped producer must be unreadable rather than
`nil`. Answer when `returns:` is built; recorded here so it is not discovered
then.

## D3 — #472: the wait payload uses the schema dialect, and arg 2 becomes an options map

**Decision: `workflow_wait` accepts an options map in argument 2, carrying every
option including `schema`. A declared schema is checked in `resume_workflow`
before the step is resumed, refused the way an `event_type` mismatch already is.**

The payload crosses a process boundary — a resume arrives from the CLI, HTTP, or
another process — so it needs the runtime structural schema of D2's second
vocabulary, not a flat type name. `nodus_lang_schema.validate_payload` exists for
exactly this.

**On the signature.** #472 assumed a free slot; there is none. Rather than adding
a fifth positional argument, argument 2 type-dispatches: a **string** is
`correlation_key`, as today; a **map** is an options map carrying
`correlation_key`, `payload`, `deadline_ms` and `schema`.

```
workflow_wait("approval", {schema: {approved: "bool", note: "string"}})
workflow_wait("approval", "order-42")          // unchanged
```

Fully additive, and it caps positional growth — the current signature is one
option away from being unwritable, and the next option after `schema` would have
made it so regardless.

**Sub-decisions:** an unspecified schema accepts anything (compatible, and the
issue's own preferred reading). A mismatch surfaces at the resume call as
`{"ok": false, "error": "..."}`, so the failure lands on the caller that sent the
wrong thing rather than inside the step that trusted it. Copy the refusal shape
from `runner.resume_workflow`'s existing event-type mismatch.

## D4 — #481: `workflow name(params)`, invoked through `run_workflow`, not through the flow value

**Decision: parameters are declared on the workflow and bound at
`run_workflow(flow, args_map)`. Bound arguments are persisted into run metadata
and validated on resume by #470's mechanism. Types on parameters wait for D1.**

```
workflow build(mode) {
    step a { return mode }
}

run_workflow(build, {mode: "lite"})
```

**This differs from the issue's sketch, which proposes `run_workflow(build("lite"))`.**
The flow value is a `MapLit` — `lower_workflow_ast` returns one — so `build("lite")`
is a call on a map, which is new syntax on a value whose shape #394 has just
finished pinning. The second-argument form needs none of that: `run_workflow`
already takes one argument and extending its arity is routine, the arguments are
named rather than positional (better for a workflow with several), and the map is
already in the shape that gets persisted, with no conversion step.

The declaration still carries the parameter list, so an unknown or missing
argument is an error rather than a silent `nil`.

**Sub-decision: arguments are part of run identity.** #470 shipped
`workflow_topology` in run metadata and a resume that refuses a drifted rebuild
with the real cause named. Arguments ride the same mechanism and reuse that
refusal message — a run resumed with different arguments is as wrong as one
resumed against different source, and the issue says so.

**Sub-decision: this supersedes the module-global workaround, and the workaround's
worst property is why.** Today `state chosen = mode` is durable and a bare `mode`
read inside a step is re-derived, and nothing marks which is which — so the
spelling silently decides whether the parameter survives a resume. A declared
parameter is durable by construction, which removes the choice rather than
documenting it.

## D5 — #480: adopt the mapped-node model. The graph does not grow

**Decision: a fan-out is a node declared in the source whose *cardinality* is
discovered at run time. The running graph never acquires undeclared nodes.**

This is Airflow's `.expand()` model, and #480's own second comment already
recommends it. It is the decision that makes the hard part tractable: the issue
identifies "expanded nodes exist in the run and not in the source, so a rebuild
from source cannot reconstruct them" as the blocker, and under this model they
*do* exist in the source — as one mapped node — with only their count in run
state. So #470's rebuild reconstructs the node and re-derives the indices from
durable data, instead of #470 having to grow into "persist an arbitrary graph".

Shape:

```
workflow pipeline {
    step plan { return ["a", "b", "c"] }
    step process each item in plan { return handle(item) }
    step collect after process { return len(process) }
}
```

`each item in plan` implies `after plan`. `steps["process"]` is the list of
results in index order.

**Sub-decision: the empty and non-list cases each get a status, because
"ran nothing, reported success" is the wrong default for a declared node with a
join behind it.** Following Airflow: a zero-length upstream makes the mapped node
`skipped`; a non-list or `nil` upstream makes it `upstream_failed`. Both statuses
already exist in `TASK_STATUSES` and both already propagate through `on:`. Today's
nearest analogue returns `{"tasks": {}, ..., "failed": []}` — defensible for a bare
`run_graph`, wrong for a declared fan-out.

**Sub-decision: re-expansion to a different cardinality is refused, not
reconciled.** Airflow needs a `REMOVED` state because it keeps instances as durable
rows; Nodus re-executes on resume (#486) and re-derives the list. A resume whose
producer yields a different length is topology drift, and #470 already refuses
topology drift with a message naming the real cause. Reusing that costs nothing
and avoids an eighth task status — which matters, because the vocabulary is named
once in `TASK_STATUSES` and pinned by `tests/test_status_vocabulary.py`.

**Sub-decision: expansion is bounded, and the bound is charged to the producer.**
Airflow's `max_map_length` defaults to 1024 and is checked when the upstream
pushes its value, failing with `unmappable_return_value_length` rather than
clamping in the scheduler afterwards. Copy both the bound and the placement.

**What this does not change.** Building a graph from runtime data already works —
`run_graph(tasks)` takes a program-constructed list and runs it concurrently, and
it works inside a workflow step. #501 has since made the resulting child run
attributable and cleanable (parent linkage, cascade cleanup). D5 is not about
gaining the capability; it is about the fan-out being *in the parent graph*
instead of beside it.

## D6 — #468 is subsumed by D5. Do not build a partial-success envelope

**Decision: close #468 as superseded. A mapped node is the partial-success
mechanism.**

Read next to #480, #468 is the same requirement at a finer granularity. Its
motivating complaint is that a retry re-runs work that already succeeded; #480's
motivating complaint is that an in-step loop makes "per-item retry, per-item
timeout and per-item caching all unavailable." Those are one requirement.

And the machinery already exists at the node level. `TaskNode` carries
`max_retries`, `retry_delay_ms`, `timeout_ms`, `cache`, `cache_key`, `on_states`,
`when` and `allow_failure` **per node**. A mapped node expanding to N instances
gets every one of them per item for free. "Retry only the two that failed" is then
the ordinary retry path, not a new concept — no eighth status, no envelope, no
second definition of what "done" means for `@exactly_once` to disagree with, which
#468 itself names as its hardest open question.

Below mapped-node granularity — three of five hunks inside one file edit — the
sub-unit is not worth a durable record, and the workaround stands: a step writes
its own progress into workflow `state` and skips completed units on resume. #468
says this "already works today," and D5 does not take it away.

**What would reopen this:** a case where the sub-units genuinely cannot be nodes
*and* the `state` workaround genuinely fails. Neither issue has produced one.

## D7 — #577: per-step `compensate_with`, not a workflow exit hook

**Decision: option 1 of the three the issue offers. Compensation is declared on
the step whose work it undoes, and the runtime runs the named steps for completed
work in reverse completion order when the run ends failed.**

```
step charge after reserve compensate_with refund { ... }
```

Why not the workflow-level exit hook (Argo's `spec.onExit`), and why not both:

- **The exit hook needs something Nodus deliberately does not have.** Argo's
  handler reads `workflow.status` and `workflow.failures`; a Nodus step has no way
  to ask how the run as a whole went, and giving it one is a larger change than
  compensation itself — it puts run-level state inside a step body, which is the
  direction every recent decision has moved away from.
- **The case only the hook covers is already served.** "Ends no step caused" —
  budget exhaustion, cancellation — reaches the *caller*, which gets the result
  map back rather than an exception. `run_workflow` returning on failure is
  deliberate and worth pinning as such: it is what makes caller-side handling
  possible, and "fixing" it toward throwing would break compensation.
- **Per-step is static and visible.** It reuses step declarations and shows up in
  `plan_workflow`, which is the property the task graph exists for.

**Sub-decisions:**

- **A tolerated failure does not unwind.** `allow_failure` (#475) means the run
  *completes*; a completed run has nothing to undo. The tolerated step's own
  partial effects are the author's business, and `on: ["failed"]` already lets a
  step react to them.
- **A failing compensation step is recorded and does not cascade.** It reports
  under a `compensation` key in the result; it does not re-trigger compensation
  and does not change the run's verdict, which is already `failed`.
- **A compensated run is terminal.** It cannot be resumed. This answers the
  issue's third sub-question — "compensation ran, then the run is resumed from a
  checkpoint: is the compensated work re-done?" — by removing the state rather
  than defining behaviour for it.
- **Ordering: after D5.** A mapped node's compensation unwinds per instance, so
  compensation needs the addressing D5 introduces. Building it first would mean
  building it twice.

Its stated prerequisite, #502 (`finally` not running for an abandoned step), is
closed, so compensation may be built on step bodies.

## D8 — #578: the conditional-writer question is answered; the barrier is deferred

**Decision on the question: a barrier cell's writers must write
unconditionally, checked at declaration. Decision on the feature: do not build it
yet.**

The issue asks its deciding question first, and it is the right one — a
conditional writer makes the writer set statically underivable, and the three
answers are a may-write analysis, a deadlock, or a refusal. **Refuse.** Two
shipped precedents do exactly this and are the message shape to copy: #500's
unconditional-checkpoint check for a goal's iteration, and `merge:` policy
validation. A third is adjacent — `when` guards already accept only
`reached("label")` predicates, so data-dependent branching is *already* routed
through checkpoints, and #500 already analyses whether a checkpoint is
unconditional. The analysis this needs has been written twice.

**The feature itself does not earn its place yet.** A barrier is a join whose
dependency is inferred from data flow rather than declared with `after`, and
`after` works, joins correctly, and now carries the dependency's value. The gain
is ergonomic; the cost is a second way to express a join, with a restriction
(unconditional writers only) that makes it strictly narrower than the spelling it
duplicates. Deferred until a case appears where the `after` spelling is genuinely
wrong rather than merely more verbose.

Recording the answer is the point: the question is settled, so it stops blocking
anything and does not need re-litigating when someone does find that case.

## D9 — #488: `budget` gains a nested `limits` map of host-registered meters

**Decision: `budget { max_iterations: N, deadline_ms: M, limits: { <meter>: <n> } }`.
The two existing dimensions become optional — at least one bound is required. The
parse-time vocabulary stays closed; `limits` is the one key whose contents are
resolved against the host.**

```
goal reach over tune {
    until reached("good_enough")
    budget { max_iterations: 5, limits: { tokens: 100000 } }
}
```

The issue's own analysis is right and is the constraint: **Nodus cannot measure
spend and should not learn how.** There is no model invocation anywhere in the
core — verified three times across the audit series — and that absence is
load-bearing, because it is what forces every semantic decision across a typed
boundary to a host handler. So `max_cost_usd` enforced by Nodus counting tokens is
not available, and a *named* cost dimension bakes in a unit Nodus cannot define.

The nesting is what keeps the good behaviour the issue explicitly praises. Today
an unknown budget key is rejected **at parse time** with an accurate message —
the opposite of the declared-but-inert pattern — and a flat open vocabulary would
have to move that check to run time to know what the host registered. `limits`
keeps the outer vocabulary closed and parse-checkable while making the open part
explicitly host-resolved.

**Sub-decisions:**

- **A declared meter with no accountant registered is an error, not silently
  unbounded** — the rule `CapabilityDecision` already applies to `ask` with no
  approval channel. Checked once before the first iteration, so it fails fast
  rather than after the spend.
- **Checked per-iteration**, at the point that already checks
  `iterations >= max_iterations`. The issue notes a single iteration can make many
  model calls, so a runaway pass is unbounded — that is true, and it is the same
  question open on the runtime side as per-syscall vs per-EU vs per-tenant. Nodus
  owns the loop-altitude bound; the call-altitude bound belongs to the host that
  owns the meter.
- **Breach returns `goal_error` with `category: "budget_exhausted"`** and the
  breached meter named, matching `max_iterations` exhaustion rather than throwing,
  so the caller can inspect partial results.

---

## Sequence

Nothing here is blocked, and the ordering is by prerequisite, not by value.

| When | What | Why here |
|---|---|---|
| **Now, no prerequisite** | Document that `after` carries the dependency's value, and that a skipped dependency binds `nil` | Undocumented in the guide, `llms.txt` and `llms-full.txt`; a reader concludes they must route everything through `state`. The cheapest real thing in the cluster |
| **Now** | **D1** (#609, filed) — warn in 5.x, error at 6.0.0 | Prerequisite for D2's step half, D3's typed reading, D4's typed parameters |
| **Next minor** | **D4** (#481 parameters, untyped) · **D9** (#488 `limits`) | Self-contained; D4 rides #470's shipped metadata mechanism |
| **Next minor** | **D2 first half** (#479 schema-from-signature) | Forces D1 into the open at the one surface that cannot fall back to `any` |
| **After that** | **D5** (#480 mapped nodes) — closes **D6** (#468) | Needs #470 (shipped); everything in group B waits on its addressing |
| **After D5** | **D7** (#577 compensation) | Unwinds per instance, so it needs D5's addressing |
| **After D1** | **D2 second half** (`returns:`) · **D3** (#472 wait schema) | Both need a type name that means something |
| **Deferred** | **D8** (#578 barrier) | Question answered, feature unjustified |

## What was rejected

- **One vocabulary for all three typed boundaries.** It reads as the tidy answer
  and #479 half-proposes it. The static annotations are flat and compile-time; the
  schema maps are structural and runtime; unifying them forces one of the two to
  become the other. Two vocabularies with a derivation between them is the honest
  shape, and the derivation is a feature (#479's second ask) rather than a seam.
- **`run_workflow(build("lite"))`.** New call syntax on a value that is a map, at
  the moment #394 finished pinning that value's shape.
- **A `partial` status or partial-success envelope (#468).** Subsumed by D5; see
  D6 for what would bring it back.
- **A `removed` status for a shrinking re-expansion.** Airflow needs it; Nodus's
  re-executing resume plus #470's drift refusal covers the case without an eighth
  task status.
- **A workflow-level exit hook (#577 option 2).** Needs run-status visibility
  inside a step body, which is a larger change than the feature.
- **A flat open `budget` vocabulary.** Would move the unknown-key check from parse
  time to run time and lose the one thing that surface currently does better than
  its neighbours.
- **Building the barrier cell (#578).** A second spelling for a join that works,
  narrower than the one it duplicates.

## Provenance

Each issue carries its own corpus provenance — Aider (#468), MAF/Autogen (#472),
Google ADK and MetaGPT (#479, #480, #488), GPT Engineer (#481), and #475's
decomposition (#577, #578). This document adds no new corpus; it reads the eight
against `src/` at 5.5.0 and decides where they collide.
