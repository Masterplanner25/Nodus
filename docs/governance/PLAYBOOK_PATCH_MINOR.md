# Playbook A: Patch and Minor Releases

**Scope:** vX.Y.Z+1 (patch) and vX.Y+1.0 (minor) releases
**Evidence base:** v2.0.0, v2.0.1, v2.1.0, v2.1.1, v3.0.1 (five cycles)
**Estimated total time:** 1-3 days (patch), 1-2 weeks (minor)

---

## When this playbook applies

- No breaking changes
- Scope is bug fixes, internal refactors, additive features, documentation
- Decisions are already settled (no design questions to resolve)

If breaking changes are in scope, switch to `PLAYBOOK_MAJOR.md`.

If a finding mid-cycle turns out to require a design decision, tag it
`phase:1-design`, file it for the next cycle, and proceed without it. Do
not let design work expand into the patch/minor release window.

---

## Session handoff methodology

Release cycles span multiple sessions. The session-to-session handoff
discipline matters as much as the within-session work. The pattern that
has produced 7 successful release cycles is:

### Per-session deliverables

Each session ends with one or more of the following:

1. **Chat session summary** — when the work happened in this chat
   interface (planning, design, eval, governance work). Captured from
   the chat itself: the decisions made, files created or staged, open
   follow-ups, and what the next session should pick up.

2. **Claude Code session summary** — when the work happened in Claude
   Code (implementation, fixes, tests, refactors). Captured from the
   Claude Code session itself, not reconstructed from memory. Includes
   commit hashes, files touched, tests run, and known follow-ups.

Both formats are first-class. Neither replaces the other. A cycle
typically has a mix: design conversations produce chat summaries, then
Claude Code sessions execute against the resulting specs and produce
their own summaries.

### Standing documentation updates from Claude Code sessions

Each Claude Code session that introduces a new pattern, command,
convention, or environmental fact updates the project's standing
documentation:

- **CLAUDE.md** — for patterns Claude Code needs every session (build
  commands, PYTHONPATH conventions, lint rules, PowerShell syntax
  quirks, GitHub API patterns, etc.). Updated in the same session
  that surfaces the pattern.
- **.claude/commands/*** — for repeatable workflows that warrant a
  named skill (file-bug, release-prep, milestone-transition, etc.).
  Created or updated in the same session that surfaces the workflow.

The discipline is: if a Claude Code session needed something the
session before didn't have, capture that delta before ending the
session. CLAUDE.md and skills compound across sessions; missing a
delta loses leverage.

### Why this matters

Without this discipline:

- Patterns are reinvented each session
- Environment-specific gotchas re-surface as bugs in the next session
- Session-to-session handoffs lose information
- The maintainer ends up re-explaining the same things

With this discipline:

- Each session inherits the accumulated wisdom of all prior sessions
- New collaborators (or the maintainer after a break) can pick up
  from CLAUDE.md and the session summaries
- The handoff doc for the next session is concrete and current

---

## Overview

Six stages in order. Stage 5 (independent eval) is optional for targeted security
patches; mandatory for all other releases. Stage 3 (creator validation) is required
for all releases; the abbreviated security-patch variant is documented in Stage 3.

1. **Docs audit** — catches drift before it ships
2. **Tiered fixes** — P0 blockers → P1 release-ready → P2 quality → P3 polish
3. **Pre-publish creator validation** — maintainer actively tries to break the language against a real wheel; fix everything fixable before uploading
4. **PyPI publish** — TestPyPI dry-run gate, then real PyPI
5. **Independent stress-test eval** — researcher mode, adversarial
6. **Issue filing and next-version planning** — eval findings become next cycle's input

---

## Stage 1 — Docs audit

**When to run:** at the start of the release window, before any code changes.

**Why it exists:** docs drift is the single most common finding across
five cycles. The audit catches it cheaply (1-2 hours) before it becomes
a post-release embarrassment.

**Inputs:**
- Full `docs/` tree
- Project root docs (`README.md`, `CHANGELOG.md`, `llms.txt`)
- The previous version's `CHANGELOG` entry (to spot stale claims)

**Outputs:**
- `DOCS_AUDIT_REPORT.md` with findings tiered P0/P1/P2/P3
- P0 = release blockers (wrong version strings, broken links, factual errors)
- P1 = should-fix-this-cycle (stale examples, missing docs for shipped features)
- P2 = nice-to-have (organizational improvements, clarity edits)
- P3 = cosmetic (typos, formatting)

**The prompt:** `DOCS AUDIT TASK.md` (in project root, capture to
`docs/governance/release-prompts/patch-minor/01_docs_audit.md` pending)

**Lessons from prior cycles:**
- Version string drift across docs is the single most common finding.
  Search every doc for the previous version string and confirm every
  occurrence is intentional.
- File paths in docs drift between releases. Always re-verify paths.
- JSON-LD blocks and structured metadata need version sync too — easy to
  miss because they're not visible in rendered docs.
- The README is read more than any other doc. Audit it last (after fixing
  other docs) so the README reflects the corrected state.
- `llms.txt` is the AI-crawler entry point — its version and key concepts
  list must match shipped behavior, not aspirational targets.

**Exit condition:** all P0 findings have a fix decided (either fix this
cycle or defer with justification). P1 findings tiered into Stage 2.

---

## Stage 2 — Tiered fixes

**When to run:** immediately after audit, before tagging.

**Four prompts** run in order: P0, P1, P2, P3. The tiering matters — P0
blockers must ship; P3 polish can defer.

**Inputs:**
- Audit findings from Stage 1
- Open GitHub issues on the release milestone
- Any bug reports filed since the last release

**Outputs:**
- Commits per tier (or per logical group within a tier)
- Tests for every code change (per the `CLAUDE.md` security boundary test
  rule and the project's standard test gate)
- `CHANGELOG.md [Unreleased]` section updated as fixes land

**The prompts:**
- `P0 BLOCKER FIXES.md` (project root, capture pending)
- P1, P2, P3 prompts: derived from P0 by adjusting tier (capture pending)

**Lessons from prior cycles:**
- P0 must include both content fixes AND infra (PyPI classifiers, package
  URLs, license metadata, classifier `Development Status`).
- For ambiguous code-example fixes, REMOVE rather than guess. A removed
  example is a known-empty state; a guessed example is a documented lie.
- `Development Status` classifier should match reality, not aspiration.
  v2.0.0 shipped `Production/Stable` and was downgraded to `Beta` in
  v2.0.1 because the eval found it wasn't ready.
- Within a tier, fix order is by blast radius: shared root causes first
  (so subsequent fixes don't conflict with their own dependencies).
- Test count grows during this stage. The v3.0.1 cycle added 67 new tests
  across four commits — well over the per-bug minimum.

**Exit condition:** all P0 and P1 fixes committed and pushed; test suite
green; `CHANGELOG.md [Unreleased]` accurately describes what shipped.

---

## Stage 3 — Pre-publish creator validation

**When to run:** after Stage 2 is complete and the test suite is green, before
building the release wheel. This stage runs against a built wheel, not dev source.

**Why it exists:** the independent stress-test eval (Stage 5) catches bugs after
users already have access to the broken version. Creator validation moves adversarial
testing to before the upload, when fixes are still cheap and the version number hasn't
been stamped on anything irreversible.

**Mode:** adversarial. The maintainer is not evaluating usability — they are actively
trying to find failures. The goal is to find every fixable bug before users encounter it.

**Protocol:**

1. Build the release candidate wheel: `python -m build`
2. Install it in a clean virtualenv:
   ```powershell
   python -m venv .venv-validation
   .venv-validation/Scripts/pip install dist/nodus_lang-X.Y.Z-py3-none-any.whl
   ```
3. Write 8–12 Nodus programs targeting the highest-complexity surfaces. Required
   categories (at minimum):
   - Closures and upvalue capture — nested closures, mutation through outer scope
   - Coroutines and channels — spawn/yield/recv sequences, closed-channel behavior
   - Error handling — try/catch/finally interactions, throw inside finally
   - Import system — multi-file imports, circular import detection, alias resolution
   - Operator and type edge cases — division by zero, nil coercion, integer vs float
   - Error messages — trigger each error category and verify the message is user-legible
   - Every quirk documented in `CLAUDE.md §"Nodus language quirks"` — any deviation
     from the documented behavior is a bug
   - At minimum one workflow or goal execution if the release touches orchestration
4. For each failure, apply the disposition rule:
   - **Fix it now** if: the root cause is clear, the fix is low regression risk, and
     it can be committed, tested, and the wheel rebuilt within the validation session.
     The fix ships in this version; add a regression test and CHANGELOG entry.
   - **File it now** if: it requires design work, carries regression risk, or is too
     large for the current release window. File a GitHub issue immediately with full
     repro, add `found-in:vX.Y.Z` label, and note it in the release announcement.
     See `docs/governance/ISSUE_RESPONSE_POLICY.md` for the response commitment.
5. Record results in `docs/evals/vX.Y.Z/CREATOR_VALIDATION.md` — a short file,
   even if everything passes. A clean run is documented evidence, not silence.

**For security patches (abbreviated variant):**
Scope the validation to the patched code path only. Write 3–5 programs specifically
targeting the security fix and any adjacent code paths it touches. Skip the full
category sweep. Record results in `CREATOR_VALIDATION.md` with the scope noted.

**Exit condition:**
- Every failure found is either committed-and-fixed or filed-as-an-issue. No
  undocumented failures.
- At least 8 programs executed (3 for security patches).
- Gate 1 (test suite) reruns and passes after any fix made in this stage.

---

## Stage 4 — PyPI publish

**When to run:** when P0 + P1 are committed and the test suite is green.
P2 and P3 may still be in flight; they ship in the next cycle if not
ready.

**Two hard gates:** TestPyPI verify, then real PyPI verify. Do not skip
TestPyPI for any release with new dependencies, new entry points, or new
package data. For pure bug-fix patches with no packaging changes,
TestPyPI may be skipped at maintainer discretion (v3.0.1 did this).

**Inputs:**
- Clean working tree
- Test suite green (`pytest tests/ -q`)
- `CHANGELOG.md [Unreleased]` content ready to promote
- PyPI token (retrieve from environment, never commit)

**Outputs:**
- Version bump in `src/nodus/support/version.py` AND `pyproject.toml`
  (these must match — `CLAUDE.md` enforces this as a hard rule)
- `CHANGELOG.md` `[Unreleased]` promoted to `[X.Y.Z] - YYYY-MM-DD`
- `git tag vX.Y.Z` pushed
- Built wheel and sdist on TestPyPI (if applicable)
- Built wheel and sdist on real PyPI
- GitHub release with CHANGELOG entry as the body

**The prompt:** `PYPI RELEASE.md` (project root, capture pending). Note:
the `release-prep` skill mechanizes this stage. Once the skill is
invoked, the prompt is largely automated.

**Lessons from prior cycles:**
- PyPI uploads are irreversible. The TestPyPI gate exists for a reason.
- Name availability check on PyPI must happen BEFORE building artifacts.
  Confirmed at the start of v2.0.0 and verified each release after.
- `--extra-index-url` is required when installing from TestPyPI to pull
  dependencies from real PyPI. The release prompt covers this.
- `nodus --version` after install from PyPI is the final smoke test. If
  it doesn't match the tag, something went wrong (most likely:
  `version.py` and `pyproject.toml` drifted).

### CHANGELOG diff check

Before locking the CHANGELOG entry for this release, diff stdlib
behavior against the previous version. The check is:

1. Identify all stdlib functions and CLI surfaces touched during this
   release cycle (including incidental changes from refactors,
   bug fixes, and dependency updates).
2. For each, verify the behavior change is captured in the CHANGELOG
   under the appropriate subsection (Added / Changed / Fixed /
   Removed / Deprecated).
3. If a behavior change is shipping but not documented, add it to the
   CHANGELOG before release. The discipline is: every behavior change
   ships in the CHANGELOG, even if discovered during release prep.

**Why this matters:** v3.0.2 shipped an undocumented improvement to
`strings.split` arity errors (from "Stack underflow" to a Nodus-voice
type error). It was a positive change; the omission was a
documentation gap, not a code gap. Caught by the v3.0.2 stress-test
eval. The diff check prevents recurrence.

**Practical approach:** Compare error messages and return values for
representative inputs against the previous shipped wheel. Where
behavior differs, confirm the CHANGELOG covers it.

**Exit condition:** PyPI page shows new version; `pip install
nodus-lang==X.Y.Z` works in a fresh environment; `nodus --version`
matches; GitHub release published with the matching tag.

---

## Stage 5 — Independent stress-test eval

**When to run:** within 1 week of PyPI publish, before any community
announcement of the new release.

**Why "independent":** the eval must be done by an agent (or session)
that did not participate in the release prep. Otherwise it confirms its
own assumptions. v3.0.0's eval was run in a fresh `C:\dev\nd testing\`
directory with a separate Claude Code session — this is the model.

**Mode:** researcher + stress test. The evaluator pretends to be a
senior engineer evaluating Nodus for adoption, doing depth, looking for
sharp corners. Not a first-impression review.

**Deliverables:** four files in the eval working directory, then moved to
`docs/evals/vX.Y.Z/`:
- `EVAL_LOG.md` — chronological evidence trail (no claim appears in
  reports without backing here)
- `NODUS_EVAL_REPORT.md` — narrative assessment, TL;DR, findings,
  migration audit, real-task experience, per-audience verdicts
- `NODUS_EVAL_RUBRIC.md` — 1-10 scoring across ~20 dimensions, weighted
  composite, comparison to prior baseline
- `NODUS_EVAL_BUGS.md` — filable issues with severity, subsystem, repro,
  expected vs actual, fix direction

**The prompt:** the v2.0.0 stress-test prompt is the original artifact
(capture pending). The v3.0.0 stress-test prompt (in `C:\dev\nd testing\`,
also pending capture) is the adapted version for major releases — for
patch/minor releases, use the v2.0.0 template and adapt for the specific
release's changes.

**Lessons from prior cycles:**
- `EVAL_LOG.md` is the evidence floor; every report claim cites it.
- The "Build something real" section in the eval prompt is the most
  useful part for next-version planning — surfaces undocumented gotchas
  the bug list misses.
- Severity calibration matters more than tone. CRITICAL means "this is
  broken in a way that blocks users." HIGH means "documented feature
  doesn't work as documented." Don't soften.
- For patches: the eval can be scoped to the patched surfaces only.
  v2.0.1 evaluated specifically the three CRITICAL fixes from the
  v2.0.0 eval, not a full re-run.
- v3.0.0 eval scored 6.45/10, up from v2.0.0's 5.52/10. The score is
  the right granularity for tracking cycle-over-cycle improvement. Don't
  obsess about absolute number, watch the trend.

**Exit condition:** all four deliverables produced; bugs filed (Stage 6);
eval directory moved to `docs/evals/vX.Y.Z/`.

---

## Stage 6 — Issue filing and next-version planning

**When to run:** same week as the eval.

**File every bug, even cosmetic ones.** Cosmetic findings are signal
about polish even when they don't block work. v3.0.0 eval filed 22
issues including 2 COSMETIC; both were resolved in v3.0.1.

**Use the `file-bug` skill** to keep issue shape consistent. Each issue
needs: BUG-NNN title, subsystem label, severity label, milestone routing,
repro, expected, actual, fix direction.

**Triage into next-version milestone vs deferred:**
- CRITICAL and HIGH from the eval → next patch release (vX.Y.Z+1) milestone
- MEDIUM → next minor release (vX.Y+1.0) milestone, or deferred to a
  major release if it requires design work
- LOW and COSMETIC → next release milestone unless they can't be batched

**Outputs:**
- One GitHub issue per finding, labeled and milestoned
- A new `VX_Y_Z_PLAN.md` if the next release scope warrants it
  (v3.0.1 didn't need one; the issues themselves were sufficient)
- Updates to `TECH_DEBT.md` for any process gaps the eval surfaced

**Lessons from prior cycles:**
- Some findings are architecture decisions, not bugs. Tag those for the
  appropriate major release, not the next patch.
- The `found-in:vX.Y.Z-eval` label helps track which findings came from
  which cycle. Useful for retrospectives.
- After two cycles of similar findings, capture the pattern in
  `TECH_DEBT.md` as a methodology rule. v3.0.0 surfaced the
  doc-vs-shipped reconciliation gap — that's now a hard gate for major
  releases.

**Exit condition:** every eval finding has a GitHub issue, every issue
has a milestone, the milestone for the next release is populated and
ready for Stage 1 of its own cycle.

---

## Anti-patterns specific to Playbook A

These have been hit and corrected; they should not be hit again:

- **Inflating the `Development Status` classifier** (v2.0.0 → v2.0.1
  downgrade). Match reality.
- **Shipping with stale version strings in non-code docs** (caught
  repeatedly by Stage 1). Verify every occurrence.
- **Skipping the eval because "it's just a patch"** (the v2.0.0 →
  v2.0.1 emergency patch did this for the security fix, and the next
  eval found that BUG-046 — the same class of issue in a different code
  path — also existed). Emergency patches still get a focused eval on
  the patched code path.
- **Treating cosmetic findings as not-worth-filing**. They're signal,
  not noise. File them, defer them if needed, but file them.

---

## Quickstart by release type

**Routine patch (vX.Y.Z+1):**
- Stage 1 (audit) → Stage 2 (P0 + P1, skip P2/P3 if no docs changes)
  → Stage 3 (creator validation, abbreviated to patched surfaces)
  → Stage 4 (PyPI, can skip TestPyPI for pure bug-fix patches)
  → Stage 5 (focused eval on patched surfaces)
  → Stage 6 (file findings)

**Feature release (vX.Y+1.0):**
- Full Stage 1-6 sequence. TestPyPI mandatory if new dependencies or
  packaging changes.

**Emergency security patch (e.g., v2.0.0 → v2.0.1):**
- Skip Stage 1 unless the security fix touches docs
- Stage 2 is the security fix only (and any closely-related test coverage)
- Stage 3 abbreviated: validate the patched code path only (3 programs minimum)
- Stage 4 with TestPyPI gate
- Stage 5 is a focused eval: only the patched code path and the security
  invariant. The full eval can wait for the next release.
- Stage 6 files any related findings the focused eval surfaces (this is
  how BUG-046 was caught for v2.1.1 after the v2.0.1 fix shipped).

---

## What this playbook does not cover

- Pre-release branching strategy. The project ships from `main` directly;
  no release branches. If that changes, the playbook needs revision.
- Community communication, announcements, social media. Downstream of
  "released to PyPI."
- Sponsored or commercial release coordination. The project is solo-
  maintained; if that changes, this playbook needs revision.

---

## When to update this playbook

After every cycle, check:
1. Did any stage fail in a way that suggests the procedure is wrong?
2. Did a new pattern emerge that should be captured?
3. Did a captured "lesson from prior cycles" turn out to be wrong?

If yes to any, revise. Revision happens between cycles, never during one.
