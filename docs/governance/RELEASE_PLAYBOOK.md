# Nodus Release Playbook

**Last validated:** 2026-05-25
**Releases this playbook has shipped:** v2.0.0, v2.0.1, v2.1.0, v2.1.1, v3.0.0, v3.0.1
**Maintainer:** Shawn Knight (solo)

---

## Purpose

Two release patterns have been proven across six cycles. This document is the
entry point: it tells you which pattern applies to the release you're planning
and points you at the right detailed playbook.

This is not a procedure to follow blindly. It's a working pattern that
emerged from doing the work, captured so the next cycle doesn't have to
re-derive the structure.

---

## Decision tree

**Does this release have breaking changes or new language semantics?**

- **No** → use **Playbook A: patch and minor releases**
  (`docs/governance/PLAYBOOK_PATCH_MINOR.md`)
- **Yes** → use **Playbook B: major releases**
  (`docs/governance/PLAYBOOK_MAJOR.md`)

A breaking change is anything that requires existing user code to be modified
to keep working. New stdlib functions, internal refactors, bug fixes, and
documentation updates are NOT breaking. New syntax that's strictly additive
(opt-in) is NOT breaking. Changes to default behavior, removed functions,
changed function signatures, changed semantics of existing operators —
those ARE breaking.

When in doubt, ask: "will a working v(N-1) program produce different
behavior in vN without code changes?" If yes, breaking. If no, not breaking.

---

## How the two playbooks differ

**Playbook A** runs a five-stage cycle: docs audit → tiered fixes → PyPI
publish → independent stress-test eval → issue filing and next-version
planning. All five stages happen in roughly the order listed, in a single
release window. Evidence base: five cycles.

**Playbook B** runs a six-phase cycle: Phase 0 decisions → Phase 1 design
docs → Phase 2 non-breaking fixes → Phase 3 breaking changes → Phase 4 docs
sweep → Phase 5 release. The phases happen in strict order, and Phase 0 and
Phase 1 happen weeks before the release window in a separate planning
conversation. Evidence base: one cycle (v3.0.0 + v3.0.1 patch).

The fundamental difference: Playbook A treats execution as the primary work,
with prompt artifacts produced in the moment. Playbook B treats design as
the primary work, with execution following pre-written specs. Major
releases need design upfront because breaking changes are decisions, not
just code. Patch and minor releases don't need design phases because the
decisions are already settled.

---

## Supporting infrastructure

Both playbooks depend on three pieces of infrastructure that aren't
prompts. These are the layers that let the playbooks be short rather
than self-contained.

### 1. `CLAUDE.md` (project root)

Standing context that Claude Code reads on every session. Captures
conventions, file locations, command patterns, and project-specific
invariants. The current version captures: how to run dev code with
`PYTHONPATH`, version sync requirements, GitHub API access (no `gh` CLI),
guide file testing standard, security boundary test rule.

**Updated between cycles**, not within them. After a cycle, review the
working conversation for patterns that repeated more than twice. Those
patterns belong in `CLAUDE.md`. The current `CLAUDE.md` was distilled from
the v2.1 and v3.0 cycles by asking Claude Code to review the conversation
for repeated context. Same approach works going forward.

### 2. Skills (`.claude/commands/`)

Mechanize high-frequency operations so they don't need to be re-explained
each cycle. Current skills:

- **`file-bug`** — files GitHub issues with the project's standard shape
  (severity labels, subsystem labels, milestone routing). Used during
  stress-test evals and during any cycle that surfaces multiple findings.
- **`release-prep`** — walks the version-bump + tag + build + upload
  sequence. Used at Stage 3 of Playbook A and Phase 5 of Playbook B.

**New skills get written when an operation repeats across cycles.** If
the same multi-step procedure has to be re-explained three times, it
becomes a skill on the third occurrence.

### 3. Governance docs (`docs/governance/`)

The plan documents (`V2_1_PLAN.md`, `V3_0_PLAN.md`, future `V3_1_PLAN.md`)
serve as per-cycle working documents. They live in this directory,
intentionally untracked or tracked depending on the cycle. They capture
scope, phase ordering, risk register, open questions, and decision logs.

`TECH_DEBT.md` and `COMPATIBILITY.md` are the cross-cycle persistent
state. Updated during cycles when relevant findings emerge.

For major releases, the design docs under `docs/design/vN/` are part of
this infrastructure — they're the falsifiable contracts that Phase 2-5
work executes against. Eval cycles validate them by treating
"doc says X, implementation does Y" as a specific finding category.

---

## Cycle naming convention

- **Patch:** vX.Y.Z+1 — Playbook A, fast turnaround, 1-3 days end-to-end
- **Minor:** vX.Y+1.0 — Playbook A, 1-2 weeks end-to-end
- **Major:** vX+1.0.0 — Playbook B, 2-6 weeks for design + execution + release

For emergency security patches (v2.0.0 → v2.0.1, v2.1.0 → v2.1.1), use
Playbook A but skip stages that don't apply (typically: skip the docs
audit because the only change is a security fix, run an abbreviated eval
focused on the patched code path).

---

## What this playbook does NOT do

- Replace the per-cycle planning conversation. Major releases especially
  need a Phase 0 conversation that resolves design questions before any
  code work happens. Playbook B describes the structure but doesn't
  substitute for the conversation.
- Mechanize every step. Some judgment calls (severity assignment, scope
  decisions, when to defer to a future release) require maintainer
  attention. The playbook names where those judgment calls happen.
- Cover release announcement, marketing, or community communication.
  Those are downstream of "released to PyPI" and outside this scope.

---

## When to revise this playbook

Three signals warrant a playbook revision:

1. **A new release pattern proves itself.** If a future release shape doesn't
   fit either playbook (e.g., a release candidate / beta cycle), document
   the new pattern.

2. **An existing playbook stage stops working.** If a stage produces wrong
   results twice in a row, the stage needs revision, not just better
   execution.

3. **The supporting infrastructure changes meaningfully.** If `CLAUDE.md`
   gains a major new section, if new skills are added, if the design doc
   template changes structure — the playbook references should be updated
   to point at the right things.

Revision happens between cycles, never during one. The playbook is read at
cycle start; if it's wrong, fix it after the cycle ships.

---

## Anti-patterns (across both playbooks)

These have been hit at least once and should not be hit again:

- **Shipping without an eval.** The eval is where unknowns become known. Six
  cycles in, every release that shipped without an eval had bugs surfaced
  by the next eval that should have been caught pre-release.

- **Letting docs drift through a release cycle.** Both playbooks have a
  docs reconciliation step. Skipping it means the docs make claims the
  code doesn't honor. v3.0.0 shipped six functions documented as existing
  that didn't exist; reconciliation would have caught all six.

- **Inflating the PyPI `Development Status` classifier.** v2.0.0 shipped
  with `Production/Stable` and was downgraded to `Beta` in v2.0.1 after
  the eval. Match the classifier to reality, not aspiration.

- **Skipping TestPyPI on a release that introduces new packaging behavior.**
  v3.0.1 skipped TestPyPI and shipped clean, but that was a low-risk
  patch with no packaging changes. For any release with new dependencies,
  new entry points, or new package data, TestPyPI is mandatory.

- **Treating design questions as fix work.** If a finding requires deciding
  something rather than implementing something, it's design work, not a
  bug fix. Tag it `phase:1-design` (or the playbook-equivalent) and
  handle it separately. v3.0 caught this; v3.0.1 caught it again with
  three of four design questions getting "decide to defer to v3.1" rather
  than implementation.

---

## Quickstart

**Routine patch release (vX.Y.Z+1):** open `PLAYBOOK_PATCH_MINOR.md`, start
at Stage 1 (docs audit), proceed in order. Most patches skip Stage 4
(eval) since they're targeted fixes; that's documented in Playbook A.

**Feature release (vX.Y+1.0):** open `PLAYBOOK_PATCH_MINOR.md`, run the
full Stage 1-5 sequence.

**Major release (vX+1.0.0):** open `PLAYBOOK_MAJOR.md`, start with Phase 0
(decisions). Phase 0 happens in a planning conversation with the
maintainer-AI pairing, separate from execution. Allow weeks between Phase
1 (design docs complete) and Phase 5 (release).

For all paths: `CLAUDE.md` is read by Claude Code automatically. Skills are
available via the project's `.claude/commands/` directory. Plan documents
get created under `docs/governance/`.

---

## File index

| What | Where |
|------|-------|
| This document | `docs/governance/RELEASE_PLAYBOOK.md` |
| Patch/minor playbook | `docs/governance/PLAYBOOK_PATCH_MINOR.md` |
| Major release playbook | `docs/governance/PLAYBOOK_MAJOR.md` |
| Captured prompts (Playbook A stages) | `docs/governance/release-prompts/patch-minor/` (capture pending) |
| Captured prompts (Playbook B phases) | `docs/governance/release-prompts/major/` (capture pending) |
| Per-cycle plans | `docs/governance/V*_PLAN.md` |
| Tech debt tracker | `docs/governance/TECH_DEBT.md` |
| Compatibility log | `docs/governance/COMPATIBILITY.md` |
| Design docs (major releases) | `docs/design/vN/` |
| Standing context | `CLAUDE.md` (project root) |
| Skills | `.claude/commands/` |

The `release-prompts/` directory is populated as a separate follow-up
task. Until that's done, the playbooks reference prompts by the existing
filenames in `C:\dev\Coding Language\` root (e.g., `DOCS AUDIT TASK.md`,
`P0 BLOCKER FIXES.md`, `PYPI RELEASE.md`).
