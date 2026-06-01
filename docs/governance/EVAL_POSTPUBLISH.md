# Nodus — Post-Publish Eval Prompt

**Canonical template:** `docs/governance/EVAL_STAGE4_TEMPLATE.md`

This file is the POST-PUBLISH instance of the generalized Stage 4 eval
template. To run a post-publish eval:

1. Copy `EVAL_STAGE4_TEMPLATE.md` to a scratch location.
2. Fill Section 0 with:
   - **INSTALL SOURCE = POST-PUBLISH**
   - Install command: `pip install nodus-lang==X.Y.Z` (exact pinned version)
   - Working dir: empty, non-git, local-only (e.g. `C:\dev\nd testing\`)
   - Deliverable dir: `docs/evals/vX.Y.Z/`
3. Fill Section 4 with the change surface for this release.
4. Hand to a **fresh evaluator session** — one that did NOT do the release prep.

## What post-publish catches that pre-publish misses

- Resolved-version mismatch (wheel reports wrong version)
- Modules present in dev source but missing from the wheel
- PyPI metadata errors (wrong classifiers, missing deps, broken entry points)
- Any behavior difference between `pip install nodus-lang==X.Y.Z` and the
  local build that passed Gate 10

## Relationship to Gate 10

Gate 10 (`EVAL_PREPUBLISH.md`) is the **creator** validation run against the
local wheel before tagging. This post-publish eval is the **independent**
validation run against the PyPI artifact after tagging. Both use the same
template; they differ only in INSTALL SOURCE and evaluator identity.

Run Gate 10 → fix or file → tag → publish → run this eval → file any
packaging-path findings.

## Deliverables (same as template Section 6)

Four files to `docs/evals/vX.Y.Z/`:
- `EVAL_LOG.md`
- `NODUS_EVAL_REPORT.md`
- `NODUS_EVAL_RUBRIC.md`
- `NODUS_EVAL_BUGS.md`
