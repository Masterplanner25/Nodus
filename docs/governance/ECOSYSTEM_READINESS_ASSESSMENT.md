<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem Readiness Assessment

**Date:** 2026-05-29
**Status:** Current-state assessment — update at each library release
**Assessor:** Codex (documentation maturity sweep)
**Rubric:** `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md`

---

## Summary

The Nodus ecosystem is **real, architecturally coherent, and prepared for a coordinated
launch** — but it is **not yet production-credible and not yet proven in real systems.**
All three artifacts (nodus-lang 4.0.0, nodus-mcp 0.1.0, nodus-a2a 0.1.0) are built and
tested. None are published. None have been used in a real production system.

This is an honest current-state. It is not a weakness — it is where a project is
six months into its library ecosystem development. The architecture is strong. The
implementation is real. The next threshold is production validation.

---

## Assessment: nodus-lang (core)

**Current version:** 3.0.2 (published on PyPI)
**Next release:** 4.0.0 (prepared, not yet published)

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — orchestration DSL identity is well-defined; design decisions documented across 17 Phase 0 decisions and 13 Phase 1 design docs |
| Implementation completeness | **Substantially complete for 3.0.2** — core language stable, experimental surfaces (workflows, coroutines) implemented but not graduated |
| Operational readiness | **Prepared** — stable CLI, embedding API, test suite (77% coverage), lint gate, doc-vs-code gate. Not yet used in large-scale production deployments. |
| Stability commitment | **Pre-stable for the whole package (Beta)** — stable surfaces are documented (LANGUAGE_STABILITY_INDEX.md) but the package classifier says Beta, which covers the experimental surfaces |
| Publication status | **Published** (3.0.2 on PyPI) |

**Composite label:** Development-complete / Prepared

**Honest assessment:**
- Core language (syntax, VM, embedding API) is stable and production-usable for scripting
  and automation tasks within its design scope
- Workflows, goals, and coroutines are implemented but their APIs have not completed the
  stability graduation process — treat as experimental
- The eval score (7.57/10 on 3.0.2) honestly reflects where the language is: real and
  usable, not yet at the quality bar of a mature language runtime
- The v4.0 cycle (not yet released) adds the stdlib modules (`std:http`, `std:tool`, etc.)
  that are central to the orchestration DSL identity — without them, 3.0.2 is a capable
  scripting runtime but not yet a full orchestration DSL

---

## Assessment: nodus-mcp

**Current version:** 0.1.0 (prepared, not published)
**Publication:** Waiting for coordinated three-artifact launch with nodus-lang 4.0.0

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — protocol adapter pattern clearly implemented; design decision docs (14 phases, 280 tests); known limitations documented (TD-001 through TD-010) |
| Implementation completeness | **Substantially complete** — all 14 implementation phases done; stdio and HTTP transports; all core MCP capabilities (Resources, Prompts, Tools, Sampling, Roots, Elicitation, Logging, Progress, Completion); OAuth deferred to v0.2 |
| Operational readiness | **Prepared, not production-credible** — 280 tests pass; known limitations documented; NOT used in a real production system; no operational procedures for monitoring, upgrade, or failure handling |
| Stability commitment | **Pre-release (v0.1.0)** — no backward compatibility commitment |
| Publication status | **Prepared-unpublished** — cannot be installed by users today |

**Composite label:** Launch-ready

**Honest assessment:**
- The architecture and implementation are strong for a v0.1 library
- The 14-phase discipline (design docs → implementation → tests) is rigorous
- The known limitations are honestly documented in TECH_DEBT.md and the README
- **The critical known limitation is OAuth:** nodus-mcp v0.1 cannot authenticate to
  production MCP servers that require OAuth 2.0 / OIDC. Many production MCP deployments
  do require OAuth. This limits nodus-mcp's immediate real-world utility to environments
  that use bearer tokens or open servers.
- "Prepared" means: if you check out the repo and run it, it works. It does not mean:
  it has been proven under real MCP ecosystem traffic.
- The MCP spec target is the 2026-07-28 RC — this is a near-current spec but still an RC;
  the final spec may differ.

---

## Assessment: nodus-a2a

**Current version:** 0.1.0 (prepared, not published)
**Publication:** Waiting for coordinated three-artifact launch with nodus-lang 4.0.0

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — message-only scope is a deliberate design decision (D5), not an oversight; protocol adapter pattern consistent with nodus-mcp; D6 inversion properly documented |
| Implementation completeness | **Substantially complete for v0.1 scope** — HTTP+JSON/REST transport; Agent Card discovery; DataPart dispatch; bearer token auth; 169 tests, 93% coverage. Out-of-scope for v0.1 is substantial: no Task lifecycle, no streaming, no push notifications, no JSON-RPC binding, no gRPC binding, no OAuth |
| Operational readiness | **Prepared, not production-credible** — tests pass; known limitations documented; NOT used in a real production system; no operational runbook |
| Stability commitment | **Pre-release (v0.1.0)** — no backward compatibility commitment |
| Publication status | **Prepared-unpublished** — cannot be installed by users today |

**Composite label:** Launch-ready (for its stated v0.1 message-only scope)

**Honest assessment:**
- v0.1 is narrower than many readers will expect from the ecosystem descriptions:
  HTTP+JSON only, message-only, no Task lifecycle, no streaming
- The D5 (message-only) decision is architecturally correct for a first version, but
  it means nodus-a2a v0.1 cannot participate in the A2A ecosystem's most interesting
  use cases (multi-turn task management, streaming, push notifications)
- 93% coverage on 169 tests is strong for v0.1
- **The key gap:** `LIBRARY_ECOSYSTEM.md` describes nodus-a2a as supporting
  "all three protocol bindings" and "full A2A spec" — this is the v0.2+ target,
  not the v0.1 reality. That description overclaims. (See DOCSET_ALIGNMENT_AUDIT.md Finding 5.)
- nodus-a2a's production auth story is underdeveloped: no `token_validator` → accepts
  all requests. Production deployments require explicit validator configuration.

---

## Ecosystem-level assessment

**Is the Nodus ecosystem real?** Yes. Two companion libraries exist as real repos with
real implementations, real tests, and real design documentation.

**Is the Nodus ecosystem mature?** No. None of the companion libraries have been published.
None have been proven in production. The core language (3.0.2) is the only published
artifact.

**Is the ecosystem architected well?** Yes. The protocols-are-adapters commitment is
sound and allows both libraries to coexist without protocol-capture. The three-tier
ecosystem model is clear. The deferral decisions are honest and documented.

**What does the ecosystem prove today?**
- That Nodus can be used as an orchestration runtime
- That the embedding API is stable enough for library development
- That MCP and A2A protocol adapters can be written against Nodus primitives
- That the design is coherent

**What does the ecosystem not yet prove?**
- That Nodus scripts perform well at scale
- That the companion libraries are stable under real protocol traffic
- That the upgrade and operational story is mature enough for production teams

---

## Gaps that must close before production-credible claims

1. At least one companion library must be published and used in a real system
2. The operational runbook must be exercised by at least one real deployment
3. The OAuth gap in nodus-mcp must be documented prominently (it is, but users may miss it)
4. nodus-a2a's auth requirement must be visible in the getting-started docs, not just the README
5. LIBRARY_ECOSYSTEM.md nodus-a2a overclaim must be corrected (Finding 5 in audit)

---

## Related documents

- `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` — the rubric used here
- `docs/governance/ECOSYSTEM_90_DAY_CHECKLIST.md` — what to complete before production
- `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` — companion library docset state
- `docs/governance/LIBRARY_ECOSYSTEM.md` — ecosystem architecture
