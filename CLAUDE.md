# Nodus — Claude Instructions

## Running code during development

The project `.venv` has a PyPI install of nodus-lang that takes precedence over
`src/` in `sys.path`. Always prefix with `PYTHONPATH` to get the dev source:

```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" ...
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/nodus.exe" run script.nd
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/
```

Without `PYTHONPATH`, you get the installed package, not the current source.
Verify with: `nodus --version` — should match `src/nodus/support/version.py`.

**The gap is live and wide: `.venv` is at 5.0.0, `src/` is at 5.5.0** (re-checked
2026-08-26 with `.venv/Scripts/nodus.exe --version`, at the 5.5.0 cut). Forgetting the
prefix gets you a runtime **nine releases** behind — no `@exactly_once` forgery fix, no
call-depth cap, doubled `main()` on cached runs, `run_source` still running the file its
`filename` happens to name (#521), `nodus graph` still executing the file it inspects
(#400), and none of the resume-durability cluster. The symptom is behaviour that
contradicts the code you are reading.

**Re-check with `.venv/Scripts/nodus.exe --version` rather than trusting this paragraph** — it
has been wrong in both directions. Do not read "the versions match today" as "the prefix is
optional" either; the moment `src/` moves ahead the gap is silent again.

## GitHub API

The `gh` CLI **is installed** and authenticated as `Masterplanner25`. Use it
directly for issue/PR/release operations:

```powershell
gh issue create --title "..." --body "..."
gh repo create Masterplanner25/name --public
gh release create vX.Y.Z --notes "..."
```

For raw API calls not covered by `gh`, use `urllib.request` with a token
retrieved from:

```bash
git credential fill <<< $'protocol=https\nhost=github.com'
```

Repo: `https://api.github.com/repos/Masterplanner25/Nodus`

Standard issue shape:

```python
{
    'title': 'BUG-NNN: short description',
    'body': '## Summary\n\n...\n\n## Reproduction\n\n...\n\n## Expected behavior\n\n...\n\n## Fix direction\n\n...\n\n## Affected versions\n\nv5.0.0 (current).',
    'labels': ['bug', 'subsystem:X', 'severity:low|medium|high|critical'],
    'milestone': None   # always None — see below
}
```

**Milestones are not used. Do not create one, and do not assign one.** Decided
2026-08-26, and all eleven are closed.

They were never a planning tool here — at the moment of the decision **zero of
the 45 open issues carried one**, so nothing was scheduled by them and nothing
moved by touching them. The practice had already lapsed: `v5.0` was the last
milestone created, and 5.0.1 through 5.5.0 all shipped without one. What
remained were five records of finished releases (`v2.1.1`, `v3.0`, `v4.0`,
`v4.0.1`, `v4.1`) left marked open, each with 0 open issues.

Release scope is tracked by `CHANGELOG.md`'s `[Unreleased]` section, which the
release process already reads and which `nodus_gate --closed-issues` already
drives off. That is one mechanism instead of two, and it is the one that has
tests behind it.

`/close-cycle` and `/milestone-transition` both operate on milestones and are
superseded; their headers say so.

Write the script to a temp file and run it — inline heredocs with
triple-quoted strings cause PowerShell/Bash quoting issues.

**This applies to any Python-in-a-heredoc, not just `gh` scripts, and it fails
*silently*.** A quoted `<<'PYEOF'` still mangles backslashes on the way in: a Windows path
written `"C:\\dev\\nodus-x"` arrives as `C:\dev` + a newline, and the script then reports
"not found" for a path that exists. It bit four times in one session. Use the **Edit/Write
tools** for anything containing backslashes, `\n`, or nested quotes — they write the bytes
you asked for. Reserve heredocs for plain prose (commit messages, issue bodies).

## GitHub release immutability — permanent gotcha

**Once a release is created against a protected tag, the tag's immutable state is permanent.**
Deleting the release does NOT clear it. Disabling the branch/tag ruleset does NOT clear it.
`gh release create <same-tag>` after deletion returns: "tag_name was used by an immutable release".

Consequences:
- Never create a GitHub release until you are certain the tag points to the right commit
- Artifact swaps (delete + re-upload) are **impossible** for immutable releases
- The only recovery is a new tag (`v4.0.0-fix1`, etc.) — accept the name change or accept the mismatch

## Version sync — must keep in step

Two files must always match:

- `src/nodus/support/version.py` — `__version__ = "X.Y.Z"`
- `pyproject.toml` — `version = "X.Y.Z"`

Release order — the whole sequence, not just the publish half:

1. Run the gates (`RELEASE_GATES.md`): suite, ruff, `nodus_gate --all`, keyword coverage
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

      Probes must print the **resolved package path and version** before their results.
      Gate 10 passed 5.0.3 with 32 green probes; validating the wrong tree is the failure
      mode, and a header makes it visible.
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

**`/release-prep` is a skill** (`.claude/commands/release-prep.md`) and walks this sequence.
It is **older than the sequence above** — it predates Stage 5, Stage 6, and the
`--closed-issues --section X.Y.Z` re-run, and its Step 5 pushes to `main` directly, which
`enforce_admins` rejects. **This file is the authority; use the skill as a prompt, not a
script.**

PyPI upload — use explicit flags; `~/.pypirc` may have an empty password field
which causes a 403:

```powershell
"C:/dev/Coding Language/.venv/Scripts/python.exe" -m twine upload --username __token__ --password <token> dist/*
```

Token: **`~/.pypirc` was populated with a working nodus-lang token as of 2026-08-17** and the
5.0.0 upload used it. Prefer it over asking. If it 403s, the password field has gone empty
again — ask the user rather than guessing. Never write a token into a repo file.

Full release checklist: `docs/release.md`.

## Guide file testing standard

Every code example in `docs/guide/` must be run and produce verbatim output.
Protocol for each guide file:

1. Create a temp test directory **outside the repo** — use the session scratchpad,
   not `/tmp` (which resolves to `C:\tmp` here) and not the repo root. Writing test
   files into the repo leaves untracked junk; the doc gate already does this, which is
   why `notes.txt`, `output.json`, and `tmp_demo/` are now gitignored.
2. Run each example against dev source using the `PYTHONPATH` prefix above
3. Paste output verbatim into the doc — no invented output
4. Any surprising behavior gets a numbered finding (F32, F33, …) in a
   `<!-- TESTED ... -->` comment block at the bottom of the file
5. File behavioral findings as GitHub issues before committing

Guide files live in `docs/guide/`. The full guide index is in
`docs/guide/getting-started.md §7` and `llms.txt`.

## Key file locations

| What | Where |
|------|-------|
| Version | `src/nodus/support/version.py` |
| Changelog | `CHANGELOG.md` |
| Bug/issue list | GitHub Issues (Masterplanner25/Nodus) |
| Semver policy | `docs/release.md#semantic-versioning` |
| Compatibility policy | `docs/governance/COMPATIBILITY_MODEL.md` |
| Deprecation timeline | `docs/governance/COMPATIBILITY.md` |
| Stability index (surface-by-surface) | `docs/governance/LANGUAGE_STABILITY_INDEX.md` |
| Security posture | `docs/governance/SECURITY_POSTURE.md` |
| Security test matrix | `docs/security/SECURITY_MATRIX.md` |
| Release gates | `docs/governance/RELEASE_GATES.md` |
| Tech debt | `docs/governance/TECH_DEBT.md` |
| Docset index (reader entry point) | `docs/governance/DOCSET_INDEX.md` |
| Ecosystem maturity | `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` |
| Runtime invariants | `docs/runtime/EXECUTION_INVARIANTS.md` |
| Failure model | `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` |
| Embedder runbook | `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` |
| Guide files | `docs/guide/` |
| Runtime reference docs | `docs/runtime/` |
| Governance docs | `docs/governance/` |
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Skills | `.claude/commands/` |
| Doc-vs-code gate | `tools/nodus_gate/` — run `python -m tools.nodus_gate.cli --all` |
| Version-claim manifest | `tools/version_claims.json` — every sentence asserting a current version; checked by `nodus_gate --versions`. Add a claim here, never to a list in prose |
| Dependent-suite gate | `tools/check_dependent_suites.py` — **Gate 10 step 0**, run before any PyPI upload. Names failing tests, classifies recorded flakes, logs full output to `.dependent-suites/` |
| Shape manifest | `tools/shape_manifest.json` — every instance of the recurring bug shape currently in the tree, each `intentional` or `tracked`. The baseline `nodus_gate --shapes` measures new ones against. Adding an entry needs a stated reason |
| Recorded dependent flakes | `tools/dependent_flakes.json` — diagnosed flakes, used to *classify* a red run, never to pass one. Every entry needs a stated reason |
| Downstream range check | `tools/check_downstream_constraints.py` — Stage 6; resolves *published* metadata |
| Publish-drift check | `tools/check_publish_drift.py` — Stage 6; downloads each published sdist and compares file contents. Also prints each companion's published version, which is why this file no longer lists them. Exits **2** on a skip |
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| Companion library contract | `docs/governance/COMPANION_LIBRARY_CONTRACT.md` |
| Pre-publish eval prompt | `docs/governance/EVAL_PREPUBLISH.md` — Gate 10 creator validation |
| Post-publish eval prompt | `docs/governance/EVAL_POSTPUBLISH.md` — Stage 5 independent eval (pointer to template) |
| Stage 4 eval template | `docs/governance/EVAL_STAGE4_TEMPLATE.md` — generalized pre/post-publish template; copy+fill Section 0 & 4 each cycle |
| Eval test scripts | `tests/eval/` — quirk_probe.nd, language_exerciser.nd, framework_capabilities.nd |
| Eval results (per-version) | `docs/evals/vX.Y.Z/` — **three documents per release**: `CREATOR_VALIDATION.md` (Gate 10, pre-publish, against the built wheel), `POSTPUBLISH_EVAL.md` (Stage 5, against the published package), `STAGE6_DOWNSTREAM_SWEEP.md` (companions). See `docs/evals/v5.1.0/` for the current shape |
| Audit prompt index | `docs/governance/AUDIT_INDEX.md` — 9 reusable audit prompts (architecture, runtime readiness + bootstrap, boundary integrity, user reality, capability, limits, security model, infinity runtime, real-world capability) |
| External audit ledger | `docs/governance/EXTERNAL_AUDIT_LEDGER.md` — verdicts on audits run *against* Nodus by outside readers. **Verify a finding before acting on it**; Audit 01 was wrong in 5 places, all negative findings |
| Capability policy design | `docs/governance/CAPABILITY_POLICY_DESIGN.md` — design input for #405, extracted from Codex / Hermes / Claude Code. Read before proposing anything at the host-function chokepoint. **Its staging is not what shipped** — it puts builtins fourth; they had to come first |
| Capability implementation | `src/nodus/runtime/capability.py` — `CapabilityPolicy`, `CapabilityDecision`, `DenyList`, `Floor`, `DEFAULT_FLOOR`, `inherit_authority()` |
| v5 design docs | `docs/design/v5/` — `00-domain-statement.md` (what Nodus is for), `01-goal-stopping-condition.md` (#409), `02-capability-policy.md` (#405) |
| Deny-by-default migration | `docs/migration/v5.0-deny-by-default.md` — the one breaking change in 5.0.0 |
| Goal validation | `src/nodus/frontend/goal_validation.py` — compile-time `reached("label")` checking |
| Maturity checklist + re-score | `docs/governance/MATURITY_CHECKLIST.md` — 72.5 → 82-83 (2026-05-31) |
| Issue response policy | `docs/governance/ISSUE_RESPONSE_POLICY.md` |
| AI discoverability (canonical map) | `llms.txt` |
| AI discoverability (rich summaries) | `llms-full.txt` |
| GitHub wiki (local) | `C:\dev\Nodus Wiki\nodus-wiki\` — git repo, branch `master`, remote `Masterplanner25/Nodus.wiki.git` |
| nodus-mcp companion repo | `C:\dev\nodus-mcp` / github.com/Masterplanner25/nodus-mcp |
| nodus-a2a companion repo | `C:\dev\nodus-a2a` / github.com/Masterplanner25/nodus-a2a |
| nodus-memory companion repo | `C:\dev\nodus-memory` / github.com/Masterplanner25/nodus-memory |
| nodus-native-memory-engine repo | `C:\dev\nodus-native-memory-engine` / github.com/Masterplanner25/nodus-native-memory-engine |
| nodus-extension companion repo | `C:\dev\nodus-extension` / github.com/Masterplanner25/nodus-extension |
| nodus-mcp-server repo | `C:\dev\nodus-mcp-server` / github.com/Masterplanner25/nodus-mcp-server |
| nodus-jupyter repo | `C:\dev\nodus-jupyter` / github.com/Masterplanner25/nodus-jupyter |
| nodus-vscode repo | `C:\dev\nodus-vscode` / github.com/Masterplanner25/nodus-vscode |
| nodus-run-action repo | `C:\dev\nodus-run-action` / github.com/Masterplanner25/nodus-run-action |
| nodus-flow repo | `C:\dev\nodus-workflow` (dir not yet renamed) / github.com/Masterplanner25/nodus-flow. **Was `nodus-workflow` until 0.2.0** — renamed because the name read as the engine behind the `workflow` keyword, which it is not (#483). The old PyPI name is a deprecation alias |
| nodus-sdk repo | `C:\dev\nodus-sdk` / github.com/Masterplanner25/nodus-sdk |
| nodus-store-sql repo | `C:\dev\nodus-store-sql` / github.com/Masterplanner25/nodus-store-sql |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=70 --ignore=tests/test_scheduler_fairness.py -q
```

**2,725 tests collected** (`--collect-only`, 2026-08-25, after the 5.4.0 cut). Coverage
baseline: **76.82%** overall (20,184 stmts) — that figure was measured 2026-08-07 at 1,878
tests and has **not** been re-measured since, so treat it as a floor, not a current reading. Gate: 70% (raised from 60% on
2026-05-31). See `docs/governance/TECH_DEBT.md` for the per-module breakdown.

**Known flaky tests — they fail under *load*, not under repetition.** Both were
characterised on 2026-08-28 and both have issues; neither is fixed. The old wording
here said "pass individually, timing-sensitive in full suite", which sent triage the
wrong way twice: the full suite is merely one way to load the box, and re-running a
test alone on an idle machine cannot clear either of these.

- **`test_scheduler_fairness.py` — both tests, not one (#631).** Under CPU load, 9 of
  10 runs red; idle, ~60 consecutive passes. It does *not* fail from repetition. And
  it is not a fairness failure: the run is killed by the 200 ms wall-clock
  `EXECUTION_TIMEOUT_MS` before the ordering assertion is reached
  (`{'kind': 'sandbox', 'message': 'Execution timed out'}`), so the test asserts the
  box can run 8000 iterations in 200 ms. An earlier revision named only
  `test_long_running_task_rotates_with_budget`; `test_multiple_tasks_progress` fails
  in the same runs.
- **`test_server.py::SQLiteWorkflowServerTests::test_workflow_run_uses_sqlite_store_when_configured`
  (#632).** Reads as a tempdir race and is not one: the database is still open when
  the directory is removed. Windows says so outright (`WinError 32 ... the file is
  being used by another process`); Linux reports only the consequence
  (`Errno 39 Directory not empty`), because WAL leaves `-wal`/`-shm` sidecars. The
  underlying gap is that `SQLiteWorkflowStore` has **no `close()`** — `grep "def
  close" src/nodus_lang_workflow/*.py` is empty — so no caller can release it.

**To reproduce either, load the machine; do not re-run it.** Burn every core but one
in a background process, then run the file. Both go red in minutes that way and pass
indefinitely without it, which is why "it passed when I ran it again" is not evidence
about either of them.

**Do not fix #334's three flakes twice.** `test_async_concurrency_timing.py`,
`test_ieee754_division.py` and `test_workflow_dsl.py` were hardened in PR #581 and are
not on this list.

**Never run two suites at once — they share `.nodus/` and corrupt each other.**

This extends past `pytest`: the **dependent-suite gate** and the **doc gate** both run full
suites, and the companion suites bind ports. Running the wheel probes alongside
`check_dependent_suites` at 5.1.0 turned `nodus-mcp` red; three serial re-runs were green.
One thing at a time when a gate's verdict is going to be believed.

The workflow store, graph registry and bytecode cache all live under the repo-root `.nodus/`,
CWD-relative. A background full-suite run and a foreground targeted run therefore write the same
files. The result looks exactly like a real race: `PermissionError: [WinError 5] Access is denied`
on `.nodus/graphs/*.tmp` → `.json` renames, and **a different test failing each run**.

This bit twice in one session, and both times the first reading was "the #376 race class is back."
It was not. With the background run stopped, the same tests passed 17/17. Before blaming timing or
your own change, check whether anything else is running: `TaskStop` the background job, then
re-run. The same applies to the doc gate (`nodus_gate --runtime` executes 245 blocks and writes to
the store) — do not run it alongside the suite.

**How much of the "flaky machine" is actually this is not established**, and concurrency does
not explain all of it: during the v5.0.0 cut, subprocess tests with 10 s timeouts failed
intermittently with **a different test named each run**, and wall-clock drifted from ~7 to
~18 minutes with nothing else running. Every such failure passed in isolation, and one
(`test_len_returns_int.py`) was verified to fail identically **with and without** the change
under test. CI on a clean runner passed every PR in 5–6 min throughout.

**It comes and goes within a single day. Do not record it as "fixed."** An earlier revision
of this section declared it "environmental and gone" on the strength of one clean 7:46 run —
hours before the same box produced a 15-minute run with 13 failures and then stopped
finishing at all. **One clean measurement does not clear this.** A good run is not evidence
of a good machine, which is the whole reason CI arbitrates.

If you see failures that move between runs and a suite that is suddenly 2× slower, do not
start bisecting your own change. Re-run the failing test alone, then push.

Two practical consequences:

- **A local full-suite run is not a gate here.** Prefer targeted runs over the areas you touched,
  then push and let CI arbitrate. CI on a clean runner finishes in 5–6 min and has been reliable.
- **CI runs `python -m unittest discover -s tests` *and* `pytest`** (`.github/workflows/ci.yml`).
  They are not interchangeable: during the #411 work, CI's unittest step caught two failures that
  `pytest` passed locally — the cause was the environment (`nodus-retry` installed locally, absent
  on a clean runner), not the runner, so **a local pytest run cannot substitute for either.**
  Optional extras are the thing to watch: `@retry` needs `nodus-lang[retry]`.

**Flaky test fix pattern — timing headroom:**
Tests that race a sleep against a timeout need **5–10x headroom**, not 2x. Under full-suite parallel
load, a 20ms sleep takes longer than 20ms wall-clock. Rule: if the test sleeps N ms and the code
times out at M ms, ensure M ≥ 5N.

Two classes can't share incompatible timeout requirements. If a test needs `session_timeout_ms=50`
(to observe expiry quickly) and another needs `session_timeout_ms=2000` (to survive load without
expiring), split them into two classes with separate server instances — one per `setUpClass`.

**Sweeper startup race:** `RuntimeService` starts the sweeper thread in `__init__` with the default
interval. If you set `_worker_heartbeat_timeout_ms` after construction, the sweeper sleeps the
default interval (500ms) before adopting the new value. Fix: pass `worker_sweep_interval_ms=N`
directly to the constructor.

## .nd file formatting — authoritative command

**Always use `python nodus.py fmt` — never `nodus.exe` or bare `nodus fmt`.**

`nodus.exe` in `.venv` is whatever release was last installed there. CI runs
`python nodus.py fmt --check {}` which loads from `src/` (the dev source). Using
`nodus.exe` writes a format that diverges from what CI checks → commits pass locally
but fail CI. This is the writer-vs-checker split that broke the stdlib format gate
repeatedly across multiple pushes.

**The rule holds even when the two happen to be the same version** — it is about which tree is
loaded, not which number is printed. `.venv` matched `src/` as of 2026-08-17 and will drift again
at the next bump.

`nodus fmt` also **used to corrupt files it did not fully understand** — writing output that no
longer parsed, for `GoalPursuit` nodes and `with { }` blocks (#427, fixed in 5.0.0). It now
refuses rather than writing a broken file, and `tests/test_formatter_completeness.py` walks the
AST node list so a **new** node type with no formatter case fails the suite instead of silently
corrupting user code.

To format .nd files correctly (matches CI exactly):
```powershell
# Format one file
python nodus.py fmt src/nodus/stdlib/hash.nd

# Format all stdlib .nd files
python nodus.py fmt src/nodus/stdlib/*.nd

# Verify (verbatim CI check):
find . -name "*.nd" -not -path "./.git/*" -not -path "./.venv/*" -not -path "./tmp_demo/*" -not -path "./tests/fixtures/fmt/*" | xargs -I {} python nodus.py fmt --check {}
```

A pre-commit hook enforces this: if staged `.nd` files fail `python nodus.py fmt --check`,
the commit is blocked and the exact fix command is printed. Hook lives at `.git/hooks/pre-commit`
(not tracked by git — reinstall after fresh clone with `chmod +x .git/hooks/pre-commit`).

## Lint gate (ruff **and mypy**)

**Both run in CI and both block merges. Ruff passing is not evidence mypy will.**

```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m mypy src/nodus/ --ignore-missing-imports --no-error-summary
```

That is CI's invocation verbatim. It is clean today; ignore the `annotation-unchecked`
notes, which are informational and not failures.

The way this bites: **extracting a condition into a helper drops mypy's type narrowing.**
Replacing `if source_path is not None and self._can_skip(...)` with
`if self._cache_is_authoritative(source_path, source)` left `load_cached_bytecode` seeing
`str | None`. Ruff was clean, the tests passed, and CI failed in 19 seconds. Keep the
`is not None` at the call site when the narrowed value is used after the branch.

Ruff runs in CI and blocks merges. Check locally before pushing:

```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
```

Two rules come up repeatedly:

- **F401 unused import** — just remove it; never suppress with `# noqa`.
- **E402 module-level import not at top** — occurs in test files that do
  `sys.path.insert` before imports (intentional path isolation pattern).
  Suppress with `# noqa: E402` on each affected import line. Do not
  restructure the path manipulation to avoid it.

**`ruff check src/ tests/` is clean — 0 errors.** Verified 2026-08-07.

Earlier revisions of this file claimed ~33 pre-existing violations in `vm.py`,
`time_module.py`, `encoding_module.py`, and `secrets_module.py`, and told you to
scope ruff to the files you changed rather than run the whole tree. Those
violations have since been fixed, so that guidance now only hides real
regressions. **Run the full-tree check and treat any output as yours.**

## Git commit syntax (PowerShell)

Multi-line commit messages require a PowerShell here-string — bash `<<EOF`
syntax is not valid in PowerShell:

```powershell
git commit -m @'
Subject line here

Body paragraph here.

Co-Authored-By: Claude <MODEL> <noreply@anthropic.com>
'@
```

**Use the model you are actually running as** — check the environment block at the start
of the session and copy that name verbatim (e.g. `Claude Opus 5 (1M context)`). Do not
copy a model name out of this file or out of `git log`; both go stale at every release,
and a hardcoded name silently misattributes the work. This has already happened once:
commits on 2026-08-07 were trailed `Opus 4.8` while running Opus 5, because this example
named a specific version.

The closing `'@` must be at column 0 with no leading whitespace. For commits
that need a file (e.g. cross-repo where stdin is awkward), write the message
to `.git\COMMIT_MSG_TEMP` with `Out-File -Encoding utf8` then use
`git commit -F ".git\COMMIT_MSG_TEMP"`.

## `nodus <cmd> --help` — safe now, was not (#353, fixed)

`--help`/`-h` is handled **centrally in `main()`**, before any subcommand body runs, so
it prints usage and exits 0 for every command in `KNOWN_COMMANDS`. Running it to learn
what a command does is safe.

**Do not add a per-command `--help` guard.** That pattern is what made this recur four
times (#1/#2, #268, #345, #353): each new subcommand shipped unguarded until someone
noticed. The ten per-command guards were deleted with the fix.

**Still live for any pinned-older environment (through v4.1.1).** There, `--help` *ran the
command*: `nodus logout --help` deleted the saved registry token from `~/.nodus/config.toml`
(this happened, 2026-08-06); `publish` crashed; `login` blocked on stdin; `install` / `add` /
`remove` / `update` / `deps` / `test` ran for real. Against an unknown build, use a throwaway
`HOME`/`USERPROFILE` before running `--help`.

## PR workflow — required (enforce_admins is ON)

`enforce_admins` is enabled on the `main` branch. **Direct pushes to `main` are rejected for
everyone, including the repo owner.** All changes must go through a branch + PR + CI.

Workflow:
1. `git checkout -b <branch-name>` — create a branch
2. Commit and push: `git push -u origin <branch-name>`
3. `gh pr create --title "..." --body "..."` — open the PR
4. Wait for CI to pass, then merge via `gh pr merge --squash` (or GitHub UI)

Never attempt `git push origin main` directly — it will be rejected.

**A commit body that mentions an issue can close it, and negation does not save you.**
GitHub's linked-issue parser matches a keyword (`close`/`fix`/`resolve`, any tense),
an optional colon, whitespace — **including newlines** — and then `#N`. It does no
grammar. So a housekeeping commit whose body reads

```
Filed, not fixed:

  #584  latest_graph_state() returns an arbitrary graph
```

closes #584 on merge. That happened, 2026-08-25, in the commit that filed it. The word
`not` is invisible to the parser; all it sees is `fixed:` … `#584`.

This bites *this* repo specifically, because our commit messages list issue numbers as a
matter of course and the phrasings that precede them — "not fixed", "to fix", "fixes
pending" — are exactly the trap. Write **`Filed (open):`**, **`Reported:`**, or put the
number on its own line well away from any such verb. After merging a PR that names issue
numbers it does not resolve, **check their state** — reopening is cheap, but a silently
closed issue is one nobody looks at again.

## CHANGELOG — update it in the same PR as the change

**Every user-visible change gets a `CHANGELOG.md` `[Unreleased]` entry in the PR that
makes the change** — not in a later sweep. Behaviour changes, bug fixes, new flags, new
gate phases, error-message format changes, performance work users would notice. Pure
refactors and test-only changes do not need one.

Why it must be same-PR: the release process reads `[Unreleased]` to build the release
notes, and the doc gate's `--closed-issues` phase reads issue references out of it to find
the regression tests. A change that lands without an entry is invisible to both. Three PRs
in the #376 series (#384, #388, #389) shipped real correctness fixes with no entry and had
to be reconstructed from `git log` afterwards.

Two conventions that keep the file usable:

- **Merge into the existing section; do not append a new one.** `[Unreleased]` should have
  at most one `### Fixes`, one `### Tooling`, and so on. Appending a fresh `### Fixes`
  per PR produced three of each and had to be untangled by script. Section order:
  `Changed` → `Fixes` → `Performance` → `Tooling`.
- **Reference the issue number on the entry line** (`- **#NNN: one-line summary.**`).
  That reference is what links the entry to its regression test via the `# closes: #N`
  marker (see the gate section below), and the gate reads issue numbers from **entry
  lines only** — so `#N` inside an entry's prose is a free cross-reference and does not
  demand a test. Put the claim on the bullet, discussion underneath.

Known issues belong here too — if something ships with a defect downgraded rather than
fixed, say so in the entry and name the follow-up issue, so it does not vanish at release.

## Doc-vs-code gate (nodus_gate)

The gate is mandatory before any release. Run from the nodus-lang root:

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --all
```

- `--static`: verifies documented symbols exist in the codebase (**135 symbols**
  across 38 documents, as of 2026-08-25)
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs (**245 blocks**); expects 0 failures with the `.nodusgate-allow`
  allowlist in place
- `--closed-issues`: runs closed-issue tests for CHANGELOG-referenced issues
- `--contracts`: verifies `HandlerContract` infrastructure is wired correctly (6 checks)
- `--consumers`: reports **non-PyPI consumers a release has left behind** —
  `nodus-vscode` (VSIX) and `nodus-run-action`. Stage 6's sweep hashes published
  sdists/wheels, so it structurally cannot see either, and both have shipped
  stale. Each records in `tools/consumers.json` the fingerprint of what it must
  stay in step with, measured **here**; when the live value moves, the consumer
  needs republishing. Reads no sibling checkout on purpose — a gate that needs
  one skips on CI, which is how `when` shipped unhighlighted. **Advisory**: it
  prints and exits 0; `--strict` makes a stale consumer fail. A manifest that
  cannot be read is always a failure. Clear a flag by republishing, then updating
  `fingerprint` and `published` in the same commit.
- `--opcodes`: verifies the frozen instruction set — reads the dispatch table
  out of a constructed `VM` and requires `BYTECODE_REFERENCE.md` §3, its
  appendix table, and the `FREEZE_PROPOSAL.md` stability tables to name the same
  49 opcodes, with matching counts and `BYTECODE_VERSION`. **If you add an
  opcode, this fails until you document it** — that is the point (#366)
- `--shapes`: reports **new instances of the recurring bug shape** — the section
  below is the reason this phase exists. It scans `src/` for the three species
  that leave a syntactic trace: one question implemented under the same name and
  signature in two modules (**A**), one vocabulary enumerated twice with a member
  missing (**B**), and module-scope state every participant in a process shares
  (**D**). Species C (the cache as a sibling path) and E (the bound on the wrong
  substrate) are not detectable and are not attempted.

  `tools/shape_manifest.json` records **every shape currently in the tree** — 43
  of them — each with `intentional` (these are not one question) or `tracked` (a
  real debt, with its issue). That baseline is the design: the value is not the
  list, it is that the *next* duplicated question shows up as **NEW** the day it
  lands. It also records `sites` per species-A entry, because the key is
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

The allowlist at `.nodusgate-allow` suppresses intentionally non-runnable
doc blocks (multi-file examples, error demos). New failing blocks go in the
allowlist OR are fixed before release.

**Regression test convention for `--closed-issues`:** add a `# closes: #N`
comment immediately before the test function that verifies a fix. The
`closed_issues_phase` scanner finds tests by this marker:

```python
# closes: #99
def test_spawn_threads_joined_on_reset(self):
    ...
```

Without the marker, the gate reports the issue as "no test found" and the
closure-verification step in `PLAYBOOK_PATCH_MINOR.md` Stage 3 will fail.

**Golden bytecode tests:** `tests/test_bytecode_golden.py` checks opcode
sequences for core constructs against fixtures in `tests/fixtures/bytecode/`.
Re-generate after intentional compiler changes:

```powershell
NODUS_UPDATE_GOLDEN=1 PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/test_bytecode_golden.py -q
```

## nodus-mcp companion library

- Repo: `C:\dev\nodus-mcp` / `github.com/Masterplanner25/nodus-mcp`
- **Published on PyPI** (version: `check_publish_drift`). Its `nodus-lang` cap is floated.
  BYTECODE_VERSION 4, no new opcodes.
- **Dual layout**: `src/nodus_mcp/` = full MCP protocol library (Phase A–N);
  `nodus_mcp_aindy/` = aindy-derived bridge adapter (wraps ToolRegistry as MCP server).
  The pyproject.toml `where = ["src"]` installs the Phase A–N library; the aindy
  adapter is importable as `nodus_mcp_aindy` but is not the primary package.
- Dev install: `pip install -e . --no-deps`
- Run tests: `cd C:\dev\nodus-mcp && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`
- **egg-info pitfall**: If `nodus_mcp.egg-info/` appears in the repo root (generated
  by old `setup.py develop` runs), pytest adds the rootdir to sys.path and
  `importlib.metadata` finds the stale egg-info instead of the site-packages dist-info.
  This breaks entry-point discovery. Fix: `rm -rf nodus_mcp.egg-info && pip install -e . --no-deps`.
  The `*.egg-info/` is in `.gitignore`.
- Entry-point contract: `[project.entry-points."nodus.nd"]` → callable returns
  absolute path to `.nd` root dir — see `docs/guide/library-entry-points.md`
- Key contracts: TD-007–010 in `docs/governance/TECH_DEBT.md`.

## nodus-a2a companion library

⚠️ **LOCAL REPO REPLACED.** Local `C:\dev\nodus-a2a` is the Tier 2 AgentCoordinator (23 tests, no nodus-lang dep).

**Current local `C:\dev\nodus-a2a` (AgentCoordinator layer, 23 tests):**
- `AgentRegistry`, `AgentCoordinator` (local/delegate mode), `DelegationRequest`
- `DeadLetterService`, `StuckRunWatchdog`
- No nodus-lang dependency; standalone coordination primitives
- This is the one on PyPI, and the only one `check_publish_drift` tracks.

### The wire adapter, and the two `C:\codev` directories — corrected 2026-08-26

The original A2A **wire-protocol** adapter (`A2AHttpServer`, transport layer,
nodus-lang dep) is **188 tests**, not the 180 an earlier revision of this section
claimed. It is **not on PyPI**, and it is a **CrewAI-showcase spin-off**, not a
maintained companion — `C:\codev\nodus-showcase-crewai` is what needed it.

**There are two `C:\codev` directories and they are not interchangeable.** An
earlier revision named only the first and called it "the local worktree" of the wire
repo. It is not:

| Directory | Remote | Branch | What it actually is |
|---|---|---|---|
| `C:\codev\nodus-a2a-wire` | **`nodus-a2a`** | **detached at `10746ce`** | a worktree of the *coordinator* repo's old history — pulls and pushes go to the wrong project |
| `C:\codev\a2a-wire-pub` | **`nodus-a2a-wire`** | `main` (tracked `origin/wire-adapter`, gone) | the one that actually corresponds to `github.com/Masterplanner25/nodus-a2a-wire` |

So the directory named `nodus-a2a-wire` is the one that is *not* the wire repo. Use
**`a2a-wire-pub`** for anything touching that GitHub repo.

**Published 2026-08-26 as `nodus-a2a-wire` 0.1.0** (#477). Module `nodus_a2a_wire`,
**no runtime dependencies**, 188 tests. Work in `C:\codev\a2a-wire-pub`, which is
the only checkout wired to that repo.

Three things it needed, and the middle one is the lesson:

- `name = "nodus-a2a"` → `nodus-a2a-wire`. The distribution name was taken.
- **The Python module was `nodus_a2a` — the same module the published coordinator
  ships.** Renaming the distribution alone would have left both writing one
  directory into site-packages. Measured: installing the wire adapter on top of
  the coordinator left `AgentCoordinator`, `AgentRegistry` and `DeadLetterService`
  **gone**, with pip reporting success both times. This is NAME-COL-001 again —
  the distribution name is what a user types, the module name is what Python
  resolves, and fixing one does not fix the other.
- **`nodus-lang` was in `dependencies` and never imported.** `grep -rnE
  "^\s*(from|import)\s+nodus" src/` is empty; the one import in the tests sits in
  a `try/except ImportError` that skips. Per the dependency-audit rule, that is
  not a dependency — a host constructs `A2AHttpServer` and wires it to their own
  `NodusRuntime.tool_registry`. It is a `dev` extra now. The declaration had also
  capped `<5.0.0`; the suite is 188/188 against 5.5.0, so the cap protected
  nothing.

**`twine` 6.2.0 rejects hatchling's `Metadata-Version: 2.5`** as invalid — upgrade
to 7.0.0. It looks like a broken package and is a stale validator.

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **`+=`, `-=`, `*=`, `/=` work** (added in 4.0.1 pre-release, PR #183). In closures, you
  still can't assign outer `let` variables at all — use a **map** with quoted keys and mutate
  via bracket notation: `state["count"] = state["count"] + 1i`.
  (The pattern uses `{"count": 0i}` — quoted-key map — NOT `{count: 0i}` record.)
- **Maps vs Records — dot vs bracket notation:**
  - `{"key": val}` (quoted keys) → **map** → access with `state["key"]`
  - `{key: val}` (unquoted keys) → **record** → access with `state.key`
  - Mixing them causes "Field access is only supported on records" or
    "Indexing is only supported on lists and maps". Never use dot on a map.
- **`run_workflow()` and `run_goal()` return maps** — use bracket notation:
  `result["steps"]`, `result["failed"]`, `result["goal"]`. NOT `result.steps`.
- **Channels are built-in functions, NOT a stdlib module.** `import "std:channel"`
  fails with "Import not found". Use built-ins directly: `channel()`, `send(ch, val)`,
  `recv(ch)`, `close(ch)`. No import needed.
- **Workflow step dependencies use `after` keyword:**
  `step b after a { ... }` — not `depends_on`, not any other syntax.
- **`checkpoint` is valid INSIDE step bodies only**, not at workflow-body level.
  `step a { checkpoint "mid"; return "done" }` — correct.
  `workflow w { checkpoint "mid"; step a { ... } }` — syntax error.
  **And it is a re-entry label for its whole step, not a position marker** (#486):
  a resume re-enters the step from the top, so effects before the checkpoint run
  again on every resume. Split the step at the checkpoint to skip completed work.
  State re-derives deterministically — including folded cells since the #486 fix
  (`resume_state` on the engine checkpoint; before it, `merge: "sum"` counted
  pre-checkpoint contributions once per resume).
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` takes a coroutine value**, not a function literal. Use
  `let c = coroutine(fn() {...})` then `spawn(c)`.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **`if` conditions with function calls require parentheses.** `if (module.fn(a, b))` works;
  `if module.fn(a, b)` gives "Expected '(', got identifier". Simple field access works without
  parens (`if record.field`), but call expressions need `if (expr)`.
  **A bare `state` variable also needs them** inside a step body: `if approve { ... }` gives
  "Expected '(', got identifier ('approve')"; `if (approve) { ... }` works.
- **A `state` cell cannot hold a record.** The run aborts at persist time with
  `Object of type Record is not JSON serializable`, blamed on the `run_workflow(...)` call
  site rather than the assignment. Records are ordinary data with an obvious JSON shape, so
  this reads as a plain gap rather than the live-handle case — but it is the same
  undeclared serializability requirement as a closure or a channel (#498). Use a map.
- **Seven task statuses, and `on:` admits three of them.** `statuses` reports `completed`,
  `failed`, `upstream_failed`, `skipped`, `omitted`, `cancelled`, `abandoned`;
  `with { on: [...] }` accepts only `completed`, `failed`, `skipped` — the three a dependency
  can reach *while the run is going*. The rest are end-of-run conclusions, so a step waiting
  on one could never become ready, and they are refused at declaration. The vocabulary is
  named once in `TASK_STATUSES` / `JOIN_ON_STATES` and pinned by
  `tests/test_status_vocabulary.py`; do not re-enumerate it in prose without checking those.
- **Multiline list literals and function calls cannot span newlines.** Both
  `[1,\n2]` and `len(\n"hi"\n)` give "Unexpected end of statement". Keep on one line.
- **`print()` is single-argument.** `print("label:", value)` → syntax error.
  Use string interpolation: `print("\(label): \(value)")`.
- **`std:hash` returns a hash record, not a string.** `hash.sha256(data)` returns
  a record with methods; call `.to_hex()` to get hex: `hash.sha256(data).to_hex()`.
- **`std:tool` names must be dotted.** `tool.register({name:"greet",...})` silently
  returns an error. Use `"myapp.greet"`. Error message says "must use dotted namespacing".
- **`http.get()` and `subprocess.run()` return records** — use dot notation:
  `result.status`, `result.body`, `result.ok` (http); `result.stdout`, `result.exit_code` (subprocess).
- **CLI sandbox flag is `--allow-paths`** (not `--allowed-paths`). Relative paths
  resolve against CWD. To block a specific subdir, pass an explicit absolute path.
- **`goal … over …` is the v5.0.0 stopping-condition form** (#409). A goal now wraps a workflow
  and re-runs it until a predicate holds:
  ```
  goal reach_quality over tune {
      until reached("good_enough")
      budget { max_iterations: 5, deadline_ms: 30000 }
  }
  ```
  `reached("label")` refers to a `checkpoint "label"` inside a step body. **A label that no step
  emits is a compile error**, not a silent never-satisfied loop (`frontend/goal_validation.py`) —
  so `nodus check` catches the typo. Result map adds `goal_satisfied` and `iterations`.
  Five new **contextual** keywords: `over`, `until`, `budget`, `reached`, `retry` — contextual, so
  they remain usable as identifiers.
- **Coroutine execution limits (scheduler quirk):** The default 200ms deadline
  (`EXECUTION_TIMEOUT_MS=200`) counts wall-clock time including cooperative sleep.
  A coroutine that sleeps 4 × 100ms will be killed after 200ms total even though it
  consumed no CPU. Workaround: `nodus run --time-limit N`. SCHED-001, deferred to 4.0.1.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.

## The recurring bug shape — a check on one path, a sibling path that bypasses it

This codebase's most common defect is not a wrong check. It is a **correct check that only one
of several paths goes through**. It has now surfaced **twenty-one** times across the v5.0.0–5.4.0
cycles, which is why it gets its own section: when you find one, the next question is always
*"what else has this shape?"* — not *"is this fixed?"*

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

**There is a gate for this now — `nodus_gate --shapes`.** It will not find the shape for you in the sense of telling you what is broken; it finds *places where one question is answered in more than one voice*, which is where every instance above came from. Its first run produced #597 and #598. `tools/shape_manifest.json` holds the 43 it already knows about, so what it reports is the ones that are new. When you add a second implementation of anything, expect to justify it there.

**The fix is always the same: move the decision to one place, then assert on the source.** A
behaviour-only test passes on whichever path is already correct. Working examples to copy:
`test_retry_path_unification.py` asserts where the retry branch *lives*;
`test_vm_authority_inheritance.py` reads `VM.__init__`'s signature so a **new** parameter nothing
propagates fails; `test_annotation_forgery.py` fails if any lowering emits an unbound
`Call(Var(...))`; `test_workflow_runner_ownership.py` fails if a **sixth** builtin resolves the
runner from module state while the other five stay routed.

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

## Documentation governance

The governing docset layer was established in a 2026-05-29 sweep. Key rules:

- **`docs/governance/DOCSET_INDEX.md`** — the reader entry point and precedence list.
  When docs conflict, DOCSET_INDEX.md defines which wins.
- **`docs/governance/DOCSET_ALIGNMENT_AUDIT.md`** — 14 findings from that sweep.
- **`docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`** — **closed.** All
  seven conflicts were verified resolved on 2026-08-07. Its status flags had said
  "ACTION REQUIRED" for months after the fixes landed, because the tracker was
  maintained by hand separately from the work. Do not use it as a to-do list.

**19 governance docs still open with `<!-- Authored by Codex during non coding
session. Needs review before repo commit and push. -->`** — including
`DOCSET_INDEX.md`, which is the reader entry point, and `SECURITY_POSTURE.md`. They
were committed and pushed on 2026-05-29, so the marker is self-contradicting. Left in
place pending a decision on whether to strip them.

## nodus-memory companion library

⚠️ **LOCAL REPO REPLACED.** Local `C:\dev\nodus-memory` is the Tier 2 full memory library (28 tests).

The original nodus-lang adapter (192 tests, `attach_to_runtime`, `nm_*` host functions,
`import "nodus-memory"`) exists **in git history only** — commit `f02ab1e`, which still
carries `src/nodus_memory/nodus_bindings.py`. Commit `6d3a241` ("remove stale nodus-lang
adapter") deleted it from the tree. Earlier wording here said it was "preserved at
`github.com/Masterplanner25/nodus-memory`", which reads as *go clone it*; the current
tree there is the Tier 2 library. Recover with `git show f02ab1e:src/nodus_memory/nodus_bindings.py`,
or give it its own repo the way `nodus-a2a-wire` got one.

**Current local `C:\dev\nodus-memory` (Tier 2 full library, 28 tests):**
- `MemoryNode`, `InMemoryStore`, MAS `build_path()`/`glob_match()`
- `score_nodes()`, `update_feedback()`, `recall()`/`recall_async()`, `EmbeddingProvider` protocol
- No runtime dependencies (`dependencies = []`); optional `pgvector` and `openai` extras
- Flat layout (`nodus_memory/`), setuptools build
- Run tests: `cd C:\dev\nodus-memory && python -m pytest -q`

## nodus-native-memory-engine companion library

- Repo: `C:\dev\nodus-native-memory-engine` / `github.com/Masterplanner25/nodus-native-memory-engine`
- **Published on PyPI** (version: `check_publish_drift`). PyO3/Maturin Rust extension; pure-Python fallback for all operations. `is_native()` → True when Rust extension loaded.
- **Build requires Rust:** `VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release`
  Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed.
- Run tests: `cd C:\dev\nodus-native-memory-engine && "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q`

## nodus-extension companion library

- Repo: `C:\dev\nodus-extension` / `github.com/Masterplanner25/nodus-extension`
- **Published on PyPI** (version: `check_publish_drift`). BYTECODE_VERSION 4, no new opcodes.
- **Purpose:** Typed, versioned, sandboxed plugin framework. Third-party developers
  write `nodus-extension.json` + `extension.py`; the framework loads them via subprocess.
- **Python API:** `ExtensionRegistry`, `ExtensionHost`, `attach_to_runtime(runtime, registry)`
- **Nodus bindings:** `import "nodus-extension"` → `ext_load(path)`, `ext_list()`,
  `ext_invoke(name, tool, args_json)`, `ext_describe(name)`
- **Host functions use `_ext_` prefix** (not `ext_`): `_ext_load`, `_ext_list`, etc.
  The .nd wrappers are named `ext_load`, `ext_list` etc. (same split as nodus-memory)
- **ext_invoke takes args as JSON string** — not a Nodus map. Caller must pass e.g.
  `ext_invoke("myext", "tool.name", "{\"key\": \"value\"}")`.
- **Sandbox tier 1 only** (subprocess, insecure-dev). OCI/VM deferred to v0.2.
- **Capability gate:** extension must declare `"tool.invoke"` to call tools.
- Dev install: `pip install -e . --no-deps` (from `C:\dev\nodus-extension`)
- Run tests: `cd C:\dev\nodus-extension && PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q`

## Standalone package ecosystem (at `C:\dev\`)

All packages have GitHub repos under Masterplanner25. No nodus-lang dependency unless noted.
Test command: `cd C:\dev\<pkg> && python -m pytest -q`.
Package tables (deps + key abstractions by tier): `docs/ecosystem/PACKAGE_QUICK_REF.md`.

### Dependency audit (critical pattern)

**Rule — before adding a dep:** Check that it has a module-level unconditional import with no fallback. `TYPE_CHECKING`, `try/except ImportError`, and constructor injection all mean optional.

### `.nodus/` cache in standalone packages

When nodus-lang tests run inside a standalone package directory, nodus may
write a `.nodus/` cache directory (bytecode cache, graph state). This has been
added to `.gitignore` in all repos but watch for it in new packages — it can
contain hundreds of files that should never be committed.

### Ecosystem dependency notes

- **nodus-extensions** test fix: use `asyncio.run()` not `asyncio.get_event_loop().run_until_complete()` (Python 3.11+)
- nodus-queue redis tests need a live Redis server — always run with `--ignore=tests/test_redis_backend.py` in dev
- **nodus-mcp** test_phase_m.py has 2 port-conflict-sensitive tests — they pass individually but fail in full suite runs (pre-existing race condition, not a code bug)

### In-tree framework modules (namespace-qualified to avoid collision)

The in-tree workflow and schema modules were renamed in 2026-05-31 (NAME-COL-001 Option A)
to avoid install-order collisions with the same-named standalone PyPI packages. The
install-order collision is now resolved.

| In-tree module | Python import | Standalone package | Python import |
|----------------|---------------|--------------------|---------------|
| `src/nodus_lang_schema/` | `nodus_lang_schema` | `C:\dev\nodus-schema` | `nodus_schema` |
| `src/nodus_lang_workflow/` | `nodus_lang_workflow` | `C:\dev\nodus-workflow` | `nodus_flow` (PyPI `nodus-flow`) |

**In-tree vs standalone — different scope, different content:**
- `nodus_lang_schema` = runtime ABI contracts for syscalls and extension surfaces (used by nodus-lang internally)
- `nodus_schema` (standalone) = general schema validation library (SchemaRegistry, parse_versioned_name)
- `nodus_lang_workflow` = full orchestration framework wired into the nodus-lang server (7-state lifecycle, SQLite store, HTTP/CLI)
- `nodus_workflow` (standalone) = lightweight workflow primitives (FlowDefinition, SchedulerEngine, no server wiring)

**Option C consolidation** (make standalone packages canonical, remove in-tree modules,
have nodus-lang depend on them) is **deferred indefinitely** — #104 was closed as
completed on 2026-06-06 because the rename above resolved the collision by construction.
The skill `/nodus-name-col-consolidation` still exists if the decision is ever revisited,
but there is no open work item.

## Ecosystem incubators (`packages/` in this repo)

Eight Python-first scaffold packages live at `C:\dev\Coding Language\packages\`.
They are **design references / API contracts**, not production implementations.

- `nodus-a2a`, `nodus-agent`, `nodus-event`, `nodus-events`, `nodus-http`,
  `nodus-memory`, `nodus-retry` (dir names have no `-spec` suffix; the Python
  module inside each is `nodus_<name>`)
- **`nodus-store-sql` has been promoted** — no longer an incubator scaffold;
  production package at `C:\dev\nodus-store-sql` (47 tests, sync+async). Its dir
  still exists under `packages/` but is superseded by the standalone repo.
- **The scaffolds share Python module names with the published production
  packages** (`nodus_agent`, `nodus_events`, `nodus_retry`, …). In a venv where the
  production packages are editable-installed, `import nodus_<name>` would otherwise
  resolve to the **production** package, not the scaffold. The scaffolds with a
  `src/` layout set `pythonpath = ["src"]` in their pytest config so their own
  package is imported instead (fixed for `nodus-agent`/`nodus-events`/`nodus-retry`
  in #312). Still, do not pip-install a scaffold alongside its production namesake.
- Run incubator tests from within each package directory:
  ```powershell
  cd "C:\dev\Coding Language\packages\nodus-memory" && python -m pytest -q
  ```
  All scaffolds now collect and pass in a dev venv (agent 9, events 5, retry 8,
  a2a 9, event 8, http 5, memory 6, store-sql 6).
- Spec docs live at `docs/ecosystem/` (NODUS_HTTP.md, NODUS_RETRY.md, etc.)

## nodus-workflow (in-tree framework)

- **Location:** `src/nodus_lang_workflow/` (in this repo, not a separate package yet)
- **Status:** Near-runtime-complete. Core semantics complete; production hardening
  and packaging documented in `plans/nodus-workflow-framework.md`.
- **Test file:** `tests/test_nodus_workflow_framework.py` (30 tests)
- **7 run states:** `pending → running → waiting → retry_scheduled → completed / failed / dead_lettered`
- **Backends:** `LocalWorkflowStore` (file-backed) and `SQLiteWorkflowStore` (cross-process)
- **VM builtins added:** `workflow_wait(event_type, ...)`, `resume_workflow(id, checkpoint, payload)`,
  `workflow_resume_payload()` — delegate to `get_default_workflow_runner()`
- **CLI:** `nodus workflow runs|inspect|dead-letters|replay|migrate-state`
- **HTTP:** `GET /workflow/runs`, `GET /workflow/runs/{id}`, `GET /workflow/dead-letters`, `POST /workflow/replay`
- **Server flags:** `--workflow-store-backend {local|sqlite}`, `--workflow-store-path PATH`

**Operational gotcha — local store scan performance:**
`LocalWorkflowStore.list_runs()` reads every `.nodus/workflow_framework/runs/*.json`
on every sweep, so **cost is linear in the number of accumulated runs**. #380 made it
roughly 4× cheaper — the cost was never parsing, it was `nt.mkdir` (the store re-created
its own directory once per record) and an `os.path.exists` before every `open` — but
linear it remains.

**Do not quote a file-count threshold here.** Two earlier revisions did and both were
wrong in the same direction; the numbers are cheap to regenerate and have moved twice.
Measure if you need one. The bound itself is still open in #380.

The default store root is **CWD-relative**, so anything running a workflow from
the repo root writes there. As of #380 the suite and the doc gate clean up after
themselves (`tests/conftest.py`, `tools/nodus_gate/runtime_phase.py`) — check this
before blaming a flake on timing:

```powershell
ls .nodus/workflow_framework/runs | Measure-Object -Line
ls .nodus/graphs | Measure-Object -Line
```

**Both halves are covered as of #585.** They were not: the gate redirected
`NODUS_WORKFLOW_STORE_ROOT`, which moved the run records only, so one
`nodus_gate --runtime` run added **0** run records and **67** graph-state files, every
time. `_GRAPH_ROOT` was a hardcoded module constant and had no override at all.

`NODUS_RUN_STATE_ROOT` now relocates **both halves together**. The gate does **not**
set it yet, so a `--runtime` run still leaves ~67 graph-state files here: pointing it at
the new variable works locally (measured: 5,799 graphs before and after a full runtime
phase) and reproducibly turns
`test_agent_handler_timeout.py::test_a_step_timeout_bounds_a_blocking_handler` red on CI
— 6/6 with the change, 0/9 without, across five bisect branches. **#596** carries the
evidence; do not re-apply that two-line change without reading it.
`NODUS_WORKFLOW_STORE_ROOT` still works and still moves the records only; that is the
half-relocated state #585 is about, so prefer the former. There is deliberately **no**
graphs-only variable: a second knob would re-enable exactly what this fixed.

`conftest.py` still cleans up rather than redirecting, because several tests chdir into
a project directory and assert the default runner wrote under *that* root (26 failures
when redirection was tried) — but it now sweeps both halves off one list rather than
growing a second hand-maintained sweep.

Two things not moved by that variable, on purpose. `.nodus/{cache,modules,deps.json}`
are **project**-scoped, resolved against `find_project_root()`, and have nothing to do
with which run wrote them. And historic accumulation is not cleared by the fix —
`nodus workflow cleanup --force` does that (the 30-day default retention will not touch
anything from this week).

**The Floor follows the roots now, and did not before.** `DEFAULT_FLOOR` forbids a
program writing into the runtime's own state by matching a literal `.nodus` path
segment — so the *supported* way to relocate the store also moved it outside the
Floor's reach. Demonstrated, not inferred: with `NODUS_WORKFLOW_STORE_ROOT` set, a
guest's `fs.write("../relocated/pwned.txt", "x")` landed in the live run store while
the identical write to the default location was denied. Any new state directory must go
through `nodus/runtime/state_paths.py`, or it is unprotected.

`rm -rf .nodus/workflow_framework/runs` is safe **in this repo's root** (test
artifacts only) — but it is not a general cleanup: a run is split across that
directory and `.nodus/graphs/`, and deleting only the records makes any live
waiting run unresumable while its state survives (#476; the resume now says so
instead of "not found"). Use `nodus workflow cleanup`, which removes both
halves.
`NODUS_RUN_STATE_ROOT` relocates both halves of a run's state for a process
(`NODUS_WORKFLOW_STORE_ROOT` moves the records alone). Bounding
the store's cost — pruning by count, or an index instead of a full rescan —
is still open in #380.

**Circular import (CIRC-001, #103) — FIXED** 2026-06-01. `nodus.vm.vm` no longer imports
`get_default_workflow_runner` at module level; the imports are lazy, inside
`builtin_run_workflow` / `builtin_resume_workflow` (`vm.py:1077`, `:1139`, `:1154`).
Importing `nodus_lang_workflow` before `nodus` in a fresh process is safe. Do not
"fix" this again by hoisting the import.

## nodus_lang_schema (in-tree ABI contracts package)

- **Location:** `src/nodus_lang_schema/` — renamed from `nodus_schema` (NAME-COL-001, 2026-05-31)
- **Python import:** `from nodus_lang_schema.syscalls import SyscallSpec`
- **Exports:** `SyscallSpec`, `parse_syscall_name()`, `resolve_version()`,
  `validate_input()`, `validate_output()`, `validate_payload()`, extension ABI models.
- **Note:** Not the same as the standalone `nodus-schema` package (`C:\dev\nodus-schema`).
  Option C post-launch will consolidate these. Skill: `/nodus-name-col-consolidation`.

## nodus-vscode VS Code extension

- Repo: `C:\dev\nodus-vscode` / `github.com/Masterplanner25/nodus-vscode`
- **Live on the VS Code Marketplace** under publisher `MasterplanInfiniteWeave`. The
  published version is recorded in `tools/consumers.json`, not here — this line said 0.1.2
  for a full cycle after 0.1.3 shipped. Marketplace validation takes **~4 minutes**; a
  gallery-API check immediately after upload still reports the previous version, which is
  not a failure.
- **It must be republished when the keyword set changes.** `nodus_gate --consumers`
  fingerprints the keywords here and flags it when they move.
- **Phase 1:** TextMate grammar, 23 snippets, bracket/fold config
- **Phase 2:** Diagnostics via `nodus check` (fallback; skipped once LSP starts)
- **Phase 3:** Run File (`Ctrl+Alt+N`), Format File, DAP debugger (`Ctrl+Alt+D`, `nodus dap`)
- **Phase 4:** LSP via `nodus lsp` — hover docs, go-to-definition, completions
- **Build:** `cd C:\dev\nodus-vscode && npm run package` (requires `@vscode/vsce`)
- **Publish — the update path is not the first-publish path.** `package.json`
  `publisher` must be `MasterplanInfiniteWeave`, and bump `version` before packaging.
  - **Updating an existing extension** (the normal case): go to
    <https://marketplace.visualstudio.com/manage/publishers/MasterplanInfiniteWeave>,
    find **Nodus Language** in the list, use the row's **`…` menu → Update**, and
    upload the new `.vsix`. Validation takes a few minutes.
  - **First publish only:** `+ New extension` → `Visual Studio Code`. Using this for
    an update is wrong — the extension already exists.
  - **Or by CLI:** `npx vsce publish -p <PAT>` from the repo (`vsce` is already in
    `node_modules`). The PAT is an Azure DevOps token with **Marketplace → Manage**
    scope and organization set to **All accessible organizations** — scoping it to a
    single org is the failure that looks like a bad token.
- **Verify a publish** without opening a browser:
  ```powershell
  # POST to the gallery API; latest version is versions[0]
  # https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery
  # filterType 7 = extension name, value "MasterplanInfiniteWeave.nodus-lang"
  ```
- **This extension is not on PyPI**, so the Stage 6 content-hash sweep cannot see it.
  A release that adds or removes a keyword must republish it — see Gate 3b.
- **Key settings:** `nodus.executablePath` (default: `nodus`), `nodus.lspCommand` (array, overrides LSP command — useful for dev source: `["C:/dev/Coding Language/.venv/Scripts/python.exe", "C:/dev/Coding Language/nodus.py", "lsp"]`)
- **LSP note:** VS Code spawns the INSTALLED `nodus.exe`, not dev source. LSP server changes require a new nodus-lang release to take effect in the extension.

## nodus-mcp-server

- Repo: `C:\dev\nodus-mcp-server` / `github.com/Masterplanner25/nodus-mcp-server`
- **Published on PyPI** (version: `check_publish_drift`). Install via `pipx install nodus-mcp-server`.
- **Supports two transports:**
  - **Claude Desktop (stdio):** Add to `claude_desktop_config.json` under `mcpServers`
  - **ChatGPT Desktop (HTTP/SSE):** Run `nodus-mcp-server --http --port 8765`, tunnel via ngrok
- **HTTP transport uses `StreamableHTTPSessionManager`** (MCP SDK 1.28.0), single endpoint `POST /mcp`.
  The old `SseServerTransport` (two-endpoint SSE) is broken — do not use it.
- **ngrok static domain:** `nodusmcpserver.ngrok.io` (paid plan). ChatGPT Desktop requires public HTTPS;
  server runs plain HTTP, ngrok terminates SSL. Point ChatGPT at `https://nodusmcpserver.ngrok.io/mcp`.
- **Windows auto-startup:** Registry `HKCU:\Software\Microsoft\Windows\CurrentVersion\Run` runs
  `C:\Users\shawn\.nodus-mcp-server\startup.ps1` at login (no admin needed). Starts server + ngrok.
- **Shared memory:** Both Claude Desktop and ChatGPT Desktop read/write the same SQLite DB at
  `~/.nodus-mcp-server/data/memory.db` — memory written in one AI is readable by the other.
- **6 MCP tools:** `nodus_run_goal`, `nodus_run_workflow`, `nodus_resume_workflow`,
  `nodus_store_memory`, `nodus_recall`, `nodus_list_graphs`
- **goal vs workflow naming convention:** `goal` = outcome-oriented, single-shot (steps are impl details);
  `workflow` = process-oriented, resumable (pipeline itself is the point, returns `graph_id`).

  **Retry behaviour is now unified (#392/#393, 2026-08-16).** `run_task_graph` used to branch on
  `execution_kind` — a `workflow` deferred (`retry_scheduled`, run ends, a sweeper must resume it)
  while a `goal` retried in-process — so the same source with `retries: 2` gave workflow **1
  attempt**, goal **3**. That branch is gone. Both kinds now defer if and only if **(a)** the run
  is durably tracked — a `workflow` or `goal`, never a bare `run_graph`, which no store knows
  about — and **(b)** a retry sweeper is registered on the runner owning that store
  (`nodus_lang_workflow.runner.register_retry_sweeper(runner)`, held by `RuntimeService` for its
  lifetime). Otherwise the retry is taken in-process and the run completes before returning.
  `run_workflow_code`'s `inline_retries` parameter is removed.

  Registration is **per-runner, not per-process** — and the default runner is rebuilt per working
  directory. If you write a test that registers a sweeper, chdir *first*: `retry_sweeper()`
  binds to the runner for the cwd at the moment you enter it, so
  `with retry_sweeper(), _project_root_context(td)` silently registers on the wrong store.
  That ordering bug cost a full suite run.

  **Do not reintroduce the decision anywhere but `_retry_is_swept()`.** The wrapper-level version
  of this guard (`inline_retries`, passed by one of five callers) is exactly how the bug survived
  ten weeks. `tests/test_retry_path_unification.py` asserts on the source of the retry branch as
  well as its behaviour, because a behaviour-only test passes on the goal side alone.

  The result-shape half of #393 was **wrong and was retracted on the issue**: `status`/`retry`
  appear on both kinds when a run defers and on neither when it completes. A goal result is a
  workflow result plus a `goal` key. Only the entry points and the event prefix are kind-specific.

  **#409 closed this out in v5.0.0.** Unification left `goal` as a workflow with different event
  names, so it needed a stopping condition to mean anything distinct — that is the
  `goal … over … { until … }` form (see the language-quirks section). A goal is now *a workflow
  plus a predicate and a budget*, which is a real distinction rather than a naming one.
- Run tests: `cd C:\dev\nodus-mcp-server && python -m pytest -q`

## nodus-jupyter

- Repo: `C:\dev\nodus-jupyter` / `github.com/Masterplanner25/nodus-jupyter`
- **Published on PyPI** (version: `check_publish_drift`).
- **Install:** `pip install nodus-jupyter && python -m nodus_jupyter install`
- **32 unit tests** — require `ipykernel` installed (`pip install ipykernel`).
- Provides a Jupyter kernel for `.nd` files; works in JupyterLab, Jupyter Notebook, VS Code notebooks.

## nodus-run-action

- Repo: `C:\dev\nodus-run-action` / `github.com/Masterplanner25/nodus-run-action`
- **A GitHub Action, not a PyPI package.** Published version is in `tools/consumers.json`.
- **Usage:** `uses: Masterplanner25/nodus-run-action@v1`
- **Three modes:** `file` (run a .nd script), `test-path` (run test suite), `fmt-check` (format gate)
- **Its README pins a `nodus-lang` version, and that pin is what new users copy**, so it goes
  stale at every release and hands them an old runtime. Invisible to the Stage 6 content-hash
  sweep because it is not on PyPI — `nodus_gate --consumers` is what catches it, and did, at
  5.1.0. Republishing means: update the pins, tag, **and move the floating `v1` tag**; verify
  with `git ls-remote origin 'refs/tags/v1^{}'`, since `rev-parse` on an annotated tag returns
  the tag object rather than the commit.
- No local test suite — tests run in CI via the action itself.

## nodus-sdk companion package

- Repo: `C:\dev\nodus-sdk` / `github.com/Masterplanner25/nodus-sdk`
- **Published on PyPI** (version: `check_publish_drift`).
  99 tests. Unified platform SDK auto-wiring the 35-package companion ecosystem.
  Its `test_version_string` asserted `0.1.0` from 2026-07-12 until 0.1.2, so the
  suite shipped one guaranteed failure for a month and the v5.0.0 Stage 6 sweep
  recorded it as a known-stale test rather than fixing it. Fixed in 0.1.2.
- **Install:** `pip install nodus-sdk[agent,sql,fastapi]` (extras-based)
- **Key exports:** `NodusSDKRuntime`, `create_runtime(**kwargs)`, `detect_available()`
- **9 bridges:** redis, http, llm, observability (wrappers), sql, vector, scheduler, webhook, api (new)
- **Bridge return type:** host functions return maps not Records — `.nd` must use `r["key"]` not `r.key`
- **FastAPI bridge:** `create_nodus_router(rt)` → POST /run, GET /health, GET /syscalls, memory CRUD
- **NodusTraceMiddleware:** reads X-Trace-ID header → `runtime.set_trace_id()`
- Run tests: `cd C:\dev\nodus-sdk && PYTHONPATH="C:/dev/Coding Language/src" python -m pytest -q`

## nodus-store-sql companion package

- Repo: `C:\dev\nodus-store-sql` / `github.com/Masterplanner25/nodus-store-sql`
- **Published on PyPI** (version: `check_publish_drift`).
  47 tests (31 sync + 16 async). Promoted from `packages/nodus-store-sql` incubator scaffold.
- **Async tests require `aiosqlite`** — not installed by default. Run `pip install aiosqlite` if async tests fail with `ModuleNotFoundError`.
- **Three stores:** `RunStore` (optimistic locking), `EventStore` (append-only), `JobStore` (atomic claiming)
- **Async:** `AsyncSqlStore` via `sqlalchemy.ext.asyncio`; test with `sqlite+aiosqlite:///:memory:`
- **Tables:** `nodus_runs`, `nodus_events`, `nodus_jobs`
- **No Alembic:** `create_all()` is the dev schema bootstrap; production manages migrations independently
- Run tests: `cd C:\dev\nodus-store-sql && python -m pytest -q`

## SemVer policy

The current published version is **v5.6.0** (live on PyPI, published 2026-08-28). Both files
must stay in sync:
- `src/nodus/support/version.py` — `__version__ = "5.6.0"`
- `pyproject.toml` — `version = "5.6.0"`

**5.6.0 is additive. Every new surface is something a workflow could not previously
say, and nothing that parsed before parses differently.** Four of them, all from the
workflow-DSL cluster: a step can map over a list (`step render each page in discover`,
#480); workflows and goals take parameters (#481); a step can declare its output type
(`with { returns: "map" }`, #479); and a goal's `budget` gains `limits`, so it can be
bounded by what it spends rather than only by iterations (#488).

Two consequences worth knowing even though neither breaks code. **`each` is a new
contextual keyword** — contextual, so it remains usable as an identifier, but an editor
older than this release renders it as a plain identifier until the VS Code extension is
republished. And **an unrecognised type name is now reported rather than silently meaning
`any`** (#609), staged as a warning until 6.0.0, so a project that was "clean" may show
new warnings on annotations that never meant what they said.

One security fix, and it is the reason this release should not have waited: **a capability
policy could be bypassed by writing the async form of a call** (#616, `severity:high`).
Anything embedding a `NodusRuntime` with a policy should upgrade.

`RuntimeService.close()` now waits for its sweeper instead of only asking it to stop
(#632), which matters to embedders whose store lives in a directory they later remove.

**5.5.0 has one behaviour a reader should know about, and it is a tightening: a workflow
step body can no longer be called directly (#394).** `build["steps"][1]["fn"](nil)` used to
run that step with its dependencies unmet; it now raises. The flow value's shape is
unchanged — `keys(build)` and `build["steps"]` still read — so nothing breaks but the
bypass, and the bypass was never a supported way to run a step. Two smaller tightenings in
the same spirit: editor diagnostics now report typos inside string interpolations, compound
assignments, field assignments, `match` scrutinees and `action` payloads, so a project that
was "clean" may show new warnings on code that was always wrong; and `nodus check` resolves
imports exactly as the runtime does, which means a pip-installed companion import stops
reading as `Import not found`. Everything else is additive: `nodus docs`,
`NODUS_RUN_STATE_ROOT`, `nodus_gate --shapes`, and `llms.txt` shipping inside the wheel.

**One internal removal.** `nodus.tooling.loader` no longer defines `resolve_import_path`,
`ensure_project_root`, `import_error`, `resolve_with_extensions` or
`try_resolve_with_extensions` — the first three are re-exported from
`nodus.runtime.module_loader` and still import from the old path; the last two are gone,
since nothing outside the runtime consumed them (#598).

**5.4.0 is additive except in one place a reader should know about: `nodus graph`
no longer runs the file (#400).** Both `nodus graph <file>` and `nodus graph show`
built their plan by executing the target, side effects included; they now plan from
the workflow/goal declarations alone. A file whose graph is constructed at runtime
(`task()` / `run_graph`, or a dynamically chosen flow) is **refused** with a message
naming `--execute`, which restores the old behaviour — so a script relying on the
executing path needs that flag. Nothing else in 5.4.0 removes a behaviour: the other
changes either add a way to say something (`allow_failure`, `try`/`finally` without
`catch`, blocking send on a bounded `channel(n)`), refuse a combination that could
only ever no-op (a checkpoint resume of a *waiting* run, a goal whose every
checkpoint is conditional, a reused `ModuleLoader` handed different source under one
module name), or make an existing failure legible. **`nodus workflow cleanup` gained
a 30-day default retention** where unset previously meant *forever* — the command
still only runs when invoked, but it now removes something when it does
(`NODUS_WORKFLOW_RETENTION_SECONDS=0` restores the old no-op).

**5.3.0 has one input that used to load and now does not (#490).** A `nodus.toml`
declaring a table or key Nodus does not read — `[project]`, `[runtime]`, a misspelled
`verison` — was accepted and the unknown parts discarded. It is refused now, naming what it
found and suggesting the close match. Strictly this makes previously-"working" input fail,
so it is the one thing in 5.3.0 a reader should not assume is additive; it was shipped as a
refusal rather than the warn-then-error staging used for `worker:` (#492) and concurrent
writes (#547) because a manifest is configuration read once at load, not behaviour observed
during a run, and a warning there is read by nobody. The fix is one word in most cases and
the error says which word. `register_syscall` gained the same treatment for an unknown or
missing `capability` (#478); nothing in or out of tree registers a custom syscall, so that
half breaks nothing today.

**A `run_source` behaviour change ships in 5.1.0 (#521).** `filename=` used to select the
program: if a file of that name existed, the loader read it and discarded the `source`
argument, reporting `ok=True`. It is a label now, as the guide always said. Anything relying
on the old behaviour to run a file should call `run_file`. Present since v0.4.0, so this
is a change against every prior release, not just 5.0.x.

**Treat 5.0.3 as superseded, not merely older.** It assigns a `memory_store` attribute that
`nodus_sdk.NodusSDKRuntime` defines as a read-only property, so every construction of that
subclass raises `AttributeError: ... has no setter`. It is the one release in the 5.0.x line
that breaks a first-party companion. Fixed in 5.0.4.

**Update this paragraph in the release PR, not afterwards.** It read 5.0.1 through the whole
of 5.0.2, and `ECOSYSTEM_READINESS_ASSESSMENT.md` sat at v4.1.1 for four releases -- and was
*still* stale at the 5.1.0 cut, reading v5.0.2 in one line and 4.1.1 in two others. No gate
checks any of this.

**The set of places that claim a current version is now `tools/version_claims.json`, and
`nodus_gate --versions` checks it.** Do not maintain a list here; the list that lived here
was wrong. It said `ECOSYSTEM_READINESS_ASSESSMENT.md` had *three* such lines, and the
gate's discovery sweep found a fourth on its first run. The README *banner* deliberately
names no version -- that is why it is the one that has never gone stale, and it is the
pattern the rest should follow where it can.

**This section went stale during the 5.0.2 release** — it still read 5.0.1 afterwards, because
the release PR bumped the two version files and the CHANGELOG but not this paragraph. That is the
third time a version string in prose has gone stale in three releases, and it is exactly what the
note below predicts. Update it in the release PR, alongside the version bump, not afterwards.

Patch releases (5.1.x) for bug fixes and stability graduations. A minor bump (5.2.0) requires a
substantive feature addition. Never bump without a corresponding PyPI publish. If you see these
files at different values, fix the mismatch before doing anything else.

**v5.0.0 is the first major.** It carries exactly one breaking change — embedded runtimes deny
subprocess/network/env by default (see the embedding section below). The bytecode format did not
change: `BYTECODE_VERSION` is still **4** and the 49-opcode set is untouched, so a major bump does
not imply recompilation.

**v5.0.1 is additive only** — new exports (`GATED_BUILTINS`, `active_vm()`), new tests, docs.
No behaviour change, no new syntax. Upgrading from 5.0.0 requires nothing. It exists because five
companions capped `nodus-lang<5.0.0` and made 5.0.0 unadoptable; see the ecosystem section.

**`README.md` is current, and the fix it got is the pattern to copy.** It advertised 4.2.0
through the whole 5.0.0 cycle; the repair was not "remember to update it" but to make the
banner name **no version at all** and to register the "Recent:" paragraph as a claim in
`tools/version_claims.json`, so `nodus_gate --versions` now fails on it rather than a reader
noticing. Re-checked 2026-08-25: 11/11 registered claims agree with 5.4.0. The 4.2.0 mentions
in `RELEASE_GATES.md` and `real-world-integration.md` are historical and correct as written,
and the `docs/evals/v4.2.0/` hits are that release's own records.

**A gate checks version strings now** — `nodus_gate --versions`, in `--all`. This paragraph
used to read *"No gate checks version strings"*, which is why `COMPATIBILITY.md` and
`docs/release.md` sat at 4.1.1 through an entire release before anyone noticed, and it stayed
true through three more cycles because the response each time was a longer list to check by
hand.

The distinction it encodes is still yours to make when you *write* prose: *"X is current"*
goes stale, *"as of X"* does not. The gate cannot tell them apart either — that is precisely
why the claims are declared in `tools/version_claims.json` rather than grepped. Register a new
claim there, or word it so it never needs registering.

## Embedding API — known blockers and operational traps

These were identified by a raw-path readiness probe and are filed as GitHub issues.
Full analysis: `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`.
All entries are also in `docs/governance/TECH_DEBT.md`.

**`run_source(source, filename=...)` runs `source`. It did not, before 5.1.0** (#521,
present since v0.4.0): if a file of that name existed, the loader read *the file* and
discarded the `source` argument, returning `ok=True` with the other program's output — so
which program ran depended on the process CWD. `filename` is a label; a real path only
decides where relative imports resolve from. Use `run_file` to run a file.

Two things that make this worth remembering rather than just fixed. It was **documented
backwards**: the guide has a section headed *"Passing a filename"* saying it labels errors,
illustrated with `filename="myscript.nd"` — the safe statement and the unsafe example. And
the bytecode cache is keyed on **path + mtime**, so it carried the same defect
independently; fixing the branch in `embedding.py` alone left it reachable through a warm
cache, and guarding the cache *read* alone still let a differing source poison the entry for
the next `run_file`. Three paths, one question.

**EMBED-001 (#97) — FIXED. `timeout_ms` now defaults to `None`.** The old 200ms-default
trap is gone; `NodusRuntime()` applies no wall-clock deadline. Verified 2026-08-07:
`NodusRuntime().timeout_ms is None`. Do not re-add `timeout_ms=None` as a "fix" — it is
already the default. (SCHED-001 also means cooperative sleep no longer consumes the
budget even when a deadline *is* set.)

**`max_frames` (#350, then #387) — FIXED at both layers.** `NodusRuntime` honours
`MAX_STACK_DEPTH` (10,000), and as of 5.0.3 so does a directly constructed `VM()` — #350 fixed
the wrapper and left the engine underneath uncapped, which is the wrapper/sibling shape again.
Runaway recursion now raises `Call stack overflow` instead of growing frames until the OS kills
the process; VM frames are heap-allocated, so Python's own recursion limit never fires.

```python
rt = NodusRuntime(max_steps=None, timeout_ms=None)                  # capped at 10,000
rt = NodusRuntime(max_steps=None, timeout_ms=None, max_frames=1000) # tighter
```

There is no "unlimited" setting — pass a large integer if you genuinely want one. **Only the
call-depth cap defaults on**; `max_steps` and `deadline` stay unbounded on a bare VM because
`EXECUTION_TIMEOUT_MS` is 200 ms and a step budget is host policy. v4.1.1 and earlier are
affected at the runtime layer; anything before 5.0.3 at the VM layer.

**Capability switches deny by default as of v5.0.0 (#405).** `allow_subprocess`,
`allow_network` and `allow_env` are all **`False`**. A bare `NodusRuntime()` cannot shell out,
open sockets, or read the process environment; grant explicitly:

```python
NodusRuntime(allow_subprocess=True, allow_network=True)
```

`allowed_paths` is unchanged — it already defaulted to a CWD jail (`[os.getcwd()]`).

Earlier revisions of this file said these "default to permissive". That was true through
v4.2.0 and is the opposite of current behaviour, so **any advice written against the old
default is now backwards** — including "a bare runtime can shell out", which several docs and
issue comments relied on.

**`nodus run` and the rest of the CLI are deliberately NOT affected.** This is a decision, not
an oversight: the CLI builds a `VM` directly and never constructs a `NodusRuntime`, and a test
pins **both** halves so the "inconsistency" is not tidied away by a later reader. The domain
deny-by-default protects is *work you did not fully author* — a developer running a script they
just wrote is not that.

Three related surfaces, all in `src/nodus/runtime/capability.py`:

- **`CapabilityPolicy`** — optional, consulted at the host boundary; three-valued
  `allow | ask | deny`. `ask` with no `approval_channel` configured denies.
- **The Floor** (`DEFAULT_FLOOR`) — unbypassable; a policy that allows everything **cannot**
  override it. Its one real rule: a Nodus program cannot *write* into `.nodus/` (the workflow
  store, graph state, bytecode cache). Reads are untouched.
- **Two chokepoints, not one** — `_invoke_host_function` (host functions) and
  `VM.call_builtin` (builtins). A guard added to only one of them covers nothing that matters;
  see the recurring bug shape section.

Migration: `docs/migration/v5.0-deny-by-default.md`. Design: `docs/design/v5/02-capability-policy.md`.

**Per-runtime state, and one breaking default (5.0.3+, #185/#390/#424).**

- **Memory is isolated per `NodusRuntime`.** Two runtimes in a process no longer share it — a
  guest script writes memory via `memory_put`, so a shared store was a channel between tenants.
  `share_process_state=True` restores the old sharing; `memory_store=` injects a specific store.
  **A bare `VM` and the CLI keep the process-global store** — single-tenant by construction.
- **Agents are deliberately NOT isolated.** A guest cannot register one: the only agent builtins
  are `agent_call` / `agent_available` / `agent_describe`, and registration is host-only from
  Python. A shared registry holds what the *host* put there, so isolating it by default would
  break `register_agent(...)` → `run_source(...)` — it broke 11 tests when tried — to prevent a
  leak guests cannot cause. `agent_registry=` scopes it for hosts that want per-tenant sets.
- **`agent_timeout_ms=`** bounds a host agent handler. The tightest of the step's `timeout_ms`
  (minus time already spent) and this default wins. It stops the **wait**, not the handler:
  arbitrary Python cannot be preempted, so the handler runs on a daemon thread and is abandoned
  at the deadline. Abandoned handlers are recorded — `abandoned_agent_calls()`,
  `abandoned_agent_call_count()`.
- **`workflow_runner=`** gives a runtime its own runner. Unset keeps the process-global one, so
  nothing that worked before changes.

**Do not store new runtime state under a public attribute name without checking downstream.**
`self.memory_store` collided with a read-only property of the same name on
`nodus_sdk.NodusSDKRuntime` and broke every construction of that subclass in 5.0.3. It is
`self._memory_store` now. A base class adding a public attribute can break any subclass that
made the same name a property.

**What is promised to embedders (5.0.1, #441–#444).** Added after aindy-runtime reported four
places where it was coupled to something we had never published as a surface:

- **`GATED_BUILTINS` / `GATED_BUILTIN_NAMES`** — the registration-time gates as data, flag →
  `GatedBuiltinGroup(flag, capability, description, arity, names)`. `register_all` builds its
  refusing stubs *from* this, so the published list and the enforced gate cannot disagree.
  **This is not `BUILTIN_CAPABILITIES`** — that one is what consults the policy at call time.
  The two differ by exactly one entry (`subprocess_shell_quote`, string manipulation that runs
  nothing) and `tests/test_downstream_contracts.py` pins the relationship, because before that
  they were two hand-maintained lists with nothing checking they agreed.
- **The denial contract is `kind` and the flag name, not the sentence.** `error["kind"]` is
  `"sandbox"`; `error["message"]` contains the granting flag. The wording changed in 5.0.0 and
  turned four downstream confinement tests red **while the guest was fully confined**. If you
  rephrase a denial, keep the flag name in it.
- **`NodusRuntime.active_vm()`** is supported; the `VM` it returns is not. `_get_active_vm()` is
  retained as an alias because downstream pins it — do not "clean it up".
- **Do not add `**kwargs` to `NodusRuntime.__init__`, and keep the confinement flags
  keyword-only.** Both are load-bearing: with a catch-all, a renamed flag is silently swallowed
  and the guest runs unconfined with every mock-based test on the embedder's side still green.
  Pinned by test so it cannot be undone casually.
- **`register_function` refusing to override a builtin is a security boundary**, not a
  convenience check. Because a builtin cannot be aliased, a host can install a fail-loud guard
  under a guest-reachable name (aindy does this for `syscall`) and know the guard is the only
  thing there. Also now pinned.

**SPAWN-001 (#116) and CHAN-001 (#107) — both FIXED.** `wait_async()` suspends properly,
and a `recv()` with no possible sender raises a deadlock error rather than orphaning the
coroutine. History and implementation notes are in `docs/governance/TECH_DEBT.md`.

The one part still worth having here, because it wastes an afternoon: **testing the
deadlock error requires driving the scheduler.** `spawn(c)` alone does not run the
coroutine — without a `run_loop()` the script exits 0 and the coroutine never starts,
which *looks exactly like* the original bug. Use `spawn(c)` then `run_loop()`.

## Published ecosystem — how to find out, not what it was

All packages are live. PyPI rate limits apply to **new project creation** (~a few
per hour), not to version uploads on existing projects — republishing new versions
of already-published packages is not session-limited.

**nodus-lang:** the current version lives in the *SemVer policy* section above and in
`src/nodus/support/version.py` — not here, where it was a release behind. `nodus-retry` is
an optional dep (`nodus-lang[retry]`); the runtime falls back to the built-in
`InMemoryEffectStore` when it is absent, which is why CI's `unittest` step catches things
`pytest` passes locally when you have it installed.

**Companion `nodus-lang` ranges — do not read them by eye. Run the check:**

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_downstream_constraints
```

All six dependents float and admit the current release; the script prints each range, so
**do not transcribe them here** — a table of ranges in prose is the thing that failed below.

That was true **as of 2026-08-17 and not before it.** An earlier revision of this section said
"none caps it, so all six dependents picked up the 5.0.0 major automatically." The exact
opposite was true: five of the six published `nodus-lang<5.0.0`, so
`pip install nodus-lang==5.0.0 nodus-mcp` was `ResolutionImpossible` and 5.0.0 was unadoptable
for anyone using the ecosystem. Only `nodus-jupyter` floated. It was found by the aindy-runtime
team, not by us — the Stage 6 sweep asked exactly this question and transcribed five of six
ranges with the upper bound dropped. Fixed by republishing all five (#445).

Two durable lessons, both of which cost a day:

- **`>=4.0.0,<5.0.0` reads as "admits 4.x", which is what the eye checks for.** The clause that
  forbids the new version is at the far end of the string. This is not a lapse more care fixes;
  resolve it with `packaging`, which is what the script does. It reads **published** PyPI
  metadata, because a floated cap sitting unreleased in a companion's `main` helps nobody.
- **A passing companion suite says nothing about installability.** The sweep correctly recorded
  every dependent suite passing against 5.0.0 — they were run against the dev source. They could
  not have been reached through a normal `pip install` at all, and noticing that would have
  exposed the cap immediately.

**Policy, decided 2026-08-17: companions do not cap `nodus-lang`.** A hard upper bound on a
first-party dependency turns every major into a two-repo release train with consumers frozen in
between. The companion's own suite is the check that catches a real break; a cap earns its place
once a break is known, not before.

**Standalone companion packages — 35 as of 2026-08-26**, plus `nodus-lang`, so **36
PyPI projects** in total. Names and tiers: `docs/ecosystem/PACKAGE_QUICK_REF.md`.

That count was **32/33** for several cycles and was wrong before `nodus-flow` was
published — a hand-maintained number nothing checks, exactly like the version strings
below. **Do not adjust it by arithmetic; re-derive it.** Every first-party name is
listed in `docs/ecosystem/README.md`; probe each against
`https://pypi.org/pypi/<name>/json` and count what resolves. Two first-party names
deliberately do **not**: `nodus-vscode` (Marketplace) and `nodus-run-action`
(GitHub Action). `nodus-a2a-wire` was a third until 2026-08-26 (#477).

Send `Cache-Control: no-cache` when you do. PyPI's JSON API served a stale `info.version`
immediately after the `nodus-flow` publish — it reported the previous release as latest
when the new one had landed, which reads exactly like a failed upload.

**Version numbers are deliberately not listed here any more.** They were, and they went
stale every cycle. Two scripts read them live and neither can be transcribed wrong:

```powershell
# published version of each companion, and whether its source has drifted from it
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_publish_drift
```

`check_publish_drift` prints each companion's **published version** as a side effect of
answering the question Stage 6 actually asks — has the checkout drifted from what users
can install. It compares file contents from the published sdist. Do not substitute a git
heuristic: counting commits since the version bump gave **four false positives** at
v4.2.0, because a commit can touch only docs, only CI, or only tests. It exits **2** on a
skip, because a companion that could not be checked is not one that passed.

Note: the published `nodus-memory` and `nodus-a2a` are the **Tier 2 rewrites** — the same
thing as the local `C:\dev` checkouts, not the nodus-lang adapters. Verified against PyPI
2026-08-07:

- `nodus-a2a` 0.1.0 — *"Agent-to-Agent coordination: registry, delegation, dead letter,
  and watchdog"*, no nodus-lang dep
- `nodus-memory` 0.1.0 — *"Persistent agent memory: nodes, MAS path addressing, scoring,
  embedding, and recall"*, optional pgvector/openai extras only

Earlier wording here said they were "published from the GitHub repos, which hold the
nodus-lang adapter versions — do not publish from the local checkouts." That was backwards
on both counts: the adapters are **not on PyPI at all**, and the local checkouts are
exactly what is published. `pip install nodus-a2a` does not give you `A2AHttpServer`;
the wire adapter is `nodus-a2a-wire` on PyPI since 2026-08-26, module
`nodus_a2a_wire` (worktree `C:\codev\a2a-wire-pub` — **not** the confusingly-named
`C:\codev\nodus-a2a-wire`; see the nodus-a2a section). The nodus-memory adapter exists only in history —
`git show f02ab1e:src/nodus_memory/nodus_bindings.py`.

**Other published artifacts — neither is on PyPI, so both are invisible to the sweep
above.** They are tracked by `tools/consumers.json` and reported by
`nodus_gate --consumers`; that manifest is the authority for what each has published,
not this file, which had nodus-vscode a version behind for a whole cycle:

- nodus-vscode — VS Code Marketplace (publisher `MasterplanInfiniteWeave`)
- nodus-run-action — GitHub Action (`Masterplanner25/nodus-run-action@v1`)

**PyPI token note:** Each package in a separate repo (nodus-mcp, nodus-extension,
nodus-memory, nodus-native-memory-engine, nodus-mcp-server) needs its own project-specific PyPI token.
nodus-lang packages use the main nodus-lang token. Retrieve from user at upload time —
never store tokens in any file.

**Future publish sequence:** For any new package, the pattern is:
1. `python -m build` (in the package dir)
2. `twine upload --username __token__ --password <token> dist/*`
3. Add status badge to README, commit, push
