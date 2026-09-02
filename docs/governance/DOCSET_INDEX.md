# Docset Index

**Last reviewed:** 2026-09-01, against 5.9.0
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

**Level 2 is `docs/governance/` — the whole directory, not only what is tabled below.**
That distinction is new on 2026-09-01, and it was not pedantry: the rule read
*"governing documents in `docs/governance/` (listed below)"*, and **32 documents in that
directory were not listed**, including four governing ones. `DOCSET_GOVERNANCE.md` —
which defines how this docset is governed and prescribes the frontmatter every other
document uses — was among them, so the precedence rule did not reach the document that
describes it. The tables below are now much closer to complete, but read them as a map
rather than as the definition of what has precedence.

**A precedence rule is only worth invoking where currency is maintained.** Two governing
documents have been found carrying superseded content under their own authority:
`NODUS_POSITIONING.md` held the pre-D1 positioning for nine releases, and
`COMPATIBILITY_MODEL.md` recorded the companion dependency cap that had already made
5.0.0 unadoptable. Check a document's `Last reviewed:` before letting it win a conflict.

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
→ `docs/governance/AUDIT_INDEX.md` — **nine** reusable audit prompts (architecture,
  runtime readiness + bootstrap, boundary integrity, user reality, capability, limits,
  security model, infinity runtime, real-world capability)
→ `docs/governance/EXTERNAL_AUDIT_LEDGER.md` — verdicts on audits run *against* Nodus.
  **Verify a finding before acting on it**; Audit 01 was wrong in five places, all of
  them negative findings

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
| `docs/governance/DOCSET_GOVERNANCE.md` | How the docset is governed: frontmatter, adding/superseding a document, where doc changes are recorded |
| `docs/governance/ECOSYSTEM_BOUNDARY.md` | Where the ecosystem ends; membership and distribution |
| `docs/governance/STDLIB_PHILOSOPHY.md` | Why capabilities stay narrow |
| `docs/governance/COMPANION_LIBRARY_CONTRACT.md` | What a companion must satisfy |
| `docs/governance/CHANGE_IMPACT_MATRIX.md` | What else has to move when you change X |
| `docs/governance/ISSUE_RESPONSE_POLICY.md` | How issues are triaged and answered |

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

## Other document trees

The categories above are not the whole `docs/` tree. Also present, and outside the
precedence list until 2026-09-01:

| Directory | Role |
|-----------|------|
| `docs/security/` | `SECURITY_MATRIX.md` — the security test matrix |
| `docs/ecosystem/` | Companion roster, per-repo detail, and incubator specs |
| `docs/evals/` | Three documents per release (creator validation, post-publish, downstream sweep) |
| `docs/migration/` | Per-release migration guides |
| `docs/onboarding/`, `docs/policy/`, `docs/projects/`, `docs/tooling/` | Supporting material |

---

## Architecture documents

| Document | Role |
|----------|------|
| `docs/architecture/INFINITY_PATTERN_MAPPING.md` | Verified structural mapping of the Nodus runtime to the Infinity Algorithm pattern (execution layer vs. decision layer) |

---

## Design decision records

| Directory | Role |
|-----------|------|
| `docs/design/v6/` | v6.0 proposals — **open**; record equality (#545) is the live one |
| `docs/design/workflow-dsl/` | The workflow-DSL cluster, decided 2026-08-26 |
| `docs/design/v5/` | v5 design decisions — **decided and shipped**, not proposals |
| `docs/design/v4/` | v4.0 design decisions (Phase 0 + Phase 1 docs) |
| `docs/design/v3/` | v3.0 design decisions |

`docs/design/v5/` was labelled *"not decided; each states its open decisions"* until
2026-09-01. Every one of them shipped — the capability policy (#405) and the goal
stopping condition (#409) in 5.0.0, cancellation (#395) in 5.7.0. Read them as records.

---

## Audit and status documents

| Document | Role |
|----------|------|
| `docs/governance/AUDIT_INDEX.md` + the nine `AUDIT_*.md` | Reusable audit prompts |
| `docs/governance/EXTERNAL_AUDIT_LEDGER.md` | Verdicts on audits run against Nodus |
| `docs/governance/MATURITY_CHECKLIST.md` | Maturity score and re-score |
| `docs/governance/TEST_STRATEGY.md` | Test suite organisation and standards |
| `docs/governance/TEST_GAP_BACKLOG.md` | Known test coverage gaps |
| `docs/governance/FREEZE_PROPOSAL.md` | Opcode freeze and extension proposals |
| `docs/governance/GENERAL_PURPOSE_TRAJECTORY.md` | Dated v4.0.0 baseline; **not maintained** |

**Five documents here are frozen or closed. Do not update them to match the tree:**

| Document | State |
|----------|-------|
| `docs/governance/DOCSET_ALIGNMENT_AUDIT.md` | Dated record of the 2026-05-29 sweep |
| `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` | Dated record of the 2026-05-29 sweep |
| `docs/governance/DOCSET_STATUS_AUDIT.md` | Dated record of the 2026-05-29 sweep |
| `docs/governance/DOCSET_CHANGELOG.md` | Dated record; **one entry in nine releases** |
| `docs/governance/HIGH_CONFLICT_DOC_RECONCILIATION_PLAN.md` | **Closed** — all seven conflicts verified resolved 2026-08-07. Not a to-do list |

`INVARIANT_TEST_MAPPING.md` is **superseded**: the mapping is
`tools/invariant_coverage.json`, checked by `nodus_gate --invariants`.

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

**There is no active plan document.** `V4_0_PLAN.md` was listed as the current one
until 2026-09-01; v4.0 shipped in June and there has been no V5 plan — the cycles since
have been driven by `CHANGELOG.md`'s `[Unreleased]` section and the issue tracker, which
is where to look for what is in flight. All four `V*_PLAN.md` files are history.

---

## Companion library docsets

Each companion library has its own docs. The nodus-lang core does not maintain companion
library documentation; the companion repos are authoritative for their content.

**The roster is `docs/ecosystem/README.md`** — it lists every first-party package and
is the source for the count. Checkout paths, test commands, publish paths and per-repo
gotchas are in `docs/ecosystem/COMPANION_REPOS.md`.

This section listed two companions by hand until 2026-09-01. There are fourteen with
their own docsets, and a package with no row in `docs/ecosystem/README.md` is invisible
twice over — `nodus-a2a-wire` and `nodus-workflow-ai` had none, so the documented
procedure for counting the ecosystem returned 35 where the answer was 37.

For the ecosystem-level view (architecture, maturity, scope):
→ `docs/governance/LIBRARY_ECOSYSTEM.md`
→ `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md`
→ `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md`
→ `docs/governance/ECOSYSTEM_BOUNDARY.md`

---

## Documents that are historical only

These documents capture completed work and should not be treated as authoritative for
the current state. They are preserved for audit trail purposes.

- `docs/governance/V2_1_PLAN.md`, `V3_0_PLAN.md`, `V3_1_PLAN.md`, `V4_0_PLAN.md` — all completed
- `docs/governance/RELEASE_NOTES_0.2.0.md`, `RELEASE_NOTES_1.0.0.md` — historical
- `docs/governance/GENERAL_PURPOSE_TRAJECTORY.md` — a dated v4.0.0 baseline
- **`docs/evals/` — every directory below the newest is historical.** They are a record
  of what each release was validated against, not a claim about the present. Do not
  update one; the current release writes its own three documents
- `docs/design/v3/`, `docs/design/v4/`, `docs/design/v5/` — completed design decisions
- `docs/migration/v2-to-v3.md` — historical migration guide

The eval line named `v2.0.0` through `v3.0.2` until 2026-09-01, when there are 27 eval
directories. Naming a range means re-editing it every release; naming the rule does not.
