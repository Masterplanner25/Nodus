# What seventeen systems say about Nodus

> Synthesis of the 2026-08-17/18 research-corpus sweep: every folder under `C:\codev\*
> research` cross-checked against **Nodus 5.0.4**, with 30 issues filed (#465–#494).
> Companion to [EXTERNAL_AUDIT_LEDGER.md](EXTERNAL_AUDIT_LEDGER.md), which records
> verdicts on audits run *against* Nodus. This file records what the corpus says *about
> the language* when read as a whole.
>
> Every Nodus claim below was executed at 5.0.4, not read.

---

## 1. The finding that changes where effort goes

Thirty issues, by subsystem:

```
16   workflow
 3   runtime        2  stdlib      2  library
 2   docs           2  compiler    1  cli      1  embedding
 0   lexer / parser / vm / type-system
```

**Seventeen adversarial reads — four of them auditing Nodus directly — produced zero
findings about the language core.** Nothing about closures, control flow, types, the VM
or bytecode. The two compiler issues are both about the workflow/host boundary (#487's
missing analyzer binding, #489's absent extern declarations), not about language
semantics.

That is a real result and it should redirect effort. The lexer, parser, type system and
VM are not where the risk is. **The `workflow` DSL and its runtime semantics are.**

---

## 2. What the absence of competitors does and does not prove

Not one of the seventeen has an orchestration *language*:

- **Nine have no graph engine at all** — Aider, Devika, gpt-engineer, OpenHands,
  OpenClaw, Open Interpreter, SWE-agent, MetaGPT, Hermes.
- **Five have a graph API hosted in a general-purpose language** — LangGraph, MAF, ADK,
  CrewAI, Temporal.
- **Three are not agent orchestrators** — Linux, Claude Code, Codex.

**The tempting reading is wrong.** "Nobody built a DSL" is not evidence that a DSL is the
wrong shape. Building a language is an undertaking almost nobody attempts, with or
without AI assistance, and the absence of attempts says more about cost than about
merit. The honest version:

> Nobody built one, so nobody's experience will tell us when we get it wrong — and the
> five graph APIs are evidence that the *need* is real, because each one is a substantial
> abstraction built inside a host language to obtain what a DSL would give directly.

MAF's edge groups are `DictConvertible` specifically so the graph survives serialization.
LangGraph's channels are declared cells with typed merge policies. ADK's edges are
route-matched with a `DEFAULT_ROUTE` fallback. **Three independent teams built a
declarative, serializable graph vocabulary inside Python** rather than in the host
language's own control flow. That is the case for the language existing — weaker than
proof, stronger than nothing.

---

## 3. Which systems can actually teach us about orchestration

Not all seventeen are equally informative, and treating them as one corpus flattens the
signal. Stratified by what they own:

### Tier 1 — own a real orchestration engine (4)

| System | What it owns | What it taught |
|---|---|---|
| **LangGraph** | channels + reducers, versioned triggering, pending-writes-then-checkpoint | #485 (silent lost update), #486 (checkpoint granularity) |
| **MAF** | typed serializable edge groups, superstep barrier, `graph_signature_hash` | #469, #470, #471, #472 |
| **ADK** | frontier scheduling, route-matched edges + `DEFAULT_ROUTE`, `JoinNode`, dynamic expansion | #479, #480 |
| **Temporal** | durable execution, history-as-record, determinism boundary | #494 |

**These four produced 11 of 30 findings from 24% of the corpus**, and a disproportionate
share of the severe ones. They are the systems worth re-reading when workflow semantics
change.

### Tier 2 — partial or implicit orchestration; teach by their workarounds (5)

- **CrewAI** — the only working Nodus implementation. Teaches about the *boundary*, not
  the engine: one `.nd` flow survived four substitutions of everything beneath it.
- **MetaGPT** — a latent DAG topologically sorted and then *flattened to linear*. The
  clearest picture of what happens when you have dependencies and no engine. Also the
  cost governor (#488).
- **OpenHands** — event-sourced replay and per-conversation isolation. The recovery half.
- **SWE-agent** — typed tool-bundle contracts. The declaration-discipline half (#493).
- **OpenClaw** — markdown workflows with semantic decision points. What real workflows
  look like before anyone formalises them (#491, and the concrete case in #471).

### Tier 3 — teach by absence (8)

Aider, Devika, gpt-engineer, Open Interpreter, Hermes, Claude Code, Codex, Linux.

Still useful, but as negative evidence — *what it costs to have no boundary* — not as
design input. Devika is the sharpest: nobody there chose to skip durable resume; they
accreted the fragments they could not avoid and omitted the rest silently. Linux is the
outlier that contributed the single best design rule anyway (§6).

**Practical consequence:** when a workflow-semantics question comes up, read Tier 1. When
the question is "what does the absence cost", read Tier 3. Do not average them.

---

## 4. The counterfactual — would Nodus have changed these systems?

Speculative by construction, and worth asking anyway, because it is the closest thing to
a market test available. Judged on architecture, not on adoption likelihood:

| System | Would a pre-existing Nodus have changed the design? | Why |
|---|---|---|
| **MetaGPT** | **Yes, strongly** | Its `Plan`/`Task` list is a DAG it flattens because it has nowhere to put one. Its own analysis says the planning layer belongs neither in the runtime nor the app. |
| **OpenClaw** | **Yes, strongly** | `.agent/workflows/*.md` are workflows written in prose because no executable form was available. |
| **MAF / ADK** | **Probably** | Both built a declarative serializable graph vocabulary inside Python. That is what a DSL is for, and both pay `_missing_callable` on every predicate as the price of doing it in a host language. |
| **CrewAI** | **Demonstrated** | The showcase exists and works. |
| **LangGraph** | **Unclear** | Its nodes are arbitrary Python written by data scientists in notebooks. A compile step is friction they would resist, whatever it bought. |
| **Temporal** | **No** | Temporal *is* the durable engine. Nodus would be a client of it, not an alternative. |
| **Claude Code** | **No** | Orchestration is handed to the model deliberately. A DSL does not change that decision; it is a different bet about where intelligence goes. |
| **SWE-agent / OpenHands / Aider** | **No** | Coding agents whose loops are genuinely model-driven. Their orchestration surface is small by design. |

**Two strong yes, two probable, one demonstrated, three explicit no.** That is a real
case and not a certainty — which is the accurate way to hold it. Note the shape: the
systems that would have benefited are the ones that *coordinate multiple actors*, not the
ones that run a single agent loop.

---

## 5. Where Nodus actually sits against peers

The gap is not nodes. It is **edges**.

| Capability | MAF | ADK | LangGraph | Nodus 5.0.4 |
|---|---|---|---|---|
| one → one | `SingleEdgeGroup` | ✓ | ✓ | `after` ✓ |
| fan-out, concurrent | `FanOutEdgeGroup` | ✓ | ✓ | `after` ✓ |
| fan-in / join | `FanInEdgeGroup` | `JoinNode` | ✓ | `after b, c` ✓ |
| predicate branch | `SwitchCaseEdgeGroup` + `Default` | route-match + `DEFAULT_ROUTE` | conditional edges | **absent** — #471 |
| concurrent-write merge | — | — | reducers | **absent** — #485 |
| join failure policy | fires only if all produced | — | — | **absent** — #475 |
| topology validated on reload | `graph_signature_hash` | — | checkpoint contract | **absent** — #470 |
| determinism boundary | — | — | versioned channels | **absent** — #494 |

Three of four structural edge kinds are present and correct — verified by execution, not
inference (`levels: [["a"], ["b", "c"], ["d"]]`). Everything missing is a **policy on an
edge**: what routes, what merges, what happens when a source fails, and whether the graph
you resume into is the graph you left.

### The identity problem, found four times independently

MAF (#470, reproduced), CrewAI (§9 Q5, flagged and pointed at the right place), Temporal
(*"harden checkpoint/resume so a graph reload is authoritative"*), OpenHands
(*"checkpoint-resume ≠ event-sourced replay"*).

Nodus persists **status, not topology**. The source is the record; the state file is only
progress. That is a coherent position, but it means a reload is not authoritative, and
today the mismatch surfaces as `Dependency cycle detected: z -> z` in code that has no
cycle.

---

## 6. The signature defect, and the decision it forces

Five instances of one shape — **a declaration that reads as a contract and binds
nothing**:

| # | The declaration | What enforces it |
|---|---|---|
| #467 | `FS_READ` capability | nothing — attached to no builtin |
| #473 | `CapabilityPolicy` over tool / syscall / agent / memory | nothing — not in `BUILTIN_CAPABILITIES` |
| #478 | `SyscallSpec.capability`, published by `syscall_list()` | nothing — read only by `to_dict()` |
| #490 | `nodus.toml` sections and keys | nothing — unknown keys silently ignored |
| #492 | `step … with { worker: "…" }` | nothing — runs in-process, reports success |

**For a language whose value proposition is *declare it, then inspect it before you run
it*, this is the worst available defect class.** It is not a bug in a feature; it is the
premise failing quietly.

The same shape drove the deny-by-default decision in v5.0.0, arrived at from a prior
audit. It has now recurred five times in surfaces that decision did not touch.

### Decision: enforce

**A declaration that the runtime accepts must bind, or must be refused at the point of
declaration.** "Accepted and ignored" is not a permitted third state.

This applies to new surfaces as a design rule and to the five above as work. The rule is
implementable because **Nodus already does it correctly in two places**, and both are
worth copying rather than redesigning:

- `std:tool` — input schema *and* return schema enforced, `required` derived, good
  messages (`builtins/tool_module.py`). Verified: wrong types, missing arguments and a
  wrong return shape are all rejected.
- `register_function(..., requires=…)` — the declared capability reaches the policy and
  the call is refused. Verified: `policy saw: [('danger', 'subprocess', 'host_function')]`.

So the pattern is inconsistency, not inability. Where a surface cannot enforce a
declaration, the declaration should not exist.

---

## 7. Libraries and frameworks: adopt, create, decline

### Adopt the design — these are language features, not packages

| From | What | Lands as |
|---|---|---|
| LangGraph | reducers (`LastValue`, `BinaryOperatorAggregate`, `NamedBarrierValue`) | a merge policy on the `state` declaration — #485 |
| MAF | `graph_signature_hash` | ~30 lines on the graph metadata — #470 |
| MAF / ADK | `SwitchCaseEdgeGroup` + `Default` / route-match + `DEFAULT_ROUTE` | conditional edges — #471 |
| Temporal | replay-safe clock and RNG | #494, option 3 |

Nodus does **not** pay the price these designs pay: MAF and ADK route predicates *by name*
because a closure cannot survive serialization (`_missing_callable`). Nodus rebuilds from
source, so a predicate can be an ordinary expression. Copy the vocabulary, not the
workaround.

### Adopt the code — one candidate

**gpt-engineer's `BaseExecutionEnv`** — 43 lines, MIT. Its audit's own words: *"Nodus
guests, Hermes tools, Claude Code SDK subprocesses, and Devika's `subprocess.run` all
needed a workload-execution provider that does not exist. gpt-engineer wrote the
interface."* It is the missing type behind #492 and the natural interface for the planned
`nodus-container` (#85).

### Create — three gaps, verified absent from all 32 published packages

1. **`nodus-eval`** — highest value. SWE-agent, MetaGPT and gpt-engineer each ship a
   benchmark harness. Nodus has per-release eval *documents* and nothing a user can point
   at their own workflow. Run a workflow N times, diff outcomes, score against
   expectations. It is also what makes #494's non-determinism *measurable* rather than
   theoretical.
2. **`nodus-budget`** — #488. `grep` over `nodus-governance` and `nodus-observability`
   finds nothing about spend; governance covers *authority*, observability covers
   *telemetry*. MetaGPT's `CostManager` / `NoMoneyException` is the reference. The shape
   is forced: Nodus cannot measure tokens, so this is a host-side accountant plus a
   `budget { max_cost: … }` dimension the loop consults.
3. **`nodus-journal`** — a durable, replayable trajectory log. `RuntimeEventBus` already
   carries structured events with `to_dict()` and pluggable sinks; nothing ships that
   persists or replays them. Substrate for #486 and #494. Distinct from
   `nodus-observability`, which is OTel/Prometheus/logging — telemetry, not a program
   record.

### Already planned, priority raised by this sweep

- **`nodus-scheduler`** (#88) — OpenClaw and Temporal both have durable scheduling; Nodus
  has none at any layer (#176). A Nodus port of any cron-driven agent currently loses a
  working feature.
- **`nodus-container`** (#85) — now with a concrete hook to plug into (#492) and an
  interface to adopt.

### Decline

Anything re-implementing the ReAct loop, planners, prompt assembly, edit formats or
repo-maps. All seventeen audits classify these as app-hosted content, and MetaGPT's is
explicit that its own `AgentExecutor` plan-once model is the least agentic component in
its ecosystem. Absorbing agent *content* would negate the boundary that makes the rest
defensible.

---

## 8. Open questions

1. **Does the edge-policy work close the gap, or is there a second tier behind it?**
   #471, #475 and #485 are all "policy on an edge." If those land and a peer comparison
   still shows a gap, the model is wrong rather than incomplete.
2. **Is `goal … over …` the right shape for iteration, given #480?** A goal re-runs a
   fixed graph. Runtime fan-out over an unknown-length list is the other iteration shape
   and has no form at all.
3. **What is the smallest thing that makes a reload authoritative?** #470 proposes a
   topology hash; Temporal's answer is that history *is* the program. Those are very
   different commitments and the cheap one may be sufficient.
4. **Would a second working implementation change the Tier-2 verdict?** CrewAI is one
   datapoint for the boundary holding. OpenClaw is the obvious second, and it is blocked
   on #471.

---

*Corpus: `C:\codev\{Aider, Autogen, Claude Code, Codex, Crewai, Devika, google adk, gpt
engineer, Hermes, Langgraph, Linux, MetaGPT, Open Interpreter, openclaw, OpenHands, swe
agent, Temporal} research`. Nodus verified at 5.0.4 by execution. Issues #465–#494. Peer
systems read at their checked-out commits without execution, except CrewAI's Nodus
showcase and `C:\dev\claw`.*
