# Changelog

## [Unreleased]

### Changed

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
