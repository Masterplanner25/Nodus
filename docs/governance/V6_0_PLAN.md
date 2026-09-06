# Nodus v6.0.0 — Scope

**Status:** scoping. Nothing here is scheduled and no date is set.
**Last reviewed:** 2026-09-06, against 5.11.0.
**The register is `tools/v6_flips.json`**, checked by `nodus_gate --flips`.
§1 below is a reader's copy; the gate is the authority.

## What this document is

The register of what changes at the next major, what each change costs, and
what must be true before the major can be cut. It is not a schedule and it does
not commit to a date.

**Every claim below was checked by running it against `src/` at 5.11.0.** That
matters more than usual here: this cohort is described in four places and no two
of them agreed, so reading any one of them would have produced a wrong plan
(§3.1). Where a claim is recorded rather than measured, it says so.

---

## 0. The shape of the release

**6.0.0 is flip-only. Decided 2026-09-06 (D5).**

It carries the five staged flips in §1 and nothing else. Everything that already
warns starts failing; no feature lands alongside. Features resume at 6.1.0.

Three things follow from that, and they are the reason it is worth stating
before the list rather than after it:

- **The major's content is already fixed.** Scope creep has nowhere to enter:
  anything that is not one of the five is, by definition, 6.1.0. `tools/v6_flips.json`
  is the whole scope, and `nodus_gate --flips` fails if that stops being true.
- **Everything blocking it is 5.x work.** G2 (make the signals visible) and G3
  (let a project enumerate its exposure) both have to ship *before* the major,
  in ordinary minors — they are not part of it. So the question "when is 6.0.0?"
  is really "when are G2 and G3 done?", which is a much more tractable one.
  **G2 shipped on 2026-09-06**, so it is now just G3.
- **The upgrade is small enough to describe on one page.** A user's migration is
  "fix what the warnings already told you about", with no new surface to learn
  at the same time. That is the argument for the shape: a major that both
  breaks things *and* introduces features makes it impossible to tell which
  half caused a problem.

The cost is that 6.0.0 is unglamorous, and that is fine. It is the release that
makes eight minors' worth of warnings mean something.

---

## 1. The committed flips

Five places in `src/` promise a 6.0.0 behaviour change to a user today. All five
were reproduced.

| # | What changes | Where | Warns since | Warning visible on the path users run? | Open issue |
|---|---|---|---|---|---|
| 1 | An unrecognised type name becomes an error | `frontend/parser.py`, `frontend/type_system.py` | 5.6.0 | **`nodus check` only** — `nodus run` is silent | #609 |
| 2 | Record `==` becomes structural | `vm/types.py` | 5.4.0 | yes, once per process | #545 |
| 3 | A concurrent write that loses an update becomes an error | `orchestration/task_graph.py` | 5.2.0 | yes | #547 |
| 4 | A `worker:` declaration with no dispatcher becomes an error | `orchestration/task_graph.py` | 5.3.0 | yes | #798 |
| 5 | The default workflow store becomes SQLite | `nodus_lang_workflow/runner.py` | 5.10.0 | **no — nobody has seen it** (§3.2) | #797 |

Reproductions, all at 5.11.0 from a throwaway project:

- **#609** — `fn f(a: itn)` under `nodus check` warns twice and exits 0
  (`OK (2 warning(s))`); the same file under `nodus run` prints nothing and runs.
- **#545** — `record {x: 1i} == record {x: 1i}` is `false` while the equivalent
  map is `true`, with the one-time warning on stderr.
- **#547** — two unordered steps writing `total` with different values warns,
  names both remedies, and runs.
- **#4** — `step a with { worker: "remote" }` with no dispatcher warns
  *"This becomes an error in 6.0.0"* and runs in-process.
- **#174** — see §3.2. It does not print.

## 2. What each flip costs to do

Four of the five are small; the fifth is not.

- **#545** is the most nearly done. The 6.0.0 semantics already exist as
  `structural_eq` in `vm/types.py`, consulted today only to detect divergence.
  The flip is: delegate `Record.__eq__` to it and delete the warning. It also
  unblocks `merge: "union"` for records, which #485 shipped refusing outright
  because dedup by identity removes nothing. Design: `docs/design/v6/00-record-equality.md`.
- **#547** carries its own checklist in the issue — change the undeclared-cell
  path in `report_write_conflicts` from a stderr warning to
  `vm.runtime_error("workflow_error", …)`, matching how `merge: "once"` already
  reports, and keep both remedies in the message.
- **#609** — the parser records `UnknownTypeName` and lets whoever asks report
  it; the flip is to raise instead. The static machinery is already there.
- **#4 (worker)** — same shape: warn becomes raise, one site.
- **#174 is the outlier.** It changes a *default that owns state*, not a
  behaviour. Runs recorded in the JSON store are invisible to a SQLite one, so
  an in-flight `waiting` run becomes unresumable rather than moving.
  `nodus workflow migrate-store --to sqlite` exists, is non-destructive, has a
  real `--dry-run`, and preserves a parked run's wait — but it has to actually
  be run, by every operator with state, before they upgrade. That is a
  migration campaign, not a code change.

## 3. Findings from building this register

### 3.1 The register was incomplete, and the documents contradicted each other

Four places describe this cohort and no two agree:

| Source | Says |
|---|---|
| `src/` | **five** live 6.0.0 promises |
| `COMPATIBILITY_MODEL.md` §5.3 | *"Three changes are staged"* — #609, #547, #545 |
| `COMPATIBILITY.md` *Deprecated (Still Supported)* | **one** — the concurrent write |
| `docs/design/v6/00-record-equality.md` | #492 (`worker:`) *"is not part of the cohort"* |

The last one is the sharpest. The design doc's correction says the `worker:`
staging was dropped when #492 closed during the 5.4.0 cycle — and
`task_graph.py` still prints *"This becomes an error in 6.0.0."* to users on
every unhonoured `worker:` declaration. **One of the two is wrong, and the one
users act on is the code.**

That was decision D1, and it was **decided on 2026-09-06 in favour of the code**:
the flip is in the cohort. What makes it worth keeping this paragraph after the
answer is the mechanism — the design doc read a *closed issue* as a dropped
flip, so **closing an issue silently retracted a promise nobody had retracted.**
That is what `nodus_gate --flips` now makes impossible, and it is the reason the
register moved out of prose.

This is the failure the governance sweeps already named: a governing document
holding an enumeration that something else also holds. `COMPATIBILITY_MODEL.md`
§5.3 is dated *"Checked 2026-09-01 against 5.9.0"* and was already two short on
the day it was checked.

### 3.2 Two of five fail the project's own deprecation test

`COMPATIBILITY_MODEL.md` §5.1 requires three signals: a CHANGELOG entry, a CLI
warning, and an entry in `COMPATIBILITY.md` with a timeline.

- **#174 has no CLI warning at all.** The notice is a Python
  `DeprecationWarning` raised from `nodus/vm/vm.py`, and Python's default filter
  ignores `DeprecationWarning` outside `__main__`. Measured: with three runs in
  the store, `nodus run` prints nothing about the store; the identical command
  under `python -W always -m nodus run` prints the full notice. **No CLI user
  has ever seen it** — only embedders who enable warnings, and the test suite.
  The narrowing in `_warn_default_store_is_transitional` is careful and correct
  and it is downstream of a filter that discards the result.
- **#609's warning reaches `nodus check` only.** A project that never runs
  `check` gets no notice before the major.
- Only **#547** has all three signals. *(Fixed 2026-09-06: all five do now — see G2 below. The finding is kept because the failure mode is the point: a notice can be correct, careful and discarded.)*

The ranking that matters: **the flip with the weakest signal is the one that
costs state.** #545, #547 and #4 break a *build* — loud, immediate, fixable in
place. #174 loses a parked run.

### 3.3 Four of five cannot be audited before the fact

Only #609 is detectable statically. #545, #547 and #4 warn only when the
situation actually arises at runtime, on the code path a given run happens to
take — a codebase can hold every one of these defects and warn on none of them.
#174 warns only when the store already holds runs.

So today **a project cannot answer "am I ready for 6.0.0?"** That is the
question a major has to let people answer, and no combination of existing
commands answers it.

### 3.4 The signals are very unevenly aged

5.2.0 (#547) through 5.10.0 (#174) — nine minors apart. §5.2 requires a
deprecation to be supported for at least one major cycle after announcement.
#547, #545, #609 and #4 clear that comfortably. #174's announcement landed one
minor ago and has been invisible since, so on the project's own rule its clock
has arguably not started.

---

## 4. Gate conditions

Proposed; these are what §3 says must be true before a 6.0.0 is defensible.

| | Gate |
|---|---|
| **G1** | Every live 6.0.0 promise in `src/` has an open issue. **Closed** — #797 (default store) and #798 (`worker:`) were filed 2026-09-06; `tools/v6_flips.json` names an issue per flip and `--flips` requires the field. |
| **G2** | Every flip's warning is visible on the path a user actually runs. **Closed** — see below. |
| **G3** | A project can enumerate its own exposure without waiting to hit each path at runtime (§3.3). |
| **G4** | Each flip has a migration paragraph; #174 needs more than a paragraph. |
| **G5** | The four documents in §3.1 agree, and cannot silently drift apart again. **Closed** — see below. |
| **G6** | `check_downstream_constraints` re-run at the cut (see §5). |

**G2 is closed, and the two halves failed differently.**

**#797** — the notice existed, was carefully written, named the exact command to
type, and was discarded before reaching anyone. It was a plain
`DeprecationWarning` raised outside `__main__`. `StagedFlipWarning`
(`nodus/support/staging.py`) is a `DeprecationWarning` subclass the CLI
unsuppresses by name and renders as `warning: …`; an embedder's existing
filters still catch it, and an embedder can still turn it into an error. Scoped
to that category on purpose — unsuppressing every deprecation the CLI's
dependencies raise would bury our notice in theirs, which is how a warning
becomes noise and then becomes ignored.

**#609** — the signal was on the wrong command. `nodus check` and the LSP both
read the parser's `unknown_type_names`; the *run* path threw the parser away.
That is the wrong shape for a staged flip, because **`nodus run` is what starts
failing at 6.0.0** — so the command whose behaviour changes was the one saying
nothing. The loader accumulates them now, entry file and imports alike, and
`run_source` attaches them to stderr the way #675 attaches the unrun-task
warning.

**The bytecode cache was a third path, for the fourth time.** The first version
of #609's fix warned on a cold compile and went silent on every run after, which
is worse than never warning — it looks like something someone fixed. The
diagnostics are carried in the cache entry and replayed on a hit, the way #394's
step mark is and for the same reason. #521, #400, #394 and #348 are the earlier
instances; #348 is the closest, since `--trace-imports` also printed nothing once
the cache was warm. **Run the repro a second time, always.**

**G5 was solved structurally rather than by editing prose, because this document
is itself a prose enumeration and would have drifted the same way.** Every
enumeration in §3.1 was hand-maintained and all four drifted.

`tools/v6_flips.json` is the register now and `nodus_gate --flips` checks it
against `src/` in both directions — the same shape as `version_claims.json`,
`shape_manifest.json` and `invariant_coverage.json`. **This document holds the
reasoning, the gate conditions and the open decisions; it does not hold the
list.** §1's table is a reader's copy, and the gate is the authority.

Each promise site carries a `# v6-flip: <name>` marker, like a regression test's
`# closes: #N`. Attribution needs one: two of these flips live in
`orchestration/task_graph.py` and their promise text is nearly identical.

Four checks, all failing rather than advisory, because an unregistered promise
means the register is incomplete the moment it lands. The fourth is worth
knowing about: each entry declares how many sites it owns, because **a new
promise landing inside an existing marker's window was silently absorbed** —
found by probing the detector rather than reading it, and closed the same way
`shape_manifest.json` closes it for a third copy of an already-listed function.

The phase also reports how many flips have no full CLI signal, so §3.2 is a
number the gate prints rather than a paragraph someone has to remember.

---

## 5. Checked and clear — do not re-litigate

- **Bytecode stays at 4.** None of the five touches the instruction set; #609
  changes what the parser *accepts*, which is a source break, not a format
  break. And the bytecode cache validates `compiler_version == __version__`
  (`runtime/bytecode_cache.py`), so no 5.x cache entry survives the upgrade —
  a warm cache cannot carry 5.x acceptance into 6.0.0. Verified by reading the
  key; worth re-checking at the cut, because the cache has been a sibling path
  three times (#521, #400, #394).
- **The ecosystem admits a major by construction.** All seven published
  companions carry `>=` floors with no upper cap, verified by
  `tools/check_downstream_constraints.py` on 2026-09-06. This is the #445
  failure — five of six companions capping `<5.0.0` made 5.0.0 unadoptable —
  and the no-cap policy of 2026-08-17 closes it. Re-run at the cut anyway; the
  tool resolves *published* metadata, and a companion could add a cap.

---

## 6. Decisions

**D1 and D5 are settled** (2026-09-06); the rest are open. Each of the open
ones changes what 6.0.0 contains or when it can be cut.

- ~~**D1 — Is the `worker:` flip in the cohort?**~~ **Decided 2026-09-06:
  honour it.** It flips with the rest; #798 tracks the work. The design doc's
  2026-08-26 correction had read a *closed issue* as a dropped flip, and the
  lesson it leaves is the one the gate now enforces: **closing an issue does not
  retract a promise.** A `worker:` declaration is an isolation intent, so running
  in-process while reporting success is the worst available answer — the same
  reasoning that made it a warning rather than a silent no-op in the first
  place. Second-oldest signal in the cohort (5.3.0), so notice is not a blocker.
- **D2 — Do the v1.0-era deprecations go?** `.tl` (still accepted, still warns),
  `language.py` / `language.bat`, and `tiny_vm_lang_functions.py` have been
  *"deprecated, no removal date"* since v1.0 — five majors' worth of notice. A
  major is the only place they can be removed. `COMPATIBILITY.md` still lists
  all three under *Deprecated (Still Supported)*, which is accurate.
- **D3 — Does `_last_vm` go?** Deprecated on the embedding surface with a
  `DeprecationWarning` pointing at `get_execution_stats()`. Note that downstream
  pins private names here before (`_get_active_vm` is retained deliberately), so
  this needs a dependent-suite answer, not a judgement.
- **D4 — `run_loop()` inside a library.**
  `docs/design/v5/05-async-library-boundary.md` §10.2 defers this to *"6.0.0,
  alongside the staging cohort"*. Nothing warns today, so it is a deferred
  decision, not a staged flip — it cannot flip at 6.0.0 without a warning
  shipping first.
- ~~**D5 — Does 6.0.0 carry a feature, or is it flip-only?**~~ **Decided
  2026-09-06: flip-only, feature after.** See §0. The consequence worth
  repeating here: G2 and G3 are 5.x work that gates the major rather than
  content within it.

---

## 7. Not in scope

- **#173 (throughput)** — a JIT-scale question, unrelated to any flip.
- **#180 (durable coroutines)** — *downstream* of 6.0.0, not part of it.
  `docs/design/v5/08-durable-coroutines.md` §6: a durable coroutine must refuse
  a non-crash-safe store or land after #174's step 2. Stage 4 becomes possible
  once the default is SQLite; it does not ship in the major that makes it so.

---

## 8. Sequencing

The order §3 implies, not a schedule:

1. ~~**Close G1 and D1**~~ — **done.** #797 (default store) and #798 (`worker:`)
   were filed 2026-09-06, so every live promise has a tracker; D1 was decided
   the same day in favour of honouring the `worker:` promise, so #798 now
   tracks the flip rather than the question.
2. ~~**Close G5 structurally**~~ — **done.** `tools/v6_flips.json` plus
   `nodus_gate --flips`.
3. ~~**Fix the signals (G2)**~~ — **done.** Both halves ship in 5.x, so the
   deprecation clock is now running on something people can actually see. #797
   stays open for the flip itself. — #174's notice must reach a CLI user, and #609's
   should reach `nodus run`. Both are 5.x work and both are prerequisites for
   the deprecation clock being honest.
4. **Build the readiness answer (G3)** — whatever lets a project enumerate its
   exposure. **Now the only thing between here and a datable 6.0.0**, since D5
   fixed the scope and G1/G2/G5 are closed. It is also the largest undecided
   piece and the one most worth designing rather than improvising.

   G2 narrowed it usefully, though: #609 is now enumerable by running the
   program *or* `nodus check`, and #174 announces itself on any run with state.
   What is left is #545, #547 and the `worker:` flip, all three of which only
   speak when the situation arises on the path a run happens to take.
5. **Then decide D5**, with the cost of 1–4 known.
