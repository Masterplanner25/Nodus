# Agent experience

**Problems agents have hit while working on this repository, what caused them, and what fixed
them.** Search it by the text of the failure in front of you:

```
grep -n -i "<a distinctive part of the error>" docs/AGENT_EXPERIENCE.md
```

This is not an instruction file. Rules live in `CLAUDE.md`, the directory `CLAUDE.md` files
and `.claude/commands/`. This file records what was **observed**, and an entry is evidence,
not policy. A lesson becomes a rule only once it has been reproduced and is general enough
to apply on every task, and then it moves to the rule file and the entry points there.

## What belongs here, and what does not

**A failure you would notice.** Every entry starts from a symptom: an error message, a test
that skips, a gate that disagrees with CI. Retrieval works by searching for that symptom, so
an entry no one could find by its error text does not belong here.

**A silent trap does not belong here.** A test that passes while checking nothing, a pipe that
reports the wrong exit code, or a `git add` that skips a path all give no signal that would
send anyone looking. Those stay in the files that load on their own: `CLAUDE.md` (for
example "Mechanics that have each cost a session") and `tests/CLAUDE.md` ("Writing a test
that can fail").

**One class of defect has its own table.** For a check on one path with a sibling path that
bypasses it, see `.claude/commands/recurring-bug-shape.md`. It is not repeated here.

## Adding or changing an entry

- **Lead with the exact text** of the error or output, in a code block, so a search finds it.
- **Name the evidence:** the issue, PR or measurement that established the cause.
- **State the status.** *Verified* means the cause was reproduced or measured. *Inferred*
  means it follows from the code or from a related diagnosis but was not re-run. *Open* means
  the defect is still live and tracked. *Obsolete* means the cause was fixed: keep the entry
  for anyone on an older build and say from which version it no longer applies.
- **Point to the canonical detail** instead of copying it. The entry is the index from
  symptom to cause, not a second account of the fix.
- **Before adding, search for an existing entry with the same cause** and extend it. Two
  entries for one cause are two voices that will drift.
- **Say "tracked in #N"** for an open defect. `nodus_gate --open-claims` flags the entry once
  #N closes, which is the cue to update its status.

---

## EXP-001: a different test fails on each run, `PermissionError` on `.nodus/graphs`

```
PermissionError: [WinError 5] Access is denied: '...\.nodus\graphs\....tmp' -> '...\.nodus\graphs\....json'
```

- **Cause:** two test runs, or a test run and the doc gate, sharing the repo-root `.nodus/`
  store at the same time. It looks exactly like the #376 race and is not one.
- **Resolution:** stop the other run, then re-run. In the case that established this, the
  same tests then passed 17 of 17.
- **Evidence:** CLAUDE.md, "Test suite"; memory note "Never run two suites at once".
- **Status:** Verified.
- **Applies when:** a suite, gate or companion suite is running in the background.

## EXP-002: `PermissionError` reading or writing a workflow run record from two processes

```
PermissionError: [Errno 13] Permission denied: '...\runs\<id>.json'
PermissionError: [WinError 5] Access is denied: '...\runs\<id>.json.<hex>.tmp' -> '...\runs\<id>.json'
```

- **Cause:** on Windows, a second process holding the record open while
  `LocalWorkflowStore` replaces it. Reads have no retry. Writes retry five times, about
  0.2 s, and a busy reader can outlast that.
- **Measured:** about 5% of reads failed with a reader polling every 10 ms. With a tight-loop
  reader, the writer's `save_run` failed in 5 of 5 runs, within 1–3 s.
- **Resolution:** use the SQLite store for anything more than one process touches
  (`NODUS_WORKFLOW_STORE_BACKEND=sqlite`). The fix in the JSON store is tracked in #939.
- **Evidence:** #939; #376 for the write retry; `OPERATOR_OR_EMBEDDER_RUNBOOK.md` §6.1.
- **Status:** Open. Expected to be Windows-only; Linux and macOS were not tested.
- **Applies when:** a server, sweep or CLI command runs against a store a program is writing.

## EXP-003: tests skip and pytest reports success in a fresh venv

```
DLL load failed ... An Application Control policy has blocked this file
```

The test run then shows `N skipped` and no failures.

- **Cause:** Windows Application Control on this machine blocks native DLLs it has not seen
  before. A fresh venv's new wheel builds are unseen, so an import fails and every test that
  needs it skips.
- **Resolution:** upgrade the existing venvs in place rather than recreating them. If a fresh
  venv is unavoidable, pin to a build the policy already allows (`pydantic-core==2.50.2`),
  and check a native import before trusting a run.
- **Evidence:** CLAUDE.md, "The venvs in this directory"; 2026-11-09.
- **Status:** Verified.
- **Applies when:** creating a venv, or a run's skipped count is higher than expected.

## EXP-004: CI runs stuck in `queued` that can be neither cancelled nor re-run

```
Cannot cancel a workflow run that is completed
run <id> cannot be rerun; This workflow is already running
```

The PR shows "no checks reported" and is blocked.

- **Cause:** runs created during a GitHub Actions outage stayed stranded after GitHub
  recovered, with contradictory state.
- **Resolution:** push an empty commit to the PR branch
  (`git commit --allow-empty -m "Re-trigger CI"`). The squash merge folds it away.
- **Evidence:** PR #930, 2026-11-11. The runs had been queued for about 4 hours, and
  githubstatus.com had shown an Actions major outage.
- **Status:** Verified.
- **Applies when:** a PR is blocked on checks that never start.

## EXP-005: just after an upload, PyPI or the drift check says the release is not there

```
nodus-mcp   DRIFT ...
```

The PyPI JSON API also reports the previous version as latest, or zero files for the new
one, and `pip install <name>==<new>` fails for a few minutes.

- **Cause:** PyPI's JSON API and simple index lag an upload. `check_publish_drift` reads the
  same index.
- **Resolution:** do not treat it as a failed upload. Wait, then verify with
  `pip install <name>==<version>`, which is the only authoritative check, and re-run the
  drift check.
- **Evidence:** `release-sequence.md`, "Verify a publish by installing it". Seen at 5.6.0
  and 5.8.0, and with nodus-mcp 0.1.5.
- **Status:** Verified.
- **Applies when:** Stage 5 or Stage 6, right after a publish.

## EXP-006: `nodus run` stops with `Execution timed out`

```
Sandbox error at <file>.nd: Execution timed out
```

- **Cause:** `nodus run` has a 200 ms default budget, and anything longer is stopped. Each
  workflow resume costs about 99 ms, so two of them already exceed it.
- **Resolution:** `nodus run --time-limit <seconds> <file>`, or
  `NodusRuntime(timeout_ms=None)` when embedding.
- **Evidence:** `.claude/commands/nodus-quirks.md`; #873 for the resume cost.
- **Status:** Verified (reproduced 2026-11-11 with a 10^8-iteration loop).
- **Applies when:** running examples, probes or test `.nd` code through the CLI.

## EXP-007: behaviour contradicts the code you are reading

There is no error message. A fix you can see in `src/` does not take effect, or a
documented flag is unknown.

- **Cause:** the `nodus` that ran is not this tree. Either a venv holds a PyPI install
  rather than the editable one, or the process ran from a directory where a different
  install wins.
- **Resolution:** `.venv/Scripts/python.exe -m pip show nodus-lang` should list
  `Editable project location: C:\dev\Coding Language`. When validating a wheel, run from
  outside the repo, because the root `nodus.py` shim resolves `src/` whenever the working
  directory is the checkout.
- **Evidence:** CLAUDE.md, "Running code during development". `.venv` drifted fifteen
  minors behind before 2026-11-09. The 5.0.3 release passed 32 probes run against the wrong
  tree.
- **Status:** Verified.
- **Applies when:** anything that should have changed did not.

## EXP-008: tests time out and a different one fails each run, and the suite is 2× slower

```
subprocess.TimeoutExpired
```

This shows up in `test_cli_completion.py`'s bash tests, or in any test with a subprocess
timeout.

- **Cause:** the host runs out of physical memory, so starting a process stalls on hard page
  faults.
- **Resolution:** check free memory first (`Get-CimInstance Win32_OperatingSystem`). Under
  about 1.5 GB, treat every timeout-shaped failure as suspect. Re-run the failing test alone,
  then let CI decide.
- **Evidence:** `tests/CLAUDE.md`, measured 2026-09-08.
- **Status:** Verified. It recurs; the condition is the machine, not the tree.
- **Applies when:** any local suite run.

## EXP-009: mypy is clean locally, and CI fails on `src/nodus_lang_workflow/`

```
src/nodus_lang_workflow/<file>.py:<line>: error: ...
```

CI reports this, and the local run of the same command does not.

- **Cause:** locally, mypy reaches that package through a path registered in site-packages,
  and it silences errors in installed packages. CI has no such install.
- **Resolution:** run locally with `--no-site-packages` added.
- **Evidence:** CLAUDE.md, "Lint gate". A planted error was reported only with the flag
  (2026-11-09).
- **Status:** Verified.
- **Applies when:** a change touches `src/nodus_lang_workflow/`.

## EXP-010: `durable_spawn` refuses to start

```
durable_spawn needs a workflow store whose claims are exclusive across processes, ... LocalWorkflowStore is not
```

- **Cause:** the default JSON store's claims hold only within one process, so it cannot
  guarantee that a sweep and a restarted program do not both resume one run.
- **Resolution:** `NODUS_WORKFLOW_STORE_BACKEND=sqlite`. Move existing runs with
  `nodus workflow migrate-store --to sqlite`.
- **Evidence:** #180, #937, `docs/guide/durable-coroutines.md`.
- **Status:** Verified. It is by design until the default flips at 6.0.0.
- **Applies when:** running a durable coroutine on a default setup.

## EXP-011: `git add` refuses a path under `.claude/`

```
The following paths are ignored by one of your .gitignore files:
.claude
hint: Use -f if you really want to add them.
```

- **Cause:** `.claude/` is gitignored, but some files under it are tracked. A refused path
  can abort the whole `git add`, and a following `git push` then pushes a branch without the
  change.
- **Resolution:** `git add -f <path>`, and chain the steps with `&&`.
- **Evidence:** CLAUDE.md, PR workflow; reproduced 2026-11-11.
- **Status:** Verified.
- **Applies when:** editing `.claude/commands/`.

## EXP-012: a compiler change seems to have no effect on a `.nd` program

There is no error message. The program behaves as it did before the edit to
`src/nodus/compiler/`.

- **Cause:** a `.nodus/cache/` entry is reused when the source's path, mtime and SHA-256
  match and the nodus-lang version matches (`_is_valid_cache_payload` in
  `runtime/bytecode_cache.py`; #449, #704). Nothing in that key describes the compiler, so
  an edit to it in a dev tree, with the version unchanged, leaves every cached module as the
  old compiler built it.
- **Resolution:** delete `.nodus/cache/` and run again.
- **Evidence:** #449's diagnosis of the same key after an upgrade; memory note on the #411
  work.
- **Status:** Inferred: it follows from the cache key, read on 2026-11-11, but was not
  re-run for a dev-tree edit.
- **Applies when:** working on the compiler or the lowering of a construct.
