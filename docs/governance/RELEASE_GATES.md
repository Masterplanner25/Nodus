<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Release Gates

**Version:** 4.1.1
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

This document lists every gate that must pass before a Nodus release is declared
ready. It is authoritative; `docs/governance/RELEASE_CHECKLIST.md` is the procedural
companion that walks through execution. This document defines the standards; the
checklist executes them.

---

## Gate 1: Test suite

**Command:**
```powershell
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

**Passing criteria:**
- All tests pass (0 failures, 0 errors)
- Coverage ≥ 70% (gate: `--cov-fail-under=70`; raised from 60% on 2026-05-31)
- Coverage run uses `--ignore=tests/test_scheduler_fairness.py` to exclude
  timing-sensitive scheduler fairness tests; those tests must still pass in the
  non-coverage run. Known pre-existing flaky test under full-suite load:
  `test_scheduler_fairness.py::test_long_running_task_rotates_with_budget`.

**Exemptions:** None. The coverage gate cannot be lowered without a TECH_DEBT.md entry
documenting the reason and a plan to recover.

---

## Gate 2: Ruff lint

**Command:**
```powershell
& "C:/dev/Coding Language/.venv/Scripts/python.exe" -m ruff check src/ tests/
```

**Passing criteria:**
- Zero violations in any file you changed
- Pre-existing violations in `src/nodus/vm/vm.py` (E702),
  `src/nodus/builtins/time_module.py` (E701, F841),
  `src/nodus/builtins/encoding_module.py` (F401),
  `src/nodus/builtins/secrets_module.py` (F401) are known and do not block release
  if no new violations were introduced

**Exemptions:** When running pre-release, scope to files changed in the release cycle.
Do not introduce new violations; do not fix pre-existing violations as part of a
release without separate review.

---

## Gate 3: Doc-vs-code gate (nodus_gate)

**Command:**
```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --all
```

**Passing criteria:**
- `--static`: all 133 documented symbols exist in the codebase
- `--runtime`: all doc code blocks run without failure (0 failures; allowlist covers
  intentionally non-runnable blocks)
- `--closed-issues`: all closed-issue regression tests pass
- `--opcodes`: the VM dispatch table matches `BYTECODE_REFERENCE.md` §3, its appendix
  table, and the `FREEZE_PROPOSAL.md` stability tables exactly, and the opcode counts
  and `BYTECODE_VERSION` claimed in those docs match the live values

**Exemptions:** New failing blocks must either be fixed before release OR added to
`.nodusgate-allow` with a comment explaining why they are intentionally non-runnable.
No silent additions to the allowlist.

---

## Gate 3b: Editor grammar keeps up with the language

**Standard (established after #357):**

A release that adds or removes a language keyword must update the VS Code
grammar in the `nodus-vscode` repository and republish the extension.

`match`, `break` and `continue` shipped in v4.1.0 and were not highlighted for
two releases, because contextual keywords live in the parser rather than the
lexer's reserved set and nothing listed them where a tool could read them.

**Check:**

```powershell
PYTHONPATH="C:/dev/Coding Language/src" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m pytest tests/test_keyword_coverage.py -q
```

`nodus.frontend.lexer.ALL_KEYWORDS` is the source of truth. The grammar check
needs the `nodus-vscode` checkout and **skips without it**, so it does not run in
this repository's CI — run it locally before a release that touched syntax.

**That skip is the hole, and Gate 3c closes it.** `when` shipped in the step-guard
work with the grammar unupdated, precisely because the only check that would have
caught it cannot run where merges are gated.

---

## Gate 3c: Non-PyPI consumers are in step

**Standard (established after the `when` keyword shipped unhighlighted):**

Stage 6's downstream sweep detects drift by hashing published sdists and wheels
against local source. Anything **not on PyPI is invisible to it** — and two things
are: `nodus-vscode` (a Marketplace VSIX) and `nodus-run-action` (a GitHub Action).
Both have shipped stale with nothing to notice.

**Check:**

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --consumers
```

Unlike Gate 3b this reads **no sibling checkout and makes no network call**, so it
runs everywhere including CI. Each consumer records, in `tools/consumers.json`, the
fingerprint of whatever it must stay in step with — measured in *this* repo at the
moment it was last published. When the live value moves, the consumer is stale:

```
  [--] nodus-vscode (0.1.2) — NEEDS REPUBLISH
       keywords moved: 8670d9baf85b0313 -> 602761bf77ebb21e
```

**Advisory by default** — it prints and exits 0. `--strict` makes a stale consumer
fail the run. A stale consumer is a release obligation, not a broken tree, and
flagging it weeks early is worth more than blocking an unrelated merge. A manifest
that cannot be read is always a failure: a check is not allowed to pass by being
unable to run.

**Clearing a flag:** republish the consumer, then update its `fingerprint` and
`published` in `tools/consumers.json` **in the same commit** — the manifest is the
record of what was published, so letting it drift from reality defeats the gate.

**Adding a consumer:** add an entry naming what it `tracks`, run the gate, and
paste the value it reports. A `tracks` value the phase cannot measure is an error
rather than a skipped check.

---

## Gate 4: Closed-issue regression test gate

**Standard (established after v3.0.1 incident):**
Every issue marked as closed and referenced in CHANGELOG.md must have at least one
regression test that exercises the specific behavior fixed. Before cutting a release
wheel, the regression tests for all closed issues in the release must pass against
the **installed wheel**, not just the dev source.

**Procedure:**
1. Build the wheel: `python -m build`
2. Install in a clean virtualenv: `pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl`
3. Run the closed-issue regression tests against the installed wheel

**Why this gate exists:** v3.0.1 shipped without a fix that was present in source but
not in the wheel (missing push before PyPI upload). This gate catches that class of error.

**The trap: this gate goes vacuous the moment the CHANGELOG is cut.** The
`--closed-issues` phase scans `[Unreleased]` by default. Once that section has
been moved to `[X.Y.Z]` as part of release prep, the default scan finds an empty
section and reports:

```
Scanning CHANGELOG [Unreleased] section
Found 0 issue reference(s)
Closed-issues: PASS - 0 passed, 0 failed, 0 missing (of 0 referenced issues)
```

That is a **pass that checked nothing**, and a green `--all` run after the version
cut is not evidence the regression tests were verified. At release time it must be
run against the release section:

```powershell
PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
  "C:/dev/Coding Language/.venv/Scripts/python.exe" `
  -m tools.nodus_gate.cli --closed-issues --section "X.Y.Z"
```

Found during the v4.2.0 release (16 issues, all passing once scanned correctly).

---

## Gate 5: Version sync check

**Check:**
- `src/nodus/support/version.py` contains `__version__ = "X.Y.Z"`
- `pyproject.toml` contains `version = "X.Y.Z"`
- Both match the intended release version
- `nodus --version` (from dev source) outputs `X.Y.Z`

**Exemptions:** None.

---

## Gate 6: CHANGELOG.md entry

**Check:**
- `CHANGELOG.md` has a section for the release version
- The `[Unreleased]` section is empty or does not exist
- All significant changes in the release are listed

**Exemptions:** Trivial patch releases (e.g., version bump only) may have minimal
CHANGELOG entries.

---

## Gate 7: README version sync (for major releases)

**Check:**
- `README.md` JSON-LD block `"version"` matches the release version
- `README.md` describes current features accurately (no forward-looking claims as present)

**Exemptions:** Patch and minor releases do not require a full README review, but the
JSON-LD version field must be updated.

---

## Gate 8: Doc-vs-code gate on companion libraries

For any release that includes companion library changes, the doc-vs-code gate must
pass for all affected repos before any of them is published.

**Companion library test commands:**
```powershell
# nodus-mcp
cd C:\dev\nodus-mcp
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q

# nodus-a2a
cd C:\dev\nodus-a2a
PYTHONPATH="C:/dev/Coding Language/src" "C:/dev/Coding Language/.venv/Scripts/python.exe" -m pytest tests/ -q
```

---

## Gate 9: Spec version verification (for companion library releases)

Before any companion library is published to the registry, a final-pass spec check
must confirm the library implements the version of the spec it claims.

For nodus-mcp: verify against the 2026-07-28 RC (or final, if available)
For nodus-a2a: verify against A2A 1.0.0 (Linux Foundation)

This catches spec changes between implementation and release.

---

## Gate 10: Pre-publish creator validation

**When:** after the wheel is built (Gate 4 artifacts), before `twine upload` to PyPI.

**Purpose:** the maintainer actively tries to break the language against a real installed
wheel — not dev source — with the explicit goal of finding bugs before users do. This is
adversarial by design. It is different from the post-publish independent eval (Stage 5 /
Gate 4): that stage evaluates "does this work as a new user would expect?" This gate asks
"what can I personally make fail?"

**Protocol:**

0. **Run every dependent suite — before the upload, not after.**

   ```powershell
   PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" `
     -m tools.check_dependent_suites
   ```

   Exit 0 means every companion still passes against this tree. Exit 1 lists the
   ones that do not; exit 2 means a checkout was missing, which is not a pass — an
   unrun suite covers nothing.

   > **This step exists because v5.0.3 shipped without it.** A change to
   > `NodusRuntime.__init__` assigned `self.memory_store`, and
   > `nodus_sdk.NodusSDKRuntime` subclasses it with `memory_store` as a *read-only
   > property* holding its own vector store. Every construction of that subclass
   > raised `AttributeError: ... has no setter`; nodus-sdk went from 99 passed to
   > 29 failed and 10 errors.
   >
   > Gate 10 validates nodus-lang **against itself** and passed cleanly — 32
   > adversarial probes, all green. Stage 6 runs the dependents and caught it, but
   > Stage 6 is **post-publish**, and PyPI is immutable. The break was found one
   > release too late and needed 5.0.4.
   >
   > The lesson generalises beyond that bug: a base class adding a public attribute
   > can break a subclass that made the same name a property, and no amount of
   > testing nodus-lang against nodus-lang will reveal it.

1. Build the wheel: `python -m build`
2. Install in a **clean virtualenv** (not the dev venv):
   ```powershell
   python -m venv .venv-validation
   .venv-validation/Scripts/pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl
   ```
3. Write 8–12 Nodus programs targeting the highest-complexity surfaces. Required
   categories:
   - **Closures and upvalue capture** — nested closures, mutation through outer scope
   - **Coroutines and channels** — spawn/yield/recv sequences, closed-channel behavior
   - **Error handling** — try/catch/finally interaction, throw inside finally, rethrow
   - **Import system** — multi-file imports, circular import detection, alias resolution
   - **Operator and type edge cases** — division by zero, nil coercion, integer vs float arithmetic
   - **Error messages** — are they user-legible or internal garbage? Trigger each error category
   - **The documented quirks** from `CLAUDE.md §"Nodus language quirks"` — every quirk must
     behave exactly as documented; any deviation is a bug
   - **At least one workflow or goal execution** if the release touches the orchestration layer
4. For each failure found, apply the disposition:
   - **Fixable before publish** (clear root cause, low regression risk) → fix it now; it ships
     in this version; add a regression test; add to CHANGELOG
   - **Not fixable before publish** (requires design, risky, or too large) → file a GitHub issue
     immediately with full repro; note it as a known issue in the release announcement; commit
     to a fast turnaround (see `docs/governance/ISSUE_RESPONSE_POLICY.md`)
5. Record findings in `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` — even if everything passes.
   A clean run is evidence, not silence.

**Passing criteria:**
- No unfiled bugs. Every failure either has a fix committed or a filed issue with a severity label.
- At least 8 programs executed to completion or to expected failures.
- No regressions introduced by any fix made during this stage (Gate 1 reruns after each fix).

**Exemptions:**
- Emergency security patches may run an abbreviated version scoped to the patched code path only.
- Pure doc-only releases are exempt.

**Why this gate exists:** prior to v4.0.0, discovery of language bugs happened post-publish via
the independent eval (Stage 5). This placed bugs in front of users before the maintainer knew
about them. Creator validation closes that window by moving adversarial testing to before the
upload, when fixes are still cheap.

---

## Stage 5: Post-publish eval

**When:** immediately after `twine upload` succeeds, before announcing the release.

**Purpose:** Gate 10 asks *"what can I make fail?"* against a locally-built wheel.
This stage asks a different question — **"does this work as a new user would
expect?"** — against the package as actually published. It catches the class of
problem a local wheel cannot: a bad upload, a missing file in the sdist, a
dependency that resolves differently from PyPI, or a README instruction that no
longer matches the shipped CLI.

**Protocol:**

1. Fresh virtualenv, nothing else installed, **no `PYTHONPATH`**:
   ```powershell
   python -m venv .venv-postpublish
   .venv-postpublish/Scripts/pip install nodus-lang==X.Y.Z
   ```
2. `nodus --version` matches the release.
3. **Run the README quickstart verbatim** in an empty directory. If the README
   says `nodus init` then `nodus run`, type exactly that and nothing else — the
   point is to find the gap between what the docs say and what ships.
4. Verify every user-facing claim the release advertises — the CHANGELOG headline
   entries and the README's "Recent" line. Each one, against the published
   package, not dev source.
5. Confirm the known issues shipped in the CHANGELOG are the ones you actually
   hit, and that none of them blocks the new-user path.
6. Record in `docs/evals/vX.Y.Z/POSTPUBLISH_EVAL.md` — **even if everything
   passes.** A clean run is evidence, not silence.

**Passing criteria:**
- Installs from PyPI into a clean environment.
- The README quickstart works as written.
- Every advertised claim verified against the published artifact.
- Findings filed as issues; a finding here does not un-publish the release, but it
  does set the priority for the next patch.

**Why this stage exists:** Gate 10 validates a wheel on the maintainer's disk.
Everything between that wheel and `pip install` — the upload, the sdist contents,
dependency resolution — is untested until someone installs it, and historically
that someone was a user.

---

## Stage 6: Downstream republish sweep

**When:** after Stage 5, once the release is published and verified.

**Purpose:** a nodus-lang release can leave companion packages stale in two ways —
a pinned dependency range that no longer admits the new version, or a fix that was
committed to a companion during the release cycle and never published. Both are
invisible from this repository.

**Protocol:**

1. **Dependency ranges — run the script, do not read the files.**

   ```powershell
   PYTHONPATH="C:/dev/Coding Language/src;C:/dev/Coding Language" `
     "C:/dev/Coding Language/.venv/Scripts/python.exe" `
     -m tools.check_downstream_constraints
   ```

   Paste its output into the sweep document. Exit 0 means every published
   companion admits the new version; exit 1 lists the ones that do not; exit 2
   means the index was unreachable, which is not a pass.

   It reads **published** metadata from PyPI, because that is what a user's `pip
   install` resolves against. A cap floated in a companion's `main` but not
   released helps nobody — the check must fail until the companion is republished.
2. **Content drift — compare the published artifact, not version strings and not
   git history.** Download each package's sdist (or wheel) from PyPI and hash its
   `.py` / `.nd` / `.toml` / `.rs` files against the local checkout. Equal hashes
   mean the publish is current; any difference is unpublished work.
3. **Uncommitted work in companion checkouts.** `git status` each one. A fix
   written during a release cycle and left in a working tree is the most common
   miss, and the one this stage exists for.
4. **Editor and CI surfaces.** `nodus-vscode` republishes via a manual VSIX
   upload; `nodus-run-action` pins a nodus-lang version for reproducible CI.
   Neither is on PyPI, so neither shows up in step 2.

> **Do not read dependency ranges by eye.** The v5.0.0 sweep did, and transcribed
> **five of six** with the upper bound dropped — recording `>=4.0.0` where the
> published metadata said `>=4.0.0,<5.0.0`. It then concluded "no companion caps
> its range" when in truth only one of the six could install alongside the new
> release; `pip install nodus-lang==5.0.0 nodus-mcp` was `ResolutionImpossible`
> for a day, until a downstream team reported it.
>
> This is not a lapse that more care prevents. `>=4.0.0,<5.0.0` reads as admitting
> 4.x — which is what the eye is checking — and the clause that forbids the new
> version sits at the far end of the string. Resolve it with `packaging`; that is
> what the script does.
>
> A second lesson from the same miss: **a passing companion suite says nothing
> about installability.** §2 of that sweep correctly recorded every dependent
> suite passing against 5.0.0, because they were run against the dev source. The
> suites could not have been reached through a normal `pip install` at all, and
> noticing that would have exposed the cap a day earlier.

> **Do not use git heuristics to detect drift.** "Commits since the last
> version-bump commit" looks like the right test and is not: a version line is
> often set early in a cycle and published from a later commit, so the heuristic
> reports every fix in between as unpublished. During the v4.2.0 sweep this
> produced **four false positives**, including a claim that a published kernel was
> broken when the published artifact already contained the fix. Hashing the
> published files gave the correct answer — zero drift — in one pass.

**Passing criteria:**
- Every companion's dependency range admits the new nodus-lang version.
- Zero content drift between published artifacts and local source, or a republish
  for each package that has drift.
- No uncommitted work left in a companion checkout.

**Why this stage exists:** the v4.2.0 sweep found the #357 VS Code grammar fix
sitting uncommitted in the `nodus-vscode` working tree — the nodus-lang half had
shipped in the release while the half users actually see had not. Nothing in the
release process would have caught it, because it was not in this repository.

---

## Gate failure handling

A failed gate blocks the release. The options are:

1. Fix the failing gate → proceed with release
2. Document the failure as a known issue in `docs/governance/TECH_DEBT.md` → release
   with a corresponding GitHub issue tracking the fix (only for non-blocking failures
   like ruff pre-existing violations)
3. Change the gate criteria → requires a governance discussion and update to this document

Option 2 is only available for non-critical gates. Tests, ruff (new violations), and
doc-vs-code failures cannot be deferred.

---

## Gate summary table

| Gate | Applies to | Deferrable? |
|------|-----------|------------|
| Test suite | All releases | No |
| Ruff lint | All releases | Only for pre-existing violations |
| Doc-vs-code | All releases | No |
| Closed-issue regression | Patch/minor | No |
| Version sync | All releases | No |
| CHANGELOG entry | All releases | Minor for trivial patches |
| README version sync | Major releases | No |
| Companion library tests | Coordinated release | No |
| Spec version verification | Companion library releases | No |
| **Pre-publish creator validation** | All releases (abbreviated for security patches) | No |
| **Post-publish eval (Stage 5)** | All releases | No — runs *after* upload, so it cannot block it; a finding sets the next patch's priority |
| **Downstream republish sweep (Stage 6)** | All releases | No — companions can be stale independently of this repo |

Both validation stages produce a document in `docs/evals/vX.Y.Z/`:
`CREATOR_VALIDATION.md` (Gate 10) and `POSTPUBLISH_EVAL.md` (Stage 5). **A release
is not finished until both exist**, whether or not either found anything.

---

## Related documents

- `docs/governance/RELEASE_CHECKLIST.md` — procedural checklist (should reference this document)
- `docs/governance/RELEASE_PLAYBOOK.md` — full release playbook
- `docs/governance/TECH_DEBT.md` — known gate-adjacent issues
