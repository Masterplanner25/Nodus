<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Docset Alignment Audit

**Date:** 2026-05-29
**Scope:** Nodus core (`C:\dev\Coding Language`) — all docs under `docs/`
**Auditor:** Codex (documentation maturity sweep)
**Purpose:** Identify version drift, overclaims, missing governing docs, stale docs, and
boundary-blur across the entire Nodus core docset. This is not a style review — it is a
truth-vs-current-state audit.

---

## Summary verdict

The Nodus core docset is **partially coherent and materially stale in several high-impact
areas.** The language and runtime implementation are ahead of the documentation. The
governance layer is thin relative to the project's complexity. Several docs make claims
that do not match the current release (3.0.2) or the companion library reality.

The docset has strong design-history coverage (design decision records, eval reports,
phase plans) but weak governing coverage (no compatibility model, no true stability index,
no docset index, no security posture doc, no ecosystem boundary definition).

---

## Finding 1 — Version drift: README JSON-LD vs pyproject.toml

**Severity:** High (visible to indexers and AI tools via structured data)

`README.md` embeds a `<script type="application/ld+json">` block with:
```json
"version": "2.1.0"
```

`pyproject.toml` says:
```toml
version = "3.0.2"
```

`docs/language/LANGUAGE_VISION.md` confirms the current release is v3.0.2 (shipped 2026-05-25).

**Action required:** Update `README.md` JSON-LD version to `"3.0.2"`.

---

## Finding 2 — COMPATIBILITY.md is not a compatibility model

**Severity:** High (governance gap)

`docs/governance/COMPATIBILITY.md` is titled "Nodus Compatibility & Deprecation Timeline"
but contains only:
- a list of deprecated items
- a version-by-version changelog of deprecation decisions

There is no policy covering:
- what counts as a breaking change
- how source compatibility is defined
- how bytecode compatibility is handled between versions
- how the embedding API compatibility commitment works
- how library authors should reason about compatibility

A file named `COMPATIBILITY.md` that is only a deprecation log misleads readers looking
for a compatibility model. It should either be renamed to `DEPRECATION_TIMELINE.md` or
expanded with an actual model.

**Action:** Create `docs/governance/COMPATIBILITY_MODEL.md` as the governing compatibility
doc. Retitle or restructure `COMPATIBILITY.md` to defer to it.

---

## Finding 3 — STABILITY.md is too thin for its claimed role

**Severity:** Medium

`docs/governance/STABILITY.md` provides a three-tier classification (Stable / Mostly Stable
/ Experimental) with flat lists under each tier. This is a start, but it is not a
surface-by-surface stability index. Gaps:

- No classification of the embedding API surface (`NodusRuntime`, `run_source()`,
  `run_file()`, `register_function()`)
- No classification of bytecode format stability and upgrade path
- No classification of stdlib module APIs (`std:http`, `std:tool`, `std:subprocess`, etc.)
- No classification of runtime event API, profiler API, DAP/LSP server APIs
- No versioning policy cross-reference
- `Experimental` section lists workflows, goals, coroutines — but these are in v3.0.2 and
  substantially implemented. The "experimental" label without graduation criteria is unclear.

**Action:** Expand with `docs/governance/LANGUAGE_STABILITY_INDEX.md` as the full
surface-by-surface index. STABILITY.md should point to it.

---

## Finding 4 — LIBRARY_ECOSYSTEM.md references non-existent STDLIB_PHILOSOPHY.md

**Severity:** Medium (broken reference in a key governance doc)

`docs/governance/LIBRARY_ECOSYSTEM.md` references
`docs/governance/STDLIB_PHILOSOPHY.md` in four places, calling it a "Phase 4 deliverable."
This file does not exist. The reference is a forward-looking placeholder that was never
filled.

**Action:** Either create a minimal `STDLIB_PHILOSOPHY.md` or replace the references with
`docs/governance/LIBRARY_ECOSYSTEM.md §4` (not-pursued section) which already captures the
relevant philosophy.

---

## Finding 5 — LIBRARY_ECOSYSTEM.md overclaims nodus-a2a v0.1 scope

**Severity:** High (misleads readers about what the library actually does)

`docs/governance/LIBRARY_ECOSYSTEM.md` claims nodus-a2a provides:
> "All three protocol bindings (JSON-RPC, gRPC, HTTP+JSON/REST). Full A2A v1.0.0 spec
> support (Task lifecycle, Message/Artifact/Part data model, AgentCard discovery,
> streaming via SSE, push notifications via webhooks, multi-turn via contextId/taskId,
> Extensions mechanism, bearer-token auth for v0.1)."

The actual nodus-a2a v0.1 reality (from `nodus-a2a/README.md` and design docs):
- HTTP+JSON/REST only — JSON-RPC and gRPC are explicitly deferred to v0.2
- Message-only (D5 decision) — no Task lifecycle, no Task creation, no Task store
- No streaming — SSE is deferred; `capabilities.streaming = false`
- No push notifications — `capabilities.pushNotifications = false`
- Single-part responses only — multi-part deferred to v0.2
- No extended Agent Card — `capabilities.extendedAgentCard = false`

The LIBRARY_ECOSYSTEM.md text describes the v0.2+ target, not the v0.1 reality.

**Action:** Update `LIBRARY_ECOSYSTEM.md` nodus-a2a entry to accurately describe v0.1 scope.
Add explicit note that JSON-RPC, gRPC, Task lifecycle, streaming, and push notifications
are v0.2+ targets.

---

## Finding 6 — RELEASE_CHECKLIST.md uses pre-v1.0 CLI commands

**Severity:** Medium (wrong commands mislead release operators)

`docs/governance/RELEASE_CHECKLIST.md` pre-release checks use:
```bash
python nodus.py fmt --check {}
```
and unit tests use:
```bash
python -m unittest discover -s tests -v
```

Current CLI commands are:
```bash
nodus fmt --check <file>
python -m pytest tests/ -q
```

The checklist also references `nodus test-examples` (not a known current command) and
does not include the doc-vs-code gate (`tools/nodus_gate/`).

**Action:** Update `RELEASE_CHECKLIST.md` to use current commands. Add doc-vs-code gate step.
Reference `docs/governance/RELEASE_PLAYBOOK.md` as the authoritative playbook.

---

## Finding 7 — LANGUAGE_VISION.md "Near-Term Direction" section describes v4.0 as in-progress

**Severity:** Low-medium (status drift)

`docs/language/LANGUAGE_VISION.md` has a "Near-Term Direction" section showing v4.0 phases
as "in progress." As of 2026-05-29, nodus-lang is at 3.0.2 and v4.0 has not been released.
The note saying "v4.0 in progress" is technically accurate but the companion library status
descriptions may drift as phases complete.

**Action:** Minor. The V4_0_PLAN.md is the authoritative status source. LANGUAGE_VISION.md
should defer to it for status.

---

## Finding 8 — EMBEDDING.md section formatting is inconsistent

**Severity:** Low

`docs/runtime/EMBEDDING.md` uses prose without proper Markdown headers (sections are named
with plain numbers, not `##` headers). It reads as converted plaintext. The content is
accurate and detailed — the format just doesn't render cleanly in a Markdown viewer.

**Action:** Reformat headers. Content is otherwise accurate as of v2.1.0+ (BUG-005 fix for
error handling is correctly documented).

---

## Finding 9 — No docset index or precedence layer

**Severity:** High (structural gap)

There is no document that:
- lists all docs and their roles
- defines which doc takes precedence when docs disagree
- tells a new reader where to start
- explains the governance layer structure

Readers arriving at any doc cannot easily determine whether it is canonical, legacy,
architectural reference, or historical. The CLAUDE.md has a file-location table but that
is a developer tool, not a reader-facing index.

**Action:** Create `docs/governance/DOCSET_INDEX.md`.

---

## Finding 10 — No security posture document

**Severity:** Medium

The project has security-relevant behavior (sandbox enforcement, `allowed_paths`,
`max_frames`, bytecode cache with marshal/checksum, HTTP bearer-token auth) but no
document that describes the security posture, threat model, or what the sandbox does
and does not protect against.

`EMBEDDING.md` §8 touches sandbox controls but describes them as implementation details,
not as a security posture.

**Action:** Create `docs/governance/SECURITY_POSTURE.md`.

---

## Finding 11 — No test strategy document

**Severity:** Medium

The project has a 77% coverage baseline, a 60% gate, three timing-sensitive deselected
tests, and a test methodology note in TECH_DEBT.md (security boundary test rule). There
is `docs/tooling/TESTING.md` but it appears focused on the test framework feature, not
the project's own test strategy. No document governs:
- what the test suite covers vs. what it explicitly skips
- which categories of behavior are integration-tested vs. unit-tested
- the policy for regression tests on security fixes
- the relationship between the eval reports and the test suite

**Action:** Create `docs/governance/TEST_STRATEGY.md`.

---

## Finding 12 — No release gate document

**Severity:** Medium

The project has multiple release-quality gates:
- pytest (60% coverage floor)
- ruff lint gate
- doc-vs-code gate (nodus_gate --all)
- closed-issue regression test gate (mentioned in TECH_DEBT.md)

These are scattered across TECH_DEBT.md, CLAUDE.md, and the CI config. No single document
lists all release gates in one place with their passing criteria and exemption rules.

**Action:** Create `docs/governance/RELEASE_GATES.md`.

---

## Finding 13 — pyproject.toml classifiers mismatch stability posture

**Severity:** Low

`pyproject.toml` classifiers include:
```
"Development Status :: 4 - Beta"
```

But the stability policy (`STABILITY.md`) says the core language, VM, and embedding API
are **stable** since v1.0. "Beta" is an understatement for the stable subset, and might
imply instability where none exists.

This is a judgment call — "Beta" may be appropriate for the whole package given
experimental features. But it should be a conscious decision documented somewhere.

**Action:** Note for the v4.0 release: consider upgrading to
`"Development Status :: 5 - Production/Stable"` for the stable subset, or document the
rationale for keeping "Beta" in `RELEASE_GATES.md` or `RELEASE_PLAYBOOK.md`.

---

## Finding 14 — Docs lack cross-reference to eval reports

**Severity:** Low

The eval report system (`docs/evals/`) is comprehensive and provides the most honest
assessment of language maturity available. But none of the governing docs (STABILITY.md,
COMPATIBILITY.md, VERSIONING.md) reference the eval reports or explain how they relate
to stability classification decisions.

**Action:** Add cross-references from LANGUAGE_STABILITY_INDEX.md to the eval reports.

---

## Strongest existing docs

In order of quality and currency:

1. `docs/runtime/ARCHITECTURE.md` — highly detailed, current, accurate
2. `docs/governance/LIBRARY_ECOSYSTEM.md` — strong conceptual framework (but see Finding 5)
3. `docs/language/LANGUAGE_VISION.md` — well-written identity and design philosophy
4. `docs/language/LANGUAGE_SPEC.md` — accurate, stability-annotated per section
5. `docs/governance/TECH_DEBT.md` — honest, detailed, well-maintained
6. `docs/runtime/BYTECODE_REFERENCE.md` (presumed strong based on pattern)
7. `docs/runtime/EMBEDDING.md` — comprehensive API coverage

---

## Stale or high-conflict docs

| Doc | Issue |
|-----|-------|
| `docs/governance/COMPATIBILITY.md` | Deprecation log masquerading as a compatibility model |
| `docs/governance/RELEASE_CHECKLIST.md` | Pre-v1.0 CLI commands; missing gates |
| `README.md` JSON-LD block | Version 2.1.0 vs current 3.0.2 |
| `docs/governance/LIBRARY_ECOSYSTEM.md` | nodus-a2a scope overclaim |
| `docs/governance/STABILITY.md` | Flat and thin; no surface-by-surface |
| `docs/governance/V2_1_PLAN.md` | Historical only (complete) |
| `docs/governance/V3_0_PLAN.md` | Historical only (complete) |
| `docs/governance/V3_1_PLAN.md` | Historical only (complete) |

---

## Missing governing docs (as of this audit)

| Missing doc | Impact |
|-------------|--------|
| `docs/governance/COMPATIBILITY_MODEL.md` | No true compatibility policy |
| `docs/governance/LANGUAGE_STABILITY_INDEX.md` | No surface-by-surface stability |
| `docs/governance/SECURITY_POSTURE.md` | No security posture |
| `docs/governance/TEST_STRATEGY.md` | No test strategy |
| `docs/governance/RELEASE_GATES.md` | No consolidated gate list |
| `docs/governance/DOCSET_INDEX.md` | No reader-facing docset map |
| `docs/governance/STDLIB_PHILOSOPHY.md` | Referenced from LIBRARY_ECOSYSTEM.md; doesn't exist |
| `docs/runtime/EXECUTION_INVARIANTS.md` | No runtime guarantee document |
| `docs/runtime/FAILURE_AND_DEGRADATION_MODEL.md` | No failure mode doc |
| `docs/runtime/OPERATOR_OR_EMBEDDER_RUNBOOK.md` | No operational guide |

---

## Actions required (priority order)

1. Fix `README.md` version drift (Finding 1) — immediate
2. Fix `LIBRARY_ECOSYSTEM.md` nodus-a2a overclaim (Finding 5) — before next public discussion
3. Create `COMPATIBILITY_MODEL.md` (Finding 2)
4. Create `LANGUAGE_STABILITY_INDEX.md` (Finding 3)
5. Update `RELEASE_CHECKLIST.md` (Finding 6)
6. Create `DOCSET_INDEX.md` (Finding 9)
7. Create `SECURITY_POSTURE.md` (Finding 10)
8. Create `EXECUTION_INVARIANTS.md`
9. Create `FAILURE_AND_DEGRADATION_MODEL.md`
10. Create `STDLIB_PHILOSOPHY.md` stub (Finding 4)
