---
description: The authoritative Nodus release sequence, version-claim rules, what each release broke, and how to check published companions. Read before any release step.
---

# Release sequence

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

**Authority:** this file wins over `/release-prep`, which is older.

## Version sync — must keep in step

Release order — the whole sequence, not just the publish half:

1. Run the gates (`RELEASE_GATES.md`): suite, ruff, `nodus_gate --all`, keyword coverage,
   and Gate 3e: `python -m tools.refresh_issue_states`, then
   `nodus_gate --open-claims --strict`. In CI that phase is advisory and reads the
   committed cache, so only a refresh tells you what closed since. Commit the
   refreshed `tools/issue_states.json` in the release PR. At 5.16.0, before the
   phase existed, four `[Unreleased]` entries still called #180 open
2. Bump both version files — **and finish every `README.md` edit now, before step 6.**
   `pyproject.toml` sets `readme = "README.md"`, so the README *is* the PyPI long
   description: whatever it says at tag time is what the project page shows forever, and
   release immutability means no re-upload. This was missed at 5.0.1 — the banner fix
   landed after the tag, so <https://pypi.org/project/nodus-lang/5.0.1/> still displays
   "v5.0.0 stable on PyPI" while `main` is correct. Cosmetic, but permanent.
3. Move `[Unreleased]` in `CHANGELOG.md` to the new version section
4. **Re-run the closed-issues gate as `--closed-issues --section X.Y.Z`.** After the
   cut it scans an empty `[Unreleased]` and reports a pass that checked nothing
4b. **Re-run `nodus_gate --versions` after the bump.** Step 1 ran it against the *old*
   version, when it passed by definition. It is only after step 2 that it can tell you
   which sentences still quote the version you just left — which is the failure that hit
   three releases running. It names each file, line, and the fix
4c. **Re-run the suite too, after steps 2-4.** Step 1's run predates every edit
   those steps make, and some of those edits are things tests assert on: `llms.txt`
   ships **inside the wheel**, and `tests/test_llms_txt_shipped.py` byte-compares
   the packaged copy at `src/nodus/llms.txt` against the root. Editing the root
   version claim without running `python -m tools.sync_llms_txt` turns a green
   Gate 1 into a red CI, which is how 5.7.0's release PR failed. Do not hand-edit
   the packaged copy; the sync tool is idempotent and says `already in step`
5. Commit, PR, CI, merge
6. `git tag vX.Y.Z` → `git push origin vX.Y.Z`
7. Build the wheel **from the tagged tree**
8. **Gate 10.** Two parts, and the first one is not optional:

   a. **Run every dependent suite — before the upload.**
      ```powershell
      PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
        "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_dependent_suites
      ```
      Exit codes: **0** all green · **1** a *new* failure, do not publish · **2** a
      checkout was missing or a suite timed out — not a pass, an unrun suite covers
      nothing · **3** every failure matched a recorded flake in
      `tools/dependent_flakes.json`. **3 is not a pass either** — re-run those suites
      serially before deciding. A recorded flake changes the advice, never the verdict;
      letting one through would rebuild "re-run until green" one level up.

      **5.0.3 shipped without this and broke `nodus-sdk` at construction.** #185 assigned
      `self.memory_store` on `NodusRuntime`, and `NodusSDKRuntime` subclasses it with
      `memory_store` as a read-only property. Gate 10 passed with **32 green adversarial
      probes**, because it validates nodus-lang *against itself* and nothing in it
      constructs a dependent. Stage 6 caught it — post-publish, against an immutable
      PyPI — and it cost a 5.0.4.

      **Run it with nothing else going.** At 5.1.0 it reported `nodus-mcp FAIL — 1
      failed` while a clean-venv install and probe suite ran alongside it; three serial
      re-runs were green. It used to stop there, so a red result could not be triaged
      without re-running by hand — the manual step the gate replaced. As of #528 it
      names each failing node id, marks the ones matching a recorded flake, and writes
      full output with tracebacks to `.dependent-suites/<companion>.log`, so triage
      needs no re-run. `--retry-failed` re-runs only the failed tests and reports both
      results; it is opt-in, and cannot change the verdict.

   b. Adversarial validation against the wheel in a clean venv →
      write `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md`

      **Write the probes before step 6, not here.** They are the only check that reads
      the release's *claims* rather than its code, and at 5.1.0 writing them early caught
      four artifacts describing a task-status vocabulary the release did not have — one
      of them `README.md`, which `readme = "README.md"` makes the permanent PyPI page.
      Run after the tag, that correction would have been impossible. Nothing else caught
      it: three features touched one vocabulary, landed in sequence, and the last
      silently falsified prose written for the first two.

      **Run it from a directory outside the repo, and pass `--require-installed`.**
      The repo-root `nodus.py` shim inserts `src/` on `sys.path` and re-execs the package
      from there, so *any* process whose CWD is the checkout resolves `nodus` to the
      **source tree** no matter what is installed -- no `PYTHONPATH`, nothing in
      `pip list`. That is how 5.0.3 shipped past **32 green probes** run against the wrong
      tree, and it recurred at 5.5.0 and again at 5.6.0. The probes print the resolved
      package path first for this reason, and `--require-installed` now exits **2** rather
      than relying on someone reading the header:

      ```powershell
      cd $env:TEMP   # anywhere outside the repo
      & "C:/dev/Coding Language/.venv-validation/Scripts/python.exe" `
        "C:/dev/Coding Language/tests/eval/release_claims_probe.py" `
        --repo "C:/dev/Coding Language" --require-installed
      ```
9. Upload to PyPI
10. **Stage 5** — install the *published* package in a fresh venv and check it works
    as a new user would expect → write `docs/evals/vX.Y.Z/POSTPUBLISH_EVAL.md`
11. `gh release create vX.Y.Z --verify-tag` — **only after PyPI succeeds**, since
    release immutability is permanent (see the gotcha above)
12. **Stage 6 — downstream republish sweep.** Four questions, three of them now tooled:

    - ranges still admit the new version → `tools/check_downstream_constraints.py`
    - has a companion drifted from what it published → `tools/check_publish_drift.py`
    - non-PyPI consumers left stale → `nodus_gate --consumers`
    - work left behind → `git status` each checkout by hand

    → write `docs/evals/vX.Y.Z/STAGE6_DOWNSTREAM_SWEEP.md`

    **Clear a consumer's flag only after republishing it**, then update `fingerprint`
    and `published` in the same commit. A flag cleared before the work is done is worse
    than no flag.

**All three eval documents are part of the release, not optional write-ups.** A clean run
is evidence; silence is not. Steps 8, 10 and 12 answer different questions — "what can I
make fail?" against a local wheel, "does this work as a new user would expect?" against the
published one, and "what downstream did this break or leave behind?"

**`nodus_gate --versions` enforces the first of the three now.** A claim in
`tools/version_claims.json` may declare `points_at`, and the eval-record claim in
`ECOSYSTEM_READINESS_ASSESSMENT.md` uses it — so the gate fails unless the newest
`docs/evals/vX.Y.Z/` holds a `CREATOR_VALIDATION.md`. Added at 5.7.1, where 5.7.1's
directory held two of its three documents and the claim's *version* was the only thing
being compared: editing the string would have passed the gate while naming a file that
did not exist. Stage 5 and Stage 6 are still on you.

**That claim cannot be satisfied during the release, and step 4b is right to
pass without it.** `points_at` requires the directory to *hold* the document, so
the claim can only move once the eval record is written — which is step 12's
commit, after the publish. At the 5.12.0 cut, step 4b reported 13/13 with the
claim still naming 5.11.0 (correct: 5.12.0's directory did not exist yet), and
CI then failed the **post-release** PR that created it. That is the mechanism
working, not a miss: bumping it earlier would have named a file nobody had
written, which is the exact failure `points_at` was added to refuse.

So expect one `--versions` failure on the eval-record PR, and fix it there. It
is the only claim in the manifest whose correct value changes *because of* the
commit that carries it.

**`/release-prep` is a skill** (`.claude/commands/release-prep.md`) and walks this sequence.
It is **older than the sequence above** — it predates Stage 5, Stage 6, and the
`--closed-issues --section X.Y.Z` re-run, and its Step 5 pushes to `main` directly, which
`enforce_admins` rejects. **This file is the authority; use the skill as a prompt, not a
script.**

**There is no CI publish workflow in this repo.** `.github/workflows/` holds `ci.yml`
and nothing else, no environments are configured, and pushing a tag runs CI only. The
upload below is manual and is the only thing that publishes. (A tag-triggered,
approval-gated publish exists in the *runtime* repo, not here -- do not assume this one
behaves the same.)

PyPI upload — use explicit flags; `~/.pypirc` may have an empty password field
which causes a 403:

```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload --username __token__ --password <token> dist/*
```

Token: **`~/.pypirc` was populated with a working nodus-lang token as of 2026-08-17** and the
5.0.0 upload used it. Prefer it over asking. If it 403s, the password field has gone empty
again — ask the user rather than guessing. Never write a token into a repo file.

Full release checklist: `docs/release.md`.

## SemVer policy

**What each release added is in `CHANGELOG.md`, not here.** A narrative per release
lived in this section and duplicated the changelog it was copied from. What follows
is only what the changelog cannot tell you at a glance.

### What is *not* additive, 5.3.0 onward

Everything else in those releases adds a way to *say* something. These are the
changes that can break a reader's working setup, so the table answers one question
fast: **is this symptom a release, or is it my change?**

| Release | What stopped working | Restore / fix |
|---|---|---|
| 5.16.0 | `nodus workflow resume` / `replay`, `goal-resume` and the legacy `workflow-resume` **exit 1** when the run is not found, cannot be rebuilt or is not a workflow (#920) | intended: they printed `{"ok": false, ...}` and exited 0, so a script testing the exit code read every failure as success. The answer is still printed. A script that relied on 0 was reading a failure as a pass |
| 5.16.0 | resuming a stored run prints a `StagedFlipWarning` for each top-level call with an effect (#917) | a warning, not a refusal, until 6.0.0. The call really did run again on every resume; it was silent. Move it into `main()`, register a host function with `rebuild_safe=True`, or pass `rebuild_effects="allow"` to the sweep for a run stored before the fix |
| 5.16.0 | `let checkpoint = 1; checkpoint "x"` **on one line** is a syntax error | the only program refused: it evaluated a variable and discarded a string. `checkpoint` is otherwise not reserved, so a variable, function, parameter or field of that name still works |
| 5.15.0 | a program doing **two or more** `resume_workflow` calls under the `nodus run` default now times out (#873) | intended, and the reason it is a row: a resume child inherited no bounds at all, so a guest escaped its instruction budget *and* its deadline by parking and resuming -- measured, 8 resumes and ~800 ms inside a 300 ms budget, and ~270,000 instructions inside 5,000. A resume costs ~99 ms against the 200 ms default, so one still fits and two do not. `--time-limit N` (seconds) is the fix, as it already is for anything else needing more than 200 ms |
| 5.15.0 | `max_terminal_runs` deletes **more** than it used to (#875) | it is the documented hard ceiling on a store's size and was not one: it chose what to delete from the age-bounded listing, and terminal is exactly what it deletes, so a cap of 2 left 6 files and the survivors were the oldest. Opt-in -- the default is `None` and an unset cap still deletes nothing -- so only a host that asked for a ceiling is affected. Live runs are untouched at any age. Unset the cap to keep the old retention |
| 5.15.0 | `resume_workflow(id, "checkpoint", {payload})` on a waiting run replays instead of being refused (#870) | a restoration, not a restriction: #482 refused it on the stated grounds that the payload was "silently discarded", and it was not -- it reached the replayed step. Nothing can have depended on an error. `resume_workflow(id, "checkpoint")` with no payload is still refused, which is the part #482 earned |
| 5.14.0 | `POST /workflow/run`, `POST /goal/run`, `nodus workflow run` and `nodus goal-run` no longer run a self-running program's flow a second time (#858) | intended -- the second run was the defect (two Slack posts per webhook). A program that *defines* a flow is run for it as before; one that calls `run_workflow(w)` itself now gets its own run reported. Nothing could have relied on the double except by accident |
| 5.14.0 | the hidden legacy `workflow-run --time-limit N` means N **seconds**, as every other `--time-limit` does (#857) | it passed the value through as milliseconds, so `--time-limit 30` was a 30 ms budget that timed out every real workflow. A script that passed a large number to get a real budget now gets a much larger one; nothing that *worked* breaks |
| 5.14.0 | a step past the budget under `nodus serve` returns `ok: false` instead of hanging the request (#862) | a repair, and the reason `--time-limit` could ship: raising the budget with the hang in place would have turned every timeout into a wedged request thread |
| 5.13.0 | code submitted to `nodus serve` can no longer read or write outside the server's working directory (#843) | `--allow-paths` widens it, as it always could -- except that it did not: the roots were compared unnormalised, so on Windows it refused every path including the ones it was given. That half is a repair, not a restriction |
| 5.13.0 | a workflow `state` cell **owns** its value (#822) | intended, and the reason the conflict machinery works at all: a step can no longer change a cell by mutating what it read or what it assigned from. `cell[i] = v` is recorded as a write now, so a program relying on the untracked mutation behaves differently |
| 5.13.0 | `fs.ensure_dir` returns `io_error` where it used to return the path (#845) | it reported success for every failure, so nothing that *worked* breaks -- but code that ignored the result now has a result worth checking. An existing directory still succeeds; a **file** at the target is the case that now refuses |
| 5.12.0 | an **undeclared CLI flag is refused** instead of silently dropped (#791) | remove it, or spell it correctly. `--help` lists what each command takes and the error suggests a near miss. This is the fix for `workflow cleanup --dry-run` **deleting** — but any script passing a flag that did nothing now exits 1, including `--flag=value`, which was taken as the *filename* |
| 5.12.0 | four `nodus test` flags are gone: `--watch`, `--parallel`, `--seed`, `--coverage-per-test` (#794) | nothing to restore — they were declared, printed by `--help`, and read by no code. `nodus test --watch` ran once and exited, which looks exactly like a watcher that saw no changes |
| 5.11.0 | `runtime.time_ms()` reads the **scheduler's** clock, not the host clock (#182) | only observable to a host that installs a non-default `TimeSource`; on `HostTimeSource` it *is* `runtime_time_ms()`. It was the incoherence, not the fix: under a virtual clock a program's own 800 ms sleep measured `0.0` |
| 5.10.0 | code submitted to `nodus serve` can no longer run subprocesses, open sockets or read the environment (#754) | `--allow-subprocess` / `--allow-network` / `--allow-env`, narrowed with `--allowed-commands` / `--allowed-hosts`. `nodus run` is unchanged |
| 5.10.0 | an unconfigured local workflow store holding runs warns once per process (#174) | migrate with `nodus workflow migrate-store --to sqlite`, or set `NODUS_WORKFLOW_STORE_BACKEND=local` to mean it |
| 5.8.0 | a function assigning to a module-top-level `let` now updates it, where the write used to vanish (#671) | intended; nothing can have depended on a write disappearing |
| 5.8.0 | a named import of a builtin name is refused at load instead of silently ignored (#680) | import the module and qualify — `import "std:async" as async` |
| 5.7.0 | `nodus check` rejects a dependency read in any file declaring an `extern` (#662) | upgrade to 5.7.1 |
| 5.6.0 | an unrecognised type name is reported, not silently `any` (#609) | it is a **warning** until 6.0.0 — fix the annotation |
| 5.5.0 | a step body can no longer be called directly — `build["steps"][1]["fn"](nil)` raises (#394) | never supported; call the workflow |
| 5.5.0 | `nodus.tooling.loader` dropped `resolve_with_extensions` / `try_resolve_with_extensions` (#598) | nothing outside the runtime consumed them |
| 5.4.0 | `nodus graph` no longer executes the file it inspects (#400) | `--execute` for a graph built at runtime |
| 5.4.0 | `nodus workflow cleanup` gained a **30-day default retention**; unset used to mean forever | `NODUS_WORKFLOW_RETENTION_SECONDS=0` |
| 5.3.0 | `nodus.toml` refuses a table or key Nodus does not read (#490) | the error names the word and suggests the match |
| 5.1.0 | `run_source(filename=)` is a label and no longer selects the program (#521) | `run_file` to run a file — see the embedding section |

Some of these ask something of you rather than just explaining a symptom.
(No count here on purpose — it went stale twice, and one of the entries below
is not even a row in the table.)

- **#616 is why 5.6.0 should not be skipped by an embedder** (`severity:high`): a
  capability policy could be bypassed by writing the **async form** of a call.
  Anything embedding a `NodusRuntime` with a policy should be on 5.6.0 or later.
- **#609 is staged, not done.** An unrecognised type name warns today and becomes
  an error at **6.0.0**, alongside #547 and #492. A project that is "clean" now can
  still be red at the major, so treat those warnings as a to-do list.
- **#174 joins that cohort, and it is the one that costs *state* rather than a
  build.** The default workflow store becomes `SQLiteWorkflowStore` at **6.0.0**.
  Runs recorded in the JSON store are invisible to a SQLite one, so an in-flight
  `waiting` run would become unresumable rather than move. Migrate before the
  major with `nodus workflow migrate-store --to sqlite` — non-destructive, has a
  `--dry-run`, and preserves a parked run's wait. An unconfigured local store
  holding runs warns once per process; `NODUS_WORKFLOW_STORE_BACKEND=local`
  silences it and is the supported way to keep the JSON store.

  Do not repeat the reason this sat blocked. Three places — the runner comment,
  the test docstring and the runbook — each said *"there is no backend
  migration"*, all written together and all still saying it after
  `migrate-store` shipped. One question, three answers, stale in unison.
- **#754 is the one to read before upgrading a server.** Code submitted to
  `nodus serve` is denied subprocess, network and environment access; grant with
  `--allow-subprocess` / `--allow-network` / `--allow-env`, narrowed by
  `--allowed-commands` / `--allowed-hosts`. `nodus run` is unchanged, and that
  asymmetry is a decision: what deny-by-default protects is work you did not
  fully author.
- **#521 changed `run_source` against every prior release**, not just 5.0.x. Full
  account in the embedding section below.

**`[Unreleased]` is empty — 5.16.0 took its thirteen entries** (six changes, five
fixes, one performance, one tooling). Its theme is durable coroutines (#180),
shipped Experimental, plus the follow-ups that writing their guide turned up.

**5.15.0 has three rows, and every one of them came from outside.** A project building on Nodus reported five defects against 5.14.0; all five were real, two of its stated *causes* were not, and fixing them turned up two more (#873, #875). They were invisible here for the same reason in every case: the suite, the gates and the release probes all exercise a program that runs start to finish, and every one of these lives on the far side of a park-and-resume boundary. The lesson is the one #691 already taught in a different place — **a construct documented for use across a resume has to be tested across a resume**, not merely called.

**5.12.0 has two rows, and both are the same shape**: something that used to be
accepted and ignored is now refused. That is the release's whole theme applied
to its own surface — *a declaration the runtime accepts must bind, or be refused
at the point of declaration* (#490), which is also why `nodus test` lost four
flags and why every staged-flip warning had to become visible.

Everything else it ships is additive or a repair. `nodus check --staged` and
`NODUS_STAGED_FLIP_REPORT` are new surfaces; the #174, #797, #609 and #807 fixes
each replace silence or a Python errno with a message, and nothing could depend
on those.

**5.11.0 has exactly one row, checked rather than assumed.** Everything else it
ships is additive or a repair: `sleep_until` / `spawn_after` / `std:loop` are new
and shadowable (verified by defining a user `fn` of each name), `barrier: true`
is a new state-cell option (#578), the CLI's lazy server imports (#173) change
only how long startup takes, and the closure fixes (#783, #785, #786) repair
cases that previously raised `Stack underflow` — nothing could depend on those.
An absence recorded as checked is worth more than an absence.

**5.10.0 has two rows, and 5.9.0 has none — both checked rather than assumed.**
5.10.0's are `nodus serve` confinement (#754) and the workflow-store warning
(#174); everything else it ships is additive. #754 is *behaviour-changing but not
breaking* by this project's own definition — `docs/release.md` lists "security
patches that restrict previously-permitted behavior" among the non-breaking
examples — which is why 5.10.0 is a minor. Keep the two ideas apart: the table
above answers "will this surprise me?", and semver answers "must the major move?".

**The check that keeps being worth running, for any release adding a builtin:**
guest code can still shadow a builtin name with its own `fn`, so a new global
cannot collide with an existing program. Verified by running it at 5.9.0 (#170)
and again at 5.11.0 (`sleep_until`, `spawn_after`).

### Two releases to treat as superseded

- **5.7.0** — `nodus check` rejects correct code (#662). Fixed in 5.7.1.
- **5.0.3** — assigns a `memory_store` attribute that `nodus_sdk.NodusSDKRuntime`
  defines as a read-only property, so every construction of that subclass raises.
  The one release in the 5.0.x line that breaks a first-party companion. Fixed in
  5.0.4.

**The rule 5.7.0 left, because the pattern recurs:** when a release is found
defective **between the PyPI upload (step 9) and the GitHub release (step 11)**,
stop at step 10 and do not create the release. Roll the fix forward and cut both
artifacts at the next version. PyPI is immutable, so the bad version cannot be
withdrawn — but a GitHub release would be a *second* published record asserting it,
and release immutability means it could never be corrected, only contradicted. One
superseded artifact is better than two.

**That rule is about a release that a fix will supersede.** It does not apply when
the defect found at Stage 5 is **pre-existing** — 5.8.0 shipped its GitHub release
with #691 open, because #691 is equally present in 5.7.1 and nothing about 5.8.0
needed superseding. Check which case you are in before applying it.

### Version claims in prose

**`tools/version_claims.json` is the list, and `nodus_gate --versions` checks it.**
Do not maintain one here; the list that used to live in this file was itself wrong,
and the gate's discovery sweep found a claim it had missed on its first run.

**Re-run `--versions` after the bump** — before it, it passes by definition. At the
5.6.0 cut it named 13 stale claims across 8 files; at 5.8.0, 13 again. Each comes
with file, line and fix.

The distinction is still yours to make when you *write* prose: **"X is current"
goes stale, "as of X" does not.** The gate cannot tell them apart, which is exactly
why claims are declared rather than grepped. Register a new one, or word it so it
never needs registering — the README *banner* names no version at all, which is why
it is the one line that has never gone stale.

**v5.0.0 is the first major.** It carries exactly one breaking change: embedded
runtimes deny subprocess/network/env by default. The bytecode format did not
change — `BYTECODE_VERSION` is still **4** and the 49-opcode set is untouched — so
a major bump does not imply recompilation.

## Published ecosystem — how to find out, not what it was

**Every number in this section used to be written down, and every one of them went
stale.** What is left is how to ask, and the lessons that cost a day each.

### Ask, do not transcribe

```powershell
# does each companion's published range still admit the current nodus-lang?
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_downstream_constraints

# published version of each companion, and whether its checkout has drifted from it
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_publish_drift
```

`check_downstream_constraints` resolves ranges with `packaging` against **published**
metadata — a floated cap sitting unreleased in a companion's `main` helps nobody.
`check_publish_drift` compares **file contents** from the published sdist and prints
each companion's published version as a side effect; it exits **2** on a skip,
because a companion that could not be checked is not one that passed.

Per-repo detail: `docs/ecosystem/COMPANION_REPOS.md`. Non-PyPI consumers
(`nodus-vscode`, `nodus-run-action`) are tracked in `tools/consumers.json` and
reported by `nodus_gate --consumers` — **that manifest is the authority for what
each has published**, not prose here, which had nodus-vscode a version behind for a
whole cycle.

### Why ranges are never read by eye

Five of six companions once published `nodus-lang<5.0.0`, so
`pip install nodus-lang==5.0.0 nodus-mcp` was `ResolutionImpossible` and **5.0.0 was
unadoptable for anyone using the ecosystem**. The Stage 6 sweep had asked exactly
this question and transcribed five of six ranges with the upper bound dropped. It
was found by the aindy-runtime team, not by us (#445).

- **`>=4.0.0,<5.0.0` reads as "admits 4.x", which is what the eye checks for.** The
  clause that forbids the new version is at the far end of the string. Not a lapse
  more care fixes — resolve it with `packaging`.
- **A passing companion suite says nothing about installability.** Every dependent
  suite passed against 5.0.0 — run against dev source. They could not have been
  reached through a normal `pip install` at all.

**Policy, decided 2026-08-17: companions do not cap `nodus-lang`.** A hard upper
bound on a first-party dependency turns every major into a two-repo release train
with consumers frozen in between. The companion's own suite catches a real break; a
cap earns its place once a break is known, not before.

### The package count, and why re-deriving it is not enough

**Do not adjust the count by arithmetic; re-derive it** — every first-party name is
listed in `docs/ecosystem/README.md`, so probe each against
`https://pypi.org/pypi/<name>/json` and count what resolves. Two names deliberately
do not: `nodus-vscode` (Marketplace) and `nodus-run-action` (GitHub Action).

**But re-deriving only works if the list is complete, and at 5.8.0 it was not.**
`nodus-a2a-wire` and `nodus-workflow-ai` had no row in that file, so the procedure
returned 35 where the answer was 37. The fix was to add the rows and say in that
file that it is the source for the count — fixing the number alone would have left
it undercounting next cycle. `check_publish_drift` had already carried a comment
about the same miss happening to `nodus-flow`, which sat outside the drift sweep
under both its names. **A package published without a row there is invisible twice
over.**

As of 2026-09-05: **37 standalone companions, 38 PyPI projects** counting
`nodus-lang`. Re-derive rather than trusting that sentence — this was done by
probing every `nodus-*` name in `docs/ecosystem/README.md`, not by adding one to
the previous figure.

Four listed names deliberately do not resolve, and a re-derivation that "fixes"
them is wrong: `nodus-vscode` (Marketplace), `nodus-run-action` (GitHub Action),
`nodus-event` (not implemented), and `nodus-scheduler` — which is written **in
Nodus**, carries a `nodus.toml` rather than a `pyproject.toml`, and has no
channel to publish to, since the Nodus registry named in `ECOSYSTEM_BOUNDARY.md`
was never built (#88, closed on that basis).

### Verify a publish by installing it

**PyPI's JSON API serves stale data after an upload** — it reports the *previous*
release as latest, which reads exactly like a failed upload, and at 5.6.0 it
reported **zero files** for the version that had just landed. The simple index lags
too: `pip install nodus-lang==5.8.0` failed for minutes after the 5.8.0 upload
succeeded. `Cache-Control: no-cache` does not prevent either.

**Only `pip install <name>==<version>` is authoritative.**

### Tokens

**Never write a token into any file in any repo.** `~/.pypirc` holds an
account-scoped token, which works for every first-party project **and creates a new
project on first upload** — no PyPI-side pre-creation step is needed (established
publishing `nodus-workflow-ai`, 2026-08-30). A project-scoped token is an
alternative, not a requirement. If an upload 403s, the password field has gone
empty again — ask the user rather than guessing.

Rate limits apply to **new project creation** (~a few per hour), not to version
uploads on existing projects.

**Publishing a new package:** `python -m build`, `twine check dist/*`, install the
built wheel into a clean venv and run its suite **from a neutral CWD** so you test
the installed package rather than the source tree, then `twine upload`, then verify
by installing from PyPI.

## Release files

| What | Where |
|------|-------|
| Release-claims probes | `tests/eval/release_claims_probe.py` — the Gate 10b harness. **Also run per-PR by CI's `probes` job** (#811), against the wheel it builds, from `/tmp`, with `--require-installed` — 18s on a runner, and off the `test` job's critical path. That does not replace Gate 10b, which still validates the artifact being uploaded; it removes the window where a probe could go stale unnoticed. `tests/test_release_probe_flags.py` additionally checks that every flag a probe passes is one the command's table declares |
| Eval results (per-version) | `docs/evals/vX.Y.Z/` — **three documents per release**: `CREATOR_VALIDATION.md` (Gate 10, pre-publish, against the built wheel), `POSTPUBLISH_EVAL.md` (Stage 5, against the published package), `STAGE6_DOWNSTREAM_SWEEP.md` (companions). See `docs/evals/v5.1.0/` for the current shape |
