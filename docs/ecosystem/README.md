# Nodus Ecosystem Specs

This directory contains original design specifications for Nodus ecosystem
libraries. Eight packages were designed spec-first and have full spec files
here. The remaining packages were built from AINDY/OpenClaw codebases or as
incubator scaffolds — those are listed in the **Full ecosystem status** tables
below.

## Spec-first packages (design docs in this directory)

| Spec | Package | Status |
|------|---------|--------|
| [NODUS_HTTP.md](./NODUS_HTTP.md) | [`nodus-http`](https://github.com/Masterplanner25/nodus-http) | v0.1.0 — 13 tests, prepared, not yet published |
| [NODUS_RETRY.md](./NODUS_RETRY.md) | [`nodus-retry`](https://github.com/Masterplanner25/nodus-retry) | v0.1.0 — **published on PyPI** ✅ |
| [NODUS_EVENTS.md](./NODUS_EVENTS.md) | [`nodus-events`](https://github.com/Masterplanner25/nodus-events) | v0.1.0 — 17 tests, prepared, not yet published |
| [NODUS_STORE_SQL.md](./NODUS_STORE_SQL.md) | [`nodus-store-sql`](https://github.com/Masterplanner25/nodus-store-sql) | v0.1.0 — 47 tests, prepared, not yet published |
| [NODUS_AGENT.md](./NODUS_AGENT.md) | [`nodus-agent`](https://github.com/Masterplanner25/nodus-agent) | v0.1.0 — 28 tests, prepared, not yet published |
| [NODUS_MEMORY.md](./NODUS_MEMORY.md) | [`nodus-memory`](https://github.com/Masterplanner25/nodus-memory) | v0.1.0 — 28 tests (Tier 2 core), prepared, not yet published |
| [NODUS_A2A.md](./NODUS_A2A.md) | [`nodus-a2a`](https://github.com/Masterplanner25/nodus-a2a) | Local = AgentCoordinator layer (23 tests); full A2A wire-protocol spec preserved on GitHub |
| [NODUS_EVENT.md](./NODUS_EVENT.md) | `nodus-event` | **Not yet implemented** — higher-level event framework; `nodus-events` (transport layer) is built |

## Full ecosystem status

Packages are organized by build tier. "Published ✅" means live on PyPI; all
others are prepared and ready to publish pending the rate-limit window.

### AINDY-derived (Group 1)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-circuit-breaker`](https://github.com/Masterplanner25/nodus-circuit-breaker) | 24 | **published** ✅ |
| [`nodus-auth`](https://github.com/Masterplanner25/nodus-auth) | 36 | not yet published |
| [`nodus-observability`](https://github.com/Masterplanner25/nodus-observability) | 27 | not yet published |
| [`nodus-queue`](https://github.com/Masterplanner25/nodus-queue) | 53 | not yet published |
| [`nodus-state`](https://github.com/Masterplanner25/nodus-state) | 117 | **published** ✅ |
| [`nodus-observability-framework`](https://github.com/Masterplanner25/nodus-observability-framework) | 57 | not yet published |
| [`nodus-mcp`](https://github.com/Masterplanner25/nodus-mcp) | 280 (Phase A–N library + aindy bridge) | not yet published |

### OpenClaw-derived (Group 2)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-context`](https://github.com/Masterplanner25/nodus-context) | 29 | **published** ✅ |
| [`nodus-approvals`](https://github.com/Masterplanner25/nodus-approvals) | 32 | **published** ✅ |
| [`nodus-channels`](https://github.com/Masterplanner25/nodus-channels) | 24 | **published** ✅ |
| [`nodus-llm`](https://github.com/Masterplanner25/nodus-llm) | 24 | not yet published |
| [`nodus-delivery`](https://github.com/Masterplanner25/nodus-delivery) | 27 | not yet published |

### Tier 1 — Zero-dependency standalone (Group 3)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-retry`](https://github.com/Masterplanner25/nodus-retry) | 33 | **published** ✅ |
| [`nodus-http`](https://github.com/Masterplanner25/nodus-http) | 13 | not yet published |
| [`nodus-events`](https://github.com/Masterplanner25/nodus-events) | 17 | not yet published |
| [`nodus-schema`](https://github.com/Masterplanner25/nodus-schema) | 30 | **published** ✅ |
| [`nodus-protocol`](https://github.com/Masterplanner25/nodus-protocol) | 13 | **published** ✅ |
| [`nodus-session`](https://github.com/Masterplanner25/nodus-session) | 15 | not yet published |
| [`nodus-router`](https://github.com/Masterplanner25/nodus-router) | 18 | not yet published |

### Tier 2 — Requires Tier 1 (Group 4)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-memory`](https://github.com/Masterplanner25/nodus-memory) | 28 | not yet published |
| [`nodus-workflow`](https://github.com/Masterplanner25/nodus-workflow) | 17 | not yet published |
| [`nodus-a2a`](https://github.com/Masterplanner25/nodus-a2a) | 23 | not yet published |
| [`nodus-adapters`](https://github.com/Masterplanner25/nodus-adapters) | 11 | not yet published |

### Tier 3 — Requires T1+T2 (Group 5)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-agent`](https://github.com/Masterplanner25/nodus-agent) | 28 | not yet published |
| [`nodus-gateway`](https://github.com/Masterplanner25/nodus-gateway) | 19 | not yet published |

### Tier 4 — Requires all tiers (Group 6)

| Package | Tests | PyPI status |
|---------|-------|-------------|
| [`nodus-extensions`](https://github.com/Masterplanner25/nodus-extensions) | 35 | not yet published |
| [`nodus-governance`](https://github.com/Masterplanner25/nodus-governance) | 28 | not yet published |

### Additional packages

| Package | Tests | Notes |
|---------|-------|-------|
| [`nodus-store-sql`](https://github.com/Masterplanner25/nodus-store-sql) | 47 | Promoted from incubator scaffold; not yet published |
| [`nodus-extension`](https://github.com/Masterplanner25/nodus-extension) | 126 | nodus-lang plugin framework companion repo; not yet published |
| [`nodus-native-memory-engine`](https://github.com/Masterplanner25/nodus-native-memory-engine) | 76 | PyO3/Maturin Rust extension; not yet published |
| [`nodus-sdk`](https://github.com/Masterplanner25/nodus-sdk) | 99 | Unified platform SDK (9 bridges); not yet published |

## Shared design rules

All implementations follow these conventions:

- Python-first public APIs are the canonical contract.
- Nodus builtins are thin wrappers over those Python APIs.
- Pure logic is separable from storage and transport backends.
- Backend integration happens through explicit protocols or adapter interfaces,
  not framework-specific globals.
