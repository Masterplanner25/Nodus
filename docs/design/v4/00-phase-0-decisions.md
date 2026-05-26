# Nodus v4.0 — Working Plan

**Cycle:** v4.0 major release
**Theme:** Production-ready orchestration DSL
**Plan created:** 2026-05-25
**Status:** Phase 0 complete; Phase 1 not yet started
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Cycle overview

v4.0 is the production-ready release. The theme is "Nodus 4.0 — the
production-ready orchestration DSL." After v4.0 ships, Nodus is
architecturally complete for the orchestration DSL use case: full
stdlib for the orchestration glue role, comprehensive test framework
for production code, MCP library ecosystem validating the library
model, doc-vs-code reconciliation gate preventing the failure modes
that escaped in v3.x.

"Production-ready architecturally" is distinct from "production-ready
in practice." The latter requires 6+ months of running in real
production environments. v4.0 ships the architectural readiness; the
practice readiness follows from adoption.

---

## Phase ordering and exit conditions

### Phase 0 — Decisions (COMPLETE)

**Status:** Complete (2026-05-25)

**Deliverable:** `docs/design/v4/00-phase-0-decisions.md`

**Exit condition (met):** All 16 design decisions resolved with
reasoning, rejected alternatives, and reconsideration triggers
documented.

### Phase 1 — Design docs (NOT STARTED)

**Estimated effort:** 1-2 sessions producing 8-12 design docs

**Deliverables:** Design specifications under `docs/design/v4/`,
numbered sequentially from 01.

**Expected docs:**
- `01-http-api.md` — HTTP client specification
- `02-datetime-api.md` — Datetime API specification
- `03-crypto-hashing-api.md` — Three crypto namespaces specification
- `04-subprocess-api.md` — Subprocess API specification
- `05-string-interpolation.md` — Lexer/parser/compiler changes
- `06-tool-registry-library-handlers.md` — Dynamic tool registration
- `07-test-framework-api.md` — Comprehensive test framework
- `08-test-framework-coverage.md` — Coverage instrumentation
- `09-ieee-754-division.md` — Float division semantics + helpers
- `10-type-naming-reconciliation.md` — type() returns + math helpers
- `11-equality-coercion.md` — Numeric-only coercion + migration
- `12-doc-vs-code-gate.md` — Three-phase verification gate
- `13-err-record-location-fields.md` — Stdlib err records get
  path/line/column/stack

The MCP library has its own design phase, separate from v4.0 Phase 1
but informed by it.

**Exit condition:** Each design doc is locked, references its source
Phase 0 decision, specifies the API surface and migration impact,
includes the implementation outline at a high level.

### Phase 2 — Non-breaking fixes (NOT STARTED)

**Estimated effort:** A few hours

**Scope:**
- Verify `finally`-after-catch-return behavior; close as
  already-fixed if v3.0.1 eval was correct that it works
- Clear any straggler issues from v3.x that don't need design work
- Update LANGUAGE_VISION.md to reflect shipped v3.x reality

**Exit condition:** Test suite green; no design-required items
remaining open.

### Phase 3 — Breaking changes + new stdlib (NOT STARTED)

**Estimated effort:** 3-5 days focused work

**Subphases:**

*Phase 3A — Tier 1 breaking changes:*
- `len()` → `int`
- IEEE 754 float division
- Cyclic workflow err record + non-zero exit
- Stdlib err records get location fields

*Phase 3B — Tier 2 additive features (orchestration stdlib):*
- HTTP namespace (`std:http`)
- Environment variables (`std:env`)
- Datetime (`std:time`)
- Crypto (`std:hash`, `std:encoding`, `std:secrets`)
- Subprocess (`std:subprocess`)

*Phase 3C — Tier 2 additive features (language and tooling):*
- String interpolation
- Tool registry library-side handlers
- Test framework (`std:test`)
- Doc-vs-code reconciliation gate (`nodus_gate` command)

*Phase 3D — Tier 3 finalized changes:*
- `type()` naming reconciliation
- Equality coercion (numeric-only)
- Helper functions (`math.is_numeric`, `math.is_int`, `math.is_float`,
  `math.is_nan`, `math.is_inf`, `math.is_finite`)

**Order rationale:**
- 3A first because breaking changes affect downstream tests
- 3B before 3C because stdlib is foundation that test framework and
  doc-vs-code gate may use
- 3D last because helpers are additive and don't affect other work

**Exit condition per subphase:**
- All design doc claims implemented
- Tests for every code change
- Documentation updates (guide files, LANGUAGE_SPEC, policy docs) in
  the same commit as the code change
- Test suite green at subphase exit

### Phase 4 — Documentation sweep (NOT STARTED)

**Estimated effort:** Half a day to a day

**Scope:**
- Run `nodus_gate --static` and reconcile any failures
- Run `nodus_gate --runtime` against every guide doc example
- Complete migration guide `docs/migration/v3-to-v4.md`
- Update `LANGUAGE_VISION.md` with v4.0 reality
- Update `docs/roadmap.md` with v4.0 release and v5.x targets
- Update `docs/governance/STABILITY.md` with v4.0 stability commitments
- Create `docs/governance/STDLIB_PHILOSOPHY.md` if not yet created
- Update `llms.txt` and `docs/onboarding/NODUS.md`
- Update README.md with v4.0 capabilities
- CHANGELOG.md [Unreleased] → [4.0.0] with full entry

**Exit condition:** Every documented function exists in shipped code
(verified by gate); every guide example runs and produces documented
output (verified by gate); migration guide complete; CHANGELOG
accurately describes shipped behavior.

### Phase 5 — Release (NOT STARTED)

**Estimated effort:** 4-6 hours (extended from prior estimate due to
two-library coordination)

**Sequence overview:**

v4.0 ships three artifacts in coordination: `nodus-lang` 4.0.0 to PyPI,
`nodus-mcp` 0.1 to the Nodus registry, and `nodus-a2a` 0.1 to the Nodus
registry. The PyPI release is gated on both libraries being built and
spec-verified against the locked v4.0 source. The sequence is:

1. Phase 4 completes; `nodus_gate --all` passes against the dev branch
2. v4.0 source is locked (no further code changes to `nodus-lang`)
3. Both libraries are built against the locked source in parallel
4. Both libraries pass spec verification
5. All three artifacts release coordinated

**Detailed procedure:**

Step 1 — Lock v4.0 source

1.1. Confirm `nodus_gate --all` passes
1.2. Confirm test suite green (full and coverage variants)
1.3. Confirm CHANGELOG [Unreleased] is complete and accurate
1.4. Tag a working release candidate: `git tag v4.0.0-rc1`
1.5. The locked source is the `v4.0.0-rc1` tag commit. All library
     development uses this exact commit.

Step 2 — Build libraries in parallel

Both libraries are independent development efforts. Either or both may
already be in progress before this step (per Phase 1 design docs and any
library-specific design phases). Step 2 confirms they are complete and
production-ready against the locked source.

2.1. `nodus-mcp` v0.1 — complete implementation per Decision 16 (Phase
     A-N), spec-verified against MCP 2025-11-25 revision
2.2. `nodus-a2a` v0.1 — complete implementation per Decision 17 (Phase
     A-N), spec-verified against A2A v1.0.0 stable release
2.3. Both libraries pass their own test suites
2.4. Both libraries install cleanly via the registry tooling

Step 3 — Final spec verification

3.1. Fetch current MCP spec; compare against MCP 2025-11-25 revision.
     Classify changes: none / additive / breaking. If breaking, pause
     and evaluate.
3.2. Fetch current A2A spec; compare against A2A v1.0.0. Classify
     changes: none / additive / breaking. If breaking, pause and
     evaluate.
3.3. Document spec verification results in
     `docs/release-notes/v4.0/spec-verification.md`

Step 4 — Coordinated release

4.1. Bump version: `src/nodus/support/version.py` and `pyproject.toml`
     to `"4.0.0"`
4.2. Promote `CHANGELOG.md [Unreleased]` → `[4.0.0] - YYYY-MM-DD`
4.3. Commit: `release: bump to 4.0.0`
4.4. Tag `v4.0.0`, push tag
4.5. Build wheel; upload to TestPyPI
4.6. Smoke test against TestPyPI: install in fresh venv, run a
     representative script that exercises new stdlib namespaces
4.7. Install both libraries against the TestPyPI nodus-lang; verify
     they work end-to-end (e.g., a workflow that calls an MCP server
     and exposes itself as an A2A agent)
4.8. Upload `nodus-lang` 4.0.0 to PyPI
4.9. Publish `nodus-mcp` 0.1 to Nodus registry
4.10. Publish `nodus-a2a` 0.1 to Nodus registry
4.11. Publish GitHub release for `nodus-lang` v4.0.0 with [4.0.0]
      CHANGELOG entry as body
4.12. Publish GitHub releases for `nodus-mcp` v0.1 and `nodus-a2a` v0.1
4.13. Announce v4.0 (out of scope for this plan — handled separately)

**Exit condition:**

- PyPI shows `nodus-lang` 4.0.0
- Nodus registry shows `nodus-mcp` 0.1 and `nodus-a2a` 0.1
- `pip install nodus-lang==4.0.0` works in fresh environment
- `nodus --version` matches `4.0.0`
- Both libraries installable via the registry tooling
- `nodus_gate --all` passes against the installed PyPI wheel
- GitHub releases published for all three artifacts
- Spec verification document committed

### Post-release — v4.0 stress-test eval (NOT STARTED)

**Estimated effort:** Same-day or next-day after release

**Procedure:** Stress-test eval following the v3.0.1 evaluation pattern:
- Fresh testing directory
- Independent evaluator session
- Researcher mode + adversarial probes
- Full stress test of every new feature, every breaking change, every
  migration claim
- v4.0 patch closure verification section testing every claimed fix
- Build-something-real task using comprehensive v4.0 features
- Composite rubric scoring against v3.0.1 baseline (7.36/10)

**Target:** Composite ≥ 8.5/10. Ideally moving toward "production-ready
architecturally" 9.5+/10.

---

## Risk register

### Risk 1 — Scope creep during Phase 1

**Likelihood:** Medium

**Impact:** High (delays Phase 3 start)

**Mitigation:** Each design doc includes explicit scope ceiling. The
"anti-bloat clause" pattern from v3.0 design docs (capping function
counts, namespace counts) gets applied to every v4.0 design doc.

### Risk 2 — Either library implementation takes longer than estimated

**Likelihood:** Medium-High (two libraries instead of one; either can
slip)

**Impact:** High (PyPI release is gated on both libraries shipping)

**Mitigation:** Library development runs in parallel with v4.0 work
after Phase 3B (HTTP, subprocess, JSON dependencies). Both libraries
have well-bounded specifications and 14-phase implementation outlines.
The maintainer's design-heavy planning + concentrated execution pattern
handles bounded-task work well. If one library is at risk of slipping,
the response is to focus on that library; the PyPI release waits. No
fallback to "ship v4.0 first, library later" — the coordinated launch
is what validates the protocols-are-adapters architecture.

If both libraries are at risk simultaneously, the response is to extend
the v4.0 cycle, not to scope down. The cycle-extension cost is
acceptable; the architectural-message cost of an uncoordinated launch
is not.

**Reconsideration trigger:** If after a month of focused library
development one library is clearly capped at a percentage of scope
(say, 60%) and the other is complete, consider shipping v4.0 with the
complete library and the partial library as v4.0.1. This is a fallback,
not a default.

### Risk 3 — Doc-vs-code gate implementation surfaces unexpected
complications

**Likelihood:** Low-Medium

**Impact:** Medium (release blocking if gate doesn't work)

**Mitigation:** Implement gate in Phase 3C as the foundation; spend
time iterating on it during Phase 3 rather than at release time.
False positives are acceptable in early iterations; false negatives
are not.

### Risk 4 — Test framework comprehensive scope is too much for one
cycle

**Likelihood:** Medium

**Impact:** Medium (scope reduction)

**Mitigation:** Decision 4 includes a reconsideration trigger: "If
implementation surfaces that something in the comprehensive scope
requires more than 5 days of work or significantly complicates other
v4.0 work, scope down."

### Risk 5 — Breaking changes break unexpected v3.x code

**Likelihood:** Medium

**Impact:** Low (eval catches it post-release)

**Mitigation:** Migration guide is comprehensive. Phase 4 doc sweep
includes explicit migration testing against representative v3.x code
samples. Post-release eval catches anything that escapes Phase 4.

### Risk 6 — MCP spec changes between Phase 0 and v4.0 release

**Likelihood:** Medium (MCP is actively evolving)

**Impact:** Variable (small if additive, large if breaking)

**Mitigation:** Spec verification discipline applied (Decision 16
appendix). Run before v4.0 release to PyPI. Pause release if
breaking changes need incorporation.

### Risk 7 — IEEE 754 silent propagation surprises users

**Likelihood:** Medium

**Impact:** Low-Medium (post-release feedback)

**Mitigation:** Migration guide explicitly covers the change.
`math.is_nan`, `math.is_inf`, `math.is_finite` helpers prominently
documented. v4.0 eval includes specific probe for inf/nan handling
in real workflows.

### Risk 8 — A2A spec evolves between Phase 0 and v4.0 release

**Likelihood:** Medium (A2A v1.0.0 is stable but the protocol is still
maturing in ecosystem adoption)

**Impact:** Variable (small if additive, large if breaking)

**Mitigation:** Spec verification discipline applied (Decision 17,
mirroring Decision 16 for MCP). Run before v4.0 release to PyPI. Pause
release if breaking changes need incorporation. A2A v1.0.0 stable
status provides a versioned anchor (unlike MCP's dated revisions),
which simplifies the verification comparison.

---

## Dependencies and sequencing

**Critical path through Phase 3:**

1. JSON (already exists) ← prerequisite for stdlib err records, both
   protocol libraries, HTTP body decoding
2. Phase 3A (breaking changes) — must complete first because tests
   for new stdlib will be written against new behavior
3. Phase 3B HTTP — required for nodus-mcp HTTP transport and nodus-a2a
   HTTP+JSON binding
4. Phase 3B Subprocess — required for nodus-mcp stdio transport
5. Phase 3C Tool registry library-side handlers — required for both
   libraries' tool registration (Decision 12 covers both)
6. Phase 3C Test framework — depends on doc-vs-code gate for
   coverage doc verification
7. Phase 3C Doc-vs-code gate — depends on stdlib being settled
8. nodus-mcp library — depends on 3B HTTP, 3B Subprocess, 3C Tool
   registry
9. nodus-a2a library — depends on 3B HTTP, 3C Tool registry (no
   subprocess dependency — A2A is HTTP/gRPC, not stdio)

**Parallelism opportunities (libraries):**

- nodus-mcp and nodus-a2a are independent of each other; can be
  developed in parallel after their respective dependencies are met
- Each library's Phase A (foundation, data model) can begin once
  Phase 3B HTTP is stable; later phases require Phase 3C Tool registry
- gRPC binding for nodus-a2a (Phase L) requires no v4.0 work beyond
  what's already in scope; can be developed independently of the
  HTTP-binding phases

**Parallelism opportunities (other):**
- 3A subphases can be done somewhat in parallel (different files)
- 3B HTTP and 3B Subprocess are independent
- 3B namespaces all independent of each other (HTTP, env, datetime,
  crypto, subprocess)
- 3D helpers can be added incrementally as needed by other phases

---

## Tracking infrastructure

### GitHub milestones to create

- **v4.0** — main milestone for the cycle (probably milestone #8)
- **v5.0** — long-term placeholder for Tier 4 deferred items (probably
  milestone #9)

### GitHub labels to create

- `cycle:v4.0` — issues belonging to this cycle
- `phase:0-decisions` — Phase 0 design discussion
- `phase:1-design` — Phase 1 design docs in progress
- `phase:2-fix` — Phase 2 non-breaking fixes
- `phase:3-breaking` — Phase 3 breaking changes
- `phase:3-additive` — Phase 3 new features
- `phase:4-docs` — Phase 4 docs sweep
- `phase:5-release` — Phase 5 release prep
- `breaking-v4` — breaking changes ship in v4.0 specifically
- `tier:1-breaking-confirmed` — Tier 1 items
- `tier:2-additive-confirmed` — Tier 2 items
- `tier:3-design-needed` — Tier 3 items
- `tier:4-deferred-to-v5` — Tier 4 items

### Existing infrastructure to leverage

- CLAUDE.md (project root) — standing context for Claude Code
- `.claude/commands/file-bug` — file findings consistently
- `.claude/commands/release-prep` — release sequence mechanization
- PLAYBOOK_MAJOR.md — process guide for the cycle
- `docs/governance/RELEASE_PLAYBOOK.md` — entry point
- TECH_DEBT.md — capture process gaps found during the cycle

### Open issues to incorporate into v4.0

From v3.0.1 eval routing:
- #77 BUG-V31E-03 (workflow run --help) — MEDIUM → Phase 3 additive
- #78 BUG-V31E-04 (stdlib err record fields) — Tier 1 breaking
- #79 BUG-V31E-05 (cyclic workflow err record) — Tier 1 breaking
- #80 BUG-V31E-06 (strings.split arity Stack underflow) — LOW → Phase 3
- #81 BUG-V31E-07 (IEEE 754 float division) — Tier 1 breaking
- #82 (closure verification gate) — Tier 2 additive (Phase 3C)

From V3_1_PLAN.md routing:
- len() → int — Tier 1 breaking
- type() naming — Tier 3 design (resolved by Decision 9)
- finally-after-catch-return — Phase 2 verify

---

## Phase 0 decisions index

For quick reference, the 16 decisions from Phase 0:

| # | Decision | Status |
|---|---|---|
| 1 | Identity: Orchestration DSL (Option C) | Locked |
| 1+ | MCP as library, not core | Locked |
| 1+ | Bootstrapping is v5.x+ | Locked |
| 2 | v4.0 scope: roll everything in (5 tiers, no Tier 5) | Locked |
| 3 | Velocity: plan now, ship when ready | Locked |
| 4 | Test framework: comprehensive scope | Locked |
| 5 | HTTP API: sync default, async opt-in, rich err | Locked |
| 6 | Datetime: aware only, epoch ms, chrono format | Locked |
| 7 | Crypto: three namespaces, orchestration-scoped | Locked |
| 8 | Subprocess: no-shell default, sync default, rich options | Locked |
| 9 | type(): "float" and "int" specific, with helpers | Locked |
| 10 | IEEE 754 division: inf/nan with helpers | Locked |
| 11 | String interpolation: `"\(expr)"` Swift-style | Locked |
| 12 | Tool registry: dynamic registration, conflict-as-error | Locked |
| 13 | Test framework: pure library, block-based syntax | Locked |
| 14 | Equality: numeric-only coercion, no `===` operator | Locked |
| 15 | Doc-vs-code gate: three-phase verification | Locked |
| 16 | MCP library v0.1: comprehensive, ships with v4.0 | Locked |
| 16+ | MCP spec pin: 2025-11-25, Elicitation added to Phase F | Locked |
| 17 | A2A library v0.1: comprehensive, three bindings, ships with v4.0 | Locked |

Full reasoning, rejected alternatives, and reconsideration triggers
for each decision are in `docs/design/v4/00-phase-0-decisions.md`.

---

## Documents created or updated during this cycle

### Created at Phase 0

- `docs/design/v4/00-phase-0-decisions.md` (this document's companion)
- `docs/governance/V4_0_PLAN.md` (this document)
- `docs/governance/LIBRARY_ECOSYSTEM.md` (three-tier ecosystem
  architecture, protocols-as-adapters commitment, v4.0 launch shape)

### To create during Phase 1

- 8-12 design docs under `docs/design/v4/` (per Phase 1 deliverables)

### To create or update during Phase 4

- `docs/release-notes/v4.0/spec-verification.md` (Phase 5 deliverable)
  — both protocol library spec verifications documented
- `docs/migration/v3-to-v4.md` (new) — migration guide
- `LANGUAGE_VISION.md` (root) — updated for v4.0 reality and v5.x+
  outlook
- `docs/roadmap.md` — updated with v4.0 release and v5.x targets
- `docs/governance/STABILITY.md` — updated with v4.0 stability
  commitments
- `docs/governance/STDLIB_PHILOSOPHY.md` (new) — core vs library policy
- `llms.txt` — updated for v4.0 surfaces
- `docs/onboarding/NODUS.md` — updated for v4.0 features
- `README.md` — updated description and capability list
- `CHANGELOG.md` — full [4.0.0] entry
- `PLAYBOOK_PATCH_MINOR.md` — incorporate doc-vs-code gate in Stage 3
- `PLAYBOOK_MAJOR.md` — incorporate doc-vs-code gate in Phase 4

### To monitor during Phase 3

- `TECH_DEBT.md` — add any process gaps surfaced during execution
- All design docs under `docs/design/v4/` — update if implementation
  reveals spec gaps (with cross-ref to commit that updated them)

---

## What this plan does not yet cover

These items are explicitly out of scope for v4.0 Phase 0 planning;
they get their own design and planning when needed:

- nodus-mcp library design phase (separate cycle, dependencies on
  v4.0 Phase 3B HTTP + 3B Subprocess + 3C Tool registry)
- nodus-a2a library design phase (separate cycle, dependencies on
  v4.0 Phase 3B HTTP + 3C Tool registry)
- v5.x planning (will start after v4.0 eval cycle completes)
- Performance optimization passes (separate effort, not v4.0 priority)
- IDE integration polish beyond what exists in v3.x
- Community contribution guidelines (handled separately from release work)
- Marketing and announcement strategy for v4.0 (handled at release time)

---

## Cycle exit criteria

v4.0 is considered complete when all of the following are true:

1. PyPI shows nodus-lang 4.0.0 published
2. GitHub release v4.0.0 published with full CHANGELOG entry
3. `pip install nodus-lang==4.0.0` works cleanly in fresh environment
4. `nodus_gate --all` passes against the installed wheel
5. Both `nodus-mcp` v0.1 and `nodus-a2a` v0.1 published to the Nodus
   registry. No fallback to "library ships later as v4.0.x" — both
   libraries gate the PyPI release.
6. v4.0 stress-test eval completed with composite score ≥ 8.0
7. Migration guide complete and verified against representative v3.x
   code
8. PLAYBOOK_PATCH_MINOR.md and PLAYBOOK_MAJOR.md updated to incorporate
   doc-vs-code gate as a permanent process improvement

After exit: v4.0.x patches address eval findings; v5.0 planning starts
when accumulated v4.x work and Tier 4 items justify a new major cycle.

---

## File index

| What | Where |
|------|-------|
| This document | `docs/governance/V4_0_PLAN.md` |
| Phase 0 decisions | `docs/design/v4/00-phase-0-decisions.md` |
| Phase 1 design docs | `docs/design/v4/` (01+) |
| Migration guide | `docs/migration/v3-to-v4.md` (Phase 4 deliverable) |
| Vision doc | `LANGUAGE_VISION.md` (project root) |
| Stdlib philosophy | `docs/governance/STDLIB_PHILOSOPHY.md` (new) |
| Tech debt tracker | `docs/governance/TECH_DEBT.md` |
| Release playbook | `docs/governance/RELEASE_PLAYBOOK.md` |
| Major release playbook | `docs/governance/PLAYBOOK_MAJOR.md` |
| Library ecosystem | `docs/governance/LIBRARY_ECOSYSTEM.md` |
| nodus-mcp repo | `github.com/Masterplanner25/nodus-mcp` |
| nodus-a2a repo | `github.com/Masterplanner25/nodus-a2a` |

Plan complete. Phase 1 begins when ready.