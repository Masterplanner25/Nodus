<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Docset Changelog

This document records significant documentation changes across releases. It is distinct
from `CHANGELOG.md` (which records code changes) — this tracks documentation governance
changes: new governing docs, major reconciliations, and policy updates.

---

## 2026-05-29 — Documentation maturity sweep

**Scope:** Full docset audit and governing layer creation.

### New documents created

**Governing layer:**
- `docs/governance/NODUS_POSITIONING.md` — identity and boundary definition
- `docs/governance/LANGUAGE_STABILITY_INDEX.md` — surface-by-surface stability index
- `docs/governance/COMPATIBILITY_MODEL.md` — compatibility policy (supersedes COMPATIBILITY.md for policy)
- `docs/governance/SECURITY_POSTURE.md` — security model and sandbox scope
- `docs/governance/TEST_STRATEGY.md` — test suite organization and standards
- `docs/governance/RELEASE_GATES.md` — consolidated release gate definitions
- `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` — vocabulary for assessing companion libraries
- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — current companion library state
- `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` — companion library docset findings
- `docs/governance/DOCSET_INDEX.md` — reader-facing docset map and precedence rules
- `docs/governance/DOCSET_ALIGNMENT_AUDIT.md` — core docset issues and gaps
- `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` — plan for fixing high-conflict docs
- `docs/governance/DOCSET_STATUS_AUDIT.md` — per-document reconciliation status
- `docs/governance/DOCSET_CHANGELOG.md` — this document

**Invariant and test governance:**
- `docs/governance/INVARIANT_TEST_MAPPING.md` — invariants mapped to tests
- `docs/governance/TEST_GAP_BACKLOG.md` — known test coverage gaps

**Runtime truth:**
- `docs/runtime/EXECUTION_INVARIANTS.md` — what the runtime guarantees
- `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` — how and why execution fails
- `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` — operational guide

### Issues identified but not yet resolved

The following issues were identified in the sweep and are recorded for follow-up:

1. `README.md` JSON-LD version says 2.1.0 (current: 3.0.2) — fix before next release
2. `LIBRARY_ECOSYSTEM.md` nodus-a2a Tier 3 entry overclaims v0.1 scope — fix before public ecosystem discussion
3. `RELEASE_CHECKLIST.md` uses pre-v1.0 CLI commands — fix before next release
4. `STDLIB_PHILOSOPHY.md` referenced but missing — create stub before v4.0 release
5. Preambles needed on `STABILITY.md` and `COMPATIBILITY.md` to point to new governing docs

### Companion library issues identified

1. `nodus-a2a/pyproject.toml` missing authors, classifiers, license, readme metadata
2. `nodus-a2a` has no `docs/governance/TECH_DEBT.md`
3. `nodus-a2a` README auth warning should be more prominent
4. nodus-mcp: CLAUDE.md says "MCP 2025-11-25 spec" but README says "2026-07-28 RC" — verify CHANGELOG accuracy

---

## Prior history

Documentation changes prior to 2026-05-29 are recorded in `CHANGELOG.md` as part of
the code release notes. The DOCSET_CHANGELOG.md begins tracking doc-specific changes
from this date.
