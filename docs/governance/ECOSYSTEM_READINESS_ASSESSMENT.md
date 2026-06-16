# Ecosystem Readiness Assessment

**Date:** 2026-06-15 (updated from 2026-06-14)
**Status:** Current-state assessment — update at each library release
**Assessor:** Claude Opus 4.8 (post-publication sweep)
**Rubric:** `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md`

---

## Summary

The Nodus ecosystem is **published, real, and awaiting real-world validation.**
nodus-lang is at **v4.0.5** (current stable on PyPI). The ecosystem spans **35 standalone
packages**, all published to PyPI under Masterplanner25. The coordinated launch is
complete. No package has yet seen significant real-world traffic; that is the honest
next frontier.

v4.0.5: stability graduation release — spawn/coroutine/channel and workflow/goal/step
promoted to Mostly Stable; yield to Stable. Language Stability Index updated.
Companion tooling: nodus-vscode v0.1.0 (VS Code Marketplace), nodus-jupyter v0.1.0
(PyPI), nodus-run-action v1.0.0 (GitHub Actions), nodus-adapter-base v0.1.0 (PyPI).
v4.0.4 fixes: identity.session_id() nil in child VMs (#254), retry stderr noise suppression
(#255). v4.0.3 fixes: all 18 Sentinel evaluation bugs. Stdlib contract test suite (87 tests)
added. 1,796 tests pass. Coverage: 76%. Five patch releases since v4.0.0 with no CRITICAL
findings in any eval cycle.

---

## Assessment: nodus-lang (core)

**Current version:** 4.0.5 (published to PyPI 2026-06-15)
**Previous published:** 3.0.2 (last pre-v4 release)

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — orchestration DSL identity well-defined; design decisions documented across 17 Phase 0 and 13 Phase 1 design docs |
| Implementation completeness | **Complete for v4.0 scope** — core language, VM, embedding API, coroutine scheduler, goals/workflows DSL, AI-native stdlib, full security sandbox all shipped |
| Operational readiness | **Published and gate-validated** — CLI, embedding API, 1,798 tests (76% coverage), lint gate, doc-vs-code gate, Gate 10 creator validation all pass. Not yet proven under real production traffic. |
| Stability commitment | **Beta classifier (PyPI)** — stable surfaces documented in LANGUAGE_STABILITY_INDEX.md; classifier upgrade to Production/Stable deferred until two consecutive minor releases with clean evals |
| Publication status | **Published** — v4.0.5 live on PyPI |

**Composite label:** Published / Stable baseline

**Honest assessment:**
- Core language (syntax, VM, embedding API) is stable and production-usable for
  scripting, automation, and agent orchestration within its design scope
- Goals, workflows, and coroutines are implemented and tested; APIs are stable but
  haven't completed the formal stability graduation process — treat as supported-experimental
- Three patch release cycles (4.0.1, 4.0.2, 4.0.3) resolved all eval-identified bugs with no
  CRITICAL findings; the baseline is trustworthy
- Known identified consumer: aindy-runtime (pinned at 3.0.2; upgrade path to 4.0.3 is
  a single pin change — embedding API is backward compatible)

---

## Assessment: nodus-mcp

**Current version:** 0.1.0 (published to PyPI)

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — protocol adapter pattern clearly implemented; 14 design phases, 280 tests; known limitations documented (TD-001–TD-010) |
| Implementation completeness | **Complete for v0.1 scope** — stdio and HTTP transports; Resources, Prompts, Tools, Sampling, Roots, Elicitation, Logging, Progress, Completion; OAuth deferred to v0.2 |
| Operational readiness | **Published, not yet traffic-proven** — 280 tests pass; limitations documented; no real-world MCP traffic observed yet |
| Stability commitment | **Pre-release (v0.1.0)** — no backward compatibility commitment |
| Publication status | **Published** |

**Composite label:** Published / Launch-ready

**Honest assessment:**
- The architecture and implementation are strong for a v0.1 library
- **Critical known limitation:** OAuth 2.0 / OIDC not implemented. Production MCP
  servers that require OAuth cannot be used. Bearer token and open-server deployments work.
- "Published" means installable and functional. It does not mean traffic-proven.

---

## Assessment: nodus-a2a

**Current version:** 0.1.0 (published to PyPI — original wire-protocol adapter)
**Note:** Local `C:\dev\nodus-a2a` has been replaced with the AgentCoordinator
layer (23 tests, no nodus-lang dep). The original A2A adapter (180 tests) is preserved
at `github.com/Masterplanner25/nodus-a2a`.

| Dimension | Level |
|-----------|-------|
| Architectural coherence | **Coherent** — message-only scope is deliberate (D5); protocol adapter pattern consistent with nodus-mcp |
| Implementation completeness | **Complete for v0.1 scope** — HTTP+JSON/REST, Agent Card discovery, DataPart dispatch, bearer token auth; 169 tests, 93% coverage. No Task lifecycle, streaming, push notifications, or OAuth in v0.1. |
| Operational readiness | **Published, not yet traffic-proven** |
| Stability commitment | **Pre-release (v0.1.0)** — no backward compatibility commitment |
| Publication status | **Published** |

**Composite label:** Published / Launch-ready (message-only scope)

**Honest assessment:**
- v0.1 is narrower than many readers expect: HTTP+JSON only, message-only, no Task lifecycle
- Production auth requires explicit `token_validator` configuration — no-op default accepts all requests
- The D5 (message-only) decision is correct for v0.1 but limits participation in
  multi-turn A2A use cases until v0.2

---

## Assessment: nodus-sdk

**Current version:** 0.1.0 (published to PyPI)

| Dimension | Level |
|---|---|
| Architectural coherence | **Coherent** — extras-based optional deps; NodusSDKRuntime fluent `attach_*` pattern; 9 bridge modules in one repo |
| Implementation completeness | **Complete for v0.1 scope** — 99 tests; FastAPI router; 9 bridges (redis, http, llm, observability, sql, vector, scheduler, webhook, api) |
| Publication status | **Published** |

**Honest assessment:** Closes the "one install story" gap. Bridge host functions return
maps — `.nd` code must use `r["key"]` not `r.key` for bridge return values. Single
entry point for the full ecosystem.

---

## Assessment: nodus-store-sql

**Current version:** 0.1.0 (published to PyPI)

| Dimension | Level |
|---|---|
| Architectural coherence | **Coherent** — frozen dataclasses + SQLAlchemy ORM + stores cleanly separated |
| Implementation completeness | **Complete** — RunStore, EventStore, JobStore (sync + async); optimistic locking, atomic job claiming, 47 tests |
| Publication status | **Published** |

**Honest assessment:** Closes the SQLAlchemy persistence gap. No Alembic — `create_all()`
is the dev-time bootstrap; production teams manage migrations independently.

---

## Assessment: nodus-vscode (VS Code extension)

**Current version:** 0.1.0 (local complete — not yet published to VS Code Marketplace)
**Source:** `github.com/Masterplanner25/nodus-vscode`

| Dimension | Level |
|---|---|
| Architectural coherence | **Coherent** — four phases cleanly separated (grammar, diagnostics, DAP, LSP); `vscode-languageclient` v9 over stdio |
| Implementation completeness | **Complete for v0.1 scope** — syntax highlighting, 23 snippets, diagnostics, run/format, DAP debugger, hover/definition/completions via LSP |
| Operational readiness | **Verified locally** — all four phases tested end-to-end; not yet Marketplace-published |
| Stability commitment | **Pre-release (v0.1.0)** — no backward compatibility commitment |
| Publication status | **Not yet published** — VSIX built; awaiting Marketplace PAT |

**Composite label:** Complete / Pre-publish

**Honest assessment:**
- LSP features (hover, definition, completions) work against the installed `nodus.exe` — changes
  to `nodus lsp` server code require a new nodus-lang PyPI release to take effect in VS Code
- LSP returns no results for files with syntax errors (parser can't build symbol table); diagnostics still work
- `nodus.lspCommand` setting allows pointing at dev source without a release
- DAP debugger depends on `nodus dap`; evaluate command (#106) not yet implemented

---

## Ecosystem-level assessment

**Is the Nodus ecosystem real?** Yes. 35 packages exist as real GitHub repos with real
implementations, real tests, and real design documentation. All are published to PyPI.

**Is the Nodus ecosystem mature?** Partially. The codebase and test coverage are solid.
No package has yet been proven under real production traffic. aindy-runtime is the
identified first real-world consumer; that upgrade (3.0.2 → 4.0.3) will be the first
production validation.

**Is the ecosystem architected well?** Yes. The protocols-are-adapters commitment is
sound. The three-tier ecosystem model is clear. AI-native primitives (Phase 6) make
execution identity, idempotency, syscall dispatch, and reliability patterns first-class
language features rather than optional library wiring.

**What does the ecosystem prove today?**
- That Nodus is published, installable, and gate-validated (1,798 tests, Gate 10 pass)
- That the embedding API is stable enough for real-world consumer integration
- That MCP, A2A, agent, workflow, memory, auth, observability, and extension patterns
  all compose cleanly on the Nodus runtime
- That a unified SDK (`nodus-sdk`) can auto-wire the ecosystem with a single install line
- That four patch release cycles have resolved all identified bugs with no CRITICAL findings
- That first-party IDE tooling (VS Code extension, all four phases) is complete and working

**What does the ecosystem not yet prove?**
- That any package is stable under real production traffic
- That the upgrade and operational story is mature enough for production teams
- That the performance profile is acceptable at scale

---

## Remaining gaps (post-publication)

1. **Real-world traffic** — no package has been used in a real production system yet;
   aindy-runtime upgrade is the near-term validation event
2. **PyPI classifier** — still `4 - Beta`; upgrade to `5 - Production/Stable` requires
   two consecutive minor releases with clean evals (policy in `docs/release.md`)
3. **OAuth in nodus-mcp** — deferred to v0.2; limits use against production MCP servers
4. **nodus-a2a Task lifecycle** — deferred to v0.2; limits multi-turn A2A use cases
5. **Performance at scale** — Python interpreter ceiling (~200K instr/sec, no JIT);
   acceptable for orchestration use cases, not for high-throughput compute (LIMITS-001)

---

## Related documents

- `docs/governance/ECOSYSTEM_MATURITY_RUBRIC.md` — the rubric used here
- `docs/governance/ECOSYSTEM_90_DAY_CHECKLIST.md` — what to complete before production
- `docs/governance/LIBRARY_ECOSYSTEM.md` — ecosystem architecture
- `docs/evals/v4.0.2/CREATOR_VALIDATION.md` — most recent Gate 10 results (v4.0.2 cycle)
