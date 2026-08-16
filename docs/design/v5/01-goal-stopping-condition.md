# Goal as a stopping condition — design for #409 Part A

**Status:** proposal. Nothing here is committed to. v5 scope — new syntax and new
execution semantics, not a patch.

**Prerequisite:** #393 (landed 2026-08-16). Until the `goal`/`workflow` retry
divergence was unified, `goal` had an accidental meaning rather than no meaning,
and giving it a real one would have layered on top of a bug.

This specifies Part A only. Part B — the DSL thesis and the six moves — is
tracked on the issue and is the reason Part A is worth doing, but Part A stands
alone.

---

## 1. The gap

Two audits described the same hole from opposite sides.

Audit 02, F22:

> *"The plan→act→verify→replan loop is inexpressible. The DAG is lexically fixed
> and cycles are rejected. There is no dynamic fan-out and no conditional edge.
> The defining control structure of agentic systems cannot be written in the
> orchestration language for agentic systems."*

Audit 01, §13:

> *"Completion is structural — every declared step ran. It is not semantic —
> nothing checks that the objective the goal names was met. Nodus has no
> representation of an objective, no predicate over world state, no success
> criterion, and no mechanism by which one could be supplied."*

`goal` is the keyword that already promises to fill this and, since #393, is
openly a `workflow` with a different event prefix.

**A workflow terminates when all its steps have run — structural completion. A
goal should terminate when its predicate holds, or its budget is exhausted —
semantic completion.**

## 2. The shape: a goal declares checkpoints over a workflow

The goal does not own the work. The workflow owns the work; **the goal owns the
criteria** — which waypoints constitute progress, and the condition for being
finished.

This is what makes `goal` and `workflow` different kinds of thing rather than two
spellings of a pipeline. The two alternatives considered and rejected:

| Considered | Rejected because |
|---|---|
| Goal contains steps (today's shape + `until`) | `goal` stays a workflow with a loop bolted on; the naming problem #393 exposed is only half-answered |
| Goal drives workflows (`run w1; run w2`) | Inherits composition questions the language cannot express — audit 01 §09: *"no API for composing workflows exists"* |

Checkpoints sidestep both, and land on machinery that already works (§3).

## 3. What already exists — measured, not assumed

Everything in this section was verified against `main` at `9037273` before the
design was written. Two of the claims in #409's original body did not survive
that check and the design changed accordingly.

### 3.1 Checkpoints are named, durable, state-carrying waypoints

`_record_checkpoint` (`task_graph.py:803`) stores, per checkpoint:

```python
entry = {"label": ..., "step": ..., "task_id": ..., "timestamp": ...}
if isinstance(workflow_state, dict):
    entry["state"] = clone_state(workflow_state)
```

The full state snapshot goes to `engine_checkpoints`; the public `checkpoints`
list keeps `label`/`step`/`task_id`/`timestamp` and drops the state
(`checkpoint_public`, `workflow_state.py:14`). Both persist through
`_persist_graph_state`.

### 3.2 Re-executing a graph with state carried forward already works

This is the mechanism the loop needs, and it is not new. Measured:

```nd
workflow advance {
    state n = 0
    step bump { n = n + 1; checkpoint "bumped"; return n }
}
let r1 = run_workflow(advance)
let r2 = resume_workflow(r1["graph_id"], "bumped")
let r3 = resume_workflow(r1["graph_id"], "bumped")
let r4 = resume_workflow(r1["graph_id"], "bumped")
```

```
pass1 n=1.0 ckpts=[{"label": "bumped", "step": "bump", "timestamp": ..., "task_id": "task_1"}]
pass2 n=2.0 step=2.0
pass3 n=3.0 step=3.0
pass4 n=4.0 step=4.0
```

The step re-executes and state advances. The three modes differ:

| | state | steps re-run? |
|---|---|---|
| `run_workflow(w)` again | re-initialised | yes — fresh graph, fresh `state` block |
| `resume_workflow(id)` on a completed run | preserved | **no** — replays cached results |
| **`resume_workflow(id, "label")`** | **carried from the checkpoint** | **yes — forward from there** |

Needs `--time-limit` above the 200 ms default for several sequential resumes;
that is a deadline artifact, not a semantic one.

### 3.3 Checkpoint labels are literals, so the static check is total

`checkpoint` is a statement with a mandatory string literal, not a function call
(`parser.py:330`):

```python
if self.workflow_step_depth > 0 and self.at("ID") and self.peek().val == "checkpoint":
    start = self.eat("ID")
    if not self.at("STR"):
        self.error("checkpoint label must be a string", start)
    label_tok = self.eat("STR")
    return self.mark(CheckpointStmt(label), start)
```

A dynamic label is rejected at parse time:

```
Syntax error at dyn.nd:4:9: checkpoint label must be a string
```

**Every checkpoint label in the language is known at parse time, in a dedicated
AST node, with no dynamic fallback.** The complete checkpoint set of any workflow
is therefore statically collectable, and the check in §5 is total rather than
best-effort.

### 3.4 Re-running a DAG is not a cycle in it

Three consecutive `run_workflow` calls produce three distinct `graph_id`s and no
cycle error. `_detect_cycle_task_ids` needs no change: the loop lives one level
above the graph, and each iteration is a run over the same acyclic shape. **The
one structural invariant genuinely enforced today survives intact** — this was
expected to be the blocker and is not.

### 3.5 Corrections to #409's body

- The issue's stated success criterion — make audit 01 §4's demolition stop being
  true — is **already satisfied**. Both execution paths require a compiled Nodus
  closure (`Coroutine(task.function)` → `scheduler._ensure_metadata` reads
  `closure.function.addr`; the worker branch calls `vm.run_closure`). A Python
  callable is never invoked. `TaskNode.function: object` is a loose annotation,
  not a supported entry point. §11 restates the criterion.
- The issue's open question 2 says `state` carrying forward is nearly free
  because *"blocks already exist and already persist"*. That is true, but for a
  different reason than the question implied — see §3.2. An earlier revision of
  this analysis claimed the mechanism was missing entirely; that was wrong,
  arrived at by testing the unlabelled resume and generalising.

## 4. Syntax

Sketch, not settled. The design constraint is that everything the compiler must
check is a literal.

```
goal ship_release over deploy_pipeline {
    until reached("verified")
    budget { max_iterations: 5, deadline_ms: 300000 }
}
```

- `over <workflow>` — the workflow this goal pursues. Resolved at parse time, in
  the same class as the existing unknown-dependency check (`parser.py:537`).
- `until <predicate>` — the stopping condition. `reached("L")` takes a **string
  literal**, matching `checkpoint`'s own rule; this is what keeps §5 total.
- `budget { ... }` — **mandatory**. An unbounded goal is a hang, and bounded
  execution is the runtime's entire value proposition.

**Declaration is by use.** The declared checkpoint set is exactly the set of
literals appearing in `reached(...)` within `until`. There is no separate
declaration block to drift out of sync with the predicate.

A goal predicate can also be semantic rather than deterministic, which is the
whole point of putting the loop here:

```
goal ship_release over deploy_pipeline {
    until action agent "judge" with { prompt: "are the release notes accurate?" }
    budget { max_iterations: 3, deadline_ms: 600000 }
}
```

The runtime owns the loop; the model owns the verdict. That is the
deterministic → semantic → deterministic sandwich all three audits named as the
cleanest property in the design, applied to the one place it is currently
unavailable. Compare Claude Code and Codex, where termination is `needsFollowUp` /
`needs_follow_up` — a model-authored boolean with host *ceilings* rather than a
declared judgement. A goal with a declared predicate and a declared budget is the
same loop, **inspectable before it runs and resumable after it stops.**

## 5. Both halves: declared and observed

These are not alternatives. Each covers a failure the other has.

- **Declared-only** gives a contract with no diagnosis. A goal that fails to
  converge shows only the waypoints its author thought to name.
- **Observed-only** gives nothing to check before running — the contract exists
  only at runtime, which is the failure shape this codebase has spent a cycle
  removing (#392, #376, #399).

**The predicate may only name declared checkpoints; the trace records every
checkpoint reached.** The observed set is a superset of the declared set.

| | mechanism | cost |
|---|---|---|
| Declared | compiler walks `CheckpointStmt` labels in the target workflow; every `reached("L")` literal must be in that set | new static pass — small; the AST node exists and labels are literals |
| Observed | runtime already appends every reached checkpoint with a `clone_state` snapshot | **free** — already implemented |

### Compile-time checks

1. **Every `reached("L")` names a checkpoint the target workflow records.** Total
   (§3.3). *A goal cannot name a waypoint that does not exist.*
2. `over <workflow>` resolves to a workflow in scope.
3. `budget` is present and bounded.
4. *Future, needs move 1's reachability analysis:* warn when a declared
   checkpoint sits in a step unreachable in the workflow's DAG.

Check 1 is the `@exactly_once` property — *you cannot forget it* — reached for
the goal row, and reached without adding a restriction, because the restriction
is already in the parser. It is also the concrete answer to *what does `goal` gain
that a library cannot have*: a Python planner can observe checkpoints at runtime;
it cannot reject a goal whose waypoints do not exist, having no parse tree to
check them against.

## 6. Execution semantics

```
pass 0:  run_workflow(target)
         evaluate `until` over reached checkpoints + state
         satisfied            -> goal completes
         unsatisfied, budget  -> continue
         unsatisfied, no budget -> goal fails, status "budget_exhausted"

pass n:  resume_workflow(graph_id, <re-entry label>)   // §3.2
         evaluate again
```

The loop is `resume_workflow(id, label)` under a predicate and a budget. No new
execution mode is required.

**Budget exhaustion is a failure, not a completion.** The result carries
`status: "budget_exhausted"`, the reached-checkpoint history, and the last
predicate value. A goal that ran out of iterations must never return a
success-shaped result — that is the defect class this cycle exists to close.

**Interaction with step-level `retries` (#392):** a step's own retries are
exhausted first, inside the pass. Only then does the pass fail and the goal
decide whether to spend an iteration. The two budgets are nested, not competing.

## 7. Open decisions, with recommendations

Each is a decision, not a discovered fact.

### 7.1 Which checkpoint does a failed or unsatisfied pass re-enter?

**Recommend:** the last checkpoint reached, with an explicit override:

```
goal g over w { until reached("done") retry from "analyzed" ... }
```

Last-reached is the behaviour that makes progress monotonic by default.
`retry from` covers the case where partial work must be discarded. The override
label is a literal and so falls under check 1.

### 7.2 Is `until` a predicate over checkpoint history, or over state at a checkpoint?

These are different languages and the difference should be decided, not drifted
into.

**Recommend both, in that order.** `reached("L")` — history — in the first cut:
it is the smaller language, it is fully statically checkable, and it covers the
motivating cases. State-at-checkpoint (`state_at("L")["confidence"] > 0.9`) is a
natural extension but needs §7.4 resolved first.

Ordered history (*reached A then B*) is deliberately **not** in the first cut. It
is expressible later without breaking `reached`.

### 7.3 Budget shape

**Recommend:** `max_iterations` and `deadline_ms` required in the first cut; cost
deferred. Cost has no runtime representation today — there is no token or spend
accounting to bound — so specifying it now would be specifying a unit that does
not exist.

### 7.4 The public `checkpoints` shape

`checkpoint_public` drops the state snapshot. A state-at-checkpoint predicate
(§7.2) needs it.

**Recommend:** leave the public shape alone for the first cut, since `reached`
does not need state. When §7.2's extension lands, give the predicate an
engine-side view rather than widening the public result — the snapshot is
unbounded user state and putting it in every workflow result is a payload-size
and information-disclosure change that should be decided on its own merits.

## 8. What this does not do

- **No dynamic fan-out, no conditional edges.** The DAG stays lexically fixed and
  acyclic. This adds a bounded loop *over* a fixed graph, which is a smaller claim
  than F22's full "plan→act→verify→replan" and should not be described as
  answering it completely. What it answers is the *verify→replan* half: the loop
  and its termination.
- **No planner.** Deciding *what to run next* is planning and stays in #93. This
  proposal corrects that issue's split: the bounded loop, the declared predicate
  and the budget are language concerns because the keyword already promises them
  and a declared loop is analysable; choosing the next action is a library
  concern.
- **No mid-pass early exit.** The predicate is evaluated per pass, not at each
  checkpoint as it is recorded. Per-checkpoint evaluation would allow abandoning a
  pass whose objective is already met, which is worth having when later steps are
  expensive — but it requires interrupting a running graph and should be a later
  increment.

## 9. Durability

Iteration count, predicate history and the reached-checkpoint set join the
persisted run state. All three are small and all three sit alongside data that is
already persisted per checkpoint, so this is an addition to an existing snapshot
rather than a new store.

A goal is resumable across processes on the same terms as a workflow — **and
inherits #399**, where cross-process resume fails whenever the script reads the
`run_workflow` result and re-runs top-level side effects on each failed attempt.
A goal loop calls resume repeatedly by construction, so it multiplies that defect
rather than merely meeting it. **#399 should be fixed before this ships**, not
alongside it.

## 10. Relationship to other work

| Issue | Relationship |
|---|---|
| **#393** | Prerequisite. Landed — `goal` and `workflow` no longer diverge, so `goal` can be given a meaning rather than inheriting an accident |
| **#399** | **Blocker in practice** (§9) — a goal loop is repeated resume |
| **#93** | Corrects its language/library split — the loop is language, the planner is library |
| **#396** | Move 1; check 4 in §5 depends on its reachability analysis |
| **#405** | Independent, but a goal's budget and a capability grant are the two halves of "what may this plan do, and for how long" |
| **#394** | Step ordering is bypassable via map manipulation; a goal's guarantees are only as strong as the workflow's |

## 11. Success criterion, restated

#409's original criterion — make audit 01 §4's demolition stop being true — is
already satisfied (§3.5) and so cannot measure anything. The engine needs the
**VM**; what it does not need is the **compiler**. Every one of Part B's six moves
is a compiler-side claim, so the criterion should be stated against the compiler:

> The measure of success is that a graph the compiler did not produce is **missing
> declarations the engine requires** — resolved and cycle-checked dependencies,
> effect signatures, capability requirements, and a declared predicate and budget.

For Part A specifically, the falsifiable form is narrower and testable on
delivery:

> A goal is rejected at compile time when it names a checkpoint its target
> workflow does not record — and no Python program constructing the same graph by
> hand can be rejected the same way, because the labels it would be checked
> against exist only in a parse tree.
