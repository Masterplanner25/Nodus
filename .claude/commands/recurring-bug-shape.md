---
description: "The recurring Nodus bug shape: a correct check on one path with a sibling path that bypasses it. Instance table and worked examples; read before fixing a defect of this shape."
---

# The recurring bug shape

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## The recurring bug shape — a check on one path, a sibling path that bypasses it

This codebase's most common defect is not a wrong check. It is a **correct check that only one
of several paths goes through**. It has surfaced **once per row of the table below**, from
v5.0.0 onward — count the rows rather than trusting a word here, which had gone stale by one,
and note that the range is deliberately open-ended for the same reason. That frequency is why
it gets its own section: when you find one, the next question is
always *"what else has this shape?"* — not *"is this fixed?"*

Instances, all confirmed by reading the code rather than inferred:

| # | The check | The path that skipped it |
|---|---|---|
| #392/#393 | retry-vs-defer decision | lived in an `inline_retries` wrapper argument passed by **1 of 5** callers |
| #405 | sandbox / authority | a **derived** VM built a fresh VM and shed the parent's limits |
| #405 | capability policy | consulted at `_invoke_host_function` but **not** `VM.call_builtin` — where `subprocess`/`http` live |
| #427 | formatter round-trip | `nodus fmt` corrupted files whose nodes it did not know |
| #353 | `--help` handling | a per-command guard, so every new subcommand shipped unguarded — recurred **four** times |
| #411 | `@exactly_once` / `@retry` envelope | lowerings called **shadowable** names; a program could replace its own envelope |
| #411 | workflow state | same defect via `workflow_state()` — found only by asking what else had the shape |
| #453 | auto-run-`main` suppression | read the AST; a **cached** module has none, so it ran `main()` twice from the second run on |
| #387 | call-depth cap | lived in wrappers; a directly constructed `VM()` had none |
| #424 | every timeout | all of them bound the **instruction stream**; a host agent handler is not in it |
| #185 / #390 | per-tenant memory, run ownership | module-scope globals, so every participant in a process shared them |
| #487 | which node declares a name | four sites enumerated declaration forms; three had never heard of `goal … over …` |
| #518 | workflow-state rewriting | `_StateRewriter` knew `=`, `x[i] =`, `x.f =` — and not `+=`, so it read `nil` |
| #521 | which program `run_source` runs | the `isfile` branch **and** the path+mtime bytecode cache, read **and** write |
| #473 | the capability policy | consulted for the **four sandbox groups only**; `tool_call`, `syscall`, `agent_call` and the whole memory store were invisible to it |
| #457 | module-memo identity | **three** memo-consult sites (`_build_metadata`, `_parse_module`, `_load_module`), each deciding for itself |
| #476 | a run's lifecycle | a run is **two stores** (`.nodus/graphs/` + the workflow store) and each was cleaned without the other — in **both** directions |
| #400 | does inspection execute | `nodus graph` **and** `graph show`, plus the bytecode cache underneath — the #521 shape again |
| #401 | does static analysis enter a step body | **two** walkers skipped it: the type analyzer and the LSP diagnostics engine |
| #394 | may this closure be entered | **four** doors, one of them outside `vm.py` — and then the bytecode cache, which dropped the mark and reopened it on run 2 |
| #584 | which graph is this request's | two copies of `_graph_metadata`; the one that had **not** learned to read the VM's own events leaned on a process-global fallback instead |
| #632 | stop the background work before the directory goes | **two** sweepers; #591 stopped the workflow one and left `_worker_sweeper_loop` running, so the symptom outlived its own fix |
| #480 | is this word a keyword | `each` matched by a bare literal in `parser.py`, so `lexer.ALL_KEYWORDS` — which editors, docs and `--consumers` all read — never named it |
| #657 | does `fmt` render this node | the completeness guard walks **node types**; `each` and `budget { limits }` are new **fields**, so every node had a case and `fmt` dropped them silently |
| #662 | what names are bound in a step body | the lowering binds `after` / `each` / `compensates` deps; the analyzer pushed the same scope and bound **none** — two answers to one question, drifted |
| #671 | where does this name live | `SymbolTable._resolve_upvalue_in` and `VM.store_name` disagreed, and **neither fix alone is reachable** — fixing the resolver makes the read correct and still loses the write; fixing the VM is dead code while the compiler emits `STORE_LOCAL_IDX`. Named once as `VM.binding_namespace` now |
| #691 | which chunk was this closure compiled against | the detached module VM wrapped caller closures in a `_ClosureProxy`; the in-VM cross-module frame (the path a **step body** always takes) wrapped nothing and checked nothing |
| #696 | the same question, for a closure going the **other way** | all three of #691's context sources record something a call is still *inside* of; a **returned** closure is called after the frame has popped, so all three are empty |
| #704 | which program is this cache entry for | #521 fixed the branch, the cache **read** and the cache **write** — and the key itself still answered by path + mtime, so an edit inside the platform's timestamp resolution was invisible to all three |
| #754 | how is a VM for this service confined | `RuntimeService.graph` passed the path settings to `run_source` by hand instead of using the shared guard — a second implementation that *structurally could not* learn a capability flag, since `run_source` builds its own VM and takes none |
| #167 | is this a valid extension name | the VM refused at construction and `NodusRuntime` did not refuse until its first `run_source` — the two agreed on the **answer** and disagreed on the **moment**, which is the same shape with a different disguise |
| #182 | where does the scheduler get time | `clock_fn` was injectable; the idle path called `time.sleep` directly. Half a seam, and the unsafe half — inject a clock and `run_loop()` **hangs** |
| #769 | which VM did this construct build | a test helper patched `VM.__init__` process-wide and returned the first VM **any** thread built |
| #770 | who stops the background work | two tests started a server and two sweepers and stopped none; #632's lesson, in two more places |
| #791 | is this flag one this command takes | `commands.py` declares every subcommand's flag set correctly and **nothing consulted it at dispatch**, so an unknown flag was dropped in silence — and the flag people type on `workflow cleanup` to avoid destroying state is `--dry-run`, which that command does not have. The fix needed **two** layers, because six commands take no flags and so never reached a parser at all, and `nodus test` parsed in a second module with its own copy of the names |
| #797 | does a user see this deprecation | the notice was correct, careful, named the exact command to type — and was a `DeprecationWarning` raised outside `__main__`, which Python's default filter **discards**. Not two places disagreeing: one place, and a filter downstream of it that threw the answer away |
| #609 | which command warns about an annotation that becomes an error | `nodus check` and the LSP both read `parser.unknown_type_names`; the **run** path threw the parser away — so the one command that will start *failing* at 6.0.0 was the one saying nothing |
| #778 | how long has this task run against its timeout | one question, **four** sites — two stamping `task_started_at`, two comparing against it — each reading `runtime_time_ms()` for itself, so #182's seam could not reach any of them |
| #822 | did this step write this state cell | `cell = v` went through `TrackedState.__setitem__`; `cell[i] = v` lowered to a **read** of the cell plus an in-place mutation, so the tracker never saw it — no conflict warning, no `merge:` policy, no fold-cell refusal. The *documented* spelling for updating one element was the unwatched one |
| #394 / #180 | may this function's body run outside its workflow (`guard_step_entry`) | stage 3's `restore_continuation` rebuilt frames from data, a **fifth door** into a function; the resume re-checks only the entry closure, so a deeper frame naming a step body would have run it. Caught before merge by `test_step_entry_guard`'s Frame-construction enumeration, not by reading the code |

**#182 adds the variant that is worst to inherit: half a seam.** `clock_fn` was
injectable and the test harness overrode it, so the tree *looked* like it could
run on a supplied clock. It could not — the idle path waited through
`time.sleep`, so a supplied clock was read and never waited on, and
`run_loop()` spun forever on a `now` that never moved. Measured: a coroutine
sleeping 800 ms finishes in 926 ms on the host clock, **never** on a frozen one,
and 44 ms once waiting went through the same object.

The lesson generalises past clocks. **A seam that covers the read and not the
write is worse than no seam**, because the missing half is invisible until
someone uses the half that exists — and the failure is a hang rather than an
error. When you make something injectable, ask what else has to move with it;
here the pair is obvious in hindsight and was split for years. The fix was one
object with both operations, so an implementation answers both or neither.

**And two clocks legitimately remain, which is the part worth copying.** Event
timestamps, `created_time` and `last_resume` still read the host clock: they
answer *when did this really happen*, which a simulated clock would falsify.
That is a real distinction, so it is stated in the code rather than left for a
reader to infer — and the one member of that group which did **not** fit the
reasoning (the task-timeout comparison) was filed as #778 rather than quietly
left. A split you can justify is fine; a split nobody wrote down is the next row
of this table.

**#778 then sharpened the criterion, which is the more useful half.** The
grouping was *scheduling clock vs. wall-clock fact*, and the task timeout was
inside it and uncomfortable. The line that actually holds is **reported vs.
compared**: the other three are only ever read out, so a virtual reading merely
looks odd in a log, while the timeout was *subtracted from* — and a comparison
across two clocks is not approximate, it is a different question. Anything you
put on the host clock for good reasons, check whether something subtracts it.

**#167 adds a variant worth naming, because it is not a disagreement.** Its two
sites agreed completely about which extension names are valid. They disagreed
about *when* they would say so: the VM refused at construction, `NodusRuntime`
not until its first `run_source` — where it surfaced as a bare `ValueError`
instead of the result dict that method promises. Every other row above is two
places giving different **answers**; this is two places giving the same answer at
different **moments**, and only one of those moments is the one a caller
experiences. So "do these agree?" is not the whole question — ask *when* each one
speaks.

It also shows how the shape survives a full green suite: every test constructed a
`VM` directly, while the documented entry point is `NodusRuntime`. **The tested
path and the documented path were different ones**, which is #691's lesson on a
different construct. Gate 10b caught it against the built wheel, before anything
immutable existed — which is the argument for writing those probes before the
tag, not after.

**#696 is the one to read on "did I fix the whole shape?"** It was found by
probing the neighbourhood of #691's fix on the *day* that fix merged, and it is
the #476 lesson again: the asymmetry ran in both directions, and fixing "into a
module" left "out of a module" untouched and still silent. But it adds something
#476 does not. The two directions could not share a fix, because #691's answer is
*"find the context this call is still inside of"* and a returned closure is called
when there is no such context — the frame popped, the proxy was for an argument,
the caller VM is gone. **Finding a second instance of a shape is not the same as
finding a second instance of the fix**; check whether the mechanism you wrote can
even reach the new case before assuming symmetry.

What generalised instead was the *predicate*: `_is_foreign_closure` already
detected the returned closure correctly, because #691's widening made it
chunk-relative rather than `_caller_vm`-relative. Only the resolution was missing.
A correct question with no available answer is a much better place to be than a
question nobody asks, and it is worth widening a predicate past its immediate
caller for that reason alone.

**And the pair is the first exception to "the bytecode cache is always one of the
paths" — with a reason that generalises.** Both were checked the way that rule
demands (each repro run three times against a warming cache, `.nbc` files
confirmed present, plus three runs in one `NodusRuntime` and a second runtime in
the same process): stable every time. That is not luck. The cache broke #394
because its fix **marked** something — a mark survives compilation and not
serialization, so the bypass came back on run 2. #691 and #696 mark nothing; they
**resolve** at call time from objects that are live either way (frames, and the
module's own `functions` table). **A resolve-don't-mark fix cannot have a
cache-shaped sibling path**, because there is nothing to serialize. Worth knowing
which kind of fix you have written before spending the second run — and worth
still spending it, since knowing *why* it passed is the point.

**The cache made it five, and this one was caught in the fix rather than after
it.** #609's first fix warned on a cold compile and went silent on every run
after, because the loader's parse is skipped on a cache hit — #521, #400, #394
and #348 are the earlier instances, and #348 is the closest, since
`--trace-imports` also printed nothing once the cache was warm. **A warning that
stops on the second run is worse than no warning: it looks like something
someone fixed.** The diagnostics ride in the cache entry now and are replayed on
a hit, the way #394's step mark does.

It was found by running the repro three times rather than once, which is the
rule this file already states. Worth noting *why* it applies here even though
#691/#696 were exempt: the exemption is for a fix that **resolves** at call time
from live objects. This one **records** a compile product — and anything
recorded at compile time has to survive serialization or it is a cold-run-only
answer.

**#704 shipped in the same release and is the rule holding from the other side.**
There the cache *was* the whole defect: `cache_key` was `sha256(abspath + mtime_ns)`,
so "is this entry for this program" was answered by a clock. Two edits inside the
platform's timestamp resolution are one program to that key, and the second run
silently executed the first program — the #521 question again, on the one path
#521 did not reach. The key is content now (`source_sha256`), which is the same
move as resolve-don't-mark: stop storing a proxy for the answer and compute the
answer.

**#691 adds the one about how a symptom count reads.** It presented as five
unrelated failures — a silent truncation reporting success, `Stack underflow`,
`Cannot call non-function: nil`, `Iterator is not supported`, a coroutine that
never ran — and that spread was not five bugs, nor even evidence of complexity. A
closure's address indexes the chunk it was compiled from; run it against a
different chunk and **the symptom is whatever happens to sit at that address**. So
the number of symptoms measured the number of module shapes tried, and nothing
else. When one construct produces symptoms with no family resemblance, suspect a
single wrong address or index before you suspect several defects.

It also shows the shape's other tell. `_is_foreign_closure` *implied* `_caller_vm
is not None`, and two callers in `coroutine.py` leaned on that implication instead
of stating it — so "detached module VM" quietly became the definition of "running
foreign code", and the other way of getting there was invisible to every reader
including the ones who wrote the guards. Widening the predicate broke both callers
immediately, which is how they were found. **An unstated implication between two
predicates is a duplicated question wearing a disguise.**

**#662 adds the one about blast radius: a drifted duplicate is as harmful as its
consumers make it, and wiring a new consumer is what detonates it.** The analyzer had
never bound a step's dependencies — confirmed against published **5.6.0** — so reading
`after a` inside the step body reported `Undefined variable` on correct code. That was
*editor squiggles*: noise, easy to ignore, nobody filed it. Then #489 wired `nodus check`
to that same analyzer for files declaring an `extern`, and the identical wrong answer
became **`nodus check` rejecting correct programs**. Nothing about the defect changed; a
new consumer did.

So when you point a new surface at an existing implementation of a question, the review
is not "does this surface work" — it is **"is this the copy that is right?"** Check what
the *other* implementations of that question answer before you promote one of them from
advisory to authoritative. And note what caught it: not the suite, not Gate 10's 71 green
probes, but **Stage 5**, using both new features in one program. Neither was broken alone.

**#632 adds the sharpest version of the follow-up question.** The symptom -- a test
racing its own tempdir cleanup -- had already been diagnosed and *fixed*, by #591, which
stopped the default runner's sweep daemon. It kept happening, because there are two
sweepers and nothing stopped the other. So "is this fixed?" was answered yes for months
by a fix that was real, correct, and covered one of two paths. When a known-fixed symptom
recurs, the question is not whether the fix regressed; it is **how many things do that**.

**#584 adds the variant worth naming separately: the missing case gets papered over
rather than left broken.** Two copies of one question drifted — `server.py` learned to
resolve a graph from the VM's own events, `api.py` never did — and the copy that could not
answer correctly did not fail. It reached into the process-global `.nodus/graphs/` and
returned *something*, which was right whenever the directory held exactly one graph and a
cross-request data leak otherwise. So the drift was invisible for as long as the
substitute looked plausible, and removing the substitute broke a feature nobody knew it
was providing. When you find two implementations of one question, the one that looks
*simpler* may be the one silently standing in for the case it never handled.

**#394 is the fullest worked example — read it before the older ones.** Three things it
teaches that the rest only hint at. **Count the doors before designing**: the issue implied
one, and an AST sweep for every `Frame(` built over a caller-supplied closure found four —
including the coroutine's first resume, which lives in `builtins/coroutine.py`, is invisible
to a `grep` of `vm.py`, and is the door *the runner itself* uses. **Never gate on which path
called**: "refuse `call_closure`, allow `run_closure`" mistakes the door for the authority,
since `run_closure` has two dozen callers a guest can reach — `std:retry`, `std:test`, tool
handlers, the iterator protocol. The fix is a positive capability the owner grants for one
entry. And **the bytecode cache is always one of the paths**: the mark survived compilation
but not serialization, so the bypass returned on the *second* run of any script — refused
cold, allowed warm. That was found by running the repro twice, not by reading it, which is
now the third time the cache has been a sibling path (#521, #400, #394). **Run the repro a
second time, always.**

**The tail of this table is not "more of the same" — read what each one adds.** #518/#521 are
*three of four*: an enumeration of node types with one member missing. #457 and #401 are the
plainest form — N sites asking one question, N answers. #476 is the one to study if you think
you have found the shape and fixed it: the asymmetry ran in **both** directions, so fixing
"cleanup leaves records" left "the record cap leaves state" untouched and still a bug.

The fix that generalises is not "add the case": it is to **name the set once**
(`FLOW_DECLARATIONS`, `ASSIGNMENT_FORMS`, `TASK_STATUSES`) and make a test drive off the tuple,
so a fifth form fails the suite until somebody handles it. #415 shows the same instinct applied
*before* a defect exists: adding a catch-less `try` made `catch` fields nullable, and rather
than trust that, the fix enumerated the **seven** consumers reading those fields and put each
under a regression test — the shape prevented rather than discovered.

**#521 is worth studying as the fullest example.** Three paths shared one question, and each
had to be found separately: the explicit branch, the cache *read*, and the cache *write* —
which was found only because a probe went red after the first two were fixed, not by
inspection. And the decision belongs where it can be *computed*, not declared: a flag at each
call site would have been wrong, because the CLI legitimately passes a file's own text and
must keep its cache. The question is not "did the caller supply source" but "is it the same
source".

**There is a gate for this now — `nodus_gate --shapes`.** It will not find the shape for you in the sense of telling you what is broken; it finds *places where one question is answered in more than one voice*, which is where every instance above came from. Its first run produced #597 and #598. `tools/shape_manifest.json` holds the ones it already knows about, so what it reports is the ones that are new. The count is deliberately not written here: the gate prints it every run, and the two previous revisions of this sentence each went stale — one by four. When you add a second implementation of anything, expect to justify it there.

**The fix is always the same: move the decision to one place, then assert on the source.** A
behaviour-only test passes on whichever path is already correct. Working examples to copy:
`test_retry_path_unification.py` asserts where the retry branch *lives*;
`test_vm_authority_inheritance.py` reads `VM.__init__`'s signature so a **new** parameter nothing
propagates fails; `test_annotation_forgery.py` fails if any lowering emits an unbound
`Call(Var(...))`; `test_workflow_runner_ownership.py` fails if a **sixth** builtin resolves the
runner from module state while the other five stay routed; `test_name_resolution_agreement.py`
pins the two sites of #671 to one rule, and keeps the negative cases (a `catch` var, a
parameter, a loop variable and a function-local `let` must all still shadow a same-named
global) that a fix in either site alone would have broken.

**A source assertion can be unfalsifiable — check that it fails.** Three written in one session
could not: one matched a substring of the very function it tested (`"detect_cycle"` is inside
`_detect_cycle_task_ids`), and one asserted `ok is False` that was true for an unrelated reason
(the script never imported `std:fs`, so the Floor was never reached). For every negative
assertion, run it against the unfixed tree and confirm it goes red.

**Testing a project against itself cannot find what it breaks in consumers.** #185's fix assigned
`self.memory_store` on `NodusRuntime`; `nodus_sdk.NodusSDKRuntime` subclasses it with
`memory_store` as a read-only property. Gate 10 passed 5.0.3 with 32 green probes and nodus-sdk
was broken at construction. That is why the dependent suites now run *before* the upload — see
the release sequence.
