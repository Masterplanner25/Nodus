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

**The gap is live and ten minors wide: `.venv` is at 5.0.0, `src/` is at 5.10.0**
(re-checked 2026-09-05 with `.venv/Scripts/nodus.exe --version`, at the 5.10.0 cut).
Forgetting the prefix gets you a runtime from before the `@exactly_once` forgery fix, the
call-depth cap, the doubled-`main()` fix on cached runs, `run_source` no longer running the
file its `filename` happens to name (#521), `nodus graph` no longer executing the file it
inspects (#400), the whole resume-durability cluster, the entire workflow-DSL cluster
(#479, #480, #481, #488), everything in 5.7.x and 5.8.0 — `extern`, `compensates`,
cancellation and `retry.until` among them — and all of 5.9.0: cross-module closures in
both directions (#691, #696), the content-keyed bytecode cache (#704) and binary file I/O
(#170). The symptom is behaviour that contradicts the code you are reading.

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
| Invariant coverage ledger | `tools/invariant_coverage.json` — one entry per invariant in `EXECUTION_INVARIANTS.md`, naming the tests that cover it or stating why none is recorded. Checked by `nodus_gate --invariants`. `unrecorded` is not `uncovered`; never guess a mapping |
| Shape manifest | `tools/shape_manifest.json` — every instance of the recurring bug shape currently in the tree, each `intentional` or `tracked`. The baseline `nodus_gate --shapes` measures new ones against. Adding an entry needs a stated reason |
| Recorded dependent flakes | `tools/dependent_flakes.json` — diagnosed flakes, used to *classify* a red run, never to pass one. Every entry needs a stated reason |
| Downstream range check | `tools/check_downstream_constraints.py` — Stage 6; resolves *published* metadata. `UNPUBLISHED_COMPANIONS` registers a companion's `nodus-lang` floor **before** it is published, each with a stated reason, and reports a floor naming a version that does not exist yet — a package nobody can install. Register on the day the package is written, not the day it ships; move it into `COMPANIONS` in the publishing commit |
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
| v5 design docs | `docs/design/v5/` — `00-domain-statement.md` (what Nodus is for), `01-goal-stopping-condition.md` (#409), `02-capability-policy.md` (#405), `03-outcome-ambiguity.md`, `04-cancellation.md` (#395, proposal) |
| Deny-by-default migration | `docs/migration/v5.0-deny-by-default.md` — the one breaking change in 5.0.0 |
| Goal validation | `src/nodus/frontend/goal_validation.py` — compile-time `reached("label")` checking |
| Maturity checklist + re-score | `docs/governance/MATURITY_CHECKLIST.md` — 72.5 → 82-83 (2026-05-31) |
| Issue response policy | `docs/governance/ISSUE_RESPONSE_POLICY.md` |
| AI discoverability (canonical map) | `llms.txt` |
| AI discoverability (rich summaries) | `llms-full.txt` |
| GitHub wiki (local) | `C:\dev\Nodus Wiki\nodus-wiki\` — git repo, branch `master`, remote `Masterplanner25/Nodus.wiki.git` |
| **Companion repos (all 14)** | `docs/ecosystem/COMPANION_REPOS.md` — checkout paths, test commands, publish paths, per-repo gotchas. Indexed under **Companion repositories** below |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=70 --ignore=tests/test_scheduler_fairness.py -q
```

**3,633 tests collected** (`--collect-only`, 2026-09-05, at the 5.10.0 cut). Coverage
baseline: **76.82%** overall (20,184 stmts) — that figure was measured 2026-08-07 at 1,878
tests and has **not** been re-measured since, so treat it as a floor, not a current reading. Gate: 70% (raised from 60% on
2026-05-31). See `docs/governance/TECH_DEBT.md` for the per-module breakdown.

**Two tests were known-flaky here; both are fixed. The reproduction method is the
part worth keeping.** Neither ever failed from repetition — only under *load* — so
"it passed when I ran it again" was never evidence about either, and an idle box
passes indefinitely.

- **`test_scheduler_fairness.py` (#631) — fixed 2026-08-28.** Never a fairness
  failure: the run was killed by the 200 ms wall-clock `EXECUTION_TIMEOUT_MS`
  before the ordering assertion was reached, so the test asserted the box could
  run 8000 iterations in 200 ms. The harness sets its own generous deadline now,
  in one helper so a test added later cannot forget it; `EXECUTION_TIMEOUT_MS`
  is untouched. **Both** tests in the file were affected, not the one an earlier
  note named.
- **`test_server.py::SQLiteWorkflowServerTests::test_workflow_run_uses_sqlite_store_when_configured`
  (#632) — fixed in 5.6.0.** Read as a tempdir race and was not one: the store
  was still open when the directory was removed, and `SQLiteWorkflowStore` had
  no `close()`. `RuntimeService.close()` waits for its sweeper now.

**To reproduce this class of failure, load the machine; do not re-run the test.**
Burn every core but one in a background process, then run the file.

**And keep the control inside the same load window.** Comparing "before" and
"after" is worthless if the load generator expires partway: a first attempt at
#631 showed the unfixed tests passing 5 of 6 with run times falling from 1.75 s
to 0.49 s — the box had gone idle, so the comparison measured nothing. Re-run
inside one window, both variants, and check the durations stayed up. Matched that
way, #631 was 3 of 5 runs red before and 5 of 5 green after.

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
re-run. The same applies to the doc gate (`nodus_gate --runtime` executes 270 blocks and writes to
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

**And the test does not have to sleep to be racing something.** A test that shells
out to `nodus run` is racing the runtime's own 200ms default budget, which nothing
in the test mentions — `test_cross_module_closure.py` failed on CI that way with
`Execution timed out` and nothing else wrong (#711). Ask what deadline the code
under test carries by default, not only what the test itself waits for. Details in
the SCHED-001 entry under language quirks.

Two classes can't share incompatible timeout requirements. If a test needs `session_timeout_ms=50`
(to observe expiry quickly) and another needs `session_timeout_ms=2000` (to survive load without
expiring), split them into two classes with separate server instances — one per `setUpClass`.

**The runtime clock cannot order two events — it ticks at ~15.6 ms.** `runtime_time_ms()`
is `(time.monotonic() - _START) * 1000.0` (`runtime/runtime_stats.py`), and on this box
`time.monotonic()` advances in ~15.6 ms steps — measured deltas between consecutive
distinct readings: `[16.0, 16.0, 15.0, 16.0, 15.0, 16.0]`. So **any two things that happen
without I/O between them get the same timestamp.** A task's `started_at` and `finished_at`
are routinely equal, and a strict causal chain `a→b→c→d→e` stamped `265, 265, 281, 297, 297`
— two ties in a sequence with no ambiguity at all.

Consequences, in order of how much they cost:

- **Never derive an ordering from a timestamp.** Sorting completed tasks by `finished_at`
  puts them in an arbitrary order, not a wrong-but-close one. This is what #577's
  compensation spec had to solve (`docs/design/workflow-dsl/01-compensation.md`): the
  order exists — tasks settle one at a time on one scheduler — it is simply never
  recorded, so the fix is a counter incremented where completion is already serialized,
  not a finer clock.
- **A duration measured across a fast operation is `0.0` and means nothing.** Do not
  assert on one, and do not read it as "instant".
- **This is platform-specific, which makes it worse.** `time.monotonic()` is
  nanosecond-resolution on Linux, so a timestamp-ordering rule is *mostly* right on a CI
  runner and wrong here — correct on the test platform, broken on the developer's. CI
  cannot catch it; only a causal chain of trivial steps run locally can.

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
AST node list so a **new node type** with no formatter case fails the suite.

**That guard is node-level, and 5.6.0 shipped two defects underneath it** (#656, #657). `each`
and `budget { limits: ... }` are new **fields on existing nodes**, so every node still had a
formatter case and the suite stayed green while `fmt` **silently dropped them** — `step render
each page in discover` came back as a plain step, and a goal's budget lost its bounds. Not a
refusal and not a parse error: valid output, different program, in a published release.

The lesson generalises past the formatter. **A completeness guard at node granularity does not
cover field granularity**, and the fix that works is a **round-trip property**:
`tests/test_formatter_round_trip.py` formats, reparses, and compares the AST field by field. It
found #657 on its first run. When you add a field to an AST node, that test is what protects it
— the node walker cannot.

To format .nd files correctly (matches CI exactly):
```powershell
# Format one file
python nodus.py fmt src/nodus/stdlib/hash.nd

# Format all stdlib .nd files
python nodus.py fmt src/nodus/stdlib/*.nd

# Verify -- this IS the CI step, not a reconstruction of it:
python -m tools.check_nd_format
```

`tools/check_nd_format.py` answers both halves -- which files, and whether each is
formatted -- and CI, the hook and you all call it, so there is nothing to keep in
step. It delegates the second half to `nodus fmt --check`'s own `_format_file`, so
the gate cannot disagree with the command it is gating. One process rather than one
per file: about 4s for the 61 tracked files, against 5m41s for the `xargs` form it
replaced.

A pre-commit hook enforces it on staged files. **It is tracked now** (#741) -- it
used to exist only as an untracked `.git/hooks/pre-commit`, so a correction helped
one checkout and the next clone installed whatever it had. Install after a fresh
clone:

```powershell
cp tools/hooks/pre-commit .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit
```

The old hook restated CI's file list in its own words and got it wrong -- it omitted
all four of CI's exclusions while its header claimed to run "the same command as
CI", so it blocked commits on `tests/fixtures/fmt/`, where an `_input.nd` is
unformatted on purpose.

## Lint gate (ruff **and mypy**)

**Both run in CI and both block merges. Ruff passing is not evidence mypy will.**

```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m mypy src/nodus/ --ignore-missing-imports --no-error-summary
```

That is CI's invocation verbatim. It is clean today; ignore the `annotation-unchecked`
notes, which are informational and not failures.

**Verbatim is not equivalent: locally it does not check `src/nodus_lang_workflow/` at
all.** `nodus_lang_workflow` resolves to the **installed** nodus-lang in `.venv`
(`site-packages/nodus_lang_workflow/`), so mypy follows imports into that copy and never
reads the working tree's. CI has no install shadowing `src/`, so it does. This is the
`.venv`-shadows-`src` gap the top of this file warns about, in a place it is not
obvious — and it costs a red CI on a change that type-checked clean locally.

Established by falsification, not inference: a deliberate `_deliberate: int = "nope"`
inserted into `src/nodus_lang_workflow/runner.py` produced **no local output** and CI
failed on the real error in the same file. **Passing the directory explicitly does not
fix it** — `mypy src/nodus/ src/nodus_lang_workflow/` is also silent, because the
installed package still wins module resolution.

So for anything under `src/nodus_lang_workflow/`, **CI is the only type check**. Push and
let it arbitrate rather than trusting a clean local run.

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

- `--static`: verifies documented symbols exist in the codebase (**140 symbols**
  across 40 documents, as of 2026-08-30)
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs (**270 blocks**); expects 0 failures with the `.nodusgate-allow`
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

## Companion repositories

Per-repo detail — layout, test commands, publish paths, and the gotchas that have
cost time — lives in **`docs/ecosystem/COMPANION_REPOS.md`**. It was eleven
sections scattered across this file; consolidating it made both files navigable.
What exists and in what tier: `docs/ecosystem/README.md`.

| Repo | Path | Channel |
|---|---|---|
| nodus-mcp | `C:\dev\nodus-mcp` | PyPI |
| nodus-a2a | `C:\dev\nodus-a2a` | PyPI |
| nodus-a2a-wire | `C:\codev\a2a-wire-pub` | PyPI |
| nodus-memory | `C:\dev\nodus-memory` | PyPI |
| nodus-native-memory-engine | `C:\dev\nodus-native-memory-engine` | PyPI |
| nodus-extension | `C:\dev\nodus-extension` | PyPI |
| nodus-sdk | `C:\dev\nodus-sdk` | PyPI |
| nodus-store-sql | `C:\dev\nodus-store-sql` (`master`) | PyPI |
| nodus-workflow-ai | `C:\dev\nodus-workflow-ai` | PyPI (#93, floor `>=5.8.0`) |
| nodus-jupyter | `C:\dev\nodus-jupyter` (`master`) | PyPI |
| nodus-mcp-server | `C:\dev\nodus-mcp-server` | PyPI |
| nodus-flow | `C:\dev\nodus-workflow` (dir not renamed) | PyPI — **was `nodus-workflow` until 0.2.0** (#483) |
| nodus-vscode | `C:\dev\nodus-vscode` | VS Code Marketplace |
| nodus-run-action | `C:\dev\nodus-run-action` | GitHub Action |

**Do not write a published version number into this file.** They went stale every
cycle. `tools/check_publish_drift.py` prints each companion's published version as
a side effect of answering the question Stage 6 actually asks; `tools/consumers.json`
is the authority for the two non-PyPI consumers.

Four traps worth knowing before you open the detail file:

- **`C:\codev\nodus-a2a-wire` is NOT the wire repo** — it is a worktree of the
  *coordinator* repo's old history, so pulls and pushes go to the wrong project.
  Use `C:\codev\a2a-wire-pub`.
- **Renaming a distribution does not fix a module collision.** `nodus-a2a-wire`
  and `nodus-a2a` both shipped `nodus_a2a`; installing one over the other deleted
  the other's classes with pip reporting success both times (NAME-COL-001).
- **Bridge and host functions return maps, not Records** — `.nd` must use
  `r["key"]`, never `r.key`.
- **VS Code spawns the *installed* `nodus.exe`**, so LSP server changes need a new
  nodus-lang release before the extension sees them.

## Nodus language quirks (relevant when writing test .nd code)

These burn time when forgotten:

- **No `await` keyword.** `test.flush_async()` is synchronous — no `await`.
- **`+=`, `-=`, `*=`, `/=` work** (added in 4.0.1 pre-release, PR #183), including inside
  closures.
- **Closures CAN mutate an outer `let`. A module-top-level one silently did nothing
  from inside a function through 5.7.1; fixed in 5.8.0 (#671).**

  This entry said the opposite for a long time ("in closures you still can't assign outer
  `let` variables at all — use a map with quoted keys"), and that advice sent every session
  to an unnecessary workaround. Re-verified by running each case:

  ```
  fn make_counter() { let n = 0i; return fn() { n = n + 1i; return n } }   // 1, then 2
  ```

  Also working: two closures sharing one captured variable, two-level nesting, mutation
  from inside a spawned coroutine, and `n += 5i`.

  What was broken through 5.7.1 is **module scope**, and it was silent — `let g = 7i`
  then `fn setit() { g = 99i }` left `g` at 7 with no error, because the function got a
  frame slot for `g` and wrote there. If the right-hand side also *read* the variable you
  got `Cannot add nil and int`: a type error naming arithmetic, not scoping, because the
  fresh local was uninitialised. Reads of a top-level `let` were always fine, and so was
  mutating one *at* top level. Mechanism and the lesson it left are in the
  recurring-bug-shape table.

  **On 5.7.1 and earlier only**, use a quoted-key map mutated via bracket notation:
  `state["count"] = state["count"] + 1i` (`{"count": 0i}` — quoted-key map — NOT
  `{count: 0i}`, which is a record). It was never needed for anything scoped inside a
  function.
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
- **Cross-module closures were broken in both directions through 5.8.0; fixed in
  5.9.0** (#691 `severity:high`, #696). A callback passed *into* an imported
  module's function did not work from a **step body** — including `std:` modules,
  so `retry.until` failed in the exact position its own documentation points at.
  A closure a module *returns* did not work anywhere, so a factory
  (`let f = m.make_adder(3i)`) was unusable. On 5.8.0 and earlier: call the module
  function from `fn main()` and pass the result in, and do not use module
  factories.

  **The worst case was silent** — the step body stopped at the module call, nothing
  was raised, and the run reported `failed: []` with `steps: {}`. Mechanism and the
  three lessons it left are in the recurring-bug-shape section; the one that
  matters when you are writing `.nd` tests is this: every test and probe for
  `retry.until` ran inside `fn main()`, so the full suite, nine gate phases and 83
  release probes were green on a feature that did not work where it is meant to be
  used. **A construct documented for use inside a step body must be tested inside
  a step body.**

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
- **`spawn()` accepts a zero-argument function directly (#718, unreleased —
  in `CHANGELOG.md`'s `[Unreleased]`)** — `spawn(fn() { ... })` wraps and spawns, and
  returns the handle. `spawn(c)` after `let c = coroutine(fn() {...})` is unchanged
  and still correct.

  **Through 5.9.0 the two-step form is the only spelling**: `spawn(fn(){...})`
  raises `spawn(coroutine) expects a coroutine`. That footgun is why #336 proposed a
  `spawn { }` keyword; the keyword was rejected (the grammar position it needs is the
  one `match` occupies, see #717) and the builtin was widened instead. Widening
  delegates to `coroutine()`'s own path, so the zero-arity check and the
  ASYNC-MOD-003/#691 origin pinning are not duplicated.
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
- **`nodus run` bounds the WHOLE program at 200ms of wall clock**
  (`EXECUTION_TIMEOUT_MS`), not just a coroutine. Cooperative sleep counts, so a
  coroutine sleeping 4 × 100ms is killed having consumed no CPU — but so is any
  script that simply does 200ms of work. Fix: `nodus run --time-limit N`, in
  **seconds**. SCHED-001, deferred to 4.0.1.

  **The reason nobody reads this off the CLI is a `None` that round-trips back to
  the default.** `cli.py`'s `run` branch passes `timeout_ms=None if time_limit is
  None else ...`, which looks like "unbounded unless asked"; two frames later
  `cli.run_file` does `timeout_ms=EXECUTION_TIMEOUT_MS if timeout_ms is None else
  timeout_ms` and puts the 200ms back. Reading either site alone tells you the
  opposite of what happens.

  **An `import` is charged to that budget**, because the import compiles the
  imported module *during* the run. So a two-file script can time out having
  executed almost nothing of its own. This is what took
  `test_cross_module_closure.py` down on CI (fixed in #711): measured, the case
  spent ~78ms of the 200ms warm and failed outright below 40ms — a 2.5x margin
  where the rule here is 5-10x, and CI is colder still, since a fresh process pays
  the compiler's own lazy imports inside the window.

  **A CLI subprocess test that imports a module needs `--time-limit`.** Put it on
  the harness, not the one test that happened to go red — every case in the file
  shares the exposure. And check the embedded half of any both-ways harness:
  `NodusRuntime(timeout_ms=None)` is genuinely unbounded, so the two halves were
  bounded differently while claiming to run the same program.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.

## The recurring bug shape — a check on one path, a sibling path that bypasses it

This codebase's most common defect is not a wrong check. It is a **correct check that only one
of several paths goes through**. It has surfaced **once per row of the table below** across the
v5.0.0–5.9.0 cycles — count the rows rather than trusting a word here, which had gone stale by
one. That frequency is why it gets its own section: when you find one, the next question is
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

**There is a gate for this now — `nodus_gate --shapes`.** It will not find the shape for you in the sense of telling you what is broken; it finds *places where one question is answered in more than one voice*, which is where every instance above came from. Its first run produced #597 and #598. `tools/shape_manifest.json` holds the ones it already knows about — **39 known, 19 of them tracked as debt** at the 5.7.1 cut — so what it reports is the ones that are new. Do not transcribe that count by hand; the gate prints it every run and an earlier revision of this line was stale by four. When you add a second implementation of anything, expect to justify it there.

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

## Documentation governance

The governing docset layer was established in a 2026-05-29 sweep. Key rules:

- **`docs/governance/DOCSET_INDEX.md`** — the reader entry point and precedence list.
  When docs conflict, DOCSET_INDEX.md defines which wins.
- **`docs/governance/DOCSET_ALIGNMENT_AUDIT.md`** — 14 findings from that sweep.
- **`docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`** — **closed.** All
  seven conflicts were verified resolved on 2026-08-07. Its status flags had said
  "ACTION REQUIRED" for months after the fixes landed, because the tracker was
  maintained by hand separately from the work. Do not use it as a to-do list.

**The 2026-05-29 "needs review before repo commit and push" marker is resolved.**
It was on **23** documents, not the 19 this file used to say — a count worth
re-deriving rather than trusting, like every other count here.

Resolved per file rather than uniformly, because `git log` showed two very
different populations and one blanket answer would have been a lie either way:

- **12 were maintained since** — `RELEASE_GATES.md` had *seventeen* later commits
  and is what the release process reads; `SECURITY_POSTURE.md` had ten and carries
  a section written for #192. Asking for "review before commit" on a file
  committed and then edited seventeen more times is false, so the marker is gone.
- **4 are dated records** of the sweep itself (the audits, `DOCSET_CHANGELOG.md`).
  They say what was true that day and are not meant to move. Their marker now says
  so — do not "update" them to match the tree.
- **7 were genuinely untouched** and made live claims. **All seven were reviewed
  against 5.9.0 on 2026-09-01 (#713) and their markers are gone.** What that
  review found is below.

`DOCSET_GOVERNANCE.md` prescribed the original wording, so the convention was the
generator. It now specifies a marker that stays true after the commit — otherwise
the next non-coding session recreates the same contradiction.

### What reviewing the seven found (#713)

**A governing document can be wrong in the direction that costs a user a
guarantee, and nothing will notice.** `STABILITY.md` — listed in
`DOCSET_INDEX.md` as governing — classified `workflow`/`goal`/`step` and
`spawn`/`coroutine`/`channel` as **Experimental** for nine releases after both
graduated to Mostly Stable at v4.0.5. It also had `export` as Stable where the
index has it Mostly Stable, which errs the other way, and named 47 opcodes where
there are 49. Two of the seven were wrong in ways a reader would act on:
`ECOSYSTEM_BOUNDARY.md` made *"is distributed through the Nodus registry"* a
criterion of ecosystem membership, and **no member satisfies it** — everything
ships on PyPI, and the registry it promised to define "before the v4.0 launch"
never was.

**#710 is itself an instance of the recurring shape, in documentation form.** It
froze `DOCSET_CHANGELOG.md` and `DOCSET_STATUS_AUDIT.md` with *"Do not update it
to match the tree"* and left the three procedures in `DOCSET_GOVERNANCE.md` — and
a table row in `CHANGE_IMPACT_MATRIX.md` — instructing you to write to them. One
question, two places, one updated. The requirement had already lapsed before it
became contradictory: `DOCSET_CHANGELOG.md` holds exactly one entry across nine
releases. Doc changes are recorded in the commit and in `DOCSET_INDEX.md`; there
is no docset log.

**Four of the seven held a second copy of a list that lives elsewhere** — the
stability classification, the release sequence, the Tier 1 membership, the
precedence order — and every one had drifted. They point now rather than
restating. `RELEASE_CHECKLIST.md` is the one to remember: it prescribed *"tag →
publish release notes"*, i.e. the GitHub release **before** PyPI, which is the
one sequencing mistake release immutability makes unrecoverable.

**The `Version:` header was the generator, and is now `Last reviewed:`.**
`DOCSET_GOVERNANCE.md` prescribed `**Version:** X.Y.Z (the release this doc was
created for)` — a claim about the present that goes stale at every cut, and one
that cannot tell a reader whether the document was *checked* at that version or
merely *written* then. Same rule as `version_claims.json` — *"X is current" goes
stale, "as of X" does not.* **Every governance document carries `Last reviewed:`
now**; a further seven were stamped `Version: 3.0.2` and were reviewed on the same
day (#715).

### What reviewing the other seven found (#715)

**#710's "maintained since" split was too generous.** It classified by commit
count, and four of these seven have exactly one substantive edit since creation —
each a one-line touch from an unrelated PR. Only `SECURITY_POSTURE.md` (12
commits) and `DOCSET_INDEX.md` (6) were maintained in any real sense. A commit
count measures whether a file was *touched*, not whether anything in it was
*checked*.

**A security document contradicted itself about a live boundary.**
`SECURITY_POSTURE.md` §4 has said deny-by-default since #405; §11's comparison
table still said embedded subprocess/network/env were *"Available"*. And §12 told
embedders to run one OS process per tenant because `std:memory` is shared —
isolated per runtime since 5.0.3, with #155 closed. Both were falsified by
constructing a `NodusRuntime` and reading the values, which is the only way this
class of error surfaces.

**`COMPATIBILITY_MODEL.md` is #1 in its own reading order and recorded a reversed
policy as current** — F0-07, "cap companions at `<5.0.0`". That cap is what made
5.0.0 `ResolutionImpossible` with the ecosystem installed (#445), and it was
reversed 2026-08-17. Second time a *governing* document has been found propagating
superseded policy under its own precedence rule, after `NODUS_POSITIONING.md`.
**Check `Last reviewed:` before letting a document win a conflict.**

**A coverage claim that names a file has to be checked against the filesystem, and
prose cannot be.** `INVARIANT_TEST_MAPPING.md` cited 13 test files; **six do not
exist**, four of them under a ✅ meaning "a test exists that would fail on
violation" — one being the `allowed_paths` boundary. It also mapped 25 of 29
invariants and had never noticed the other four. That is #179's exact failure mode
still live in one of the two prose copies #179 names. Superseded by
`tools/invariant_coverage.json`; do not restore a prose table.

**`TEST_GAP_BACKLOG.md` was 8-of-11 stale, including its Critical and its High** —
two closed by tests written for unrelated purposes. Nothing links a gap to the test
that closes it, so closing one is silent. If a gap matters, file an issue.

**And the one that held up says why the others did not.**
`ECOSYSTEM_MATURITY_RUBRIC.md` needed a single correction because it **defines a
vocabulary and claims almost nothing about the tree**. Everything that rotted held
a *list* or a *classification* something else also holds. When writing a governing
document: **prefer defining a distinction to enumerating its instances**, and put
the enumeration where a gate can read it.

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

## SemVer policy

The current published version is **v5.10.0** (live on PyPI, published 2026-09-05).
Two files must stay in sync — `src/nodus/support/version.py` and `pyproject.toml`.
If they disagree, fix that before anything else.

Patch releases for bug fixes and stability graduations; a minor bump requires a
substantive feature addition. **Never bump without a corresponding PyPI publish.**

**What each release added is in `CHANGELOG.md`, not here.** A narrative per release
lived in this section and duplicated the changelog it was copied from. What follows
is only what the changelog cannot tell you at a glance.

### What is *not* additive, 5.3.0 onward

Everything else in those releases adds a way to *say* something. These are the
changes that can break a reader's working setup, so the table answers one question
fast: **is this symptom a release, or is it my change?**

| Release | What stopped working | Restore / fix |
|---|---|---|
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

Three of those ask something of you rather than just explaining a symptom.

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
- **#521 changed `run_source` against every prior release**, not just 5.0.x. Full
  account in the embedding section below.

**5.9.0 has no row, and that was checked rather than assumed.** Its four changes
are all repairs or additions: two closure fixes (#691, #696) where the old
behaviour was a silent truncation nothing could depend on, a bytecode-cache key
that now includes content (#704) — stale entries simply recompile once — and two
new builtins (#170). Guest code may still shadow a builtin name with its own `fn`,
verified by running it, so the new names cannot collide with an existing program.
An absence recorded as checked is worth more than an absence.

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
