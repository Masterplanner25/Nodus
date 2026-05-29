<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Nodus Positioning

**Version:** 3.0.2 (current)
**Status:** Governing document — supersedes any positioning claims in older docs
**Maintainer:** Shawn Knight (Masterplanner25)

---

## What Nodus is

Nodus is a **domain-specific execution language for orchestration, workflows, agents,
and runtime automation.** It is bytecode-compiled and runs on a deterministic stack-based
VM implemented in Python.

The language's job is to express coordination logic: sequencing work, routing
data, handling failures, scheduling tasks, and calling capabilities. It is not a
general-purpose language. It is a scripting layer optimized for the glue that holds
heterogeneous systems together.

---

## The one-sentence positioning

> **Nodus is the programmable glue between the components of a modern automation system.**

Longer form: you used to need Python + bash + YAML + LangChain to wire a workflow
together. Nodus replaces the wiring without replacing the components. The components
(APIs, ML models, databases, shell tools) stay where they are. Nodus calls them through
`std:http`, `std:subprocess`, MCP tools, and A2A agents — and orchestrates them through
workflows, task graphs, and coroutines.

---

## What Nodus is not

These are standing boundary decisions, not provisional deferrals:

- **Not a general-purpose language.** Python exists. JavaScript exists. Nodus does not
  compete on stdlib breadth. It competes on orchestration primitives.
- **Not a web framework or app server.** Nodus is an HTTP client, not an HTTP server.
  `nodus-lang[server]` provides an embedding host, not a web framework.
- **Not a data-processing language.** CSV, regex, full string processing are component
  concerns. Nodus calls the component that does the parsing.
- **Not a systems language.** No memory management, no unsafe, no FFI. Python's runtime
  is the host; Nodus manages its own value stack above it.
- **Not a replacement for bash.** `std:subprocess` makes Nodus capable of calling shell
  commands, but bash remains the shell. Nodus orchestrates; it doesn't supplant.
- **Not a configuration DSL.** YAML and TOML remain configuration formats. Nodus scripts
  express behavior, not schema.

---

## Core identity claims (verifiable)

| Claim | Evidence |
|-------|----------|
| Bytecode-compiled | `src/nodus/compiler/compiler.py`, BYTECODE_REFERENCE.md |
| Stack-based VM | `src/nodus/vm/vm.py`, RUNTIME.md |
| Deterministic scheduler | Round-robin, budget-enforced; `runtime/scheduler.py` |
| Coroutines, channels, task graphs | Implemented and tested; WORKFLOWS.md |
| Embeddable via `NodusRuntime` | Stable API since v1.0; EMBEDDING.md |
| MCP adapter (nodus-mcp) | Real repo, 280 tests, prepared v0.1.0 |
| A2A adapter (nodus-a2a) | Real repo, 169 tests, prepared v0.1.0 |

---

## Positioning precedence rule

When any document makes a positioning claim that conflicts with this document,
this document wins. Phase plans, design docs, and roadmap docs describe aspirations;
this document describes ground truth as of the current release.

In particular:
- v4.0 plan documents describe design decisions for a future release
- LIBRARY_ECOSYSTEM.md describes architectural commitments and planned scope
- This document describes current identity, which v4.0 will extend but not replace

---

## What "orchestration DSL" means concretely

An orchestration DSL provides exactly these capabilities:

1. **Sequencing** — run A, then B, then C with error handling between
2. **Parallelism** — spawn A and B concurrently, collect results
3. **Retry / recovery** — retry failed steps with backoff, via workflow primitives
4. **Checkpointing** — persist workflow state, resume after failure
5. **Capability invocation** — call HTTP APIs, shell commands, tools, and agents
6. **Event handling** — react to runtime events and external signals

Nodus provides all six. It does not provide:
- Data transformation at scale (that's a capability)
- Complex string parsing (that's a capability)
- ML inference (that's a tool or agent call)

---

## Identity stability

This positioning is locked through the v4.0 cycle. The only trigger for
revisiting it is documented in `docs/governance/LIBRARY_ECOSYSTEM.md §"Reconsideration
triggers"`:

- Adapter pattern proves architecturally inadequate
- General-purpose stdlib demand becomes overwhelming (10+ distinct-use-case issues)
- Orchestration DSL identity becomes a competitive disadvantage

None of these has fired as of 3.0.2.
