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

**The `.venv` install was 4.0.8 — five releases behind — until 2026-08-17**, when the Stage 6
sweep upgraded it to 5.0.0. So it currently matches `src/`, and the usual symptom of forgetting
`PYTHONPATH` (behaviour from an old release) will not appear until the next version bump. Do not
read "the versions match today" as "the prefix is optional": the moment `src/` moves ahead, the
gap is silent again. **Re-check with `.venv/Scripts/nodus.exe --version` rather than trusting
this paragraph.**

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
    'milestone': None   # check current milestone on GitHub
}
```

Write the script to a temp file and run it — inline heredocs with
triple-quoted strings cause PowerShell/Bash quoting issues.

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
2. Bump both version files
3. Move `[Unreleased]` in `CHANGELOG.md` to the new version section
4. **Re-run the closed-issues gate as `--closed-issues --section X.Y.Z`.** After the
   cut it scans an empty `[Unreleased]` and reports a pass that checked nothing
5. Commit, PR, CI, merge
6. `git tag vX.Y.Z` → `git push origin vX.Y.Z`
7. Build the wheel **from the tagged tree**
8. **Gate 10** — adversarial validation against that wheel in a clean venv →
   write `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md`
9. Upload to PyPI
10. **Stage 5** — install the *published* package in a fresh venv and check it works
    as a new user would expect → write `docs/evals/vX.Y.Z/POSTPUBLISH_EVAL.md`
11. `gh release create vX.Y.Z --verify-tag` — **only after PyPI succeeds**, since
    release immutability is permanent (see the gotcha above)
12. **Stage 6 — downstream republish sweep.** Check every companion's `nodus-lang`
    range still admits the new version; `git status` each checkout for work left
    behind; and detect drift by **hashing the published sdist/wheel against local
    source**, never by git heuristics — "commits since the version bump" gave four
    false positives during the v4.2.0 sweep. `nodus-vscode` (manual VSIX) and
    `nodus-run-action` (pins a version) are not on PyPI and need checking by hand
    → write `docs/evals/vX.Y.Z/STAGE6_DOWNSTREAM_SWEEP.md`

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
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| Companion library contract | `docs/governance/COMPANION_LIBRARY_CONTRACT.md` |
| Pre-publish eval prompt | `docs/governance/EVAL_PREPUBLISH.md` — Gate 10 creator validation |
| Post-publish eval prompt | `docs/governance/EVAL_POSTPUBLISH.md` — Stage 5 independent eval (pointer to template) |
| Stage 4 eval template | `docs/governance/EVAL_STAGE4_TEMPLATE.md` — generalized pre/post-publish template; copy+fill Section 0 & 4 each cycle |
| Eval test scripts | `tests/eval/` — quirk_probe.nd, language_exerciser.nd, framework_capabilities.nd |
| Eval results (per-version) | `docs/evals/vX.Y.Z/` — **three documents per release**: `CREATOR_VALIDATION.md` (Gate 10, pre-publish, against the built wheel), `POSTPUBLISH_EVAL.md` (Stage 5, against the published package), `STAGE6_DOWNSTREAM_SWEEP.md` (companions). See `docs/evals/v5.0.0/` for the current shape |
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
| nodus-workflow repo | `C:\dev\nodus-workflow` / github.com/Masterplanner25/nodus-workflow |
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

**2,140 tests collected** (2026-08-17, during the 5.0.1 cut). Coverage baseline: **76.82%** overall (20,184 stmts) —
that figure was measured 2026-08-07 at 1,878 tests and has **not** been re-measured since the
v5.0.0 work, so treat it as a floor, not a current reading. Gate: 70% (raised from 60% on
2026-05-31). See `docs/governance/TECH_DEBT.md` for the per-module breakdown.

**Pre-existing flaky tests (pass individually, timing-sensitive in full suite):**
- `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`

**The local suite was unreliable on this machine during the v5.0.0 cut (2026-08-16/17).**
Subprocess-based tests with 10 s timeouts failed intermittently, naming a *different* test each
run, and wall-clock drifted from ~7 min to ~18 min with nothing else running. Every such failure
passed in isolation, and one (`test_len_returns_int.py`) was verified to fail identically **with
and without** the change under test. **CI on a clean runner passed every PR in 5–6 min.**

If you see this pattern — failures that move between runs and a suite that is suddenly 2× slower —
do not start bisecting your own change. Re-run the failing test alone, then push and let CI
arbitrate.

**It was transient. Re-measured 2026-08-17 during the 5.0.1 cut: 2,138 passed, 3 skipped, 0
failures, in 7 min 46 s** — back to the normal ~7 min, with no intermittent subprocess failures
and no flake from `test_scheduler_fairness.py`. So the degradation was environmental and is gone;
keep the advice above for the next time it appears, but do not expect it as the current baseline.

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

## Lint gate (ruff)

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

What it used to do, through v4.1.1. The `.venv` install is now 5.0.0, so this is history rather
than a live hazard here — but it is still live for **any pinned-older environment**, and the
`nodus logout --help` row is the reason to check before running `--help` against an unknown build:

| Command | What `--help` did |
|---|---|
| `nodus logout --help` | **Performed the logout.** Deleted the saved registry token from `~/.nodus/config.toml` |
| `nodus publish --help` | Crashed with an unhandled traceback |
| `nodus login --help` | Blocked waiting on stdin |
| `install` / `add` / `remove` / `update` / `deps` / `test` | Ran for real |

This bit a session on 2026-08-06: `nodus logout --help`, run to read the help text,
deleted the user's registry token. `~/.pypirc` was unaffected. If you need to check
against an installed build, use a throwaway `HOME`/`USERPROFILE`.

## PR workflow — required (enforce_admins is ON)

`enforce_admins` is enabled on the `main` branch. **Direct pushes to `main` are rejected for
everyone, including the repo owner.** All changes must go through a branch + PR + CI.

Workflow:
1. `git checkout -b <branch-name>` — create a branch
2. Commit and push: `git push -u origin <branch-name>`
3. `gh pr create --title "..." --body "..."` — open the PR
4. Wait for CI to pass, then merge via `gh pr merge --squash` (or GitHub UI)

Never attempt `git push origin main` directly — it will be rejected.

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
  as of 2026-08-17)
- `--runtime`: runs all ` ```nodus ` and ` ```nodus-expect=output ` blocks
  in docs (**239 blocks**); expects 0 failures with the `.nodusgate-allow`
  allowlist in place
- `--closed-issues`: runs closed-issue tests for CHANGELOG-referenced issues
- `--contracts`: verifies `HandlerContract` infrastructure is wired correctly (6 checks)
- `--opcodes`: verifies the frozen instruction set — reads the dispatch table
  out of a constructed `VM` and requires `BYTECODE_REFERENCE.md` §3, its
  appendix table, and the `FREEZE_PROPOSAL.md` stability tables to name the same
  49 opcodes, with matching counts and `BYTECODE_VERSION`. **If you add an
  opcode, this fails until you document it** — that is the point (#366)

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
- **Status: v0.1.3 PUBLISHED on PyPI** (0.1.3, 2026-08-17, floated the `nodus-lang` cap).
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

The original A2A **wire-protocol** adapter (180 tests, nodus-lang dep) now lives in its
own repo: **`github.com/Masterplanner25/nodus-a2a-wire`** (local worktree at
`C:\codev\nodus-a2a-wire`). Earlier wording here said it was "preserved at
`github.com/Masterplanner25/nodus-a2a`" — that was true only of the *history*: its
commit `10746ce` is an ancestor of that repo's `main`, but the current tree there is the
coordinator, so cloning gives you the wrong thing. Use `nodus-a2a-wire`.

**Current local `C:\dev\nodus-a2a` (AgentCoordinator layer, 23 tests):**
- `AgentRegistry`, `AgentCoordinator` (local/delegate mode), `DelegationRequest`
- `DeadLetterService`, `StuckRunWatchdog`
- No nodus-lang dependency; standalone coordination primitives

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
- **Async test two-flush pattern:** `spawn → flush (task sleeps) → advance_clock(N) → flush (task wakes)`.
  Skipping either flush or the advance causes the test to pass vacuously.
- **`spawn()` takes a coroutine value**, not a function literal. Use
  `let c = coroutine(fn() {...})` then `spawn(c)`.
- **`fn` is a reserved keyword** — can't use as a parameter name in `.nd` files.
- **`if` conditions with function calls require parentheses.** `if (module.fn(a, b))` works;
  `if module.fn(a, b)` gives "Expected '(', got identifier". Simple field access works without
  parens (`if record.field`), but call expressions need `if (expr)`.
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
of several paths goes through**. It surfaced five times in the v5.0.0 cycle alone, which is why
it gets its own section: when you find one, the next question is always *"what else has this
shape?"* — not *"is this fixed?"*

Instances, all confirmed by reading the code rather than inferred:

| # | The check | The path that skipped it |
|---|---|---|
| #392/#393 | retry-vs-defer decision | lived in an `inline_retries` wrapper argument passed by **1 of 5** callers |
| #405 | sandbox / authority | a **derived** VM (`_resume_target_vm`) built a fresh VM and shed the parent's limits |
| #405 | capability policy | consulted at `_invoke_host_function` but **not** `VM.call_builtin` — and the builtins are where `subprocess`/`http` live |
| #427 | formatter round-trip | `nodus fmt` **corrupted** files whose nodes the formatter did not know (`GoalPursuit`, `with { }`), writing output that no longer parsed |
| #353 | `--help` handling | a per-command guard, so every new subcommand shipped unguarded — recurred **four** times |

Two still open with this exact shape, and worth reading before adding any new guard:

- **#387** — a directly constructed `VM()` has no limits at all; every guard lives in a wrapper.
- **#411** — `@exactly_once` is forgeable: the lowering calls **shadowable** names, so a program
  can replace the envelope the compiler injected into it.

**The fix is always the same: move the decision to one place, then assert on the source.** A
behaviour-only test passes on whichever path is already correct — `test_retry_path_unification.py`
asserts on where the retry branch *lives*, and `test_vm_authority_inheritance.py` reads the
sandbox arguments straight out of `VM.__init__`'s signature so a **new** parameter that nothing
propagates fails the test. Copy that pattern rather than writing another end-to-end case.

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
- **Status: v0.1.1 PUBLISHED on PyPI.** PyO3/Maturin Rust extension; pure-Python fallback for all operations. `is_native()` → True when Rust extension loaded.
- **Build requires Rust:** `VIRTUAL_ENV="C:/dev/Coding Language/.venv" maturin develop --release`
  Rust 1.93.1, PyO3 0.22.6, maturin 1.12.6 all installed.
- Run tests: `cd C:\dev\nodus-native-memory-engine && "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest -q`

## nodus-extension companion library

- Repo: `C:\dev\nodus-extension` / `github.com/Masterplanner25/nodus-extension`
- **Status: v0.1.1 PUBLISHED on PyPI.** BYTECODE_VERSION 4, no new opcodes.
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
| `src/nodus_lang_workflow/` | `nodus_lang_workflow` | `C:\dev\nodus-workflow` | `nodus_workflow` |

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
on every sweep, so cost is linear in the number of accumulated runs. Measured
2026-08-15, before and after the #380 syscall fix:

| files | `list_runs()` before | after | `expire_wait_timeouts()` after |
|------:|--------------------:|------:|-------------------------------:|
| 300 | 304 ms | **60 ms** | 48 ms |
| 1,000 | 906 ms | 238 ms | 225 ms |
| 3,000 | 3,223 ms | 863 ms | 579 ms |
| 10,000 | 13,459 ms | 3,840 ms | 2,591 ms |

The cost was never parsing — profiling 3,000 records put 1.7 s of 4.2 s in
`nt.mkdir` (the store re-created its own directory once per record) and 1.6 s in
`nt.stat` (an `os.path.exists` before every `open`). Both are gone; the sweeper
also no longer re-reads every record to find the waiting ones.

Two earlier revisions of this section were wrong in the same direction. The first
said "670+ files cause >2s per sweep"; measurement put the 500 ms sweep interval
at ~299 files, so flakes appeared well below the count anyone watched for. Do not
quote a threshold here without re-measuring — the numbers above are cheap to
regenerate and have now moved twice.

The default store root is **CWD-relative**, so anything running a workflow from
the repo root writes there. As of #380 the suite and the doc gate clean up after
themselves (`tests/conftest.py`, `tools/nodus_gate/runtime_phase.py`), so this
should stay near zero — check it before blaming a flake on timing:

```powershell
ls .nodus/workflow_framework/runs | Measure-Object -Line
```

`rm -rf .nodus/workflow_framework/runs` is safe (test artifacts only).
`NODUS_WORKFLOW_STORE_ROOT` relocates the default store for a process. Bounding
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
- **Status: v0.1.2 PUBLISHED — live on VS Code Marketplace under publisher `MasterplanInfiniteWeave`**
  (0.1.0 2026-06-15; 0.1.1 2026-08-15, the #357 grammar fix; **0.1.2 2026-08-17**, the five
  `goal` stopping-condition keywords). Marketplace validation takes **~4 minutes** — a gallery-API
  check immediately after upload will still report the previous version. That is not a failure.
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
- **Status: v0.1.12 PUBLISHED on PyPI.** Install via `pipx install nodus-mcp-server`.
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
- **Status: v0.1.0 PUBLISHED on PyPI 2026-06-15.**
- **Install:** `pip install nodus-jupyter && python -m nodus_jupyter install`
- **32 unit tests** — require `ipykernel` installed (`pip install ipykernel`).
- Provides a Jupyter kernel for `.nd` files; works in JupyterLab, Jupyter Notebook, VS Code notebooks.

## nodus-run-action

- Repo: `C:\dev\nodus-run-action` / `github.com/Masterplanner25/nodus-run-action`
- **Status: v1.0.0 — GitHub Action (not a PyPI package).**
- **Usage:** `uses: Masterplanner25/nodus-run-action@v1`
- **Three modes:** `file` (run a .nd script), `test-path` (run test suite), `fmt-check` (format gate)
- Pin the nodus-lang version with `version: '5.0.0'` for reproducible CI. **It pins a version, so
  it is invisible to the Stage 6 content-hash sweep** — check it by hand at each release.
- No local test suite — tests run in CI via the action itself.

## nodus-sdk companion package

- Repo: `C:\dev\nodus-sdk` / `github.com/Masterplanner25/nodus-sdk`
- **Status: v0.1.2 PUBLISHED on PyPI.**
  99 tests. Unified platform SDK auto-wiring the 32-package companion ecosystem.
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
- **Status: v0.1.0 PUBLISHED on PyPI.**
  47 tests (31 sync + 16 async). Promoted from `packages/nodus-store-sql` incubator scaffold.
- **Async tests require `aiosqlite`** — not installed by default. Run `pip install aiosqlite` if async tests fail with `ModuleNotFoundError`.
- **Three stores:** `RunStore` (optimistic locking), `EventStore` (append-only), `JobStore` (atomic claiming)
- **Async:** `AsyncSqlStore` via `sqlalchemy.ext.asyncio`; test with `sqlite+aiosqlite:///:memory:`
- **Tables:** `nodus_runs`, `nodus_events`, `nodus_jobs`
- **No Alembic:** `create_all()` is the dev schema bootstrap; production manages migrations independently
- Run tests: `cd C:\dev\nodus-store-sql && python -m pytest -q`

## SemVer policy

The current published version is **v5.0.1** (live on PyPI, published 2026-08-17). Both files must stay in sync:
- `src/nodus/support/version.py` — `__version__ = "5.0.1"`
- `pyproject.toml` — `version = "5.0.1"`

Patch releases (5.0.x) for bug fixes and stability graduations. A minor bump (5.1.0) requires a
substantive feature addition. Never bump without a corresponding PyPI publish. If you see these
files at different values, fix the mismatch before doing anything else.

**v5.0.0 is the first major.** It carries exactly one breaking change — embedded runtimes deny
subprocess/network/env by default (see the embedding section below). The bytecode format did not
change: `BYTECODE_VERSION` is still **4** and the 49-opcode set is untouched, so a major bump does
not imply recompilation.

**v5.0.1 is additive only** — new exports (`GATED_BUILTINS`, `active_vm()`), new tests, docs.
No behaviour change, no new syntax. Upgrading from 5.0.0 requires nothing. It exists because five
companions capped `nodus-lang<5.0.0` and made 5.0.0 unadoptable; see the ecosystem section.

**`README.md` still advertises 4.2.0 as the stable version** (its banner and its "Recent:"
paragraph) — left through the 5.0.0 cut deliberately, and the first task of the next cycle.
Checked 2026-08-17: it is the **only** doc making a stale *current-version* claim; the 4.2.0
mentions in `RELEASE_GATES.md` and `real-world-integration.md` are historical and correct as
written, and the `docs/evals/v4.2.0/` hits are that release's own records.

**No gate checks version strings**, which is why `COMPATIBILITY.md` and `docs/release.md` sat at
4.1.1 through an entire release before anyone noticed. Treat a version string in prose as
unverified until you grep it — and distinguish *"X is current"* from *"as of X"* before
rewriting either.

## Embedding API — known blockers and operational traps

These were identified by a raw-path readiness probe and are filed as GitHub issues.
Full analysis: `C:\dev\nodus-mcp\docs\design\06-embedding-runtime-blockers.md`.
All entries are also in `docs/governance/TECH_DEBT.md`.

**EMBED-001 (#97) — FIXED. `timeout_ms` now defaults to `None`.** The old 200ms-default
trap is gone; `NodusRuntime()` applies no wall-clock deadline. Verified 2026-08-07:
`NodusRuntime().timeout_ms is None`. Do not re-add `timeout_ms=None` as a "fix" — it is
already the default. (SCHED-001 also means cooperative sleep no longer consumes the
budget even when a deadline *is* set.)

**`max_frames` (#350) — FIXED.** `None` now means `MAX_STACK_DEPTH` (10,000), the
same cap the CLI applies, so `NodusRuntime(max_steps=None, timeout_ms=None)` raises
`Call stack overflow` on runaway recursion instead of growing frames until OOM. The
cap lives in one place, `configure_vm_limits` in `tooling/sandbox.py`; `embedding.py`
only overwrites it when the caller passed a value. Do not "fix" this by making the
assignment unconditional again — that is the bug.

```python
# Fine as of the #350 fix — capped at 10,000 frames:
rt = NodusRuntime(max_steps=None, timeout_ms=None)

# Tighter, for untrusted scripts:
rt = NodusRuntime(max_steps=None, timeout_ms=None, max_frames=1000)
```

There is no "unlimited" setting — pass a large integer if you genuinely want one.
v4.1.1 and earlier are affected; hosts pinned there must pass `max_frames`.

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

**SPAWN-001 — FIXED.** Tracked as **#116** (closed), not #117 (which was closed as a
duplicate of it). `wait_async()` now suspends properly: it runs `proc.wait()` on a
worker thread, registers a result channel with `scheduler._io_channels`, and sets
`coroutine.state = "suspended"`. See `builtins/subprocess_module.py::_wait_async`.

**CHAN-001 (#107) — FIXED** in PR #137, verified 2026-08-07. A coroutine blocked on
`recv()` with no possible sender now raises a deadlock error instead of being silently
orphaned:

```
Deadlock: 1 coroutine(s) blocked on recv() with no possible sender: __anon_1
```

Note when testing this: the scheduler must actually be driven. `spawn(c)` alone does not
run the coroutine — without a `run_loop()` the script exits 0 and the coroutine never
starts, which *looks* like the original bug. Use `spawn(c)` then `run_loop()`.

## Published ecosystem — current state (nodus-lang verified 2026-08-17; companions 2026-08-05)

All packages are live. PyPI rate limits apply to **new project creation** (~a few
per hour), not to version uploads on existing projects — republishing new versions
of already-published packages is not session-limited.

**nodus-lang:** **v5.0.0** on PyPI (2026-08-17). nodus-retry is an optional dep (`nodus-lang[retry]`); runtime falls back to built-in `InMemoryEffectStore` when absent.

**Companion `nodus-lang` ranges — do not read them by eye. Run the check:**

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" -m tools.check_downstream_constraints
```

All six dependents now float (`>=4.0.0`, or `>=4.0.5` for `nodus-mcp-server`) and admit 5.0.0.

That is true **as of 2026-08-17 and not before it.** An earlier revision of this section said
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

**Standalone companion packages — 32 live on PyPI** (33 projects counting nodus-lang).
All at v0.1.0 except where noted:
```
nodus-schema, nodus-protocol, nodus-state, nodus-session, nodus-events
nodus-channels, nodus-context, nodus-approvals, nodus-circuit-breaker
nodus-agent, nodus-auth, nodus-observability, nodus-queue, nodus-router
nodus-delivery, nodus-http, nodus-llm, nodus-adapter-base
nodus-observability-framework, nodus-workflow, nodus-store-sql
nodus-extension, nodus-native-memory-engine, nodus-jupyter
nodus-governance, nodus-memory, nodus-a2a
```
Ahead of v0.1.0: `nodus-retry` **0.2.0**, `nodus-mcp` **0.1.3**, `nodus-gateway` **0.1.1**,
`nodus-sdk` **0.1.2**, `nodus-mcp-server` **0.1.12**, `nodus-extension` **0.1.1**,
`nodus-native-memory-engine` **0.1.1**.

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
the wire adapter is at `nodus-a2a-wire` (git only). The nodus-memory adapter exists only
in history — `git show f02ab1e:src/nodus_memory/nodus_bindings.py`.

**Other published artifacts:**
- nodus-vscode **v0.1.2** — VS Code Marketplace (MasterplanInfiniteWeave), 2026-08-17
- nodus-run-action v1.0.0 — GitHub Action (Masterplanner25/nodus-run-action@v1)

**PyPI token note:** Each package in a separate repo (nodus-mcp, nodus-extension,
nodus-memory, nodus-native-memory-engine, nodus-mcp-server) needs its own project-specific PyPI token.
nodus-lang packages use the main nodus-lang token. Retrieve from user at upload time —
never store tokens in any file.

**Future publish sequence:** For any new package, the pattern is:
1. `python -m build` (in the package dir)
2. `twine upload --username __token__ --password <token> dist/*`
3. Add status badge to README, commit, push
