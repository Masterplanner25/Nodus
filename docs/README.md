# Nodus Documentation

**Current stable version:** v4.0.6 · [CHANGELOG](../CHANGELOG.md) · [PyPI](https://pypi.org/project/nodus-lang/)

This directory contains all technical documentation for Nodus. Start with the
[Getting Started guide](guide/getting-started.md) if you are new.

---

## Quick Navigation

| Looking for… | Go to |
|---|---|
| Install and run Nodus | [`guide/getting-started.md`](guide/getting-started.md) |
| Language syntax reference | [`language/LANGUAGE_SPEC.md`](language/LANGUAGE_SPEC.md) |
| Embed Nodus in Python | [`runtime/EMBEDDING.md`](runtime/EMBEDDING.md) |
| Standard library reference | [`guide/standard-library.md`](guide/standard-library.md) |
| Workflow and task graph DSL | [`guide/workflows-and-tasks.md`](guide/workflows-and-tasks.md) |
| AI-native primitives | [`guide/ai-primitives.md`](guide/ai-primitives.md) |
| Error handling | [`guide/error-handling.md`](guide/error-handling.md) |
| Versioning and release policy | [`release.md`](release.md) |
| Security reporting | [`security/SECURITY_MATRIX.md`](security/SECURITY_MATRIX.md) |
| Migrate from v3 → v4 | [`migration/v3-to-v4.md`](migration/v3-to-v4.md) |

---

## Directory Map

### `guide/` — User Guides

Practical, runnable documentation. Every code example has been executed
against the dev source. The primary reference for Nodus users.

| File | Contents |
|---|---|
| `getting-started.md` | Install, first script, CLI overview |
| `types-and-values.md` | Floats, ints, strings, booleans, nil, type coercion |
| `working-with-maps.md` | Map literals, bracket notation, mutation |
| `working-with-json.md` | `std:json` parse/stringify, JSON-to-map gotcha |
| `modules-and-imports.md` | Import forms, export, live bindings, resolution |
| `standard-library.md` | All stdlib modules with examples |
| `error-handling.md` | `try/catch/finally`, five exit paths, `throw` |
| `workflows-and-tasks.md` | `workflow`/`goal`/`step` DSL, task graphs, checkpoints |
| `ai-primitives.md` | `std:tool`, `std:identity`, `std:effects`, `std:sys`, `std:retry` |
| `embedding-nodus.md` | `NodusRuntime`, host functions, sandbox configuration |
| `library-entry-points.md` | Third-party library entry-point contract |
| `real-world-integration.md` | HTTP, subprocess, secrets, production patterns |
| `testing.md` | `std:test` framework, `nodus test`, async test patterns |
| `debugging.md` | `nodus debug`, breakpoints, trace mode, profiler |
| `ecosystem.md` | Companion library overview (nodus-sdk, nodus-mcp, etc.) |

---

### `runtime/` — Runtime Reference

Internal specification documents. Authoritative for VM behavior, embedding,
and bytecode. Required reading for contributors and embedders.

| File | Contents |
|---|---|
| `RUNTIME.md` | VM overview: stack, frames, memory model, scheduler |
| `BYTECODE.md` | Full bytecode specification with all 47 opcodes |
| `INSTRUCTION_SEMANTICS.md` | Per-opcode stack transitions (frozen at v1.0) |
| `EMBEDDING.md` | `NodusRuntime` API reference |
| `EXECUTION_INVARIANTS.md` | Runtime guarantees the VM must uphold |
| `FAILURE_AND_DEGRADATION_MODEL.md` | Failure categories, error shapes, host guidance |
| `OPERATOR_OR_EMBEDDER_RUNBOOK.md` | Setup, monitoring, troubleshooting, upgrade procedure |
| `ARCHITECTURE.md` | Full runtime pipeline and component overview |
| `BYTECODE_REFERENCE.md` | Quick opcode lookup table |
| `SERVER_MODE.md` | `nodus serve` HTTP server mode |
| `TASK_GRAPHS.md` | Low-level task graph runtime |
| `WORKFLOWS.md` | Workflow runtime internals |
| `PROFILER.md` | `nodus profile` output format |
| `RUNTIME_EVENTS.md` | Event emission system |

---

### `tooling/` — Tooling Reference

| File | Contents |
|---|---|
| `LSP.md` | Language Server Protocol implementation |
| `DAP.md` | Debug Adapter Protocol implementation |
| `DEBUGGER.md` | Interactive debugger commands |
| `DEBUGGING.md` | Full debugging guide |
| `EDITOR_SUPPORT.md` | VS Code extension and editor setup |
| `TESTING.md` | `nodus test` runner reference |
| `REPL.md` | `nodus repl` reference |
| `PACKAGE_MANAGER.md` | `nodus.toml`, `nodus install`, registry protocol |
| `PROJECTS.md` | `nodus init` and project layout |

---

### `language/` — Language Design

| File | Contents |
|---|---|
| `LANGUAGE_SPEC.md` | Authoritative language specification |
| `LANGUAGE_VISION.md` | Design philosophy and long-term direction |
| `DESIGN.md` | Key design decisions and rationale |
| `STYLE_GUIDE.md` | Nodus code style conventions |
| `FORMAT.md` | Formatter rules (`nodus fmt`) |

---

### `governance/` — Governance and Process

Policy, stability, release process, and audit documents. Reader entry point
and precedence rules: [`governance/DOCSET_INDEX.md`](governance/DOCSET_INDEX.md).

Key documents:

| File | Contents |
|---|---|
| `DOCSET_INDEX.md` | Doc precedence rules and reader entry point |
| `LANGUAGE_STABILITY_INDEX.md` | Per-surface stability ratings |
| `COMPATIBILITY_MODEL.md` | What "stable" means and backward-compat policy |
| `COMPATIBILITY.md` | Deprecation timeline |
| `RELEASE_PLAYBOOK.md` | End-to-end release procedure |
| `RELEASE_GATES.md` | Gate criteria (Gate 0–10) |
| `TECH_DEBT.md` | Known deferred issues and per-module coverage |
| `SECURITY_POSTURE.md` | Security threat model and controls |
| `ECOSYSTEM_READINESS_ASSESSMENT.md` | Per-package maturity assessment |
| `MATURITY_CHECKLIST.md` | 72-point maturity score and re-score schedule |
| `ISSUE_RESPONSE_POLICY.md` | Issue triage and SLA |
| `FREEZE_PROPOSAL.md` | Opcode freeze declaration and post-freeze process |
| `DEPRECATIONS.md` | Active deprecations and timelines |
| `COMPANION_LIBRARY_CONTRACT.md` | Contract for companion library integration |
| `AUDIT_INDEX.md` | Index of 9 reusable audit prompts |

---

### `migration/` — Migration Guides

| File | Contents |
|---|---|
| `v2-to-v3.md` | Breaking changes from v2.x → v3.0 |
| `v3-to-v4.md` | Breaking changes from v3.x → v4.0 |
| `v4.0-patch-notes.md` | Cumulative patch notes within v4.0.x |

---

### `ecosystem/` — Companion Package Specs

Design and API specifications for the companion library ecosystem. Incubator
scaffolds live at [`packages/`](../packages/) in the repo root.

| File | Contents |
|---|---|
| `PACKAGE_QUICK_REF.md` | All 35 packages — deps, key abstractions, tier |
| `README.md` | Ecosystem overview |
| `NODUS_HTTP.md` | `nodus-http` spec |
| `NODUS_RETRY.md` | `nodus-retry` spec |
| `NODUS_A2A.md` | `nodus-a2a` spec |
| `NODUS_AGENT.md` | `nodus-agent` spec |
| `NODUS_EVENTS.md` / `NODUS_EVENT.md` | `nodus-events` spec |
| `NODUS_MEMORY.md` | `nodus-memory` spec |
| `NODUS_STORE_SQL.md` | `nodus-store-sql` spec |

---

### `security/` — Security

| File | Contents |
|---|---|
| `SECURITY_MATRIX.md` | Test matrix for sandbox and boundary enforcement |

---

### `onboarding/` — Onboarding

| File | Contents |
|---|---|
| `GETTING_STARTED.md` | Quick-start for new contributors |
| `NODUS.md` | High-level project orientation |

---

### `projects/` — Showcase Projects

Standalone Nodus projects built end-to-end using only the installed ecosystem and
the skills that ship with the language. Each one tests the skills in a real context
and serves as reference material for a future Nodus coding agent.

| File | Contents |
|---|---|
| `PROJECTS.md` | All three projects — purpose, status, architecture, next steps |

---

### `evals/` — Evaluation Results

Per-version independent evaluation reports (Stage 4/5 process).
See [`governance/EVAL_STAGE4_TEMPLATE.md`](governance/EVAL_STAGE4_TEMPLATE.md)
for the eval template.

---

## Root-Level Files

| File | Contents |
|---|---|
| `release.md` | Semver policy, release procedure, build validation |

---

## See Also

- [`llms.txt`](../llms.txt) — AI-readable canonical map of the project
- [`llms-full.txt`](../llms-full.txt) — Rich AI-readable summaries
- [`CHANGELOG.md`](../CHANGELOG.md) — Full version history
- [`governance/DOCSET_INDEX.md`](governance/DOCSET_INDEX.md) — Doc precedence rules
