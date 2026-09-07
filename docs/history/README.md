# Dated records

Documents that said what was true on a particular day. **None of them is
maintained, and none should be updated to match the tree** — several carry that
instruction in their own header. If the tree has moved on, the right response is
to write a new record, not to edit an old one into agreement.

They live here because `docs/governance/` had grown to 63 documents, which made
it hard to tell what governs from what merely happened. A record of a finished
sweep is not policy.

## What is here

| | |
|---|---|
| `docset-sweep-2026-05-29/` | The four records of that sweep: the alignment audit, the status audit, the docset changelog, and the ecosystem docset audit. All four carry the "do not update" banner. |
| `plans/` | Superseded version plans — v2.1, v3.0, v3.1, v4.0, and the v4.0 phase-3 runbook. The live one is `governance/V6_0_PLAN.md`. |
| `release-notes/` | Release notes for 0.2.0 and 1.0.0. Current history is `CHANGELOG.md`. |
| `HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` | Closed 2026-08-07, all seven conflicts resolved. **Not a to-do list** — its status flags said "ACTION REQUIRED" for months after the work landed, because the tracker was maintained separately from it. |
| `ECOSYSTEM_90_DAY_CHECKLIST.md` | Complete; the coordinated launch ran 2026-06-10. |
| `ECOSYSTEM_COVERAGE_ANALYSIS.md` | Coverage against 12 reference systems, pinned to v4.0.7. |
| `CORPUS_SYNTHESIS.md` | The 2026-08-17/18 research-corpus sweep against 5.0.4, which filed #465–#494. |
| `INVARIANT_TEST_MAPPING.md` | Superseded by `tools/invariant_coverage.json`. It cited 13 test files, **six of which did not exist**, four under a ✅ meaning "a test exists that would fail on violation". A prose coverage table cannot be checked against the filesystem, which is why the replacement is a manifest a gate reads. Do not restore a prose table. |

## Why the paths inside these records were not rewritten

Moving a document and updating everything that points at it is ordinary
housekeeping. Rewriting the paths *inside* a dated record is not: the record is
a statement about a tree that existed on a given day, and `docs/governance/V2_1_PLAN.md`
is where that file was when the sweep saw it. Editing it to the current path
would make the record claim something that was never true.

So the sweep records and the superseded plans keep their original path text.
Where a document links to something still live, the **markdown link** was
repointed so it resolves — a link is navigation, not a claim — but prose naming
an old location was left alone.

The same reasoning is why `CHANGELOG.md` was not touched: its entries describe
releases that happened, and one of them names `docs/governance/V3_1_PLAN.md`
because that is where the file was at the time.
