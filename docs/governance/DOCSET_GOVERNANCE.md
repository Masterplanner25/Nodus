<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Docset Governance

**Version:** 3.0.2
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document defines how the Nodus docset is governed: who owns which documents,
how documents get added or removed, and how conflicts between documents are resolved.

---

## Ownership

All documents in the Nodus core repo (`C:\dev\Coding Language\docs\`) are maintained
by the project maintainer (Shawn Knight, Masterplanner25). The companion library docsets
(`C:\dev\nodus-mcp\docs\`, `C:\dev\nodus-a2a\docs\`) are governed by the same maintainer
but may have different currency.

---

## Precedence hierarchy

When two documents make conflicting claims, the hierarchy in `DOCSET_INDEX.md` determines
which is authoritative. In brief:

1. Governing documents (`docs/governance/`)
2. Runtime truth documents (`docs/runtime/`)
3. Language specification (`docs/language/`)
4. Design decision records (`docs/design/`)
5. Phase plans (`docs/governance/V*_PLAN.md`)
6. Guide documents (`docs/guide/`)
7. Historical documents

---

## Adding a new document

Before creating a new document:

1. Check `DOCSET_INDEX.md` and `DOCSET_STATUS_AUDIT.md` — the document may already exist
2. Identify the appropriate category and directory
3. Use the standard frontmatter (see below)
4. Add the document to `DOCSET_INDEX.md` under the correct section
5. Add a note to `DOCSET_CHANGELOG.md`

### Standard frontmatter for new governing documents

```markdown
# Document Title

**Version:** X.Y.Z (the release this doc was created for)
**Status:** [Governing document | Working document | Reference document | Historical]
**Maintainer:** Shawn Knight (Masterplanner25)
```

Documents created during non-coding sessions (by AI tooling) must include:
```
<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->
```

---

## Updating an existing document

When materially updating an existing document:

1. Update the `**Version:**` field to the current release
2. Add the Codex note if the update was AI-assisted
3. Add a note to `DOCSET_CHANGELOG.md`
4. Update `DOCSET_STATUS_AUDIT.md` status

Minor corrections (typos, formatting) do not require `DOCSET_CHANGELOG.md` entries.

---

## Removing or superseding a document

When a document is superseded:

1. Add a preamble to the old document pointing to the superseding document
2. Mark it `📚 Historical` in `DOCSET_STATUS_AUDIT.md`
3. Add a note to `DOCSET_CHANGELOG.md`
4. Update `DOCSET_INDEX.md` to reflect the new preferred path

Do not delete docs unless they are redundant and all links have been updated. Historical
docs serve as audit trail.

---

## Release-time docset responsibilities

Before every release, verify:
- `DOCSET_INDEX.md` is current
- New features in the release have corresponding guide or spec updates
- `LANGUAGE_STABILITY_INDEX.md` is updated for any stability changes
- `CHANGELOG.md` (code) and `DOCSET_CHANGELOG.md` (docs) both have entries

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
It tests that documented symbols exist and code examples run. Maintainers are responsible for:
- Keeping the gate passing (`--all` must pass before release)
- Adding new allowlist entries for intentionally non-runnable blocks
- Removing stale allowlist entries when blocks are fixed

---

## Related documents

- `docs/governance/DOCSET_INDEX.md` — document map and precedence
- `docs/governance/DOCSET_STATUS_AUDIT.md` — per-document status
- `docs/governance/DOCSET_CHANGELOG.md` — history of docset changes
- `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` — conflict resolution plan
