# External Audit Findings Ledger

Verification record for audits performed **against** Nodus by an outside reader,
as distinct from [AUDIT_INDEX.md](AUDIT_INDEX.md), which holds the prompts we run
*ourselves*.

Every finding in an external audit gets a verdict here — **confirmed**,
**wrong**, **partly wrong**, or **reframed** — with the command or code
reference that settled it. Two reasons this file exists:

1. **A finding is a claim, not a fact.** The first audit in the series was
   directionally sound and factually wrong in five places, all in the same
   direction: *"Nodus does not have X"* where X existed in a file the auditor
   did not think to open. An unverified negative finding turns into work we do
   not need, or a doc correction that makes the docs worse.
2. **Later audits should start here.** Repeat findings across audits are a
   signal about the codebase; repeat *errors* across audits are a signal about
   what the codebase fails to make discoverable. Both are worth more than any
   single audit's conclusions.

---

## Audit 01 — "Nodus: a durable workflow runtime that happens to be a language"

| | |
|---|---|
| **Source** | `C:\codev\Claude Code research\docs\nodus-architecture-audit.md` |
| **Type** | Adversarial architecture audit, comparator Claude Code (grounded), Temporal + LangGraph (conceptual) |
| **Audited at** | commit `3376702`, v4.1.1 |
| **Verified at** | commit `6205e72`, 2026-08-15 |
| **Hypothesis under test** | *"An orchestration DSL and embedded runtime for building agentic systems"* |

The audit's headline verdict — *embedded capability-confined runtime is the
defensible claim; "orchestration DSL" understates where orchestration actually
lives; "for building agentic systems" is not supported* — **survives verification
intact.** Every error found below is in a negative finding, and none of them
changes that conclusion.

### Confirmed

| § | Finding | How it was verified |
|---|---|---|
| 06 | No model anywhere in the core | grep for openai/anthropic/llm/inference across `src/nodus/`: **0 hits** |
| 15 | No cancellation | grep `cancel` across `src/nodus/`: **1 hit**, `print("Login cancelled.")` → **#395** |
| 18 | Step ordering is bypassable | Executed: `build["steps"][1]["fn"](nil)` ran `test` with `lint` never having run → **#394** |
| 04 | No orchestration opcodes | See below — verified from emitted bytecode, not from the dispatch table |
| 04 | `workflow`/`goal` lower to a plain map before compilation | `workflow_lowering.py:78`; confirmed by printing `keys(build)` from guest code |
| 13 | A goal's completion is structural, never semantic | Confirmed — nothing evaluates an objective |
| 23 | Cycles are not caught at compile time | `nodus check` passes a cyclic workflow → **#396** (narrower than the audit states, see below) |

#### §04 in detail — the orchestration-opcode claim

Worth recording how this one was settled, because the first attempt used the same
method that produced every error in the **Wrong** table below: a grep of the two
directories where the answer *ought* to live.

The claim is that no orchestration semantics reach the instruction set. Verified
by compiling a program that exercises every relevant construct:

```
workflow ship {
    step build { return 1i }
    step test after build { return 2i }
    step review after test { return action agent "reviewer" with { diff: "x" } }
}
let c = coroutine(fn() { return 1i })
spawn(c)
let ch = channel()
send(ch, 1i)
let v = recv(ch)
let r = run_workflow(ship)
```

`nodus dis` emits 13 opcodes, all ordinary — `BUILD_LIST BUILD_MAP CALL
FRAME_SIZE HALT JUMP LOAD MAKE_CLOSURE POP PUSH_CONST RETURN STORE STORE_ARG` —
with every construct appearing as a builtin call (`CALL coroutine 1`, `CALL spawn
1`, `CALL channel 0`, `CALL send 2`, `CALL recv 1`, `CALL __action_agent 2`,
`CALL run_workflow 1`). The workflow is `BUILD_MAP`/`BUILD_LIST`/`MAKE_CLOSURE`
— a data structure. **Confirmed.**

Doing it properly surfaced a defect in our own tracker: **#336 asserted a `SPAWN`
opcode that does not exist**, in both its title and its "no new opcode" scoping
note. It was the only thing in the repo contradicting §04, and as written it
would have sent a v5 implementer looking for a dispatch entry that isn't there —
and, if they concluded they had to add one, into the frozen-set amendment
process (#366) for no reason. Corrected and retitled.

| § | Claim | Reality |
|---|---|---|
| 23 | No compile-time check for undefined `after` targets, and duplicate step names "not found" — billed as *"the audit's most significant negative finding"* | Both exist **at the audited commit**: `parser.py:528` duplicate-name, `:534` unknown-dependency. Only cycle detection is genuinely missing from `check`, and #323 already moved it to graph-build time, ahead of the scheduler. 1 of 4 missing, not 4 of 4 |
| 22, 24 | No disassembler; "a `disasm` command was not found" | The command is **`nodus dis`** — a full disassembler with source positions |
| 22 | No bytecode version field or compatibility policy | `BYTECODE_VERSION = 4` at `compiler.py:68`; `COMPATIBILITY_MODEL.md`, `BYTECODE_REFERENCE.md` |
| 10 | No idempotency keys or exactly-once machinery | `@exactly_once` + `effect_action_id`/`effect_resolve`, present at the audited commit. The audit's *conclusion* stands — it is not a distributed guarantee, which the code's own comment states — but the fact is wrong |
| 04 | "Forty-three opcodes" | **49.** The list omits EQ/NE/LT/GT/LE/GE, all emitted at `compiler.py:967–972`. Conclusion unaffected |
| 13 | goal ≡ workflow except for event names | False, and materially so — see below |

### Missed

**The `goal`/`workflow` divergence — the single most consequential finding, and
the audit reported its opposite.** `run_task_graph` branches on `execution_kind`
at `task_graph.py:1101` for **retry scheduling**: a `workflow` defers
(`retry_scheduled`, run ends, a sweeper must resume it) while a `goal` retries
in-process. Same source, same step, same options, one `nodus run` → workflow **1
attempt**, goal **3 attempts**. The result maps also differ in key set.

Two issues came out of it, and they share a root:

- **#392** — step-level `retries` are honoured only by `nodus workflow-run`; the
  embedding API returns `ok: True` after one attempt with the retry dropped. That
  is the path `nodus-mcp-server` uses, and it is the same success-shaped-failure
  signature as #376.
- **#393** — unify the retry path. **Decision taken: unify**, rather than
  document the difference.

`CLAUDE.md` asserted the audit's error as fact — *"Runtime treats them
identically; convention is semantic"* — which is what a contributor or agent
reads before writing host wrappers. Corrected.

### Reframed rather than fixed

**§00/§06: "for building agentic systems does not hold — there is zero model
invocation in the core."** Factually correct, and **not a defect.** The absence
of a model is what makes the semantic boundary unblurrable: because the runtime
cannot perform inference, every semantic decision *must* cross a typed boundary
to a host handler. The audit itself identifies this as the cleanest architectural
argument in Nodus's favour (§05) and then scores it as a failed claim, because it
is testing the tagline rather than the design.

The resolution is positioning, not code: Nodus is **an ecosystem for building
agentic hosts**, not a framework for building agents. Hosting is the verb. See
the open decision below.

---

## Audit 02 — "Nodus Language Architecture Audit — In Light of Modern Agent Systems"

| | |
|---|---|
| **Source** | `C:\codev\Codex research\NODUS_LANGUAGE_ARCHITECTURE_AUDIT.md` |
| **Type** | Adversarial architecture audit, comparative baseline `openai/codex@9afb96fa` |
| **Audited at** | commit `3376702`, v4.1.1 — **the same commit as Audit 01** |
| **Verified at** | commit `75221c7`, 2026-08-15 |
| **Hypothesis under test** | identical to Audit 01 |

Materially more rigorous than Audit 01: line-level citations throughout, explicit
`[Observed]` / `[Inferred]` / `[Unknown]` labels, and 23 numbered findings. Its
verdict — *"capability-gated guest language for host-supervised workflow
execution"* — agrees with Audit 01's on the substance.

### Confirmed, and filed

| F | Finding | Verification | Issue |
|---|---|---|---|
| **F6** | `action agent` blocks the scheduler; concurrent agent steps serialise | Measured: two 1.0s agent calls in independent steps took **2.73s**, handler overlap **−0.01s** | **#398** |
| **F8** | Resume re-executes the module source | Confirmed — and worse than stated, see below | **#399** |
| **F14** | `nodus graph <file>` executes the file | `fs.write` probe fired while the command reported "No graph plan produced" | **#400** |
| **F11** | Static analysis never enters a workflow body | Confirmed, and wider — `nodus check` reports no undefined symbol in ordinary code either | **#401** |
| **F17** | `waiting_senders` is dead code; no backpressure | One grep hit, the declaration; `send` on a full channel raises | **#402** |
| F13 | Cycles detected at run time, not parse time | Already filed from Audit 01 | #396 |
| F16 | No cancellation, no compensation | Already filed from Audit 01 | #395 |
| F19 | Embedding isolation is per-script, not per-orchestration; process-globals shared | Independently corroborates the root cause behind #376 | #390 |
| F12 | Parse-time dependency-name validation is the best argument for the language | **Independently confirms the correction to Audit 01 §23** | — |
| F5 | Zero model integration, *and this is correct* | 0 grep hits; and note this audit calls the restraint a design virtue rather than a failed claim | D1 |
| F10 | Persistence engineering is genuinely careful | `_atomic_write_json` + dir `fsync` confirmed | — |

### Wrong

| F | Claim | Reality |
|---|---|---|
| **F3** | *"`goal` is `workflow` with a different marker string… same execution path"* | The same error Audit 01 made at §13. `task_graph.py:1101` branches on `execution_kind` for retry: workflow **1 attempt**, goal **3**. See #393 |
| **F9** | *"Dependency ordering… none is bypassable from Nodus code. This is the project's strongest and most defensible claim."* | Ordering **is** bypassable — `build["steps"][1]["fn"](nil)` runs a step whose dependency never ran (#394). Audit 01 got this right at §18 |
| **F2** | *"The full 39-opcode set"* | **49.** Audit 01 said 43. Two auditors, same commit, two different undercounts |

### Beyond F8 — what chasing it found

F8 says resume re-executes the module source. Verified, and it produces a failure
the audit did not reach:

**Cross-process resume fails for any script that uses the `run_workflow` return
value** — which is how every guide example is written. Suppression during rebuild
makes `run_workflow` return nil, the script's next line indexes nil and raises, a
bare `except Exception: return None` swallows it, and the caller reports
`Unknown graph` for a run that `nodus workflow runs` lists as `waiting`. Discard
the result and the identical workflow resumes correctly.

**And every failed attempt performs the module's side effects.** Suppression
covers `run_workflow`, `run_goal` and `print` — nothing else. Five resumes, all
returning `ok: false`, produced five filesystem writes. Filed as **#399**.

---

## What the two audits together are worth

Both audited `3376702`. Independent auditors, same hypothesis. The comparison is
more informative than either audit alone.

**Where they disagreed, the disagreement marked a real defect — both times.**

| Question | Audit 01 | Audit 02 | Truth |
|---|---|---|---|
| Is step ordering bypassable? | §18 **yes** | F9 **no** | Audit 01 — #394 |
| Do concurrent agent calls overlap? | §06 **yes** | F6 **no** | Audit 02 — #398 |

Each caught something the other got backwards, and neither error was careless:
Audit 01 saw that `builtin_agent_call_async` exists and read existence as
reachability; Audit 02 saw that `ready_tasks()` gates dispatch and read the engine's
guarantee as the language's.

**Where they agreed, they were both wrong — twice.**

| Claim | Audit 01 | Audit 02 | Truth |
|---|---|---|---|
| `goal` ≡ `workflow` | §13 | F3 | Diverge on retry — #393 |
| Opcode count | 43 | 39 | **49** |

**The methodological conclusion: agreement between independent audits is not
corroboration.** Two readers following the same reasonable path reach the same
wrong place. The `goal`/`workflow` divergence is invisible to code reading and
took thirty seconds to expose by running the same source twice; the opcode count
was wrong in both and neither matched the stale docs (which said 47 — the #366
bug, since fixed and now gate-enforced).

Treat convergent findings as *unverified*, and divergent findings as *high-value
leads*.

## Patterns across the series

*Status after two audits. P1 partly refuted, P2 and P3 strengthened, P4 added.*

**P1 — Negative findings cluster on "searched the expected location."** All five
factual errors in Audit 01 are the same shape: validation was sought in the
analyzer and lowering but lives in the parser; the disassembler was sought as
`disasm` and is `dis`; idempotency was sought in the graph engine and lives in a
compiler lowering; the version field was sought in a bytecode header and lives in
the compiler. No error came from misreading code that was found — every one came
from not finding code that exists.

P1 is not only an auditor's problem. **#336 asserted a `SPAWN` opcode that does
not exist** — written by us, about our own instruction set, and it sat there
through the opcode-freeze work of #366. The audit was right and our tracker was
wrong. Treat P1 as a property of the codebase's discoverability, not of any
particular reader's care.

The method that settles these is not grep. For §04 it was *compile a program
using every construct and read the emitted opcodes*; for §13 it was *run the same
source as a `goal` and as a `workflow` and compare*; for §18 it was *call the step
closure and see whether the dependency ran*. Each took a few minutes and each
produced an answer a search could not.

**Audit 02 largely refutes P1 as an auditor property.** It cited line numbers
throughout, found the parse-time validation Audit 01 missed (F12), and made only
one location error — the opcode count, which Audit 01 also got wrong, differently.
Its errors are a different shape: **reading a capability's existence as its
reachability** (F9, F3, and Audit 01's §06 all have this form). `agent_call_async`
exists but `action agent` cannot reach it; `ready_tasks()` gates dispatch but the
step closure is reachable around it; `goal` and `workflow` share a lowering
function but not an execution path. So keep P1 as a statement about *the codebase
being hard to search*, and read the newer failure mode as P4.

**P2 — The missing artifact behind P1: nothing states where a guarantee is
enforced.** An auditor asking "is ordering an invariant?" or "is there a version
field?" has to reconstruct the answer from the source every time, and a
reconstruction can miss a file. `EXECUTION_INVARIANTS.md` is the natural home and
does not currently carry this. The shape that would have prevented four of the
five errors:

| Guarantee | Enforced at | Bypassable? | Test |
|---|---|---|---|
| filesystem confinement | `vm.py:_ensure_path_allowed` (after `realpath`) | no route from guest code | … |
| step ordering | `task_graph.ready_tasks()` | **yes** — via the lowered map (#394) | … |
| duplicate step names | `parser.py:528` | no | … |

This is worth building *before* the next audit lands, so subsequent audits check
it rather than re-derive it — and so a claim of the form "Nodus has no X" is
cheap to settle.

**P3 — Closed issues are not proof.** Four closed issues appeared to cover
findings that verification suggested were still live. Three were genuinely fixed
(#323, #240, #109); **#226 was fixed on one entry point out of five** and its
closing comment overstated the scope ("used by `nodus run`" — it is
`workflow-run`). Same shape as #106 earlier this cycle: closed while half-broken.
When an audit contradicts a closed issue, re-test before trusting either.

Audit 02 supplies a fourth instance from a different direction: **#294 added
`agent_call_async` and the capability is real, but `action agent` — the documented
way to call an agent — never reaches it** (#398). A feature can be delivered,
tested, and closed on a path nobody uses. The generalisation across #226, #294 and
#106 is the same: *closing an issue on one entry point is not closing the issue.*

**P4 — Existence read as reachability.** The dominant error in Audit 02, and one
of Audit 01's two: a mechanism is found in the source and assumed to be on the
path that matters. `agent_call_async` exists → "concurrent agent calls overlap"
(false: `action agent` calls the sync builtin, and the async one falls back to sync
in graph contexts anyway). `ready_tasks()` gates dispatch → "ordering is not
bypassable" (false: the step closure is reachable through the lowered map).
`workflow` and `goal` share `_lower_flow_ast` → "identical execution path" (false:
`run_task_graph` branches on `execution_kind`).

This is a harder error to avoid than P1, because the code that was read was read
correctly. The only reliable defence is to **exercise the documented path**, not
the mechanism — call `action agent` from a workflow step and time it; call
`run_workflow` and `run_goal` on the same source and compare. Every P4 error in
both audits fell in under five minutes to a test of the user-facing path.

It also predicts where to look next: any capability whose issue was closed on one
entry point (P3) is a candidate to be unreachable from the documented one (P4).

---

## Open decisions

### D1 — Positioning: "agentic host ecosystem", not "for building agentic systems"

The tagline claim the audit rejects is a wording problem, not a capability gap.
Candidate framing: *an ecosystem for building agentic hosts* — the runtime
supplies durable, inspectable, capability-jailed orchestration and a clean
handoff to externally-supplied semantic actors; the model loop belongs to the
host.

Touches README, `llms.txt`, `llms-full.txt`, PyPI description, wiki. **Not yet
decided** — deferred until more of the audit series is in, since positioning
should answer all of them at once rather than one.

### D2 — `goal` after unification

Once #393 lands, `goal` and `workflow` are the same construct with two spellings.
Either give `goal` something a workflow lacks — a completion predicate
re-evaluated after each step is the natural candidate, and the readiness loop is
already shaped for it — or deprecate it and let a workflow's name carry the
intent. Shipping both as distinct keywords while the implementation makes no
distinction is what produced this ledger entry.

---

## How to add an audit

1. Record source, audited commit, and verification commit.
2. Verify each finding by execution or a code reference — **not by agreement.**
   A finding that reads plausibly and cites a real file can still be wrong.
3. Give every finding a verdict. Withdraw your own verification errors in place;
   there is one in Audit 01 (a cycle result read as a bare string is in fact a
   structured `error` value with `kind`/`message`).
4. File issues for confirmed findings; record reframings and decisions here.
5. Add to **Patterns** only what two audits support, or mark it as awaiting
   confirmation, as P1–P3 are.
