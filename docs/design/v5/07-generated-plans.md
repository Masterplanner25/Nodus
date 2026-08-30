# Generated plans — design for #93

**Status: proposal.** Nothing is built. Written in the shape `04`–`06` use.

**Everything in §2 was measured by running it** against `main` at `eb4f5c5`
(5.7.1 dev source). The measurement changed what this issue is: the execution
substrate for a generated workflow already exists and is safer than expected,
while the thing actually missing is a **contract**, not a package.

---

## 1. What #93 asks, after the recheck

The recheck (issue comment, 2026-08-30) established that the language half
shipped as #409 (`goal … over … until`) and that all three named blockers
(`nodus-agent`, `nodus-memory`, `nodus-tooling`) are cleared. What is left is:

- `workflow.plan(goal)` — generate a workflow toward a goal
- `workflow.reflect(result)` — post-execution reflection
- the memory-of-prior-state half of `workflow.resume(id)`

## 2. What already exists — measured

### 2.1 A workflow can be built from data at runtime, and run

This is the finding that reframes the issue. `task(fn, {"deps": [...]})`,
`graph(tasks)`, `plan_graph(g)` and `run_graph(g)` are all guest-reachable
builtins (`vm.py:354-356`, `1269`, `1321`, `1327`, `1335`). Run:

```
let plan = [
    {"name": "fetch",   "after": []},
    {"name": "analyze", "after": ["fetch"]},
    {"name": "report",  "after": ["analyze"]}
]
// ... build each with task(fn, {"deps": [...]}) ...
print("plan: \(plan_graph(g)["parallel_groups"])")
let r = run_graph(g)
```

```
plan: [["task_1"], ["task_2"], ["task_3"]]
failed: []
```

**A generated workflow is not a missing capability.** The dependency structure is
honoured, the levels are right, and it runs.

### 2.2 Two of the three orchestration invariants come free — the third does not

`00-domain-statement.md §4` says orchestration's unforgettable property is *"deps
resolved, acyclic, reachable"*, enforceable **at parse time**. A generated graph
has no parse time, so the obvious worry is that generation drops all three. It
does not:

| Invariant | Declared workflow | Generated graph |
|---|---|---|
| deps resolved | parse time | **free** — a dependency is a `task` *value*; you cannot reference one you do not have |
| acyclic | parse time (#396), and again at run (#323, shared `detect_cycle`) | **free, and stronger** — see below |
| reachable | `frontend/goal_validation.py` checks `reached("label")` against checkpoint literals | **absent** — no labels, no compile step |

**Acyclicity is enforced by construction, which is stronger than checking for
it.** A cycle requires a forward reference, and a dependency must be an
already-constructed value:

```
let a = task(fn() { return 1i }, {"deps": []})
let b = task(fn() { return 2i }, {"deps": [a]})
// closing the cycle would need `a` to depend on `b`; `a` is already built
```

No mutation path onto a built `TaskNode`'s dependencies was found. So the
generated form cannot express the thing the parser exists to reject. That is a
real property to state and to keep — it is the reason a generated plan is not
inherently more dangerous than a declared one, and any future "edit a graph after
building it" convenience would destroy it.

### 2.3 A planner exists, and it does not emit a DAG

`nodus-agent` (published, 28 tests) ships `PlannerBackend`, `LocalPlanner`
(heuristic, no LLM) and `LLMPlanner` (via `nodus-llm`'s `FailoverClient`). The
protocol:

```
plan(objective, tools, context) -> {"steps": [{"tool", "args", "description"}],
                                     "objective", "planner", "risk"}
```

**The steps are a flat list of tool calls with no dependencies between them.**
That is the gap, and §4 is about it.

### 2.4 The goal loop already exists

`goal … over … until` with `budget { max_iterations, deadline_ms }` re-runs a
workflow until a predicate holds, and `reached("label")` naming a label no step
emits is a **compile error**. So "keep trying until the objective is met, under a
bound" is a language feature, not something a planning library must build.

### 2.5 Reflection has a substrate

`nodus-memory` (published) ships `recall()`, `score_nodes()` and
`update_feedback()`. Outcome-weighted recall is what "reflect on results and do
better next time" reduces to.

### 2.6 Two capability models, and they are not duplicates

Worth naming before someone treats it as the recurring shape. They answer
different questions:

| | Question | Where |
|---|---|---|
| core `CapabilityPolicy` | may **this call** proceed? | `runtime/capability.py`, at the two VM chokepoints |
| `nodus-agent` `CapabilityToken` | is **this run** authorised, and by whom? | `nodus_agent/capability.py`, minted and signed |

A token authorises a run; the policy gates each call inside it. They compose;
neither substitutes for the other. **But nothing currently connects them**, and a
generated plan is exactly where they must meet — §6.

## 3. What is actually missing

Not a planner, not an executor, not a loop. Three things:

1. **Names.** The generated graph's tasks are `task_1`, `task_2`, `task_3`. The
   plan's own names (`fetch`, `analyze`, `report`) are discarded. Inspectability
   is one of the three domain properties, and a run whose steps are numbered is
   not inspectable in the way `workflow { step fetch … }` is — not in
   `plan_graph` output, not in the graph store, not in an operator's `nodus
   workflow inspect`.
2. **The plan→graph bridge**, and the dependency question it forces (§4).
3. **A contract for what is checked before a generated graph runs** (§5).

## 4. The dependency question — the real design fork

A planner emits a flat list. A workflow is a DAG. Something must decide the
edges.

| | A: sequence | B: planner emits `after` | C: infer from data flow |
|---|---|---|---|
| Shape | step *n* depends on *n-1* | plan carries dependencies | derive edges from which step consumes which output |
| Correct? | always safe | as correct as the model | as correct as the declared inputs |
| Keeps the DAG? | **no** — everything serialises | yes | yes |
| New failure mode | none | a model can assert a wrong edge | none new; a missing input is already an error |

### 4.1 Recommendation: B, with A as the default and C rejected for now.

**A alone defeats the purpose.** A serial chain is a script; Nodus's orchestration
value is the DAG, and a planning library that can only emit sequences hands back
the least interesting shape.

**C is where this wants to end up and should not start.** Inferring edges from
data flow is the principled answer, but it needs a plan format that declares each
step's inputs and outputs, which `PlannerBackend` does not have. Adding it is a
change to a published package's protocol; that is a second decision, not a
prerequisite.

**So: B, and the plan format grows an optional `after`.** When absent, fall back
to A — a sequence is a correct DAG, just a narrow one. That makes the library
useful against today's `LocalPlanner`/`LLMPlanner` output unchanged, and better
against a planner that learns to emit edges.

**The wrong edge is a real new failure mode and gets stated, not hidden.** A
model asserting `after: ["analyze"]` on a step that does not need it costs
parallelism; asserting the reverse costs correctness. §5 is what bounds it.

## 5. The contract: what must hold before a generated graph runs

The heart of this document. A declared workflow is checked by the compiler; a
generated one has no compiler, so the checks have to be somewhere, and "the model
was careful" is not somewhere.

| Check | Status | Where it goes |
|---|---|---|
| acyclic | **free** (§2.2) | construction |
| deps resolved | **free** (§2.2) | construction |
| every named tool exists | **missing** | before the run — `tool.has(name)` per step |
| every tool is permitted | **missing** | the policy already refuses at call time; checking *first* turns a mid-run denial into a pre-run rejection |
| the plan is bounded | **partly** — `goal`'s budget bounds iterations | a plan should also declare a step ceiling |
| steps are named | **missing** (§3.1) | the bridge |
| reachable / goal satisfiable | **absent** | see §5.1 |

**The rule: a generated plan is validated as a whole before any step runs.** Not
step-by-step as it goes. A plan that will fail at step 7 because a tool does not
exist should be rejected at step 0 — the run has not touched the world yet, and
after step 1 it has.

This is the same instinct as `goal_validation.py` rejecting an unreachable
`reached("label")` at compile time rather than looping forever, applied at the
only moment a generated plan has that is equivalent to compile time: **after
generation, before execution.**

### 5.1 Reachability is the one that does not transfer

For a declared goal, `reached("good_enough")` is checked against checkpoint
literals in the source. A generated plan has no literals to check — the predicate
and the steps are both produced by the model, so checking one against the other
proves only that the model was self-consistent.

**Recommendation: do not fake it.** Do not synthesise checkpoint labels to make
the existing check pass. State that a generated plan's goal satisfiability is
bounded by the budget and nothing else, which is what `max_iterations` and
`deadline_ms` are for. A check that cannot fail is worse than an absent one,
because it reads as a guarantee.

## 6. Where the two capability models meet

A generated plan is the domain statement's phrase made literal: **work you did
not fully author**. So this is the surface where §2.6's two models have to
connect, and the connection is the security story of the whole library.

**Recommendation:** a generated plan runs under a policy **narrowed to the tools
the plan declares**, not the ambient one. The plan names its tools before it
runs (§5); that list is exactly the grant it needs. A plan that later attempts a
tool it did not declare is refused — not because the tool is forbidden in
general, but because *this plan* did not ask for it.

That is a real strengthening over "run the plan with the host's policy", and it
costs nothing to compute, because the tool list is already being collected for
the existence check.

The `CapabilityToken` then authorises the run and carries that narrowed grant;
`CapabilityPolicy` enforces it per call at the chokepoints. Neither model
changes.

## 7. Reflection

The vaguest word in the issue, so it gets a definition or it gets dropped.

**Recommendation: reflection is not a control construct.** It is writing a
structured outcome to memory, keyed so the next plan's `context` recalls it.
`nodus-memory` already has the three pieces — `recall()`, `score_nodes()`,
`update_feedback()` — and `PlannerBackend.plan()` already takes a `context` dict
documented as carrying memory.

So `workflow.reflect(result)` is: derive a record from the run result (what was
attempted, what failed, what it cost), write it with `update_feedback`, and have
the planner's `context` recall it next time. **No new mechanism, and no new
loop** — the loop is `goal … over … until`.

If reflection turns out to need to *change the plan mid-run*, that is a different
and much larger feature, and it should be a separate issue rather than smuggled
in under this word.

## 8. What this does not do

- **Does not add a language surface.** #409 took the language half; the rest is
  a library. The domain rule's test 2 fails for planning — the compiler cannot
  make a *good* plan unforgettable, only a bounded one, and the bound is already
  in the language.
- **Does not build a planner.** `nodus-agent` has two.
- **Does not add a loop.** `goal … over … until` is the loop.
- **Does not infer dependencies from data flow.** §4.1, deliberately deferred.
- **Does not make a generated plan's goal statically satisfiable.** §5.1.
- **Does not let a plan mutate itself mid-run.** §7.

## 9. Open decisions, with recommendations

### 9.1 Where does the bridge live?

`nodus-agent` has the planner; `nodus-lang` has `task`/`graph`/`run_graph`; the
bridge needs both. **Recommendation: a new package** (`nodus-workflow-ai`, this
issue's name), depending on `nodus-agent` and `nodus-lang`. Putting it in
`nodus-agent` would give that package a `nodus-lang` dependency it does not have
today, which the dependency-audit rule treats as a real cost.

### 9.2 Does the generated graph get named steps, and how?

**Yes** (§3.1). The open part is whether naming is a `task()` option — a
`"name"` key alongside `"deps"` — or whether the bridge maintains its own
mapping. **Recommendation: a `name` option on `task()`**, because the graph store
and `plan_graph` output are where the name needs to appear, and a bridge-side
mapping cannot reach them. That is a small core change and should be filed as its
own issue against nodus-lang rather than carried by the library.

### 9.3 May a generated plan call `agent_call`?

That is a plan that can ask a model to make more decisions mid-run — recursion
through the agent boundary. **Recommendation: permitted but not by default.**
Under §6, `agent_call` is a tool like any other: the plan must declare it, and
the narrowed grant then allows it. What must not happen is a plan reaching the
model implicitly.

### 9.4 What happens to a partially-executed generated plan on resume?

A declared workflow resumes by re-entering a step (#486), rebuilding from source.
A generated plan has no source — the graph was built from a value that existed in
one process. **Recommendation: treat this as the open question it is**, and in
the first version, say plainly that a generated run is not resumable across
processes. It is the one place where a generated workflow is genuinely weaker
than a declared one, and it should not be discovered by a user.

## 10. Success criterion

1. A plan produced by `LocalPlanner` runs as a Nodus graph, with its **own step
   names** visible in `plan_graph` output and the graph store.
2. A plan naming a tool that does not exist, or one the host has not granted, is
   rejected **before any step runs** — asserted by a test that fails if the
   rejection happens at the failing step instead.
3. A plan that declares `after` edges runs those steps in parallel where the
   edges allow, and `parallel_groups` proves it.
4. A plan attempting a tool it did not declare is refused even when the host's
   ambient policy would allow it (§6).
5. No document claims a generated plan's goal is statically checked (§5.1).

(2) and (4) are the ones that need source-level assertions rather than behavioural
ones: both pass accidentally against a plan that happens not to exercise them.
