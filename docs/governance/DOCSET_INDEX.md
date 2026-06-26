<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Docset Index

**Version:** 3.0.2
**Status:** Governing document — the authoritative reader's guide to the Nodus docset
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document tells you where to find what, and which document takes precedence when
documents disagree. It is the entry point for any reader trying to understand Nodus.

---

## Precedence rule

When two documents make conflicting claims, the document higher in this list wins:

1. This document (DOCSET_INDEX.md)
2. Governing documents in `docs/governance/` (listed below)
3. Runtime truth documents in `docs/runtime/`
4. Language specification in `docs/language/`
5. Design decision records in `docs/design/`
6. Phase plans in `docs/governance/V*_PLAN.md` (describe process, not ground truth)
7. Guide documents in `docs/guide/` (user-facing; may lag the spec)
8. Historical documents (eval reports, release notes, migration guides)

---

## Start here by role

### "What is Nodus?"
→ `docs/governance/NODUS_POSITIONING.md`

### "What is stable and what can I rely on?"
→ `docs/governance/LANGUAGE_STABILITY_INDEX.md`
→ `docs/governance/COMPATIBILITY_MODEL.md`

### "How do I embed Nodus in my application?"
→ `docs/runtime/EMBEDDING.md`
→ `docs/guide/embedding-nodus.md`
→ `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md`

### "What does the runtime guarantee?"
→ `docs/runtime/EXECUTION_INVARIANTS.md`
→ `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md`

### "Is Nodus secure? What does the sandbox protect against?"
→ `docs/governance/SECURITY_POSTURE.md`

### "How does the language work?"
→ `docs/language/LANGUAGE_SPEC.md` (syntax, types, control flow)
→ `docs/runtime/ARCHITECTURE.md` (compiler and VM pipeline)
→ `docs/runtime/RUNTIME.md` (VM internals)

### "Why is Nodus the right execution substrate for the Infinity Algorithm?"
→ `docs/architecture/INFINITY_PATTERN_MAPPING.md`

### "How do workflows and coroutines work?"
→ `docs/runtime/WORKFLOWS.md`
→ `docs/runtime/ARCHITECTURE.md §Workflow Orchestration`

### "What is the companion library ecosystem?"
→ `docs/governance/LIBRARY_ECOSYSTEM.md` (architecture)
→ `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` (honest current state)

### "I want to audit or evaluate this runtime"
→ `docs/governance/AUDIT_INDEX.md` — six reusable audit prompts (architecture,
  runtime readiness, boundary integrity, user reality, capability, limits, security)

### "I want to contribute to Nodus"
→ `CONTRIBUTING.md`
→ `docs/governance/TECH_DEBT.md`
→ `docs/governance/RELEASE_GATES.md`
→ `docs/governance/RELEASE_PLAYBOOK.md`

### "How do I release a new version?"
→ `docs/governance/RELEASE_PLAYBOOK.md`
→ `docs/governance/RELEASE_GATES.md`
→ `docs/governance/RELEASE_CHECKLIST.md`
→ `docs/release.md`

---

## Governing documents (highest precedence)

| Document | Role |
|----------|------|
| `docs/governance/NODUS_POSITIONING.md` | Identity and boundary definition |
| `docs/governance/LANGUAGE_STABILITY_INDEX.md` | Surface-by-surface stability |
| `docs/governance/COMPATIBILITY_MODEL.md` | What breaks between versions |
| `docs/governance/SECURITY_POSTURE.md` | Security model and sandbox scope |
| `docs/governance/LIBRARY_ECOSYSTEM.md` | Ecosystem architecture and tiers |
| `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` | How to assess companion libraries |
| `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` | Current companion library state |
| `docs/governance/ECOSYSTEM_COVERAGE_ANALYSIS.md` | Coverage vs. 12 reference systems (strict, gaps + strengths) |
| `docs/governance/RELEASE_GATES.md` | What must pass before a release |
| `docs/governance/TECH_DEBT.md` | Open items and known limitations |
| `docs/governance/VERSIONING.md` | Semver policy |
| `docs/governance/STABILITY.md` | Stability summary (superseded by LANGUAGE_STABILITY_INDEX.md for detail) |
| `docs/governance/COMPATIBILITY.md` | Deprecation timeline (complement to COMPATIBILITY_MODEL.md) |

---

## Runtime truth documents

| Document | Role |
|----------|------|
| `docs/runtime/ARCHITECTURE.md` | Full compilation and execution pipeline |
| `docs/runtime/EXECUTION_INVARIANTS.md` | Guarantees the runtime makes |
| `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` | How and why execution fails |
| `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` | Operational guide |
| `docs/runtime/EMBEDDING.md` | Embedding API reference |
| `docs/runtime/RUNTIME.md` | VM internals |
| `docs/runtime/WORKFLOWS.md` | Workflow and task graph reference |
| `docs/runtime/BYTECODE.md` | Bytecode format overview |
| `docs/runtime/BYTECODE_REFERENCE.md` | Opcode reference |
| `docs/runtime/INSTRUCTION_SEMANTICS.md` | Opcode semantics |

---

## Language specification

| Document | Role |
|----------|------|
| `docs/language/LANGUAGE_SPEC.md` | Full language syntax and semantics |
| `docs/language/LANGUAGE_VISION.md` | Design philosophy |
| `docs/language/DESIGN.md` | Design decisions and principles |
| `docs/language/STYLE_GUIDE.md` | Nodus style guide |
| `docs/language/FORMAT.md` | Formatter behavior |

---

## Architecture documents

| Document | Role |
|----------|------|
| `docs/architecture/INFINITY_PATTERN_MAPPING.md` | Verified structural mapping of the Nodus runtime to the Infinity Algorithm pattern (execution layer vs. decision layer) |

---

## Design decision records

| Directory | Role |
|-----------|------|
| `docs/design/v4/` | v4.0 design decisions (Phase 0 + Phase 1 docs) |
| `docs/design/v3/` | v3.0 design decisions |

---

## Audit and status documents

| Document | Role |
|----------|------|
| `docs/governance/DOCSET_ALIGNMENT_AUDIT.md` | Core docset issues and gaps |
| `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` | Companion library docset issues |
| `docs/governance/DOCSET_STATUS_AUDIT.md` | Per-doc reconciliation status |
| `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` | Plan for fixing high-conflict docs |
| `docs/governance/DOCSET_CHANGELOG.md` | What changed in the docset over time |
| `docs/governance/INVARIANT_TEST_MAPPING.md` | Invariants mapped to tests |
| `docs/governance/TEST_GAP_BACKLOG.md` | Known test coverage gaps |

---

## User guide documents

| Document | Role |
|----------|------|
| `docs/guide/getting-started.md` | Entry point for new users |
| `docs/guide/types-and-values.md` | Type system guide |
| `docs/guide/error-handling.md` | Error handling patterns |
| `docs/guide/workflows-and-tasks.md` | Workflow and task guide |
| `docs/guide/modules-and-imports.md` | Module system guide |
| `docs/guide/embedding-nodus.md` | Embedding guide |
| `docs/guide/testing.md` | Test framework guide |
| `docs/guide/standard-library.md` | Standard library guide |
| `docs/guide/debugging.md` | Debugging guide |
| `docs/guide/library-entry-points.md` | Library entry point contract |

---

## Phase plans and cycle history

Phase plans (`V2_1_PLAN.md`, `V3_0_PLAN.md`, etc.) describe process and intent for their
cycle. They are **not ground truth** for the current state — always prefer the implementation
and the governing docs above.

Current active plan: `docs/governance/V4_0_PLAN.md`

---

## Companion library docsets

Each companion library has its own docs. The nodus-lang core does not maintain companion
library documentation; the companion repos are authoritative for their content.

| Library | Repo | Doc entry point |
|---------|------|-----------------|
| nodus-mcp | `C:\dev\nodus-mcp` | `nodus-mcp/README.md` |
| nodus-a2a | `C:\dev\nodus-a2a` | `nodus-a2a/README.md` |

For the ecosystem-level view (architecture, maturity, scope):
→ `docs/governance/LIBRARY_ECOSYSTEM.md`
→ `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md`

---

## Documents that are historical only

These documents capture completed work and should not be treated as authoritative for
the current state. They are preserved for audit trail purposes.

- `docs/governance/V2_1_PLAN.md` — completed
- `docs/governance/V3_0_PLAN.md` — completed
- `docs/governance/V3_1_PLAN.md` — completed (merged into v3.0.2)
- `docs/governance/RELEASE_NOTES_0.2.0.md` — historical
- `docs/governance/RELEASE_NOTES_1.0.0.md` — historical
- `docs/evals/v2.0.0/` through `docs/evals/v3.0.2/` — historical eval reports
- `docs/design/v3/` — completed design decisions
- `docs/migration/v2-to-v3.md` — historical migration guide
