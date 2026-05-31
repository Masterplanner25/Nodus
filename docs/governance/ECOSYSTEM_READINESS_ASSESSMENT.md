<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem Readiness Assessment

**Date:** 2026-05-30 (updated from 2026-05-29)
**Status:** Current-state assessment — update at each library release
**Assessor:** Codex (documentation maturity sweep) / updated for v4.0.0
**Rubric:** `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md`

---

## Summary

The Nodus ecosystem is **real, architecturally coherent, and prepared for a coordinated
launch** — but it is **not yet production-credible and not yet proven in real systems.**
nodus-lang is at **4.0.0** (unpublished). The ecosystem now spans **29 standalone packages**
(27 Nodus packages + nodus-sdk v0.1.0 + nodus-store-sql v0.1.0), all with GitHub repos
under Masterplanner25. None are published to PyPI. None have been used in a real
production system.

v4.0.0 additions: 6 new AI-native stdlib modules (std:identity, std:effects, std:sys,
extended std:memory, std:retry, std:circuit_breaker), HandlerContract infrastructure
in nodus_schema, nodus-sdk (unified SDK), and nodus-store-sql (SQLAlchemy persistence).
1,612 tests pass in nodus-lang. Both ecosystem audits (A.I.N.D.Y. and OpenClaw) are
now fully covered.

---

## Assessment: nodus-lang (core)

**Current version:** 4.0.0 (prepared, not yet published)
**Published on PyPI:** 3.0.2 (last published release)

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

**Is the Nodus ecosystem real?** Yes. 29 packages exist as real GitHub repos with real
implementations, real tests, and real design documentation. The A.I.N.D.Y. and OpenClaw
ecosystem audits (25 capabilities, 9+ library candidates, 7 framework candidates) are now
fully covered by implemented packages.

**Is the Nodus ecosystem mature?** No. None of the packages have been published to PyPI.
None have been proven in production. The core language (3.0.2) is the only published
artifact. nodus-lang 4.0.0 and the companion libraries await coordinated publication.

**Is the ecosystem architected well?** Yes. The protocols-are-adapters commitment is
sound. The three-tier ecosystem model is clear. The AI-native primitives (Phase 6)
make execution identity, idempotency, syscall dispatch, and reliability patterns
first-class language features rather than optional library wiring.

**What does the ecosystem prove today?**
- That Nodus can be used as an orchestration runtime (1,612 tests passing)
- That the embedding API is stable enough for library development (27 packages built on it)
- That MCP, A2A, agent, workflow, memory, auth, observability, and extension patterns
  all compose cleanly on the Nodus runtime
- That a unified SDK (`nodus-sdk`) can auto-wire the ecosystem with a single install line
- That both audit-identified capability gaps (A.I.N.D.Y. + OpenClaw) are now closed

**What does the ecosystem not yet prove?**
- That any package is stable under real production traffic
- That the upgrade and operational story is mature enough for production teams
- That the performance profile is acceptable at scale

---

## Assessment: nodus-sdk

**Current version:** 0.1.0 (prepared, not published)

| Dimension | Level |
|---|---|
| Architectural coherence | **Coherent** — extras-based optional deps; NodusSDKRuntime fluent attach_* pattern; bridge code in one repo |
| Implementation completeness | **Complete for v0.1 scope** — 9 bridge modules; factory; 99 tests |
| Publication status | **Prepared-unpublished** |

**Honest assessment:** Closes the "one install story" gap. The five new Python bridges
(sql, vector, scheduler, webhook, api) are net-new code with no prior equivalent. Bridge
host functions return maps (not Records) — .nd code must use index access `r["key"]`
not dot access `r.key` for bridge return values. LLMBridge requires a `provider_fn` arg.

---

## Assessment: nodus-store-sql

**Current version:** 0.1.0 (prepared, not published)

| Dimension | Level |
|---|---|
| Architectural coherence | **Coherent** — frozen dataclasses (domain models) + SQLAlchemy ORM (storage) + stores (operations) cleanly separated |
| Implementation completeness | **Complete** — RunStore, EventStore, JobStore (sync + async); optimistic locking, atomic job claiming, causal event chains, pagination |
| Publication status | **Prepared-unpublished** |

**Honest assessment:** Closes the last gap identified by both ecosystem audits. The scaffold
was already architecturally sound — this release added API completion (4 new methods),
async support, and expanded tests (6 → 47). No Alembic integration — `create_all()` is
the dev-time schema bootstrap; production teams manage migrations independently.

---

## Gaps that must close before production-credible claims

1. At least one package must be published to PyPI and used in a real system
2. The operational runbook must be exercised by at least one real deployment
3. The OAuth gap in nodus-mcp must be documented prominently (it is, but users may miss it)
4. nodus-a2a's auth requirement must be visible in the getting-started docs, not just the README
5. LIBRARY_ECOSYSTEM.md nodus-a2a overclaim has been noted (Finding 5 in audit) — partial fix applied

---

## Related documents

- `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` — the rubric used here
- `docs/governance/ECOSYSTEM_90_DAY_CHECKLIST.md` — what to complete before production
- `docs/governance/ECOSYSTEM_DOCSET_AUDIT.md` — companion library docset state
- `docs/governance/LIBRARY_ECOSYSTEM.md` — ecosystem architecture
