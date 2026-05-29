<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem Docset Audit

**Date:** 2026-05-29
**Scope:** nodus-mcp (`C:\dev\nodus-mcp`) and nodus-a2a (`C:\dev\nodus-a2a`)
**Auditor:** Codex (documentation maturity sweep)
**Purpose:** Assess the documentation state of companion libraries honestly.

---

## nodus-mcp docset

### Files present

```
docs/design/00-decisions.md
docs/design/01-adapter-mapping.md
docs/design/02-elicitation.md
docs/design/03-transports.md
docs/design/04-server-mode.md
docs/design/05-deprecated-features.md
docs/governance/TECH_DEBT.md
CHANGELOG.md
README.md
```

### Audit findings

**F-MCP-01: README is current and honest** (Positive)

The README accurately describes the library's status (`v0.1.0 prepared, not yet published`),
prominently warns about the OAuth limitation, lists known limitations in a table, and specifies
the exact spec target (2026-07-28 RC). This is a well-written README for a pre-release library.

**F-MCP-02: TECH_DEBT.md is specific and actionable** (Positive)

`docs/governance/TECH_DEBT.md` lists TD-001 through TD-010 with exact code sites, status,
and resolution gates. This is above average for a library at this stage.

**F-MCP-03: Design docs cover the 14 implementation phases** (Positive)

Five design docs cover decisions, adapter mapping, elicitation, transports, server mode,
and deprecated features. They are detailed and the D6 inversion warning is particularly
clear.

**F-MCP-04: Missing operational documentation** (Gap)

There is no document covering:
- How to monitor a running nodus-mcp server
- What to do when a transport connection drops
- How to upgrade nodus-mcp between versions
- What the failure modes of each transport are

This is expected for a pre-release library. The gap matters before production use.

**F-MCP-05: No CHANGELOG entry for the 2026-07-28 RC spec change** (Gap, possible)

The README says the spec target is "2026-07-28 RC" but the CLAUDE.md says "MCP 2025-11-25
spec." This discrepancy suggests the spec target was updated and the CHANGELOG may not
reflect it. Verify that CHANGELOG.md accurately tracks the spec version changes.

**F-MCP-06: Missing user-facing guide** (Gap)

There is no "getting started" or "how to use" guide for nodus-mcp as a Nodus script author.
The README's "Use from a Nodus script" section is minimal. Users will need a fuller tutorial
once the library is published.

**F-MCP-07: MCP spec version claim needs verification gate** (Risk)

nodus-mcp targets the 2026-07-28 RC. The RC → final progression may introduce changes
that break compatibility. The `spec verification discipline` in `LIBRARY_ECOSYSTEM.md`
requires a final-pass spec check before public registry release. There should be a checklist
item for this in the release procedure.

### Assessment

| Dimension | Level |
|-----------|-------|
| Architectural coherence | Coherent |
| Implementation completeness | Substantially complete (14 phases, OAuth deferred) |
| Documentation completeness | Good for design docs; weak on operational docs |
| Operational readiness | Prepared (not production-credible) |

---

## nodus-a2a docset

### Files present

```
docs/design/00-decisions.md
docs/design/01-adapter-mapping.md
docs/design/02-message-model.md
docs/design/03-transport-http.md
docs/design/04-discovery.md
docs/design/05-deferred-features.md
CHANGELOG.md
README.md
```

### Audit findings

**F-A2A-01: README is current and honest about scope** (Positive)

The README correctly says "message-only" (D5), lists all deferred features, and
warns about production auth requirements. The wire format table is precise and correct.

**F-A2A-02: D6 inversion is well-documented** (Positive)

`docs/design/05-deferred-features.md §2` is the clearest documentation of the D6 inversion
in the entire ecosystem. The standing assertion (`inversion-note`) that makes it permanent
is excellent practice.

**F-A2A-03: No TECH_DEBT.md** (Gap)

nodus-mcp has a `docs/governance/TECH_DEBT.md` with specific tracked items. nodus-a2a has
no equivalent. Known limitations are in the README and in design doc 05 (deferred features),
but there is no single place tracking open items with code sites and resolution criteria.

**F-A2A-04: Missing GOVERNANCE directory structure** (Gap)

nodus-a2a has no `docs/governance/` directory at all. At minimum, a TECH_DEBT.md is needed.

**F-A2A-05: No user-facing guide** (Gap)

Like nodus-mcp, there is no getting-started guide for users. The README is minimal.
The quick start covers the Python API but not the intended Nodus-script workflow.

**F-A2A-06: Auth requirement is buried** (Risk)

The production auth requirement ("Without a `token_validator`, the server runs in dev mode
and accepts all requests. Production deployments must configure a validator.") appears
in the README's Authentication section. It is not in the quick start or the first screen
of the README. Users who deploy without reading the full README may expose an unprotected
endpoint. The warning should be more prominent.

**F-A2A-07: LIBRARY_ECOSYSTEM.md overclaim not reflected in nodus-a2a's own docs** (Mismatch)

`docs/governance/LIBRARY_ECOSYSTEM.md` in the core repo claims nodus-a2a v0.1 supports
"All three protocol bindings" and "Full A2A v1.0.0 spec support." nodus-a2a's own README
accurately says HTTP+JSON only and lists the deferred features. The overclaim is in the
nodus-lang repo's ecosystem doc, not in nodus-a2a's own docs. Readers arriving via
`LIBRARY_ECOSYSTEM.md` will get a misleading picture.

**F-A2A-08: pyproject.toml has no authors or classifiers** (Minor)

`nodus-a2a/pyproject.toml` is missing `authors`, `license`, `readme`, `classifiers`, and
`description` compared to nodus-mcp's `pyproject.toml`. This affects PyPI presentation
when published.

### Assessment

| Dimension | Level |
|-----------|-------|
| Architectural coherence | Coherent |
| Implementation completeness | Substantially complete for stated D5 scope |
| Documentation completeness | Good for design docs; weak on governance and operational docs |
| Operational readiness | Prepared (not production-credible) |

---

## Cross-ecosystem findings

**F-ECO-01: Dependency version claim not yet true**

Both libraries declare `nodus-lang>=4.0.0` as a dependency. nodus-lang 4.0.0 does not
exist yet (current: 3.0.2). This means both libraries cannot be installed via `pip install`
today. Development requires `PYTHONPATH` pointing to the nodus-lang source directory.
This is documented in each README but is the most significant barrier to any external
contributor or early adopter.

**F-ECO-02: Both libraries need operational governance**

Neither library has:
- An upgrade guide
- A monitoring guide
- A contribution guide
- A security disclosure process

These are below-bar for production-credible libraries. They are appropriate absences for
a pre-launch v0.1.

**F-ECO-03: The three-artifact launch couples all three to zero-published state**

The coordinated three-artifact launch means that nodus-mcp cannot be published
independently even if it is "ready." Both libraries wait on nodus-lang 4.0.0, which
requires the full v4.0 cycle completion. This is a deliberate coupling decision but it
means the ecosystem as a whole cannot gain real-world usage until the launch completes.

---

## Actions required

| Action | Target | Priority |
|--------|--------|----------|
| Add `docs/governance/TECH_DEBT.md` to nodus-a2a | nodus-a2a | Medium |
| Make nodus-a2a auth warning more prominent in README | nodus-a2a | High |
| Fix nodus-a2a `pyproject.toml` metadata | nodus-a2a | Low |
| Verify CHANGELOG.md for MCP spec version history | nodus-mcp | Medium |
| Fix LIBRARY_ECOSYSTEM.md nodus-a2a overclaim | nodus-lang core | High (see DOCSET_ALIGNMENT_AUDIT.md F5) |
| Add release gate for spec-version final-pass check | nodus-mcp | Medium |
