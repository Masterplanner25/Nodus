# What is the domain? — design input for #409 Part B

**Status:** proposal. The domain statement in §3 is put forward for decision; the
agent-boundary question it produced is **decided** in §4.1. Written because #409
Part B names an unanswered question and says answering it is prerequisite to
deciding which surfaces deserve language-level work.

---

## 1. The question, and what it is not

All three external architecture audits tested Nodus against *"an orchestration
DSL and embedded runtime for building agentic systems"* and all three rejected
the last clause. The positioning half of that was fixed on 2026-08-15 (`649a2ed`)
— the docs now say **hosting**, not building.

**That was a positioning fix, not a domain answer.** They are different questions:

| | Question | Answered? |
|---|---|---|
| Positioning | Who is this for and what does it claim? | Yes — *"durable, inspectable, capability-jailed task orchestration, with a clean handoff boundary to model-driven decisions your host supplies"* |
| **Domain** | **What class of concept must this language make unforgettable?** | **No** |

The domain question is the operational one. #409's central observation is that
`@exactly_once` is the best DSL feature in the project and it is not in the
headline:

> *"the compiler lowering guarantees every annotated function gets the
> resolve→pending→execute→complete envelope with a content-addressed action id.
> **You cannot forget it.**"* — Audit 03 §8

**"You cannot forget it" is the DSL property in four words.** A library gives you
a facility you must remember to use correctly; a DSL makes the concept
unforgettable and rejects the program, or corrects the execution, if you try. So
the domain is not a topic — it is **the set of things this language refuses to let
you forget**.

> **This claim was false when written. It is true as of the #411 fix.** The
> lowering emitted ordinary calls on `effect_resolve` and friends, and `CALL`
> resolves user functions before builtins — so a program could supply the envelope
> the compiler had injected into its own code, in three lines, and the annotated
> body never ran. You could not forget it; you could *defeat* it. A guarantee that
> the program's author can switch off is a convention, not a language property, and
> the whole argument on this page rests on the difference.
>
> Lowerings now emit calls the VM binds straight to the builtin table, ahead of any
> user lookup. The general rule matters more than the one annotation: **a
> compiler-applied guarantee is only as strong as the name resolution of the calls
> it emits.** Any future lowering meant to hold against the program's author —
> capability checks, declared-effect enforcement, the dependency guards
> contemplated in `01-goal-stopping-condition.md` — must use `builtin_call()` from
> `frontend/ast/ast_nodes.py` rather than an ordinary call to a shadowable name.
>
> The rule was not hypothetical even at the time of the fix. Asking *what else has
> this shape* found the **workflow lowering** carrying the same hole: every step
> body opens with `let __workflow_state = workflow_state()`, so defining
> `fn workflow_state()` replaced the state map every step reads. Two of the four
> rows in the table below — `@exactly_once` and `@retry` — plus the workflow state
> machinery were all forgeable by the same three-line move.

## 2. Method: derive it from what verifiably works

Rather than assert a domain and check whether the language serves it, this derives
the domain from the features that already qualify. Each was verified against
`main` at `803b4af`.

| Verified feature | Mechanism | What forgetting it would break |
|---|---|---|
| `@exactly_once` | compiler lowering (`compiler.py:441`) | a side effect double-fires across retry and resume |
| `@retry` | compiler lowering | failure handling is absent or unbounded |
| Closed annotation set | parse-time — `@nonsense` → `Syntax error: Unknown annotation: @nonsense` | a misspelled guarantee silently does nothing |
| `TASK_STEP_BUDGET = 1000` | instruction stream (`scheduler.py:266`) | a CPU-bound coroutine starves every other |
| Deadlock detector | instruction stream (`scheduler.py:229`) | a silent hang instead of a typed error naming the blocked coroutines |
| `max_steps` / `max_frames` / `deadline` | runtime limits, applied by default | unbounded resource use |
| Duplicate step names, unknown dependencies | parse-time (`parser.py:531`, `:537`) | a malformed plan is discovered only when it runs |
| `checkpoint` labels are literals | parse-time (`parser.py:330`) | — enables the total static check in `01-goal-stopping-condition.md` |

Three properties account for all of them:

- **Bounded** — step budget, deadlock detection, `max_steps`/`max_frames`/
  `deadline`, `@retry`, acyclicity (an acyclic graph terminates).
- **Durable** — `@exactly_once`: progress and side effects survive interruption,
  exactly once.
- **Inspectable** — parse-time step and dependency checks (the plan is
  well-formed and knowable *before* it runs); the deadlock detector *naming* the
  blocked coroutines (what happened is recoverable *after*).

These are the same three words already in the positioning — *durable,
inspectable, capability-jailed* — with "capability-jailed" generalised to
**bounded**, of which reach is one bound among several.

## 3. Proposed domain statement

> **The domain is work that will be interrupted, that you did not fully author,
> and that touches the world.**
>
> A concept belongs in the language when **both** hold:
>
> 1. Forgetting it breaks **bounded**, **durable**, or **inspectable**; and
> 2. The **compiler** or the **instruction stream** can make forgetting
>    impossible.
>
> Everything else is a library.

Test 2 is what keeps this honest. "Important to agentic systems" is not
sufficient — a great many things are. The question is whether the property can be
*enforced at compile time or in the instruction stream*, because that is the only
thing a host-language library structurally cannot reproduce. A Python decorator
cannot preempt the interpreter; `asyncio` cannot detect this class of deadlock;
and no library can reject a program.

### Why "agentic" is not the domain

Under this statement, agentic systems are the **application**, not the domain.
That is consistent with what all three audits found independently, with the
positioning fix already made, and with the fact that there is no model in the
core and should not be. Nodus is not a DSL for agents; it is a DSL for running
work under guarantees, and agentic systems are the current best example of work
that needs them — generated, long-running, and effectful.

### Why the general-purpose surface is not a problem

Audit 01 flagged general-purpose expressiveness as *"scope that works against the
thesis."* #409 already rejected that inference; the domain statement explains
why. General computation **inside** a bounded, durable, inspectable unit is the
payload, not a widening of the domain. Audit 01 argues against itself at §09: a
graph API makes you write control flow in the host language, *"at which point you
have two abstractions, two error models, and two places state can live. Nodus is
one."*

What must grow faster than the general-purpose surface is not the language's
size but **the number of things it refuses to let you forget**.

## 4. Applying it — the scoping answer

Both columns must be yes.

| Surface | Must never be forgotten | Property | Enforceable by compiler / instruction stream? | Verdict |
|---|---|---|---|---|
| **Effects** | resolve→pending→execute→complete, content-addressed | Durable | yes — lowering | **in, done** |
| **Concurrency** | fairness; no silent deadlock; bounded task time | Bounded, Inspectable | yes — instruction stream | **in, done** |
| **Orchestration** | deps resolved, acyclic, reachable | Bounded, Inspectable | yes — parse-time; partial today | **in, partial** (#396) |
| **Goal** | a stopping condition and a budget | Bounded, Inspectable | yes — checkpoint labels are literals | **in, specified** (`01-…`) |
| **Capability** | the grant is checked before the call; refusal is recorded | Bounded | runtime half yes (#405); static half needs effects in signatures | **in, not started** |
| **Agent boundary** | a declared bound on the call | Bounded | the compiler can require the *declaration*; the runtime must do the *enforcement* | **in — narrowly** (§4.1) |
| **Memory** | address validity | none of the three | a MAS path typo is a correctness bug, not a bound or a survival property | **out — library** |

**Memory falls out, and that is the point.** A domain statement that admits
everything is a slogan. This one excludes a surface the issue's table listed,
with a reason: `nodus-memory` is already a separate package, and validating an
address string is ordinary correctness rather than a guarantee only a compiler
can make unforgettable.

### 4.1 The agent boundary — decided, after reading the code

**Decision: in, narrowly.** Not "make `agent` a language concept" — it already is
— but "the compiler must not let you omit the bound."

The premise this was going to be decided on was wrong. #409's table describes the
agent surface as *soft — string-compared `ID`s after `ACTION`*, and lists
*timeout, JSON-safety, paired events, trace id* as the must-never-forget set.
An earlier revision of this document repeated both without checking. Measured
against `803b4af`:

| Audit 02 F4 claim | Reality |
|---|---|
| *"not a keyword"* | **wrong** — `ACTION` is a token (`parser.py:94`) |
| *"not an AST node"* | **wrong** — `ActionStmt(kind, target, payload)` |
| *"not an opcode"* | correct |

And the surface is stricter than "soft" suggests. Verified:

- The kind set is **closed and parse-enforced** —
  `action frobnicate "x" with {…}` → `Syntax error: Unsupported action kind: frobnicate`
- The target is a **string literal** —
  `action agent n with {…}` → `Syntax error: Expected string literal, got identifier ('n')`

That is the same mechanism as the annotation allowlist this document cites
approvingly in §2. *"String-compared ID"* is accurate about how the kind is
matched and misleading about what it means.

The runtime side is also in better shape than claimed:

| Claimed must-never-forget | Reality |
|---|---|
| JSON-safety | **enforced**, both directions — payload in and handler result out |
| paired start/complete events | **enforced** unconditionally in `call_agent`; `goal_action_*` additionally inside a goal |
| **timeout** | **does not exist** — no deadline anywhere in `agent_runtime.py` |
| trace id | **does not exist** in this path |

Two of the four items were never real. **One gap is, and it is a bound:** a host
handler can block forever. Measured — a `NodusRuntime(timeout_ms=200)` run whose
handler slept 3 s took 3.77 s and returned `ok: True`. Filed as **#424**.

Applying the two tests to that gap:

1. **Does forgetting it break bounded?** Yes, and it produces the
   success-shaped-failure signature this codebase has spent a cycle removing.
2. **Can the compiler or the instruction stream make forgetting impossible?**
   Not the *enforcement*. A handler is a host function, executed outside the
   instruction stream, so the VM cannot preempt it — the same structural limit as
   #405's chokepoint, and the reason every other bound misses it. But the
   compiler **can** make the *declaration* impossible to omit: `action` payload
   keys are currently unvalidated (`with { nonsense_key: 1i }` parses clean) even
   though `parse_named_map_literal` already supports a key allowlist.

So the boundary is in the domain on a **split rule**, which is worth stating
generally because it recurs:

> When a guarantee must hold across the host boundary, the language owns the
> **declaration** and the runtime owns the **enforcement**. The compiler's job is
> that you cannot forget to declare the bound.

That is the identical shape to `budget` being mandatory on a goal
(`01-goal-stopping-condition.md` §4), and it is the honest version of test 2 for
anything that leaves the instruction stream.

## 5. Re-reading the six moves through it

| Move | Serves | Verdict |
|---|---|---|
| 1. Orchestration static analysis | Inspectable, Bounded | **in** — cheapest, in flight (#396) |
| 2. Effect and capability typing on steps | Bounded | **in — highest value.** Turns #405's runtime enforcement into something checkable *before* execution: *"this generated workflow provably cannot touch the network"* is a claim only a compiler can make |
| 3. `goal` as a bounded, declared loop | Bounded, Inspectable | **in** — specified in `01-goal-stopping-condition.md` |
| 4. Typed dataflow between steps | *contested* | **Weakest under this statement.** Rejecting `b` for misusing what `a` returns is ordinary type checking — value typing, not domain typing. #409 itself says *"a general-purpose language types its values; a DSL types its domain."* It may serve Inspectable (knowing what crosses an edge is part of knowing what a plan does), which is why this is contested rather than out — but it should be argued on that basis, not on "it makes the compiler necessary" |
| 5. Workflow composition as a language operation | Inspectable | **in, marginal** — composed workflows staying analysable is the whole justification; without that it is convenience |
| 6. Orchestration-aware opcodes | *mechanism, not a claim* | **Reframe.** This is test 2's second half, not a goal in itself. Each guarantee moved into the instruction stream needs its own justification; "zero of 48 opcodes are orchestration-aware" is an observation, not a requirement. #366 already makes adding one a governed process, which forces exactly that argument |

The uncomfortable result — move 4 being the weakest rather than the pivotal one —
is the kind of answer a domain statement is supposed to produce. If it only
ratified the existing plan it would not be doing any work.

## 6. The consequence for "why not just write this in Python?"

The answer this statement licenses:

> Because the compiler and the instruction stream enforce things about your
> orchestration that no Python library structurally can — the plan is resolved,
> acyclic and inspectable before it runs; the effects are declared and checked
> against the grant; the loop has a declared predicate and a bounded budget; a
> CPU-bound task cannot starve the others; a deadlock names itself instead of
> hanging. **You cannot forget any of it, and you cannot opt out.**

Two of those five hold today, verified. One is specified. Two are open issues.
That is a defensible claim with a known gap, which is a better position than a
claim that sounds complete and is not — the thing all three audits caught.

**One caveat that must be stated wherever the bounds are claimed:** `timeout_ms`
is a bound on VM execution, not wall clock. A host call — an agent handler, a
tool handler — runs outside the instruction stream and no deadline reaches it
(#424). Until that is fixed, "bounded" is true of Nodus code and false of the
host functions it calls, and the guide should say so rather than let an embedder
read it as a request deadline.

## 7. What this does not settle

- **Whether move 4 survives.** It needs an Inspectable argument or it should be
  reclassified as general-purpose type-system work — worth doing, but not
  evidence for the DSL thesis.
- **Sequencing.** The domain statement says what is in; it does not say in what
  order. Current backlog order is #399 → Part A → #405/move 2.
- **Whether this is the right domain at all.** It is derived from what already
  works, which is a good way to be self-consistent and a poor way to be
  ambitious. A domain chosen for where the project is going rather than where it
  has been would look different, and that is a call this document cannot make.
