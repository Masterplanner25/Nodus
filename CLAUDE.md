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

**The gap is live and twelve minors wide** — re-checked 2026-09-06 after the
5.12.0 cut: `.venv` says **5.0.0**, `src/` says 5.12.0. It widens at every
release, because nothing reinstalls it. Forgetting the prefix gets you a runtime from before
essentially every 5.x fix, and **the symptom is behaviour that contradicts the code you
are reading** — which is the part worth remembering, because it does not look like a
stale install, it looks like a bug.

The list of what is missing used to be written out here and grew at every release; read
`CHANGELOG.md` between the two versions instead.

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

**The full release sequence is in `.claude/commands/release-sequence.md`. Read it before
any release step.** It is the authority; `/release-prep` is older than it. Three rules that
must not wait for that read: run the dependent-suite gate (`tools.check_dependent_suites`)
before any PyPI upload, create the GitHub release only after PyPI succeeds, and never write
a token into a repo file.

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
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Doc-vs-code gate | `tools/nodus_gate/` — run `python -m tools.nodus_gate.cli --all` |
| Version-claim manifest | `tools/version_claims.json` |
| Dependent-suite gate | `tools/check_dependent_suites.py` |
| nodus-lang dependent registry | `tools/nodus_lang_dependents.json` |
| Staged next-major readiness | `nodus check --staged` |
| Staged-flip warnings | `src/nodus/support/staging.py` |
| Staged next-major register | `src/nodus/support/staged_flips.json` |
| Invariant coverage ledger | `tools/invariant_coverage.json` |
| Shape manifest | `tools/shape_manifest.json` |
| Recorded dependent flakes | `tools/dependent_flakes.json` — diagnosed flakes, used to *classify* a red run, never to pass one. Every entry needs a stated reason |
| Downstream range check | `tools/check_downstream_constraints.py` |
| Publish-drift check | `tools/check_publish_drift.py` |
| Library entry-point contract | `docs/guide/library-entry-points.md` |
| Companion library contract | `docs/governance/COMPANION_LIBRARY_CONTRACT.md` |
| Pre-publish eval prompt | `docs/evals/EVAL_PREPUBLISH.md` — Gate 10 creator validation |
| Release-claims probes | `tests/eval/release_claims_probe.py` |
| Post-publish eval prompt | `docs/evals/EVAL_POSTPUBLISH.md` — Stage 5 independent eval (pointer to template) |
| Stage 4 eval template | `docs/evals/EVAL_STAGE4_TEMPLATE.md` — generalized pre/post-publish template; copy+fill Section 0 & 4 each cycle |
| Throughput + startup benchmark | `tools/benchmark_runtime.py` |
| Scheduler time source | `src/nodus/runtime/time_source.py` |
| Eval test scripts | `tests/eval/` |
| Eval results (per-version) | `docs/evals/vX.Y.Z/` |
| Audit prompt index | `docs/audits/AUDIT_INDEX.md` |
| External audit ledger | `docs/governance/EXTERNAL_AUDIT_LEDGER.md` |
| Capability policy design | `docs/governance/CAPABILITY_POLICY_DESIGN.md` |
| Capability implementation | `src/nodus/runtime/capability.py` — `CapabilityPolicy`, `CapabilityDecision`, `DenyList`, `Floor`, `DEFAULT_FLOOR`, `inherit_authority()` |
| v5 design docs | `docs/design/v5/` |
| 6.0.0 migration guide | `docs/migration/v6.0-staged-flips.md` |
| Deny-by-default migration | `docs/migration/v5.0-deny-by-default.md` — the one breaking change in 5.0.0 |
| Goal validation | `src/nodus/frontend/goal_validation.py` — compile-time `reached("label")` checking |
| Maturity checklist + re-score | `docs/governance/MATURITY_CHECKLIST.md` — 72.5 → 82-83 (2026-05-31) |
| Issue response policy | `docs/governance/ISSUE_RESPONSE_POLICY.md` |
| AI discoverability (canonical map) | `llms.txt` |
| AI discoverability (rich summaries) | `llms-full.txt` |
| GitHub wiki (local) | `C:\dev\Nodus Wiki\nodus-wiki\` — git repo, branch `master`, remote `Masterplanner25/Nodus.wiki.git` |
| **Companion repos (all 14)** | `docs/ecosystem/COMPANION_REPOS.md` |
| Ecosystem incubator specs | `docs/ecosystem/` — spec docs for planned libraries |
| Ecosystem incubator scaffolds | `packages/` — Python-first scaffolds for planned libraries |

**Read on demand.** These hold what used to sit in this file; open the one that matches the task.

| Task | File |
|------|------|
| Any release step, the version-claim rules, "is this symptom a release?" | `.claude/commands/release-sequence.md` |
| Fixing a defect, or anything shaped like a check with a sibling path | `.claude/commands/recurring-bug-shape.md` |
| Writing or debugging `.nd` code | `.claude/commands/nodus-quirks.md` |
| Embedding, `NodusRuntime`, capabilities | `.claude/commands/nodus-embedding.md` |
| Governance docs, and the longer notes on files listed above | `.claude/commands/docset-governance.md` |
| Work under `tests/`, `tools/` or `src/nodus_lang_workflow/` | that directory's `CLAUDE.md`, loaded automatically |

## Test suite

```powershell
# Full suite
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# Coverage (excludes 3 timing-sensitive tests)
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ --cov=src/nodus --cov-fail-under=70 --ignore=tests/test_scheduler_fairness.py -q
```

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
re-run. The same applies to the doc gate (`nodus_gate --runtime` executes every documented block and writes to
the store) — do not run it alongside the suite.

**So the first question when the suite misbehaves is not "what did I change" but
"how much memory is free".** One command:

```powershell
Get-CimInstance Win32_OperatingSystem |
  ForEach-Object { "{0:N1} GB free of {1:N1} GB" -f ($_.FreePhysicalMemory/1MB), ($_.TotalVisibleMemorySize/1MB) }
```

Under ~1.5 GB free, treat every timeout-shaped failure as suspect until it
reproduces on a calmer box or on CI.

Two practical consequences:

- **A local full-suite run is not a gate here.** Prefer targeted runs over the areas you touched,
  then push and let CI arbitrate. CI on a clean runner finishes in 5–6 min and has been reliable.
- **CI runs `python -m unittest discover -s tests` *and* `pytest`** (`.github/workflows/ci.yml`).
  They are not interchangeable: during the #411 work, CI's unittest step caught two failures that
  `pytest` passed locally — the cause was the environment (`nodus-retry` installed locally, absent
  on a clean runner), not the runner, so **a local pytest run cannot substitute for either.**
  Optional extras are the thing to watch: `@retry` needs `nodus-lang[retry]`.

Flake histories, the host-memory diagnosis, timing-headroom rules and the clock's limits are
in `tests/CLAUDE.md`, which loads when you work under `tests/`. **Read it before fixing a
flake or writing a test that races a timeout.**

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

Phases: `--static`, `--runtime`, `--closed-issues`, `--contracts`, `--consumers`, `--opcodes`,
`--shapes`, `--versions`, `--invariants`, `--flips`. What each checks, and why, is in
`tools/CLAUDE.md`, which loads when you work under `tools/`.

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

Four things worth knowing before you open the detail file:

- **The wire repo is `C:\codev\a2a-wire-pub`**, and there is only one candidate
  now. `C:\codev\nodus-a2a-wire` was a worktree of the *coordinator* repo's old
  history, so its name pointed at the wrong project and pulls and pushes went
  there; **removed 2026-09-07** with `git worktree remove`, after checking it held
  no uncommitted or untracked work, that `10746ce` is reachable from
  `nodus-a2a`'s `origin/main`, and that `a2a-wire-pub` contains that commit at the
  base of its own 17-commit history. Nothing was lost, and `git worktree add` at
  that commit recreates it. Recorded because a directory named after the package
  it is *not* is the kind of thing that comes back.
- **Renaming a distribution does not fix a module collision.** `nodus-a2a-wire`
  and `nodus-a2a` both shipped `nodus_a2a`; installing one over the other deleted
  the other's classes with pip reporting success both times (NAME-COL-001).
- **Bridge and host functions return maps, not Records** — `.nd` must use
  `r["key"]`, never `r.key`.
- **VS Code spawns the *installed* `nodus.exe`**, so LSP server changes need a new
  nodus-lang release before the extension sees them.

## Nodus language quirks (relevant when writing test .nd code)

Read `.claude/commands/nodus-quirks.md` before writing or debugging `.nd` code, including
`.nd` embedded in a test. It holds the map-vs-record rules, syntax traps, and the 200 ms
default budget on `nodus run`.

## Security boundary test rule

Any fix for a security boundary (path traversal, sandbox escape, allowed_paths
enforcement, resource limits) must have tests covering BOTH CLI mode and
`NodusRuntime` embedded mode. The enforcement code path can differ between
contexts. See `docs/governance/TECH_DEBT.md § Testing Methodology`.

## The recurring bug shape — a check on one path, a sibling path that bypasses it

This codebase's most common defect is not a wrong check. It is a **correct check that only
one of several paths goes through**. When you find one, the next question is always *"what
else has this shape?"* — not *"is this fixed?"*

**The fix is always the same: move the decision to one place, then assert on the source.** A
behaviour-only test passes on whichever path is already correct. Name the set once and drive
a test off it, and run every negative assertion against the unfixed tree to confirm it goes red.

**Run the repro a second time, always.** The bytecode cache is usually one of the paths.
`nodus_gate --shapes` reports new places where one question is answered in two voices.

The instance table and worked examples are in `.claude/commands/recurring-bug-shape.md`.
Read it before fixing anything of this shape, and add each new instance's row there.

## Documentation governance

`docs/governance/DOCSET_INDEX.md` is the reader entry point and says which document wins a
conflict; check `Last reviewed:` before letting one win. When writing a governing document,
**prefer defining a distinction to enumerating its instances**, and put the enumeration where
a gate can read it. The rules and what past reviews found are in
`.claude/commands/docset-governance.md`.

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

## nodus-workflow (in-tree framework)

Status, store-scan cost, state roots and cleanup are in `src/nodus_lang_workflow/CLAUDE.md`,
which loads when you work under that directory. Three rules apply from anywhere:

- **Do not "fix" CIRC-001 (#103) by hoisting the lazy `get_default_workflow_runner` imports in `vm.py`.**
- **Clear run state with `nodus workflow cleanup`, not `rm -rf`, outside this repo's root.** A run
  is split across two directories, and deleting only the records strands a live waiting run.
- **`nodus workflow cleanup` has no preview.** Against 5.11.0 or earlier, `--dry-run --force` deletes.

## SemVer policy

The current published version is **v5.15.0** (live on PyPI, published 2026-09-25).
Two files must stay in sync — `src/nodus/support/version.py` and `pyproject.toml`.
If they disagree, fix that before anything else.

Patch releases for bug fixes and stability graduations; a minor bump requires a
substantive feature addition. **Never bump without a corresponding PyPI publish.**

What each release added is in `CHANGELOG.md`. If a working setup broke and you need to know
whether the cause is a release or your change, see "What is *not* additive" in
`.claude/commands/release-sequence.md`.

## Embedding API — known blockers and operational traps

Full detail is in `.claude/commands/nodus-embedding.md`. **Read it before changing `NodusRuntime`.**

**Capability switches deny by default as of v5.0.0 (#405).** `allow_subprocess`,
`allow_network` and `allow_env` are all **`False`**. A bare `NodusRuntime()` cannot shell out,
open sockets, or read the process environment; grant explicitly:

**`nodus run` and the rest of the CLI are deliberately NOT affected.** This is a decision, not
an oversight: the CLI builds a `VM` directly and never constructs a `NodusRuntime`, and a test
pins **both** halves so the "inconsistency" is not tidied away by a later reader. The domain
deny-by-default protects is *work you did not fully author* — a developer running a script they
just wrote is not that.

- **The denial contract is `kind` and the flag name, not the sentence.** `error["kind"]` is
  `"sandbox"`; `error["message"]` contains the granting flag. The wording changed in 5.0.0 and
  turned four downstream confinement tests red **while the guest was fully confined**. If you
  rephrase a denial, keep the flag name in it.

- **Do not add `**kwargs` to `NodusRuntime.__init__`, and keep the confinement flags
  keyword-only.** Both are load-bearing: with a catch-all, a renamed flag is silently swallowed
  and the guest runs unconfined with every mock-based test on the embedder's side still green.
  Pinned by test so it cannot be undone casually.

- **`register_function` refusing to override a builtin is a security boundary**, not a
  convenience check. Because a builtin cannot be aliased, a host can install a fail-loud guard
  under a guest-reachable name (aindy does this for `syscall`) and know the guard is the only
  thing there. Also now pinned.

**Do not store new runtime state under a public attribute name without checking downstream.**
`self.memory_store` collided with a read-only property of the same name on
`nodus_sdk.NodusSDKRuntime` and broke every construction of that subclass in 5.0.3. It is
`self._memory_store` now. A base class adding a public attribute can break any subclass that
made the same name a property.

**`run_source(source, filename=...)` runs `source`. It did not, before 5.1.0** (#521,
present since v0.4.0): if a file of that name existed, the loader read *the file* and
discarded the `source` argument, returning `ok=True` with the other program's output — so
which program ran depended on the process CWD. `filename` is a label; a real path only
decides where relative imports resolve from. Use `run_file` to run a file.

## Published ecosystem — how to find out, not what it was

The checks, their history and the package count are in `.claude/commands/release-sequence.md`.

**Policy, decided 2026-08-17: companions do not cap `nodus-lang`.** A hard upper
bound on a first-party dependency turns every major into a two-repo release train
with consumers frozen in between. The companion's own suite catches a real break; a
cap earns its place once a break is known, not before.

**Only `pip install <name>==<version>` is authoritative.**

**Never write a token into any file in any repo.** `~/.pypirc` holds an
account-scoped token, which works for every first-party project **and creates a new
project on first upload** — no PyPI-side pre-creation step is needed (established
publishing `nodus-workflow-ai`, 2026-08-30). A project-scoped token is an
alternative, not a requirement. If an upload 403s, the password field has gone
empty again — ask the user rather than guessing.

**PyPI's JSON API serves stale data after an upload** — it reports the *previous*
release as latest, which reads exactly like a failed upload, and at 5.6.0 it
reported **zero files** for the version that had just landed. The simple index lags
too: `pip install nodus-lang==5.8.0` failed for minutes after the 5.8.0 upload
succeeded. `Cache-Control: no-cache` does not prevent either.
