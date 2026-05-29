<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Docset Status Audit

**Date:** 2026-05-29
**Status:** Working document — reflects state after the 2026-05-29 documentation sweep
**Maintainer:** Shawn Knight (Masterplanner25)

This document records the reconciliation status of every significant document in the
Nodus core docset. Use this as the tracking reference for the ongoing documentation
maturity effort.

---

## Status key

| Status | Meaning |
|--------|---------|
| ✅ Current | Document is accurate and current as of 3.0.2 |
| 🟡 Partially reconciled | Document is mostly accurate; preamble or cross-reference added in this sweep |
| 🔄 New (this sweep) | Created in the 2026-05-29 documentation sweep |
| ❌ Needs action | Document has identified issues; not yet reconciled |
| 📚 Historical | Accurate for its time; not current. Read for audit trail only. |
| 🏗️ Stub/missing | Referenced from other docs; does not exist |

---

## Governing documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/governance/NODUS_POSITIONING.md` | 🔄 New | Created in this sweep |
| `docs/governance/LANGUAGE_STABILITY_INDEX.md` | 🔄 New | Supersedes STABILITY.md for surface-by-surface detail |
| `docs/governance/COMPATIBILITY_MODEL.md` | 🔄 New | Supersedes COMPATIBILITY.md for policy |
| `docs/governance/SECURITY_POSTURE.md` | 🔄 New | Created in this sweep |
| `docs/governance/TEST_STRATEGY.md` | 🔄 New | Created in this sweep |
| `docs/governance/RELEASE_GATES.md` | 🔄 New | Created in this sweep |
| `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` | 🔄 New | Created in this sweep |
| `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` | 🔄 New | Created in this sweep |
| `docs/governance/DOCSET_INDEX.md` | 🔄 New | Created in this sweep |
| `docs/governance/DOCSET_ALIGNMENT_AUDIT.md` | 🔄 New | Created in this sweep |
| `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` | 🔄 New | Created in this sweep |
| `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` | 🔄 New | Created in this sweep |
| `docs/governance/DOCSET_STATUS_AUDIT.md` | 🔄 New | This document |
| `docs/governance/DOCSET_CHANGELOG.md` | 🔄 New | Created in this sweep |
| `docs/governance/LIBRARY_ECOSYSTEM.md` | ❌ Needs action | nodus-a2a overclaim in Tier 3 section |
| `docs/governance/STABILITY.md` | 🟡 Partially reconciled | Accurate but thin; LANGUAGE_STABILITY_INDEX.md is the primary now |
| `docs/governance/COMPATIBILITY.md` | 🟡 Partially reconciled | Deprecation timeline; COMPATIBILITY_MODEL.md is the policy doc |
| `docs/governance/VERSIONING.md` | ✅ Current | Accurate; delegates to release.md for policy |
| `docs/governance/TECH_DEBT.md` | ✅ Current | Well-maintained; accurate as of 3.0.2 |
| `docs/governance/RELEASE_CHECKLIST.md` | ❌ Needs action | Pre-v1.0 CLI commands; missing doc-vs-code gate |
| `docs/governance/RELEASE_PLAYBOOK.md` | 🔍 Unverified | Assumed current; not audited in this sweep |
| `docs/governance/PLAYBOOK_PATCH_MINOR.md` | 🔍 Unverified | Assumed current; not audited |
| `docs/governance/PLAYBOOK_MAJOR.md` | 🔍 Unverified | Assumed current; not audited |
| `docs/governance/DEPRECATIONS.md` | 🔍 Unverified | Assumed current; not audited |
| `docs/governance/STDLIB_PHILOSOPHY.md` | 🏗️ Missing | Referenced from LIBRARY_ECOSYSTEM.md; does not exist |

---

## Runtime documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/runtime/ARCHITECTURE.md` | ✅ Current | Highly accurate; detailed |
| `docs/runtime/EXECUTION_INVARIANTS.md` | 🔄 New | Created in this sweep |
| `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` | 🔄 New | Created in this sweep |
| `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` | 🔄 New | Created in this sweep |
| `docs/runtime/EMBEDDING.md` | ✅ Current | Accurate; formatting is plain-text style not Markdown |
| `docs/runtime/RUNTIME.md` | 🔍 Unverified | Content appears accurate; not fully audited |
| `docs/runtime/WORKFLOWS.md` | 🔍 Unverified | Not audited in this sweep |
| `docs/runtime/TASK_GRAPHS.md` | 🔍 Unverified | Not audited |
| `docs/runtime/RUNTIME_EVENTS.md` | 🔍 Unverified | Not audited |
| `docs/runtime/BYTECODE.md` | 🔍 Unverified | Assumed accurate; not audited |
| `docs/runtime/BYTECODE_REFERENCE.md` | 🔍 Unverified | Assumed accurate; not audited |
| `docs/runtime/INSTRUCTION_SEMANTICS.md` | 🔍 Unverified | Assumed accurate; not audited |
| `docs/runtime/ARCHITECTURE_ANALYSIS.md` | 📚 Historical | Architecture analysis doc; may be superseded by ARCHITECTURE.md |
| `docs/runtime/SERVER_MODE.md` | 🔍 Unverified | Not audited; server mode is experimental |
| `docs/runtime/PROFILER.md` | 🔍 Unverified | Not audited |

---

## Language documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/language/LANGUAGE_SPEC.md` | ✅ Current | Well-maintained with stability annotations per section |
| `docs/language/LANGUAGE_VISION.md` | ✅ Current | Accurate; v4.0 "in-progress" section will need update post-launch |
| `docs/language/DESIGN.md` | 🔍 Unverified | Not audited |
| `docs/language/STYLE_GUIDE.md` | 🔍 Unverified | Not audited |
| `docs/language/FORMAT.md` | 🔍 Unverified | Not audited |

---

## Tooling documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/tooling/TESTING.md` | 🔍 Unverified | Not audited; test framework doc |
| `docs/tooling/DEBUGGING.md` | 🔍 Unverified | Not audited |
| `docs/tooling/DAP.md` | 🔍 Unverified | Not audited |
| `docs/tooling/DEBUGGER.md` | 🔍 Unverified | Not audited |
| `docs/tooling/EDITOR_SUPPORT.md` | 🔍 Unverified | Not audited |
| `docs/tooling/PACKAGE_MANAGER.md` | 🔍 Unverified | Not audited |
| `docs/tooling/LSP.md` | 🔍 Unverified | Not audited |
| `docs/tooling/REPL.md` | 🔍 Unverified | Not audited |
| `docs/tooling/PROJECTS.md` | 🔍 Unverified | Not audited |

---

## Guide documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/guide/getting-started.md` | 🔍 Unverified | Entry point; should be accurate |
| `docs/guide/types-and-values.md` | 🔍 Unverified | |
| `docs/guide/error-handling.md` | 🔍 Unverified | |
| `docs/guide/workflows-and-tasks.md` | 🔍 Unverified | |
| `docs/guide/modules-and-imports.md` | 🔍 Unverified | |
| `docs/guide/embedding-nodus.md` | 🔍 Unverified | |
| `docs/guide/testing.md` | 🔍 Unverified | |
| `docs/guide/standard-library.md` | 🔍 Unverified | |
| `docs/guide/debugging.md` | 🔍 Unverified | |
| `docs/guide/library-entry-points.md` | 🔍 Unverified | |

---

## Top-level documents

| Document | Status | Notes |
|----------|--------|-------|
| `README.md` | ❌ Needs action | JSON-LD version says 2.1.0; current is 3.0.2 |
| `CHANGELOG.md` | ✅ Current | Well-maintained |
| `pyproject.toml` | ✅ Current | Accurate |
| `docs/release.md` | 🔍 Unverified | Not audited |

---

## Historical and phase documents

| Document | Status | Notes |
|----------|--------|-------|
| `docs/governance/V2_1_PLAN.md` | 📚 Historical | Completed cycle |
| `docs/governance/V3_0_PLAN.md` | 📚 Historical | Completed cycle |
| `docs/governance/V3_1_PLAN.md` | 📚 Historical | Completed cycle |
| `docs/governance/V4_0_PLAN.md` | ✅ Current | Active cycle plan |
| `docs/governance/V4_0_PHASE3_RUNBOOK.md` | 🔍 Unverified | |
| `docs/governance/EVOLUTION.md` | 📚 Historical | |
| `docs/governance/FREEZE_PROPOSAL.md` | 📚 Historical | v1.0 freeze decisions; archival |
| `docs/design/v3/` | 📚 Historical | v3 design decisions; completed |
| `docs/design/v4/` | ✅ Current | Active design docs |
| `docs/evals/v2.0.0/` through `v3.0.2/` | 📚 Historical | Eval history |
| `docs/governance/RELEASE_NOTES_*.md` | 📚 Historical | |
| `docs/migration/v2-to-v3.md` | 📚 Historical | |
| `docs/migration/v3-to-v4.md` | 🔍 Unverified | May be draft/placeholder |

---

## Governance documents: new count

Documents created in the 2026-05-29 sweep:
- `NODUS_POSITIONING.md`
- `LANGUAGE_STABILITY_INDEX.md`
- `COMPATIBILITY_MODEL.md`
- `SECURITY_POSTURE.md`
- `TEST_STRATEGY.md`
- `RELEASE_GATES.md`
- `ECOSYSTEM_MATURITY_RUBRIC.md`
- `ECOSYSTEM_READINESS_ASSESSMENT.md`
- `ECOSYSTEM_DOCSET_AUDIT.md`
- `DOCSET_INDEX.md`
- `DOCSET_ALIGNMENT_AUDIT.md`
- `HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md`
- `DOCSET_STATUS_AUDIT.md`
- `DOCSET_CHANGELOG.md`
- `INVARIANT_TEST_MAPPING.md`
- `TEST_GAP_BACKLOG.md`

Runtime docs created:
- `EXECUTION_INVARIANTS.md`
- `FAILURE_AND_DEGRADATION_MODEL.md`
- `OPERATOR_OR_EMBEDDER_RUNBOOK.md`
