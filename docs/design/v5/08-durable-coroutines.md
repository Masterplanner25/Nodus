# Durable coroutines — design for #180

**Status: proposal.** No code has been built. This document answers the one
question #180 has been open on since it was filed, and which every re-baseline
of it has restated rather than resolved:

> *"a coroutine has no step to re-enter, so 'resume from a checkpoint' has to
> mean something new."*

**Answer: it means a position.** A bare-coroutine checkpoint should resume *at*
the checkpoint, not from the top — the opposite of the workflow checkpoint
(#486). That is not a wish: the runtime already captures a coroutine's
continuation on every suspend, and §3 measures what is in it.

**Everything in §2 and §3 was measured against `main` at `316dfb5`**, by running
programs and reading the values out, not by reading the code and inferring. §9
says how to re-derive each figure. `tests/test_durable_coroutine_premises.py`
pins the four facts this design rests on, so a premise cannot rot silently while
the document still asserts it.

---

## 1. What #180 asks, and what is already done

The issue proposes two fixes.

**The near-term documentation half has shipped** and four successive
re-baselines have confirmed it: `OPERATOR_OR_EMBEDDER_RUNBOOK.md` §6.2 is titled
*"A bare coroutine is transient — only a workflow survives a crash (#180)"* and
carries the comparison table the issue asked for.

**What remains is the feature half**, verbatim:

> A coroutine checkpoint API — `checkpoint("label")` usable outside a workflow
> step — would allow bare coroutines to persist their state to the SQLite store
> and resume on restart. This is the same mechanism as workflow checkpoints but
> generalized.

The last clause is the part this document disagrees with. "The same mechanism,
generalized" is not available, because §2 shows the workflow mechanism is not a
checkpoint mechanism at all.

### 1.1 What a user gets today

`checkpoint` outside a step body is not a keyword — it is an ordinary
identifier:

```
fn main() {
    let c = coroutine(fn() {
        checkpoint "half-way"
        return 1i
    })
    spawn(c); run_loop()
}
```
```
Name error at cp_outside.nd:3:9: Undefined variable: checkpoint
```

`parser.py` recognises the word only when `self.workflow_step_depth > 0`, so
outside a step it parses as a variable reference. The word *is* named in
`lexer.WORKFLOW_BODY_KEYWORDS`, so #480's coupling is intact and the editor
grammar knows about it — checked, not assumed.

The `"checkpoint used outside workflow execution"` message in
`builtin_workflow_checkpoint` is therefore unreachable from source: the compiler
only emits that call from a `CheckpointStmt`, which only the step-body parse
produces. It guards a host calling the builtin directly.

---

## 2. A workflow checkpoint is not a checkpoint

Measured, not inferred. `_record_checkpoint` (`task_graph.py:1932`) writes:

| field | what it is |
|---|---|
| `label`, `step`, `task_id`, `timestamp` | which step said it had got this far |
| `state` | a snapshot of the workflow's **`state` cells** |
| `resume_state` | the same cells *without* this step's pending fold (#486) |

That is the whole record. **No execution position is stored** — not an
instruction pointer, not a frame, not a local variable. And it could not be: the
snapshot is of `state` cells, which are the workflow's declared shared data, not
the step's.

So a resume cannot land at the checkpoint, and does not try to. It re-enters the
step **from the top** with the cells restored, which is what #486 settled and
what CLAUDE.md records as the surprising part: *effects before the checkpoint run
again on every resume*.

### 2.1 What makes a workflow resumable, precisely

`VM._rebuild_workflow_graph` (`vm.py:2183`) resumes by **recompiling and
re-finding by name**:

1. read `workflow_source_code` out of the persisted run (or re-read
   `workflow_source_path`, warning that the rebuild is unpinned);
2. re-execute the module through `ModuleLoader`, with `_suppress_flow_execution`
   set so the rebuild does not spawn a fresh run;
3. `find_workflow_value(self.globals, flow_name)` — **look the workflow up by
   name** in the freshly compiled globals;
4. rebuild the graph, restore per-task bookkeeping, re-run what is unfinished.

The load-bearing ingredient is step 3. A workflow is a **named top-level
declaration**, so a fresh process can find it again in a program compiled from
the same text. Everything else in the resume machinery is bookkeeping on top of
that one property.

**This is why "the same mechanism, generalized" is not available.** A bare
coroutine's body is a `Closure`: a `FunctionInfo` (whose `addr` is an index into
one compiled chunk) plus a list of live `Cell` upvalues. There is no name to look
up and no declaration to find.

---

## 3. What is actually live inside a bare coroutine

### 3.1 The runtime already captures a continuation

`VM.save_current_coroutine_state(next_ip)` (`vm.py:1374`) runs on every suspend
and writes exactly this onto the coroutine:

| captured | type | durable? |
|---|---|---|
| `ip` | `int \| None` | **yes**, given §3.3 |
| `stack` | operand stack | **yes at a statement boundary** — §3.2 |
| `frames` | list of `Frame` | **conditionally** — §3.4 |
| `handler_stack` | list of int 4-tuples | yes |
| `deferred_return` / `_depth` | value, int | conditionally (a value) |
| `deferred_error` / `_depth` | value, int | conditionally (a value) |
| `module_ctx` | live VM context | no — **reconstructable** by re-loading the module |

This is the design's central observation. **A durable checkpoint does not need a
new mechanism; it needs the existing capture written down.** Every suspend
already performs it — into memory, where a `SIGKILL` takes it. The question
#180 has been open on is not *can a coroutine's position be captured* but
*can that capture be serialised*.

`tests/test_durable_coroutine_premises.py` reads this method's assignments out
of the source and fails if the set changes, so a new piece of per-coroutine
continuation state cannot be added while this table silently goes stale.

### 3.2 The operand stack is empty at a statement boundary

The hardest part of continuation capture is arbitrary intermediate values on the
operand stack — a half-evaluated expression holding a channel, a file handle, a
closure. **At a statement boundary there are none.**

Measured across three shapes of coroutine, at a builtin call in statement
position: `operand_stack_depth: 0`, every time.

A `checkpoint` statement *is* a statement boundary — `CheckpointStmt` compiles to
`compile_expr(label)`, `CALL`, `POP`, and the label is a string literal. So the
one place a durable checkpoint would capture is the one place the stack is
reliably empty. That is a property of where the construct sits, not luck, but it
must be **asserted rather than assumed** — a future expression-position
`checkpoint(...)` would silently break it.

### 3.3 Compilation is deterministic across processes

A saved `ip` is an index into a compiled chunk, so it is meaningful in a fresh
process only if identical source compiles identically.

It does. The identity probe was run in two separate interpreters with the cache
cleared; the entry addresses and every frame `return_ip` were **byte-identical**
(`diff` clean).

Two pieces of existing machinery make this usable rather than merely true:

- **#704** made the bytecode cache key `source_sha256` — content, not path and
  mtime. The question *"is this the same program?"* is already answered by
  content, and answering it any other way is the defect #704 fixed.
- **`_warn_on_source_drift`** already exists on the resume path, and
  `workflow_source_code` is already persisted per run (#469, #497).

So the pin a durable coroutine needs is the pin a durable workflow already has.

### 3.4 What is *not* durable, measured

Three cases, one probe:

| program | entry `display_name` | upvalues | a local that is not JSON-safe |
|---|---|---|---|
| `spawn(coroutine(holds_a_channel))` | `holds_a_channel` | 0 | `ch: Channel` |
| `spawn(coroutine(fn() { return named_worker(5i) }))` | `__anon_3` | 0 | — |
| `spawn(coroutine(make_closure(10i)))` | `__anon_1` | **1** | — |

Three distinct obstacles, and they are worth separating because they have
different answers:

1. **Identity.** Only the first row has a durable name. The second is the
   *idiomatic* spelling — a named worker wrapped in an anonymous thunk — and it
   is anonymous, so the durable case is the one users write least often. §5.
2. **Captured environment.** The third row closes over a local. Upvalues are
   `Cell` objects; their *values* may be durable, but **`Cell` identity is not
   reconstructable**. Two closures sharing one captured variable — which #671
   made work — would come back from a resume holding two independent cells, and
   a write through one would stop being visible through the other. This is a
   silent wrong answer, so it must be a refusal.
3. **Non-durable locals.** A frame local holding a `Channel` cannot be written
   down. Neither can a closure, an open handle, or a host object. This is #498's
   undeclared-serializability requirement one level deeper: there, a `state` cell
   could not hold a record and said so at persist time; here a *local* cannot
   hold a channel.

---

## 4. The decision

**A bare-coroutine checkpoint is a position marker.** `checkpoint "label"` in a
coroutine means: *the continuation at this point is durable; a resume continues
from here, and the effects before it do not run again.*

This is the opposite of the workflow checkpoint, and the asymmetry should be
stated in the language documentation rather than smoothed over. The reason is
structural, not a matter of taste:

- A **step** has a re-entry point that survives a process — its name in the
  workflow declaration — and no capturable position, because what is persisted is
  the workflow's shared `state`, not the step's frame.
- A **coroutine** has no re-entry point that survives a process, and a fully
  capturable position, because the suspend machinery already captures it and the
  stack at a statement boundary is empty.

Each construct gets the semantics its substrate can actually support. The issue
frames "a coroutine has no step to re-enter" as the problem; it is in fact what
makes the *better* semantics available, since there is no re-entry point to be
tempted into re-running.

### 4.1 It must refuse rather than lie

Every obstacle in §3.4 is detectable *at the checkpoint*, before anything is
written. So:

> **`checkpoint` in a coroutine fails loudly at the moment it cannot honour its
> promise**, naming the local, the upvalue, or the anonymous entry point that
> blocks it.

This is the house rule, and it has three precedents in this tree, all of which
were arrived at after the silent version shipped:

- **#427/#657** — `nodus fmt` refuses rather than writing a file it does not
  fully understand, after a release in which it silently dropped `each`.
- **#498** — a `state` cell refuses a non-serializable value at persist time.
- **#584** — the copy of a question that could not answer correctly reached for a
  plausible substitute instead of failing, and the drift stayed invisible for as
  long as the substitute looked right.

A durable checkpoint that silently degrades to "re-run from the top" would be
#584 exactly: right whenever the coroutine happened to be idempotent, and a
silent double-execution otherwise.

---

## 5. Identity: what `spawn` cannot tell you

A resumed coroutine needs its entry closure rebuilt, and §3.4 shows the idiomatic
spelling is anonymous. Three options, in the order they were considered:

**A. Infer a name.** Rejected. `__anon_3` is stable across processes (§3.3) but
it is a *position* in the compiled program, so it is stable only while the source
is byte-identical — which the pin already guarantees — and it silently renames
when an unrelated earlier closure is added. It is an index dressed as a name, and
a resume that binds to the wrong function is worse than one that refuses.

**B. Require a named top-level function with no upvalues.** The first row of
§3.4. Honest and implementable, but it makes the durable path the one users write
least, and the diagnostic ("your coroutine is anonymous") arrives at the
checkpoint, deep inside a program that already ran.

**C. A declared durable spawn.** Recommended. Durability is declared where the
work starts, not discovered where it checkpoints:

```
durable spawn worker(job_id)     // named top-level fn, JSON-safe args
```

The declaration is what makes the entry point findable — the same property §2.1
identifies as the whole reason workflows resume — and it moves every refusal in
§4.1 that can be decided statically to **compile time**, where `goal_validation.py`
already puts `reached("label")` checking for exactly this reason (#409).

What cannot move to compile time is the local-holding-a-channel case, which
depends on runtime values. That stays a refusal at the checkpoint.

**C is a proposal, not a decision.** It adds surface syntax, and §7 lists what
must be settled before it earns that.

---

## 6. Dependencies

- **#174 blocks the guarantee, not the code.** The default store is
  `LocalWorkflowStore`, file-backed JSON, explicitly not crash-safe; it becomes
  SQLite at 6.0.0. Shipping "your coroutine survives a crash" on top of a store
  that does not is a documented promise the default cannot keep — and the failure
  mode is the one this feature exists to prevent. **A durable coroutine must
  refuse a non-crash-safe store, or land after #174's step 2.**
- **#486** decided the workflow checkpoint's meaning; §4 deliberately diverges
  from it and must say so wherever `checkpoint` is documented.
- **#704** supplies content-addressed program identity (§3.3).
- **#498** supplies the durability-refusal precedent (§4.1).
- **#182 / #778** are not blockers but are adjacent: a resumed coroutine's timers
  meant something on a clock that no longer exists. A durable coroutine that was
  sleeping must decide whether its remaining sleep is re-derived from wall time
  or discarded. Now that reading and waiting are one seam, that question has a
  single place to live.

---

## 7. Open questions this document does not settle

1. **Does `durable spawn` earn surface syntax?** #336 proposed a `spawn { }`
   keyword and was rejected because the grammar position it needs is the one
   `match` occupies (#717). A builtin taking a function reference may be enough.
2. **What happens to a coroutine that is *blocked* at crash time?**
   `BLOCKED_REASONS` has seven members; a coroutine parked on `channel_recv` has
   a durable position and a counterparty that no longer exists. The likely answer
   is that a checkpoint is only honoured while runnable, but that needs stating.
3. **Sleep, on resume.** §6's last bullet.
4. **What resumes it?** A workflow has a sweeper and `rehydrate_runs`. A durable
   coroutine needs an owner, and the answer is probably "the same store and the
   same sweeper", which makes it a run in the store — worth checking whether that
   collapses back into a one-step workflow with better semantics.
5. **Cost.** The frame-serialisation and refusal machinery is small; the store
   schema, sweeper integration and CLI surface are not. This is not a
   single-PR feature, and §8 stages it accordingly.

---

## 8. Staging

Each stage is independently useful and independently abandonable.

| stage | what | value if the next stage never happens |
|---|---|---|
| 0 | `tests/test_durable_coroutine_premises.py` — pin §3's four facts | the design's premises stop being folklore |
| 1 | `checkpoint` in a coroutine is a *diagnosed* error, not `Undefined variable` | the current dead end names itself and points here |

**Stage 1 must not reserve the word.** `checkpoint` is contextual on purpose, and
`let checkpoint = 42i` outside a step body compiles and runs today — verified,
because the obvious implementation of stage 1 breaks it. The shape that is safe
to diagnose is narrower: an identifier `checkpoint` **immediately followed by a
string literal**, in statement position, outside a step. Today that parses as two
consecutive expression statements — a bare variable reference and a discarded
string — which is never meaningful code, which is why the current error is
`Undefined variable: checkpoint` rather than a syntax error.

| 2 | a durability predicate over a live coroutine — frames, locals, upvalues, entry identity — reporting *why* not just *whether* | reusable by any later persistence work; testable with no store |
| 3 | serialise and restore a continuation **in-process** (checkpoint, discard, rebuild, continue) | proves §3's claim end-to-end before any store schema exists |
| 4 | the store schema, `durable spawn`, sweeper, CLI | the feature |

Stage 3 is the one that falsifies this document. Everything before it is
plumbing that would survive being wrong; if a continuation cannot be rebuilt
in-process from its own serialised form, §4 is wrong and no amount of store work
would have saved it.

**Stage 0 ships with this document.**

---

## 9. How to re-derive every measurement here

The probes are small and are deliberately not committed as fixtures — the
committed artefact is `tests/test_durable_coroutine_premises.py`, which asserts
the conclusions. To re-measure from scratch:

- **Operand stack and frame locals (§3.2, §3.4):** register a host function with
  `NodusRuntime.register_function`, call it in statement position inside a
  coroutine, and read `RT.active_vm().current_coroutine` — `stack`, `frames`,
  and each frame's `locals` merged with `locals_array` via `locals_name_to_slot`.
  Test each value with `json.dumps`.
- **Cross-process determinism (§3.3):** run that probe twice in separate
  interpreters with `.nodus/` removed, and `diff` the reported `addr` and
  `return_ip` values. Note the CLAUDE.md trap: the cache resolves against the
  *script's* project root, so clearing `.nodus/` in the repo is not enough when
  the script lives elsewhere.
- **What a workflow checkpoint stores (§2):** read `_record_checkpoint` in
  `task_graph.py`; the entry it appends is the whole record.
- **Today's error (§1.1):** run the four-line program in that section.
