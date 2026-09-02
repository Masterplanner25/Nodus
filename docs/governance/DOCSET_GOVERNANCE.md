# Docset Governance

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document defines how the Nodus docset is governed: who owns which documents,
how documents get added or removed, and how conflicts between documents are resolved.

---

## Ownership

All documents in the Nodus core repo's `docs/` tree are maintained by the project
maintainer (Shawn Knight, Masterplanner25). Every companion docset is governed by
the same maintainer but may have different currency; the checkouts are indexed in
`docs/ecosystem/COMPANION_REPOS.md`. This section previously named two companion
paths by hand, when the ecosystem has fourteen.

---

## Precedence hierarchy

When two documents make conflicting claims, **the hierarchy in
[`DOCSET_INDEX.md § "Precedence rule"`](./DOCSET_INDEX.md) decides, and it is
stated there and only there.**

This section used to carry an "in brief" copy of that list, and the copy had
drifted: it dropped the top level (`DOCSET_INDEX.md` itself), so every remaining
level was numbered one lower than the real one. Two enumerations of one ordering
is the shape this repository documents most often; a precedence rule that
disagrees with itself is worse than a pointer.

---

## Adding a new document

Before creating a new document:

1. Check `DOCSET_INDEX.md` — the document may already exist
2. Identify the appropriate category and directory
3. Use the standard frontmatter (see below)
4. Add the document to `DOCSET_INDEX.md` under the correct section

`DOCSET_INDEX.md` is the one index that is maintained, and step 4 is the step
that matters: a document not listed there is outside the precedence rule.

### Standard frontmatter for new governing documents

```markdown
# Document Title

**Last reviewed:** YYYY-MM-DD, against X.Y.Z
**Status:** [Governing document | Working document | Reference document | Historical]
**Maintainer:** Shawn Knight (Masterplanner25)
```

**`Last reviewed`, not `Version`.** The field used to be
`**Version:** X.Y.Z (the release this doc was created for)`, which reads as a
claim about the present and goes stale the moment the next release cuts — four
governing documents sat stamped `3.0.2` nine minors after the fact, and a reader
cannot tell from that field whether the document was *checked* at 3.0.2 or merely
*written* then. A review date answers the question the reader actually has and
never needs updating to stay true. It is the same distinction
`tools/version_claims.json` is built around: **"X is current" goes stale, "as of
X" does not.**

Documents created during non-coding sessions (by AI tooling) must include a
marker that stays true after the commit:

```
<!-- Authored <YYYY-MM-DD> in a non-coding session and committed without review.
     Treat its claims as unverified; check them against the tree before relying
     on one. Remove this once someone has. -->
```

**Not "needs review before repo commit and push".** That was the original
wording, and it contradicted itself the moment the file was pushed — which is
exactly what happened: twenty-three documents carried it from 2026-05-29, twelve
of them were then edited up to seventeen more times, and the marker still asked
for a review "before commit" on files committed months earlier. A marker that is
false on its face gets read as noise, and then it is protecting nothing.

The wording above is a statement about provenance, not an instruction about a
commit that has already happened, so it stays accurate until the review it
describes actually occurs. Delete it when that happens; do not delete it to tidy
the header.

---

## Updating an existing document

When materially updating an existing document:

1. Update `**Last reviewed:**` — but **only if you actually checked the claims**.
   Editing one section is not a review of the document; move the date when the
   document as a whole has been read against the tree, and say what it was read
   against.
2. Add the unverified-provenance marker **only if the update was written without
   review** — see above. An AI-assisted update that *was* reviewed does not get
   one; applying it to every AI-assisted edit is precisely how twenty-three files
   came to carry a marker that was false on twelve of them.

The commit message is the record of what changed. There is no separate doc-change
log to update — see *Where doc changes are recorded* below.

---

## Removing or superseding a document

When a document is superseded:

1. Add a preamble to the old document pointing to the superseding document
2. Set its `**Status:**` to `Historical`
3. Update `DOCSET_INDEX.md` to reflect the new preferred path

Do not delete docs unless they are redundant and all links have been updated. Historical
docs serve as audit trail.

---

## Where doc changes are recorded

**In the commit, and in `DOCSET_INDEX.md`. There is no separate docset log.**

Three procedures in this document used to end by writing to
`DOCSET_CHANGELOG.md` and `DOCSET_STATUS_AUDIT.md`. Both were frozen on
2026-09-01 as dated records of the 2026-05-29 sweep, each carrying *"Do not
update it to match the tree — write a new record instead"*, and this document
was not updated to match — so a governing procedure instructed you to edit two
files that forbid being edited. `CHANGE_IMPACT_MATRIX.md` carried the same
instruction as a table row, and has been corrected too.

The instruction had already stopped being followed long before it became
contradictory: `DOCSET_CHANGELOG.md` holds exactly one entry, the sweep that
created it, across the nine releases since. A log nobody keeps records nothing
and provides false assurance that something is being tracked.

If a sweep of that scale happens again, **write a new dated record** and list it
in `DOCSET_INDEX.md`. That is what the frozen files are examples of. Do not
reopen them.

---

## Release-time docset responsibilities

Before every release, verify:
- `DOCSET_INDEX.md` is current
- New features in the release have corresponding guide or spec updates
- `LANGUAGE_STABILITY_INDEX.md` is updated for any stability changes
- `CHANGELOG.md` has an entry per user-visible change, added in the PR that made
  the change rather than swept up later — the release notes and
  `nodus_gate --closed-issues` both read it
- `nodus_gate --versions` has been re-run **after** the version bump, not only
  before it

---

## Companion library docset governance

The companion library docsets are governed by the same maintainer. Core governance docs
(positioning, stability, compatibility) are in the nodus-lang repo. Companion libraries
reference them rather than duplicating.

Each companion library must have at minimum:
- `README.md` — accurate, current, with known limitations documented
- `CHANGELOG.md` — version history
- `docs/governance/TECH_DEBT.md` — open items

Optional but recommended:
- Design docs in `docs/design/`
- Operational guide
- Contribution guide

---

## Doc-vs-code gate responsibility

The doc-vs-code gate (`tools/nodus_gate/`) is the mechanical enforcement of docset accuracy.
Maintainers are responsible for:
- Keeping the gate passing (`--all` must pass before release)
- Adding new allowlist entries in `.nodusgate-allow` for intentionally
  non-runnable blocks, and removing stale ones when blocks are fixed

**Know what it cannot see.** The gate checks that documented symbols exist
(`--static`) and that documented code runs (`--runtime`). It cannot check that a
*classification*, a *list*, or a *procedure* is still true — which is the whole
class of error the 2026-09-01 review of this document and six others found. Prose
that restates something the code owns is unguarded by construction, so the
defence is not to write it: **name the set once and point at it.** Where a claim
must appear in prose, register it in `tools/version_claims.json` so
`nodus_gate --versions` owns it.

---

## Related documents

- `docs/governance/DOCSET_INDEX.md` — document map and precedence
- `docs/governance/DOCSET_STATUS_AUDIT.md` — per-document status
- `docs/governance/DOCSET_CHANGELOG.md` — history of docset changes
- `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` — conflict resolution plan
