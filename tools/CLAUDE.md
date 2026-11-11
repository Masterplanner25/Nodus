# Working under tools/

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## nodus_gate phases

- `--static`: verifies documented symbols exist in the codebase. It prints the
  symbol and document counts every run — read them there rather than from here,
  which is the same rule `--shapes` below already states and which this line
  needed twice
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs; expects 0 failures with the `.nodusgate-allow` allowlist in place
- `--closed-issues`: runs closed-issue tests for CHANGELOG-referenced issues
- `--contracts`: verifies `HandlerContract` infrastructure is wired correctly (6 checks)
- `--consumers`: reports **non-PyPI consumers a release has left behind** —
  `nodus-vscode` (VSIX), `nodus-run-action`, and **the GitHub wiki**. Stage 6's
  sweep hashes published sdists/wheels, so it structurally cannot see any of
  them, and all three have shipped stale. Each records in `tools/consumers.json`
  the fingerprint of what it must
  stay in step with, measured **here**; when the live value moves, the consumer
  needs republishing. Reads no sibling checkout on purpose — a gate that needs
  one skips on CI, which is how `when` shipped unhighlighted. **Advisory**: it
  prints and exits 0; `--strict` makes a stale consumer fail. A manifest that
  cannot be read is always a failure. Clear a flag by republishing, then updating
  `fingerprint` and `published` in the same commit.

  **The wiki was registered on 2026-09-07, after it had documented v4.1.1 for
  twelve minors.** It is the one surface here with no PR and no CI — a push to
  `Masterplanner25/Nodus.wiki` goes straight live — so nothing could fail on it,
  and nothing did: 1 of its 26 pages mentioned 5.x, its Embedding-API page listed
  7 of the constructor's 27 parameters with all three capability flags missing,
  and its Security page named `v4.0.x` as the latest supported release. Tracking
  it here is the cheapest thing that turns silence into a line of output at every
  release. It tracks `nodus_version`, so it goes stale on **every** version bump
  by construction — that is the point, not a nuisance; a wiki that has not been
  looked at since the last release is exactly the thing to be told about.

  **It can only see what `lexer.ALL_KEYWORDS` names, so a keyword the parser
  matches by bare string literal is invisible to it.** At the 5.6.0 cut it
  reported `2/2 in step` on a release that adds `each` -- the fingerprint it
  compares is a hash of that set, and `each` had never reached it. The finding
  came from the gate staying *quiet* when it should have moved, which is a much
  worse signal to read than a failure. `tests/test_keyword_coverage.py` now
  checks **both** directions -- it used to verify only that every named word
  parses, never that every word the parser recognises is named -- and reads
  `parser.py`'s source, because a behavioural test cannot tell a word matched
  from a named set from one matched from a literal. Add a contextual keyword to
  a set in `lexer.py` and read it from there; never a literal in `parser.py`.
- `--opcodes`: verifies the frozen instruction set — reads the dispatch table
  out of a constructed `VM` and requires `BYTECODE_REFERENCE.md` §3, its
  appendix table, and the `FREEZE_PROPOSAL.md` stability tables to name the same
  49 opcodes, with matching counts and `BYTECODE_VERSION`. **If you add an
  opcode, this fails until you document it** — that is the point (#366).

  It also requires every dispatched opcode to carry a **semantic spec** and a
  `- Category:` line (#412 phase 4). The specs live in
  `tests/test_opcode_semantics*.py`, discovered by glob, and the relation is an
  equality — an opcode with no spec and a spec naming nothing dispatched are both
  failures. The gate cannot check semantics, only that the thing which does is
  still aimed at the whole set.

  **Write the spec by executing one instruction against a hand-built VM state,
  and prove it can fail.** "Run a program and check the output" is what the
  golden tests already do, and it is why #370 survived — the opcode was wrong on
  a path the program never reached. Phase 2 verified 14 deliberate defects and
  phase 4 another 52, all killed; two of phase 4's survived the first pass, and
  both were gaps in the spec rather than in the VM. A green spec run is not
  evidence that a spec constrains anything
- `--shapes`: reports **new instances of the recurring bug shape** — the section
  below is the reason this phase exists. It scans `src/` for the four species
  that leave a syntactic trace: one question implemented under the same name and
  signature in two modules (**A**), one vocabulary enumerated twice with a member
  missing (**B**), the same **still in agreement** (**B=**), and module-scope
  state every participant in a process shares (**D**). Species C (the cache as a
  sibling path) and E (the bound on the wrong substrate) are not detectable and
  are not attempted.

  **B= is the one to understand, because it inverts when the phase speaks
  (#685).** B requires a strict subset, so it fires only once a vocabulary has
  *already* drifted — the expensive half, and the half a human has always found
  first anyway (#518, #487 were both diagnosed after the divergence shipped). Two
  *equal* enumerations are still two voices; they simply agree today, and nothing
  makes them. Adding a member is then N edits where the one you miss is silent.
  Detected as two **module-level named constants** with equal string members and
  related names — a name bound at module scope declares that something *is* the
  set, where an inline literal is usually an argument, and the name-stem test is
  what keeps `{"true","false"}` from matching itself all day. **An alias
  (`_B = A`) is never collected**: an alias is the *fix*, and a detector that
  still fired afterwards would teach people to silence it in the manifest instead.

  Its first run found one instance in 135 modules — `_VALID_EFFECTS` in
  `builtins/tool_module.py` against `VALID_EFFECTS` in
  `nodus_lang_schema/contracts.py`, the "unified" handler contract. The two
  agreed. The detail worth keeping: the comment *directly above* that constant
  records #479 making exactly this fix to the **type** vocabulary in the same
  file, and leaving its neighbour alone.

  `tools/shape_manifest.json` records **every shape currently in the tree**, each
  with `intentional` (these are not one question) or `tracked` (a real debt, with
  its issue). The gate prints the count every run — do not transcribe it here; the
  number that used to sit in this sentence was stale by four. That baseline is the
  design: the value is not the list, it is that the *next* duplicated question
  shows up as **NEW** the day it lands. It also records `sites` per species-A entry, because the key is
  name+signature and a *third* copy of an already-listed function would otherwise
  be silent — a hole found by probing the detector, not by reading it.

  **Advisory**: it prints and exits 0; `--strict` fails on a new shape, a grown
  one, or a manifest entry matching nothing. A manifest that cannot be read is
  always a failure — the check may not pass by being unable to run.

  Two of its findings became #597 and #598 within an hour of the first run, and
  it independently re-found the `GATED_BUILTINS`/`BUILTIN_CAPABILITIES` pair that
  is already known-intentional and pinned by test — which is how the detector
  earned trust.

- `--versions`: verifies that prose still agrees with the version files. Three
  checks: `version.py` vs `pyproject.toml`; every claim declared in
  `tools/version_claims.json` against what it must equal; and a **discovery
  sweep** for claim-shaped lines nobody registered, so a new one cannot hide.
  The first two fail the gate — a stale version string is wrong *now* and the fix
  is one line, unlike a stale consumer that needs an external republish. The
  sweep is advisory. It reads `version.py` as **text**, never importing `nodus`,
  because an installed package shadowing the checkout would otherwise have the
  gate compare docs against the wrong version, silently and in the direction
  that hides a real mismatch
- `--invariants`: verifies the **invariant-to-test ledger** is honest (#179).
  `EXECUTION_INVARIANTS.md` documents 29 runtime invariants; which test checks
  which was recorded in prose, in two different places, by hand, so a renamed
  test left the document pointing at nothing and a new invariant arrived
  uncovered — with no CI signal for either. `tools/invariant_coverage.json` is
  the ledger; four checks fail the gate: an invariant with no entry, an entry
  naming an invariant the document no longer has, a named test file that does
  not exist, and an entry with no tests and no stated reason. Citation drift
  (the document names a test the ledger has not learned) is advisory.

  **It cannot verify an invariant holds** — the tests do that. It verifies the
  mapping, which is the only part a gate can own. **6 of 29 name a covering
  test**; the other 23 are `unrecorded`, which is deliberately not `uncovered`:
  the behaviour may be tested, but nothing ties a test to the invariant. Do not
  "fix" the count by guessing which test covers what — an invented mapping is
  worse than a recorded gap. An unreadable manifest is always a failure
- `--flips`: verifies that **every promise this tree makes about the next major
  is registered**. A staged flip is a promise made to a user *now* about a
  release that has not happened — `"This becomes an error in 6.0.0."` is printed
  on stderr today by code that still allows the thing. `nodus/support/staged_flips.json` is
  the register; `docs/governance/V6_0_PLAN.md` holds the reasoning and the open
  decisions.

  **It exists because the register was found two short.** Five promises live in
  `src/`; `COMPATIBILITY_MODEL.md` §5.3 said *"Three changes are staged"*,
  `COMPATIBILITY.md` listed one, and a design doc said a fourth had been
  dropped. The two that went missing were the two whose issues had been
  **closed** — the staging shipped, the issue closed, and the flip fell out of
  every register while the code kept promising it. Closing an issue does not
  retract a promise.

  Each site carries a `# v6-flip: <name>` marker, like a regression test's
  `# closes: #N`, because attribution is the whole problem: two of these flips
  live in `task_graph.py` and their text is nearly identical. A marker covers 30
  lines below it.

  Four checks, all failing — an unregistered promise is wrong *now* and the fix
  is one manifest entry. **The fourth is the one to understand**: each entry
  declares `sites`, the number of promise lines it owns, because a new promise
  landing inside an existing marker's window is silently absorbed. That hole was
  found by *probing* the detector, not reading it — the same hole, closed the
  same way, that `shape_manifest.json` records for a third copy of an
  already-listed function.

  It also reports how many flips have no full CLI signal, because a flip whose
  warning nobody sees is not a deprecation under `COMPATIBILITY_MODEL.md` §5.1.
  **Two of the five are in that state today** — #797's notice is a
  `DeprecationWarning` raised outside `__main__`, which Python's default filter
  discards, so no CLI user has ever seen it

## Tool notes

| What | Where |
|------|-------|
| Version-claim manifest | `tools/version_claims.json` — every sentence asserting a current version; checked by `nodus_gate --versions`. Add a claim here, never to a list in prose |
| Dependent-suite gate | `tools/check_dependent_suites.py` — **Gate 10 step 0**, run before any PyPI upload. Names failing tests, classifies recorded flakes, logs full output to `.dependent-suites/`. Also sweeps beside the registered checkouts and exits **2** on a dependent nobody registered (#810) |
| nodus-lang dependent registry | `tools/nodus_lang_dependents.json` — the **one** list of companions that *declare* a nodus-lang dependency, read by Gate 10a and by Stage 6's range check. They kept separate lists until #810 and drifted; `nodus-a2a-wire` was missing from **both**. The criterion is `declares`, not `imports` — a package that emits Nodus source or shells out to the CLI breaks without importing anything. Non-first-party checkouts go under `ignored` with a stated reason |
| Invariant coverage ledger | `tools/invariant_coverage.json` — one entry per invariant in `EXECUTION_INVARIANTS.md`, naming the tests that cover it or stating why none is recorded. Checked by `nodus_gate --invariants`. `unrecorded` is not `uncovered`; never guess a mapping |
| Shape manifest | `tools/shape_manifest.json` — every instance of the recurring bug shape currently in the tree, each `intentional` or `tracked`. The baseline `nodus_gate --shapes` measures new ones against. Adding an entry needs a stated reason |
| Downstream range check | `tools/check_downstream_constraints.py` — Stage 6; resolves *published* metadata. `UNPUBLISHED_COMPANIONS` registers a companion's `nodus-lang` floor **before** it is published, each with a stated reason, and reports a floor naming a version that does not exist yet — a package nobody can install. Register on the day the package is written, not the day it ships; move it into `COMPANIONS` in the publishing commit |
| Publish-drift check | `tools/check_publish_drift.py` — Stage 6; downloads each published sdist and compares file contents. Also prints each companion's published version, which is why this file no longer lists them. Exits **2** on a skip |
| Throughput + startup benchmark | `tools/benchmark_runtime.py` — reports VM instructions/sec on a hot loop **and** on `examples/expr_compiler.nd` (from the VM's own counter, not an estimate per loop iteration), and CLI startup. No figure is asserted anywhere; it exists so #173's numbers can be re-derived instead of transcribed, which is how they went stale by 2-4x. Run it under `.venv-pypy` too: the PyPy ratio is the figure that moved most, both ways (#702) |
