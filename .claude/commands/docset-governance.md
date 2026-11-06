---
description: Nodus documentation governance rules, what past docset reviews found, and longer notes on governance and staged-flip files. Read before editing governing docs.
---

# Documentation governance

> Moved out of the root `CLAUDE.md` on 2026-11-05 so it loads on demand. "This file" in the text
> below may mean the root file as it was. A section it names may now be in another file:
> release rules in `.claude/commands/release-sequence.md`, the bug shape in
> `.claude/commands/recurring-bug-shape.md`, embedding in `.claude/commands/nodus-embedding.md`.

## Documentation governance

The governing docset layer was established in a 2026-05-29 sweep. Key rules:

- **`docs/governance/DOCSET_INDEX.md`** — the reader entry point and precedence list.
  When docs conflict, DOCSET_INDEX.md defines which wins.
- **`docs/history/docset-sweep-2026-05-29/DOCSET_ALIGNMENT_AUDIT.md`** — 14 findings from that sweep.
- **`docs/history/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`** — **closed.** All
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

## Longer notes on key files

| What | Where |
|------|-------|
| Staged next-major readiness | `nodus check --staged` — what in a project breaks at the next major, from source. Implementation `src/nodus/tooling/staged_readiness.py`; design `docs/design/v6/01-readiness.md`. **Four of the five flips are answerable statically and the fifth is not**, so the report names every flip with its status and a clean run says *nothing found in what was checked*, never *ready* |
| Staged-flip warnings | `src/nodus/support/staging.py` — `StagedFlipWarning` and `warn_staged_flip()`. A `DeprecationWarning` subclass so an embedder's filters still catch it, and a distinct category so the CLI can unsuppress **only** the warnings a user must act on before the major. Use it for a registered flip; a surface merely going away stays a plain `DeprecationWarning` |
| Staged next-major register | `src/nodus/support/staged_flips.json` — every promise this tree makes about 6.0.0, each with its issue, the release its warning shipped in, whether that warning reaches a CLI user, and the count of sites it owns. Checked by `nodus_gate --flips`; each site carries a `# v6-flip: <name>` marker. **In the package, not `tools/`**, because `nodus check --staged` ships and reads the same file. Reasoning and open decisions: `docs/governance/V6_0_PLAN.md` |
| Audit prompt index | `docs/audits/AUDIT_INDEX.md` — 9 reusable audit prompts (architecture, runtime readiness + bootstrap, boundary integrity, user reality, capability, limits, security model, infinity runtime, real-world capability) |
| External audit ledger | `docs/governance/EXTERNAL_AUDIT_LEDGER.md` — verdicts on audits run *against* Nodus by outside readers. **Verify a finding before acting on it**; Audit 01 was wrong in 5 places, all negative findings |
| v5 design docs | `docs/design/v5/` — numbered, one per design question, each headed with its issue and a **Status:** line saying whether it shipped or is a proposal. Start with `00-domain-statement.md` (what Nodus is for). **Do not enumerate them here**: this cell listed `00`-`04` while the directory held `00`-`08`, stale by four, which is the same enumeration-vs-pointer failure the governance section describes |
| 6.0.0 migration guide | `docs/migration/v6.0-staged-flips.md` — all five staged flips, what each costs and how to fix it. #174 carries the procedure, verified against a parked run. **`docs/migration/*.md` is in the doc gate's scan**, so its examples run and its `nodus-expect=output` blocks are compared |
| **Companion repos (all 14)** | `docs/ecosystem/COMPANION_REPOS.md` — checkout paths, test commands, publish paths, per-repo gotchas. Indexed under **Companion repositories** below |
