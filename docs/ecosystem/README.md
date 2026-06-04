# Nodus Ecosystem Specs

This directory contains the original design specifications for Nodus ecosystem
libraries. Each spec was the build-ready contract that the implementation was
written against. Most of these packages are now implemented; see the status
column below.

| Spec | Package | Status |
|------|---------|--------|
| [NODUS_HTTP.md](./NODUS_HTTP.md) | `nodus-http` | v0.1.0 — 13 tests, prepared, not yet published |
| [NODUS_RETRY.md](./NODUS_RETRY.md) | `nodus-retry` | v0.1.0 — **published on PyPI** ✅ |
| [NODUS_EVENTS.md](./NODUS_EVENTS.md) | `nodus-events` | v0.1.0 — 17 tests, prepared, not yet published |
| [NODUS_STORE_SQL.md](./NODUS_STORE_SQL.md) | `nodus-store-sql` | v0.1.0 — 47 tests, prepared, not yet published |
| [NODUS_AGENT.md](./NODUS_AGENT.md) | `nodus-agent` | v0.1.0 — 28 tests, prepared, not yet published |
| [NODUS_MEMORY.md](./NODUS_MEMORY.md) | `nodus-memory` | v0.1.0 — 28 tests (Tier 2 core), prepared, not yet published |
| [NODUS_A2A.md](./NODUS_A2A.md) | `nodus-a2a` | Local = AgentCoordinator layer (23 tests); full A2A wire-protocol spec preserved on GitHub |
| [NODUS_EVENT.md](./NODUS_EVENT.md) | `nodus-event` | **Not yet implemented** — higher-level event framework; `nodus-events` (transport layer) is built |

Shared design rules that all implementations follow:

- Python-first public APIs are the canonical contract.
- Nodus builtins are thin wrappers over those Python APIs.
- Pure logic is separable from storage and transport backends.
- Backend integration happens through explicit protocols or adapter interfaces,
  not framework-specific globals.
