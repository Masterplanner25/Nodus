# Playbook B: Major Releases

**Scope:** vX+1.0.0 releases with breaking changes or new language semantics  
**Evidence base:** v3.0.0 (one major release cycle, plus the v3.0.1 patch
that followed it via Playbook A)  
**Estimated total time:** 2–6 weeks for design + execution + release  
**Maturity:** one-cycle evidence base. This playbook captures the pattern
that worked once. Revise after the next major release adds a second data
point.

---

## When this playbook applies

Use Playbook B when the release includes any of:

- Breaking changes to existing user code (changed defaults, removed
  functions, changed semantics)
- New language semantics (operators, type system changes, control flow
  additions)
- Backward-incompatible API changes (embedding API marshaling, stdlib
  contracts)
- A version bump from vX to v(X+1) regardless of scope

If the release is bug fixes and additive features only, use Playbook A.

If a major release feels like it should be straightforward, it isn't.
v3.0 started as "fold v2.2 bug fixes into v3" — that framing was correct,
but the cycle still needed Phase 0 and Phase 1 design work because
breaking changes need decisions before they need code. The phases exist
to slow down the parts that benefit from slowing down.

---

## Overview

Six phases in strict order. Phase 0 and Phase 1 happen in a planning
conversation with the maintainer-AI pairing. Phases 2–5 happen in
execution sessions (typically Claude Code). The handoff between planning
and execution is the design docs.

| Phase | Name | Where |
|---|---|---|
| 0 | Decisions | Planning conversation |
| 1 | Design docs | Planning conversation |
| 2 | Non-breaking fixes | Claude Code execution |
| 3 | Breaking changes | Claude Code execution |
| 4 | Documentation sweep | Claude Code execution |
| 5 | Release | Claude Code execution |

After release, the eval typically surfaces issues. Those are handled via
Playbook A (patch release).

---

## Session handoff methodology

Release cycles span multiple sessions. The session-to-session handoff
discipline matters as much as the within-session work. The pattern that
has produced 7 successful release cycles is:

### Per-session deliverables

Each session ends with one or more of the following:

1. **Chat session summary** — when the work happened in this chat
   interface (planning, design, eval, governance work). Captured from
   the chat itself: the decisions made, files created or staged, open
   follow-ups, and what the next session should pick up.

2. **Claude Code session summary** — when the work happened in Claude
   Code (implementation, fixes, tests, refactors). Captured from the
   Claude Code session itself, not reconstructed from memory. Includes
   commit hashes, files touched, tests run, and known follow-ups.

Both formats are first-class. Neither replaces the other. A cycle
typically has a mix: design conversations produce chat summaries, then
Claude Code sessions execute against the resulting specs and produce
their own summaries.

### Standing documentation updates from Claude Code sessions

Each Claude Code session that introduces a new pattern, command,
convention, or environmental fact updates the project's standing
documentation:

- **CLAUDE.md** — for patterns Claude Code needs every session (build
  commands, PYTHONPATH conventions, lint rules, PowerShell syntax
  quirks, GitHub API patterns, etc.). Updated in the same session
  that surfaces the pattern.
- **.claude/commands/*** — for repeatable workflows that warrant a
  named skill (file-bug, release-prep, milestone-transition, etc.).
  Created or updated in the same session that surfaces the workflow.

The discipline is: if a Claude Code session needed something the
session before didn't have, capture that delta before ending the
session. CLAUDE.md and skills compound across sessions; missing a
delta loses leverage.

### Why this matters

Without this discipline:

- Patterns are reinvented each session
- Environment-specific gotchas re-surface as bugs in the next session
- Session-to-session handoffs lose information
- The maintainer ends up re-explaining the same things

With this discipline:

- Each session inherits the accumulated wisdom of all prior sessions
- New collaborators (or the maintainer after a break) can pick up
  from CLAUDE.md and the session summaries
- The handoff doc for the next session is concrete and current

---

## The actual workflow

This playbook describes a layered system, not a procedure to follow
blindly. The layers are:

**Standing context** lives in `CLAUDE.md`. Claude Code reads it on every
session. It captures conventions, file locations, command patterns. It is
distilled from prior cycles by asking Claude Code to review the working
conversation for repeated context. The current `CLAUDE.md` was created
this way after v2.1.

**Mechanized operations** live in `.claude/commands/`. Skills like
`file-bug` and `release-prep` mechanize multi-step procedures so they
don't need to be re-explained each cycle.

**Per-cycle design specs** live in `docs/design/vN/`. These are the
falsifiable contracts that execution work runs against. Eval cycles
validate them by treating "doc says X, implementation does Y" as a
specific finding category.

**Per-cycle plan** lives in `docs/governance/VN_PLAN.md`. Scope, phase
ordering, risk register, decision log. The plan document is updated as
phases exit.

**Per-cycle issues** live on GitHub. Each issue carries the per-bug
detail (repro, expected, actual, severity, fix direction, cross-refs).
The `file-bug` skill keeps issue shape consistent.

**Tactical execution prompts** are short, generated as needed during
execution conversations. They are not standalone artifacts — they're
"now do Commit 2" with the implicit context that Commit 2's scope is
already specified in `VN_PLAN.md` and the issues are already filed.

The playbook describes when to use each layer. It does not contain the
detailed prompts because the detailed prompts depend on the layers.

---

## Phase 0 — Decisions

**When to run:** before any design or code work, when a major release is
being scoped.

**Why it exists:** breaking changes are decisions, not just code. Phase 0
resolves the questions that gate the rest of the cycle. v3.0's Phase 0
resolved five questions (migration window, integer type model, equality
coercion, Python error wrapping, eval timing) and reduced the design
work from five docs to three.

**Inputs:**
- The list of breaking changes being considered (typically from a
  prior cycle's eval findings tagged for major release)
- Any deferred items from prior cycles (`docs/governance/V(N-1)_PLAN.md`
  "Out of scope" sections, `TECH_DEBT.md` items tagged for major)
- The constitutional document `CLAUDE.md` (for any project-wide
  conventions that affect the decisions)

**Outputs:**
- `docs/design/vN/00-phase-0-decisions.md` — the audit trail. For each
  decision: the question, options considered, chosen option with
  reasoning, rejected alternatives with their costs.
- `docs/governance/VN_PLAN.md` — the working plan. Decisions inform
  scope. Plan includes the full phase ordering, risk register, open
  questions remaining for Phase 1, tracking infrastructure.

**The workflow:** Phase 0 happens in a planning conversation between
maintainer and AI (Claude in a chat session, not Claude Code in a repo
session). The conversation produces the two output documents. The
conversation is iterative — questions get raised, decisions get made,
the AI pressure-tests reasoning, the maintainer makes the final call.

**Lessons from v3.0:**
- Time-box this phase. v3.0's Phase 0 ran in a single working session,
  not over days. Faster decisions where the maintainer has strong
  context; slower for cross-cutting concerns.
- For each decision, write down the rejected alternative's cost. Future
  cycles will revisit the decision; the cost analysis is what makes it
  reusable rather than just "we decided X."
- Some questions resolve as "defer to a future cycle" rather than "fix
  in this cycle." That's a real decision. Document it the same way.
- The plan document gets ahead of itself sometimes — early drafts
  contain scope that turns out to need Phase 1 design work. That's fine.
  The plan is a working document; it evolves between phases.

### Spec-fetch requirement for protocol or format decisions

When a Phase 0 decision references an external specification —
including but not limited to:

- Protocol libraries (MCP, A2A, future protocols)
- Format specifications (JSON Schema, Protobuf, CBOR, etc.)
- Standards documents (RFCs, W3C specs, etc.)

The decision drafting MUST include a fresh fetch of the specification
as the first step. Drafting from memory is forbidden for spec-
referencing decisions.

**Why this matters:** the v4.0 Phase 0 session originally produced
Decision 16 (nodus-mcp library v0.1) from memory. The implementation
outline missed the Elicitation capability that the MCP 2025-11-25
revision had added. The omission was caught only when the A2A spec
was fetched later in the same session, prompting a re-fetch of MCP.
Decision 16 received an amendment block; Decision 17 (nodus-a2a) was
drafted correctly against a fresh spec fetch from the start.

**Procedure:**

1. Before drafting the decision, identify the authoritative spec
   source (URL to the canonical specification document).
2. Fetch the current revision. Note the date or version.
3. Read the spec sections relevant to the decision (data model,
   operations, capabilities).
4. Draft the decision against the fetched content, citing the spec
   revision in the decision text.
5. The pinned revision becomes the contract for implementation. The
   spec verification step (before release) compares against this
   pinned revision.

**Cost:** typically 10-30 minutes per spec, depending on length.
Cheap relative to the rework cost of discovering missing capabilities
during Phase 3 implementation.

**Exit condition:** every open design question has a decision (which
may be "defer to a later cycle"); the plan document is sufficient to
start Phase 1.

---

## Phase 1 — Design docs

**When to run:** after Phase 0 decisions are locked.

**Why it exists:** the design docs are the contract that Phases 2–5
work executes against. They make claims falsifiable. v3.0's eval
specifically credited the design docs for making bugs findable:
"Because they existed, this evaluation could definitively say 'doc says
X, implementation does Y' rather than 'behavior seems inconsistent.'"

**Inputs:**
- Phase 0 decisions from `docs/design/vN/00-phase-0-decisions.md`
- Open design questions identified in the plan document

**Outputs:**
- One design doc per significant design question, numbered sequentially
  under `docs/design/vN/`. v3.0 produced `01-integer-type.md`,
  `02-python-error-replacement.md`, `03-err-record-shape.md`.
- Each design doc contains: problem statement, options considered (min 2),
  chosen direction with reasoning, migration impact, implementation
  outline (high-level, not code), open implementation questions for
  Phase 3, exit checklist.

**The workflow:** design docs are drafted in the planning conversation,
the same context that ran Phase 0. The conversation iterates on each
design doc — first draft, maintainer pushback on specific items, AI
revision, lock. The pushback is the work; the drafting is the easy part.

**Lessons from v3.0:**
- Design docs interact. v3.0's doc 1 (integer type) introduced err kinds
  that doc 2 (Python error replacement) had to enumerate. Doc 2 produced
  err records that doc 3 (err record shape) had to specify. Cross-refs
  in each doc capture the interactions.
- For each design doc, identify the scope ceiling explicitly. v3.0's
  doc 2 included an "anti-bloat clause" capping the taxonomy at 20
  exception types and 4 namespaces. Without ceilings, design work
  expands.
- Resist the urge to start coding mid-Phase-1. The temptation is real
  because the design questions feel small once you've thought about them.
  But Phase 1's value is in finishing the design before code work
  starts; if code work mixes in, Phase 1 doesn't exit cleanly.
- After each design doc, update the plan document's §1.A to mark it
  complete. The plan is the index; the design docs are the contents.

### Required sections in every Phase 1 design doc

Every Phase 1 design doc MUST include the following sections (in
addition to whatever else the design needs):

1. **Problem statement** — what's being designed and why
2. **What Phase 0 already settled** — explicit reference to which
   Phase 0 decisions this doc implements
3. **Bytecode impact** — explicit statement of whether the feature
   requires new opcodes
   - If NO: state that explicitly. Example: "No new opcodes required.
     `BYTECODE_VERSION` stays at N. [Feature] is implemented through
     [existing infrastructure]."
   - If YES: enumerate the new opcodes, the new `BYTECODE_VERSION`,
     and the compatibility implications for pre-existing `.ndbc`
     files.
4. **API surface or implementation specification** — the actual
   design content
5. **Migration impact** — how users (and existing code) migrate
6. **Open Phase 3B implementation questions** — concerns that surface
   during design but are resolved during implementation
7. **Cross-references** — to sibling design docs, governance docs,
   Phase 0 decisions

The bytecode-impact section (item 3) is critical for preserving the
frozen-bytecode contract from v1.0. Adding new opcodes is allowed (per
LANGUAGE_VISION.md principle #4) but architecturally significant and
must be explicit. The default in Phase 1 design is "no new opcodes";
features that require them must justify the cost.

This requirement was added retroactively to v4.0 Phase 1 (the first
four design docs were drafted before the requirement was formalized;
those docs gained bytecode-impact sections in commit a1e8538).

**Exit condition:** every design doc is complete and the linked GitHub
issues are updated with the design doc paths.

---

## Phase 2 — Non-breaking fixes

**When to run:** after Phase 1 design docs are locked.

**Why it exists:** the v3.0 cycle folded a bug-fix backlog (23 issues
from prior eval) into the major release. Clearing those first means
Phase 3 work happens against a clean baseline. Mixing fixes with
breaking changes makes both harder to verify.

**Inputs:**
- GitHub issues on the major release milestone, tagged with severity
- The plan document's Phase 2 batching (Batch 2A: HIGH severity,
  Batch 2B: MEDIUM, Batch 2C: LOW/cosmetic)

**Outputs:**
- One commit per logical group within a batch
- Tests for every code change
- Closed GitHub issues

**The workflow:** Phase 2 runs in Claude Code (execution sessions, not
the planning conversation). Each batch starts with a short tactical
prompt: "run Batch 2A — issues #X, #Y, #Z, file shared root cause first
if applicable." Claude Code reads the issues, reads `CLAUDE.md` for
conventions, executes. The plan document and issue bodies carry the
detail.

**Lessons from v3.0:**
- Investigate shared root causes before writing fix prompts. v3.0's
  Phase 2 Batch 2A had three import cluster bugs that turned out to
  share one root cause; investigating first saved writing three
  separate fixes.
- Test count is the gate. v3.0 Phase 2 added 46 new tests across three
  batches; v3.0.1 (patch following Phase 5) added 67 more. The pattern
  is "one test per fixed bug minimum, more if the fix surface area is
  large."
- Phase 2 is fast (one execution session per batch, multiple batches in
  a day) because the issues are well-specified by the time Phase 2
  starts. The work upfront (Phase 0/1) is what makes Phase 2 fast.

**Exit condition:** all Phase 2 batches merged, test suite green, no
regressions.

---

## Phase 3 — Breaking changes

**When to run:** after Phase 2 closes.

**Why it exists:** implement the design specs from Phase 1.

**Inputs:**
- Design docs from `docs/design/vN/`
- The plan document's Phase 3 ordering (by blast radius — largest
  first so downstream test changes happen against final behavior)

**Outputs:**
- One commit per major breaking change, or per logical sub-component
- Tests covering documented contract per design doc spec
- Closed GitHub issues
- Implementation that matches the design doc

**The workflow:** same as Phase 2 — Claude Code execution sessions, with
tactical prompts that point at the design doc and the specific issues.
The design docs are detailed enough that Claude Code can execute against
them without re-deriving the spec.

**Lessons from v3.0:**
- Phase 3 should ship the breaking changes in the order specified by the
  plan, not in the order that feels easiest. v3.0's plan ordered by
  blast radius (integer type first, then Python error replacement, then
  err record shape) for a reason — downstream tests need stable
  upstream behavior to write against.
- Each breaking change ships with its guide doc updated in the same
  pass. The "Phase 4 docs sweep" is for cleanup and reconciliation, not
  for the primary doc writing. If a breaking change ships without its
  documentation, that's a Phase 3 exit-condition failure.
- The eval that follows in Stage 4/Phase 5 will catch design-vs-shipped
  drift. Knowing this is true makes Phase 3 work cleaner — implement to
  the spec, verify against the spec, file any spec inconsistencies as
  Phase 4 work.

**Exit condition:** all breaking changes implemented, tests cover the
documented contracts, guide docs updated alongside code.

---

## Phase 4 — Documentation sweep

**When to run:** after Phase 3 closes.

**Why it exists:** docs that didn't get updated in Phase 3 need
reconciliation. Migration guide needs to be complete. Policy docs need
to match shipped behavior.

**Inputs:**
- The full docs tree
- The `CHANGELOG` `[Unreleased]` section as it stands after Phase 3
- Any v(N-1) docs that need to be EOL'd or marked deprecated

**Outputs:**
- Every code example in `docs/guide/` re-tested against the new version
  per the `CLAUDE.md` guide file testing standard
- Migration guide complete (`docs/migration/v(N-1)-to-vN.md`)
- New policy docs as needed (v3.0 added `docs/policy/error-surfaces.md`)
- `CHANGELOG.md` `[Unreleased]` complete and accurate
- `llms.txt` updated with new surfaces
- `docs/release.md` updated with release target

**The workflow:** Phase 4 is a full docs pass in a single execution
session or two. The maintainer guides the pass; Claude Code reads each
guide doc, re-runs examples, paste-verifies output, files findings for
anything that doesn't behave as documented.

**Lessons from v3.0:**
- This phase needs a hard gate at the end: a script that asserts every
  function documented in policy docs and stdlib references actually
  exists. v3.0 shipped six functions documented in `error-surfaces.md`
  that didn't exist. Mechanical check, would have caught all six
  pre-release. **This gate is the most important addition to Playbook B
  going forward.**
- Re-testing every guide example is tedious but catches real bugs.
  v3.0 found behavioral findings in five guide files via this pass.
- Don't forget non-`docs/` doc locations: `README.md`, `llms.txt`,
  PyPI long_description, GitHub release templates. v3.0 missed some
  onboarding docs in the initial pass and had to do a follow-up sweep.

### CHANGELOG diff check (major release variant)

For a major release, the CHANGELOG entry is larger and the diff check
is more involved. Run all of the following before locking the [X.Y.Z]
entry:

1. **Stdlib surface diff:** for every public stdlib function, compare
   behavior against the previous major release on representative
   inputs. Document deltas.
2. **Error message diff:** compare error message text for the same
   error categories. Even small wording changes affect users who
   string-match errors (a known anti-pattern, but it happens).
3. **CLI surface diff:** every CLI flag and subcommand exit code,
   confirmed against current behavior.
4. **Embedding API diff:** every dict shape returned by NodusRuntime,
   every kwarg accepted, every error type raised.
5. **For each diff item:** confirm the CHANGELOG [X.Y.Z] entry covers
   it under the appropriate subsection.

If the diff surfaces a behavior change not in the CHANGELOG, either
add it to the CHANGELOG or revert the unintended change. Behavior
changes shipping silently is a credibility cost; once is unfortunate,
twice is a pattern.

The `nodus_gate --runtime` check catches doc-vs-code drift in guides.
This CHANGELOG diff check catches CHANGELOG-vs-code drift in the
release notes themselves. Both are necessary; neither subsumes the
other.

**Exit condition:** every documented function exists; every documented
example runs and produces verbatim output; migration guide is complete;
CHANGELOG accurately describes shipped behavior.

---

## Phase 5 — Release

**When to run:** after Phase 4 closes.

**Why it exists:** ship to PyPI. Same procedure as Playbook A Stage 3.

**Inputs:** clean working tree, test suite green, CHANGELOG ready.

**Outputs:** version bumped, tagged, pushed, built, uploaded, GitHub
release published.

**The workflow:** use the `release-prep` skill. It mechanizes the entire
sequence. Maintainer reviews each step's output before proceeding.

**Lessons from v3.0:**
- The `release-prep` skill compresses this phase from ~30 minutes of
  procedure-reading to ~10 minutes of confirming each step.
- For a major release, TestPyPI is mandatory regardless of packaging
  changes. The release is too consequential to skip the dry-run.
- After PyPI publish, post-release eval starts immediately. Stage 4 of
  Playbook A applies here — adapt for major release scope.

**Exit condition:** PyPI shows new version; install + smoke test passes;
GitHub release published.

---

## Post-release: handoff to Playbook A

After Phase 5, the cycle hands off to Playbook A for the post-release
eval and any patches the eval surfaces. v3.0.0 followed this exact path:
Phase 5 shipped v3.0.0, the eval found 22 issues, and Playbook A
shipped v3.0.1 within 24 hours of the eval landing.

The eval itself is Playbook A Stage 4 with adaptations for the major
release:
- The stress-test prompt is the v3.0.0 template (capture pending at
  `docs/governance/release-prompts/major/04_stress_test_eval.md`)
  adapted for the specific release's design decisions, breaking changes,
  and migration paths.
- The prompt should explicitly probe each design doc's claims.
  Falsifying design docs is high-value.
- The rubric should include dimensions for the new features specifically
  so cycle-over-cycle improvement is trackable.

If the eval finds CRITICAL or HIGH issues, ship a patch (vN.0.1) via
Playbook A within a few days. If it finds only MEDIUM and below, batch
into the next planned release.

---

## Anti-patterns specific to Playbook B

These have been hit once each and should not be hit again:

- **Treating Phase 0 as optional.** "We already know what we're doing,
  let's skip to design docs." v3.0 caught this once — the integer type
  question would have shipped as Model A without Phase 0 pressure-
  testing, which would have been a 3–5 week project instead of the
  1–2 week scope that actually shipped. Phase 0 is the cheapest
  insurance in the cycle.

- **Letting Phase 1 design docs ship without scope ceilings.** v3.0's
  doc 2 caught this and added the anti-bloat clause. Future cycles
  should add the ceiling explicitly to each design doc up front.

- **Skipping the doc-vs-code reconciliation gate.** v3.0 shipped six
  documented functions that didn't exist. This is the most important
  process gap captured from the cycle. Future major releases need a
  hard gate in Phase 4: lint docs against shipped surfaces.

- **Mixing design and implementation in Phase 1.** Phase 1 produces
  design docs, not code. If code work starts mid-Phase-1, it bleeds
  into Phase 2/3 scope unclearly and Phase 1 doesn't exit on schedule.

- **Skipping the formal eval after a major release** because "we've
  been testing throughout." v3.0 didn't skip; the eval found 4 CRITICAL
  bugs that internal testing missed. The eval is independent for a
  reason.

---

## What this playbook does not cover

- Release candidate or beta cycles. v3.0 didn't use them. If a future
  major release scope justifies an RC cycle, this playbook needs a new
  phase.
- Backporting fixes from vN.x to v(N-1).x. v3.0 explicitly chose EOL
  for v2.x at v3.0 release. If a future major release maintains the
  prior line, the playbook needs revision.
- Migration tooling beyond a written migration guide. v3.0 shipped a
  guide and the parser-error-message-as-migration-hint pattern. If
  future releases need codemods or auto-migration tooling, that's
  separate scope.

---

## Maturity caveat

This playbook is captured from one major release cycle (v3.0). It is
defensible but not yet validated across multiple cycles. The v2.x
methodology contributed to the supporting infrastructure (eval prompt
shape, tiered fix pattern, release procedure) but Playbook B's
specific phase structure has one data point.

The next major release will either:
1. Confirm the structure works as-is (no significant revisions needed),
2. Identify which phases need more or less structure, or
3. Surface a missing phase that v3.0 didn't need but the next release
   does.

Revise this playbook after the next major release. Mark the revision
date and the cycle it was validated against.

---

## File index

| What | Where |
|---|---|
| This document | `docs/governance/PLAYBOOK_MAJOR.md` |
| Overview | `docs/governance/RELEASE_PLAYBOOK.md` |
| Patch/minor playbook | `docs/governance/PLAYBOOK_PATCH_MINOR.md` |
| Captured prompts (Playbook B) | `docs/governance/release-prompts/major/` *(pending)* |
| Per-cycle design docs | `docs/design/vN/` |
| Per-cycle plan | `docs/governance/VN_PLAN.md` |
| Standing context | `CLAUDE.md` (project root) |
| Skills | `.claude/commands/` |
| Tech debt tracker | `docs/governance/TECH_DEBT.md` |
| Compatibility log | `docs/governance/COMPATIBILITY.md` |

---

## Quickstart

If you are starting a major release cycle:

1. Open `docs/governance/PLAYBOOK_MAJOR.md` (this file).
2. Start Phase 0 in a planning conversation. Bring: the proposed scope,
   the deferred items from prior cycles, any decisions you've already
   formed an opinion on.
3. Phase 0 produces `docs/design/vN/00-phase-0-decisions.md` and the
   first draft of `docs/governance/VN_PLAN.md`.
4. Phase 1 produces the remaining design docs in `docs/design/vN/`.
5. Phases 2–5 happen in Claude Code execution sessions. Each phase ends
   with the plan document's exit condition met.
6. After Phase 5 publishes to PyPI, run the post-release eval via
   Playbook A Stage 4.
7. If the eval finds CRITICAL or HIGH issues, ship a patch via Playbook A.
8. After the cycle settles, revise this playbook with any lessons.
