# Changelog

## [Unreleased]

### Changed

- **#718: `spawn()` accepts a zero-argument function, not only a coroutine.**

  `spawn(fn() { ... })` wraps and spawns, and returns the handle. Launching a task
  used to cost two statements, and passing the function — the thing every reader
  tries first — was a runtime type error documented as a language quirk. It also
  brings `spawn` into line with `async.parallel`, which has always accepted either
  form.

  Strictly additive: `spawn(fn)` was a hard error before, so no program can depend
  on the old behaviour, and `spawn(c)` is untouched.

  **The wrapping delegates to `coroutine()`'s own builtin rather than constructing
  a `Coroutine` in `spawn`.** That path carries the zero-arity check and the
  ASYNC-MOD-003 / #691 `_foreign_closure_origin` pinning; a second construction
  site would be one question answered in two voices and would drift the moment
  either was amended — and the resulting failure (a cross-module coroutine resumed
  against the wrong chunk) is #691's symptom class, which is not traceable back to
  a duplicated constructor. `tests/test_spawn_accepts_function.py` asserts on the
  source for that reason; behaviour cannot see the difference until one copy moves.

  Checked, not reasoned: the new path is **not** a fifth door into a workflow step
  body (#394). Creating a coroutine is not a door — the guard is at first resume —
  and both spellings are refused with identical wording, which is what the test
  pins.

  This is the part of **#336** worth having. That issue proposed a `spawn { ... }`
  keyword for the same footgun and was closed as not planned: the block form has to
  be an expression to keep returning the handle, which puts it in the one grammar
  position that is broken (#717), and it would have had to reproduce the wrapping
  logic in the compiler.

### Fixes

- **#717: `match` can be used as an identifier, as a contextual keyword should be.**

  `match` is listed in `lexer.EXPRESSION_KEYWORDS` — contextual, meaning the word
  stays available as a name. It was the only one of the fourteen contextual
  keywords that was not: `let match = 7i` bound fine and **every read was a syntax
  error** (`print(match)`, `match + 1i`, `"\(match)"`, `[match]`, `match = 9i`).
  Present since `match` shipped in v4.1.0 (#308).

  The expression-atom dispatch fired on the name alone. It now takes one token of
  lookahead against a deny-list of tokens that can only *follow* a value.

  **The direction of that list is what makes the change safe.** Before it, an `ID`
  named `match` in expression position always took `parse_match`, so every program
  the lookahead diverts is one that raised — turning those into a variable read can
  only convert an error into a working program, and cannot change the meaning of
  any match expression that parses today. An allow-list would have the opposite
  failure mode: one omission silently breaks a shipped construct.

  Residual ambiguity is pinned by test rather than papered over: `match - 1i`,
  `match(f)` and `match[0]` still parse as match expressions, because `-`, `(` and
  `[` can each begin a scrutinee. Separating those needs unbounded lookahead, and
  reserving the word would break the contract this fixes.

### Tooling

- **#717: the two tests for "a contextual keyword is still usable as an identifier"
  are now one.**

  `tests/test_keyword_coverage.py` had two, and they disagreed. The narrow one
  covered `GOAL_KEYWORDS` (5 words) and did bind-then-read; the wide one covered all
  14 and only *bound*, never reading the variable back. So the wider test was the
  weaker one — and it was the wider one whose name stated the property, which is how
  `match` passed it for four minor releases while being unreadable.

  One question, one test, covering every contextual keyword and asserting on the
  read. Verified red on the unfixed parser before landing, along with a boundary
  test that goes red if the deny-list is widened.

## [5.9.0] - 2026-08-31

### Added

- **#170: `fs.read_bytes` / `fs.write_bytes` — binary file I/O.**

  `std:fs` could only read and write UTF-8 text: `write_file` opens with
  `encoding='utf-8'` and there was no binary mode, so a Nodus program could not
  write a compiled artifact. The Runtime Readiness audit recorded that as a
  Stage 3 bootstrap gap — to write a Nodus compiler in Nodus, the compiler has to
  be able to write bytecode files.

  **A byte sequence is a list of integers 0–255, not a new value type.** The issue
  listed a `Bytes` type as "consider" and it is deliberately not taken: a real
  byte type needs indexing, slicing, concatenation, equality, a literal syntax and
  JSON serialisation before it is usable, and a list of ints already has all six.
  If `Bytes` arrives later it can be a representation change behind the same two
  builtins.

  `write_bytes` validates every element before opening the file, so a refused
  write leaves no partial file. Out-of-range values raise a `value` error naming
  the index; non-integers — including `true`, which is an `int` in Python and is
  not a byte here — raise a `type` error.

  Both go through **both** filesystem mechanisms, which is the part that needed
  care: `_ensure_path_allowed` (the `allowed_paths` jail and the Floor) *and*
  `BUILTIN_CAPABILITIES` (what a `CapabilityPolicy` can see). #467 was a builtin
  wired to the first and not the second — "the map, not the chokepoint" — and it
  was invisible to a policy while looking confined.

### Fixes

- **#704: the bytecode cache now notices a content change the mtime does not.**

  `cache_key` is `sha256(abspath + mtime_ns)` and the stored payload records
  `mtime_ns`. Neither depends on what the file *contains*, so **any edit landing
  inside the platform's mtime resolution was invisible**: the key matched,
  validation passed, and a stale program ran.

  The window is not hypothetical and not PyPy-only. Five rapid rewrites, each with
  different content, on Windows:

  | | distinct cache keys |
  |---|---|
  | CPython 3.11 | **2 of 5** |
  | PyPy 7.3.23 | **2 of 5** |

  CPython's `st_mtime_ns` here is roughly millisecond-grained, so the window is
  small but real — write a file and re-run within it and you get the previous
  program. PyPy on Windows reports whole seconds, so the window is a full second
  and the collision is near-certain, which is how this surfaced: a
  resume-validation test wrote a workflow, ran it, rewrote the file with an extra
  step, and resumed. The rebuild was handed the **original** program from cache,
  so the topology guard compared the old shape against itself, found nothing
  wrong, and resumed a run whose workflow had changed.

  The cache entry now carries a SHA-256 of the source bytes and validation
  compares it. An entry written before this has no hash and is treated as a miss,
  so it recompiles once. Measured cost on a warm-cache run importing 12 modules:
  none above this machine's noise — the cache exists to skip parse and compile,
  which dominate reading a few KB.

  **This is the fourth time the cache has been a sibling path** — #521 (which
  program `run_source` runs), #400 (does inspection execute), #394 (a mark that
  survived compilation but not serialization). Those were about *what* was cached;
  this one was the key itself.


- **#696: a closure *returned* from a module now runs against its own chunk too.**

  The mirror of #691, and it needed a different answer. #691 fixed closures going
  *into* a module; every context source that fix uses records something a call is
  still inside of — a `_ClosureProxy` wrapped for an argument, a live cross-module
  frame, a caller VM. By the time a **returned** closure is called, the frame has
  been popped and there is no caller VM, so all three are empty and the closure
  ran at its own address in whatever chunk happened to be loaded.

  Same five-way symptom spread as #691, for the same reason — the symptom is
  whatever sits at that address. Measured one repro each: `Method calls are only
  supported on records`, `run_workflow(workflow) expects a workflow`, `Cannot add
  int and string`, `Stack underflow`, `'NoneType' object is not subscriptable`,
  and a stateful factory closure that **printed nothing at all**.

  This did not need a workflow or a coroutine: `let f = m.plain_maker()` in
  `fn main()` was enough, which makes a factory function — an ordinary thing for
  a module to export — unusable.

  The fix resolves rather than marks. Marking a closure on the way out would mean
  a hook at each exit *and* a walk of returned lists, maps and records — the case
  #339 found the entry side had missed. Instead `VM._foreign_closure_origin` asks
  which of the modules this VM can **reach** owns the closure's `FunctionInfo`: a
  module holds its `functions` table for its whole life, so the answer survives
  every frame being gone. Reachability rather than a process-wide registry, which
  would be the module-scope state shape behind #185 and #390.

  `VM.module_ctx` is now the single definition of a module's execution context,
  used both by `_try_enter_module_call` on the way in and by the resolution
  above, so the two cannot drift.

- **#691: a callback handed to an imported module's function now runs against
  its own chunk, wherever the call is made from.**

  A `Closure` is an address plus its upvalues, and the address indexes the chunk
  it was compiled from. A module function reached from `fn main()` runs in a
  detached VM, which wrapped closure arguments in a `_ClosureProxy` on the way in
  and dispatched them back correctly. A module function reached from inside a
  scheduler-managed coroutine takes the #105 fast path instead — the module's
  code is swapped into the *running* VM — and nothing there was wrapped or
  checked, so the callback's address was executed against the module's
  instructions. **A workflow step body is always a coroutine**, which is why the
  construct worked at top level and failed inside a step.

  Five symptoms came out of one construct, depending only on what happened to sit
  at that address:

  | Symptom | Shape |
  |---|---|
  | step truncates, `failed: []`, `steps: {}`, run reports success | module defines one function |
  | `Stack underflow` | module defines two |
  | `Cannot call non-function: nil` | callback is a named top-level `fn` |
  | `Iterator is not supported` | callback reached through the iterator protocol |
  | callback silently never runs | callback wrapped in a `coroutine()` |

  `retry.until` (#466) is the feature this blocked: a `std:retry` function whose
  documented home is a step body.

  `VM._foreign_closure_origin` answers "which context does this closure need, if
  not the one loaded" once, and both sites that jump to a closure's address —
  `call_closure` and `run_closure` — consult it. `builtin_coroutine_create` and
  `builtin_spawn` had their own version of the question and now ask the same one;
  theirs assumed a detached VM was the only way to be running foreign code, which
  is precisely the assumption that hid this. Origin is resolved by asking which
  saved context *owns* the closure's `FunctionInfo`, not by taking the nearest
  boundary — nearest is wrong as soon as a closure is passed through two modules.

  Not a regression: v5.7.1 and every earlier release behave identically.

### Performance

- **#702: ~9.6x recovered on PyPy, by moving five constants off the instance.**

  PyPy stores an instance's attributes in a compact map and its JIT specialises
  reads against it — up to **80 attributes**. Past that it falls back to dict
  storage and every attribute read in the dispatch loop deoptimises. Measured on
  a generated class with one attribute read in a loop: **79 attrs → 786M
  reads/sec, 80 attrs → 71.5M**. CPython is flat across the same range.

  `VM.__init__` sat at 79. #488 — a goal-budget feature touching nothing in the
  dispatch loop — made it 80, and cost ~9x of PyPy throughput. It shipped in
  v5.6.0 and survived three releases with every gate green, because the cliff is
  structurally invisible to CPython benchmarking.

  **The commit was incidental**: adding a single *unrelated* attribute to
  `__init__` at #488's parent reproduces the drop exactly. Any 80th attribute
  does it.

  Five constants with no constructor parameter behind them (`_resume_origin`,
  `budget_meters`, `trace_errors`, `last_graph_plan`, `trace_count`) are now
  class-level defaults. Reads resolve through the class; an instance entry
  appears only when something writes one. No call site changes.

  On `main` under PyPy, same probe: **1.87M → 17.93M instructions/sec**. CPython
  is unchanged at 0.62M either way.

### Tooling

- **A test now counts the `VM`'s instance attributes (#702).**

  `tests/test_vm_attribute_budget.py` fails if a bare VM or a `NodusRuntime`-built
  VM reaches the cliff, with the measurement and the three ways out in its
  docstring. This is the only thing that can see the problem: CPython — every
  benchmark, gate and CI job this project runs — is flat across the boundary, so
  the next crossing would otherwise surface releases later, as this one did.

  It also pins the mechanism the headroom depends on: that the five hoisted names
  still read correctly, are absent from the instance dict, and that writing one
  creates an ordinary per-instance attribute rather than leaking across VMs.


- **Two guards over the filesystem builtin surface, both driven off the named set
  rather than a list written in the test (#170).**

  - Every builtin classified `fs.read` or `fs.write` is asserted to refuse a path
    outside `allowed_paths`. Deliberately behavioural: a source scan for
    `_ensure_path_allowed` is unsound in both directions here — `hash_*_file`
    reach it through a local helper and would read as uncovered, while the
    subprocess builtins call it for `cwd` and redirects and would read as
    filesystem builtins when their capability is `subprocess`.
  - Every such builtin is asserted to actually reach a `CapabilityPolicy`. That is
    the half #467 was, and the sweep above would have passed while it was live.

- **`BUILTIN_NAMES` is now checked against the live registry, in both directions.**

  `builtins/__init__.py` documents three steps for adding a builtin and only the
  first two have any runtime effect, so step 3 is the one that gets forgotten —
  **this change forgot it.** A builtin missing from `BUILTIN_NAMES` is not merely
  undocumented: that set is what every capability totality check is measured
  against, so the builtin is *exempt from classification* and one with real
  authority can be added with nothing noticing. #616 recorded that after the fact;
  it is enforced now.

- **#412 phase 4: all 49 opcodes now carry a semantic spec, and the gate
  requires one.**

  Phase 2 specified the ten control-flow opcodes #412's scope note names. The
  other 39 were left deliberately — `ADD` and `POP` are not where the bugs were.
  Two things about that reasoning did not hold up. Of the **sixteen** opcodes
  phase 1's census found executing fewer than 100 times across the whole suite,
  only three had a spec; `JUMP_IF_TRUE`, `NOT`, `STORE_UPVALUE` and `TO_BOOL`
  execute **twice** each. And phase 2's rate of finding the reference wrong did
  not depend on complexity — what drives it is a short entry describing a
  multi-branch handler, which is exactly the shape of the simple ones.

  `tests/test_opcode_semantics_core.py` specifies the remaining 39 in the shape
  #412 asks for: construct a known VM state, execute one instruction, assert the
  resulting state. **Verified by mutation** — 52 deliberate defects applied to
  `vm.py` one at a time, all 52 killed. Two survived the first pass and both were
  real gaps in the specs rather than in the VM.

  `nodus_gate --opcodes` runs **29** checks rather than 28. The spec requirement
  is now the whole dispatch table rather than the `exceptions` category, spec
  modules are discovered by glob so a third is covered by construction, and a
  new check requires every dispatched opcode to declare a `- Category:` in §3.

  **Twenty-four corrections to `BYTECODE_REFERENCE.md §3`**, each one a test that
  went red against what the document said. The consequential ones:

  - **`DIV` and `MOD` have three branches each**, and "host float division
    behavior" described none of them: int/int is *floor* division, `bool` is
    excluded from the int path (so `4 / true` is `4.0`), and each has two
    distinct zero errors rather than a host `ZeroDivisionError`.
  - **`EQ`/`NE` are not "Python value equality semantics".** `1 == 1.0` is true
    by explicit coercion and `1 == true` is **false** — the opposite of Python.
    Records compare by identity (#545).
  - **`STORE_FIELD` creates a missing record field rather than erroring**, which
    the entry got backwards; only a *module* receiver requires the name to exist.
    It also pushes the assigned value back, so its net effect is -1, not -2.
  - **`RETURN` has three exits**, of which one was documented: deferred by a
    pending `finally` with no frame popped, coroutine completion returning
    `("return", value)` and pushing nothing, and the ordinary path.
  - **`LOAD_FIELD` accepts a module receiver**, not only a record — the same
    omission phase 2 corrected in `CALL_METHOD`, in the sibling opcode.
  - **`ADD`/`SUB`/`MUL`/`NEG` and the four ordering comparisons convert the host
    `TypeError`** into a Nodus `type` error; the entries pointed at host
    behaviour for errors that never surface.
  - `HALT` does not advance `ip`; `CALL` has five resolution paths including the
    #411 compiler prefix; `BUILD_MAP` refuses a `bool` key; conditional jumps pop
    whether or not they jump; an empty record is truthy while an empty map is not.


- **`CLAUDE.md` trimmed from 1,889 to 1,619 lines; per-repo companion detail moved
  to `docs/ecosystem/COMPANION_REPOS.md`.**

  Eleven per-companion sections were scattered across three regions of the file,
  interleaved with unrelated material, and the key-file table repeated all their
  paths a fourth time. They are one document now, reached by a pointer and a
  fourteen-row index. Every gotcha is preserved — the two `C:\codev` directories,
  the egg-info pitfall, the VS Code PAT scope, the `nodus-flow` rename rule.

  Two sections had said the same thing twice. The SemVer section carried a
  narrative per release duplicating `CHANGELOG.md`, told 5.7.0's supersession
  twice, and printed the *"X is current" vs "as of X"* paragraph verbatim in two
  places (146 → 85 lines). "Published ecosystem" repeated per-package detail that
  now lives in the new file (116 → 94).

  **Two version claims were retired rather than re-registered.** They guarded
  CLAUDE.md quoting `version.py`'s and `pyproject.toml`'s literal contents back at
  the reader — a third copy of a fact with two authorities, while the gate's own
  `version files agree` check compares those authorities directly. The
  restatement was removed instead. A claim is worth having when prose asserts
  something a reader acts on, not to guard a transcription that need not exist.

  Facts re-measured rather than carried forward: 3,132 tests collected, 138 gate
  symbols, 268 runtime blocks, `.venv` still at 5.0.0 against `src/` at 5.8.0.

- **`nodus-workflow-ai` is published, and the registers that should have seen it
  now do.**

  It moves from `UNPUBLISHED_COMPANIONS` into `COMPANIONS` in
  `check_downstream_constraints.py`, per the rule that the move happens in the
  publishing commit, and it is added to `check_publish_drift.py` so it is swept
  from now on. It was the first companion registered with a floor naming a
  version that did not exist yet; `nodus-lang` 5.8.0 made that floor satisfiable.

- **The PyPI project count was re-derived and was two short, because the list it
  is derived from was incomplete.**

  CLAUDE.md says to re-derive the count by probing every first-party name in
  `docs/ecosystem/README.md` rather than adjusting it by arithmetic. That only
  works if the list is complete, and it was missing `nodus-a2a-wire` (published
  2026-08-26) and `nodus-workflow-ai` — so the procedure returned 35 where the
  answer is 37. Both now have rows, and the file says out loud that it is the
  source for that count, since a package published without a row here is
  invisible both to the count and to anyone reading the file for what exists.

  Prose updated in five files: 36 standalone companions, 37 PyPI projects.

## [5.8.0] - 2026-08-30

### Added

- **#466: `retry.until` — retry on a predicate, not on failure.**

  ```nodus
  let r = retry.until(
      fn(previous) { return edit(source, previous) },
      fn(result) { return result["ok"] },
      {"max_attempts": 3i}
  )
  ```

  `retry.call` re-attempts when a call **errors**. A call that returns
  successfully but returns something *wrong* — a malformed edit, a
  schema-invalid payload, a plan that fails its own check — was not a retry
  trigger, and that shape existed only at the workflow altitude
  (`goal … over … { until … }`), so a bounded validated retry around one call
  meant standing up a workflow.

  **The failing result reaches the next attempt.** Give the function one
  parameter and it receives the previous result, `nil` on the first. Without
  that carrier the retry is a blind re-roll, which is the thing the pattern
  exists to avoid. A zero-argument function still works.

  Returns `{value, satisfied, attempts}` — exhaustion is a reported outcome, not
  an error. `{max_attempts, deadline_ms}` mean what `budget { max_iterations,
  deadline_ms }` means for a goal, so the two altitudes read alike, and **a bound
  always applies**: declare neither and an implicit cap of 10,000 is imposed,
  because a predicate that never holds is an unbounded loop. `budget` grew the
  same guarantee in #488.

- **#465: a documented plan-then-act handoff**, in
  `docs/guide/workflows-and-tasks.md` §9 with a runnable
  `examples/plan_then_act.nd`.

  One actor produces a plan, a second consumes it — the shape every user was
  re-deriving. **Deliberately a documented workflow rather than a
  `handoff(planner, editor, request)` stdlib function**, which was the open
  question on the issue: the value being claimed is that a handoff becomes
  inspectable state on disk and resumable through `resume_workflow` instead of
  in-process glue, and that property comes from *being a workflow*. A wrapper
  would hide it, and would fix the shape at two actors and one hop.

  It composes with `goal … over …` so the handoff re-runs until the edit
  validates, which is the second half of what the issue asked — and is only
  possible because it stayed a declaration.


- **#395: a workflow run can be cancelled — `nodus workflow cancel <graph_id>`,
  and `cancel_run(run_id)` for an embedder.**

  The run is marked `cancelled`, an **eighth run status**: terminal, and
  deliberately *not* rehydratable, since a cancelled run that comes back on the
  next sweep has un-cancelled itself. The status it was cancelled from is kept in
  the record, so "what was it doing when it was stopped" has one place to look.

  **In-process this is immediate; across processes it is cooperative.** A CLI
  cannot reach into the scheduler of whichever process owns a running run, so it
  marks the store and that process observes it at the next step boundary — a
  cancel is *eventually* effective, bounded by the duration of the step currently
  running. The command says so rather than implying otherwise.

  Cancelling a finished or unknown run reports what it found instead of raising,
  matching `cancel(task)`: the caller usually cannot know the target's state.

  **The run-status vocabulary is now named once.** It was named three times —
  `REHYDRATABLE_RUN_STATUSES` in `store.py` and `_REHYDRATABLE_STATUSES` in
  `runner.py` were independent definitions of one equal set, with the members
  listed again as `_KNOWN_RUN_STATUSES`. Adding a status is exactly when that
  costs something. `models.py` owns it; the others import it.

  **Cancelling a run does both halves**: it stops dispatching new steps *and*
  unwinds the ones already in flight, through the same `cancel` verb, so a step
  holding a lock still runs its `finally`. Stopping dispatch alone would let a
  step blocked on a slow agent call run to completion, which is exactly what
  someone cancelling a run is trying to stop.

  The graph asks via a predicate the runner **injects** rather than imports --
  `task_graph` importing the workflow runner at module scope would reinstate the
  circular import #103 fixed. A bare `run_graph` gets no predicate and is
  unaffected: a run no store knows about cannot be cancelled through one.

- **#395 / #157: `cancel(t)` and `wait(t)` — a task can be stopped, and its
  outcome can be asked for.**

  `spawn(c)` now returns the coroutine it was given instead of `nil`. That return
  was the whole mechanical cause of #157: the value channel a program needs
  already existed on the coroutine (`last_result`) and was simply unreachable, so
  libraries reached for a channel to work around a discarded handle.

  The handle is the coroutine, not a new record type. A record would be a
  *value*, so a `state` field on it would freeze at spawn time.

  ```nodus
  let t = spawn(coroutine(fn() { return 77i }))
  let v = wait(t)        // drive until it settles, return its value
  cancel(t)              // stop it, running its `finally` blocks
  ```

  **`wait` has two contexts.** Inside a coroutine it suspends, like `recv`. At
  top level it drives the scheduler until the task settles — a *bounded* drive,
  not an isolated one: it still runs other coroutines, because a task can depend
  on its siblings, but it returns when the task settles rather than when the
  whole queue empties. That is what lets a library hand back a handle instead of
  calling `run_loop()` and running its caller's unrelated work to completion.

  **A waited failure is raised into the waiter, and reported once** — not also to
  stderr and `run_loop()`'s error list. An *unwaited* failure is byte-identical
  to before. This is not a new error-propagation path: `resume(c)` has always
  raised a task's failure into the resumer, and having `wait` collect instead
  would be one question answered in two voices.

  **`cancel` reuses #502's unwind unchanged** — pending `finally` blocks run,
  `catch` blocks are refused so a task cannot swallow its own cancellation, and
  the whole thing is bounded by the same step budget. It returns whether it
  actually stopped something; cancelling a finished or never-spawned task is a
  no-op, not an error, because the caller usually cannot know.

  Every reason a coroutine can be parked is now named in one place
  (`BLOCKED_REASONS`), with a test that reads `src/` and fails when a literal
  appears outside the set. That is not cosmetic: cancelling a *parked* task means
  unparking it, and an unpark that handles five of six reasons is a cancel that
  hangs on the sixth.

  **The verb is `wait`, not `join` as the design record first said.** `join`
  collides with `std:strings.join` and `std:path.join`, and a builtin silently
  shadows an explicitly imported name — filed separately as issue 680, since it
  makes *any* new builtin a potential breaking change.

### Changed

- **#680: a named import of a builtin name is refused instead of silently
  ignored.**

  ```nodus
  import { sleep } from "./mod.nd"
  sleep(1i, 2i)
  ```

  `_op_call` resolves builtins **before** locals and globals, so the binding that
  import created was never reached. The program then failed somewhere else
  entirely — `sleep expected 1 args, got 2`, naming neither the import nor the
  shadowing. **Adding any builtin was therefore a silent breaking change** for
  programs importing a matching name; it was found when a `join` builtin
  collided with `std:strings.join`.

  **Refused rather than reordered, deliberately.** `register_function` refuses to
  override a builtin so a host can rely on a builtin name meaning the builtin —
  a security boundary, since a guest that could redefine a guarded name would
  walk past the guard. Letting an import take the name is the same hole through
  a second door.

  This cannot break a working program: the import already did nothing. The
  message names the collision and the namespace form that does work
  (`import "std:async" as async` → `async.sleep(...)`), which matters because
  **thirteen stdlib functions share a builtin name** and every one of them is
  reached that way. `nodus check` reports it too, so it is visible before
  running.


- **`resume(c)` raises a coroutine's failure into the resumer — documented at
  last, and it decides a design question.**

  It has always done this, catchably, including for a failure after a `yield`,
  with the full err record (`kind = "thrown"`, `origin = "user"`). It was
  documented nowhere — not `LANGUAGE_SPEC.md`, not
  `FAILURE_AND_DEGRADATION_MODEL.md`, not the guide.

  Long enough that the task-handle decision was nearly taken on the belief that
  no such path existed: `06-task-handle.md` §D6 stated `join` raising would be
  *"the first error-propagation path in Nodus"*. It would not be. §D6 is
  corrected — the outcome stands, the argument changes from a fresh commitment to
  consistency with `resume`, which is the stronger reason. `resume(c)` and
  `join(c)` ask one question — drive this task, give me its outcome — and one
  raising while the other collected would be that question answered in two
  voices.

  `FAILURE_AND_DEGRADATION_MODEL.md` §9.1a now puts the three answers in one
  place: `resume` raises, `spawn` + `run_loop` collects, `run_workflow` returns
  the failure in its result map. The distinction is not arbitrary — `resume` is a
  call, so its failure returns to the caller; `spawn` is a hand-off, and there is
  nobody to return to.


- **#671: a function assigning to a module-top-level `let` now updates it. It used
  to silently write a frame-local.**

  A behaviour change, and named as one rather than filed under fixes: a program
  that relied on the old silence will now see its globals actually mutate. That
  is the point — nothing can have depended on a write disappearing — but it is a
  change in what running code does.

  ```nodus
  let g = 7i
  fn setit() { g = 99i }
  setit()
  // g was 7. It is 99.
  ```

  There was no error and no warning. When the right-hand side also read the
  variable, the fresh uninitialised local surfaced as `Cannot add nil and int` —
  a type error naming arithmetic rather than scoping, which is why it was
  diagnosed as everything except what it was.

  **Two sites answered "where does this name live" and disagreed**, and neither
  fix alone is sufficient — which is why the bug looked unfixable from either
  end. `SymbolTable._resolve_upvalue_in` returned `None` whenever there was no
  enclosing *function* scope, so a module-level `let` was invisible from a
  top-level function and `Assign` allocated a frame slot instead. And
  `VM.store_name` wrote into the current frame whenever one existed, while
  `load_name` walked on to `module_globals` — so reads were correct throughout,
  which is how this survived every behavioural test ever written.

  The rule is named once now (`VM.binding_namespace`) and both paths consult it.
  `tests/test_name_resolution_agreement.py` pins the behaviour, the negative
  shadowing cases (a `catch` variable, a parameter, a loop variable and a
  function-local `let` must all still shadow a same-named global), and the
  source-level property — each site verified to turn the suite red on its own.

  Unaffected, and worth stating because DESIGN-006 (#156) claimed otherwise for
  years: **function-scoped upvalue mutation always worked**. Escaping closures,
  two closures sharing one captured variable, nesting, `+=`, and mutation from a
  spawned coroutine are all covered as controls. The map-with-quoted-keys
  workaround is no longer needed for module scope either.

- **The agent skill's first "non-negotiable rule" was wrong, and sent readers to an
  unnecessary workaround.**

  `skills/nodus.skill` — the file `nodus docs` points users at — said *"`let` in
  closures is read-only — use a map"*. Upvalue mutation works: an escaping counter
  closure, two closures sharing one captured variable, two-level nesting, `+=`, and
  mutation from inside a spawned coroutine were all verified working against 5.7.1.

  What is actually broken is one scope narrower: a `let` at **module top level**
  assigned from inside any function or closure silently writes a frame-local and
  leaves the top-level value unchanged. Newly filed as issue 671, with both root-cause
  sites. The map-with-quoted-keys pattern is still correct for module-scope shared
  state, and unnecessary for anything declared inside a function.

  Corrected in `skills/nodus.skill` (five places), `skills/nodus/references/idioms.md`,
  `skills/project-AGENTS.md`, `skills/project-CLAUDE.md` and `CLAUDE.md`. The old
  DESIGN-006 issue, whose reproduction was the still-broken top-level case but whose
  title generalised it, is closed as superseded.

- **The concurrency docs now state the worker-pool model plainly, and one of them
  was describing behaviour the runtime does not have.**

  `FAILURE_AND_DEGRADATION_MODEL.md §9.1` said an unhandled exception in a
  spawned coroutine "is recorded on the coroutine object" and that "the spawning
  code receives the error when it resumes or waits on the coroutine". Neither is
  true, and the second implies a parent/child await relationship that does not
  exist — `spawn` returns `nil`, so there is no handle to wait on, and resuming a
  `finished` coroutine is itself a runtime error.

  What actually happens, measured: the trace goes to stderr, the error goes to
  the scheduler's list, `coroutine_status()` reports plain `finished`,
  **`run_loop()`'s return value is the only way a program can observe it**, and
  the run still exits `0`. A script that ignores that return value cannot tell a
  clean run from one where every spawned coroutine died. The spec had never
  documented the return value at all.

  A new `§9.0` states the model normatively — a spawned coroutine outlives its
  scope, a failure does not stop its siblings, and there is nothing to wait on or
  cancel — and points at the workflow DSL, which is where "first failure stops
  the rest" actually lives (`allow_failure`, `step … each`). `LANGUAGE_SPEC.md`
  and `standard-library.md` carry the same statement, the latter with a runnable
  example. A new `§9.4` documents the timeout unwind as the one cancellation
  path, with the un-preemptable-host-handler caveat.

  This is the documentation half of issue 395, whose design record is
  `docs/design/v5/04-cancellation.md`; the runtime is unchanged.

- **`LANGUAGE_SPEC.md` no longer calls `std:async`'s `worker_pool` and `pipeline`
  non-functional.** They were, through v4.1.1, and were fixed on 2026-08-15 —
  three releases before this correction. `standard-library.md` had it in the past
  tense, so the two documents contradicted each other and the spec was the wrong
  one. Both were verified working by running them.

### Fixes

- **#679: a runtime-built graph can name its steps, and its per-step results
  stop being silently dropped.**

  ```nodus
  let a = task(fn() { return 1i }, {"name": "fetch",   "deps": []})
  let b = task(fn() { return 2i }, {"name": "analyze", "deps": [a]})
  run_graph(graph([a, b]))["steps"]     // {"fetch": 1, "analyze": 2}
  ```

  Before, `steps` came back **empty** for any generated graph — the results were
  computed and then discarded — and every step was `task_N`, so a planner's
  output was a second-class graph next to a declared `workflow`.

  **Two halves, and fixing one would have looked complete.** `TaskNode.step_name`
  already existed and `task()` could not reach it; separately, the result map is
  keyed off graph metadata only the workflow-DSL lowering populated. Adding the
  option without filling that metadata would have given named steps and an empty
  `steps` map, so the regression tests assert both.

  `plan_graph` now shows names too, through the same relabelling `plan_workflow`
  already used — the same DAG read differently depending on how it was built.

  Two decisions worth knowing: an **unnamed** task gets no entry rather than a
  synthetic `task_N` key (a name is either meaningful or absent, and `task_N` is
  an unstable VM-counter id), and two tasks in one graph sharing a name is
  **refused at construction**, since one result would silently overwrite the
  other. Unnamed graphs behave exactly as before.


- **#664: an undefined name the program declared `extern` now says so.**

  `nodus run` cannot register host functions, so a declared extern reaches its
  call site undefined and the message was the pre-#489 one:
  `Undefined function: notify`. A user who had just written `extern notify(...)`
  was told nothing connecting the two. It now names the declaration and says
  what registers it, at both undefined-name sites — the call and the value
  position.

  The CLI still does not pre-flight the way `NodusRuntime` does, and that is the
  decision rather than the defect: pre-flighting would refuse every
  extern-declaring program from the CLI, which is the workflow the feature
  exists for. `nodus check` still passes such a file. Both are documented in
  `OPERATOR_OR_EMBEDDER_RUNBOOK.md` now, which is what #664 asked for.

  The declared names travel in the module's cached metadata, not derived from
  the AST at the error site — a cached module has no AST, so the hint would
  otherwise appear on a script's first run and vanish on every run after.

### Tooling

- **The 5.4.0 stale-prose probe cried wolf on a true sentence, and its
  self-check could not have caught it.**

  The pattern was written out **twice** — once in the probe, once in the
  self-check that exists to hold the probe honest — so the self-check validated
  a *copy*. Tightening either one would have left the other unchanged and green.
  One constant now, read by both.

  What it fired on: `| 5.4.0 | `nodus graph` no longer executes the file it
  inspects (#400) |`, a correct historical row in CLAUDE.md's "what stopped
  working" table, added after 5.7.1's Gate 10b had already run clean. A regex
  steps straight over the negation — the same blindness that makes GitHub close
  an issue on "Filed, not fixed: #N". Fixed with a negation guard rather than an
  exemption for that file, since the table gains a row every release, and both
  the stale and the true forms are now pinned in the self-check.

- **#412 phase 3: stack discipline — does the runtime agree with what the
  compiler assumed?**

  Statically, over every stdlib module: every jump target lands inside the code,
  none survived unpatched, every function body opens with `FRAME_SIZE`, and no
  slot or frame operand is negative. That last is the case the runtime does not
  catch — a read past the end raises `IndexError`, but a **negative index
  silently wraps** to the far end of the frame and returns another variable's
  value.

  Frame sizing is checked **at run time**, and the reason is a finding rather
  than a convenience. Attributing each slot access to the nearest preceding
  `FRAME_SIZE` does not work: a nested closure's body is emitted inside its
  parent's code at a higher address, so instructions after the closure get
  credited to it — twelve false violations in `async.nd` alone. A compiled
  function has no recorded end, so there is no sound span to attribute against.
  At run time the frame doing the access is the frame that was sized.

  Both halves are shown to detect something: the static checkers run against
  synthetic broken input, and the runtime check was verified by under-sizing
  every frame by one slot, which turns all three corpus tests red.

  Phases 1–3 of #412 are complete.


- **#179: `nodus_gate --invariants` — the invariant-to-test ledger is checked
  rather than asserted.**

  `EXECUTION_INVARIANTS.md` documents 29 runtime invariants. Which test checked
  which was recorded **in prose, in two different places** — sometimes inline
  under the invariant, sometimes in §8's coverage bullets — and maintained by
  hand. So a renamed test left the document pointing at a file that no longer
  existed, and a new invariant could arrive with nothing covering it, with no CI
  signal for either. The same failure mode the opcode inventory had before #366.

  `tools/invariant_coverage.json` is the ledger, one entry per invariant. Four
  things fail the gate: an invariant documented with no entry, an entry naming an
  invariant the document no longer has, a named test file that does not exist,
  and an entry with no tests and no stated reason. Citation drift — the document
  naming a test the ledger has not learned — is advisory.

  **The phase cannot verify that an invariant holds**; the tests do that. It
  verifies the mapping, which is the only part a gate can own.

  Two things the ledger made visible. **Six of the twenty-nine invariants name a
  covering test** — §8 opened by claiming *"Most of these invariants have direct
  test coverage"*, which the document that made the claim did not support. And
  the remaining 23 are recorded as `unrecorded` rather than `uncovered`: the
  behaviour may well be tested, but nothing ties a test to the invariant, which
  is the gap the issue is about. Inventing a mapping would have been worse than
  recording the gap.


- **#412 phase 2: the ten control-flow and frame opcodes have a semantic spec,
  and `nodus_gate --opcodes` checks that they still do.**

  The gate verified the opcode *inventory* and `test_bytecode_golden.py` verifies
  *emission*; between them nothing verified that an opcode does what it is
  documented to do, which is why the gate was green through all three of the v5
  cycle's exception-unwind bugs. `tests/test_opcode_semantics.py` builds a VM
  state by hand, executes one instruction, and asserts the result — the pre-state
  is constructed rather than arrived at, because a program that happens to reach
  an opcode passes as long as the *program's* output is right.

  Verified by mutation: fourteen deliberate defects applied to `vm.py`, all
  fourteen killed, none survived.

  Four handler/reference disagreements found and corrected in
  `BYTECODE_REFERENCE.md §3` — `FINALLY_END` documented one of its three exits,
  `CALL_METHOD` omitted that a module is a valid receiver, `THROW`'s `err.*`
  fields describe the record a `catch` receives rather than the exception it
  raises, and `CALL_VALUE` transfers control rather than pushing a result.

  The gate's new check is coverage, not semantics: every opcode in the
  reference's `exceptions` category must be specified, and every specified
  opcode must still be dispatched. The category is read from the document, so a
  fifth unwind opcode is covered by construction.


- **#655: `test_workflow_store_isolation` no longer counts an in-flight atomic
  write as a leaked run record.**

  It failed intermittently on CI naming a `g_….json.<hex>.tmp` — the temp half
  of a write-then-rename, which exists only *during* a write — and reported it
  as "the run wrote into the repo despite the override". The run under test had
  written exactly where it was told; something else in the process was mid-write
  while the directory was snapshotted. The snapshot ignores `*.tmp` now, so the
  message is true when it fires, and the test stops the default runner's sweep
  daemon first, so a thread bound to a repo-root runner from an earlier test is
  not writing there at all.

- **The claim-discovery sweep now recognises the bare phrase "X is current".**
  Its marker list had `current version` and `current stable` but not `is current`
  -- which is the exact phrasing CLAUDE.md names as the one that goes stale
  ("*'X is current' goes stale, 'as of X' does not*"). Adding it immediately
  found two unregistered lines, one of them pre-existing.

- **A version claim that names a *path* is now checked for that path existing.**
  Claim entries in `tools/version_claims.json` may declare `points_at`, and
  `nodus_gate --versions` fails when the document a claim sends a reader to is
  not there.

  Found at the 5.7.1 cut. The eval-record claim went red for naming the previous
  cycle, and the obvious one-line fix -- edit the version in the string -- would
  have passed the gate while pointing at a `CREATOR_VALIDATION.md` that had
  never been written: 5.7.1's directory held two of its three release documents.
  The number agreed; the file did not exist.

  The effect is that a release cannot satisfy the gate without writing its
  Gate 10 record, which CLAUDE.md required in prose and nothing enforced.

## [5.7.1] - 2026-08-29

### Fixes

- **#662: a step body's dependencies were unbound in the analyzer, so reading one
  was a false `Undefined variable` — and in 5.7.0 `nodus check` rejected it.**

  `after a` binds `a` to a's return value, `each p in d` binds `p` to the item,
  and `compensates a` binds the compensated step's result. All three run
  correctly; the analyzer pushed a scope for the step body and bound none of
  them.

  Two consequences. The **pre-existing** one is false `Undefined variable`
  squiggles in any editor using `nodus lsp` — confirmed against published
  **5.6.0**, so it long predates the release that surfaced it. The **5.7.0**
  one is that #489 wired `nodus check` to this analyzer for files declaring an
  `extern`, turning that false positive into a rejection of correct programs:
  a file with any `extern` could not read *any* step dependency by name.

  Found by Stage 5 of the 5.7.0 release — installing the published wheel in a
  fresh venv and running it as a new user would, on a program using both new
  features together. **Neither feature is broken alone**; nothing covered the
  pair, because the compensation tests declared no `extern` and the extern tests
  used no compensation.

  The fix binds the step's `deps` in the analyzer's step scope, substituting
  `each_var` for `each_source` as the lowering does. Two properties are pinned
  against binding too much: a genuine typo is still reported, and `each p in d`
  binds `p` and not `d`.

  **5.7.0 is superseded.** It is on PyPI and immutable; its GitHub release was
  deliberately never created, so that one superseded artifact stands rather than
  two published records disagreeing. Both are cut at 5.7.1.

## [5.7.0] - 2026-08-29

### Added

- **#577: `compensates` — a declared undo path for work that already succeeded.**

  ```
  workflow saga {
      step reserve { return "res-1" }
      step charge after reserve { return "ch-1" }
      step ship after charge { throw "carrier down" }

      step release compensates reserve { cancel(reserve) }
      step refund  compensates charge  { refund_card(charge) }
  }
  ```

  When the run ends failed, each completed step's handler runs in **reverse
  completion order** and reports under a new `compensation` key — a list in
  execution order, since the ordering is the semantics.

  The declaration is on the **handler**, not the forward step, so it reads
  locally as what it is and the pair is named once. The compensated step's value
  binds by the rule `after` already uses, so `refund` reads `charge` to get
  `"ch-1"`. A handler is **excluded from the forward graph** — it never appears
  in `steps`, `statuses` or `failed`, which keeps `TASK_STATUSES` closed.

  **Reverse completion order comes from a recorded counter, not the clock.**
  `TaskNode` gains `completion_seq`, assigned where completion is already
  serialized. `finished_at` is `time.monotonic()`, which ticks at ~15.6 ms — a
  strict causal chain stamps `265, 265, 281, 297, 297`, two ties in a sequence
  with no ambiguity, and sorting by it would refund before uncharging.

  Sub-behaviours, each pinned: a **tolerated** failure does not unwind
  (`allow_failure` completes the run); a **failing handler** is recorded and does
  not cascade or change the verdict; a **compensated run is terminal** and a
  resume is refused naming that, because a resume re-executes (#494) and would
  re-run steps against a remote already refunded.

  Refused at declaration: `after`, `each` or `when` on a handler, and a step
  compensating itself.

  **`nodus-vscode` needs republishing** — `compensates` is a new keyword, as is
  `extern` (#489). One republish covers both.

- **#472: `workflow_wait` can declare the shape of the payload a resume must
  deliver.**

  ```
  step approve {
      return workflow_wait("approval", {schema: {approved: "bool", note: "string"}})
  }
  ```

  A resume whose payload does not match is refused **at the resume call**, the
  way a mismatched `event_type` already was — so the failure lands on the caller
  that sent the wrong thing rather than inside the step that trusted it:

  ```
  {"ok": false, "error": "Wait payload does not match the declared schema:
   argument 'approved' must be a boolean. 'approval' declares {approved, note}."}
  ```

  **Argument 2 now type-dispatches**: a **string** is `correlation_key`, exactly
  as before; a **map** is an options map carrying `correlation_key`, `payload`,
  `deadline_ms` and `schema`. All four positions were already named, so there was
  no free slot — and this caps positional growth rather than adding a fifth
  argument to a signature that was one option away from unwritable. Mixing the
  two forms is refused.

  **An unspecified schema accepts anything**, so every wait written before this
  is untouched. The schema is normalised and checked at the **wait site**: an
  unknown option or an unrecognised type name fails there, not when someone
  eventually tries to resume. It uses the same validator as `std:tool` and
  `register_function` (#493), so all three typed boundaries word a failure
  identically.

- **#489: `extern` — a program can declare the host functions it requires.**

  ```
  extern delegate(who: string, task: string) -> string

  fn main() {
      print(delegate("researcher", "find it"))
  }
  ```

  Two things followed from having no such declaration, and both are closed.
  `nodus check` could not catch a typo in any program using host functions,
  because it could not tell one from a name the host would supply — the same
  `OK` for the correct program and the broken one. And a host could not verify a
  program before running it; you found out when the call failed, partway through
  a run that had already had effects.

  Now: a file that declares **any** `extern` gets strict name resolution, so an
  undeclared unknown name is reported as the typo it is. And `NodusRuntime`
  refuses **before executing anything** when a program declares a host function
  the runtime has not registered, naming it.

  **Strictness is per file, so nothing already written changes.** A program with
  no `extern` behaves exactly as before — an unknown free name still passes,
  because rejecting it would reject every embedded program. That permissiveness
  stays pinned by test as decided behaviour.

  `extern` is **contextual**, so it remains usable as an identifier. An unknown
  type name in a declaration is an **error** rather than #609's staged warning:
  the surface is new, so nothing can already depend on a misspelling being
  ignored. The declaration is also indexed by the LSP, so hover,
  go-to-definition and completion now work for names the host supplies.

  **`nodus-vscode` needs republishing** — `extern` is a new keyword, and
  `nodus_gate --consumers` reports the extension stale until it ships a grammar
  that highlights it. The grammar change is made; the publish is not.

- **#493: `register_function` takes a schema, so a host function has a real
  contract.** A tool declared in Nodus had its arguments and return shape
  checked; a function registered from the host had **arity and nothing else** —
  the weaker contract on the more dangerous surface, since a host function runs
  Python outside the VM and the sandbox. The reported case succeeded with a
  plausible-looking result: `write_file(42, {"not": "a string"})` returned
  `"wrote 42 (1 bytes)"`, because `len()` of the map is 1.

  ```python
  runtime.register_function(
      "host_write", write_file, arity=2,
      schema={"path": "string", "contents": "string"},
      returns_schema={"bytes": "int"},
      requires="fs.write",
  )
  ```

  The schema is an **ordered** map of parameter name to Nodus type, applied
  positionally — a host function takes positional arguments, where a `std:tool`
  handler receives one args map. It must name exactly `arity` parameters, and a
  variadic registration with a schema is refused rather than partly covered: a
  positional contract that covered only some arguments would be worse than none.
  A misspelled type fails at registration rather than on the first call, the way
  `requires=` already does.

  **Additive** — a registration without a schema behaves exactly as before.

  Enforced at `_invoke_host_function`, the same chokepoint `requires=` uses, and
  it **raises** rather than returning an err record: a tool reports through an
  envelope its Nodus caller is holding, whereas the defect here is precisely that
  a bad value proceeded. A schema is a type contract, not a sandbox — it
  constrains what reaches the function, not what the function then does.

### Changed

- **#642: a pass that ended `failed` no longer satisfies a goal's `until`.**
  `until` is evaluated against the checkpoints a pass recorded, and a checkpoint
  recorded *before* a `throw` still counted — so a goal stopped and reported
  `goal_satisfied: true` on a run that ended `failed`.

  That was an artefact rather than a policy. The goal loop **already retries a
  failed pass**: a workflow that throws on pass 1 and succeeds on pass 2 reports
  satisfied at iteration 2. So a goal stopped only because the `checkpoint`
  happened to sit before the `throw` — swap those two lines and the identical
  workflow keeps iterating. Termination that depends on statement order inside a
  failing step is not a contract anyone chose.

  **This is a behaviour change.** A goal that stopped satisfied on a failing pass
  now keeps iterating and, if every pass fails, ends with the existing
  `budget_exhausted` err record (`goal 'reach' exhausted its budget (after 3
  iteration(s)) without satisfying its condition`) rather than a success-shaped
  result map. That is consistent with the invariant already stated at that
  branch: a goal that ran out of budget has not met its objective and must never
  return a success-shaped result.

  A **tolerated** failure (`allow_failure`) is unaffected and needs no special
  case — it means the run *completes*, so `failed` is empty and such a pass can
  still satisfy.

  Retrying a failed pass is unchanged, and is pinned: *"a failed pass does not
  satisfy"* is **not** *"a failed pass ends the goal"*, and the obvious
  implementation of the second passes the bug cases while breaking the first.

- **#174: the default workflow runner honours `NODUS_WORKFLOW_STORE_BACKEND`.**
  `get_default_workflow_runner()` hardcoded `LocalWorkflowStore` — the JSON store
  that is explicitly not crash-safe — so an embedder calling `run_workflow()`
  could only get a durable store by calling `configure_default_workflow_runner()`
  at startup. Meanwhile `nodus serve` had honoured
  `NODUS_WORKFLOW_STORE_BACKEND` and `NODUS_WORKFLOW_STORE_PATH` all along: one
  question, two answers, and the half every embedder reaches was the one that
  could not be configured.

  Both halves read the same two variables now, through one pair of readers.
  Setting `NODUS_WORKFLOW_STORE_BACKEND=sqlite` gives a WAL-backed, crash-safe
  store with no code change. An unknown backend name is **refused** rather than
  falling back, so a misspelling cannot quietly cost the durability that was
  asked for.

  **The default is unchanged and stays `local` in 5.x.** Flipping it is a 6.0.0
  change, and not merely because the file location moves: runs already recorded
  in the JSON store are invisible to a SQLite one, so an in-flight `waiting` run
  would silently become unresumable. `nodus workflow migrate-state` migrates
  graph *snapshots*, not store backends, so the flip needs a migration that does
  not exist yet. The same caution applies to switching by hand — switch when
  nothing is in flight, or drain first.

### Tooling

- **An opcode execution census, and one opcode nothing runs.** Phase 1 of the
  opcode semantic audit (issue 412, which stays open for phases 2–3).
  `nodus_gate --opcodes` verifies the *inventory*; nothing measured whether any
  opcode is ever executed. `tools/opcode_census.py` wraps every dispatch entry,
  runs the suite, and reports executions per opcode — executions, not
  appearances in compiled code, because an opcode that is emitted and never
  reached is the case worth finding.

  Baseline: **49 declared, 48 executed, 895,076 executions** across a green
  2,898-test suite. Sixteen opcodes run fewer than 100 times, and `POP_TRY` (18)
  and `FINALLY_END` (60) are the ones to look at first — those two plus
  `SETUP_TRY` are the exception-unwind path where #361, #370 and #371 all lived.

  **`BUILD_MODULE` is executed zero times, and is not emitted either.** Its one
  emit site is the compiler's `ModuleAlias` case, and `ModuleAlias` is built only
  by `tooling/loader.py`, which `runtime/module_loader.py` superseded. Checked
  rather than inferred: an aliased `std:` import, an aliased local-file import,
  `run_source` and `run_file` all execute it zero times, and it does not appear
  in the disassembly of an aliased import at all. `BYTECODE_REFERENCE.md` said
  "Emitted by compiler: yes" and now records the measurement. The opcode stays —
  the set is frozen and removing one is a bytecode-format change.

  Phases 2 and 3 (per-opcode semantic specs, stack-discipline verification) are
  untouched; the census is the risk register they start from.

- **#536: the shell-completion scripts are executed, not just inspected.** Of
  the four shells `nodus completion` emits, only bash was exercised in the
  suite. PowerShell had been checked **by hand** during #534 and written down
  nowhere, so it did not survive that session; zsh and fish had structural and
  quoting assertions only, which cannot tell whether a script loads. A `compdef`
  arity error or a bad `__fish_*` predicate would have shipped green.

  Now: PowerShell is parsed with the parser API and driven through
  `TabExpansion2` (the entry point a Tab press uses); fish is loaded and driven
  through `complete -C`; zsh is syntax-checked and loaded under a real
  `compinit`, proving it defines `_nodus`. CI installs zsh and fish so those
  classes actually run — each is guarded on its shell being present, so without
  the install they would skip in silence, which is the failure mode #536 is
  about. The structural assertions are kept: they are what runs on a machine
  with no shells, and they cover all four at once.

  One gap remains, deliberately: **zsh is not driven through a real completion.**
  It has no non-interactive entry point comparable to `complete -C`, and doing it
  properly needs a `zpty` harness. The coverage table in the test module says so
  rather than implying four equally verified shells.

- **The coverage job stopped skipping the scheduler-fairness tests.** They were
  deselected because they were flaky; #631 fixed that, so the deselection was
  hiding the tests it was added for.

- **#631: the scheduler-fairness tests measured the machine, not fairness.**
  Both tests in `tests/test_scheduler_fairness.py` ran under the default 200 ms
  `EXECUTION_TIMEOUT_MS`, which is wall clock and counts time a coroutine did not
  consume — so a `while (i < 8000)` loop under CPU contention was killed
  (`{'kind': 'sandbox', 'message': 'Execution timed out'}`) before the ordering
  assertion was ever reached. Measured in one load window: **3 of 5 runs red
  before, 5 of 5 green after.**

  The harness now sets its own generous deadline, in a single helper so a test
  added later cannot forget it, and it reports a deadline kill as itself rather
  than as a confusing ordering failure. The deadline is raised rather than the
  loop shortened: fewer iterations would make the interleaving these tests exist
  to observe less likely to happen at all.

  Test-only. **`EXECUTION_TIMEOUT_MS` is unchanged** — it is a deliberate
  production default, and `nodus run --time-limit` is what raises it.

### Fixes

- **#656: `nodus fmt` rewrote a mapped step's `each` clause as `after`, silently
  changing what the program does.** `each` shipped in 5.6.0 (#480); the formatter
  was never taught it, and the parser adds `each_source` to `deps` so the
  dependency cannot disagree with the `in` clause — so a mapped step printed as
  `after SRC` with the loop variable dropped. The result still parsed and still
  ran:

  ```
  original    ok=True   {"discover": [1, 2], "render": [10, 20]}
  after fmt   ok=True   {"discover": [1, 2]}
  ```

  Both report success; the mapped step simply disappears from the results. CI
  runs `fmt --check` over every `.nd` file, so any committed workflow using
  `each` was one format away from this.

- **#657: `nodus fmt` crashed on a single-dimension goal budget, and silently
  dropped `limits`.** #488 made `max_iterations` and `deadline_ms` individually
  optional and added `limits`; the formatter still printed both unconditionally
  and never read `limits`. `budget { max_iterations: 3i }` raised
  `Unknown expr node: None`, and a goal bounded by host meters was reformatted
  into one without that bound — the silent half, and the reason this is not
  merely a crash fix.

- **The formatter is now checked field by field, not node by node.**
  `test_formatter_completeness.py` fails when a node *type* has no formatter
  case, which is why both bugs above were invisible: `WorkflowStep` and
  `GoalPursuit` were "handled", and the new *fields* were not. The new
  round-trip property test parses a corpus, formats it, re-parses, and compares
  the ASTs structurally — so a field the formatter does not render fails the
  suite instead of corrupting a file. It found #657 on its first run.

- **#629: `source_drift` was blind to a resume driven from a different file.**
  The check compared the recorded source against the file at the *recorded
  path*, so it only ever noticed an edit to the file that created the run. A
  resume driven from another file that has its own copy of the flow replayed the
  recorded source, stale, and reported `source_drift: false` — no warning, no
  key on the result. The signal depended on which file the caller happened to be
  sitting in rather than on anything about the run.

  Both referents are checked now, and the second one is compared **at the flow,
  not the file**. That distinction is load-bearing: a resume driver necessarily
  differs from the recorded program somewhere, because it holds the
  `resume_workflow(...)` call the original did not — so a file-level comparison
  would warn every time someone copied the workflow verbatim into their driver,
  while the message claims specifically that the flow differs. Both
  declarations are rendered through the formatter, so the claim is true.

  The `workflow_source_drift` event gains a `referent` field
  (`"recorded_path"` or `"resuming_module"`), so a consumer can tell "the file
  was edited" from "you are resuming with a different program". What executes is
  unchanged — replaying the recorded source is deliberate (#470) and only the
  warning's blind spot was at issue.

### Docs

- **#494: the resume determinism boundary is stated, and one invariant that got
  it wrong is corrected.** A resume re-executes; nothing records what the
  original execution observed, so any fresh read — the clock, randomness, the
  environment, a file, an HTTP response — may come back different. Checkpointed
  `state` is restored faithfully and is the whole of what holds. Measured:

  ```
  fresh now      = 1788019818831
  state started_at = 1788019818831
  fresh now      = 1788019818896     <- replay
  state started_at = 1788019818831
  ```

  The step's **return value is the replay's reading**, so a caller reading
  `steps[...]` after a resume gets the second one.

  New `I-WFLOW-07` states the boundary; the guide's *Checkpoints* section gives
  the supported answer (write it into `state` before the checkpoint) with a run
  example. There is deliberately no replay-safe clock and no divergence
  detection — both remain open on #494, which records the position rather than a
  mechanism.

  **`I-WFLOW-06` was wrong and is corrected.** It claimed completed steps are
  never re-executed across a resume, naming *both* `resume_workflow(id)` and
  `resume_workflow(id, "label")`. True of the plain form only. A label is a
  re-entry point (#486), so its step runs again from the top **and every step
  downstream of it runs again too**, whatever their saved status — measured on
  three completed steps with the checkpoint in the middle. The labelled form is
  the one a debugging loop reaches for, so the invariant was misleading exactly
  where it mattered.

- **The production checklist had the capability defaults backwards.** The
  Operator / Embedder Runbook §6 told operators to set `allow_subprocess=False`,
  `allow_network=False` and `allow_env=False`, each annotated *"(default is
  `True`)"*. All three have defaulted to **`False`** since v5.0.0, so the advice
  described the pre-5.0.0 runtime and implied a bare `NodusRuntime()` could shell
  out, open sockets and read the process environment. It cannot. The item now
  reads as a confirmation that nothing has granted them, and notes that the CLI is
  deliberately unaffected.

- **The runbook now says which unit of concurrent work survives a crash.** A bare
  `spawn()` coroutine lives in process memory only: an unclean exit loses it with
  no record it ever ran, while a workflow step's state is persisted as it goes and
  `rehydrate_runs()` replays it. The distinction was invisible in the API and is
  now §6.2, with the recovery call and its dependence on a durable store (§6.1).
  Closes the near-term half of #180; the coroutine checkpoint API it also asks for
  is untouched.

- **The runbook now states that `register_function()` runs host code unsandboxed.**
  A registered callable executes in the host process with everything that process
  can reach; the confinement flags bound the guest script, not the host function.
  New §6.3 records that this is deliberate — it is the seam where a host lends the
  guest one of its capabilities — names the two consequences (register only what
  you authored; a registered function *is* a capability grant), and points at
  `nodus-extension` for genuinely untrusted plugin code, which loads it in a
  subprocess. Answers #169.

## [5.6.0] - 2026-08-28

### Added

- **#480: a workflow step can map over a list.**

  ```nd
  step render each page in discover { return "rendered \(page)" }
  step index after render { return "indexed \(len(render)) pages" }
  ```

  The body runs once per item, concurrently, and `render` stays **one step**:
  `steps`, `statuses` and `failed` each name it once however many items it ran
  over, and its result is the list of item results in the producer's order.
  `index` joins the whole fan-out and receives that list as one argument.

  `in` is itself the dependency, so `after discover` is neither needed nor able
  to disagree with it. The graph does not grow: `plan_workflow` still shows one
  node, and only the **cardinality** is discovered at run time, which is what
  lets a resume rebuild the run.

  Three outcomes at the edges, deliberately distinct. An **empty** list is
  `skipped` with a result of `[]` (it ran; the answer was no items), so a join
  opts in with `on: [..., "skipped"]` like any other skipped step. A producer
  that returned **no list at all** *fails* and leaves no result, naming the
  producer. Over **1024** instances the run fails before anything runs, charged
  to the producer rather than reported against the scheduler afterwards.

  Closes **#468** as subsumed: dynamic fan-out was the thing it asked for.

  Two things the design doc (D5) anticipated that were removed rather than
  built, because testing showed neither could happen. There is **no
  cardinality-drift refusal on resume** — drift needs the producer to re-run
  *and* the mapped node to re-expand, and those are mutually exclusive. And
  there is **no second copy of the cardinality**, because a completed
  producer's result is already durable and the fan-out re-derives from it.

- **#479: a workflow step can declare its output type.**

  ```nd
  step fetch with { returns: "map" } { return {"rows": 42i} }
  ```

  Checked by `nodus check` the way a function's return type is — by setting the
  analyzer's `current_return` for the walk of the step body, so every `return`
  inside it goes through the same comparison. The body was already walked (#401);
  it simply had nothing to check its own returns against.

  Optional and static-only: a step without it is checked exactly as before, and
  nothing is enforced at run time. **An unknown type name is an error here, not a
  warning** — unlike a function annotation (#609 warns until 6.0.0), the option is
  new, so nothing can be relying on a misspelling being ignored, and a `returns:`
  that silently meant "any type at all" would be the declared-but-inert field this
  issue is about.

  **It describes the step, not the edge** — the sub-decision D2 deferred, settled
  by running it. A step declaring `returns: "int"` that is then *skipped* still
  binds `nil` in its dependent; that is the edge's behaviour and `on: ["skipped"]`
  is how a dependent opts into it. So `returns:` does not imply nullable, and
  declaring it on a step that may be skipped is not an error.

  This half needed #609: a bare type name that silently meant `any` when
  misspelled would have made the whole field inert.



- **#488: a goal can be bounded by what it spends.** `budget` gains `limits`, a
  map of **host-registered meters**, and `max_iterations`/`deadline_ms` become
  optional — at least one bound is still required.

  ```nd
  goal reach over tune {
      until reached("good_enough")
      budget { max_iterations: 5, limits: { tokens: 100000 } }
  }
  ```

  ```python
  runtime.register_meter("tokens", lambda: session.total_tokens)
  ```

  **Nodus does not know what a token is and deliberately never will.** There is
  no model invocation anywhere in the core, and that absence is load-bearing — it
  is what forces every semantic decision across a typed boundary to a host
  handler. So a `max_cost_usd` that Nodus enforced by counting tokens was never
  available, and a *named* cost dimension would bake in a unit it cannot define.
  The host counts; the goal declares a ceiling; the runtime compares two numbers.

  **The outer vocabulary stays closed and parse-checkable**, which is the property
  this surface already had and the issue explicitly praises — an unknown budget
  key is still refused at parse time with an accurate message. Only the
  *contents* of `limits` are open, and they are resolved against the host.

  **A declared meter with no accountant is an error**, refused before the first
  iteration so nothing is spent — the rule `CapabilityDecision` already applies
  to `ask` with no approval channel. A reader that raises counts as a breach: a
  host whose accountant is broken has lost the ability to bound the loop.

  Also new: an **implicit cap of 10,000 iterations** when no iteration or
  deadline bound is declared. Making both optional meant `limits` could be the
  only bound, and a meter is only a bound while it *moves* — a stuck counter
  would loop forever, which is exactly what `budget` exists to prevent. Found by
  mutation testing, which hung. It is reported distinctly, naming what to check.



- **#481: workflows and goals take parameters.**

  ```nd
  workflow build(mode) {
      step compile { return "compiling in \(mode)" }
  }

  run_workflow(build, {mode: "lite"})
  ```

  Each parameter is in scope in every step body. Both `{mode: "x"}` (a record)
  and `{"mode": "x"}` (a map) bind; a record is normalised before it reaches run
  metadata, since a `Record` is not JSON serializable.

  **Bound at the call, not by calling the flow value.** The issue sketches
  `run_workflow(build("lite"))`; the flow value is an ordinary map whose shape
  #394 has just finished pinning, so that would be new syntax on it. D4 in
  `docs/design/workflow-dsl/00-cluster-decisions.md` has the reasoning.

  **The argument is part of the run, which is the point.** It is persisted into
  run metadata beside `workflow_topology`, and a resume reads it back rather than
  re-binding it. The module-global workaround this replaces had three problems,
  and the third is why the feature exists: `state x = mode` was captured and
  restored while a bare `mode` read inside a step was re-derived on rebuild — so
  the *spelling* silently decided whether the value survived a resume, and
  nothing in the language marked which was which.

  Refused where it is written rather than left to a step reading `nil`: a missing
  argument, an unknown one, arguments to a flow that declares none, a parameter
  colliding with a step or state-cell name, a duplicate parameter, and an empty
  `()`. `plan_workflow` needs no arguments — it reports shape, not values.

  **A `goal … over …` cannot bind them** and says so, naming both the goal and
  the workflow. That form has no slot for arguments; left to the binder it
  reported "pass them to `run_workflow(tune, {…})`", naming a call the author did
  not write.

  New builtin `workflow_arg`, emitted by the lowering as a prelude `let` per
  declared parameter. Reached only through `builtin_call` (#411), so binding the
  name in guest code cannot intercept a step's own parameter reads.

- **#491: `NodusRuntime.register_agent` / `unregister_agent`.** The agent registry
  was reachable only through `nodus.services.agent_runtime.register_agent`, which
  defaults to the **process-global** registry — so an embedder who scoped a
  runtime with `agent_registry={}` and registered the obvious way got a handler
  that runtime could neither see nor call:

  ```
  scoped runtime sees : []
  calling it          : false | [{"type": "AgentError", "message": "No handler
                                  registered for agent 'picker'", ...}]
  ```

  Registered, and invisible. The methods route to whichever registry *that*
  runtime uses, so registration and scoping cannot disagree. This is a
  correctness fix, not only the ergonomic one the issue asked for — an embedder
  reaching for `register_agent` beside `register_function` got an
  `AttributeError`, but an embedder who found the module-level function got
  something worse.

### Changed

- **#479: the compiler no longer discards a declared signature.**
  `FunctionInfo` carries `param_types` and `return_type`, populated from the AST
  at its single construction site. Static-only, exactly as before — nothing here
  is enforced at run time. It is the prerequisite #479 names for both its halves,
  and what `returns:` will need.

  Also corrected: the issue suggests deriving in the frontend *"since
  `tool.register` is lowered from source anyway"*. It is not lowered —
  `stdlib/tool.nd` defines `fn register(meta) { return tool_register(meta) }`, an
  ordinary call to a builtin — so no frontend pass knows a registration is
  happening, and the signature has to survive compilation instead.

- **#479: the tool schema's type vocabulary stops being a third enumeration.**
  `_NODUS_TO_JSON_TYPE` was a private list of seven names beside `TYPE_NAMES` and
  the parser, and it had already drifted: `record` and `function` were missing, so
  neither could be named in a tool schema. `record` maps to `object`; `function`
  is named and refused with a reason (a callable does not cross a tool boundary)
  rather than reported as unknown. Pinned against `TYPE_NAMES` by test.



- **`state_contribute` and `__workflow_checkpoint` are now in `BUILTIN_NAMES`,
  and that does not make them newly reachable.** A test asserted
  `state_contribute` was absent from the set on the reading that absence made it
  non-public. It did not: the name resolved from a guest program the whole time,
  because the VM dispatches from its own table and `BUILTIN_NAMES` is not
  consulted for resolution. What kept a program from contributing to a cell with
  no policy was — and still is — the runtime guard `state contribution outside a
  workflow step`.

  Its neighbour asserted only that *some* error came back, so it passed on that
  runtime guard's message rather than on non-resolution, and would have kept
  passing if resolution had broken. Both are corrected to assert what they
  actually mean.



- **#474: the positioning clause is "for building agentic hosts".** Ledger
  decision **D1**, open since Audit 01, is decided and applied:

  > An orchestration DSL and embedded runtime for **building agentic hosts**.

  It replaces *"for hosting agentic systems"* in `pyproject.toml` — which is the
  **PyPI summary** and so is permanent at each tag — and in `llms.txt`,
  `llms-full.txt` and `README.md`. The claim it makes is the one the audit series
  converged on and six corpora support: the model loop belongs to the host, and
  the absence of a model in the core is what makes that boundary unblurrable.
  Nodus is what you build the host out of.

  **A partial sweep had already run, and that is the part worth recording.**
  Three of the four files said *"hosting agentic systems"*; `llms-full.txt` still
  said *"building agentic systems"* — the one file `nodus_gate` did not scan
  until #483. `tests/closed_issues/issue_474.py` now pins all four (plus the
  packaged `src/nodus/llms.txt`) to one string, and was confirmed red against the
  exact state the repo was found in.

- **The companion-package count was wrong in seven places.** *"32-package
  companion ecosystem"* against a verified live count of **35** — in `README.md`,
  `llms.txt` (×4), `llms-full.txt`, `getting-started.md` and `CLAUDE.md`. Same
  class as the version strings this project already refuses to carry in prose: a
  hand-maintained number nothing checked. The test now at least requires the
  prose to agree with itself.

- **`llms-full.txt` dated v5.5.0 to 2026-08-25.** It published on the 26th.


- **#609: an unrecognised type name is reported instead of silently meaning
  `any`.** `fn b(name: strng)` used to check clean — one transposed letter
  disabled checking on that parameter permanently, with no diagnostic at any
  altitude. It is a **warning** now, in `nodus check` and inline in the editor,
  and becomes an **error at 6.0.0** alongside #545 and #547. The exit code does
  not change until then.

  ```
  $ nodus check typo.nd
  typo.nd:2:12: warning: Unknown type name 'strng' — did you mean 'string'? ...
  typo.nd: OK (1 warning(s))
  ```

  Two consequences of the same hole are fixed with it. **`map` is now a type
  name**: it was absent while looking nameable, so `fn g(y: map) -> map` checked
  clean and meant `any` — and `map` is what `run_workflow`, `plan_workflow` and
  most step bodies return. **`record` and `nil` are now spellable**: both are
  keywords, so they never reached the lookup, and `record` sat in the table as an
  entry no program could use. `map` and `record` are interchangeable to the
  checker, because the analyzer infers `record` for both literal forms and a
  checker that told them apart would reject correct code.

  The validation lives in `parser.parse_type_name` — the one place that sees an
  annotation's name *and* its token — and `nodus check` and the editor
  diagnostics both read the list it produces rather than each deciding what a
  type name is. That is deliberate: those two walkers are the pair that drifted
  in #401 and #597, and `tests/closed_issues/issue_609.py` asserts they agree
  rather than checking each alone.

### Fixes

- **#480 follow-up: `each` is a named contextual keyword, and the keyword list
  is checked in both directions.** `each` shipped as a bare string literal in
  `parser.py`, so `lexer.ALL_KEYWORDS` never learned about it — which is the
  exact defect #357 fixed, reintroduced. Editor grammars, docs and
  `nodus_gate --consumers` all read that list, so the VS Code extension would
  have rendered `each` as a plain identifier and the consumer gate could not
  have noticed, because the fingerprint it compares never moved.

  Every check in `tests/test_keyword_coverage.py` ran **list → parser** (each
  word the list names must parse). Nothing ran **parser → list**, so a word the
  parser recognised but the list did not name was invisible. That direction now
  exists, and it reads `parser.py`'s source, because a behavioural test cannot
  tell a word matched from a named set from the same word matched from a
  literal.

  It immediately found two more: **`checkpoint` and `state`** were also absent
  from the list. The VS Code grammar happened to name them by hand, which is
  precisely the coupling the list exists to remove.

- **#632: `RuntimeService.close()` waits for its sweeper instead of only asking
  it to stop.** It set the stop event and notified the condition, then returned
  — so it could return while `_worker_sweeper_loop` was still inside `sweep()`,
  touching the workflow store. Any caller that then removed the store's
  directory raced a live thread: on Windows `PermissionError: [WinError 32] ...
  workflow_framework.sqlite3`, on Linux `sqlite3.OperationalError: no such
  table: workflow_runs` followed by `OSError: [Errno 39] Directory not empty`.
  Only Linux's symptom was ever seen in CI, which is why this was triaged for
  months as a temporary-directory race.

  This is the **second** sweeper. #591 fixed the same symptom by stopping the
  default runner's `nodus-workflow-sweep` daemon and left this one running, so
  the bug outlived its own fix — two threads, one question.

  Affects embedders, not just tests: a service pointed at a scratch directory
  could not reliably release it. A sweeper that overruns the join is reported
  as a `RuntimeWarning` rather than raised, because `close()` runs from
  `server_close()` inside `finally` blocks.

- **#480: a mapped step is one step in every aggregation that names steps.**
  `steps`, `statuses`, `failed` and `tolerated` all key by step name, and each
  learned separately that an instance is not a step, getting it wrong
  differently each time. One failing item named its step **twice** in `failed`;
  whichever instance was iterated last stood in for the step in `statuses`,
  reporting `completed` for a step that had failed. Asked once now, at
  `TaskNode.is_mapped_instance`, with a source assertion so a fifth aggregation
  cannot quietly answer it again.

- **#479: `tool.register` refuses a handler it could never invoke.** A tool
  handler is called with **exactly one argument** — the args record
  (`run_closure(handler, [args])`). A handler declaring any other number can
  never run, and registration accepted it anyway; the failure surfaced at *call*
  time as a bare `Stack underflow` naming the handler, with nothing connecting it
  to the registration.

  ```
  tool.register: tool 'app.t' handler declares 2 parameters ('name', 'times'), but
  a handler is called with exactly one argument: the args record. Take one
  parameter and read the fields from it, e.g. `fn handler(args) { ... args.name ... }`.
  ```

  **This is not the schema derivation #479 asks for, and building it is what
  showed why.** The `schema` names the keys of that one args record; a signature
  cannot carry them, so deriving a schema from handler *parameters* would encode
  a calling convention this registry does not have. The issue's own example
  registered fine on `main` and then died on invoke — characterised and filed as
  **#624**. What the signature genuinely says here is arity, and that was the
  field going unchecked. The issue's premise holds exactly; the field is
  different.


- **#616: a capability policy could be bypassed by writing the async form, and
  seven builtins could be shadowed by a host.** `BUILTIN_NAMES` is a
  hand-maintained set; the VM's dispatch table is what actually runs. They had
  drifted by seven names, and two guards consult the stale one.

  **The security half.** `agent_call` is governed by the `agent.call` capability;
  `agent_call_async` was one of the seven, so it carried no capability at all:

  ```
  agent_call("picker", {})        -> Blocked: agent.call is not granted to this runtime
  agent_call_async("picker", {})  -> {"choice": "rebase"}          <- same agent, same policy
  ```

  A `DenyList("agent.call")` refused one spelling and permitted the other. It is
  governed by the same capability now.

  **The shadowing half.** `register_function`'s "cannot override a builtin"
  check reads `BUILTIN_NAMES`, so `register_function("chr", …)` was accepted and
  `chr(65i)` returned `"HIJACKED"`. That guard is a security boundary: a host
  installing a fail-loud guard under a guest-reachable name has to know the
  guard is the only thing there. All seven are refused now.

  The seven: `agent_call_async`, `chr`, `ord`, `effect_get_result`,
  `state_contribute`, `collection_validate_reduce_fn`, `__workflow_checkpoint`.

  **Why the existing coverage did not catch it.** `test_capability_coverage.py`
  already requires `BUILTIN_CAPABILITIES | NO_AUTHORITY_BUILTINS ==
  BUILTIN_NAMES`, precisely so a new builtin fails the suite until someone
  decides which side it is on — but that totality was measured against the
  *stale* set, so it was true of the wrong thing.
  `tests/closed_issues/issue_616.py` anchors it to the dispatch table, read out
  of a constructed `VM` the way `nodus_gate --opcodes` reads the instruction set.


- **`llms-full.txt`'s workflow example had never parsed.** `step validate after []`
  is `Expected identifier, got '['`. It went unnoticed because the doc gate's file
  list included `llms.txt` and not `llms-full.txt` — so the file 5.5.0 shipped
  inside the wheel for agents to read was the one nothing checked. Fixed, and
  `llms-full.txt` is now scanned by `nodus_gate --static`/`--runtime`; its other
  three blocks were already clean.

### Tooling

- **#612: two store tests patched the process-global `os.replace`, so a
  concurrent rename anywhere failed them — or was failed by them.**
  `LocalWorkflowStore._replace_with_retry` takes an injectable `replace=` now
  (defaulting to `os.replace`, resolved late, so no real caller changes) and the
  tests inject instead of patching.

  The counting test asserted 3 and saw **7** on CI: its own logic accounts for at
  most 3, so four renames came from elsewhere in the process — the graph-state
  writer and the bytecode cache both call `os.replace`. Reproduced
  deterministically with a background renamer: the old form counts **9**, the new
  form counts **3**.

  The sibling was the more dangerous of the two. It made the global raise
  `PermissionError` for the whole retry window — roughly 200 ms of `time.sleep` —
  so any concurrent rename in the process failed outright while it ran.

  A third assertion comes with them, on the mechanism rather than the count: a
  count-based test passes whether the fake was injected or installed globally, so
  it cannot tell the two apart, which is how the original survived.



- **`nodus_gate` scans `llms-full.txt`.** One list decides which documents are
  checked; it had two AI-discoverability files in it and covered one.

### Docs

- **The companion count was still wrong in `README.md`, in a second place.** The
  sweep that fixed seven occurrences of *"32-package"* missed the paragraph at
  `README.md:213` and the summary in
  `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md`, both of which still read
  32 standalone / 33 projects against a verified live count of **35 / 36**.
  Caught by a Gate 10b probe written before the tag, which matters because
  `pyproject.toml` sets `readme = "README.md"`: whatever that file says at tag
  time is the PyPI project page forever.

- **#624: the `std:tool` guide taught the wrong handler shape.** Its registration
  example — the thing people copy — was

  ```
  handler: fn(query) { return http_get("...?q=" + query) }
  ```

  alongside a `schema` declaring `query`. That reads unmistakably as *"the
  parameter is the schema key"*. It is not: a handler is called with **one
  argument, the whole args record**, so the example produced
  `?q=record {"query": "..."}`.

  That is why anyone wrote a multi-parameter handler in the first place — and
  those crash on invoke with a bare `Stack underflow` (refused at registration
  since #479).

  The example is corrected, **self-contained, and gate-checked now**: its
  allowlist entry stopped matching when the block changed, so a future edit
  reintroducing the wrong shape fails `nodus_gate --runtime` rather than sitting
  there. Verified by breaking it deliberately and watching the gate catch it.

  The guide also states the contract explicitly, including the case that cannot
  be refused: a *single* misnamed parameter — `fn(query)` — is a legal handler
  that happens to receive the record under a misleading name, which is why the
  correct spelling is `fn(args)`.

  **Argument spreading was considered and rejected.** Supporting
  `fn(query, limit)` by spreading the record would make the one-parameter case
  ambiguous — is `fn(args)` the whole record, or the value of a key named `args`?
  Backwards compatibility forces the first, leaving the semantics
  arity-dependent: one rule for one parameter, another for two. One clear rule is
  worth more.



- **#491: `docs/guide/agent-host-boundary.md` — the host boundary was
  undocumented.** `agent_call` is the point where a program hands a *semantic*
  decision to the host, and it appeared **zero** times in `docs/guide/`,
  `llms.txt` and `llms-full.txt`. Every hit in `docs/` was in an eval record or a
  governance document — writing *about* the project, not *for* a user.

  The new guide covers all five surfaces (`agent_call`, `agent_call_async`,
  `agent_available`, `agent_describe`, `action agent … with { … }`), registering
  a handler, agents vs tools, the workflow shape, and handler bounding. Two
  things it documents that the shape actively invites getting wrong:

  - **The nine-key envelope.** `agent_call` does not return the handler's value;
    it is under `result`. Four of the other keys (`filename`, `stdout`,
    `stderr`, `diagnostics`) describe the *calling script*, not the agent.
  - **Failure is soft.** An unregistered agent or a raising handler yields
    `ok: false` and the run *continues*, so an unchecked call looks like it
    worked. Inside a step, the unchecked read then fails the step — which
    presents as a step missing from `steps` while the run's `error` stays `nil`.

  `llms.txt` and `llms-full.txt` both carry it now; the latter gets the envelope
  and the soft-failure rule inline, since an agent reading it and concluding
  Nodus had no agent boundary was reading it correctly.

- **The guide index gained an entry.** `getting-started.md`'s "AI-native and
  agentic patterns" section had exactly one file in it.



- **`docs/guide/types-and-values.md` said `nodus check` was syntax-only. It is
  not.** The page asserted twice — in §1 and §9 — that *"`nodus check` does not
  catch type errors — it only validates syntax"*, while `nodus check` has been
  reporting `Type error at f.nd:6:17: expected string but got int` for annotated
  code at both the definition and the call site. New **§9.1** documents what is
  actually checked, the full list of type names, that annotations are
  static-only and optional, and the unknown-name warning. Every example run and
  pasted verbatim.



- **An `after` edge carries the dependency's value, and the guide never said so.**
  Inside a step body each name declared with `after` is bound to that step's
  return value, and a step that did not declare the dependency cannot read it —
  correct scoping, working since the DSL shipped, documented nowhere in
  `docs/guide/`, `llms.txt` or `llms-full.txt`. A reader concludes they must route
  all data through `state`. New §3.1 in `docs/guide/workflows-and-tasks.md`, with
  the skipped-dependency case: a `skipped` producer binds `nil`, indistinguishable
  from a step that returned `nil`, and only `r["statuses"]` tells them apart.

- **`docs/design/workflow-dsl/00-cluster-decisions.md`** — decisions for the eight
  open workflow-DSL design questions (#468, #472, #479, #480, #481, #488, #577,
  #578), taken together because three of them stop being independent when read
  side by side. Records one prerequisite defect found while verifying them: an
  unrecognised type name silently means `any`.

### Ecosystem

- **#477: the A2A wire adapter is published as `nodus-a2a-wire` 0.1.0.** It had been
  complete since 2026-05-29 and unpublishable, because it declared the distribution
  name `nodus-a2a` — taken by the coordinator. Nothing in `nodus-lang` changes.

  **Renaming the distribution was not enough, and that is the part the issue did not
  have.** The published `nodus-a2a` coordinator ships a Python module *also* called
  `nodus_a2a`, so both distributions wrote one directory into site-packages.
  Measured before the fix: installing the wire adapter on top of the coordinator
  left `AgentCoordinator`, `AgentRegistry` and `DeadLetterService` **gone**, with
  pip reporting success both times. The module is `nodus_a2a_wire` now and the two
  coexist. This is NAME-COL-001 again — the distribution name is what a user types,
  the module name is what Python resolves, and fixing one does not fix the other.

  **`nodus-lang` was in its `dependencies` and never imported**, which is a larger
  correction than the `<5.0.0` cap the issue names. `grep -rnE
  "^\s*(from|import)\s+nodus" src/` is empty; the one import in its tests sits in
  a `try/except ImportError` that skips. Per the dependency-audit rule that is not
  a dependency — a host constructs `A2AHttpServer` and wires it to their own
  `NodusRuntime.tool_registry`. It is a `dev` extra now, uncapped. The suite is
  188/188 against nodus-lang 5.5.0, so the cap protected nothing.

- **`nodus-a2a-wire` is tracked by `tools/check_publish_drift.py`**, which now covers
  11 companions, all matching what they published.


- **The package picture is re-verified against the live index, and four claims were
  wrong.** Prompted by a simple question — are we sure what our packages actually
  are? Every first-party name was probed against PyPI rather than read out of a doc.

  - **`CLAUDE.md` named the wrong directory for the A2A wire adapter.** It called
    `C:\codev
odus-a2a-wire` "the local worktree" of the wire repo. That directory's
    remote is `nodus-a2a` and its HEAD is **detached**; the worktree that actually
    corresponds to `github.com/Masterplanner25/nodus-a2a-wire` is
    `C:\codev2a-wire-pub`. Following the old text would push wire-adapter commits at
    the coordinator repo. Both are CrewAI-showcase artifacts, which nothing recorded.
  - **The wire adapter is 188 tests, not the 180 claimed.**
  - **The companion count was stale by two** — "32 live on PyPI (33 counting
    nodus-lang)" against a verified **34 + nodus-lang = 35**, and it was already wrong
    before `nodus-flow` was published. Replaced with a dated figure and the method to
    re-derive it, since a hand-maintained count is the same failure mode as the version
    strings the section below already refuses to carry.
  - **`docs/ecosystem/README.md` hardcoded two consumer versions** that
    `tools/consumers.json` is supposed to own, and had `nodus-mcp-server` a patch
    behind. The consumer rows now point at the manifest; the one stale version is
    corrected. The other seven hardcoded versions in that table were checked and are
    accurate.

- **`nodus-flow` is now tracked by `tools/check_publish_drift.py`.** It never was under
  either name, so a published first-party package sat outside the sweep that asks
  whether a companion has drifted from what it published. 10/10 match.


- **#483: the standalone `nodus-workflow` package is renamed `nodus-flow`.** It
  was never the engine behind the `workflow` keyword — that ships inside
  `nodus-lang` as `nodus_lang_workflow` and is not separately installable — but
  the name read as though it were, and that misreading is on the record: Audit 03
  F1 attributed the standalone package's architecture to the language core,
  concluded the project had *"forked its own thesis"*, and made resolving it its
  top recommendation. It stood in `EXTERNAL_AUDIT_LEDGER.md` as a confirmed
  finding for months.

  Nothing in `nodus-lang` changes; this is a reference update plus a policy.
  `COMPANION_LIBRARY_CONTRACT.md` **§8b** now states the rule that prevents the
  third instance: a first-party distribution may not take the name of a language
  construct it does not implement. The old PyPI name is kept as a deprecation
  alias so `import nodus_workflow` keeps working, and so nobody else takes it.

  Two corrections landed with it. The ledger and #483 both attributed the phrase
  *"…for Nodus AI systems"* to the package's published **summary**; it is not
  there — it is in the README, which is the long description. That distinction is
  the argument for renaming rather than rewording, since the metadata a reader
  would have to open was never what misled anyone. And the `nodus-name-col-consolidation`
  skill planned to publish the in-tree engine *as* `nodus-workflow`, which §8b now
  forbids; it is marked superseded.

### Known

- **The wiki still names a v4-line release as its stable one** — four minors and
  a major behind what ships — and repeats the 32-package count, in `Home.md` and
  `Roadmap.md`. It carries no positioning clause, so it needed nothing for D1.
  Left for a wiki-wide version sweep: a partial update there would be worse than
  none.

## [5.5.0] - 2026-08-26

### Added

- **#605: `nodus docs` — where the guide, the index and the agent skills live.**
  Nothing in an installed `nodus-lang` led anywhere: the wheel shipped Python and
  `stdlib/*.nd` only, no CLI command mentioned the documentation, and PyPI
  **strips the README's relative links entirely** — fetched the live page and
  `llms.txt`, `nodus.skill` and `project-CLAUDE.md` rendered as plain text with
  no href. An agent inside a venv had no next step, which is exactly how this was
  reported. `llms.txt` now ships as package data, and `nodus docs` (`--json` for
  a machine) prints it plus the guide, embedding page and skills. The URLs are
  pinned to the **running version**, not `main`: an agent on 5.2.0 reading main's
  guide is how the shipped skill came to teach a default removed two releases
  earlier.

### Fixes

- **#605: the shipped Claude/Codex skill described v4.1.1, and part of it was
  wrong.** `skills/nodus.skill` declared `version: "4.1.1"` through nine
  releases. It taught that `NodusRuntime()` defaults to `timeout_ms=200` and that
  you must always pass `timeout_ms=None` — measured, it is `None`; that trap was
  removed in #97, so the skill prescribed a workaround for a fixed bug. And it
  said **nothing** about `allow_subprocess`/`allow_network`/`allow_env`, which
  are `False` since v5.0.0, so an agent following it wrote embedding code that
  silently could not shell out and got no explanation. CLAUDE.md names that risk
  exactly: *advice written against the old default is backwards.*

  The v4 body is unchanged and still correct — 5.x added surface rather than
  breaking syntax — so this refreshes the version metadata, replaces the
  embedding section, and adds a "what is new since v4" section covering
  deny-by-default, `goal … over …`, join `on:`/`upstream_failed`,
  `allow_failure`, folded state cells, catch-less `try`/`finally`, channel
  backpressure, `nodus graph` no longer executing, and the `run_source` filename
  change. Every code sample in it was **run**; the folded-state one was wrong
  twice before it was right (`state x: int` does not parse, and a folded cell is
  written with `+=`, not `=`).

  `skills/project-CLAUDE.md` and `skills/project-AGENTS.md` said "Nodus v4
  (`nodus-lang 4.1.1`)" too — a template users copy into their own projects as a
  standing instruction file, so a stale one propagates.

  All four version claims are now registered in `tools/version_claims.json`, so
  `nodus_gate --versions` fails on them rather than a reader noticing nine
  releases later.

- **#605: every link in `README.md` is absolute.** All 23 were relative, and PyPI
  reaches more installers than GitHub does. `readme = "README.md"` plus release
  immutability makes a relative link permanent for that version.




- **#602: editor diagnostics stop reporting correct code as an error, and start
  reporting six kinds of typo they were accepting.** `_SemanticAnalyzer` had no
  case for `DestructureLet`, so `let [alpha, beta] = …` followed by
  `print(alpha)` reported **`Undefined variable: alpha`** — a false error on
  every line reading a destructured name. That is #401's own failure mode
  recurring for a different binding form: that issue fixed "the diagnostics
  engine never bound *any* block-scoped `let`, so every function local was a
  false Undefined variable". Same engine, same symptom, a form nobody
  re-checked. A false positive is worse than a missing warning, because it
  teaches people to ignore the panel and the true ones then cost nothing to
  ignore too.

  The completeness check added alongside turned three missing cases into seven.
  `ActionStmt`, `GoalPursuit`, `CompoundAssign`, `FieldAssign`,
  `InterpolatedString` and `Match` were all unwalked, so a typo in any of them
  was silently accepted — including `print("v=\(typo)")`, probably the most
  common place a name appears in a Nodus program.

  Every new case is paired with a negative control, since a walker that reports
  everything is as useless as one that reports nothing.

- **Pattern-name collection is one implementation instead of four.** The
  compiler had `Compiler.collect_pattern_names`, the workflow lowering had
  `_collect_pattern_names`, `lsp/server.py` grew `_pattern_names` in #597, and
  the analyzer above needed the same thing — which would have made a fifth copy,
  for the very bug a missing case caused. It now lives in `ast_nodes` as
  `pattern_names` and everything delegates. Worth noting why three survived:
  `nodus_gate --shapes` keys its duplicate detection on name *and* signature, so
  `collect_pattern_names` and `_collect_pattern_names` never collided. A renamed
  copy is invisible to it.

- **#598: the editor and the runtime resolve an import the same way.**
  `resolve_import_path` existed twice — 159 lines in `runtime/module_loader.py`
  and 55 in `tooling/loader.py`, 38% similar — and `nodus lsp` and
  `tooling/diagnostics.py` import from the second. The short copy had **no
  entry-point lookup**, which is how a pip-installed companion ships its `.nd`
  files, so `import "nodus-mcp"` resolved when run and read as `Import not found`
  in the editor. A false error on correct code is worse than a missing one: it
  teaches people to ignore the panel, after which the true errors are worth
  nothing either.

  Four functions around it — `import_error`, `ensure_project_root`,
  `resolve_with_extensions`, `try_resolve_with_extensions` — were **byte-identical**
  copies, so this was never a difference of purpose. Nor was there a structural
  reason for it: `tooling/loader.py` already imported `ModuleLoader` from the
  module it was forking. All five are gone; the two the editor needs are
  re-exported and declared in `__all__`, the rest removed outright.

  `tests/test_import_resolution_is_shared.py` keeps it gone two ways — by
  identity, and by behaviour over a corpus of import forms, because "they are the
  same object" stops being true the moment someone adds a wrapper. The
  entry-point case skips rather than passing when no companion is installed, since
  "not found on both sides" would agree while proving nothing.

- **#597: the editor sees inside a step body.** `_DocumentIndexer` builds the
  definitions, references and scopes behind hover, go-to-definition and
  completions, and it had no case for `WorkflowDef` or `GoalDef` — so everything
  inside a step was invisible to it, in exactly the place orchestration logic and
  generated code live. The flow's *name* was indexed, which is why this read as
  "the editor half-works" rather than as an outage. #401 found two walkers
  skipping step bodies and fixed both; this was the third, in the same file as
  one of them, and it survived four more releases.

  Three further gaps in the same walker, found by the completeness test below
  rather than by reading it: `let [a, b] = …` bound **nothing**, so destructured
  names had no hover or go-to-definition anywhere; `action agent … with { … }` —
  the commonest statement in a step body — resolved no names in its payload; and
  `goal X over Y` never recorded the name it declares. Walking step bodies
  without the action case would have indexed the `let`s and skipped the actions,
  which every behaviour test would still have passed.

  The durable half is `tests/test_lsp_step_bodies.py`, which drives off the AST
  node list the way `tests/test_formatter_completeness.py` does for the
  formatter: every node is either handled or named in an exemption list with a
  reason, so a new statement node fails a test that names it instead of being
  discovered by a user whose editor goes quiet. It checks **both** walkers,
  because `action …` parses as an expression wrapped in `ExprStmt` — a
  `_walk_stmt` case for it is dead code, which is what the first version of this
  fix added.

- **#596: a step's `timeout_ms` bounds an `action agent` handler, which it did
  not.** #398 made `action agent` dispatch its handler off the scheduler thread
  so independent steps overlap. #424 then bounded agent handlers by reading the
  step budget from `vm.scheduler.current_task` — which the scheduler sets
  immediately before a coroutine resume and clears in the matching `finally`, so
  it is readable only *on that thread, inside that resume*. The worker runs after
  the coroutine suspends, so it read `None`, added no candidate, and the call ran
  unbounded. The two landed in the same cycle and nothing connected them.

  It looked like it worked because of a race: the worker thread often called
  `_effective_timeout_ms` before the scheduler cleared `current_task`. On a
  developer machine the worker usually won; on CI under coverage it did not, and
  the run took the handler's full block every time — which is how this was found,
  by instrumenting a failing CI run rather than by reading the code.

  The budget is now read where it is knowable — on the scheduler thread, past the
  guard that guarantees the coroutine is current — and passed to the worker.
  `_effective_timeout_ms` is still the only place that decides; only the moment it
  is evaluated moved. `call_agent` gained an explicit `timeout_ms`, with a
  sentinel so a captured `None` still means unbounded rather than "not supplied".

  So `I-424` now holds for `action agent`, not only for a synchronous
  `agent_call`. The regression tests assert on **thread identity** rather than
  elapsed time, deliberately: which thread reads the budget is deterministic,
  whether it wins the race is not, and a timing assertion would pass on one
  machine while the bound stayed broken on another.

- **#585: both halves of a run's state relocate together, and the capability floor
  follows them.** A durable run is one thing split across `.nodus/graphs/` (graph
  state and checkpoint) and `.nodus/workflow_framework/` (the run record). #476
  gave the two halves a shared *lifecycle*; their *location* stayed asymmetric —
  `NODUS_WORKFLOW_STORE_ROOT` moved the records and the graph root was a hardcoded
  module constant with no override at all. So "give this process its own store"
  was not expressible, and every tenant in a process shared one CWD-relative graph
  directory. `NODUS_RUN_STATE_ROOT` now moves both. There is deliberately **no**
  graphs-only variable: a second knob would re-enable the half-relocated state
  this fixes. `NODUS_WORKFLOW_STORE_ROOT` keeps working and keeps moving the
  records alone.

  **The security half.** `DEFAULT_FLOOR` forbids a Nodus program from writing into
  the runtime's own state, and decided that by matching a literal `.nodus` path
  segment — so the *supported* way to relocate the store also moved it outside the
  floor. Demonstrated rather than inferred: with `NODUS_WORKFLOW_STORE_ROOT` set,
  a guest's `fs.write("../relocated/pwned.txt", "x")` landed in the live run store
  while the identical write to the default location was denied. The floor now also
  asks whether a path is inside a root the runtime is *currently* using, so
  relocated state is covered — and a new state directory that does not go through
  `nodus/runtime/state_paths.py` is not. This hole predates the issue and applied
  to the existing variable, so it is fixed here rather than filed.

  **The doc gate is deliberately not switched over yet.** It redirects the run
  records only, so a `--runtime` run still leaves ~67 graph-state files in the
  working tree. Pointing it at the new variable is a two-line change that works,
  and it reproducibly turns
  `test_agent_handler_timeout.py::test_a_step_timeout_bounds_a_blocking_handler`
  red on CI — 6/6 with it, 0/9 without across five bisect branches. That test is
  #11 of ~2766, so nothing after it can be the cause, and the failure is binary
  rather than marginal: the run takes the handler's full 3 s instead of the
  step's 300 ms, meaning the bound does not fire at all. Deferred with its
  evidence rather than merged with a known trigger; filed as #596.

  `.nodus/{cache,modules,deps.json}` are project-scoped, resolved against
  `find_project_root()`, and deliberately not moved by this variable.

- **#584: a graph response names the graph *this request* produced, or none.**
  `_graph_metadata` fell back to `latest_graph_state()` when it could not resolve
  a graph id, and that helper read the process-global `.nodus/graphs/`, sorted the
  filenames, and returned the last — but a graph id is `uuid4().hex[:8]`, so
  sorting them lexicographically orders them by nothing. A request that declared
  **no graph at all** was therefore answered with another request's graph id,
  status and full task map, step return values included; on a server handling more
  than one caller that is a cross-request leak, not a wrong label. Resolution now
  reads only state belonging to the request — the id supplied, the plan this VM
  built, the events this VM emitted — and reports `graph_id: null` with an empty
  task map when there is none. Sorting that directory by time would **not** have
  fixed it: it picks a different stranger, and the regression test rejects that
  version too.

  Two things this turned up. `latest_graph_state()` was also the only thing
  resolving a `run_workflow`'s graph in `services/api.py` — `last_graph_plan` is
  set by `plan_workflow`, not `run_workflow` — so it had been standing in for
  request-scoped resolution, correct only while the directory held exactly one
  graph; removing it alone closed the leak by breaking the feature. And the two
  copies of `_graph_metadata` in `services/api.py` and `services/server.py` had
  drifted, the server scanning the VM's own graph events and the api not, which is
  why only one of them needed a global fallback. There is one implementation now,
  in `services/graph_metadata.py`, and `latest_graph_state()` is gone.

- **#394: a workflow step body runs only when the graph runner starts it.**
  `step B after A` was the strongest ordering claim the runtime made and it held
  only for execution routed through `run_workflow`/`run_goal`: a lowered flow is
  an ordinary map, its `steps` an ordinary list, and each step's `fn` an ordinary
  callable, so `build["steps"][1]["fn"](nil)` ran `test` with `lint` never having
  run. `I-WFLOW-04` described `ready_tasks()` while the document's preamble
  defines an invariant as a guarantee made *to scripts* — so ordering was a very
  good default wearing the word "invariant". A step's compiled `FunctionInfo` now
  carries `step_owner`, set by the lowering and reachable from no surface syntax;
  the runner grants authorization for one specific entry, once `ready_tasks()` has
  already cleared the step; and the four sites that can enter a caller-supplied
  closure all consult one guard. Calling a step any other way raises
  `Workflow step 'flow.step' cannot be called directly`. The flow value's shape is
  unchanged — `keys(build)` and `build["steps"]` still read — so nothing breaks
  but the bypass. Authorization is deliberately a capability the runner grants
  rather than a property of the calling path: gating on "is a workflow context
  active" would admit a step calling a *sibling's* `fn`, and gating on
  `run_closure` vs `call_closure` would admit anything a guest can hand a closure
  to, `run_closure` having two dozen callers. `tests/test_step_entry_guard.py`
  asserts on the source as well as the behaviour, enumerating every frame built
  over a caller-supplied closure so a fifth door fails the suite.

  The mark also had to survive the **bytecode cache**, and did not at first:
  `FunctionInfo` is serialized into the cached module, `step_owner` was not among
  the fields written, and so the bypass came back on the *second* run of any
  script — refused cold, allowed warm. Found by running it twice rather than by
  reading it, the same way #521's cache write was. `step_owner` is now carried
  across all three `FunctionInfo` rebuilds outside the compiler (the cache
  round-trip and the optimizer's two address remappers), each pinned by a test.

### Tooling

- **`nodus_gate --shapes`: the recurring bug shape, reported the day it is
  introduced.** This codebase's most common defect is a correct check that only
  one of several paths goes through — twenty-one instances across v5.0.0–5.4.0,
  every one found by a human asking "what else has this shape?" *after* a bug
  report. The new phase asks first. It scans `src/` for the three species that
  leave a syntactic trace: one question implemented under the same name and
  signature in two modules, one vocabulary enumerated twice with a member
  missing, and module-scope state every participant in a process shares. The two
  species that do not — a cache acting as a sibling path, and a bound placed on
  the wrong substrate — are named in the phase docstring so their absence is
  deliberate rather than an oversight.

  `tools/shape_manifest.json` records all 43 shapes currently in the tree, each
  as `intentional` (with why they are not one question) or `tracked` (with the
  issue). The baseline is the point: what gets reported is what is **new**. It
  also records how many implementations each duplicated function had, because the
  key is name+signature and a *third* copy would otherwise match the existing
  entry silently — a hole found by probing the detector with a deliberate
  duplicate and watching it report nothing.

  Advisory, like `--consumers`: it prints and exits 0, and `--strict` fails. A
  manifest that cannot be read is always a failure, since a check must not pass
  by being unable to run.

  The first run produced **#597** (the LSP indexer never enters step bodies, so
  hover and go-to-definition are blind there — #401 fixed two walkers of three)
  and **#598** (two import resolvers, and the editor's has no entry-point lookup,
  so importing a pip-installed companion is a false "Import not found" in the
  editor while it runs fine). It also re-found the
  `GATED_BUILTINS`/`BUILTIN_CAPABILITIES` pair, which is known-intentional and
  already pinned by test — the check that the detector finds real pairs.

- **#591: the HTTP server tests stop every thread they start before removing the
  directory those threads write into.** Four teardowns ended with
  `thread.join(timeout=1.0)` whose result was discarded, and each is followed by
  a `TemporaryDirectory` removal holding the SQLite store — so on CI, a docs-only
  commit produced `sqlite3.OperationalError: no such table: workflow_runs` and
  `OSError: [Errno 39] Directory not empty`, with the identical parallel job
  green. **The join was not the culprit**, which the issue got wrong: measured,
  the server thread is reliably dead after `shutdown()` (which already blocks
  until `serve_forever` returns), while `nodus-workflow-sweep` — the default
  runner's auto-sweep daemon, started by any workflow run and bound to the
  working directory — was still running. That is the thread the cleanup raced.
  Teardown now calls `reset_default_workflow_runner()`, and also fails plainly if
  a server thread outlives its join rather than letting it become an `OSError` in
  whichever test the GC reaches next. `ignore_cleanup_errors=True` is removed from
  the one class that had it, since the threads it was hiding now stop.

- **#452 follow-up: `test_task_yield`'s stderr filter reads warning *blocks*, not
  lines.** The #452 fix dropped stderr lines containing `Warning`, which is two of
  the three lines `warnings` prints — the header and the tracemalloc hint. The
  middle one is the offending *source line*, indented and containing no such word,
  so it survived and failed the test with
  `['  self._waiters = _deque()'] != []`. Caught on a docs-only commit, red on one
  CI job and green on the identical one beside it. An indented continuation now
  goes with the header above it; unindented stderr still fails the assertion,
  including immediately after a warning block.

## [5.4.0] - 2026-08-25

### Added

- **#402: bounded channels exert backpressure — `send` on a full channel
  blocks instead of raising.** `waiting_senders` was declared and never
  wired, so a bounded channel was an assertion about queue depth rather than
  a flow-control primitive. A send in a coroutine now parks on the channel
  and a `recv` that frees a slot wakes it, mirroring the blocking-receive
  path; the deadlock detector accounts for parked senders (`… blocked on
  send() with no possible receiver`), with the recv wording unchanged;
  `close()` flushes parked senders' values into the still-drainable queue
  and wakes them. Outside a coroutine there is nothing to suspend, so a
  full-channel `send` at top level still raises — now with the same
  wrap-in-`spawn` guidance `recv` gives. Unbounded channels are unchanged.

- **#415: `try { } finally { }` needs no `catch`.** The grammar demanded a
  catch, so the canonical cleanup-without-handling form — release the lock,
  let the error propagate — had to be spelled `catch e { throw e }`, forcing
  every cleanup site onto the catch-re-throws path (the exact path #361 had
  to fix). The parser now accepts a catch-less try when `finally` is present,
  and the compiler lowers it to the rethrowing form, so the VM's handler
  machinery is untouched and the documented finally semantics apply
  unchanged. The formatter renders the form as written; a bare `try` with
  neither clause is refused (`try needs a 'catch', a 'finally', or both`).
  Seven consumers read the catch fields; each is exercised by the regression
  suite so the None-carrying node cannot break one silently.

- **#475: `allow_failure` — a step the run tolerates failing.**
  `step flaky with { allow_failure: true } { … }` declares that this step
  failing (after its retries) is not the run's failure — the last
  inexpressible piece of #475's failure semantics, after 5.1.0 made failure
  poison descendants rather than the graph and 5.2.0 gave joins
  `upstream_failed` plus `on: [...]`. History and verdict stay separate: the
  step's status still says `failed`, dependents are poisoned or satisfied
  exactly as for any failure, and only the run's verdict changes — it
  completes, `failed` stays `[]`, and the step is listed under a new
  `tolerated` result key (present only when non-empty). Retries run first;
  tolerance applies to the exhausted step. A resume of a run whose failure
  was tolerated stays completed rather than resurrecting as failed. Guide
  §4.2 documents it; the naming follows GitLab CI's `allow_failure` /
  Argo's `continueOn`.

- **#498: a persist failure names the workflow, the cell or step, and the
  remedy — and `durable: false` now actually protects a live value.** The
  serializability requirement on workflow state and step returns surfaced as
  json's own error (`Object of type Closure is not JSON serializable`),
  attributed to the `run_workflow` call site, naming neither the cell nor
  the step. The persist path now walks the snapshot for the culprit:
  `workflow 'nocp' could not be persisted: state cell 'ch' holds a Channel …
  declare with { durable: false } …`, with step returns named by step and
  records pointed at maps. Found by this change's own control test: 5.2.0's
  `durable: false` filtered only the top-level `workflow_state` — the
  metadata's copy of the state and the checkpoint snapshots still carried
  the non-durable cell, so the declaration did not actually keep a live
  value out of the persist. Every copy applies the same rule now.
  Assignment-time rejection and a wider persist format remain explicitly
  deferred, recorded on the issue with the seam they would attach to.

### Changed

- **#545: record equality is decided — structural at 6.0.0 — and a comparison
  the flip will change now warns.** `record {x: 1i} == record {x: 1i}` is
  `false` today: records compare by identity, unlike every other value. At
  6.0.0, record `==` compares `kind` and `fields` recursively with the same
  equality lists and maps already use; `datetime` keeps comparing by instant
  (zone ignored) and `duration` by length, function-valued fields compare by
  identity, and the `merge: "union"` refusal of record elements is lifted.
  Until then, two distinct records that field-by-field comparison calls equal
  print a one-time warning naming the change — joining #547 and #492 in the
  6.0.0 staging cohort. The 6.0.0 semantics ship now as
  `nodus.vm.types.structural_eq`, consulted only to detect the divergence.
  Decision record: `docs/design/v6/00-record-equality.md`.

### Fixes

- **#401: static analysis enters workflow step bodies.** Two walkers skipped
  them: the type analyzer bound a flow's name and returned, so `nodus check`
  never type-checked a step body (a call to a typed function with the wrong
  argument was caught in a function body and passed in a step, where
  orchestration logic and generated code actually live); and the workspace
  diagnostics engine (`nodus lsp`) had no case for flow declarations, so step
  bodies got no undefined-variable, unused-variable or unreachable-code
  diagnostics at all. Both walk them now — state cells resolve, and are never
  reported unused (whether a cell is read is the runtime's business, not a
  lint). Found on the way in and fixed with it: the diagnostics engine never
  bound *any* block-scoped `let`, so every function local was a false
  `Undefined variable` error in editor diagnostics. What `nodus check`
  guarantees is now written down in `nodus check --help`, including the
  deliberate half that stays open: a call to a name defined nowhere still
  passes, because a host-registered function is indistinguishable from a typo
  until a program can declare its host surface (#489).

- **#416: a closure over a top-level loop body's variable gets a diagnosis
  instead of a lie.** Upvalue capture reads an enclosing *function* frame,
  and a block at module root — a top-level `while`/`for`/`if` body — has no
  frame, so a closure written there has nothing to capture from. The compile
  error was `Undefined variable: snap` with `snap` declared on the line
  above — accurate about resolution, actively misleading about the fix. It
  now says: `Cannot capture 'snap': it is declared inside a top-level loop
  or block body, which a closure cannot capture from. Move the loop into a
  function, or declare 'snap' at module top level.` A genuine typo still
  reports `Undefined variable`. Making top-level blocks actually capturable
  (the issue's deeper option) is a compiler/VM design change recorded on the
  issue, not taken here; the working shape's per-iteration binding semantics
  are pinned by test either way.

- **#457: a reused `ModuleLoader` refuses different source under one module
  name, instead of silently returning the first snippet's bytecode.** The
  loader memoises by module id, and `"<memory>"` is the default — so a REPL,
  notebook kernel, or test helper compiling several snippets through one
  loader got the first one back for all of them, and the symptom surfaced
  somewhere else entirely. Same name + different source now raises
  (`… was already compiled from different source by this loader … Use a fresh
  ModuleLoader per snippet, or give each snippet its own module_name`); same
  name + same source still returns the memo, and load-from-path is exempt
  (the file is the source by construction). All three memo-consult sites —
  `_build_metadata`, `_parse_module`, `_load_module` — route through one
  guard, per the sibling-path rule.

- **#500: a goal whose workflow only checkpoints on success is refused at
  compile time, with the remedy.** A `goal … over …` iterates by resuming
  from the last checkpoint its workflow reached *this pass* — so the natural
  formulation, checkpoint only when the condition is met, recorded nothing on
  every other pass and halted the goal after one iteration with its budget
  untouched, while `nodus check` passed it. The compiler now refuses a
  pursuit whose workflow has only conditional checkpoints (nested in `if`/
  loops, or in a `when`-guarded step):
  `goal 'reach' cannot iterate: every checkpoint in 'tune' is conditional …
  Add a checkpoint at statement level in a step body -- a waypoint that runs
  on every pass.` The check is conservative — it refuses only the shape that
  provably cannot iterate unless satisfied on the first pass; the runtime
  error remains the backstop and now names the remedy too. The guide's §7.1
  marks the waypoint in its examples as load-bearing rather than decorative.
  Option (4) from the issue — re-running from the start when no checkpoint
  was reached — is a semantics change and was not taken.

- **#499: source persistence is disclosed, bounded, and controllable.** Every
  workflow run persists the whole module source, verbatim, into
  `.nodus/graphs/` — it is the cross-process rebuild handle, so it cannot be
  removed, but it was undocumented, unpruned by default, and mandatory. Now:
  the workflow guide and `SECURITY_POSTURE.md` §6b say it happens (including
  the deliberate asymmetry with the Floor's no-guest-writes rule);
  `nodus workflow cleanup` has a finite default retention — terminal runs
  older than 30 days (`NODUS_WORKFLOW_RETENTION_SECONDS` overrides, `=0`
  disables; nothing prunes automatically, cleanup still only runs when
  invoked); and an embedder running code it did not author can opt out with
  `NodusRuntime(persist_workflow_source=False)` — a `run_file` run then
  resumes from the file as it is on disk (the unpinned-rebuild warning names
  the opt-out rather than claiming the run "predates source recording"), and
  a `run_source` run is not resumable across processes. Found while staging
  the default: cleanup's age test compared wall-clock now against the
  process-monotonic `updated_at`, so any configured retention removed every
  terminal run regardless of age — latent while retention was opt-in and
  unset; age now comes from the state file's mtime.

- **#501: a nested run knows where it came from, and cleanup follows the
  link.** A `run_graph`/`run_workflow` call inside a workflow step creates a
  separate run whose record was an orphan: metadata `{}`, no reference in
  either direction, and one more per resume (a resume re-enters the step, so
  the nested call runs again — #486's rule, now documented for this case in
  the guide's checkpoint section). The child's metadata now records
  `parent_graph_id`/`parent_step`/`parent_task_id`/`parent_workflow` from its
  first persist; the parent accumulates `child_graph_ids`, carried across
  resume rebuilds so the list is cumulative; `workflow list` surfaces the
  parent link; and `workflow cleanup` cascades — a child whose parent was
  removed goes with it, and its children in turn. Making the nested run part
  of the parent graph remains #480, a design question this does not answer.

- **#476: the two halves of a run now share a lifecycle.** A durable run is
  split across `.nodus/graphs/` (graph state + checkpoint) and the workflow
  store (run record), and nothing kept them in step: `nodus workflow cleanup`
  removed graph state and left records accumulating forever; the store's
  opt-in `max_terminal_runs` cap deleted records and left graph state
  orphaned; and a resume whose record was gone — while the state sat on disk —
  reported `not found`. Now cleanup removes the run record with the graph
  state (unless the record says the run is still live and `--force` was not
  given), reporting them as `run_records_removed`; the record cap prunes the
  graph state and checkpoint with the record; stores gained `delete_run`
  (concrete no-op default on the `WorkflowStore` ABC, so host store
  implementations keep working); and a missing-record resume says the real
  thing — the two halves were cleaned independently — with
  `category: "run_record_missing"`, the same honesty shape as #399 and #425
  on this path. CLAUDE.md's "`rm -rf .nodus/workflow_framework/runs` is safe"
  note is corrected: it makes any live waiting run unresumable.

- **#400: `nodus graph` no longer executes the file it is asked to inspect.**
  An inspection command ran its target: `nodus graph <file>` executed the whole
  module — side effects included — to obtain the plan, and `nodus graph show`
  (5.2.0) inherited the path while exiting 0, so the execution was invisible
  behind a successful diagram. Both now plan by loading **only the flow
  declarations**: the module is parsed in full (a syntax error anywhere still
  fails), then every other top-level statement — imports included — is dropped
  before compilation, and the plan is produced by the same
  `plan_workflow`/`plan_goal` machinery the executing path uses, so the two
  projections cannot disagree about what the graph is. A filtered load never
  touches the bytecode cache (the #521 shape, guarded at the shared
  `_source_is_the_file` question). The old behaviour is `--execute`, needed
  only for graphs constructed at runtime (`task()`/`run_graph`, or a
  dynamically chosen flow) — a file with no flow declaration is refused with
  a message naming the flag rather than silently executed.

- **#558: `nodus graph show` plans a workflow whose `plan_workflow` call lives
  inside `main()`.** Fixed by the #400 change: the declaration alone is enough,
  so where (or whether) the file calls `plan_workflow` no longer matters to
  inspection.

- **#482: a checkpoint resume of a genuinely waiting run is refused with the
  real reason, instead of silently re-waiting.**
  `resume_workflow(id, "checkpoint")` on a waiting run re-entered the waiting
  step, which hit its `workflow_wait` again — the run went straight back to
  `waiting` behind a healthy-looking result (`ok` not false, nothing in
  `failed`, a duplicate checkpoint entry as the only trace). With a payload
  alongside the checkpoint it was worse: the rollback re-armed the wait and
  the payload was silently discarded. Both combinations now return
  `{ok: false, category: "waiting_run_checkpoint_resume"}` naming the event
  the run is waiting on and the call that advances it
  (`resume_workflow(graph_id, {...})`), before any re-execution — the waiting
  step's pre-wait effects no longer fire on the refused attempt. "Genuinely
  waiting" means the persisted graph state agrees: a record marked waiting
  administratively over a graph that ran past the wait (a stale registration)
  still resumes and clears the mark.

- **#486: resuming from a mid-step checkpoint no longer double-counts folded
  state, and the re-entry rule is documented.** A resume re-enters the step
  that recorded the checkpoint from the top — that is the decided semantics,
  now stated loudly in the guide (effects before the checkpoint repeat; split
  the step to skip completed work). What was wrong: the checkpoint snapshot
  deliberately includes the step's pending fold contributions (5.2.0, so the
  value is observable at the checkpoint), and that same snapshot was also the
  rollback base — so a resume restored the contribution and then re-made it.
  `counter += 1i; checkpoint "mid"` gave 1, 2, 3 across resumes, silently. The
  engine checkpoint now records `resume_state` — the committed base without
  the checkpointing step's pending fold — and rollback prefers it, so
  re-entry re-derives the same total every time. Plain-cell semantics are
  unchanged, and checkpoints persisted before this fix keep the old behaviour
  rather than becoming unresumable. Positional resume (re-entering *at* the
  checkpoint) remains undone by decision, not oversight — recorded on the
  issue.

- **#470: a resume refuses a run whose step structure has changed, instead of
  manufacturing a false diagnosis.** Nothing recorded what a run's graph looked
  like, so a rebuild whose shape had drifted — a pre-#469 run rebuilt from an
  edited file, a hand-edited state file, a lowering change across versions —
  applied the persisted per-task state to the wrong shape and failed with
  `Dependency cycle detected: z -> z` in source that has no cycle. Every run now
  records `workflow_topology` (step names + `after` edges) in its metadata, and
  `_rebuild_workflow_graph` compares on rebuild, refusing a mismatch with the
  real cause: `planned against a different version of workflow 'w': its step
  structure has changed since the run started (steps added: z)`. Structure only,
  deliberately — a body or `when` edit does not refuse. Legacy runs without the
  recorded topology are checked on step names alone (from `step_to_task`); an
  edge-only rewire on such a run remains undetectable, a stated limit.

- **#497: both halves of the resume-source fork now say which rule is in
  effect.** The pinned half (all runs since #469) already warned on drift; the
  warning now also lands where a program can react to it — `source_drift: true`
  on the resume result map, present only when the file has changed. The legacy
  half — a pre-#469 run rebuilt from the file *as it is now* — was completely
  silent about being the opposite rule; it now warns on stderr
  (`resume: run '<id>' predates source recording …`) and emits a
  `workflow_rebuild_unpinned` event. With #469's pinning, this closes #497: one
  rule for every new run, and both surviving paths announce themselves.

### Tooling

- **#334: the three recurring timing flakes are hardened against load.** The
  resume-API test (`KeyError: 'steps'`, the suite's most frequent flake —
  ~50% of coverage jobs across consecutive docs-only PRs) now polls for a
  settled result instead of reading once; retrying converges in both race
  modes, since resuming a completed run returns its full result. The
  `*_overlaps` ratio tests re-measure their serial baseline **under the same
  load** when the first comparison fails — the baseline was taken once at
  class setup, and a load spike between then and the test skewed the ratio
  (a genuinely serial fan-out still fails against any baseline). The
  ieee754 subprocess tests get 60s timeouts — 10s was 5× headroom against an
  idle box, not the instrumented, loaded one, which is what the headroom
  rule means. Fittingly, the overlap flake fired one last time on the #415
  PR's coverage job while this fix sat in the working tree.

- **#452: `test_task_yield` no longer fails on other tests' garbage.** Two
  tests in `test_task_graph.py` asserted `err.strip() == ""` — but stderr is
  process-wide, so a `ResourceWarning` emitted by the collector for file
  objects an *earlier* test leaked failed them at random (same commit green
  one CI run, red the next). They now assert on their own stderr with
  interpreter warning chatter filtered; anything else still fails. The
  issue's second half — the genuinely unclosed handles the warnings point at
  — is not hunted here and is recorded on the issue.

- **#562: the closed-issues gate binds a marker only when it is a comment.**
  The scanner matched `# closes: #N`-shaped text anywhere in a file and took
  the first occurrence, so a docstring *mentioning* the marker convention
  bound the issue to whatever `def` followed the docstring — `-k` then
  selected nothing and a passing regression suite reported as failed (the
  second false verdict from whole-file matching; the first was the `setUp`
  binding). The scan is tokenizer-backed now: only COMMENT tokens carry
  markers, prose and string literals are inert, and a file that does not
  tokenize falls back to the old behaviour rather than silently finding no
  test. The gate's own suite gains the docstring-trap case this shipped
  with.

## [5.3.0] - 2026-08-25


### Added

- **#471 / #537: a conditional edge now says so, in the plan and the diagram.**
  Two different things make a workflow edge conditional, and the plan object
  recorded neither — so `plan_workflow` rendered a guarded edge identically to an
  unguarded one, and `nodus graph show` drew both as plain arrows.

  ```
  edges:             [["build", "notify"], ["build", "verify"], ["build", "done"]]
  conditional_edges: [["build", "verify"]]          # step ... when reached("flaky")
  edge_conditions:   {"build->notify": ["failed"]}  # with { on: ["failed"] }
  ```

  Both are **additional keys**; `edges` and `levels` are untouched, so anything
  reading a plan keeps working. `nodus graph show` labels a filtered edge
  (`build -->|failed| notify`) and dashes a guarded one (`build -.-> verify`).
  A plain solid arrow means the default, `on: ["completed"]` — labelling every
  edge `completed` would be noise, so absence carries meaning, which
  `TASK_GRAPHS.md` now states rather than leaving to inference.

  `levels` is documented as a **superset** once guards exist: it is the
  topological partition, not a prediction of what will run.

- **#467: `writable_paths` — read-only context, editable files.** `allowed_paths`
  was a single flat list: a path was reachable for everything or for nothing.
  `_ensure_path_allowed(path, op_name)` took the operation's name and used it
  **only to phrase the error message**, never to decide, so "this tree is
  readable context, that subtree is editable" — the two-tier model every coding
  agent wants — could not be expressed.

  ```python
  NodusRuntime(
      allowed_paths=["/repo"],          # readable
      writable_paths=["/repo/src"],     # subset that may be written
  )
  ```

  CLI: `nodus run app.nd --allow-paths /repo --writable-paths /repo/src`.

  **Additive.** `writable_paths=None` means "everything readable", which is every
  release through 5.2.0, so a runtime that never asks for the split is unchanged.
  `[]` is a statement rather than an omission: it refuses every write and leaves
  reads alone. Both checks always run, so a writable path grants nothing
  `allowed_paths` does not already allow — and declaring one outside the read
  jail is refused at construction instead of silently ignored.

  **No environment variable, deliberately.** `NODUS_ALLOWED_PATHS` widens a
  *default* jail when the caller passed nothing; there is nothing to widen here,
  so a variable could only narrow, and write confinement that moves with ambient
  state produces a program that works locally and is refused in production with
  no difference in the code.

  **It does not cover subprocess children.** A subprocess's `cwd` and its
  stdout/stderr redirect targets are path-checked and obey both lists, but what
  the spawned program itself writes is the OS's business. With
  `allow_subprocess=True`, `writable_paths` scopes the runtime's writes only.

### Changed

- **#492: an unhonoured `worker:` declaration warns instead of running
  silently.** `step … with { worker: "hardened-sandbox" }` names *where* a step
  runs. With a dispatcher registered, an unsatisfiable name already failed —
  `WorkerPool.submit` waits for a worker advertising the capability and raises
  `No workers registered with capability: X`. Without one, the step fell through
  to in-process execution and reported success, so `worker: "gpu"` and
  `worker: "hardened-sandbox"` behaved exactly like no declaration at all.

  The check existed; only one of the two paths reached it. Since the thing being
  declared is an isolation intent, running it silently in-process is the worst
  available answer. It now warns, names both remedies, and announces the flag
  day: **this becomes an error in 6.0.0**, staged the way the concurrent-write
  conflict was in 5.2.0.

- **#492: `NodusRuntime(worker_dispatcher=…)`.** `vm.worker_dispatcher` was set
  only by `services/server.py`, so an embedded runtime could not honour a worker
  declaration at all — the declaration had no reachable meaning outside a
  server. Any object with a compatible `.submit` works.

- **#490: `nodus.toml` refuses what it does not read, and `entry` is real.** The
  manifest loader accepted any table and any key, read four of them, and threw
  the rest away without a word. Two of the three real `nodus.toml` files on
  record were, in consequence, entirely fictional — declaring `[project]`,
  `[runtime]`, `[workflows]` and an `entry`, none of which Nodus had ever read.

  A manifest is the worst place for a declaration to be accepted-and-ignored,
  because unlike a bad flag it produces no error and unlike bad code it produces
  no wrong answer. It just looks like configuration that worked. Loading one now
  fails with the unknown tables and keys named, plus a suggestion when one is
  close: `[project]` is told about `[package]`.

  The other half is what those manifests were reaching for. `entry` in
  `[package]` now selects the file `nodus run` starts from, relative to the
  project root; omitting it keeps the `src/main.nd` convention. It must resolve
  inside the project root — a manifest is data, and an `entry` pointing out of
  its own tree is refused at both the API and the CLI.

  Also fixed in passing: `nodus add` and `nodus remove` rewrite the manifest from
  parsed values, and did not carry `registry_url` across — so adding a dependency
  silently deleted a project's registry URL. Both keys now survive the rewrite.

### Fixes

- **#471: a step guard error blamed goal `until`.** `step b after a when (a < 5i)`
  was refused with ``goal `until` supports reached("label")…`` — naming a
  construct that appears nowhere in the program. Both clauses share a grammar and
  a parser, and the error named the parser's original caller. Each clause now
  names itself, and the step case points at the idiom that does work: record a
  checkpoint conditionally in the upstream step and guard on it.

  The guard grammar is **unchanged**. `reached()` takes a string literal so the
  complete set of checkpoints is known at parse time, which is what lets
  `nodus check` reject a typo'd label instead of leaving a step that silently
  never runs.

- **#478: `SyscallSpec.capability` is enforced.** Every syscall declared one,
  `syscall_list()` published it to any host that asked, and `call_syscall` never
  read the field — a policy denying `memory.write` watched
  `sys.v1.memory.put` succeed while the registry advertised
  `"capability": "memory.write"` on the way past.

  A syscall now reaches the policy **twice**, and the two are different intents:
  the `syscall` builtin carries the blanket `syscall` capability (#473), and the
  spec's own field is consulted before dispatch. So "no syscalls at all" and "no
  memory writes, whether spelled `memory_put` or `sys.v1.memory.put`" are both
  expressible. A refusal raises with `kind == "sandbox"` rather than returning an
  error envelope, which would make a capability refusal indistinguishable from a
  handler that failed.

  `register_syscall` also refuses a spec whose capability is missing or outside
  `ALL_CAPABILITIES`. Accepting a name the policy layer cannot express, then
  skipping it at dispatch, would be the same defect one layer along.

- **#473: a `CapabilityPolicy` that denied everything denied nothing.** The
  policy was consulted only for the four sandbox capability groups. Every effect
  surface that was not filesystem/subprocess/network/env — `tool_call`,
  `syscall`, `agent_call`, and the whole memory store — was invisible to it, and
  the vocabulary was closed, so there was no name to add them under:
  `DenyList("tool.invoke")` raised `unknown capability`.

  The chokepoint was never the problem. `VM.call_builtin` consulted
  `BUILTIN_CAPABILITIES` faithfully; the map never grew past the flags. Five
  capabilities are added — `tool.invoke`, `syscall`, `agent.call`, `memory.read`,
  `memory.write` — and the builtins behind them now reach the policy, with their
  arguments, so a policy can decide on *which* tool rather than merely whether.

  `action tool "x"` and `action agent "a"` are governed too. They lower to
  `__action_tool` / `__action_agent` without passing through `tool_call`, and a
  host can shadow neither, so gating one spelling would have left the DSL form
  uninterposable.

  **Additive**: a runtime with no policy behaves exactly as before.
  `ALL_CAPABILITIES` grows from five names to ten — it is closed, not fixed, so
  validate against the frozenset rather than a copy.

- **`FS_READ` was declared and attached to nothing.** It sat in
  `ALL_CAPABILITIES` from 5.0.0 with no builtin carrying it, so reads were
  invisible to a policy for the same reason the surfaces above were.
  `read_file`, `list_dir`, `path_exists` and the `hash_*_file` family now carry
  it. This is half of what issue #467 reports; the other half — a declarative
  read-only/writable split for `allowed_paths` — is unchanged, and that issue
  stays open for it.

- **Every builtin is now classified.** `NO_AUTHORITY_BUILTINS` names the 227
  builtins that carry no authority, grouped by why, and a test requires
  `BUILTIN_CAPABILITIES | NO_AUTHORITY_BUILTIN_NAMES == BUILTIN_NAMES`. A new
  builtin fails the suite until somebody decides which side it is on, so "is
  this governed?" stops depending on whether anyone remembered.

### Docs

- **The embedder runbook said the `allow_*` switches "default to permissive".**
  They have denied by default since 5.0.0. The paragraph was backwards for three
  releases in the document an embedder reads to configure confinement.

## [5.2.0] - 2026-08-23

### Fixes

- **#532: `nodus publish` silently ignored `--project-root` and published the
  CWD.** The flag has always been documented in `publish --help`, but was absent
  from the command's parse set, so `_parse_flags` swallowed both it and its value
  as positionals and the branch fell back to `os.getcwd()`. No error, no warning
  — the wrong directory went to the registry. Found while inventorying flags for
  the command table, which is the fix that generalises: a test now cross-checks
  every flag each command's help documents against the flags it actually parses.

- **#533: `nodus graph --help` and `nodus workflow --help` printed the generic
  stub.** Both commands carry a full hand-written help block — nine subcommands
  and ten examples in `workflow`'s case — inside their dispatch branch, where the
  central #353 `--help` guard made it unreachable. Same shape as the bug #353
  fixed, one layer along: centralising the guard without moving what it shadowed.
  Both blocks now live beside the command table, where the guard reads them, and
  the dead branches are gone. Bare `nodus workflow` still prints its help.

### Added

- **#485: folded state cells — `merge: "sum"`, `"append"` and `"union"`.** Two
  concurrent branches that read a cell, do something slow, and write it back
  silently lost one of the writes. Declaring a fold closes it:

  ```nd
  state counter = 0i with { merge: "sum" }
  state log = [] with { merge: "append" }
  ```

  **`+=` contributes; `=` is refused.** `counter += 1i` means *contribute one*,
  folded at the join — it never reads the cell, which is what removes the
  read-modify-write window. `counter = 5i` on a folded cell is a **compile-time
  error** caught by `nodus check`: a plain assignment names a *final* value, and
  two final values cannot be combined without double-counting. There is no
  reading of `counter = seen + 1i` that means "add one", so the form is rejected
  rather than reinterpreted. This is Option A from the issue, decided there.

  The policy is read from the `with { ... }` literal at compile time, so
  `merge:` must be a literal policy name — it decides what a write *means*, and
  that cannot be computed. A wrong contribution (a list to `sum`, a number to
  `append`) fails the step naming both.

  Two behaviours worth knowing. A contribution is not visible to a plain read of
  the same cell in the same step — it lands at the join, not at the statement. And
  a `checkpoint` *does* see pending contributions, because a resume from that
  label would otherwise contribute a second time.

  Folded cells no longer draw the concurrent-writer warning: two branches
  contributing is the feature, not the defect, since neither read the cell.

  **`union` also ships**, and its blocker turned out to be answerable from what
  the language already does. Sameness is ordinary Nodus `==`, which is structural
  for numbers, strings, booleans, `nil`, lists and maps at any depth. It is *not*
  structural for records -- `Record.__eq__` is `self is other`, with `datetime`
  and `duration` carved out -- so a list of records would deduplicate nothing and
  `union` would silently behave as `append`. Record elements are therefore
  **refused** in a union contribution, with a message naming the workaround and
  the underlying question (#545, filed).

  Deduplication keeps the first occurrence, which is what makes it
  batching-invariant: `dedup(dedup(a) + b) == dedup(a + b)`. It borrows
  `VM._nodus_eq` rather than Python `==` or a `set`, because Nodus equality
  coerces int/float and refuses bool/int (`1 == 1.0` is true, `true == 1` is
  false), and lists and maps are not hashable. Re-implementing those rules beside
  the originals is the duplication that drifts.

  The fold set stays closed rather than taking a user function: `sum` and
  `append` are batching-invariant (`fold(fold(s, xs), ys) == fold(s, xs + ys)`),
  so a resume that regroups writes produces the same total by construction rather
  than by the author's contract. Pinned by test.

  **Not everything on #485.** An undeclared cell still defaults to last-write-wins
  with a warning; making `once` the default is step 4 and would break workflows
  whose branches legitimately agree. The barrier policy is untouched.


- **`nodus graph show <file> [--format mermaid|dot] [--output FILE]`.** Renders a
  planned task graph as a diagram instead of JSON. The plan object was already
  there — `plan_workflow` / `plan_graph` have always returned nodes, edges and
  parallel levels — so this adds no information, only a projection other tools
  read. DOT emits each parallel level as a `rank=same` group, so the steps the
  scheduler actually runs concurrently line up visually.

  **Known issue — #537.** An edge means "B depends on A". A step's `on: [...]`
  dependency-outcome filter is deliberately **not** drawn, because the plan does
  not record it and an unconditional arrow for a conditional edge is a lie the
  diagram tells convincingly. A step that runs *only when its dependency failed*
  therefore renders identically to one that runs on success. The fix is to carry
  the condition in the plan, not to guess at it in the renderer.

- **`nodus doctor`** — reports what the environment actually resolves to: the
  package path and version that `import nodus` loads, whether that is a checkout
  or an installed distribution, whether the two disagree, the interpreter,
  optional extras that change runtime behaviour by their presence (`nodus-retry`),
  the project manifest, and the accumulated workflow-store size (#380). `--json`
  for scripting; exits 1 only on an error-level finding.

  The version-gap check is the point: a `.venv` install shadowing a newer `src/`
  checkout produces behaviour that contradicts the code you are reading, and
  nothing in normal output says which tree ran. Note it derives the package
  directory from a *submodule*, not `nodus.__file__` — the repo-root `nodus.py`
  shim occupies that name when the CWD is the checkout root.

  **Known issue — #535.** It cannot diagnose that gap until it ships: against an
  installed package the command does not exist, which is the environment the gap
  appears in. `CLAUDE.md`'s existing `--version` re-check advice stays correct
  until a release carries `doctor`.

  **Doctor never writes.** It does not create `.nodus/`, touch the cache, or
  migrate anything; a diagnostic that mutates what it diagnoses is worse than
  none, and this is the command reached for when an install is already broken.
  Pinned by `test_doctor_does_not_write`.

- **`nodus completion <bash|zsh|fish|powershell>`** — completion scripts
  generated from the command table, so a command or flag added there is
  completable without updating a second list. Hidden legacy aliases are not
  offered. The script is written as **bytes**: a text-mode stdout on Windows
  rewrites `\n` as `\r\n`, and bash rejects the result outright with
  `syntax error near unexpected token $'{\r'`.

  **Known issue — #536.** Verification is uneven: `bash` is syntax-checked and
  functionally exercised in the suite; `powershell` was verified by hand and has
  no test; `zsh` and `fish` get structural and quoting assertions only, because
  neither shell is installed on the development or CI machines. Since the only
  execution class is guarded on `bash`, a machine without it verifies nothing
  executable.

### Changed

- **#485 step 4: the concurrent-write warning fires only when an update was
  actually lost.** It used to warn whenever two unordered steps wrote one cell,
  which included the case where both wrote the same constant and nothing was
  lost. That noise is what teaches people to ignore the warning that matters.

  It now warns when either:

  - the writers **disagreed** — different values, one was overwritten; or
  - a writer **read the cell before writing it** — a read-modify-write, which
    loses an update whatever the values are.

  **The second signal is the load-bearing one, and value comparison alone is
  wrong without it.** Two branches doing `counter = seen + 1i` from the same base
  both write `1`: the values agree *precisely because* an update was lost. That
  is this issue's own reproduction, and it falsified the first implementation —
  the read-before-write check exists because of it.

  Not breaking: nothing that ran now fails, and a class of false positives
  stopped. **The remaining warning becomes an error in 6.0.0**, which the message
  says, along with both fixes — a fold to combine the writes, or `merge: "any"`
  for deliberate last-write-wins. Recorded in
  `docs/governance/COMPATIBILITY.md`.

  **The default stays `any`, deliberately.** #485 proposed defaulting to `once`.
  `workflow`/`step` are *Mostly Stable*, where "breakage is avoided but not
  guaranteed" — turning working programs into errors is not the minor refinement
  that tier permits, and it needs the major cycle plus the deprecation signal
  this change starts. Making the warning precise first is also what makes the
  error defensible later: it can now only fire on a genuine lost update.


- **Workflow state writes are recorded per step.** Key, value
  and order, closed when the step ends — step 2 of the write-merge work in #485,
  which this does **not** close. Nothing acts on the record yet — the
  write still lands exactly when it always did — and step 3 turns it into a fold
  at the join, under the emission model decided on the issue (`+=` contributes,
  `=` is refused for a folded cell).

  `TrackedState` already knew *who* wrote each key, which is enough to warn and
  not enough to merge; it now also keeps *what* they wrote, for the duration of
  the step, via `begin_step` / `end_step`. The close is called from all four
  paths a task can stop running by — success on either execution path, failure,
  and suspension at a `workflow_wait` — and each is covered separately, because a
  record left open would make a step's writes invisible to the merge that will
  read it: the same silent loss #485 is about, reintroduced by its own fix.

  **This deviates from the plan on the issue, on evidence.** The scoping comment
  proposed a per-task overlay that steps read *through* — a snapshot at step
  start, applied at step end. Implemented, it turned a correct program into a
  wrong one:

  ```
  step a { counter = counter + 1i }
  step b { counter = counter + 1i }
  ```

  With no suspension the cooperative scheduler runs these one after the other, so
  `b` reads what `a` wrote and the answer is 2. Snapshotting at step start makes
  both read 0 and the answer 1 — introducing the very lost update the issue is
  about, in the one case that did not have it. And the fold does not need it:
  under `merge: "sum"`, `counter += 1i` contributes `1` from the expression, not
  from reading the cell. Read isolation is a separable property with its own
  cost and is left to its own decision rather than smuggled in here.

  Same reason a checkpoint still sees the running step's own writes:
  `x = x + 1i; checkpoint "l"` has always recorded the incremented value, and a
  resume from that label must not run the increment twice.

  **#485 is not fixed by this** and the tests say so — the lost update is still
  lost and still warned. This is the machinery the fix needs.


- **The CLI command surface is data.** `main()` declared each command's flags
  inline in its own dispatch branch — 47 `_parse_flags(...)` call sites, ten of
  them repeating `{"--path", "--project-root"}` as a bare literal at the call.
  That is the recurring shape this codebase keeps hitting: a correct declaration
  on one path, with siblings free to drift. It had already drifted (#532).

  The set is named once now, in `src/nodus/cli/commands.py`, and the global help,
  per-command help, flag parsing, the `--help` guard registry, and shell
  completion are all projections of it. `cli.py` drops from 2,486 to 1,991
  lines and no longer imports `re` — the old `_command_summary()` recovered each
  command's usage by regex-scraping the rendered help text, which the table makes
  unnecessary.

  Byte-compared against the previous output: every pre-existing help row is
  unchanged. `tests/test_cli_command_table.py` asserts on the **source** of
  `cli.py` that no branch re-declares a flag literal, because a behaviour-only
  test passes on whichever branch is already correct.

### Performance

- **#522: the VM no longer retains an event per function call and return.**
  The event bus appended to an unbounded list whether or not anything would read
  it, and the VM emits one event per call, per return, and per 100 instructions.
  On a compiler workload (`examples/expr_compiler.nd`, 400 expressions, 1.96M
  instructions) that was **206,382 retained objects for a run that printed one
  line** — 58% of everything it allocated — with no consumer on the default path.

  Measured on the same machine, before and after:

  | | before | after |
  |---|---:|---:|
  | throughput | 227,401 instr/sec | **477,417 instr/sec** (2.10×) |
  | events retained | 206,382 | **0** |
  | live memory | 80.2 MB | **0.4 MB** |
  | attributed to `runtime_events.py` | 46.4 MB (58%) | **0.0 MB** |

  Two changes. Retention is a bounded `deque` — 50,000 by default,
  `NODUS_EVENT_HISTORY` to change it, `0` to keep none while still feeding sinks.
  And `vm_call` / `vm_return` / `vm_instruction_batch` are emitted only when
  something can observe them: a sink is attached — which is what
  `--trace-events`, `--trace-json`, `--trace-file` and the DAP debugger do — or a
  host asks via `record_vm_events` / `NODUS_TRACE_VM_EVENTS=1`.

  The speedup exceeds the 1.5× the issue predicted because the guard sits
  *before* the `RuntimeEvent` is constructed. `emit_event` used to build the
  object and its `data` dict and then decide whether to keep it, so a suppressed
  event still cost an allocation. A test pins that it is never built.

  **The aggregate is unaffected.** `function_calls`, `returns` and
  `instructions_executed` are counters maintained independently of the bus and
  are what `get_execution_stats()` reports; suppression changes what is kept,
  never what happened. A test compares a default run against one recording
  everything and asserts the counts are identical.

  `RuntimeEventBus.wants(event_type)` is the single place the decision lives. The
  VM had three emit sites each deciding for itself — the shape `CLAUDE.md` warns
  about — and they consult it now rather than re-implementing it, pinned by a
  source assertion because a behaviour-only test passes as long as one of the
  three is right.

  Note for anyone reading `runtime_events()` from a Nodus program or the HTTP
  endpoint: the VM bookkeeping types are absent by default, and the window is
  bounded. Neither was ever in the documented event contract —
  `RUNTIME_EVENTS.md` does not list them among the types it describes.

### Tooling

- **#528: the dependent-suite gate now says what to look at when it goes red.**
  `tools/check_dependent_suites.py` is Gate 10 step 0 — the check between a build
  and PyPI, added because 5.0.3 shipped a broken `nodus-sdk`. It printed a count
  and "do not publish", and nothing else. That instruction could neither be acted
  on nor dismissed without leaving the tool and re-running the companion by hand:
  the manual step the gate was written to replace, and a path whose natural end is
  re-running until green.

  A red run now prints each failing pytest node id (`FAILED` and `ERROR` alike,
  so a collection failure names the file that would not import), marks which of
  them match a recorded flake in `tools/dependent_flakes.json`, and writes full
  output *including tracebacks* to `.dependent-suites/<companion>.log`. Triage no
  longer requires a re-run. The suites now run with `--tb=short -rfE` rather than
  `--tb=no`; `-r` is passed explicitly because a companion's own pytest config
  could otherwise decide whether the summary this parses exists at all.

  **A recorded flake never turns a red run green.** It changes the exit code from
  1 to 3 and changes the advice — *re-run these serially before deciding* — and
  that is all. Exit 3 is not a pass. Letting a listed test through would rebuild
  "re-run until green" one level up, which is the failure this process exists to
  prevent, so the manifest is a triage aid and is documented as one. Every entry
  requires a stated reason, checked by test.

  New exit code **3**; 0, 1 and 2 keep their meanings. `--retry-failed` re-runs
  only the failed tests and reports both results — opt-in rather than automatic,
  and unable to change the verdict.

- **`nodus_gate --versions` — prose that quotes the version files is now checked.**
  A version string in prose has gone stale in three consecutive release cycles.
  CLAUDE.md named the failure in writing — *"No gate checks version strings"* —
  and it kept happening, because the response each time was a longer list of
  places to check by hand.

  Three checks. `version.py` vs `pyproject.toml`. Every claim declared in
  `tools/version_claims.json` against what it must equal. And a **discovery
  sweep** for claim-shaped lines nobody registered, so a new one cannot hide.
  The first two fail the gate; the sweep is advisory.

  Claims are declared rather than grepped because *"X is current"* goes stale and
  *"as of X"* does not — README's release history names 5.0.4, 5.0.3, 5.0.1 and
  5.0.0 and is correct forever — and no pattern over version tokens can tell the
  two apart. The sweep exists so declaring them stays honest: on its first run it
  found a **fourth** nodus-lang claim in `ECOSYSTEM_READINESS_ASSESSMENT.md`,
  where CLAUDE.md's hand-maintained list said three.

  It reads `version.py` as **text and never imports `nodus`**. Importing would
  resolve through `sys.path`, so an installed `nodus-lang` shadowing the checkout
  would have the gate compare docs against the wrong version — silently, and in
  the direction that hides a real mismatch. Pinned by an AST-level test.

  Included in `--all`. **Re-run it after the version bump**: at Gate 1 it compares
  prose against the version it already matches and passes by construction, which
  is the same shape as the `--closed-issues` trap already documented.

- **First catch, fixed in the same PR.**
  `ECOSYSTEM_READINESS_ASSESSMENT.md` pointed at `docs/evals/v4.0.2/CREATOR_VALIDATION.md`
  as "most recent Gate 10 results" — six releases behind, with
  `docs/evals/v5.1.0/` present. Nothing updated it when a release wrote a new
  record. That claim type (`latest_eval_version`) is now checked against the
  newest `docs/evals/vX.Y.Z` directory, ordered numerically so v5.1.0 sorts above
  v5.0.10.

## [5.1.0] - 2026-08-20

### Fixes

- **#521: `run_source` runs the source it is given.** If `filename` named an
  existing file, `run_source` read that file and **discarded the `source`
  argument**, returning `ok=True` with the other program's output. Which program
  ran depended on the process CWD and on what happened to be sitting in it.

  `filename` is a label — it is what error messages interpolate, and
  `embedding-nodus.md` says so under a heading called "Passing a filename",
  illustrated with `filename="myscript.nd"`. So a host following the guide was
  told the safe thing and given the unsafe example. The docstring's *"the module
  loader reads it directly (allowing relative imports)"* was the only warning, and
  it does not read as *your source is ignored*.

  A real path still resolves relative imports against its directory — that is the
  half worth keeping, and deleting the branch outright would have broken it. It no
  longer selects the program. `run_file` is unchanged and is still how you run a
  file; it already read the file itself and forwarded the text, so the loader's
  re-read was thrown away and its docstring's claim to be
  `run_source(open(path).read(), filename=path)` was true only by accident.

  **Two paths, as usual.** The bytecode cache is keyed on path + mtime, which
  identifies *the file* — so a warm entry for `x.nd` would still be served to a
  caller passing different source under that name, and fixing only the branch in
  `embedding.py` leaves that live. Both cache-consult sites now route through one
  predicate that asks whether the source *is* the file's content. Deciding by
  comparison rather than by a flag each call site sets is deliberate: the CLI
  legitimately passes a file's own text and must keep its cache, so the question
  is not "did the caller supply source" but "is it the same source".

  Guarding the read alone was not enough either — that was caught mid-fix by a
  probe rather than by reasoning. Compiling a differing source under the file's
  name **wrote** an entry under the file's key, so the next `run_file` got the
  caller's program. The write is gated on the same predicate.

  Present since **v0.4.0** (`c245d31`), so every published release. No first-party
  companion passes `filename=` to `run_source`, so nothing we ship was affected.

- **#518: `counter += 1i` now reaches workflow state.** Compound assignment to a
  `state` cell inside a step body did not lower at all. A `state` cell is not a
  real variable — the lowering rewrites reads and writes of it into operations on
  a hidden map — and the rewriter knew `=`, `x[i] =` and `x.f =` but had never
  heard of `+=`. So the write passed through untouched, resolved as a local that
  was never declared, and read `nil`:

  ```
  Type error at w.nd:3:25: Cannot add nil and int
  ```

  Accumulating into workflow state is the archetypal use of `+=`, and the error
  blamed arithmetic rather than the rewrite that never happened. `nodus check`
  reported `OK`. The workaround — write `counter = counter + 1i` — worked, which
  is what kept this quiet: the two forms are documented as equivalent and are,
  everywhere except here.

  Three of four again, so the fix is the #487 fix: **`ASSIGNMENT_FORMS` in
  `ast_nodes`** names the set. These genuinely need different rewrites, so unlike
  `FLOW_DECLARATIONS` there is no shared answer to give — what the tuple buys is
  the failure. `tests/test_state_compound_assign.py` demands a worked sample per
  member, so a fifth form fails the suite until somebody has decided what it means
  for a `state` cell.

  The source assertion walks *identifiers*, not `Var` nodes, deliberately:
  `CompoundAssign` carries its target as a bare `str` with no `Var` anywhere, so a
  Var-only walk would have passed on the unfixed tree. Verified against it — only
  the `CompoundAssign` subtest goes red, so the walk discriminates rather than
  failing everything.

- **#516: the SQLite workflow store closes its cursors instead of relying on
  refcounting.** `conn.execute(...)` returns a cursor; left unreferenced, CPython
  frees it at once and finalises the statement. A runtime without refcounting
  keeps it alive until the next GC, so the statement is still open at commit:

  ```
  sqlite3.OperationalError: cannot commit transaction - SQL statements in progress
  ```

  The store was depending on *when CPython happens to free an object* for
  correctness — a latent defect there too, not a foreign-runtime quirk. All twelve
  query sites now route through three helpers that own the cursor from creation,
  so it closes on every exit including a statement that raises. A test asserts no
  call site bypasses them, because on CPython an unclosed cursor is invisible.

  Found by running the suite on PyPy while measuring throughput for #173: nine
  tests failed there, every one from this single cause. They pass now.

- **#487: `goal … over …` can now be used from inside a function.** `workflow` and
  the plain `goal` form both bound the name they declare; the stopping-condition
  form did not, so calling it from inside a function — the normal place to call it
  from — failed with `Undefined variable`, and the v5 flagship construct only
  worked at top level.

  The compiler's own hoisting pass had the case all along. **Three other places
  that register a declared name did not** — `runtime/module_loader.py`,
  `tooling/loader.py` and `tooling/analyzer.py` — which is why the name was
  "defined somewhere" and simultaneously absent from the module's defs, and
  `ensure_name_access` refused it.

  That is the recurring shape in `CLAUDE.md`: a correct mechanism with sibling
  paths that bypass it.

  Adding the missing case to each site fixed the instance and left the class — four
  places enumerating node types independently drift again the next time a form is
  added. They now share one answer: **`FLOW_DECLARATIONS` and `declared_flow_name`
  in `ast_nodes`**, with each site keeping its own action (define a symbol, add to a
  defs set, bind a type) and none of them enumerating.

  The tests drive off that tuple rather than grepping the files, so a form added to
  it fails until every site handles it. One of them exercises the tooling collector
  directly, because the end-to-end tests do not reach it: while consolidating, an
  unimported name sat in `tooling/loader.py` and every behavioural test still
  passed. Only `ruff` caught it, and a linter is not evidence that a path works.

- **#502: a timed-out step now runs its `finally` blocks before it is dropped.**
  `EXECUTION_INVARIANTS.md` **I-VM-06** states that `finally` blocks always
  execute. The scheduler discarded a timed-out coroutine where it stood, so they
  did not — a step holding a lock, an open transaction or a spawned subprocess
  lost its release in exactly the circumstances cleanup exists for.

  `timeout_ms` is the sharp case: it is a documented step option whose whole
  purpose is to bound a step that might hang, so a user who bounds a hanging step
  *and* wraps its resource in `try/finally` had done everything the documentation
  asks and still leaked.

  The coroutine is now resumed once more with a cancellation in flight, unwinds
  through its pending `finally` blocks, and then delivers the timeout exactly as
  before. Bounded by the same step budget as any other resume, so a `finally`
  that loops cannot turn a timeout into a hang.

  **A `catch` cannot swallow the deadline.** While cancelling, `handle_exception`
  refuses to enter a catch handler: `finally` runs, `catch` does not. Unwinding
  with an ordinary error would have let a step absorb its own timeout and carry
  on past the bound it was given.

  A step with no pending handlers takes the original path untouched — no extra
  resume, no behaviour change for the common case.

  The other trigger, a sibling step failing, was fixed earlier in this cycle by
  draining the run rather than tearing down the scheduler.

- **#469: a workflow started through `NodusRuntime` can now be resumed in another
  process.** `vm.source_code` is what `_rebuild_workflow_graph` recompiles to resume
  a run, and only `tooling/runner.py` and `dap/server.py` set it. Every embedded run
  therefore recorded `workflow_source_code: None`, so one `resume_workflow` call meant
  three different things depending on how the run had started:

  | entry point | resume replayed |
  |---|---|
  | `nodus run`, `nodus dap` | the source stored with the run — edits ignored |
  | `NodusRuntime.run_file` | whatever was on disk at resume time — edits picked up |
  | `NodusRuntime.run_source` | nothing; the run could not be resumed at all |

  All three are pinned now: **a resume replays the source the run was planned
  against.** Re-executing against the program the run was planned for is what makes
  checkpoint-restore mean anything, and it is the only reading compatible with a
  determinism boundary (#494).

  Same-process resume always worked — it succeeds off the in-memory graph registry
  and never reaches the rebuild — which is why this went unnoticed.

  `source_code` is now a `VM` constructor parameter beside `source_path` rather than
  an attribute assignable only afterwards. That is the actual fix for the class of
  bug: an entry point could pass `source_path`, look complete, and record no source.

  **Behaviour change for embedders:** `NodusRuntime.run_file` no longer picks up
  edits made between a run and its resume.

### Added

- **A `state` cell can declare how it merges and whether it is durable — D6.**

  ```nd
  state attempts = 0i  with { merge: "once" }
  state client   = nil with { durable: false }
  ```

  Same `with { ... }` form steps take, so no new syntax and the policy stays
  inspectable data. Two axes, **not three**: an earlier framing had typing here as
  well, but #479 is about untyped *step outputs* and hand-written tool schemas and
  never mentions state — the `: type` slot stays free for a separate decision.

  **`merge`** — what happens when two steps the graph does not order write the
  same cell:

  | value | meaning |
  |---|---|
  | *(undeclared)* | last write wins, and a warning names both steps |
  | `"any"` | last write wins, warning silenced |
  | `"once"` | a second concurrent writer is an error |

  Declaring `"any"` changes no behaviour — it says *I know these branches agree*,
  and silencing the warning by stating that is the point. An undeclared cell keeps
  warning, since that warning is the only thing between a lost update and silence.

  **Folding is not available**, deliberately. `sum` / `append` / `union` need a
  branch to contribute a value the runtime applies at the join rather than
  assigning into a shared slot — a change to what a state write *is* (#485).
  `merge: "sum"` is refused where it is written, with that reason, rather than
  quietly behaving as last-write-wins. When it lands it should stay a closed set:
  a fold must be batching-invariant or a resume that regroups writes produces a
  different total, silently.

  **`durable: false`** keeps a cell out of the checkpoint (#498). A cell holding a
  live handle has no meaning after a resume, and every cell was previously
  persisted — so a value `json` could not encode killed the run at the first
  checkpoint. A non-durable cell is **absent** from restored state rather than
  restored as `nil`, because a `nil` would look like a value the workflow had set.

  No new opcodes; `BYTECODE_VERSION` is still 4.

- **Concurrent writes to one state key are now reported instead of silently losing
  one.** Two fan-out branches that read a `state` key, yield, and write it back
  lose one of the writes: the run reports `ok`, nothing appears in `failed`, and
  the value is wrong (#485).

  ```
  warning: steps a and b both wrote state 'counter' while running concurrently;
  only b's write survives. If they each read it first, one update was lost.
  ```

  Also emitted as a `workflow_state_write_conflict` event.

  **This reports; it does not repair.** Repairing means changing what a state
  write *is* — a branch contributing a value the runtime applies at the join,
  rather than assigning into a slot another branch is halfway through reading.
  That is a state-model change, and it wants deciding alongside the type (#479)
  and durability (#498) axes that attach to the same declaration. Turning a
  silent wrong answer into a loud one is the half that is cheap now.

  **The test is structural, not temporal.** A first attempt compared the recorded
  start/finish timings and flagged a plain sequential `a → b → c` writing one key:
  instant steps share a millisecond timestamp, so every interval overlaps every
  other. Wall-clock cannot separate "sequential and fast" from "concurrent";
  dependency order can, exactly.

  **It warns before the bug happens.** Two independent steps that happen to be
  serialised — because neither yielded — are still reported. That is deliberate:
  the cooperative scheduler serialises a step body with no suspension, so the
  obvious test passes and teaches you concurrent state writes are safe. They are
  safe until a step does something real, and the warning has to arrive before the
  step grows its first `sleep` or agent call.

  A warning rather than an error, because two branches writing one key can be
  deliberate when the author knows they agree — and there is currently no way to
  say so. Once a declaration exists, the default can tighten.

- **A step can carry a guard — `step ship after review when reached("approved")`.**
  Workflow edges were unconditional, so data-dependent branching was expressible
  only *inside* a step body, where the graph cannot see it: `plan_workflow` reported
  the same levels regardless of what the run would do (#471).

  The guard takes the **same restricted predicate grammar** as a goal's `until` —
  `reached("label")` composed with `&&`, `||`, `!` and parentheses — and for the
  reason already recorded in the parser: a general expression would be compiled
  code, invisible to `plan_workflow`, and would make the checkpoint check
  best-effort. Restricted, the predicate stays *data*, so a guard naming a
  checkpoint its workflow never records is a **compile error**:

  ```
  step 'deploy' waits on checkpoint "aproved", which 'deployment' never records.
  It records "approved".
  ```

  A step whose guard does not hold is **`skipped`**, and the skip **cascades**:
  a step whose dependency was skipped is skipped too, since `after` reads as
  *needs*. `on: ["completed", "skipped"]` runs it anyway.

  That default is Airflow's rather than Argo's, and it is a deliberate departure
  from what the issue's earlier analysis suggested. Argo treats a skipped upstream
  as *satisfying* the dependency because it has no way for the downstream task to
  say otherwise; Nodus now does, so the safe default plus an explicit escape is
  available and the surprising default is not needed.

  `when` is contextual, so it stays usable as an identifier. No new opcodes;
  `BYTECODE_VERSION` is still 4.

  **`plan_workflow` becomes a superset once any step carries a guard** — every step
  that could run, not every step that will. It remains exact about structure, and
  every step still reaches a reported status.

- **A step can declare which dependency outcomes satisfy its join — `with { on: [...] }`.**
  `step b after a` has always meant *and a produced a value*. That is a join policy,
  and it was the only one, so the cleanup step every pipeline needs — run this when
  the deploy fails — could not be expressed in the graph at all (#475).

  ```nd
  step rollback after deploy with { on: ["completed", "failed"] } { ... }
  ```

  Valid outcomes are `completed` and `failed`: the two a dependency can reach while
  the run is going. `upstream_failed` and `cancelled` are conclusions drawn once the
  run winds down, so a step waiting on one could never become ready — accepting them
  would ship a knob that silently never fires. An outcome outside the vocabulary is
  refused where it is declared rather than quietly never matching.

  The default is `["completed"]`, so existing workflows are unchanged.

  Three consequences worth knowing:

  - **A step whose condition is not met reports `omitted`, not failed.** That is
    distinct from `upstream_failed` — a decision excluded me, versus something above
    me broke — and keeping them apart is the point of declaring a policy at all. It
    also means such a step no longer turns the run into a "Missing task dependencies"
    error, which is what a step left pending used to do.
  - **Fail-fast exempts a step that opted in.** A failure otherwise stops the run
    scheduling new work, which would make `on: ["failed"]` unreachable in exactly the
    situation it exists for.
  - **A failed dependency passes `nil`**, since it produced no value. The step is not
    told *why*; that belongs with the partial-success envelope (#468).

  No new syntax, no new keywords, and no opcode change — `with { ... }` and the
  option-key validation already existed, and the policy is data, following the
  precedent set by a goal's `until` predicate. `BYTECODE_VERSION` is still 4.

  This answers the second half of #475. The first half — whether an independent
  branch should run at all after a sibling fails — is still open, and is now visible
  in the result as `cancelled` rather than silent.

- **A resume says so when the file has changed since the run started.** Pinning is
  the right rule but a trap when it is silent — the natural debugging loop is *the
  workflow failed, so edit the step and resume*, and the edit appears to do nothing.
  A resume whose stored source differs from the file now writes a warning to stderr
  and emits a `workflow_source_drift` event:

  ```
  resume: 'w' is replaying the source stored when the run started; wf.nd has changed
  since and those edits are not in this run. Start a new run to pick them up.
  ```

  Reported rather than refused: a resume that stops working because someone touched
  the file would be worse than one that explains itself.


- **Every task in a run now reports a status — `statuses` and `task_statuses`.**
  A failing run produced four distinguishable outcomes and named one of them:
  `failed` listed the step that threw, and anything that never got a turn was simply
  absent from the result. The two new keys mirror how `steps` and `tasks` are keyed
  (by step name and by task id):

  | status | meaning |
  |---|---|
  | `completed` | produced a value |
  | `failed` | threw, retries exhausted |
  | `upstream_failed` | a transitive dependency failed |
  | `skipped` | its guard was not satisfied |
  | `omitted` | a step it depended on was skipped |
  | `cancelled` | never started — the run had already failed |
  | `abandoned` | still running when the run ended |

  The vocabulary is limited to distinctions the runtime can actually draw. When this
  entry was first written that was five values, and it said `skipped` and `omitted`
  waited on a conditional-edge design — then step guards landed in this same release
  and made both drawable, so they ship here too. `omitted` is the transitive closure
  of `skipped`, the way `upstream_failed` is of `failed`.

  `cancelled` is the open half of #475 made visible: whether an independent branch
  should run anyway is a design question, and it is easier to answer when the result
  says which steps it applies to. `abandoned` should be unreachable on the failure
  path after the change above — if it appears, something dropped a coroutine without
  unwinding it.

  Additive only: existing keys are unchanged and callers checking `failed` are
  unaffected.

### Changed

- **A failed step no longer tears down the scheduler: the run drains, then reports.**
  A terminal step failure told the scheduler to break its loop, which dropped every
  other coroutine where it stood. A healthy independent branch that was mid-execution
  was abandoned — its remaining statements never ran and its `finally` never
  executed, so a step holding a lock or an open transaction lost its release in
  exactly the circumstances cleanup exists for. That contradicted runtime invariant
  I-VM-06 (`finally` blocks always execute); see #502, whose other trigger — a step's
  own `timeout_ms` — is unchanged and still open.

  The failure now stops the run from *advancing* without stopping it *finishing*:
  no new work is scheduled, and whatever is already in flight runs to completion
  before the run reports. This is Argo's `failFast: true`, which is stricter than
  #475 asks for and looser than what shipped.

  Nothing was added to hold work back — `spawn_task` has always refused to schedule
  once a failure is recorded. Only the loop teardown was wrong.

  Two visible consequences: a failing run takes as long as its slowest in-flight
  step rather than returning immediately, and `steps` now includes work that
  finished after the failure.

### Tooling

- **`nodus_gate --consumers`: which non-PyPI consumers a release has left behind.**
  Stage 6's downstream sweep detects drift by hashing published sdists and wheels,
  so anything not on PyPI is invisible to it — and two things are: `nodus-vscode`
  (a Marketplace VSIX) and `nodus-run-action` (a GitHub Action). Both have shipped
  stale with nothing to notice. Documented as Gate 3c.

  Each consumer records in `tools/consumers.json` the fingerprint of whatever it
  must stay in step with, measured in *this* repo when it was last published. When
  the live value moves, the consumer needs republishing:

  ```
    [--] nodus-vscode (0.1.2) — NEEDS REPUBLISH
         keywords moved: 8670d9baf85b0313 -> 602761bf77ebb21e
    [--] nodus-run-action (v1.0.0) — NEEDS REPUBLISH
         nodus_version moved: 4.0.5 -> 5.0.4
  ```

  It reads **no sibling checkout and makes no network call**, which is the whole
  design. Gate 3b's keyword-highlighting check does read the `nodus-vscode`
  grammar, and therefore skips on CI where the checkout is absent — which is
  exactly how the `when` keyword shipped unhighlighted. A check that cannot run
  where merges are gated is not a check.

  **Advisory**: it prints and exits 0, so a stale consumer does not block an
  unrelated merge; `--strict` makes it fail. A manifest that cannot be read is
  always a failure, and a `tracks` value the phase cannot measure is an error
  rather than a silent skip.

  Both consumers were flagged on the gate's first run, and both have since been
  republished — **nodus-vscode 0.1.3** (highlights `when`) and
  **nodus-run-action v1.0.1** (README pins 5.0.4, `v1` moved). The manifest
  records those, so the gate now reports 2/2 in step.

## [5.0.4] - 2026-08-17

### Fixes

- **5.0.3 broke `nodus-sdk` at construction.** `NodusRuntime.__init__` assigned
  `self.memory_store` (#185), and `nodus_sdk.NodusSDKRuntime` subclasses it with
  `memory_store` as a **read-only property** returning its own vector store — a
  different concept from Nodus script memory. Every construction raised:

  ```
  AttributeError: property 'memory_store' of 'NodusSDKRuntime' object has no setter
  ```

  nodus-sdk went from 99 passed to **29 failed, 10 errors**. The store is now held
  privately as `_memory_store`, leaving the public name free; nodus-sdk is back to
  99 passed with no change needed on its side, so the fix reaches users through a
  nodus-lang release rather than requiring every companion to move.

  Two things worth keeping from it: a base class adding a public attribute can
  break a subclass that made the same name a property, and taking a name already
  used downstream for a different concept is how you get there.

### Tooling

- **`tools/check_dependent_suites.py`, and Gate 10 now runs it before the upload.**
  Gate 10 validates nodus-lang against itself and passed 5.0.3 cleanly — 32
  adversarial probes, all green. Nothing in it executes a *dependent*. Stage 6
  does, and caught this, but Stage 6 is post-publish and PyPI is immutable, so the
  break was found one release too late.

  Running the six dependent suites is now step 0 of Gate 10. A missing checkout
  exits 2 rather than passing: an unrun suite covers nothing.


## [5.0.3] - 2026-08-17

### Fixes

- **#185: two `NodusRuntime` instances in one process shared guest-writable memory.**
  `GLOBAL_MEMORY_STORE` was bound at import and shared by every runtime, so in a
  multi-tenant host — the nodus-sdk FastAPI bridge, say — one request's script
  could read another's. Verified before the fix:

  ```python
  rt_a.run_source('memory_put("secret", "password123")')
  rt_b.run_source('print(memory_get("secret"))')      # -> password123
  ```

  Each runtime now gets its own store. Sharing is still available, deliberately:
  pass `memory_store=` to hand two runtimes the same one, or
  `share_process_state=True` to restore the previous behaviour in one word. A bare
  `VM` and the CLI keep the process-global store — single-tenant by construction,
  so changing them would be churn without a threat model.

  **Agents are deliberately *not* isolated**, though the issue groups them with
  memory as "similar process-level scope". They are not the same: a guest script
  *writes* memory (`memory_put` is a builtin), but cannot register an agent at all
  — the only agent builtins are `agent_call`, `agent_available` and
  `agent_describe`, and registration is host-only from Python. So a shared agent
  registry holds what the *host* put there, and isolating it by default would break
  the ordinary `register_agent(...)` then `run_source(...)` flow — it broke 11
  existing tests when tried — to prevent a leak guests have no way to cause. Hosts
  that do want per-tenant agent sets pass `agent_registry=`.

- **#390: workflow state was process-global with no owner.** Every workflow builtin
  resolved the runner through `get_default_workflow_runner()`, so the VM had no
  handle on which runner it belonged to, and any two participants in a process — a
  service, an embedded runtime, a test — shared one store, one graph registry and
  one sweeper thread with no way to tell whose run was whose.

  Four separate bugs in #376 traced back to this, and each was fixed with a
  *timing* defence (`min_idle_ms`, claim-before-rehydrate) against a *structural*
  problem. Ownership makes the class unreachable rather than individually
  patchable: a sweeper that can only see its own runner's runs cannot adopt
  someone else's.

  A VM now resolves its runner from context (`VM.resolve_workflow_runner()`), and
  `RuntimeService` threads its own runner into every VM it builds — previously
  eight separate `VM(...)` constructions, now one factory, so a ninth call site
  cannot forget. `NodusRuntime(workflow_runner=…)` injects one for embedded use.

  The fallback is kept: a VM with no runner uses the process-global one, so a bare
  embedded runtime and the CLI behave exactly as before and no embedding API
  breaks. Tests assert on the *source* as well as the behaviour — a sixth builtin
  reaching for the global directly fails the suite, which a behaviour test would
  not catch while the other five stayed routed.


- **#424: a host agent handler could hang the run forever.** `call_agent` invoked
  the registered handler with no deadline of any kind, so a hung HTTP call, a model
  provider that never responds, or a `while True` blocked the run indefinitely.

  Every other bound in this runtime is a property of the **instruction stream**,
  and a host handler is not in it. Measured with the same step option and the same
  value:

  | `step … with { timeout_ms: 500 }` | elapsed |
  |---|---|
  | around a pure-Nodus busy loop | **0.59 s** — bounded |
  | around a handler blocking 3 s | **3.76 s** — not bounded |

  Worse than merely absent: the blocked step *did* fail as timed-out, but only
  after the handler ran to completion. The bound was **reported without being
  enforced**.

  A deadline now applies, from the tightest of two sources: the step's existing
  `timeout_ms` (minus what the step has already spent), and a new runtime-level
  default, `NodusRuntime(agent_timeout_ms=…)`, for `agent_call()` made outside any
  step. No new per-step syntax — the knob users already reach for now does what it
  says. Same handler, before and after: **3.50 s → 0.34 s**.

  **What this does not do, stated plainly.** Arbitrary Python cannot be preempted.
  The handler runs on a daemon thread and the caller stops waiting at the deadline;
  the handler itself keeps running and cannot be cancelled. The *run* becomes
  bounded, which is the property that was missing. The thread is not reclaimed,
  which is the price — so abandoned handlers are recorded and countable
  (`abandoned_agent_calls()`, `abandoned_agent_call_count()`), and the record is
  itself bounded to 100 entries, because an unbounded one would be this same defect
  one level up.

  A timeout is reported as an ordinary agent failure, so a step's `retries` and the
  retry classifier act on it exactly as they do on any other. Unbounded remains the
  default: nothing changes for a host that does not ask for a deadline.

  Note this is **not** covered by `goal … over … { budget { deadline_ms } }`.
  That budget is evaluated between iterations, after the workflow hands control
  back — verified: a 0.5 s budget over a 3 s handler still took 3.10 s.


- **#387: a directly constructed `VM()` had no call-depth cap.** `max_frames` now
  defaults to `MAX_STACK_DEPTH` (10,000) instead of `None`, matching what the CLI,
  the HTTP server and `NodusRuntime` all already install.

  This is #350 one layer down. That issue was "`NodusRuntime` applies no
  `max_frames` cap despite documenting one", and the fix put the cap in the
  embedding path — but the defect was never really about `NodusRuntime`: the guard
  lived in a wrapper and every other entry point bypassed it. A real consumer was
  already exposed; `nodus-jupyter`'s kernel runs every notebook cell on a bare
  `VM(...)` and never calls `configure_vm_limits`.

  **Why this limit and not the other two.** VM frames are heap-allocated, so
  Python's own recursion limit never fires — measured before the fix, depth 5,000
  completed on a bare VM against a `sys.getrecursionlimit()` of 1,000. Unbounded
  recursion does not raise; it grows until the OS kills the process, which a host
  cannot catch, log, or recover from. `max_steps` and `deadline` stay `None` on
  purpose: `EXECUTION_TIMEOUT_MS` is 200 ms and would break most in-process
  consumers, and a step budget is host policy. Both are pinned by test so
  "give the VM limits" is not over-applied later.

  Hosts can still opt out — `vm.max_frames = <large int>` — exactly as with
  `NodusRuntime`. `VM` also gains a class docstring saying plainly that
  constructing one directly opts out of the remaining limits and of
  deny-by-default, and pointing at `NodusRuntime` or `configure_vm_limits`.


- **#453: a script ending in `main()` executed it twice on every run after the
  first.** Silently — no error, and nothing in the output to suggest a second
  execution:

  ```
  $ nodus run script.nd      # cold cache
  M
  $ nodus run script.nd      # warm cache
  M
  M
  ```

  `auto_run_main` exists so a script that merely *defines* `main()` still runs it,
  and is suppressed when the module's own top level already calls `main()`. That
  suppression read the AST and returned `False` whenever `parsed is None` — which
  is exactly the state of a module loaded from the bytecode cache. So the guard
  held on the first run and was bypassed on every run after it.

  This codebase's recurring shape: a correct check that one path goes through and
  a sibling path skips. The answer now travels with the bytecode
  (`has_top_level_main_call` in the cached module metadata) instead of being
  recomputed from an AST that is not always there. Where it is genuinely unknown,
  the loader now assumes the top level *did* call `main` — running it once too few
  produces a script that visibly does nothing, while once too many silently
  repeats every side effect.

  **Blast radius was wider than the issue recorded.** It was filed as "running a
  script by path from inside a Nodus project", because a project directory is
  where a `.nodus/` cache tends to exist. The real trigger is the warm cache, so
  it applied to any repeated run anywhere — and doubled side effects are precisely
  what `@exactly_once` exists to prevent, arriving by an unrelated route.

  It also means **every Gate 10 before v5.0.2 read doubled eval output** without
  noticing, because those evals compared the wheel against dev source and found
  them byte-identical. They were: both sides doubled equally.

- **#396: `nodus check` now reports a workflow dependency cycle.** It previously
  printed `OK` for a workflow whose steps depend on each other in a loop — the one
  structural property of a workflow knowable from the source alone:

  ```
  $ nodus check cyc.nd
  Dependency cycle in workflow 'w': a -> b -> a
  ```

  The detector was not written for this. `_detect_cycle_task_ids` has run at
  *execution* time since #323; both callers now route through one implementation
  in `support/graph_cycles.py`, so the check-time and run-time notions of a cycle
  cannot drift.

  **Deliberately not a parse error.** Rejecting the cycle in the parser also works,
  and breaks 14 tests in `tests/test_cyclic_workflow_err.py` — because #323
  established on purpose that `run_workflow` returns an inspectable `err` record
  with `category: "cyclic_workflow"` that scripts test against. The right reading
  of those failures is that the runtime behaviour is load-bearing, not that the
  tests were stale. `check` gains the diagnosis; `run` keeps the recoverable error.
  Both halves are pinned by test.

- **#425: resuming a workflow run that does not exist now says so.** It reported
  `Workflow run 'g_x' is already claimed`, sending the reader to look for a
  concurrent run that was never there. Every status check on the resume path is
  guarded on `record is not None`, so an unknown `graph_id` fell through all of
  them to `claim_run`, which returns `None` both for "someone else holds the claim"
  and for "there is nothing to claim". A typo'd id is far likelier than a claim
  conflict.

- **Backlog: a duplicate issue closed.** The same closure-mutation defect was
  filed twice in the 2026-06-07 audit batch under two headings — #177 (LIMITS-005)
  is closed in favour of #156 (DESIGN-006), which carries the fuller reproduction.
  Verified still reproducing on 5.0.2 before closing. No code change; the defect
  itself remains open on #156.

### Tooling

- **`src/nodus/support/graph_cycles.py`** — the cycle algorithm, extracted so the
  checker and the runtime share it. Iterative rather than recursive: a long
  dependency chain would otherwise be bounded by Python's recursion limit, and a
  `RecursionError` surfacing from `nodus check` is a poor way to learn that. Tested
  against a 5,000-node chain.

## [5.0.2] - 2026-08-17

### Fixes

- **#411: `@exactly_once` and `@retry` were forgeable.** Both lower to calls on
  builtins (`effect_action_id` / `effect_resolve` / `effect_pending` /
  `effect_complete`, and `retry_call`). Those calls went through ordinary name
  resolution, and `VM._op_call` resolves user functions **before** builtins — so a
  program could supply the machinery the compiler had injected into its own code:

  ```nodus
  fn effect_resolve(aid) { return {done: true, cached: {result: "FORGED"}} }

  @exactly_once
  fn work() { return "real" }

  print(work())        // -> FORGED. The annotated body never ran.
  ```

  Lowerings now emit their calls through a reserved prefix that `_op_call`
  dispatches straight to the builtin table, ahead of the user-function lookup.
  Names beginning with that prefix are rejected in source, so the namespace cannot
  be entered from a program.

  **The workflow lowering had the same hole, and it was live.** #411 mentioned
  `workflow_state` in passing as "same for any builtin a lowering depends on"
  without demonstrating it; asking *what else has this shape* found that every step
  body begins `let __workflow_state = workflow_state()`, so three lines replaced
  the state map every step reads:

  ```nodus
  fn workflow_state() { return {"total": 9999i} }

  workflow w {
      state total = 0i
      step add { total = total + 1i; print("total is \(total)") }   // -> 10000
  }
  ```

  Fixed with the same helper, along with the five `__action_*` calls the lowering
  emits. The helper therefore lives in the AST module rather than on `Compiler`:
  lowerings are split across the compiler and `orchestration/`, and a fix only one
  of them could reach would have left the other forgeable.

  Binding those action calls also required teaching `_is_action_builtin` to look
  past the prefix. It decides whether a step body's trailing action becomes a
  `Return`, and it compared the raw callee name — so prefixing the call silently
  stopped it matching and every step ending in an action returned nil. The symptom
  surfaced a full call away, as `Indexing is only supported on lists, maps, and
  strings`. That is #411's own defect in miniature — a name-based decision broken
  by a rename — which is why the matcher now strips the prefix rather than
  comparing against both spellings.

  **A fourth vector, not in the issue: a *parameter* named `effect_resolve` forged
  the envelope just as well.** A parameter is a local binding, so it resolves ahead
  of both globals and builtins — which is why the issue's alternative fix,
  reserving a list of global builtin names, would not have closed this. The fix
  covers it because the emitted name never participates in resolution at all.

  Scope unchanged in one respect, and pinned by test: this never crossed a module
  boundary. A caller could not forge an *imported* module's envelope, because the
  library resolved the builtins in its own module scope.

  No new opcode and no bytecode change — still 49 opcodes at `BYTECODE_VERSION` 4.

  The general rule matters more than the annotation: **a compiler-applied guarantee
  is only as strong as the name resolution of the calls it emits.** Any future
  lowering intended to hold against the program's author must use
  `Compiler.builtin_call()`. `docs/design/v5/00-domain-statement.md` — which rests
  its whole argument on `@exactly_once` being unforgettable — now records that the
  claim was false when written and what makes it true.

- **#449: the bytecode cache was not keyed on the nodus-lang version, so compiler
  fixes silently did not apply after an upgrade.** Found while verifying the #411
  fix, and it is the more dangerous of the two.

  `.nodus/cache` entries are keyed on `sha256(absolute_path + mtime_ns)` and
  validated against `NODUS_BYTECODE_VERSION` — the *bytecode format* version,
  frozen at 4 since v1.0 and governed by #366, which by policy does not move when
  the compiler changes. So after an upgrade every cached module stayed compiled by
  the **old** compiler until its source was touched:

  ```
  old compiler populates cache      -> result: FORGED
  upgraded compiler, cache present  -> result: FORGED   # fix did not apply
  same, after rm -rf .nodus         -> result: real
  ```

  A host upgrading to pick up a compiler fix, with a warm cache, kept executing the
  vulnerable lowering — no error, no warning, and `nodus --version` reporting the
  new release. The cache payload now records the nodus-lang version and a mismatch
  invalidates the entry. Compared strictly, not "newer than": a downgrade must miss
  too, since that bytecode came from a compiler this one does not match either.

  Existing coverage read as though this were handled —
  `test_bytecode_cache_invalidates_when_version_changes` bumps
  `NODUS_BYTECODE_VERSION`, the one version that never changes for a compiler fix.
  The case that happens on *every* upgrade had no test; it does now, with a
  positive control so a change that made every load miss cannot pass by turning the
  cache off.

### Tooling

- **`tests/test_annotation_forgery.py`** — the forgery vectors, each with a
  positive control, because a lowering that stopped calling the effect builtins
  altogether would pass every negative test. Also asserts on the *source* of both
  lowerings: a future lowering that emits an ordinary `Call(Var("effect_…"))` fails
  the suite even if nothing yet exploits it. 10 of its 14 cases were verified to
  fail against 5.0.1 and pass after the fix; the 5 that pass either way are the
  pre-existing properties, including the module boundary.

  One measurement worth recording, because it nearly drove a worse design. The
  added `startswith` on the call path first appeared to cost ~8% on a call-heavy
  loop, which prompted a more complicated fix (pre-aliasing every builtin under
  the prefix at VM construction). Measured directly with `timeit`, the check costs
  **~81 ns/call** — 0.08% of that loop. The 8% was noise from this machine's
  documented timing instability, which was active at the time (the suite ran 15:11
  against 7:46 earlier the same day). The simpler call-time resolution was kept,
  and it is also the more robust one: it has no construction-order dependency, so
  builtins merged later are reachable.

## [5.0.1] - 2026-08-17

Every item here came from a downstream adoption report on 5.0.0 (aindy-runtime).
None is a defect in what 5.0.0 does; all are places where a consumer was coupled
to something that was never published as a surface.

### Added

- **#441: `GATED_BUILTINS` and `GATED_BUILTIN_NAMES`** in `nodus.runtime.capability`.
  The registration-time capability gates, as data: flag → `GatedBuiltinGroup`
  with `flag`, `capability`, `description`, `arity` and `names`.

  There was no way to enumerate the gated surface, so an embedder asserting its
  own confinement regexed the source of `BuiltinRegistry.register_all`. The 5.0.0
  refactor moved those names into the `else:` branch and the regex broke —
  silently, then loudly: it began capturing flag names out of `_denied_reason()`
  and reporting them as three phantom leaked builtins.

  `register_all` now builds its refusing stubs *from* this data rather than from
  its own copy of the names, so the published list and the enforced gate cannot
  disagree. Note it is a different list from `BUILTIN_CAPABILITIES` — that one is
  what consults the policy at call time — and the two differ by exactly one entry
  (`subprocess_shell_quote`, string manipulation that runs nothing). They were
  previously maintained separately with nothing checking they agreed;
  `tests/test_downstream_contracts.py` now pins the relationship.

- **#442: `NodusRuntime.active_vm()`** — a supported accessor for the VM of the most
  recent run. Embedders were reaching it through `_get_active_vm()`, which carried
  no compatibility promise. That name is retained as an alias, un-deprecated,
  because downstream pins it. The promise is narrow and stated as such: the
  accessor is stable, the `VM` object it returns is internal.

- **A capability-policy section in `LANGUAGE_STABILITY_INDEX.md`.** The whole
  `nodus.runtime.capability` surface shipped in 5.0.0 unindexed — no tier for
  `CapabilityPolicy`, `DEFAULT_FLOOR`, the labels, or the denial contract. Being
  absent from the index is why scraping the source looked like the only option.

### Changed

- **#444: the denial contract is now stated.** Two fields are contractual: `error["kind"]`
  is `"sandbox"` for every capability refusal, and `error["message"]` contains the
  name of the flag that grants the capability. The wording around the flag name is
  **not** contractual and did change in 5.0.0 — which cost a downstream embedder
  four red confinement tests while its guest was fully confined, refusals firing
  correctly with `kind: "sandbox"` and `capability_denied` on the bus. Documented
  in the embedder runbook §3.3 and pinned by test.

### Fixes

- **#445: five companion packages could not be installed alongside 5.0.0.** No change to
  this package, but the most user-visible problem with the 5.0.0 release:
  `nodus-mcp`, `nodus-mcp-server`, `nodus-extension`, `nodus-sdk` and
  `nodus-native-memory-engine` all published a `nodus-lang<5.0.0` cap, so
  `pip install nodus-lang==5.0.0 nodus-mcp` failed with `ResolutionImpossible`.
  Only `nodus-jupyter` was installable. Every cap was prophylactic — no 5.x break
  was ever recorded in any of them, and all five suites pass against 5.0.0
  unchanged (363 / 25 / 126 / 99 / 76).

  All five have been republished with the cap floated: nodus-mcp 0.1.3,
  nodus-mcp-server 0.1.12, nodus-extension 0.1.1, nodus-sdk 0.1.2,
  nodus-native-memory-engine 0.1.1.

  The Stage 6 sweep that was supposed to catch this recorded five of the six
  ranges with the upper bound dropped, and concluded the opposite of the truth.
  `docs/evals/v5.0.0/STAGE6_DOWNSTREAM_SWEEP.md` carries a dated correction.

- **`README.md` advertised 4.2.0 as the current stable release** through the whole
  5.0.0 cycle — its banner, and a "Recent:" paragraph describing 4.2.0's contents.
  It also still framed deny-by-default as "breaking in the next release" after that
  release had shipped.

### Tooling

- **#443: `tests/test_downstream_contracts.py`** — pins the surfaces above, plus three
  properties of `NodusRuntime.__init__` that an embedder asked us to *keep* and
  that nothing protected: it takes no `**kwargs` (so a renamed confinement flag
  raises `TypeError` instead of being silently swallowed while the guest runs
  unconfined), its confinement flags are keyword-only (so an argument reorder
  cannot change which boundary is denied), and they still default to `False`.

  Also pins `register_function`'s refusal to override a builtin name. That refusal
  is load-bearing as a security boundary — because a builtin cannot be aliased, a
  host can install a fail-loud guard under a guest-reachable name and know the
  guard is the only thing there — and it was documented in a docstring and never
  asserted.

  Following this codebase's rule: where a behaviour test would pass on whichever
  path already works, the test asserts on the source instead. The gate-list test
  fails against the 5.0.0 registry and passes against the refactored one; verified
  both ways rather than assumed.

- **`tools/check_downstream_constraints.py`** — Stage 6's dependency-range check,
  as a command. It reads *published* PyPI metadata and resolves it with
  `packaging`, rather than reading `pyproject.toml` by eye. `RELEASE_GATES.md`
  Stage 6 step 1 now requires running it and pasting the output; its former
  wording offered `>=X,<5.0.0` as the example of a range that "needs nothing",
  which is precisely the range that blocked this release.

  `tests/test_downstream_constraints_tool.py` runs it against the six requirement
  strings as they were actually published on 2026-08-17, so the check is pinned to
  fail on the metadata that fooled a careful reader — not merely to pass today.

## [5.0.0] - 2026-08-17

### Changed — BREAKING

- **#405 stage 5.** `allow_subprocess`, `allow_network` and `allow_env` now
  default to **`False`** on `NodusRuntime`. A bare `NodusRuntime()` cannot shell
  out, open sockets, or read the process environment.

  ```python
  # before — worked
  NodusRuntime().run_source(script)

  # now — grant what the script needs
  NodusRuntime(allow_subprocess=True, allow_network=True).run_source(script)
  ```

  The error names the flag rather than merely reporting the absence, because with
  deny-by-default most readers never set it to `False` themselves:

  ```
  Blocked: subprocess execution is not granted;
           pass allow_subprocess=True to NodusRuntime to allow it
  ```

  `allowed_paths` is unchanged — it already defaulted to a CWD jail.

  **`nodus run` and the other CLI commands are deliberately unaffected.** The
  domain this protects is *work you did not fully author*; a developer running a
  script they just wrote is not that, and a CLI that refused to shell out would
  be like `python` refusing to open sockets. The paths are genuinely separate —
  `nodus run` builds a `VM` directly and never constructs a `NodusRuntime` — and
  a test pins both halves so the "inconsistency" is not later tidied away.

  Why now: all three external architecture audits identified the host-function
  boundary as the highest-leverage change available, and audit 03 named the gap
  exactly — *"the chokepoint is built; the door is propped open by registering
  subprocess and http by default."* Stages 1–4 built the lock; leaving the
  defaults permissive would have shipped a lock on an open door.

  **Migration:** [`docs/migration/v5.0-deny-by-default.md`](docs/migration/v5.0-deny-by-default.md).
  Restoring the previous behaviour is one constructor call; there is deliberately
  no global switch.

  Blast radius, measured on this repo's own suite: **11 tests** assumed a bare
  runtime could shell out.

- **#405: a Nodus program can no longer write into `.nodus/`.** That directory is
  the workflow store, graph state and bytecode cache. Until now a guest script
  could overwrite a run record with defaults in place — verified: it wrote
  `{"forged": true}` over `.nodus/workflow_framework/runs/<id>.json` and the run
  reported success. That is forging durable state.

  This is the default capability **floor**, and the only non-additive part of
  #405. Reads are untouched; only writes are refused, matched on normalised path
  segments so `my.nodus-notes.txt` is unaffected and `../.nodus/x` is not. A
  floor that never fires would be the "check that cannot fail" this codebase
  keeps finding, so it ships with one real rule rather than empty.

### Added

- **#405: a capability policy can now be consulted at the host boundary.**
  Experimental, and additive — the default is no policy, and a runtime without
  one behaves exactly as before.

  ```python
  from nodus.runtime.capability import DenyList, SUBPROCESS
  rt = NodusRuntime(capability_policy=DenyList(SUBPROCESS))
  ```

  All three external architecture audits identified this boundary as the
  highest-leverage change available. Stages 1–2 of the staging in
  `CAPABILITY_POLICY_DESIGN.md`: a policy consulted at the chokepoints, denials
  recorded, and capability metadata on `register_function`.

  **Both chokepoints, not one.** That document stages builtins fourth, after host
  functions — which would have covered nothing that matters, because
  `subprocess_run`, `http_get` and `env_get` are *builtins* dispatched by
  `VM.call_builtin` and never touch `_invoke_host_function`. Both are covered
  from the start, and the policy travels with the VM so it is not shed by
  crossing into a module or a tool handler.

  What this adds over the existing `allow_subprocess` / `allow_network` /
  `allow_env` flags, which are registration-time and binary per category:
  per-call decisions, per-function authority via
  `register_function(..., requires=…)`, decisions that can read the call's
  arguments (permit `sp.run(["echo", …])`, refuse `sp.run(["hostname"])`), and a
  **`capability_denied` event** — including for those pre-existing flags, whose
  denials until now emitted nothing structured at all.

  Only capability-bearing builtins consult the policy; `len` and `push` do not,
  so the hot path pays one dict miss. That mapping is also the language's
  capability surface in one readable place.

  **The decision is three-valued** — `allow | ask | deny`. `ask` means *this
  needs a human*, and an embedder supplies an `approval_channel` to answer it.
  **`ask` with no channel is `deny`, never "run anyway"** — the alternative
  silently turns an unanswered question into permission.

  **A floor is consulted before any policy and can only restrict.** `Floor.check`
  returns a decision to impose or abstains; there is no way for it to return
  `allow`, so it can never grant what a policy would refuse. Built now because
  every reference system added a bypass mode under pressure and retrofitted a
  floor afterwards — Nodus has no bypass mode, so building it first is free.

  **Not built, deliberately:** routing `ask` to the durable `workflow_wait` pause
  (it only exists inside a step, and a capability check can happen anywhere),
  layered rule sources, approval caching, attenuation, and deny-by-default.
  Defaults otherwise stay permissive, so this builds the lock and leaves the door
  open — see `docs/design/v5/02-capability-policy.md` §6–7 for what that does and
  does not license claiming.

- **#409: `goal … over …` — a goal can now declare a stopping condition.**
  Experimental, and **additive**: `goal g { step … }` is unchanged.

  A workflow finishes when every step has run. A goal finishes when its condition
  holds, or its budget runs out. It contains no steps of its own — it names a
  workflow, and watches the checkpoints that workflow records:

  ```nd
  goal reach_quality over tune {
      until reached("good_enough")
      budget { max_iterations: 5, deadline_ms: 30000 }
  }
  ```

  Each pass resumes the workflow from the last checkpoint it reached, so `state`
  carries forward and successive passes differ. `retry from "label"` pins the
  re-entry point. `until` composes `reached("literal")` with `&&`, `||`, `!`.

  This is the loop two of the three external audits said was missing — audit 02's
  *"the plan→act→verify→replan loop is inexpressible"* and audit 01's *"no
  representation of an objective, no predicate over world state"*. It answers the
  **verify→replan** half; dynamic fan-out and conditional edges remain out of
  scope, and the DAG stays lexically fixed and acyclic.

  **The compiler checks the waypoints exist.** Naming a checkpoint the workflow
  never records is a compile error, not a goal that quietly never finishes:

  ```
  Syntax error at g.nd:5:11: goal 'ship' waits on checkpoint "verifed", which
  'deploy' never records. It records "attempted", "verified".
  ```

  That check is **exact, not best-effort**, because neither `checkpoint` nor
  `reached` accepts a computed label — and it is the thing a library structurally
  cannot do: a planner can watch checkpoints as they happen, but it cannot refuse
  to start.

  **`budget` is mandatory** (`max_iterations` and `deadline_ms`), and exhausting
  it is a **failure**: the goal returns an err record
  (`kind: "goal_error"`, `payload.category: "budget_exhausted"`, with the
  iterations and waypoints reached) rather than a result map, so it cannot be
  mistaken for success.

  Not implemented, each of which would extend the surface: pursuing a workflow
  declared in another module; predicates over the state *at* a checkpoint or over
  the *order* checkpoints were reached; a cost bound. Design record and the
  deviations from it: `docs/design/v5/01-goal-stopping-condition.md`.

  **`over`, `until`, `budget`, `reached` and `retry` are contextual keywords** —
  still usable as ordinary identifiers. The VS Code grammar was updated in the
  same change; the extension needs republishing for the highlighting to ship.

### Changed

- **`nodus workflow-run` accepts `--time-limit <ms>`.** It was the one run command
  without it (`run`, `check`, `debug` and `profile` all had it), and the #392 fix
  below made the gap bite: step retries are now taken in-process, so a step with
  `with { retries: N }` spends wall-clock budget it previously deferred out of.
  Measured on an idle machine, three attempts of a *trivial* retrying step cost
  ~110 ms warm and 801 ms cold — against a 200 ms default — and there was no flag
  to raise it. Behaviour is unchanged when the flag is omitted.

- **#393: `goal` and `workflow` now retry identically.** `run_task_graph`
  branched on `execution_kind` to decide how a failed step retries — a
  `workflow` persisted `retry_scheduled` and ended the run for a sweeper to
  resume, a `goal` retried in-process and completed. Two constructs that lower
  through the same function and are documented as identical differed in exactly
  the place nobody thinks to check, and in the direction opposite to their names:
  `goal` was the more reliable of the two for retries. The branch is gone. Both
  kinds now take the same decision, and it is made on the one thing that
  actually matters — see #392 below. `goal_retry_scheduled` is emitted alongside
  `workflow_retry_scheduled` so the two kinds' telemetry stays symmetric too.

  **What changes for you:** a `goal` with `retries` running under
  `nodus serve` now defers to the sweeper the way a workflow always has,
  instead of retrying in-process. Everywhere else — CLI, embedding, in-language
  `run_goal` — it retries in-process as before.

- **`run_workflow_code`'s `inline_retries` parameter is removed.** It existed to
  turn on the retry loop that is now unconditional inside the runtime, and
  passing it is no longer meaningful. Callers passing `inline_retries=True` get
  the same behaviour by dropping the argument; callers relying on the `False`
  default now get retries honoured, which is the fix.

### Fixes

- **#427: `nodus fmt` no longer writes a file that stops parsing.** `with { ... }`
  is parsed by `parse_named_map_literal`, which requires **identifier** keys —
  and the formatter printed the resulting map through `format_expr`, which quotes
  them:

  ```
  step a with { retries: 2 }   ->   step a with {"retries": 2}
  Syntax error: Expected identifier, got string literal ('retries')
  ```

  `nodus fmt` writes in place, so it turned a valid file into a broken one, on the
  headline workflow syntax. It affected step options, `action … with { … }`
  payloads and goal budgets. The format gate never caught it because no `.nd` file
  in this repo uses `with { }`.

- **#427: nothing forced a new AST node to have a formatter case.** `nodus fmt`
  raises `TypeError: Unknown stmt node: …` for one it does not handle, and CI
  format-checks every `.nd` file — so the omission is a crash for whoever writes
  the new syntax first. It happened with `GoalPursuit` (#409): it parsed, compiled
  and ran, the full suite was green, and `fmt` died with a raw traceback, because
  the formatter tests are per-node *examples* and a node with no example has no
  test.

  Now every AST node must be either handled by `format_stmt` or named in an
  explicit `NOT_STATEMENTS` list with a reason, and the test names any node that
  is neither. The exclusions are checked too: a stale name fails, and
  `ActionStmt`'s excuse — that `format_expr` handles it — is verified rather than
  trusted. **The bug above was found by writing this guard.**

- **#405: a derived VM no longer sheds the sandbox it was derived from.** Found by
  sweeping every site that builds a VM from another, after the same bug shape
  turned up three times in one day (#392, #399, and the capability policy's own
  first version): **a check that lives on one path while a sibling path bypasses
  it.**

  Two sites were losing authority, neither related to the policy work:

  | Site | Was |
  |---|---|
  | `VM._resume_target_vm` | lost **7 of 8** — `allowed_paths` jail → `None`, `allow_subprocess` `False` → `True`, plus commands/hosts/env/network |
  | DAP `evaluate` | carried `allowed_paths` only — the debug console could shell out of a jailed program |

  `_resume_target_vm` builds the child used when resuming a run **this VM did not
  create**, which is the ordinary cross-process durable-workflow case. It was
  inheriting `host_globals`, `memory_store`, the worker dispatcher and the
  builtins — and none of the sandbox.

  Authority is now one list (`AUTHORITY_ATTRIBUTES`) copied by one helper
  (`inherit_authority`) at all four derivation sites, and
  `tests/test_vm_authority_inheritance.py` reads the sandbox arguments **out of
  `VM.__init__`'s signature** and fails when one is not in that list — so a new
  sandbox knob cannot be added without every derived VM inheriting it. Covered in
  both CLI and embedded mode, per the security-boundary rule.

- **#399: cross-process resume works for a script that reads the `run_workflow`
  result — the shape every guide example uses.** Resume in a fresh process
  rebuilds the graph by re-executing the module, during which
  `run_workflow`/`run_goal` are replaced by an index-safe placeholder result. The
  placeholder was missing `status`, `wait`, `retry` and `error` — precisely the
  keys a result carries when a run **defers**, which is the only kind of run
  anyone resumes. So `let r = run_workflow(w)` followed by `r["status"]` raised
  `Missing map key` during every rebuild.

  The placeholder now carries every key a real result can. A test generates each
  shape `run_task_graph` actually returns — completed, waiting, retry_scheduled,
  failed, goal — and requires the placeholder to cover all of them, so adding a
  result key without adding it there fails the suite instead of breaking resume
  in the field.

- **#399: a failed rebuild says why, instead of `Unknown graph`.** The rebuild
  swallowed every exception (`except Exception: return None`) and the caller
  turned `None` into `Unknown graph` — reported for a run the store lists as
  waiting, whose state file is on disk. The diagnosis was discarded, which is why
  this survived releases.

  ```
  # before
  {"ok": false, "error": "Unknown graph"}

  # after
  {"ok": false, "error": "Could not rebuild run 'g_80613ca6': re-executing the
   module to rebuild 'w' failed: LangRuntimeError: module top level ran a second
   time", "graph_id": "g_80613ca6", "category": "workflow_rebuild_failed"}
  ```

  New `WorkflowRebuildError` distinguishes the four ways a rebuild can fail from
  "this graph_id is genuinely unknown". `rehydrate_run` records the reason on the
  run record, which is the only place it survives for a sweeper.

  **Known issue, unchanged by this release:** module top level still re-executes
  once per resume, so side effects there repeat — on completed runs too.
  `docs/guide/workflows-and-tasks.md §8` now documents this and says to keep top
  level side-effect-free or use `@exactly_once`. Deciding whether to rebuild
  definitions without a full re-execution is still open on #399.

- **#392: step-level `with { retries: N }` is honoured on every entry point.**
  #226's fix lived in a wrapper — an `inline_retries=True` loop in
  `run_workflow_code`, passed by one caller (`nodus workflow-run`). The default
  was `False`, so the other four entry points made one attempt, dropped the
  scheduled retry, and reported success. Through `NodusRuntime.run_source` — the
  path `nodus-mcp-server` and embedding hosts use — that meant `ok: True`,
  `failed: []`, and a declared retry policy that never ran.

  A deferred retry is only correct if something will resume it, so the runtime
  now asks that directly instead of taking a caller's word for it.
  `run_task_graph` defers only when both hold: the run is durably tracked (a
  `workflow` or `goal`, which the workflow framework registers in its store — a
  bare `run_graph([...])` is registered nowhere, so deferring one would lose it),
  and a sweeper is registered on the runner owning that store. `RuntimeService`
  registers on its own runner for its lifetime and withdraws in `close()`;
  registration is per-runner, not per-process, so a service sweeping one
  project's store does not change retry behaviour for a run in another.

  With no sweeper — CLI, embedding, in-language `run_workflow`/`run_goal` — the
  retry happens in-process and the run finishes before returning. Exhausted
  retries still report `failed`, so the honest outcome is preserved in both
  directions.

  ```python
  # same script, same NodusRuntime, before → after
  # step flaky with { retries: 2, retry_delay_ms: 1 }
  ok: True   stdout: "attempt 1"                          # retry silently dropped
  ok: True   stdout: "attempt 1\nattempt 2\nattempt 3"    # policy honoured
  ```

  The deferred path is unchanged under a running service, and is now reachable
  by goals as well (#393).

### Performance

- **#398: independent steps that call agents now run concurrently.** `plan_graph`
  identified the concurrent steps and `ready_tasks()` returned them together, and
  then they executed strictly serially, because `action agent` was wired to the
  synchronous `agent_call`. Measured, two 1-second agent calls in two independent
  steps:

  ```
  before   2.44s   handler overlap -0.01s  (serial)
  after    1.15s   handler overlap +1.01s  (parallel)
  ```

  `action agent` now dispatches the handler off the scheduler thread and suspends
  the step until it lands — the mechanism `agent_call_async` has used since #294.

  **The cause was not what the issue said**, which is why the fix is small. #398
  reported that the async path was unavailable inside a workflow step because "a
  workflow step **is** a graph context" and graph contexts cannot yield. They can:
  `spawn_task` runs a step body *as a scheduler coroutine*, so calling
  `agent_call_async` from inside a step already overlapped. Only the wiring was
  missing.

  **Behaviour change worth naming:** agent handlers for independent steps may now
  execute on overlapping threads. A handler that was implicitly relying on being
  called one at a time needs to be thread-safe. `action tool` is unchanged and
  still serial.

  Paired `goal_action_start`/`_complete` events are preserved, and the completion
  is emitted when the handler finishes rather than when the call suspends — the
  naive wiring emits it at suspend time carrying the suspension marker, and three
  tests guard against exactly that.


## [4.2.0] - 2026-08-15

### Known issues

Found by Gate 10 pre-publish creator validation against the built wheel
(`docs/evals/v4.2.0/CREATOR_VALIDATION.md`). Both are long-standing limitations
rather than regressions, and both fail at compile time — no silent wrong answers.

- **`try { } finally { }` without `catch` is a syntax error** (#415). `catch` is
  mandatory, so cleanup-without-handling must be written
  `catch e { throw e }` + `finally` — which routes it through the re-throw path
  that this release fixes (#361).
- **A closure inside a loop body at module top level cannot capture that body's
  variables** (#416). The same loop inside a function works, with correct
  per-iteration binding. The error is `Undefined variable: <name>` for a variable
  declared on the line above.

### Changed — breaking for anything parsing stderr

- **#342: every error now reports the resolved absolute path.** Runtime errors
  already did; syntax errors echoed the path exactly as typed, so the same
  command printed two conventions depending on which phase failed. `run` and
  `check` now agree, and so does the fallback used by errors that carry no path
  of their own (a sandbox limit).

  ```
  # before, same directory, same invocation style
  Name error at /abs/path/err.nd:2:7: Undefined variable: y
  Syntax error at err.nd:1:9: Unexpected '=' in expression

  # after
  Syntax error at /abs/path/err.nd:1:9: Unexpected '=' in expression
  ```

  **This breaks stderr consumers that pass a relative path and expect that exact
  string back.** Checked before landing: the VS Code extension passes
  `document.uri.fsPath`, already absolute, so its diagnostic regex is unaffected.

  `nodus check <file>` still echoes the given path in its `: OK` line — that is
  not an error location.

### Fixes

- **#376: a background sweeper hijacked workflow runs it did not own, a store
  write could fail on Windows, and resuming timed out on its own bookkeeping.**
  Four causes behind one intermittent failure whose signature was a resume
  returning `ok: true` with the result keys missing. Three are below; the fourth
  was unbounded store growth, entered separately under #380.

  - **A `RuntimeService` sweeper adopted every non-terminal run in the store**,
    every 500ms, including runs it never created. Rehydration is not read-only:
    it calls `register_graph()`/`register_graph_vm()`, which replace the
    process-global registry entry for a run and bind it to the sweeper's own
    throwaway VM. Landing that on a run another participant is mid-way through
    hands them a graph pointed at the wrong VM. `rehydrate_run()` now claims the
    run first — `resume_workflow()` always did — and `sweep()` takes
    `min_idle_ms` so a run touched moments ago is not treated as abandoned.
  - **`LocalWorkflowStore.list_runs()` scanned without the store lock**, so a
    scan could hold a run file open while another thread replaced it. On Windows
    `os.replace` onto an open path fails with `[WinError 5] Access is denied` and
    the record is lost; POSIX permits it, which is why this never appeared in
    CI. Reads take the lock, and the replace retries briefly for handles held by
    scanners or indexers.
  - **Resuming ran under a 200ms wall-clock budget** (`EXECUTION_TIMEOUT_MS`),
    sized for running a script. A resume first reads state and checkpoint from
    disk and rebuilds the graph — recompiling the stored workflow source — before
    any step executes, all charged to that budget. New `RESUME_TIMEOUT_MS` (30s)
    covers the resume paths; nothing else changes.

  All three are user-facing correctness bugs, not test-only flakiness: a host
  doing run-then-resume under concurrent load could hit any of them, and the
  failure presented as `ok: true`, so the caller had no way to detect it.

  **Known issue.** #376 is closed and downgraded from release blocker, but not
  claimed as proven-zero: the flake rate on the affected tests fell from roughly
  6-in-10 to 2-in-20 and a full suite run reached zero failures for the first
  time this cycle. The residual failures name a different test each run, which
  suggests several small independent races rather than one remaining cause. All
  four causes trace to the same root — workflow state is process-global with no
  owner, so any two participants in a process share a store, a graph registry
  and a sweeper. That refactor is tracked separately as **#390**; it needs the
  VM to resolve the runner from execution context rather than module state, the
  same shape as #339, so it is design work rather than another patch.

- **#106: the DAP debug console could not see a function's own locals.** The
  `evaluate` request has existed since 2026-06-06 and works — for module
  globals. `DebugSession.get_locals()` read `frame.locals`, but since v0.8 that
  dict holds only parameters and captured cells: every `let` inside a function
  lives in the slot-indexed `frame.locals_array`. So at a breakpoint inside

  ```nd
  fn add(a, b) {
      let total = a + b
      return total          // <- paused here
  }
  ```

  evaluating `total` returned `Undefined variable: total`, which is the case a
  debug console is for.

  Two other copies of the same logic — `_collect_frames()` in the same file, and
  the CLI debugger's `get_locals()` — already merged both sources, so the
  Variables pane and `nodus debug` were correct. This was the copy that drifted.
  It now delegates to the CLI debugger's, and `evaluate` honours the `frameId`
  the client sends, so evaluating against a selected caller frame works too.

  The issue is closed as originally scoped — `evaluate` was implemented and the
  issue was stale — but it was only half-verified: every existing test used a
  module-level `let`, which passes on globals alone. Added tests for a function
  local and for evaluation being read-only against the paused program.

- **#342: a syntax error in an imported module named the wrong file.** Not in
  the issue as filed, and the more serious half. Syntax errors carried no path,
  so the reporter fell back to the path the CLI was given — printing the **entry
  file's** name against the **module's** line and column:

  ```
  $ nodus run main.nd            # the error is in sub/bad.nd
  Syntax error at main.nd:1:25: Unexpected '=' in expression
  ```

  `main.nd:1:25` exists and sits inside the import string, so the report looks
  plausible while pointing at a file that does not contain the error.
  `ModuleLoader._parse_module` now stamps the module being parsed onto the error.

  Regression tests: `tests/test_error_path_convention.py` (9 tests, 6 failing
  before the fix), including one that reads the reported line and column out of
  the file the error *names* — reading them out of the file the test expects
  would pass either way, since the position was always the module's.

- **#348: `--trace-imports` printed nothing once the bytecode cache was warm.**
  `ModuleLoader._build_metadata()` returns early on an on-disk cache hit, and
  `resolve_import()` — the only site that emits the trace — sits after that
  return. The flag therefore worked only on the first run after `rm -rf .nodus`,
  which is the run you are least likely to be debugging.

  The early-return path now replays the imports the cached unit recorded,
  including transitive ones, marked so the provenance is visible:

  ```
  [import] Resolved (from bytecode cache) "./helper" -> /abs/path/helper.nd
  ```

  Nothing is re-resolved and nothing is re-parsed — a debug flag must not change
  what a run does, only what it reports, and a test asserts stdout and exit code
  are identical with and without it.

  Distinct from issue 51 (the in-memory cache within a single run), which
  remains fixed. Regression tests run the CLI twice
  (`tests/test_import_trace_warm_cache.py`, 8 tests): a cross-run bug is
  invisible to any test that looks at a single run.

- **#339: `std:async.worker_pool` and `pipeline` never ran their workers.** The
  other half of ASYNC-MOD-003 — `parallel` and `series` were fixed in 4.1.1.
  These two spawn coroutines *inside* the module and hand a channel back for the
  caller to drive; the coroutines landed on the detached module VM's scheduler,
  which nothing ever runs, so every job was silently dropped. No error, no
  output, `ok: True`.

  Two halves, each useless alone:

  1. A module VM shares the caller's scheduler, so spawned work is queued where
     the caller's `run_loop()` will find it.
  2. **A coroutine is resumed on the VM that spawned it**, not on the
     scheduler's own VM. Builtins close over the VM that registered them, so
     resuming module coroutines on the caller's VM hands them the wrong
     `recv`/`send` and the wrong `current_coroutine` — which is what an earlier
     attempt at (1) alone ran into.

  A worker or stage may now also **suspend**: previously a worker calling
  `async.sleep` died with `Task yielded during graph execution`, because a
  closure from the caller was invoked through `run_closure` — a nested execute
  loop with nowhere to put a yield. `_try_enter_foreign_closure` pushes a frame
  with the closure's origin context instead, keeping it in the current
  coroutine's loop, so callbacks suspend and interleave like any other code.

  This was never specific to `std:async`: any `.nd` module that spawned a
  coroutine and returned a channel had the same hole, and that case is covered
  by a test.

  Regression tests: `tests/test_async_worker_pool_pipeline.py` (11 tests, CLI
  **and** embedded, since the two modes failed differently). 9 of the 11 fail
  against the unfixed VM; the other two are `parallel`/`series` guards.

  Not fixed: issue 157 — a library still cannot return a value from a coroutine
  it spawned. That remains the open design question.

- **#49: `nodus run` printed all 10,000 frames of a stack-overflow trace.**
  1,500,317 bytes of stderr across 10,003 lines — larger than the ~800 KB in the
  original report, because stack entries gained absolute paths (issue 342) and
  every line grew. The same program now produces 23 lines / 3,195 bytes.

  The 20-frame cap had been implemented, and this issue closed on that evidence
  — but in only one of two stack-trace formatters. `runtime/diagnostics.py`
  capped; `runtime/errors.py` joined every frame, and the CLI renders through the
  latter. Measured on the unfixed tree, the same 10,001-frame stack rendered as
  803 bytes through one and 370,075 through the other.

  Both now call `diagnostics.format_stack_section`. Only the rendered text is
  capped: `err.stack` and an error payload's `stack` field still carry every
  frame, so embedders can slice their own way (see `docs/guide/debugging.md` §9).

  `tests/test_stack_trace_cap.py` (8 tests) asserts the rendered line count and
  byte size rather than the error message — a message-only test was blind to this
  bug, which is why it survived being "fixed" — and asserts that both formatters
  produce a byte-identical stack section, so a cap added to one and not the other
  fails.

- **#353 (and #345): `--help` ran the command instead of printing usage.**
  `--help` was each subcommand's own responsibility, so every new subcommand
  shipped unguarded and the fixes landed one at a time — issues 1 and 2
  (`check`, `ast`, `dis`), then issue 268 (`serve`, `worker`), then #345
  (`test`), and now the whole package-manager group. On v4.1.1:

  ```
  $ nodus logout --help
  Token removed from ~/.nodus/config.toml     # it performed the logout
  ```

  `publish --help` crashed with an unhandled `FileNotFoundError` traceback,
  `login --help` blocked on stdin, and `install` / `add` / `remove` / `update` /
  `deps` / `test` all executed. `--help` must never mutate state.

  `main()` now handles `--help`/`-h` centrally, before any subcommand body runs,
  and the ten per-command guards are gone — one place to get it right, and the
  next subcommand is correct by default. Every command in `KNOWN_COMMANDS` exits
  0 with usage on stdout.

  Added help text for `test`, `install`, `update`, `add`, `remove`, `deps`,
  `cache`, `login`, `logout`, `publish`, `ast` and `dis`. Commands without a
  hand-written entry fall back to usage derived from `nodus --help`, so the
  fallback cannot drift from the command list.

  `KNOWN_COMMANDS` is module-level so `tests/test_cli_help_guard.py` (11 tests)
  can be table-driven over the registry rather than one case per command — a
  subcommand added tomorrow is covered without anyone remembering. The sweep runs
  out of process with a timeout: against the unfixed CLI `login --help` blocks on
  input even with stdin at `/dev/null`, so an in-process table test would hang the
  suite instead of failing it.

- **#350: `NodusRuntime` applied no call-depth cap, contradicting its own
  docstring.** `configure_vm_limits()` installs `MAX_STACK_DEPTH` (10,000) — and
  `embedding.py` then overwrote it unconditionally with `self.max_frames`, `None`
  by default, which means *no cap*. With the default `max_steps` a runaway
  recursion still died on the step limit, so the hole only showed in the
  configuration `EMBEDDING.md` recommends for long-lived hosts:

  ```python
  rt = NodusRuntime(max_steps=None, timeout_ms=None)   # no step limit, no deadline…
  rt.run_source("fn f(n) { return f(n + 1i) }\nf(0i)")  # …and no frame cap either
  ```

  That grew the frame stack until the process was killed — VM frames are
  heap-allocated, so Python's own recursion limit never fires. It now raises
  `Call stack overflow` in 0.2s. The assignment is conditional on the caller
  having passed a value, so the default lives in exactly one place and the CLI
  and embedded paths cannot drift apart again. The CLI was never affected.

  **Behavior change:** an embedded run that recursed deeper than 10,000 frames
  previously succeeded and now raises. Pass an explicit `max_frames` to raise the
  ceiling — there is deliberately no "unlimited" setting, since this is the only
  guard left when `max_steps` and `timeout_ms` are both `None`.

  Regression tests: `tests/test_max_frames_default.py` (9 tests, embedded **and**
  CLI per the security-boundary rule). The 4 covering the embedded default fail
  against the unfixed code. The recursion cases run in subprocesses with timeouts
  on purpose: an uncapped run does not raise, it grows, so an in-process test
  would hang CI rather than fail it.

- **#361: `finally` was skipped when `catch` re-threw** — the one exit path where
  cleanup matters most. `handle_exception` leaves a finally-gate on the handler
  stack while a `catch` block runs, so a `return` inside the catch defers to the
  `finally`. An exception raised by that catch hit the same gate and *skipped* it,
  so the error propagated outward with the `finally` never run:

  ```nd
  fn f() {
      try { throw "boom" }
      catch e { print("A caught"); throw e }
      finally { print("B finally") }   // never ran
  }
  ```

  The gate now defers the exception the way `RETURN` defers a return: unwind to
  the catch's depths, jump into the `finally`, and resume propagation at
  `FINALLY_END`. All five exit paths run `finally` exactly once. An exception
  raised by the `finally` itself supersedes a pending re-throw or return.

- **#370: a `return` deferred to a `finally` that then raised was applied by an
  unrelated `finally` later.** The pending return lived in a single VM-wide slot
  cleared only by `FINALLY_END`. If the `finally` raised instead of completing,
  the return stayed pending and the next `FINALLY_END` anywhere in the program
  acted on it — at module level that surfaced as the internal error
  `FINALLY_END deferred return outside function`. Deferred state is now discarded
  when an exception escapes the region that owes it, identified by the
  handler-stack depth recorded at deferral. An error raised *and caught* inside
  the `finally` leaves the region intact and the return still lands.

- **#371: deferred state was VM-wide, not per-coroutine.** `stack`, `frames` and
  `handler_stack` are all saved per coroutine; the deferred return was not. Two
  coroutines suspended inside a `finally` consumed each other's pending action —
  the first to resume returned the other's value, and the second returned `nil`.
  The deferred return and the new deferred re-throw now travel on the `Coroutine`
  alongside `handler_stack`, through `save_current_coroutine_state`,
  `load_coroutine_context` and `save_execution_context`. The `DEFERRED_NONE`
  sentinel moved to `runtime/coroutine.py`, since `None` cannot mean "nothing
  pending" when a function may defer a return of nil.

  Regression tests: `tests/test_finally_rethrow.py` (14 tests, CLI **and**
  embedded for every case, asserting ordered output rather than membership).
  12 of the 14 fail against the unfixed VM.

  `tests/test_finally_after_catch_return.py::test_finally_runs_when_inner_error_propagates`
  — the test written for exactly this path — printed the same marker from its
  `catch` and its `finally` and asserted membership, so the catch alone satisfied
  it and it could not fail. It now asserts the ordered sequence.
  `tests/test_finally.py::test_exception_from_outer_try_still_caught` asserted the
  buggy output (no `finally` line) as expected behavior; corrected.

### Performance

- **#380 (part 2): `LocalWorkflowStore` scans got 4x cheaper, and the sweep 11x.**
  Listing runs cost ~1.3 ms per file, and a background sweeper calls it on a
  timer, so an accumulated store slowed everything touching workflow state.

  | files | `list_runs()` before | after | `expire_wait_timeouts()` before | after |
  |------:|--------------------:|------:|-------------------------------:|------:|
  | 300 | 304 ms | **60 ms** | — | 48 ms |
  | 3,000 | 3,223 ms | **863 ms** | 6,600 ms | **579 ms** |
  | 10,000 | 13,459 ms | 3,840 ms | — | 2,591 ms |

  It was never the parsing. Profiling 3,000 records put 1.7 s of 4.2 s in
  `nt.mkdir` — `_runs_root()` re-created the store's own directory on every call,
  and `_run_path()` calls it once per record, so listing 3,000 runs issued 6,000
  mkdir syscalls — and 1.6 s in `nt.stat`, from an `os.path.exists` before an
  `open` that already reports a missing file (also a race: the file could vanish
  between the two). `expire_wait_timeouts()` additionally re-read every record it
  had just been handed, for every run rather than only the waiting ones.

  New opt-in `max_terminal_runs` caps how many finished runs are kept, oldest
  deleted first. **Off by default**: run records are history a host may rely on,
  and silently deleting them is not a decision the store should make on anyone's
  behalf. Live runs are never pruned.

  Regression tests assert the *syscall behaviour* rather than elapsed time — a
  timing assertion would be flaky on shared CI and would not say which of the
  three regressed (`tests/test_workflow_store_scan_cost.py`, 10 tests).

### Tooling

- **Known issues recorded from an external architecture audit — two of them
  affect embedded hosts.** An outside adversarial audit of v4.1.1 was verified
  against the implementation; findings, verdicts and the audit's own five factual
  errors are in `docs/governance/EXTERNAL_AUDIT_LEDGER.md`. Nothing is fixed yet.
  What a host should know now:

  - Step-level `with { retries: N }` is honoured only by `nodus workflow-run`.
    Through `NodusRuntime` or an in-language `run_workflow()`, the step runs once
    and the call returns **`ok: true`** with the retry silently dropped (#392).
  - `goal` and `workflow` are not interchangeable, despite lowering through the
    same function. A `goal` retries in-process; a `workflow` defers. Their result
    maps also differ in key set, so `result["status"]` works for one and errors on
    the other (#393). The retry path will be unified.

  Also recorded: step ordering is a strong default rather than an unbypassable
  invariant (#394), there is no cancellation anywhere (#395), and `nodus check`
  does not catch dependency cycles (#396).

  A second audit of the same commit by a different auditor added five more, two of
  which affect anyone running workflows:

  - `action agent` runs synchronously, so workflow steps the dependency graph
    identifies as concurrent execute serially — two 1s agent calls take 2.7s
    (#398).
  - Cross-process resume fails with `Unknown graph` whenever the script reads the
    value `run_workflow` returns, which is how the guide examples are written; and
    every failed attempt re-runs the module's top-level side effects (#399).

  Also: `nodus graph` executes the file it is asked to inspect (#400), the
  analyzer never enters workflow step bodies (#401), and channels have no
  backpressure (#402).

  A third audit of the same commit added the capability finding below, and one
  claim that verification retracted:

  - **`workflow_wait` behaves as documented.** #404 was filed against it and is
    **closed as invalid** — a waiting step completing with `nil` is the design, and
    the resumed value reaches later steps through `workflow_resume_payload()`, per
    `docs/guide/real-world-integration.md`. No code changed.
    `tests/test_workflow_wait_resume.py` now pins that contract, including the
    case that reads the dependency value instead and gets `nil`.
  - **The host-function chokepoint performs no authorisation** —
    `register_function` takes no permission metadata and the capability defaults
    are permissive (#405). All three audits independently name this the
    highest-leverage change available.

- **The doc gate's closed-issues phase penalised honest changelog prose, and
  timed out on its own slowest regression test.** Two fixes to
  `tools/nodus_gate/closed_issues_phase.py`, both found by running it against
  this release's own `[Unreleased]` section.

  - It scanned every `#N` in the section, including references inside an entry's
    prose, and demanded a passing regression test for each. An entry that names a
    known issue or the follow-up tracking a root cause is doing the right thing —
    but doing it made the gate fail, which is an incentive to write a worse
    changelog. It now reads issue references from entry lines only; a claim needs
    a test, a cross-reference does not.
  - Its per-test budget was 60s. The #348 suite runs the real CLI in a subprocess
    eight times and takes ~41s unloaded, so it had 1.4x headroom and timed out
    under gate load — reported as a failing regression test with nothing
    regressed. Raised to 300s, which is the 5-10x the repo's own flaky-test rule
    asks for.

- **#357: the VS Code grammar did not highlight `match`, `break` or
  `continue`.** They shipped in v4.1.0 and rendered as plain identifiers, so a
  reader following the Control Flow docs sees their `match` expression
  un-highlighted and reasonably concludes the syntax is not real yet — on the
  most externally visible surface the language has.

  They are *contextual* keywords: recognised by the parser from identifier
  tokens rather than reserved by the lexer, so they existed only as string
  literals at two `if` statements in `parser.py` and nowhere a tool could read.
  `nodus.frontend.lexer` now exports `ALL_KEYWORDS` (with
  `CONTEXTUAL_KEYWORDS`, `LOOP_CONTROL_KEYWORDS` and `EXPRESSION_KEYWORDS`), and
  the parser reads its recognition sets from them, so the list cannot drift from
  what the parser accepts.

  `tests/test_keyword_coverage.py` holds both ends: the parser accepts every
  contextual keyword the list names, and the shipped grammar highlights every
  keyword in the list. The grammar check needs the `nodus-vscode` checkout, so it
  skips in CI and runs for whoever publishes — recorded as Gate 3b in
  `RELEASE_GATES.md` rather than left to memory.

  The duplicate grammar under `tools/vscode/` is **removed**. The two copies had
  diverged with neither a superset of the other, and the in-repo one was missing
  17 of the language's 31 keywords. `nodus-vscode` is now the only grammar.

  The extension fix is prepared as **nodus-vscode v0.1.1** and needs a Marketplace
  republish, which is a manual upload.

- **#380 (part 1): the test suite and doc gate no longer leave workflow-run
  files in the repo.** The default workflow store root is CWD-relative, so
  anything running a workflow from the repo root wrote into
  `.nodus/workflow_framework/runs/`. Retention is 30 days, so nothing was ever
  cleaned; the directory reached 299 files.

  That matters because `LocalWorkflowStore.list_runs()` parses every file on
  every call — ~1.3 ms each, measured linear to 10,000 files (13.5 s). At 299
  files a single scan costs **540 ms**, past the 500 ms sweep interval
  deadline-sensitive tests assume. The suite was degrading its own later runs,
  surfacing as unrelated-looking flakes that passed on re-run: a server endpoint
  test, a doc-gate block, and a scheduler fairness test, all from one cause.

  A session fixture now removes what a pytest run added, and the gate's runtime
  phase runs doc blocks against a throwaway store. Cleanup rather than
  redirection, because several tests build a project directory, chdir into it,
  and assert the default runner wrote under *that* root — pointing the default
  elsewhere broke 26 of them, and their behavior is the documented one.

  `NODUS_WORKFLOW_STORE_ROOT` now overrides the default store root, for hosts
  whose working directory is read-only or ephemeral.

  Corrected in `CLAUDE.md` and `test_task_graph.py`: both said "670+ files cause
  >2s per sweep", which understates it about 2x in the direction that matters.

  Bounding the store's cost — pruning by count, or an index instead of a full
  rescan — remains open in #380.

- **#366: the opcode freeze is now enforced by a gate instead of by prose.**
  `tools/nodus_gate/opcode_phase.py` adds a `--opcodes` phase (included in
  `--all`, which CI runs). It reads the dispatch table out of a constructed `VM`
  — not a regex over `vm.py` — and requires every record of the instruction set
  to agree: `BYTECODE_REFERENCE.md` §3, its appendix quick table, and the
  `FREEZE_PROPOSAL.md` stability tables must name exactly the same opcodes;
  removed opcodes must stay out of the dispatch table; the compiler must not be
  able to emit an opcode with no handler; and the opcode counts and
  `BYTECODE_VERSION` asserted in those documents must match the live values.

  The freeze had been declared at v1.0 and checked by nobody, which is how `MOD`
  and `RESET_LOCAL_IDX` were added post-freeze without any of the three mandatory
  steps and went unnoticed until the 2026-08-07 doc sweep — about two and a half
  months and two months later. Run against the tree as it stood before that
  sweep, the new phase reports both as undocumented.

  `BYTECODE_VERSION` stays at **4** by explicit decision — bumping it now would
  invalidate every cached bytecode file in the field to close a window that has
  already passed for anyone on current 4.x. Recorded in the `FREEZE_PROPOSAL.md`
  amendment.

  Fixed the drift the new phase found: five opcodes missing from the
  `BYTECODE_REFERENCE.md` appendix table (`FRAME_SIZE`, `LOAD_LOCAL_IDX`,
  `STORE_LOCAL_IDX`, `RESET_LOCAL_IDX`, `MOD`) and stale counts of 47 in
  `BYTECODE_REFERENCE.md`, `FREEZE_PROPOSAL.md`, `INSTRUCTION_SEMANTICS.md`,
  `ARCHITECTURE_ANALYSIS.md`, and `LANGUAGE_STABILITY_INDEX.md`.

## [4.1.1] - 2026-08-05

### Fixes

- **ASYNC-MOD-003 (#339): closures passed to a module function inside a container
  ran against the wrong bytecode.** A module function is dispatched in a detached
  VM whose `code` is the module's. `invoke_function` wrapped top-level `Closure`
  arguments in a `_ClosureProxy` so they dispatch back through the caller — but a
  closure nested inside a **list, map, or record** was never wrapped, so its
  `fn.addr` (an index into the *caller's* bytecode) was executed against the
  *module's* instructions. Under the CLI this raised `Stack underflow` or
  `'NoneType' object is not subscriptable`; under `NodusRuntime` it was worse — the
  task body silently never ran and `ok` was still `True`.

  This broke every library, not just the stdlib: any `.nd` module taking a list of
  callbacks was affected (`fn call_nested(fns) { return fns[0]() }` → `Stack
  underflow`).

  The fix identifies a foreign closure by `FunctionInfo` identity against the
  module's own `functions` table (which includes mangled anonymous entries such as
  `__anon_1__fn2`) and routes it back through the caller VM at three points:
  `CALL_VALUE` dispatch, `coroutine()` creation, and `spawn()`. Coroutines now pin
  the context their closure was compiled against at creation time rather than
  inheriting the spawning VM's.

  `std:async.parallel` and `std:async.series` work as documented as a result,
  including with pre-built coroutines and with tasks that `sleep()` — a sleeping
  task suspends and the others continue, rather than blocking. Regression tests:
  `tests/test_async_module_boundary.py` (12 tests, CLI **and** embedded for each
  behavior, since the two modes failed differently).

  `_caller_vm` is now initialized in `VM.__init__` so the `CALL_VALUE` hot path is
  a plain attribute read; without that, the added check cost ~1s of CLI startup.

### Known bugs

- **`std:async.worker_pool` and `std:async.pipeline` are still broken**
  ([issue 339](https://github.com/Masterplanner25/Nodus/issues/339) remains open for
  these two). Both spawn coroutines inside the module and return a channel for the
  caller to drive; those coroutines land on the detached VM's own scheduler, which
  nothing runs, so work is silently dropped. Sharing the caller's scheduler is not
  sufficient — builtins close over the VM that registered them, so resuming a
  module coroutine on the caller VM installs the wrong builtins. Fixing it needs
  VM-agnostic builtins, tracked with the design gap in
  [issue 157](https://github.com/Masterplanner25/Nodus/issues/157). The guide
  documents an inline workaround.

### Documentation

- **Doc sweep against the shipped 4.1.0 surface.** Re-pointed every `4.0.8` version
  claim (README, `llms.txt`, `llms-full.txt`, `CLAUDE.md`, the Claude and Codex
  skills) and reconciled the companion-package count, which read 29 / 33 / 35 in
  different files, against PyPI: **32 companion packages, 33 projects including
  `nodus-lang`**.
- **Corrected stdlib documentation errors:** `std:string` → `std:strings` (the
  singular form does not exist); `std:time` no longer documented as having
  `now_ms()` or `sleep()` (the latter is in `std:async`); `std:math` no longer
  claimed to provide trig functions; `std:async` signatures corrected
  (`queue()` takes no arguments, `worker_pool(worker, count)`, `parallel`/`series`
  return nil rather than a list of results).
- **`break`, `continue`, and `match` documented in the AI-assistant assets.** Both
  skills still stated "No `break` or `continue`" and the Claude skill's operator
  table contradicted itself on `+=`. README, `llms-full.txt`, and both skills now
  cover the 4.1.0 control-flow surface, including the two compile-time errors
  (`'break' outside a loop`, `'break' cannot cross a try/catch/finally boundary`).
- **README:** added the missing stdlib modules (`std:collections`, `std:path`,
  `std:env`, `std:utils`, `std:runtime`, `std:async`, `std:tools`/`std:agent`),
  documented the `[http]`/`[schema]`/`[retry]` extras alongside `[server]`, noted
  that `std:http` requires the `[http]` extra, and linked the user guide,
  standard-library reference, embedding guide, and ecosystem guide.
- **`llms.txt`:** removed a link to `docs/guide/build-a-library.md`, a page that was
  never written and had been advertised to AI crawlers since the discoverability
  commit.
- **`docs/guide/ecosystem.md`:** added the missing `nodus-jupyter` and
  `nodus-mcp-server` entries.
- **`.nodusgate-allow`:** re-pointed 8 line-number suppressions whose blocks moved.
  Gate verified green afterward (static 132/132, runtime 229/229).

## [4.1.0] - 2026-07-10

### Language

- **`break` and `continue` loop control (#309):** Both statements are now
  implemented for `while`, C-style `for`, and `for … in` loops, replacing the
  prior flag-variable workaround. `break` exits the innermost loop; `continue`
  skips to the next iteration (and, in a `for` loop, still runs the increment,
  matching C semantics). A `foreach`'s live iterator is popped when breaking so
  code after the loop runs on a clean stack. Both are compile-time errors
  outside a loop, or when they would jump out across a `try`/`catch`/`finally`
  boundary (which would strand the runtime's exception-handler stack) — a loop
  wholly *inside* a `try` still allows `break`/`continue`. No new opcodes;
  BYTECODE_VERSION is unchanged.
- **`match` expression for value dispatch (#308):** A `match` expression
  dispatches on a scrutinee against value-matching arms, replacing stacked
  `if/else` chains at every tag-dispatch site (the canonical tree-walking
  evaluator pattern). Arms use `pattern => body`; the body is an expression, a
  `{ … }` block (its final expression is the arm's value), or a bare
  `throw`/`return`. `_` is the catch-all and must be the last arm. Arms compare
  with `==` and the first match wins; a scrutinee that matches no arm and has no
  `_` raises at runtime. `match` is an expression, so it composes as a `let`
  RHS, a `return` value, a call argument, or nested inside another `match`.

  ```nodus
  fn classify(kind) {
      return match kind {
          "num" => "number",
          "bin" => "binary",
          _ => "unknown",
      }
  }
  print(classify("bin"))  // -> binary
  ```

  Value-matching only for now — no destructuring/binding patterns or
  exhaustiveness checking. Additive surface syntax (new `=>` token; `match` is a
  soft keyword); no new opcodes and BYTECODE_VERSION is unchanged.

### Enhancements

- **Async agent calls — `agent_call_async` / `agent.call_async` (#294):** New async
  variant of `agent_call` that runs the agent handler on a daemon thread and suspends
  the calling coroutine until it completes (the same thread + `_io_channels` +
  `ChannelRecvRequest` pattern as `http_*_async` / `subprocess_run_async`). Fanning
  agent calls out under `spawn()` now genuinely **overlaps** instead of serializing on
  the single cooperative scheduler thread — closing ASYNC-MOD-002. It falls back to the
  synchronous path when not called from inside a scheduler coroutine, and the
  `std:agent` module wrapper propagates the async yield (ASYNC-MOD-001). Timing
  regression tests added alongside the HTTP ones in
  `tests/test_async_concurrency_timing.py`.

- **Workflow/goal dependency cycles are rejected before the scheduler runs (#323):**
  A cyclic `after` graph (`step a after b` + `step b after a`) is now detected at
  graph-build time — the moment `run_workflow`/`run_goal` constructs the graph —
  instead of only after the scheduler drains with tasks stuck pending. The
  `workflow_error` record is unchanged (same `Dependency cycle detected: …` message,
  `cyclic_workflow` category, and cycle step list); only the timing moves earlier, so
  a runnable sibling step no longer executes before the cycle is reported (fail-fast,
  no partial execution). The post-drain check remains as a defensive backstop.

- **Structured errors now carry a source snippet + caret:** Every error dict
  returned by the runner (`run_source`/`check_source`/`build_ast`/`disassemble_source`)
  — and therefore the CLI, the internal HTTP API, and the four agent tools
  (`nodus_execute`/`nodus_check`/`nodus_ast`/`nodus_dis`) — now includes a
  `snippet` field: the offending source line plus a caret line pointing at the
  reported column. This closes the long-standing Phase 9 "maybe snippet" gap so
  an agent (or human) gets the source context needed for precise self-repair,
  not just line/column coordinates. The snippet resolver prefers the error's own
  file from disk (so errors inside imported modules render *their* line, not the
  entry file's) and falls back to the in-memory source for `<memory>`/REPL
  inputs; the caret prefix preserves tabs for correct alignment under
  tab-indented code and pads correctly for end-of-line/EOF columns. `snippet` is
  always present (value or `null`) for a stable dict contract, matching `stack`.

### Fixes

- **Async fan-out no longer builds a separate HTTP client per worker (#295):**
  `_get_or_create_client` had a check-then-set race — an async fan-out (N coroutines
  each calling `http_get_async`/`http.get_async`) starts N worker threads that all
  found no client yet and each built their own `httpx.Client` with a separate
  connection pool, so requests couldn't share connections and the fan-out serialised
  toward ~2×. Double-checked locking now creates exactly one shared client. Measured
  raw fan-out improved from ~2.2× to ~3.3× (6 × 300ms local GETs). A residual gap to
  full N× remains — a cooperative-scheduler/GIL interaction, documented as
  ASYNC-CAP-001 in TECH_DEBT and deferred. Deterministic regression test asserts a
  single shared client under an N-way fan-out.

- **Resume no longer re-executes the workflow during graph rebuild (#322):**
  `resume_workflow` rebuilds a graph by re-executing the workflow's source module
  (to re-bind its definitions and imports). For a self-invoking flow
  (`… let r = run_workflow(build)`) that re-ran the top-level `run_workflow`,
  spawning a **spurious fresh graph** (a new random `graph_id`) and re-running every
  step — duplicating side effects. The rebuild now suppresses top-level
  `run_workflow`/`run_goal` execution (they return a benign, index-safe empty result
  so top-level code reading the result doesn't crash), so resume reuses the original
  graph and resumes from the checkpoint correctly. Verified across the runner/CLI/HTTP
  resume paths; regression test in `tests/test_checkpoints.py` asserts no spurious
  graph is created on resume.

- **In-script `resume_workflow` no longer clobbers the calling script (#328):**
  The rebuild `reset_program`s its execution target, so calling `resume_workflow(…)`
  from inside a running `.nd` script used to replace that script's program — the
  statement after `resume_workflow(…)` never ran, and the rebuilt module's top-level
  output leaked into the resumed run. When a rebuild is required and the caller is
  running its own program, the resume now executes on a **dedicated child VM**
  (inheriting host functions, shared memory, event bus, and worker dispatcher), and
  the rebuild's throwaway stdout is suppressed. The graph-reuse path and the
  runner/CLI/HTTP paths (bare resume VM — nothing to clobber) are unchanged.

- **`nodus fmt` no longer corrupts `\r` / `\0` string escapes (#310):** The
  formatter decoded string-literal escapes and re-emitted only `\\`, `\n`, `\t`,
  and `"`; `\r`, `\0`, and other control code points were written back as raw
  control bytes, corrupting the file so it no longer parsed (`fmt --check` in CI
  then failed on a file the author never hand-broke). A single shared
  `escape_string_body()` helper — the full inverse of the lexer's escape set —
  now drives both re-emission sites (plain strings and interpolated-string
  literal parts), preferring named escapes and falling back to `\xHH` / `\uXXXX`
  for other non-printables. `fmt` output is also written with LF endings verbatim
  instead of being rewritten to CRLF on Windows, keeping the round-trip
  idempotent. Found while formatting the `examples/expr_compiler.nd` example.

### Docs / Tooling

- **The doc-vs-code gate now runs in CI (#302):** `python -m tools.nodus_gate.cli
  --all` (static / runtime / closed-issues / contracts) is executed on every push
  and PR, failing the build on non-zero exit. Previously CI only ran `nodus check`
  on two examples, so the gate could — and did (#293) — ship red across releases
  undetected. Also made the closed-issue tests path-portable (the gate now supplies
  both `src` and the repo root on `PYTHONPATH`; removed hardcoded local paths) so the
  gate runs cleanly on the Linux CI runner.

- **Workflow composition documented (#324):** `docs/guide/workflows-and-tasks.md`
  §9 now shows conditional routing and iteration by *composition* — control flow
  (`match`/`while`) selecting nested `run_workflow` calls, with two gate-run
  examples — and §11 is reframed from "no conditional steps" to "a single workflow
  is a static acyclic DAG; route/loop by composition." Both carry the durability
  caveat (composition executes and each sub-workflow checkpoints independently, but
  whole-flow resume re-runs nested workflows — #322). A matching idioms-reference
  entry was added.

- **Doc-vs-code gate restored to green (#293):** The mandatory `nodus_gate --all`
  gate had been shipping red since ~v4.0.7 — 21 runtime doc-block failures plus a
  contract-check failure. Two unrelated causes: (1) the doc-reformat pull requests
  273 and 276 shifted line numbers so `.nodusgate-allow` entries no longer matched their blocks,
  and a handful of examples had real errors; (2) `contracts_phase.py` still imported
  `HandlerContract`/`VALID_EFFECTS` from `nodus_schema`, a stale reference from before
  the NAME-COL-001 rename — that name now resolves to the standalone PyPI package,
  which has no such symbols. **Fixed real doc bugs:** `docs/runtime/RUNTIME.md` used
  the reserved word `record` as a variable; `docs/guide/standard-library.md`'s
  `std:time` example read a non-existent `now.unix` field (correct: `now.epoch_ms`)
  and used `"YYYY-MM-DD"` parse tokens (correct: `"yyyy-MM-dd"`);
  `docs/language/STYLE_GUIDE.md` showed unquoted `import std:strings` (correct:
  `import "std:strings" as strings`). **Re-pointed the allowlist** for the remaining
  17 intentionally-illustrative fragments (undefined context vars, paren-less
  control-flow demos, host-registered functions, error demos). **Pointed the contract
  check at `nodus_lang_schema`.** Gate now reports Static/Runtime/Closed-issues/
  Contracts all PASS (0 failures, 227/227 blocks, 6/6 contract checks).

---

## [4.0.8] - 2026-06-25

### Fixes

- **ASYNC-MOD-001 fix (stdlib async wrappers fell back to sync — #105):** Async builtins called through a `std:` module wrapper — `http.get_async()`, `subprocess.run_async()`/`shell_async()` via `import "std:http"` / `import "std:subprocess"` — silently executed **synchronously**, so fanning N of them out across coroutines ran serially instead of overlapping (the documented async fan-out lost its concurrency). Root cause: module functions were dispatched through `invoke_function`, which runs the wrapper in a detached VM whose `run_closure` cannot yield, so the async builtin's `ChannelRecvRequest` suspension could not propagate and a `current_task` guard fell back to the blocking path. (#105 was previously closed when only the *direct*-builtin path — `http_get_async(...)` — was fixed; the module-wrapper path it actually describes remained broken.) Fixed by dispatching a module function **in the calling VM** when it is invoked from inside a scheduler-managed coroutine: `_op_call_method` swaps the module's execution context onto a cross-module call frame (restored on frame pop in `_op_return`/`handle_exception`), so execution stays in the same coroutine and `execute()` loop and the yield propagates to the scheduler. The swapped context is tracked per-coroutine (`Coroutine.module_ctx` — captured at spawn, saved on suspend, restored on resume) and saved/restored around `resume`, so a coroutine suspended mid-cross-module call never leaks its context to another coroutine and re-entrant resumes (e.g. `test.flush_async` stepping tasks) are not clobbered. The `BuiltinMethod` call path now also propagates `SleepRequest`/`ChannelRecvRequest` sentinels, so `handle.wait_async()` is genuinely async. The async guards in `_do_async_request`/`_do_async_run` are deliberately kept so `run_closure`/graph contexts stay synchronous. Verified by a new timing regression test (`tests/test_async_concurrency_timing.py`): `http.get_async` fan-out now overlaps (~2x+ vs the prior serial baseline).

---

## [4.0.7] - 2026-06-21

### Fixes

- **REHYDRATE-001 fix (cross-process workflow resume dropped module imports — #285):** When a waiting workflow was resumed in a VM other than the original (live VM/graph evicted — e.g. a human approves later in a different process), `VM._rebuild_workflow_graph` recompiled the source with `ModuleLoader.compile_only`, which is import-blind: it emits bytecode but never resolves the workflow's `import` statements. The rebuilt VM ran with `tool`/`mem`/`json`/aliased stdlib imports unbound, so a post-wait step referencing them failed with `Undefined variable: <name>` — surfaced only in `spawned_errors` while the run still reported `ok: True` (resume silently no-op'd). Fixed by rebuilding through the normal module-load path with the workflow VM as the execution target (`ModuleLoader(vm=self).load_module_from_source(...)`), which re-binds named/aliased imports into `module_globals` and bare-namespace imports via `_bare_import_hints`, exactly as on first run. In-process resume was unaffected (it reuses the still-live registered VM). **Known limit:** host-injected, non-import globals (e.g. an embedder-supplied `llm_client`, custom effect handlers) are not reconstructable from source — the embedder must re-supply them on the rehydrating runtime; the framework then re-binds all `import`ed names automatically.

---

## [4.0.6] - 2026-06-20

### Fixes

- **COMPILER-001 fix (`@retry` annotation was a no-op — PR #267):** `_lower_retry()` emits annotation args verbatim (`max`, `delay_ms`) but `_policy_from_map()` was reading `max_attempts`/`backoff_ms`, producing a 1-attempt/no-delay policy regardless of what the annotation declared. Fixed by adding short-form key aliases in `_policy_from_map()`: `max` → `max_attempts`, `delay_ms` → `backoff_ms`. Both spellings are now accepted. `@retry(max: 3i, delay_ms: 50i)` now retries up to 3 times as expected.
- **WARN-001 fix (spurious "spawned task never executed" warning — PR #268):** `run_workflow()` and `run_graph()` were printing a false warning after every successful run. Coroutines spawned *during* `run_loop()` by task callbacks were incrementing `_spawned_without_loop` and the counter was only reset at the *start* of `run_loop()`, not the end. Fixed by resetting to 0 at the end of `run_loop()` as well. Tasks that run inside a loop are not unrun.

### CLI

- **`nodus serve --help` and `nodus worker --help` now print help and exit (PR #267):** Both commands were starting the server / attempting live worker registration instead of showing usage. Added `--help`/`-h` guards matching the pattern used by every other command. Full usage text added to `_COMMAND_HELP` for both commands.

### Documentation

- **`@exactly_once` scope warning (EXACT-001 — PR #268):** Added a scope note to `_lower_exactly_once()` in the compiler and a new `@exactly_once` subsection in `docs/guide/ai-primitives.md` clarifying that the annotation deduplicates within a single `NodusRuntime` instance only — not across separate instances, threads, or process restarts. Documents how to get durable idempotency via a persistent `EffectStore`.
- **`std:async` channel builtin note (CHAN-001 — PR #268):** `docs/guide/standard-library.md` now explicitly notes that `channel()`, `send()`, `recv()`, `close()`, `spawn()`, and `coroutine()` are VM builtins and must be called directly — `async.channel()` fails with "Missing module export: channel".
- **Type annotation enforcement note (TYPES-001 — PR #268):** `LANGUAGE_STABILITY_INDEX.md` entry for optional type annotations now explicitly states that `let x: int = "hello"` succeeds silently with no runtime enforcement, and names `nodus check --strict` as the forward path.

---

## [4.0.5] - 2026-06-15

### Stability graduations

The following experimental language surfaces have completed the graduation
criteria (two eval cycles without regression, ≥70% coverage, closed issues,
documented semantics) and are promoted in the Language Stability Index:

- **`spawn`, `coroutine`, `channel`**: Experimental → **Mostly Stable**
  SCHED-001 (#94), SCHED-002 (#95), CHAN-001 (#107), and CIRC-001 (#103) are
  all resolved. API is frozen.
- **`workflow`, `goal`, `step`**: Experimental → **Mostly Stable**
  WorkflowFrameworkRunner path unified (#108, #109). WF-SCAN-001 (#102) and
  checkpoint API (#110) resolved. NAME-COL-001 (#104) resolved via Option A
  (in-tree rename completed 2026-05-31).
- **`yield expr`**: Mostly Stable → **Stable**
  Semantics and `YIELD` opcode unchanged since v1.0; promoted to Stable.

### Documentation

- **Language Stability Index** updated to v4.0.5: graduation entries above,
  string interpolation corrected to Stable (was incorrectly marked "planned
  for v4.0" — shipped in v4.0), `+=/-=/*=/=/=` compound assignment added
  (shipped in v4.0.1), DAP evaluate corrected (implemented, #106 closed),
  coverage gate updated to 70% (raised from 60% on 2026-05-31).

### Companion tooling (published alongside this release)

- **nodus-vscode v0.1.0** — VS Code extension; TextMate grammar, snippets,
  diagnostics, run/format/DAP/LSP support. Published to VS Code Marketplace
  under publisher `MasterplanInfiniteWeave`.
- **nodus-jupyter v0.1.0** — Jupyter kernel for Nodus. Cross-cell state via
  full source accumulation. `pip install nodus-jupyter`. Published to PyPI.
- **nodus-mcp-server v0.1.0** — Standalone MCP tool server wrapping a
  NodusRuntime. 6 MCP tools. Available on GitHub.
- **nodus-adapter-base v0.1.0** — Abstract base for channel adapters;
  reconnect loop, health recording, `ConnectionManager`. Published to PyPI.

---

## [4.0.4] - 2026-06-13

### Fixes

- **#254 fix (`identity.session_id()` nil under CLI — residual from #236):** `module.py` now propagates `session_id` to child VMs alongside `trace_id`. One-line addition: `vm.session_id = getattr(caller_vm, "session_id", None)` after the existing `trace_id` propagation.
- **#255 fix (retry error trace bleeds to stderr on eventual workflow success):** `task_graph.py` marks the exception with `_retry_pending = True` when a step will be retried. `scheduler.py` checks that flag before printing and suppresses the per-attempt trace; the error is only printed if retries are exhausted and the step permanently fails.

---

## [4.0.3] - 2026-06-11

### Fixes

- **#225 fix (tool.register in imported module → re-execution storm):** `builtin_tool_invoke` now saves the bytecode context at registration time and creates an isolated child VM when invoking a handler whose code differs from the current root VM. Eliminates the entry-script re-execution loop caused by `run_closure` executing the wrong bytecode after `reset_program`.
- **#226 fix (step `with { retries: N }` no-ops under `nodus run`):** Added `inline_retries=True` path to `run_workflow_code` that loops on `retry_scheduled` responses — sleeping `retry_delay_ms` then calling `resume_graph` — so `nodus run` honours step-level retries without a long-running workflow framework sweeper. The workflow framework's external retry path is unchanged (default `inline_retries=False`).
- **#227 fix (state vars invisible in string interpolation):** `_StateRewriter` in `workflow_lowering.py` now recurses into `InterpolatedString` sub-expressions, so `"\(x)"` inside a workflow step correctly rewrites `x` to `__state["x"]`.
- **#228 fix (`let` in `for` loop — no per-iteration binding):** New `RESET_LOCAL_IDX` opcode emitted before `STORE_LOCAL_IDX` in `ForEach` (for the loop variable) and `Let` (for all let bindings). It writes `None` directly to the locals-array slot without touching any existing Cell, so the next `MAKE_CLOSURE` creates a fresh per-iteration Cell rather than reusing the previous iteration's Cell.
- **#229 fix (`run_loop()` swallows coroutine errors):** `builtin_run_loop()` now returns the list of coroutine error strings (e.g. `["worker failure"]`) when any worker failed, instead of returning `nil`. Coroutine isolation is preserved (session continues), but callers can detect partial failure by checking the return value.
- **#230 fix (`tool.register` JSON-Schema form crashes at invoke):** `_normalize_schema` now deep-converts nested Nodus Records in `properties` values via `_as_dict`, so `"type" in prop` succeeds at validation time. JSON-Schema-style registration (`{type: "object", properties: {x: {type: "string"}}, required: [...]}`) now works end-to-end.
- **#231 fix (`time.format()` garbled with strftime tokens):** `builtin_time_format` now detects `%` in the format string and delegates to Python's `datetime.strftime`, enabling standard strftime syntax (`%Y-%m-%d %H:%M:%S`). The existing Java/ICU token syntax (`yyyy-MM-dd HH:mm:ss`) continues to work unchanged.
- **#232 fix (`nodus test` UnicodeEncodeError on Windows):** Test runner output is now written through `_safe_write`, which falls back to `sys.stdout.buffer.write(...encode("utf-8", errors="replace"))` on `UnicodeEncodeError`, fixing the crash on Windows cp1252 consoles caused by `✗`/`✓` characters.
- **#233 fix (`nodus test` rejects `../lib/x` from `tests/` subdir):** `_run_one_file` now calls `_find_project_root` to walk up from the test file directory to find `nodus.toml`, using that as the sandbox root instead of the test file's directory. `import "../lib/tools"` from `tests/` is now valid when the resolved path stays within the project root.

### Known bugs (found during Sentinel evaluation against v4.0.2, filed 2026-06-10)

**Critical (P0)**
- **#225 (tool.register in imported module → re-execution storm):** Fixed in this release — see Fixes above.
- **#226 (step `with { retries: N }` no-ops under `nodus run`):** Fixed in this release — see Fixes above.

**High (P1)**
- **#227 (state vars invisible in string interpolation):** Fixed in this release — see Fixes above.
- **#228 (`let` in `for` loop — no per-iteration binding):** Fixed in this release — see Fixes above.
- **#229 (`run_loop()` swallows coroutine errors):** Fixed in this release — see Fixes above.

**Medium (P2)**
- **#230 (tool JSON-Schema form explodes at invoke):** Fixed in this release — see Fixes above.
- **#231 (`time.format()` garbled):** Fixed in this release — see Fixes above.
- **#232 (`nodus test` UnicodeEncodeError on Windows):** Fixed in this release — see Fixes above.
- **#233 (`nodus test` rejects `../lib/x` from tests/ subdir):** Fixed in this release — see Fixes above.

**Low (P3) — Fixed in this release**
- **#214 (`_last_vm` still public):** Renamed internal storage to `__last_vm` (name-mangled). `_last_vm` is now a `@property` that emits `DeprecationWarning` pointing to `get_execution_stats()`.
- **#234 (`cb.create` map form crashes):** Python builtin now accepts both positional `(name, threshold, timeout_secs)` and map `(name, {failure_threshold, recovery_timeout_ms})` forms. `.nd` wrapper retains 3-arg positional signature; `create_config(name, config)` added for map form.
- **#235 (`cb.call` never throws on circuit-open):** `cb.call` now throws `circuit_open` when the breaker is in open state. Function-call failures still return `{kind: "circuit_error", message: ...}` to allow failure accumulation before the breaker trips.
- **#236 (`identity.trace_id/session_id` nil under CLI):** `runner.py` now auto-generates `trace_id` and `session_id` UUIDs before script execution, matching the documented auto-generation behaviour.
- **#237 (`mem.tag`/`mem.forget` not implemented):** Both functions added to `std:memory`: `forget(key)` aliases `delete(key)`; `tag(key, tags)` stores tags under `__nodus_tags__:<key>`.
- **#238 (`tool.execute`/`tool.available` missing in `std:tool`):** Added `execute(name, args)` (alias for `invoke`) and `available(name)` (alias for `has`) to `std:tool`. Added `has(name)` to `std:tools`.
- **#239 (`fx.get_result()` absent):** `effect_get_result(action_id)` builtin added; `std:effects` exposes it as `get_result(action_id)` — returns the cached result value or `nil` if not yet complete.
- **#240 (failed-step IDs inconsistent wf vs goal):** `failed_id()` in `task_graph.py` now always prefers `step_name` over `task_id`, making `result["failed"]` consistent for both workflows and goals.
- **#241 (`nodus test` absent from `--help`):** `test [path]` added to the Execution section of `_render_help()`.
- **#242 (`.nodus/` run artifacts never cleaned up):** `nodus workflow cleanup` now removes runs in `failed` and `dead_lettered` terminal states in addition to `completed`.

### Tests

- **#252 (stdlib contract test suite):** 87-test contract suite added to `tests/test_stdlib_contracts.py`, gated on `NODUS_RUN_CONTRACTS=1`. Verifies installed-wheel API shapes match documentation for all stdlib modules (tool, identity, effects, sys, memory, retry, circuit-breaker, channel, http, subprocess, hash, time, fs, encoding, json, math). Run with `NODUS_RUN_CONTRACTS=1 python -m pytest tests/test_stdlib_contracts.py`.

---

## [4.0.2] - 2026-06-10

### Fixed

- **#207/#208 (@exactly_once broken):** Idempotency not enforced; return value always nil.
- **#209 (allowed_commands not enforced):** Blocked binaries run freely in embedded mode.
- **#210 (@retry silent skip):** Function body runs 0 times when nodus-retry missing.
- **#212 (event_sinks never fires):** Sink callable wired but never called.

### Added

- **#211 (trailing comma in multiline):** `[1i, 2i,]` now valid syntax.
- **#213 (channel() docs):** Correct positional API documented (`channel(2i)` not `channel(maxsize=N)`).

---

## [4.0.1] - 2026-06-10

### Added

- **#101 (@annotation syntax): `@exactly_once` and `@retry(...)` function decorators.**
  Annotations are lowered at compile time — no new opcodes, no BYTECODE_VERSION bump.
  Lexer: `@` added to the OP token set. AST: new `Annotation(name, args)` node; `FnDef`
  gains an `annotations` list field. Parser: `annotated_fn_def()` collects one or more
  `@name` / `@name(k: v, ...)` annotations before `fn`; works in top-level and `export`
  positions. Compiler lowering:
  - `@retry(max_attempts: N, backoff_ms: M)` — wraps the original body in a zero-arg
    closure and calls `retry_call(fn() { body }, policy_map)`. Parameters are captured as
    upvalues automatically. Requires `nodus-retry`.
  - `@exactly_once` — generates the full `effect_resolve` wrapper: computes action ID from
    fn-name + params, checks `effect_resolve().done` (Record field access via `Attr`), calls
    `effect_pending` on a cache miss, runs the body, calls `effect_complete`, and returns the
    result. Idempotent across calls with the same arguments.
  - Unknown annotations raise a compile-time `LangSyntaxError`.
  Closes #101.

- **Compound assignment operators `+=`, `-=`, `*=`, `/=` (PR #183).**
  Desugared by the parser — no new opcodes, no BYTECODE_VERSION bump. Works on
  variables (`x += 1i`), index targets (`lst[i] += n`), and field targets
  (`rec.field += n`). The formatter preserves the short form as a round-trip.

- **Multiline expressions inside delimiters (PR #178).**
  Function calls, list literals, and map literals can now span lines. Newlines
  inside an unclosed `(`, `[`, or `{` are silently consumed instead of terminating
  the statement — the same rule used by Python, JavaScript, and Go.

- **`std:math` bit operations (PR #172):** `math.bit_and(a, b)`, `math.bit_or(a, b)`,
  `math.bit_xor(a, b)`, `math.bit_not(a)`, `math.bit_lshift(a, n)`,
  `math.bit_rshift(a, n)`. All six validate int-typed arguments; shifts require a
  non-negative amount.

- **`NodusRuntime(allow_subprocess=False)` and `allow_network=False` (PR #165).**
  Capability flags added end-to-end: `VM.__init__`, `BuiltinRegistry`, and
  `NodusRuntime`. When disabled, the matching stdlib modules are replaced with
  sandbox-error stubs so every call path — including calls routed via
  `import "std:subprocess"` — is gated. Critical bug fix: `NodusModule.invoke_function()`
  now propagates both flags to child VMs (previously they could be bypassed via a
  module import).

- **`NodusRuntime(allow_env=False)` (PR #189).**
  Gates all six `env_*` builtins and their `std:env` module-method equivalents.
  Mirrors the `allow_subprocess` / `allow_network` pattern. Bug fix:
  `invoke_function()` now propagates all three capability flags to child VMs
  consistently.

- **`NodusRuntime(allowed_commands=[...])` (PR #198).**
  Subprocess allowlist — scripts may only invoke binaries named in the list.
  Shell mode (`shell=True`) is blocked entirely when the list is set.
  Closes #161.

- **`NodusRuntime(allowed_hosts=[...])` (PR #198).**
  HTTP allowlist — requests to hosts not in the list raise a sandbox error.
  Closes #162.

- **`NodusRuntime(event_sinks=[...])` (PR #200).**
  Wires event observer callables to `vm.event_bus` immediately after VM construction
  so sinks observe the full execution. Closes #190.

- **`NodusRuntime(coroutine_timeout_ms=N)` (PR #200).**
  Per-coroutine wall-clock deadline. `builtin_spawn()` stamps it onto each spawned
  coroutine as `task_timeout_ms`; the scheduler enforces it on first resume.
  Closes #191.

- **`NodusRuntime.get_execution_stats()` (PR #200).**
  Returns `{"instructions_executed": int, "coroutines_spawned": int}` — the
  documented public replacement for the deprecated `_last_vm`.

- **`NodusRuntime.clear_shared_state()` class method (PR #172).**
  Resets process-level singletons (`GLOBAL_MEMORY_STORE`, `AGENT_REGISTRY`,
  `_GRAPH_*`) for clean sequential restart after `shutdown()`. Does not fix
  concurrent multi-instance isolation (tracked as #166 RUNTIME-001).

- **`channel(N)` optional capacity cap (PR #197).**
  `send()` raises `runtime_error("channel", ...)` when the cap is exceeded.
  Omitting the capacity argument preserves the existing unbounded behaviour.
  Correct call syntax is positional: `channel(2i)` — not `channel(maxsize=N)`.
  Closes #175.

- **String indexing (PR #197).**
  `"hello"[1]` returns `"e"` with bounds checking. Out-of-range raises
  `runtime_error("index", ...)`. Closes #171.

- **Capability audit events (PR #165).**
  `vm.event_bus` now emits `RuntimeEvent("capability_use")` for `fs_read`,
  `fs_write`, `fs_exists`, `fs_append`, `fs_list`, `http_request` (method + URL),
  and `subprocess_run` (cmd + shell flag). Embedders get a real-time capability
  log with no extra configuration.

- **`nodus serve` unauthenticated startup warning (PR #165).**
  A `stderr` warning is printed when `--auth-token` is not configured, telling
  operators that all requests are accepted without authentication.

### Changed

- **`NodusRuntime.last_vm` renamed to `_last_vm` (PR #200).**
  Signals this is an implementation detail, not a stable API. Use
  `get_execution_stats()` for runtime metrics. **Migration:** replace `rt.last_vm`
  with `rt._last_vm` (or switch to `get_execution_stats()`). Closes #186.

- **`httpx` is now an optional dependency (PR #172).**
  `pip install nodus-lang` no longer installs httpx. Use `pip install nodus-lang[http]`
  or `nodus-lang[server]` to restore it. When httpx is absent all `std:http` builtins
  emit a clear install-hint error instead of an import crash.

- **Integer division now returns an integer (PR #197).**
  `6i / 2i` returns `3` (floor division) instead of `3.0`. Mixed-type expressions
  (`6i / 2.0`) still return a float. Closes #151.

- **Expression nesting depth limit raised from 50 to 100 (PR #178).**
  Accommodates generated code and macro expanders that previously hit the ceiling.

### Fixed

- **#106 (DAP-001): DAP `evaluate` command implemented — expression evaluation at breakpoints.**
  VS Code debug console and any DAP client can now evaluate Nodus expressions while paused.
  The server compiles the expression as `let __eval_result__ = (<expr>)`, runs it in a
  child VM that inherits a Cell-unwrapped copy of the paused VM's globals and current-frame
  locals (read-only — side effects do not modify the paused session). Returns `result`,
  `type`, and `variablesReference: 0`. Syntax errors and runtime errors return a DAP error
  response; the debug server never crashes on a bad expression. `allowed_paths` and
  `host_globals` are forwarded to the child VM so sandbox integrity is preserved.
  Closes #106.

- **UX: six runtime-audit gaps (PR #150).**
  - `HostFunctionError` from host-registered callbacks now returns `ok=False` instead
    of escaping `run_source()` as a live Python exception.
  - Indexing a caught error record (`e[0]`) adds: _"this is a caught thrown value —
    access the original via e.payload"_.
  - `spawn()` without `run_loop()` appends `"Warning: N spawned tasks never executed"`
    to `Result.stderr`.
  - Spawned-coroutine errors are collected in `result["spawned_errors"]` for embedder
    inspection without parsing stderr.

- **UX: error-message improvements from user reality audit (PR #159).**
  `import "std:channel"` now gives _"channel(), send(), recv(), and close() are
  built-in functions — no import needed"_ instead of an unhelpful path dump.
  Additional targeted hints for other common mistake sites.

- **#163 (SEC-004): `NODUS_ALLOWED_PATHS` env var now honoured in embedded mode
  (PR #197).** `NodusRuntime()` reads it when `allowed_paths` is not passed explicitly.

- **#164 (SEC-005): Symlink traversal fixed (PR #197).** All path enforcement points
  now use `os.path.realpath` instead of `os.path.abspath`.

- **#152 / #153: Division and modulo by zero raise `runtime_error("math", ...)` (PR #197).**
  Previously returned IEEE 754 `inf` / `nan` or inconsistent error records.

- **`run_source()` thread safety (PR #178).** `NodusRuntime` gains `_run_lock`
  (threading.Lock); concurrent `run_source()` calls serialize instead of racing on
  `_last_vm`.

- **Default workflow sweep thread auto-starts (PR #178).** `get_default_workflow_runner()`
  starts a daemon thread (`nodus-workflow-sweep`) on first call; calls
  `expire_wait_timeouts()` every 30 seconds so workflow wait-deadlines are enforced
  without host involvement.

- **#187: `legacy_error_dict()` consolidated onto `coerce_error()` path (PR #196).**
  Eliminates duplicate exception-parsing logic; all exception types derive their
  legacy dict from `coerce_error()` except `TypeError` (preserved to keep the
  `"type"` prefix that `format_error_payload` depends on).

- **#184 (BI-03): Core value types extracted to `src/nodus/vm/types.py` (PR #201).**
  `Cell`, `Closure`, `_ClosureProxy`, `Record`, `BuiltinMethod`, and `Frame` moved
  out of `vm.py`. Re-imports in `vm.py` preserve backwards compatibility for existing
  code using `from nodus.vm.vm import Record`.

### Removed

- **`nodus.run_source` top-level re-export dropped (PR #196, closes #188).**
  Deprecated in v4.0; removed from `nodus.__init__`. Use `NodusRuntime.run_source()`
  from `nodus.runtime.embedding`.

---

## [4.0.0] - 2026-06-04

> **SemVer note:** The following additions were implemented during the v4.0.0
> development cycle and are all part of v4.0.0. Published to PyPI 2026-06-04.

### Added (Phase 6 — AI-native primitives)

- **Phase 6A — Execution identity auto-propagation:** VM gains `execution_unit_id`
  (always set, `secrets.token_hex(8)`, unique per VM instance) and injectable `trace_id`
  (nil by default; set via `NodusRuntime.set_trace_id()`). Both fields are automatically
  injected into every `RuntimeEvent` emitted (memory, tool, workflow, error, syscall).
  New `std:identity` stdlib module exposes `identity.trace_id()`, `identity.session_id()`,
  `identity.execution_unit_id()`. Module VM propagation: `NodusModule.invoke_function`
  now forwards `trace_id`, `execution_unit_id`, `event_bus`, `effect_store`,
  `memory_store`, and `circuit_breakers` from the caller VM to each cross-module invocation.

- **Phase 6B — Stdlib memory extensions:** `std:memory` gains three namespaced KV
  operations: `memory.recall_from(ns, key)`, `memory.recall_all(ns)`,
  `memory.share(ns, key, val)`. Keys are prefixed `{ns}::` in the in-process
  `MemoryStore`. All three emit dedicated runtime events (`memory_recall_from`,
  `memory_recall_all`, `memory_share`). Memory builtins extracted from `VM.__init__`
  inline dict into `builtins/memory_module.py` (pure refactor).

- **Phase 6C — sys.v1.* syscall dispatch:** New `services/syscall_runtime.py` with
  `SYSCALL_REGISTRY`, `call_syscall(name, payload, vm)`, and a stable uniform envelope:
  `{status: "ok"|"error", data, error, trace_id}`. Four initial syscalls registered:
  `sys.v1.memory.get`, `sys.v1.memory.put`, `sys.v1.memory.delete`,
  `sys.v1.memory.recall_from`. New `syscall(name, payload)` and `syscall_list()`
  builtins. New `std:sys` stdlib module with ergonomic helpers.

- **Phase 6D — EffectStore as language primitive:** `nodus-retry` promoted from optional
  to required dependency. VM gains `self.effect_store = InMemoryEffectStore()`. New
  `builtins/effects_module.py` registers: `effect_resolve(id)`, `effect_pending(id, hash)`,
  `effect_complete(id, status, result)`, `effect_action_id(type, payload, scope)`,
  `effect_store_size()`. New `std:effects` stdlib module. `NodusRuntime.set_effect_store()`
  for Python-host injection.

- **Phase 6E — Retry/circuit-breaker stdlib bindings:** Optional-dep stdlib wrappers for
  `nodus-retry` (`std:retry` — `retry.call(func, policy_map)`) and `nodus-circuit-breaker`
  (`std:circuit_breaker` — `cb.create/call/state/reset`). Both packages remain optional;
  builtins return a `{kind: "dependency_error"}` map when not installed. `VM` gains
  `self.circuit_breakers: dict` (propagated cross-module). `_ClosureProxy`-aware execution
  in both bridge builtins.

- **Phase A — HandlerContract in nodus_schema:** New `src/nodus_schema/contracts.py`
  defines `HandlerContract` dataclass with `name`, `description`, `input_schema`,
  `returns_schema`, `effects`, `capabilities_required`, `version`, `tags`, `deprecated`.
  `VALID_EFFECTS` frozenset: `pure | reads_state | writes_state | network | filesystem |
  spawns_task`. `validate()` returns structural error list. Exported from
  `nodus_schema.__init__`.

- **Phase B — tool.register() effects and returns_schema enforcement:**
  `builtins/tool_module.py` adds `_validate_effects()` and `_validate_return()` helpers.
  `tool.register()` now accepts `effects` (validated against `VALID_EFFECTS`; `pure` is
  mutually exclusive; unknown effects → `invalid_metadata` error) and `returns_schema`
  (normalized at registration). `tool.invoke()` validates handler return value against
  `returns_schema`; violation produces a `contract_violation` error record.

- **Phase C — nodus-extension contract fields:** `nodus-extension`'s `ToolSurface` gains
  `returns_schema` and `effects` fields with Pydantic validator enforcing the closed effects
  vocabulary. Bridge passes new fields through to the tool registry entry.

- **Phase D — nodus_gate --contracts flag:** New `tools/nodus_gate/contracts_phase.py`
  implements 6 smoke-test checks on `HandlerContract` infrastructure. `--contracts` flag
  added to `nodus_gate` CLI; wired into `--all`. Output formatted via `format_contracts()`
  in `output.py`.

### Changed

- `nodus-retry>=0.1.0` promoted from optional to required dependency in `pyproject.toml`.
  `EffectStore` is now always available — agents can rely on it without checking installation.

### New packages (ecosystem)

- **nodus-sdk v0.1.0** — Unified platform SDK at `C:\dev\nodus-sdk`. Single-package
  installation story: `pip install nodus-sdk[agent,sql,fastapi]`. Provides
  `NodusSDKRuntime` with fluent `attach_*` bridge methods, `create_runtime(**kwargs)`
  factory, and 9 bridge modules: redis, http, llm, observability (wrappers over existing
  packages), sql (SQLAlchemy), vector (pgvector), scheduler (APScheduler), webhook (HMAC
  signing + retry), api (FastAPI router + `NodusTraceMiddleware`). 99 tests.

- **nodus-store-sql v0.1.0** — Promoted from incubator scaffold at `packages/nodus-store-sql`
  to standalone production package at `C:\dev\nodus-store-sql`. SQLAlchemy 2.x persistence
  adapters for three durable state surfaces: `RunStore` (optimistic locking, `list_by_status`,
  `list_by_owner`), `EventStore` (append-only with `append_batch`, pagination),
  `JobStore` (atomic `claim_pending`). `[async]` extra adds `AsyncSqlStore` / `AsyncRunStore`
  / `AsyncEventStore` / `AsyncJobStore` via `sqlalchemy.ext.asyncio`. 47 tests (31 sync +
  16 async). Closes the last gap in both ecosystem audits.

### Fixed

- **#107 (CHAN-001): recv() blocked on empty channel no longer orphaned silently.**
  The scheduler now tracks channels with waiting receivers in `_recv_channels`. When
  `recv()` blocks, the channel is registered; when `send()` or `close()` wakes receivers,
  it's deregistered. The scheduler exits its loop only when all pending work is truly
  exhausted. If only blocked `recv()` calls remain with no possible sender (no runnable
  coroutines, no timers, no daemon channels), the scheduler raises a `deadlock` runtime
  error instead of silently returning. Closes #107.
- **#99 (EMBED-003): `subprocess_spawn` pump threads are now joined on `reset()`/`shutdown()`.**
  Each `subprocess_spawn` call registers its two daemon pump threads (stdout + stderr)
  in `vm._spawned_handles`. `NodusRuntime.reset()` and `NodusRuntime.shutdown()` now
  kill any live subprocesses and join their threads (500ms timeout per thread) before
  releasing the VM reference. The handles list is cleared so no stale references accumulate
  across calls in long-lived embedded servers. Closes #99.
- **#108/#109: `run_goal()` and `resume_goal()` now route through `WorkflowFrameworkRunner`.**
  Both functions previously bypassed the framework runner and called the task-graph layer
  directly. They now call `get_default_workflow_runner().start_graph()` and
  `get_default_workflow_runner().resume_workflow()` respectively, so every goal execution
  creates a persisted framework run record with `execution_kind='goal'`, and resumptions
  increment `resume_count` in the store. The `_rebuild_workflow_graph` callback handles both
  `goal` and `workflow` kinds transparently. Closes #108, #109.
- **#110: Checkpoint API documented and tested.** Eight new tests in `tests/test_checkpoints.py`
  cover checkpoint label creation, multi-checkpoint ordering, resume-from-checkpoint,
  `resume_count` increment, duplicate-label last-wins semantics, and rollback scope
  (checkpointed task + dependents only; sibling steps unchanged). Module docstring
  documents the `checkpoints` (public) vs `engine_checkpoints` (internal snapshot) split.
  Closes #110.
- **#102: `LocalWorkflowStore.list_runs()` uses mtime-based scan to skip old files.**
  Switched from `os.listdir()` full-read to `os.scandir()` with `entry.stat().st_mtime`
  check. Files older than `terminal_max_age_days` (default 30) are skipped without loading
  their JSON. New constructor parameter `terminal_max_age_days` (set to 0 to disable).
  Prevents >2s sweep latency seen in CI with 670+ accumulated run files. Closes #102.
- **#94 (SCHED-001): cooperative sleep no longer counted against execution deadline.**
  The scheduler now extends `vm.deadline` by the actual wall-clock duration of each
  `time.sleep()` it calls while waiting for timers or I/O channels. Only active
  instruction execution consumes the deadline budget; idle sleep time is excluded.
  A coroutine sleeping 4×100ms with `timeout_ms=200` now completes cleanly. CPU
  tight-loops are still killed. Closes #94.
- **#96 (SCHED-003): scheduler sandbox deadline path now has test coverage.**
  `SchedulerSandboxLimitTests` exercises the full `run_source` → scheduler → deadline path.
  `Chan001OrphanTests` covers the `_recv_channels` deadlock detection path. Closes #96.
- **#83 (BUG-NEW-01): `1ii` now gives a parse error with a suggestion.** The lexer detects
  integer literals followed immediately by identifier characters (e.g. `1ii`, `5ib`) and
  raises `LangSyntaxError` with a "did you mean `1i`?" message instead of a confusing
  runtime name error.
- **#116 (BUG-116): `spawn().wait_async()` is now truly async.** Previously a synchronous
  alias for `wait()`; now uses the same daemon-thread + channel suspension pattern as
  `subprocess_run_async`, allowing multiple spawned processes to wait concurrently.
- **#128 (BUG-128): `push()` is now a top-level builtin alias for `list_push()`.** Resolves
  the naming inconsistency where `push` only worked after `import "std:collections"`.
- **#131 (BUG-131): Em-dashes in `nodus --help` and `nodus stability` replaced with ASCII
  `--`.** Prevents mojibake on Windows console (cp1252/cp850).

### Documentation

- **`EXECUTION_INVARIANTS.md` — added I-WFLOW-04/05/06:** Documents step dependency
  ordering (steps do not run until all `after` dependencies complete), checkpoint snapshot
  semantics (state deep-copied at call time, public API strips internal `state` field),
  and resume idempotency (completed steps are never re-executed). Closes #111.

### Added (original 4.0.0 scope)

- **Third-party .nd module resolution via `nodus.nd` entry-point group:** Pip-installed
  Nodus libraries can now be imported with a bare `import "library-name"` after
  `pip install library-name`, with no additional setup steps. Libraries declare
  a `[project.entry-points."nodus.nd"]` entry in their `pyproject.toml`; the
  value is a `module:callable` reference where the callable returns the absolute
  path to the package's `.nd` source root directory. The resolver fires this
  check as the fourth lookup tier, after project-root, `.nodus/modules/`, and
  stdlib — local always wins, installed is last resort. The colon form
  `import "library-name:submodule"` resolves `submodule.nd` within the nd root.
  Import failure errors now list all attempted paths including `.nodus/modules/`
  (previously omitted) and the entry-point check result. See
  `docs/guide/library-entry-points.md` for the full contract and library-author
  checklist. This is the final v4.0 language-complete piece; nodus-mcp and
  nodus-a2a can now scaffold with `pip install` as the sole install step.

- **3D.2 — Equality coercion narrowing (Doc 11):** `==` now performs numeric-only
  coercion (int ↔ float) and rejects cross-family coercions. `0i == false` is
  `false` in v4.0 (was `true`). `1i == true`, `"" == false`, `"1" == 1i` are
  all `false`. Number-family coercion preserved: `1i == 1.0` is still `true`.
  `!=` updated for consistency. New builtins: `type_eq(a, b)` (strict same-type
  equality), `bool_equal(value, bool_value)`. New `std:bool` module exposing
  `bool.equal(x, bool_value)`. Breaking change for code relying on `0 == false`
  or `1 == true`.

- **3D.1 — type() naming reconciliation (Doc 10):** `type(1.0)` now returns
  `"float"` (was `"number"`). `type(42)` (unadorned literal) also returns
  `"float"`. `type(1i)` unchanged (`"int"`). New math helpers: `math.is_float(x)`,
  `math.is_numeric(x)` (joins existing `math.is_int`). Breaking change for code
  comparing `type(x) == "number"` — update to `math.is_float(x)` or `"float"`.

- **3C.4 — nodus_gate doc-vs-code reconciliation gate (Doc 12):** New
  `tools/nodus_gate/` Python tool implementing the three-phase verification gate.
  `python -m tools.nodus_gate.cli --static` verifies every `import "std:*"` and
  `nodus <cmd>` in docs exists in the codebase. `--runtime` executes all
  ` ```nodus ` and ` ```nodus-expect=output ` code blocks in documentation and
  verifies they run clean / produce expected output. `--closed-issues` parses
  `CHANGELOG.md [Unreleased]` for issue references, locates tests by file
  convention or `# closes: #N` marker, and runs them. `--all` runs all three.
  Supports `.nodusgate-allow` allowlist, `--verbose`/`--quiet`/`--format` flags.
  Mandatory pre-release step per the PLAYBOOK_MAJOR.md Phase 4 exit criterion.

- **3C.3 — std:test framework (Doc 07 + Doc 08):** New `std:test` namespace
  implementing a full pytest/jest-equivalent test framework. 11 assertions
  (`assert`, `assert_eq`, `assert_neq`, `assert_err`, `assert_ok`, `assert_kind`,
  `assert_throws`, `assert_close`, `assert_contains`, `assert_has_key`,
  `assert_in_range`). Suite/case API: `test.suite`, `test.case`, `test.case_async`,
  `test.skip`. Lifecycle hooks: `before_all`, `after_all`, `before_each`,
  `after_each`. Fixtures with test/suite scopes and `test.cleanup` teardown.
  Parameterized tests via `test.parameterize` (list and map row forms). Async
  tests with virtual clock: `test.advance_clock`, `test.flush_async`. Test
  isolation by default (env, cwd, tool registry reverted between tests).
  CLI: `nodus test [path] [--filter] [--format] [--coverage] [--bail]
  [--verbose] [--quiet]`. Output formats: pretty, plain, JSON, JUnit XML.
  Coverage: line-hit collection via event bus; JSON + HTML reports written
  to `./coverage/` with `--coverage` flag. Doc 08 coverage integration.

- **3C.2 — Tool registry library-side handlers (Doc 06):** New `std:tool`
  namespace for dynamic tool registration. `tool.register({name, handler,
  description, schema?, version?, tags?, deprecated?, metadata?})` — conflict
  on duplicate name returns err (`category: "registration_conflict"`). Schema
  supports simple flat map form (auto-normalized to JSON Schema) and full JSON
  Schema. `tool.unregister(name)`, `tool.invoke(name, args)`,
  `tool.lookup(name)`, `tool.list_tools(filter?)`, `tool.has(name)`. Deprecated
  tools emit a warning once per VM instance on first invocation.
  `NodusRuntime.tool_registry` property exposes a Python-side `ToolRegistry`
  wrapper with the same API; Python-registered tools persist across `run_source`
  calls and are pre-populated into each VM. Value translation (Nodus ↔ Python)
  for Python callable handlers. `threading.RLock` for concurrent host access.

- **3C.1 — String interpolation:** Swift-style `"\(expr)"` syntax for inline
  expression embedding in string literals. Lexer uses a character-by-character
  mode-stack (`_lex_string` / `_lex_interp`) replacing the prior regex-based
  string match; plain strings (no `\(`) still emit the classic `STR` token for
  full backward compatibility. Interpolated strings emit a token sequence:
  `STRING_START`, zero or more `STRING_LITERAL` / (`INTERP_START` expr-tokens
  `INTERP_END`) interleaved parts, `STRING_END`. Parser builds an
  `InterpolatedString(parts)` AST node where each part is `StringLiteralPart`
  or `InterpolationPart`. Compiler lowers to existing opcodes: each literal
  part becomes `PUSH_CONST`, each interpolated expression is compiled then
  coerced with `CALL str 1`; all parts are joined with N−1 `ADD` ops. No new
  bytecode opcodes (BYTECODE_VERSION stays at 4). Escape sequences (`\n`,
  `\t`, `\r`, `\0`, `\"`, `\\`, `\xHH`, `\uXXXX`) decoded inline in the lexer
  so they work correctly in both literal and interpolated segments. Literal
  `\(` is written `\\(` in source. Empty interpolations (`"\()"`) and format
  specifiers (`"\(x:.2f)"`) are parse errors with descriptive messages. Nesting
  depth capped at 32 levels. Formatter round-trips interpolated strings
  correctly. Analyzer treats `InterpolatedString` as `STRING` type. AST printer
  handles the new nodes. 39 new tests added (`tests/test_string_interpolation.py`).
  1227 total tests passing.

- **3B.5 — std:subprocess:** New `std:subprocess` namespace with 7 public
  functions: `run(argv, options?)`, `run_async(argv, options?)`,
  `shell(command, options?)`, `shell_async(command, options?)`,
  `spawn(argv, options?)`, `spawn_shell(command, options?)`,
  `shell_quote(string)`. `run`/`shell` block until process exit and
  return a result record (`stdout`, `stderr`, `exit_code`, `duration_ms`,
  `command`) or err record (`kind: "subprocess_error"`, five `category`
  values: `exit_code`, `timeout`, `signal`, `spawn_error`, `io_error`).
  `spawn`/`spawn_shell` return a process handle with `stdout`/`stderr`
  Channels (background-thread pumped, registered on root-VM scheduler's
  `_io_channels`), a `stdin` record with `send`/`close` BuiltinMethods,
  and lifecycle methods (`wait`, `wait_async`, `is_alive`, `terminate`,
  `kill`, `interrupt`, `signal`). Options: `output`, `stdout`, `stderr`
  (per-stream override including file-path redirect with `>>` prefix),
  `output_encoding` (`"utf-8"` or `"bytes"`), `stdin`, `env`/
  `env_inherit`/`env_passthrough` for environment merging, `cwd`,
  `timeout_ms`/`kill_grace_ms`, `check` (default true), `process_group`,
  `chunk_mode` (`"lines"` default or `"bytes"`) for spawn streams.
  `_async` variants are Phase 3B synchronous under the hood (true async
  bridging deferred to Phase 3C). `shell_quote` uses
  `subprocess.list2cmdline` on Windows and `shlex.quote` on Unix.
  No new dependencies (Python stdlib only). 48 new tests, 1186 total passing.

- **3B.4 — std:http:** New `std:http` namespace with 19 public functions:
  8 sync verbs (`get`, `post`, `put`, `delete`, `patch`, `head`, `options`,
  `request`), 8 `_async` counterparts (Phase 3B: synchronous at I/O level;
  parallelism via Nodus scheduler), `stream`, and `sse`. Buffered response
  records have `status`, `headers`, `body`, `url`, `method`, `ok`,
  `is_redirect`, `is_client_error`, `is_server_error` fields plus
  `json()`, `header(name)`, `headers_all(name)` method fields.
  Options: `json`, `form`, `text`, `bytes`, `multipart` body keys
  (mutually exclusive); `headers`, `query`, `auth_bearer`, `auth_basic`
  shortcuts; `timeout_ms`, `connect_timeout_ms`, `read_timeout_ms`;
  `follow_redirects`, `verify_tls`, `proxy`. Stream responses carry a
  `chunks` channel filled by a background thread; scheduler's new
  `_io_channels` list is polled by `run_loop` to wake blocked coroutines.
  SSE responses carry an `events` channel with parsed event dicts
  (`event`, `data`, `id`, `retry` fields). `r.as_sse()` converts a stream
  to an SSE channel. Err records use `kind: "http_error"` with six
  `category` values (`network`, `timeout`, `client_error`, `server_error`,
  `decode_error`, `redirect_error`). Requires `httpx>=0.27,<1` (already
  in `pyproject.toml`). Scheduler extended with `_io_channels` polling
  for thread-backed Channel wakeup.

- **3B.3 — std:hash, std:encoding, std:secrets:** Three new namespaces
  using Python stdlib only (no new dependencies).
  `std:hash`: 15 hash functions (5 algorithms × one-shot/builder/file),
  5 HMAC functions, constant-time `compare`. Hash records have `to_hex`,
  `to_hex_upper`, `to_base64`, `to_base64_url`, `to_bytes` method fields
  (via `BuiltinMethod`) plus `algorithm` and `length`. Builder pattern
  is single-use; reuse after `finalize` returns err
  (`kind: "state_error"`). `std:encoding`: base64 standard/URL-safe
  encode/decode, hex lower/upper encode, hex decode, URL RFC 3986
  percent-encode, URL form-encode/decode. `std:secrets`: `random_bytes`,
  `random_int` (rejection sampling), `token_hex/base64/urlsafe/
  alphanumeric`, `uuid_v4`, `uuid_v7` (RFC 9562 manual implementation).

- **3B.2 — std:time:** New `std:time` namespace with 7 datetime constructors
  (`now`, `now_in`, `at`, `from_epoch_ms`, `from_iso8601`, `from_http_date`,
  `parse`), 6 duration constructors plus `duration_between`, 12 calendar
  operations, chrono-style format engine, and serialization helpers
  (`to_iso8601`, `to_http_date`, `to_epoch_ms`). Datetimes store
  `epoch_ms + zone`; durations store `total_ms`. DST gap/fold detection
  with `on_invalid`/`on_ambiguous` options. Err records use
  `kind: "time_error"` with four categories. `datetime` and `duration`
  Records support comparison operators (`==`, `!=`, `<`, `>`, `<=`, `>=`).
  Requires `tzdata>=2024.1` (added to `pyproject.toml`).

- **3B.1 — std:env:** New `std:env` namespace with `get`, `set`, `unset`,
  `has`, `list`, `list_keys`. All values are strings; `env.get` accepts an
  optional default; `env.set` with an invalid name (contains `=` or null byte)
  returns an err record (`kind: "env_error"`, `category: "invalid_name"`).
  Modifications affect the current process only.

- **Doc 15:** Cyclic workflow dependency detection now returns an err record
  (`kind: "workflow_error"`, `origin: "stdlib"`) instead of a plain dict.
  The payload contains `category: "cyclic_workflow"`, `cycle` (ordered list
  of step names forming the cycle), and `workflow_name`. The DFS cycle
  detector extracts the actual cycle path; ambiguous "missing tasks" cases
  return `category: "missing_tasks"`. `run_workflow_code` runner translates
  err-record returns to `ok: false` for CLI/API consumers.

- **Doc 14:** `len()`, `count()`, `index_of()`, `last_index_of()`, and `range()`
  now return `int`. `math.floor()`, `math.ceil()`, and new `math.round()` return
  `int`. `index_of()` and `last_index_of()` return `nil` when not found (was
  `-1`). New top-level builtins `count`, `index_of`, `last_index_of`, `range`
  (1–3 args) added.

- **Doc 09:** Float division by zero now returns IEEE 754 `inf`/`nan` instead
  of throwing. `0.0 / 0.0` → `nan`; `1.0 / 0.0` → `inf`; `-1.0 / 0.0` →
  `-inf`. Float modulo by zero returns `nan`. Integer division or modulo by
  zero returns an err record (`kind: "math_error"`, `origin: "vm"`). New
  `math.is_nan(x)`, `math.is_inf(x)`, `math.is_finite(x)` functions and
  `math.nan`, `math.infinity`, `math.neg_infinity` constants added to
  `std:math`.

- **Doc 13 (#78):** All err records now carry five location fields: `path`,
  `line`, `column`, `stack`, and `origin`. Stdlib-returned errs are augmented
  in `call_builtin()` with `origin="stdlib"` and the call-site location.
  VM-thrown errs get `origin="vm"` via `build_runtime_error()`. User-thrown
  errs get `origin="user"` via `_op_throw()`.

### Breaking Changes

- **`type(float)` returns `"float"` not `"number"`** (Doc 10). Code checking
  `type(x) == "number"` will silently stop matching. Migrate: use
  `math.is_float(x)` or `type(x) == "float"`. Grep for `"number"` in type
  comparisons.

- **`==` no longer coerces across type families** (Doc 11). `0 == false`,
  `1 == true`, `"" == false`, `"1" == 1` are all `false` in v4.0. Number-family
  coercion (`1i == 1.0`) is preserved. Migrate: use `bool.equal(x, true/false)`,
  `type_eq(a, b)`, or explicit type-checked comparisons.

- **`index_of()` and `last_index_of()` return `nil` for not-found** (Doc 14,
  v4.0). Was `-1` in v3.x. Migrate: check `result == nil` instead of `== -1`.

- **Float division by zero returns `inf`/`nan`** instead of throwing (Doc 09).
  Code catching `RuntimeError: Division by zero` will silently get `inf`/`nan`.
  Migrate: use `math.is_nan(x)` or `math.is_inf(x)` to check results.

- **Cyclic workflow returns err record** instead of a plain dict (Doc 15).
  Migrate: check `type(result) == "error"` for cyclic workflow detection.

- **Err records now carry location fields** (`path`, `line`, `column`, `stack`,
  `origin`) in v4.0 (Doc 13). Code pattern-matching err record fields must
  allow for the new fields.

### Fixed

- **BUG-V31E-03 (#77):** `nodus workflow run --help` and `nodus graph run --help`
  now display help text instead of treating `--help` as a script filename and
  producing "File not found: --help".

## [3.0.2] - 2026-05-25

Patch release fixing two issues surfaced by the v3.0.1 independent stress-test
eval: a patch closure failure (BUG-V31E-01, #75) and a new HIGH bug introduced
by v3.0.1's `math.log` addition (BUG-V31E-02, #76).

### Fixed (undocumented in original release)

- `strings.split(x)` (wrong arity) now produces a Nodus-voice type error
  (`type error: split(x, delimiter) expects a string`) instead of leaking the
  internal "Stack underflow" message. This was an unintended side effect of
  the v3.0.2 work that was not captured in the original release notes.
  Identified by the v3.0.2 stress-test eval. The fix is real and shipped in
  the v3.0.2 wheel; this note is a retroactive disclosure.

### Fixed

- **BUG-V31E-01 (#75):** `1I` (uppercase integer suffix) now reliably produces
  a parse-time syntax error in all distribution artifacts. The lexer fix was
  committed in v3.0.1 but was absent from the v3.0.1 wheel due to a packaging
  gap (see `docs/governance/TECH_DEBT.md` § Patch closure verification gap).
- **BUG-V31E-02 (#76):** `math.log(value, base)` now correctly returns
  `log_base(value)`. The v3.0.1 implementation silently computed `ln(base)` and
  ignored `value` for all two-argument calls. The `log` and `log_base` wrappers
  in `std:math` have been unified into a single `fn log(n, base)` that passes
  `nil` for the base when called with one argument. The separate `log_base`
  export has been removed; callers should use `math.log(n, base)`.

## [3.0.1] - 2026-05-25

Patch release addressing 22 issues found during the v3.0.0 stress-test eval.
All issues filed as GitHub #53–#74 against the v3.0.1 milestone.

### Fixed

**Replace contract completeness (Commit 1)**

- **BUG-E01 (#53):** `json.parse` type-check now returns a `type_error` err
  record when the argument is not a string, instead of throwing a VM runtime
  error.
- **BUG-E02 (#54):** `math.sqrt(-1)` now returns a `value_error` err record
  instead of throwing. The Replace contract now covers all `std:math` domain
  errors.
- **BUG-E05 (#57):** `math.log(n)` and `math.log_base(n, base)` are now
  exposed in `std:math`. Previously `math_log` was wired as a builtin but
  never surfaced through the stdlib module.
- **BUG-E06 (#58):** `math.pow(base, exp)` is now exposed in `std:math`.
  Handles `OverflowError` and returns a `math_error` err record on overflow.
- **BUG-E07 (#59):** `fs.mkdir(path)` is now exposed in `std:fs`. Creates
  the directory; returns an `io_error` err record if the path already exists
  or is inaccessible.
- **BUG-E10 (#62):** `fs.delete(path)`, `path.relative(p, base)`, and
  `path.absolute(p)` are now exposed in `std:fs` and `std:path` respectively.
  All three are Replace-wrapped and return err records on failure.
- **BUG-E13 (#65):** The parser now accepts `catch (err)` with parentheses
  around the catch variable, in addition to the existing `catch err` form.

**Embedding API (Commit 2)**

- **BUG-E03 (#55):** `NodusRuntime.run_source(host_globals=...)` now correctly
  forwards `host_globals` to the `ModuleLoader`, so named variables injected
  from the host are accessible in Nodus scripts.
- **BUG-E04 (#56):** Python exceptions raised by host-registered functions
  (via `NodusRuntime.register_function`) now propagate to the Python caller
  as the original exception type. Previously they were silently absorbed by
  the VM's `except Exception` handler and converted to `LangRuntimeError`.
  A new `HostFunctionError` sentinel in `nodus.runtime.diagnostics` bypasses
  the VM wrapper.

**Documentation reconciliation (Commit 3)**

- **BUG-E08 (#60):** `docs/policy/error-surfaces.md` now documents that sandbox
  validation fires before stdlib error wrapping. Includes a code example showing
  that absolute paths produce sandbox errors, not `io_error` records.
- **BUG-E09 (#61):** `docs/policy/error-surfaces.md` §5 trace-errors example
  output updated to match the actual `print_trace()` format emitted at runtime.
- **BUG-E19 (#71):** `docs/migration/v2-to-v3.md` now includes an explicit
  breaking-change callout that `has_key(err, key)` **crashes** in v3.0 (throws
  a runtime type error) rather than silently returning a wrong value. Includes
  the error message, an audit call-to-action, and replacement patterns.
- **BUG-E20 (#72):** CHANGELOG v3.0.0 `path.join` entry corrected — removed
  the incorrect claim "in addition to the variadic form". The function accepts
  a single list argument only.

**Polish, deprecations, and design capture (Commit 4)**

- **BUG-E11 (#63):** The lexer now emits `"Identifiers must use ASCII letters
  only: '<char>'"` when a non-ASCII alphabetic character appears at identifier
  position, instead of the generic `"Unexpected character"` message.
- **BUG-E12 (#64):** `1I`, `42I`, and similar integer literals with an
  uppercase `I` suffix now produce a parse error (`"Integer suffix must be
  lowercase 'i'"`) instead of silently splitting into a number and a name that
  later causes a confusing runtime name-lookup failure.
- **BUG-E16 (#68):** Import error messages no longer double the `.nd` extension.
  `import "logparse.nd"` that fails now shows `"logparse.nd"` in the tried
  paths, not `"logparse.nd.nd"`. Fixed in both the local resolution path and
  the stdlib fallback path.

### Changed

- **BUG-E14 (#66):** `nodus.tooling.loader.run_source()` now emits
  `DeprecationWarning` on every call, directing callers to
  `NodusRuntime.run_source()` from `nodus.runtime.embedding`. Planned removal
  in v4.0. See `docs/governance/DEPRECATIONS.md`.

### Documentation

- **BUG-E15 (#67):** `docs/guide/standard-library.md` now notes that `len()`
  returns a float (e.g., `3.0`) in v3.x. Changing to `int` is a v3.1 design
  candidate; see `docs/governance/V3_1_PLAN.md §1`.
- **BUG-E17 (#69):** `docs/guide/standard-library.md` now notes the `type()`
  naming asymmetry (`"number"` for floats, `"int"` for integers). Renaming
  `"number"` to `"float"` is a v3.1 design candidate; see
  `docs/governance/V3_1_PLAN.md §2`.
- **BUG-E21 (#73):** `docs/guide/standard-library.md` now documents that
  `print(42i)` displays `42` (not `42i`). The `i` suffix is source syntax only;
  it is not part of the runtime string representation.
- **BUG-E22 (#74):** `docs/guide/standard-library.md` now notes that
  `json.stringify` accepts `int` values natively (e.g., `42i` serializes as
  `42` in JSON output).
- `docs/governance/V3_1_PLAN.md` created — captures deferred design items
  (BUG-E15, BUG-E17, the `finally`/`catch`-return bug) as v3.1 candidates
  with rationale and proposed resolution options.
- `docs/governance/DEPRECATIONS.md` updated with the `run_source()` entry.

## [3.0.0] - 2026-05-25

### Breaking changes

**v2.1.1 is the last v2.x release.** v3.0 folds the v2.2 bug-fix milestone
and all breaking language changes into a single release. Migration guide:
`docs/migration/v2-to-v3.md`.

- **`{foo: bar}` is now a record literal, not a map lookup.** In v2.x, bare
  (unquoted) identifier keys in a map literal context were evaluated as variable
  lookups. In v3.0, `{ host: "localhost" }` is a **record literal** — `host`
  is a field name, not a variable. To use a variable's value as a map key, wrap
  it in parentheses: `{ (mykey): value }`. To create a map with a literal string
  key, quote it: `{ "host": "localhost" }`.

- **Bare identifier as map key is now a parse error.** Using a bare identifier
  as a map key (e.g. `{ host: ... }` in a map context) was a silent runtime error
  in v2.x. In v3.0 it is a parse error with a helpful message naming the two
  correct forms.

- **`fs.*` and `json.*` errors are returned, not thrown.** `fs.read`, `fs.write`,
  `json.parse`, and similar stdlib functions now **return** an err record when
  they fail. They no longer throw a runtime error. `try/catch` still works for
  VM-level errors; returned err records are the preferred pattern for expected
  I/O and parse failures. Check with `type(result) == "error"`.

- **New err.kind values for stdlib failures.** Code that branched on
  `err.kind == "runtime"` to catch file or JSON errors will no longer match.
  The specific kinds are:

  | v2.x kind | v3.0 kind | What changed |
  |-----------|-----------|--------------|
  | `"runtime"` | `"io_error"` | `fs.read`, `fs.write`, `fs.listdir`, etc. |
  | `"runtime"` | `"parse_error"` | `json.parse` failures, `math.parse_int` failures |
  | `"runtime"` | `"type_error"` | `json.stringify` with non-serializable value, `math.idiv` with float args |
  | `"runtime"` | `"math_error"` | `math.idiv` division by zero |
  | (new) | `"value_error"` | Domain errors in math functions (`math.sqrt(-1)`) |
  | (new) | `"internal_error"` | Unexpected internal error in a wrapped stdlib function |

- **`err.payload` is always present.** In v2.x, `err.payload` was absent on
  runtime errors and string throws — accessing it raised `"Key error: Missing
  record field: payload"`. In v3.0, `err.payload` is always present and is `nil`
  for runtime errors and string throws. Existing guards (`has_key(err, "payload")`)
  are still safe; they return true where they previously returned false.

- **Integer type: `42i` literals, `type()` returns `"int"`.** v3.0 introduces
  the `int` type. Integer literals use the `i` suffix (`42i`, `0i`, `-1i`). Plain
  number literals (`42`) remain floats. `type(42i)` returns `"int"`; `type(42)`
  still returns `"number"`. Integer arithmetic (`int + int`) returns `int`;
  integer division always returns float. Code that checks `type(x) == "number"`
  for values that may now be integers should also check `type(x) == "int"`.

### Added

- **Integer type** (`42i` syntax, `"int"` type). New integer stdlib functions in
  `std:math`: `math.parse_int(s)`, `math.to_int(n)`, `math.to_float(n)`,
  `math.is_int(v)`, `math.idiv(a, b)`. Large integers maintain exact precision.
  Booleans continue to coerce to float in arithmetic.
- **`--trace-errors` CLI flag and `NODUS_TRACE_ERRORS=1` env var.** When set,
  prints the original Python exception to stderr whenever a stdlib function
  converts a Python exception to an err record. Script behavior is unchanged —
  `err.message` always contains only Nodus-voice text.
- **`docs/policy/error-surfaces.md`** — new policy doc describing the Replace
  contract, which stdlib surfaces are wrapped, and how to use `--trace-errors`.
- **`docs/migration/v2-to-v3.md`** — migration guide for all six breaking changes,
  "What does NOT break" section, and list of non-breaking v2.2 improvements.

### Fixed (v2.2 backlog, folded into v3.0)

- **`finally` now runs correctly in all cases** except the one known case where
  `catch` has a `return` (tracked as a v3.1 bug). Previously, `finally` was
  silently skipped in several exit paths.
- **Import errors inside function bodies and `if/else` blocks now work
  correctly.** Previously, a failed import inside a function body or `if/else`
  branch silently left the module name undefined instead of propagating the error.
- **Imports inside function bodies and `if`/`else` blocks now work correctly** —
  the module is loaded and the alias is defined in the enclosing scope, matching
  expected behavior. Note: import errors inside `try/catch` are still not catchable
  (the alias is left undefined and accessing it raises a `"name"` error); this
  is a known v3.1 bug, documented in error-handling.md §6.
- **`strings.is_blank` correctly returns `true` for whitespace-only strings.**
  Previously returned `false` for strings containing only spaces, tabs, or newlines.
- **`path.join` accepts a list of path segments.** `path.join(["a", "b", "c"])`
  joins a list of strings into a path. The function takes a single list argument,
  not variadic arguments.
- **`path.ext` now returns the leading dot.** `path.ext("file.nd")` returns
  `".nd"` (previously returned `"nd"`).
- **`utils.get(map, key, default)` added** — new function for safe map access
  with a default value when the key is absent.
- **Multi-line map literals work.** The value of a map entry can now start on
  the line after the `:` without a parse error.
- **`err.line`, `err.column`, `err.path`, `err.stack` are now documented fields.**
  These fields were always present but undocumented. `err.line` and `err.column`
  are `int` values in v3.0.
- **`type()` and `rt.typeof()` are now consistent and documented.** Previously
  the two functions returned different strings for the same value in some cases.
  `rt.typeof()` returns the runtime type name; `type()` returns the user-facing
  type name. See `docs/guide/types-and-values.md` for the complete comparison table.
- **`collections.has_key` O(n) shadow fixed.** The stdlib `has_key` function
  in `std:collections` was inadvertently shadowing the O(1) builtin `has_key`
  with an O(n) implementation.
- **`coalesce` now evaluates arguments lazily.** Previously `coalesce(a, b)`
  evaluated `b` even when `a` was non-nil.
- **Cyclic workflow dependency now errors correctly.** Previously, a workflow
  with a cyclic step dependency produced exit code 0 silently.
- **Stack overflow trace truncated.** Previously, a call stack overflow would
  print all 10,000 frames to stderr. Now truncated to a readable summary.
- **`nodus debug --help` no longer outputs "File not found".**
- **`nodus fmt --check` false-negative on fresh files fixed.**
- **`else if` is now valid syntax.** Previously required `else { if ... }` nesting.

### Documentation

- `docs/guide/types-and-values.md` — complete rewrite for v3.0: integer type
  section, `42i` syntax, arithmetic semantics, integer stdlib table, `{key: value}`
  disambiguation (record vs map), updated falsy values list, equality coercion
  documented as stable behavior.
- `docs/guide/error-handling.md` — major update: new stdlib err.kind table,
  err.payload always present, returned-not-thrown pattern documented, Section 5
  rewritten with guidance on try/catch vs. err-record checks, `--trace-errors`
  usage in Section 7.
- `docs/guide/standard-library.md` — v3.0 update: integer type additions,
  `json.parse_int`, updated fs error docs, rt.typeof comparison table corrected.

## [2.1.1] - 2026-05-24

### Security
- **BUG-046 — `allowed_paths` sandbox bypassed via `std:fs` module calls (CRITICAL):** `fs.read`, `fs.write`, `fs.append`, `fs.exists`, `fs.listdir`, and `fs.ensure_dir` now correctly enforce `NodusRuntime(allowed_paths=...)` restrictions. Previously, `NodusModule.invoke_function` created a new internal VM without forwarding `allowed_paths` or `fs_root` from the calling VM, allowing any embedded script to read or write arbitrary files by routing calls through the `std:fs` module. Direct builtin calls (`read_file`, `write_file`, etc.) were correctly sandboxed; stdlib wrappers were not. Also fixes the same bypass in CLI mode when `fs_root` enforcement is active. Path traversal via `std:fs` is now also blocked.

## [2.1.0] - 2026-05-24

### Added
- **BUG-020 — `has_key(map, key)` builtin:** New top-level builtin for O(1) map membership testing. No import required. Raises a `type` error when called on non-map values.
- **BUG-010 — Modulo operator `%`:** Integer and floating-point modulo now supported as a first-class arithmetic operator.
- **BUG-011 — Scientific notation literals:** Numeric literals in scientific notation (`1e3`, `2.5e-4`, `1E10`) are now parsed correctly by the lexer.
- **BUG-019 — `strings.replace(s, old, new)` / `str_replace` builtin:** New string replacement function available via `import "std:strings"` and as a raw builtin.

### Fixed
- **BUG-015 — Stdlib errors report user call site:** Runtime errors originating inside stdlib modules (e.g. `fs.read`, `math.sqrt`) now report the user's call site (file and line) instead of the internal stdlib file path. Implemented via `_is_stdlib_path()` helper and `_caller_vm` fallback in `build_runtime_error()`.
- **BUG-005 — `NodusRuntime.run_source` no longer raises on error:** The embedding API now catches all runtime and syntax errors and returns `{"ok": false, ...}` instead of propagating exceptions to the caller.
- **BUG-018 — `json.parse` returns maps, not records:** `json.parse` (and `json_parse` builtin) now returns plain maps, enabling `obj["key"]`, `keys(obj)`, `values(obj)`, and `has_key(obj, "key")`. Previously returned Record objects, which only supported dot notation.
- **BUG-022 — `print()` inside workflow/goal steps now visible:** Output from `print()` calls inside workflow and goal step functions is now captured and shown in CLI output.
- **BUG-027 — `throw` kind is `"thrown"` not `"runtime"`:** Throwing a string or primitive value (`throw "msg"`) now sets `err.kind = "thrown"`. Previously all throws reported `"runtime"`.
- **BUG-026 — `while` without parentheses gives helpful hint:** `while true { }` (missing parentheses) now produces: `while condition must be in parentheses: while (condition) { ... }` instead of a generic parse error.
- **BUG-008 — Unclosed string literal error message:** An unterminated string literal now reports `Unterminated string literal` instead of the misleading `Unexpected character`.
- **BUG-009 — Parser errors use ASCII hyphens:** Error messages in the parser used Unicode em-dashes (`—`). Replaced with ASCII hyphens (`-`) for terminal compatibility.
- **BUG-024 — `nodus init` prints success message:** `nodus init` now prints `Initialized Nodus project at <path>/` instead of silently succeeding.
- **BUG-028 — `--trace-no-loc` trailing whitespace removed:** Opcode lines emitted with `--trace-no-loc` no longer include trailing spaces when no context string is present.
- **BUG-001 / BUG-002 — `nodus check` / `nodus ast` / `nodus dis` `--help` handling:** `--help` after a subcommand is now handled correctly instead of being treated as a filename. `nodus check` now prints `OK` on success.
- **BUG-003 — `nodus check` help text accuracy:** Help text now correctly describes check as parse-only validation (does not detect undefined variable/function references).
- **BUG-023 — Unicode arrow in `NodusRuntime` docstring:** Replaced `→` with `->` in `embedding.py` docstrings, preventing `UnicodeEncodeError` on Windows CP1252 terminals.

### Documentation
- **BUG-014 — `foreach` removed from docs:** `foreach` does not exist in Nodus. All references in `LANGUAGE_VISION.md` and `docs/onboarding/NODUS.md` updated to `for item in list`.
- **BUG-021 — REPL.md lists `:modules` and `:reload`:** REPL command reference now matches the actual help text output by `nodus repl`.

## [2.0.1] - 2026-05-23

### Security
- **BUG-016 — path traversal in `fs.*` builtins (CRITICAL):** `read_file`, `write_file`, `append_file`, `mkdir`, `list_dir`, and `exists` now enforce a filesystem root in CLI mode. When no `allowed_paths` sandbox is active, scripts are restricted to the process working directory (or the `nodus.toml` project root when one is discovered). Paths that resolve outside this root raise a `sandbox` runtime error. Previously, any script could read or write arbitrary files on the host machine regardless of where `nodus run` was invoked.

### Fixed
- **BUG-017 — Python traceback on UTF-8 BOM files (CRITICAL):** Source files that begin with a UTF-8 BOM (`\xef\xbb\xbf`) — commonly produced by Windows editors — previously caused a raw Python `SyntaxError` or `UnicodeDecodeError` crash rather than a clean Nodus error. All file-read paths (`cli.py`, `module_loader.py`, `embedding.py`, `builtins/io.py`) now open files with `encoding="utf-8-sig"`, which transparently strips the BOM before parsing. `read_file()` also strips BOMs from data files read at runtime.
- **BUG-007 — `RecursionError` on 100+ nested parentheses (CRITICAL):** Deeply nested expressions (e.g. `((((…))))` with 100+ levels) caused Python's recursion limit to be exceeded, surfacing as an unhandled `RecursionError` traceback. The parser now tracks expression nesting depth and raises a `LangSyntaxError("Expression too deeply nested")` at depth 50, well before Python's stack limit is reached.

### Changed
- **PyPI classifier downgrade:** `Development Status :: 5 - Production/Stable` → `Development Status :: 4 - Beta`. The v2.0.0 stress-test evaluation revealed three CRITICAL bugs that disqualify a Production/Stable rating.

## [2.0.0] - 2026-05-23

### Fixed
- **CI lint regression (Phase 5A):** Two ruff errors introduced in Phase 6 test additions (commit `0568185`) caused the `ruff check .` CI gate to exit 1. Fixed `tests/test_run_trace.py:64` (E741: renamed ambiguous loop variable `l` -> `line`) and `tests/test_workflow_unification.py:56` (F841: removed unused `exit_code` assignment from `test_workflow_no_args_shows_usage`). `ruff check .` now exits 0.
- **`--trace-imports` Windows encoding crash (Phase 5B):** `src/nodus/runtime/module_loader.py` used the Unicode arrow `→` (U+2192) in the `[import] Resolved` output line and an em dash `—` (U+2014) in the `[import] Failed` line. Both characters are non-ASCII; the arrow is not encodable in Windows CP1252, causing `UnicodeEncodeError` when `--trace-imports` wrote to a CP1252 terminal. Replaced `→` with `->` and `—` with `--` (ASCII equivalents). Existing tests were unaffected because they redirect stderr to `io.StringIO()`.
- **CHANGELOG.md E402 count discrepancy (Phase 5B):** Corrected the E402 fix count in the Refactoring section from 8 to 11. The actual count resolved in commit `b9e6418` was 11, matching the git commit message and AUDIT_REPORT_2.md baseline.
- **TECH_DEBT.md vm.py line count stale (Phase 5B):** Updated from "2,418 lines as of v1.1.2" to "2,438 lines as of v1.1.2 (post-Phase 6)" to reflect the +20 lines added for `builtin_memory_has` in Phase 6.

### Documentation
- **README.md: JSON-LD structured metadata (Phase 5C):** Added a `<script type="application/ld+json">` block at the end of `README.md` with `schema.org/SoftwareApplication` metadata (name, description, author, category, language, OS, URLs, license, version, Python requirement). Improves discoverability by AI indexers and search engines.
- **LANGUAGE_SPEC.md: `--strict` flag and `nodus status` added (Phase 5B):** Added a "Run mode flags" entry documenting `--strict` (disables project auto-discovery, requires explicit file path) and `--trace-imports` (ASCII format). Added `nodus status` to the CLI commands section describing its three-field output and always-zero exit behavior.

### Added
- **AUTHORS file (Phase 5C):** Added `AUTHORS` at the project root listing Shawn Knight as the sole author with a GitHub profile link. Standard file for PyPI/GitHub attribution.
- **Cross-platform documentation (Task 7.2):** Audited `CONTRIBUTING.md` and `docs/onboarding/DEVELOPMENT.md` for shell commands that differ between bash and PowerShell. All three bash-only constructs in `CONTRIBUTING.md` now have adjacent PowerShell equivalents: `source .venv/bin/activate` ↔ `.venv\Scripts\Activate.ps1` (pre-existing), `pip install dist/*.whl` ↔ `pip install (Get-Item dist\*.whl).FullName` (added by Task 7.1), and `NODUS_RUN_DIST_SMOKE=1 python -m pytest ...` ↔ `$env:NODUS_RUN_DIST_SMOKE = "1"; python -m pytest ...` (added by Task 7.1). `DEVELOPMENT.md` contains no platform-diverging shell commands (all invocations use `nodus <tool> file.nd` or `python` forms that are identical across platforms); no changes required.
- **CI distribution validation (Task 7.1):** CI pipeline now has an explicit `Build wheel` step (`python -m build --wheel`) that runs after `Install build tooling` and before the smoke test, making the wheel build visible as its own CI step. The `Installed wheel smoke test` step was already gated by `NODUS_RUN_DIST_SMOKE: "1"` and creates an isolated venv for clean-install verification. Added `nodus --help` smoke check to `tests/test_distribution_smoke.py` (verifies exit 0 and "Usage" in stdout). Updated `_build_wheel` to reuse a pre-built wheel from `dist/` when available (avoids a redundant second build in CI). `CONTRIBUTING.md` updated with a new "Distribution Testing" section documenting the wheel build and smoke-test commands.
- **Execution trace format update (Task 6.2):** `nodus run --trace` now writes opcode trace lines to **stderr** (previously stdout) with the format `[trace] <OPCODE padded to 14 chars>  line N  <context>`. Opcode-specific context: `CALL` shows `fn=<name>`, `LOAD`/`STORE` show `name=<var>`, `LOAD_FIELD`/`STORE_FIELD` show `field=<name>`, `PUSH_CONST` shows `val=<repr>`, `JUMP` shows `target=<ip>`. `--trace-no-loc` omits the `line N` field. Existing `--trace-filter` and `--trace-limit` flags are unchanged. Three existing tests in `tests/test_nodus.py` updated to capture stderr; 6 new tests added in `tests/test_run_trace.py`. `_COMMAND_HELP["run"]` updated to note high-volume stderr output.
- **Memory API stabilization (Task 6.1):** Added `memory_has(key)` top-level builtin and `has(key)` method to `std:memory`. The previous `has` implementation incorrectly used `value != nil` and returned `false` when `nil` was stored under a key; it now calls `memory_has` which checks key existence directly. `memory_has` is registered in `BUILTIN_NAMES`, the VM builtin dispatch, and `memory_runtime.py`. All four stable methods (`put`, `get`, `delete`, `has`) and their top-level counterparts are now fully tested. Non-string keys raise a runtime `TypeError` across all methods. `LANGUAGE_SPEC.md` updated with a dedicated Memory API section. Tests added in `tests/test_memory_api.py` (19 tests).
- **Path traversal error message improvement (Task 5.1):** The error raised when a relative import would escape the project root now names the offending path: `Invalid import: path '../outside.nd' escapes the project root.` Previously the message did not include the path. The check continues to fire before any filesystem access, in both project mode (explicit `nodus.toml`) and single-file mode (no manifest, root defaults to entry file's directory). Tests added in `tests/test_path_traversal.py` (6 tests covering: project-mode rejection, error message names the path, in-tree relative import accepted, double-dot chain blocked, single-file-mode rejection, single-file in-tree accepted). `LANGUAGE_SPEC.md` and `docs/governance/TECH_DEBT.md` updated.
- **REPL import parity verified and tested (Task 5.2):** The REPL uses the same `ModuleLoader` and `resolve_import_path` code path as CLI execution. Automated tests in `tests/test_repl_import_parity.py` confirm: (1) bare project-root-relative imports resolve from project root in the REPL, (2) path traversal (`../outside.nd`) is blocked in the REPL with the same error as CLI, (3) `lib/index.nd` fallback resolution works in the REPL. No separate REPL import code path exists or was introduced.
- **CLI help system (Task 1.1):** Every primary subcommand now has a per-command `--help` that shows usage, a one-sentence description, all options with descriptions, and at least two examples. Commands covered: `run`, `repl`, `init`, `check`, `fmt`. Implemented via a `_COMMAND_HELP` dict in `src/nodus/cli/cli.py`; `--help` after a command no longer falls through to the global help.
- **Execution transparency (Task 1.3):** `nodus run` now prints two lines to stderr when auto-discovering a project (no file argument, or a directory argument): `Running project from: <absolute path>` and `Entry: <relative path>`. Single-file invocations (`nodus run script.nd`) are unchanged. Tests added in `tests/test_project_run_header.py`.
- **Project-root-relative imports (Task 3.1):** Bare import paths (no leading `./`) resolve against the project root first, then `.nodus/modules/`, then stdlib. When all fail, the error message now names all paths tried including stdlib candidates. Tests added in `tests/test_bare_imports.py`.
- **Index module support (Task 3.2):** When a bare or relative import path has no extension and no exact file match, Nodus now checks `<path>/index.nd` and `<path>/index.tl` as fallbacks. Resolution order: `path.nd` → `path.tl` → `path/index.nd` → `path/index.tl`. Tests added in `tests/test_bare_imports.py`.
- **`nodus run --trace-imports` flag (Task 3.3):** When set, prints one `[import] Resolved "path" → /abs/path` line to stderr for each import resolved at module-load time. Failed imports print `[import] Failed "path" — <reason>` before the error is raised. No effect on execution behavior. Tests added in `tests/test_trace_imports.py`.
- **Strict run mode (Task 2.2):** `nodus run --strict` disables project auto-discovery and requires an explicit file path. Without a file argument it prints `Error: --strict mode requires an explicit file path.` and exits non-zero. The flag is documented in `nodus run --help`. Tests added in `tests/test_strict_mode.py`.
- **`nodus status` command (Task 2.3):** New command that reports the project root, entry file, and working directory that would be used if `nodus run` were called from the current directory. Prints `No project found in current directory` when no `nodus.toml` is reachable; always exits 0. Appears in `nodus --help`. Help text available via `nodus status --help`. Tests added in `tests/test_status_command.py`.
- **Context-aware REPL prompt (Task 4.2):** `run_repl()` now calls `load_project_from(os.getcwd())` at startup. When a project is found the prompt becomes `nodus (<name>)> `; without a project it shows `nodus> `. The `ModuleLoader` is also initialised with the project root rather than raw cwd when a project is detected, so bare imports resolve correctly inside the REPL.
- **REPL error deduplication verified (Task 4.3):** Investigation confirmed the REPL prints exactly one error message per failed user action; `_execute_source` raises exceptions rather than printing them, and the `run_repl` loop prints exactly once via `format_error`. Two regression tests added to `tests/test_repl_commands.py` (`ReplErrorDeduplicationTests`) to lock this behaviour in place.
- **REPL `:modules` and `:reload` commands (Task 4.1):** `:modules` lists all modules imported in the current REPL session (paths from `import_state["loaded"]`), or prints `No modules imported.` when the session is clean. `:reload` clears session state and recreates the VM and loader, then prints `REPL session restarted.`. Unknown colon-commands now print `Unknown REPL command ':xyz'. Type :help for available commands.` instead of raising an exception. `:help` output updated to include all seven commands. `execute_repl_command` return type extended to a 4-tuple `(handled, output, should_exit, should_reload)`. Tests updated in `tests/test_repl_commands.py`; 5 new tests added.
- `llms.txt` at project root: machine-readable AI crawler index with project name, tagline, creator attribution, key concept definitions, and links to 8 key documents.

### Changed
- **CLI command visibility (Task 1.2):** `nodus --help` now shows `nodus init` instead of the internal `package-init` alias. `login`, `logout`, and `publish` added to the known-commands dispatch table (they were listed in help but silently failed at runtime). `nodus --help` now requires `--help` to be the first argument; `--help` after a command routes to per-command help.
- **Parser error messages (Task 1.4):** Parser errors no longer expose raw token kind names (`ID`, `COLON`, `RBRACE`, etc.). All error messages in `eat()`, `parse_pattern()`, and `parse_primary()` now use human-readable terms: `identifier` for `ID`, `end of file` for `EOF`, `end of statement` for `SEP`, `'{'`/`'}'` for brace tokens, etc. Context-specific hints added for `Unexpected '}'` and `Unexpected end of file` in expression position.

### Changed
- `pyproject.toml` `[server]` optional extras now pin `fastapi>=0.136.0,<1` and `uvicorn>=0.30.0,<1`; lower bound raised to the tested 0.136 series after a clean upgrade from 0.111.0.
- CI: `permissions: contents` downgraded from `write` to `read`; the job no longer requires write access now that the auto-format commit step has been removed.
- `pyproject.toml` `filterwarnings`: removed `ignore::PendingDeprecationWarning:starlette` suppression — starlette 1.0.1 no longer emits the python_multipart `PendingDeprecationWarning`.

### Security
- Updated `certifi` 2026.2.25 → 2026.5.20 (security certificate bundle; pinned in `requirements.txt`).
- Updated `idna` 3.11 → 3.16 (IDNA protocol library; pinned in `requirements.txt`).
- Updated `fastapi` 0.111.0 → 0.136.1 and `starlette` 0.37.2 → 1.0.1; both pinned in `requirements.txt`. The `services/server.py` FastAPI code (`FastAPI()`, `@app.middleware("http")`, `@app.get/post/delete` decorators, `Request`, `JSONResponse`, `request.json()`) is compatible with starlette 1.0 — no `on_startup`/`on_shutdown`, no bare `@app.route()`, no removed Starlette-level decorators are used. All 413 pytest tests pass against the upgraded versions.

### Fixed
- CI: `test_formatter_foreach.py` was silently excluded from the CI `unittest` runner. Added a `Pytest` step (`python -m pytest -q`) so pytest-style tests are covered.
- CI: Auto-format step that committed `.nd` changes directly to the branch on every push has been removed. Format enforcement is now check-only via the existing `nodus fmt --check` step.
- `nodus.py` shim: `main` was referenced in the `__main__` block without an explicit import (ruff F821). Added `from nodus.cli.cli import main` inside the block so the name is unconditionally resolved.
- `src/nodus/frontend/types.py`: replaced `exec(compile(...))` pattern with explicit `from types import ...` statements. No behavior change; removes exec() risk and makes the module statically analysable.
- `src/nodus/runtime/project.py`: removed 9 unused imports (`DependencySpec`, `create_project`, `find_project_root`, `load_manifest`, `load_project`, `load_project_from`, `parse_dependencies`, `read_lockfile`, `write_lockfile`). None were referenced in the file body or consumed via re-export from this module.

### Improved
- None.

### Documentation
- `README.md`: added Shawn Knight creator attribution and Masterplan Infinite Weave / Infinity Algorithm canonical definition in the opening paragraph; added CI, PyPI, and license badges; added Documentation section with links to language spec, architecture, changelog, contributing guide, and llms.txt.
- `CONTRIBUTING.md`: updated repository structure diagram from stale flat layout to current `src/nodus/` package structure; fixed `requirements-dev.txt` reference to `requirements.txt`; fixed `LANGUAGE_SPEC.md` bare reference to `docs/language/LANGUAGE_SPEC.md`.
- `docs/onboarding/DEVELOPMENT.md`: updated all core component file references from bare filenames to full `src/nodus/` paths (`src/nodus/frontend/lexer.py`, `src/nodus/frontend/parser.py`, `src/nodus/frontend/ast/ast_nodes.py`, `src/nodus/compiler/compiler.py`, `src/nodus/vm/vm.py`, `src/nodus/orchestration/task_graph.py`, `src/nodus/orchestration/workflow_lowering.py`).

### Tests
- **CI: Coverage gate added (Phase 5C):** Added a `Coverage` step to CI running `pytest --cov=src/nodus --cov-report=term-missing --cov-fail-under=60`. Three timing-sensitive tests are deselected from the coverage run (they pass in the regular `Pytest` step but fail under instrumentation overhead): `test_scheduler_fairness.py::test_multiple_tasks_progress`, `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`, `test_task_graph.py::TaskGraphTests::test_worker_death_detection`. Overall baseline: 77% (14,232 stmts). `pytest-cov==7.1.0` added to `requirements.txt`.
- **CI: GitHub Actions SHA pinning (Phase 5C):** Both `actions/checkout` and `actions/setup-python` are now pinned to 40-character commit SHAs with inline version comments. `actions/checkout v4.3.1` → `34e114876b0b11c390a56381ad16ebd13914f8d5`; `actions/setup-python v5.6.0` → `a26af69be951a213d495a4c3e4e4022e16d87065`. Prevents supply-chain attacks via tag mutation.
- **CI: mypy non-blocking baseline (Phase 5C):** Added a `Type check` step with `continue-on-error: true` running `mypy src/nodus/ --ignore-missing-imports --no-error-summary`. Current baseline: 208 errors across 29 modules (top offenders: `cli/cli.py` 49, `vm/vm.py` 24, `formatter.py` 18, `task_graph.py` 18). Baseline recorded in `TECH_DEBT.md`. `mypy==2.1.0` added to `requirements.txt`; `[tool.mypy]` section added to `pyproject.toml`.
- CI: Added `Lint` step (`ruff check .`) positioned immediately after `Set up Python`, before all test and format steps. The step fails the build on any lint error, surfacing the existing backlog of 77 errors.

### Refactoring
- **`BuiltinRegistry` extracted to `builtins/registry.py` (Phase 5C):** Moved `BuiltinRegistry` class from `src/nodus/builtins/__init__.py` to `src/nodus/builtins/registry.py`. `__init__.py` now re-exports it with `# noqa: F401`. `register_all()` moved to the class body; all four category-module registrations (`io`, `math`, `coroutine`, `collections`) are performed there. Only `vm.py` imported `BuiltinRegistry` from `nodus.builtins`; no consumer changes required.
- **`src/nodus/__init__.py` function-body imports removed (Phase 5C):** Three wrapper functions (`resolve_imports`, `run_source`, `main`) that existed only to provide lazy-import deferred loading were replaced with `__getattr__` handlers plus `globals()` caching. Startup cost unchanged (imports still deferred); module-body wrapper definitions eliminated. `if __name__ == "__main__"` updated to use `__getattr__("main")()`.
- **Lint cleanup — ruff error count 66 → 0** (Phase 4A): resolved all outstanding ruff errors so CI passes on every push.
  - F811: removed duplicate `import threading` at `services/server.py:48`; kept the import at line 12.
  - F401 (46): removed 45 unused imports across `builtins/collections.py`, `lsp/server.py`, `orchestration/workflow_lowering.py`, `runtime/errors.py`, `services/server.py`, `tooling/analyzer.py`, `tooling/loader.py`, `tooling/registry_client.py`, `tooling/runner.py`, `tooling/user_config.py`, `vm/vm.py`, and test files; `runtime/semver.py` re-exports protected with `# noqa: F401`.
  - E402 (11): moved `TASK_STEP_BUDGET` constant in `runtime/scheduler.py` to after imports; moved `from nodus.support.version import VERSION` in `services/server.py` to top-level import block; added `# noqa: E402` to `cli.py`, `language.py`, and `task_graph.py` shims where imports must follow `sys.path` manipulation.
  - E401 (2): split multi-import lines in `tmp_demo/` (auto-fixed).
  - F841 (6): removed `scheduler_hint` initial declaration and intermediate assignment in `orchestration/task_graph.py`; removed unused `by_id` dict in `orchestration/task_graph.py`; removed dead `else_header` in `tooling/formatter.py`; narrowed `except Exception as err:` to `except Exception:` in `lsp/server.py`; dropped unused assignment targets in `tests/test_incremental_compilation.py` and `tests/test_registry_client.py`.

## [1.1.2] - 2026-04-27

### Added
- `nodus repl` CLI command.

### Fixed
- duplicate execution when both `main.nd` and `src/main.nd` exist.
- circular import detection with full chain reporting.
- stdlib packaging issues.

### Changed
- clarified execution behavior for `nodus run`.

### Notes
- runtime behavior is now consistent between development and installed environments.

## 1.1.1 - 2026-04-26

### Added
- Optional `server` install extra for FastAPI/Uvicorn: `pip install "nodus-lang[server]"`.

### Changed
- `nodus check` now mirrors `nodus run` project resolution and can validate the default project entry file when invoked with no explicit file from a project directory.
- HTTP server docs now identify canonical route names and compatibility aliases for overlapping endpoint names.

### Improved
- Added installed-wheel smoke coverage for the packaged `nodus` CLI, including `run`, `init`, `repl`, `serve`, and stdlib import resolution.

### Documentation
- Clarified that `nodus serve` is the canonical user-facing HTTP API surface.
- Documented optional server dependency behavior for plain installs versus `nodus-lang[server]`.

### Tests
- Added installed-wheel distribution smoke validation.
- Added CLI coverage for `nodus check` project-root and project-directory resolution.

## 1.1.0

* Added automatic `main()` execution
* Introduced installable PyPI package (`nodus-lang`)
* Cleaned repository boundary (removed A.I.N.D.Y. concepts)
* Clarified execution model

## [0.9.0] - 2026-03-15 — Registry Auth, Publish & Ecosystem Completeness

### Added
- **Registry authentication**: Bearer token support via `--registry-token` flag, `NODUS_REGISTRY_TOKEN` env var, and `~/.nodus/config.toml` user config file. Three-tier resolution: flag > env > config.
- **`nodus login` / `nodus logout`** commands: write and clear the registry token in `~/.nodus/config.toml`.
- **`nodus publish`**: uploads a package archive to the registry via POST with SHA-256 digest sent as `X-SHA256` header. 409 Conflict returns a clear error. Implemented via `create_package_archive()` and `publish_package()`.

### Changed
- `compile_source()` public re-export removed from `nodus.__init__`; loader body retained in `nodus.tooling.loader` for internal use until v1.0.

### Fixed
- CI: `tests/test_formatter_coverage.py` was using `import pytest`, causing `ModuleNotFoundError` in the unittest-based CI runner. Converted to `unittest.TestCase`.

### Documentation
- `CONTRIBUTING.md`: replaced stale `pytest` commands in the Running Tests section with `python -m unittest` equivalents.
- `docs/tooling/TESTING.md`: added `test_formatter_coverage.py` entry to the Formatter Test Files section; updated Known Flaky Tests run command from `python -m pytest` to `python -m unittest`; removed stale `pytest` alternative from Running Tests.

### Tests
- 11 new tests covering registry authentication: token resolution priority (flag > env > config), `nodus login`/`nodus logout`, and Bearer token header injection.
- 9 new tests covering publish: archive creation, POST upload, `X-SHA256` header, and 409 Conflict handling.
- Converted `tests/test_formatter_coverage.py` from pytest to `unittest.TestCase` (CI fix).

### Provisional Opcodes
- `GET_ITER`/`ITER_NEXT` `pending_get_iter` cleanup deferred to v1.0 by design; behavior documented in `INSTRUCTION_SEMANTICS.md`.
- Exception model: `finally` blocks and typed catches deferred to v1.0. `SETUP_TRY`, `POP_TRY`, and `THROW` remain provisional.

## [0.8.0] - 2026-03-15 — Stability and Package Ecosystem

### Added
- **Registry-backed package resolution**: new `RegistryClient` (`src/nodus/tooling/registry_client.py`) fetches package index, resolves semver constraints, downloads archives with SHA-256 verification, and extracts to `.nodus/_staging/`. Registry URL resolved from `--registry` flag, `NODUS_REGISTRY_URL` env var, or `registry_url` in `nodus.toml`. 12 new tests in `tests/test_registry_client.py`.
- **FRAME_SIZE opcode**: pre-allocates `frame.locals_array` (list of N slots) at function entry. First instruction of every compiled function body. Bytecode version bumped to `BYTECODE_VERSION = 2`.
- **LOAD_LOCAL_IDX opcode**: slot-indexed read from `frame.locals_array[slot]`; replaces name-keyed `LOAD_LOCAL` for all function-scope locals. ~40%+ hot-loop improvement over name-keyed dict lookup.
- **STORE_LOCAL_IDX opcode**: slot-indexed write to `frame.locals_array[slot]`; handles Cell boxing in-place for closure capture. Emitted for all let-bindings, assignments, loop variables, catch variables, and destructuring targets.
- **Opcode freeze proposal**: `docs/governance/FREEZE_PROPOSAL.md` — formal stability table for all 47 opcodes (39 stable, 7 provisional, 1 deprecated), freeze prerequisites, post-freeze extension process, and version history.
- **Formatter coverage complete**: handlers added for `Yield`, `Throw`, `TryCatch`, `DestructureLet`, `VarPattern`, `ListPattern`, `RecordPattern`. New `format_pattern()` helper. All 48 AST node types now covered. See `tests/test_formatter_coverage.py`.

### Changed
- `Frame` dataclass extended with `locals_array: list | None` and `locals_name_to_slot: dict[str, int] | None`. `STORE_ARG` syncs to both `locals` dict and `locals_array`.
- `SymbolTable.define()` now assigns `Symbol.index` (local slot) for function-scope symbols. `Upvalue.index` carries the local slot when `is_local=True`.
- `FunctionInfo` gains `local_slots: dict[str, int]` field; serialized to/from bytecode cache.
- `capture_local()` prefers `locals_array` path when available; Cell boxing goes through array slot.
- `ProjectConfig` gains optional `registry_url` field; written to `nodus.toml` when set.
- LSP server `serverInfo.version` bumped to `0.8.0`.

### Fixed
- LSP `_uri_to_path` now uses `os.path.realpath` instead of `os.path.abspath`, normalising double-slash paths (`//tmp/…`) that arise from 4-slash `file:////…` URIs on Linux.
- LSP `_publish_diagnostics` echoes back the exact URI registered via `textDocument/didOpen` instead of reconstructing one, preventing URI mismatches on Linux.

### Deprecated / Removed
- `compile_source()` internal callers fully migrated to `ModuleLoader` in v0.8. Public stub in `nodus.__init__` retained with `DeprecationWarning` until v1.0. All 24 test files migrated to `ModuleLoader.compile_only()`.
- `LOAD_LOCAL` opcode classified **deprecated**; retained as fallback only. Removal target: v1.0 after full bytecode migration.

### Documentation
- `docs/governance/FREEZE_PROPOSAL.md`: new — opcode stability classifications and v1.0 freeze process.
- `docs/runtime/BYTECODE_REFERENCE.md`: added FRAME_SIZE, LOAD_LOCAL_IDX, STORE_LOCAL_IDX entries; opcode count updated to 47; reference to FREEZE_PROPOSAL.md added.
- `docs/governance/TECH_DEBT.md`: GET_ITER/pending_get_iter cleanup and Exception model finalization sections added; all v0.8 items marked complete.
- `docs/governance/ROADMAP.md`: all five v0.8 goals marked ✅.
- `docs/language/FORMAT.md`: formatting rules for Yield, Throw, TryCatch, DestructureLet.
- `docs/tooling/PACKAGE_MANAGER.md`: Registry Installation section added.
- `docs/tooling/TESTING.md`: corrected CI step description; updated formatter test authoring guidance.

### Tests
- `tests/test_formatter_coverage.py`: 7 new tests covering all previously-missing AST formatter nodes.
- `tests/test_registry_client.py`: 12 new tests covering HTTP fetch, semver resolution, checksum verification, install/extract, and full integration flow.
- Rewrote `tests/test_formatter_fnexpr.py` as a `unittest.TestCase` class.

## [0.7.0] - 2026-03-15 — Runtime Orchestration, Diagnostics, Debugging, and Sprint Fixes

### Added
- Incremental module compilation backed by a persistent dependency graph (`.nodus/deps.json`).
- Disk bytecode cache for compiled modules (`.nodus/cache/*.nbc`).
- DAP debug adapter over stdio with `nodus dap`.
- LSP server with completion, hover, go-to-definition, and diagnostics.
- Workflow persistence snapshots and checkpoint files under `.nodus/graphs/`.
- Workflow management CLI commands: `nodus workflow list`, `nodus workflow resume`, `nodus workflow cleanup`.
- `NodeVisitor` base class (`src/nodus/frontend/visitor.py`) — automatic `visit_<ClassName>` dispatch for all AST walkers.
- `BuiltinRegistry` class (`src/nodus/builtins/__init__.py`) — category modules (`io`, `math`, `coroutine`, `collections`) register builtins at VM construction time.
- String escape sequences: `\r`, `\0`, `\xHH`, `\uXXXX` now supported in the lexer.
- Import chain depth limit: configurable via `NODUS_MAX_IMPORT_DEPTH` env var (default 100); raises `LangSyntaxError` instead of `RecursionError`.
- Formatter handlers for `FnExpr` (anonymous functions), `FieldAssign` (`obj.field = val`), and `RecordLiteral` (`record { ... }`).
- CI auto-formats `examples/*.nd` before the format check and commits back with `[skip ci]`.

### Changed
- Runtime module loader now skips recompilation when dependency mtimes are unchanged.
- Workflow resume logic rehydrates persisted task state and scheduler order.
- `nodus deps` now reports the incremental compilation dependency graph.
- `compile_source()` marked deprecated since v0.5.0; `ModuleLoader(...).load_source(src)` is the canonical pipeline. Removal target: v1.0.
- AST `Base` dataclass carries explicit `_tok` and `_module` fields (excluded from `__repr__`/`__eq__`) on all node types.
- Bytecode cache format changed from `pickle` to `marshal` with `NDSC` magic header + format version byte + SHA-256 integrity check. Eliminates pickle's arbitrary-code-execution risk.
- Channel `waiting_receivers` / `waiting_senders` converted from `list` to `collections.deque`; `pop(0)` replaced with `popleft()` (O(1)).
- Optimizer `collect_jump_targets()` hoisted to once per outer fixed-point iteration; O(n) list-equality dirty-detection fallback removed in favour of a boolean `changed` flag.
- Legacy `.tl` files removed from `examples/`; `examples/` now contains only `.nd` files.

### Fixed
- `decode_string_literal` now raises `LangSyntaxError` directly with line/col rather than bare `SyntaxError`; tokenize() re-raise workaround removed.
- Optimizer bool constant folding normalised: arithmetic ops convert bool operands to int before folding to match VM runtime semantics.
- `builtin_close` now guards receiver wake-up with `state == "suspended"` check to prevent waking non-suspended coroutines.

### Improved
- VM `execute()` dispatch replaced `if/elif` chain with a dict dispatch table (`_build_dispatch_table()`). Benchmark: 388 ms → 260 ms (~33% throughput improvement).
- `LOAD_LOCAL` opcode: compiler emits `LOAD_LOCAL name` instead of `LOAD name` for confirmed function-local variables, bypassing the 4-scope probe in `load_name()`. Benchmark: ~21% additional improvement on tight loops.
- Scheduler fairness via round-robin execution and `TASK_STEP_BUDGET` enforcement.
- LSP diagnostics are dependency-aware with cross-module publishing and incremental refresh.
- Debugger integration reused by both interactive debugger and DAP server.
- Workflow checkpoint handling preserves upstream task outputs while rolling back downstream steps.

### Documentation
- Added/updated docs for LSP, DAP, debugging entrypoints, workflow persistence, and scheduler fairness.
- Documentation synchronisation pass: FORMAT.md, TESTING.md, BYTECODE_REFERENCE.md, RELEASE_CHECKLIST.md, TECH_DEBT.md, GETTING_STARTED.md updated to reflect Phases 1–4.

### Tests
- Added coverage for bytecode cache, incremental compilation, scheduler fairness, workflow persistence, LSP diagnostics, and DAP server behavior.
- Added/expanded tests for module isolation and runtime module objects.
- Added `tests/test_formatter_fnexpr.py` covering FnExpr, FieldAssign, RecordLiteral formatting.

### Refactoring
- `_StateRewriter` documented in `src/nodus/runtime/workflow_lowering.py`.

## [0.5.0] - 2026-03-14 — Interactive Shell and Inspection

### Added
- REPL multiline editing with `... ` continuation for brace-delimited blocks.
- Persistent REPL history via `~/.nodus_history` when Python `readline` is available.
- REPL inspection commands: `:ast <expr>`, `:dis <expr>`, `:type <expr>`, `:help`, and `:quit`.
- Dedicated REPL documentation in `docs/tooling/REPL.md`.
- Profiler documentation and runtime integration for the 0.5.0 tooling milestone.

### Changed
- REPL inspection output now supports compact expression AST views and expression bytecode inspection.
- Onboarding and runtime docs now describe the interactive shell workflow and inspection commands.
- Project metadata now aligns on version `0.5.0`.

### Fixed
- None.

### Removed
- None.

## [0.4.x Tracking]
- Module bytecode unit format and bytecode version headers.
- Minimal runtime module objects and debugger MVP.
- Semver parsing and lockfile format groundwork.

## [0.4.0] - 2026-03-14 — Runtime Architecture & Packaging

### Added
- Bytecode version headers in compiled modules.
- Runtime sandbox limits (steps/time/stdout).
- Embedding API for host execution and host function registration.
- Runtime module system with module objects and caching.
- Per-module bytecode units and per-module global namespaces.
- Project manifest parsing (`nodus.toml`) and dependency resolution.
- `nodus.lock` lockfile generation with resolved metadata.
- Debugger MVP with breakpoints, stepping, stack inspection, and variable inspection.
- Tooling-side package management modules for project parsing, semver, dependency resolution, installation, and registry metadata.
- Deterministic `[[package]]` lockfile entries with `name`, `version`, `source`, and `hash`.
- Test coverage for installer behavior, lockfile generation, runtime loading from `.nodus/modules`, and manifest/resolution flows.

### Changed
- Imports now resolve through the runtime module loader with dependency-first resolution.
- Module execution is isolated per module with cached module objects.
- Tooling execution flows updated for module-based runtime execution.
- CLI includes `nodus update` for dependency refresh.
- Refactored package management so runtime execution no longer performs manifest parsing, dependency resolution, registry access, or network operations.
- Installed dependencies now live under `.nodus/modules/` instead of `deps/`.
- Runtime module loading now resolves imports in the order: local project modules, `.nodus/modules/`, then standard library.
- `nodus install` and `nodus update` now route through tooling-side resolution and installation.

### Internal
- Module loader integrates project manifests, lockfile resolution, and dependency paths.
- VM supports module-bound function wrappers for module exports.
- Package manager routes through the runtime project system and lockfile format.

### Tests
- Added coverage for manifest parsing, semver ranges, and dependency resolution.
- Updated package tests for the new lockfile format and module execution behavior.

### Fixed
- Worker-required tasks always dispatch through the worker manager.

### Removed
- Package-management responsibilities from the runtime project/loading path.

## [0.3.0] - 2026-03-13

### Added
- Workflow and goal syntax with task graph planning, execution, resume, and checkpoints.
- Cooperative coroutines, scheduler, and channels (`coroutine`, `resume`, `spawn`, `run_loop`, `sleep`, `channel`, `send`, `recv`, `close`).
- Runtime event bus with human/JSON sinks and CLI flags `--trace-events`, `--trace-json`, `--trace-file`.
- Service mode `nodus serve`, session snapshots (`nodus snapshot`, `nodus snapshots`, `nodus restore`), and worker registration (`nodus worker`).
- Orchestration CLI commands: `nodus graph`, `workflow-*`, `goal-*`.
- Runtime service CLI commands: `tool-call`, `agent-call`, `memory-get`, `memory-put`, `memory-keys`.
- Package management commands: `nodus init`, `nodus install`, `nodus deps` with `nodus.toml`/`nodus.lock`.
- Stdlib modules: `std:json`, `std:math`, `std:runtime`, `std:tools`, `std:memory`, `std:agent`, `std:async`, `std:utils`.
- Editor support: TextMate grammar, VS Code config, and snippets under `tools/vscode/`.
- Inspection tooling: `nodus ast`, `nodus dis`, `nodus ast --compact`, `nodus dis --loc`.
- Debug command: `nodus debug`.
- Example smoke test command: `nodus test-examples`.
- Added `examples/project_layout_demo/` as a small multi-file onboarding example.

### Changed
- Formatter preserves integer-looking numeric literals and uses a dedicated unary minus AST node.
- Trailing comment behavior clarified and `--keep-trailing` option added.
- `nodus run` adds `--no-opt`, `--project-root`, scheduler tracing, and trace filters/limits.
- Bytecode reference updated to document the `NEG` opcode explicitly.

### Fixed
- Expire polling workers after heartbeat timeout to ensure dead workers are removed promptly.

### Removed
- None.

## [0.2.0] - 2026-03-11

### Added
- Module system (imports/exports, selective imports, re-exports, `std:` aliases).
- Deterministic import resolution with package/index support and project-root overrides.
- Standard library modules: `std:strings`, `std:collections`, `std:fs`, `std:path`.
- `nodus fmt` (formatter) with `--check` and comment handling controls.
- `nodus check` for syntax/import/compile validation without execution.
- Debug flags: `--dump-bytecode` and `--trace` with controls.
- CI workflow via GitHub Actions.
- Release discipline docs: `RELEASE_CHECKLIST.md`, `VERSIONING.md`, `COMPATIBILITY.md`.

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).
- Centralized version metadata in `version.py`.
- Compatibility: `.tl` extension still supported with warnings; legacy launchers remain available.

### Fixed
- None.

### Removed
- None.

## [0.1.0] - 2026-03-09

### Added
- Modular runtime architecture (lexer, parser/AST, compiler, VM, loader).
- Imports/exports with selective and namespaced imports.
- Deterministic import resolution with `std:` aliases.
- Stack traces with source mapping.
- Debugging flags: `--dump-bytecode` and `--trace`.
- Package/index resolution and project-root overrides.
- Re-export support (`export { name } from "./mod.nd"`).

### Changed
- Primary source extension is `.nd` (legacy `.tl` remains supported).
- Public CLI is `nodus` (legacy launchers still supported).

### Fixed
- None.

### Removed
- None.
