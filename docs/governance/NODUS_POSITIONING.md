# Nodus Positioning

**Last reviewed:** 2026-09-01, against 5.9.0
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

> **Nodus is an orchestration DSL and embedded runtime for building agentic hosts.**

That clause was decided 2026-08-26 (D1) and is pinned in `README.md`,
`pyproject.toml` — where it is the PyPI summary — and `llms.txt`. It supersedes
this document's earlier sentence, *"the programmable glue between the components
of a modern automation system"*, which is kept here only as the note below.

**This is the correction the precedence rule below made urgent rather than
academic.** That rule says this document wins any positioning conflict, and this
document carried the superseded sentence for the nine releases after D1 was
decided — so anyone applying the rule as written would have reverted the current
positioning to the old one, on this document's own authority. A governing
document that is stale is worse than one that is silent.

The older sentence is still a fair description of what Nodus *does*; it is not
the positioning, because it names the mechanism rather than who it is for.

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
| MCP adapter (nodus-mcp) | Published on PyPI; `docs/ecosystem/COMPANION_REPOS.md` |
| A2A adapter (nodus-a2a) | Published on PyPI; `docs/ecosystem/COMPANION_REPOS.md` |
| A companion ecosystem, all published | `docs/ecosystem/README.md` is the roster and the source for the count |

---

## Positioning precedence rule

When any document makes a positioning claim that conflicts with this document,
this document wins. Phase plans, design docs, and roadmap docs describe aspirations;
this document describes ground truth as of the current release.

In particular:
- Phase plans (`docs/governance/V*_PLAN.md`) describe design decisions for the
  cycle they were written for. All four — V2_1, V3_0, V3_1, V4_0 — describe
  cycles that have shipped, so they are history, not intent.
- LIBRARY_ECOSYSTEM.md describes architectural commitments and planned scope
- This document describes current identity

**The rule cuts both ways, which is the lesson this document is now the record
of.** It carried the superseded one-sentence positioning for the nine releases
after D1 replaced it, so anyone applying the rule as written would have reverted
`README.md` and `pyproject.toml` — where that sentence is the PyPI summary — to
the older one, on this document's own authority. Precedence is only worth having
where currency is maintained. Check the date above before invoking the rule.

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

This positioning holds until one of the reconsideration triggers in
`docs/governance/LIBRARY_ECOSYSTEM.md §"Reconsideration triggers"` fires:

- Adapter pattern proves architecturally inadequate
- General-purpose stdlib demand becomes overwhelming (10+ distinct-use-case issues)
- Orchestration DSL identity becomes a competitive disadvantage

**None has fired as of 5.9.0.** Checked 2026-09-01: the adapter pattern carries
the whole published companion ecosystem, no general-purpose stdlib request is
open at all (let alone ten across distinct use cases), and the identity was
sharpened rather than abandoned by D1.

This section previously read *"locked through the v4.0 cycle"*, with a trigger
status *"as of 3.0.2"*. A lock that expires with a cycle needs renewing at every
cycle boundary and never was; the triggers are the real condition, and they do
not expire. Stated that way it stays true without maintenance — the same reason
the README banner names no version.
