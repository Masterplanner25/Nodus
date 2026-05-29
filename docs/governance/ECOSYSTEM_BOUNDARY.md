<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem Boundary

**Version:** 3.0.2
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document defines where the Nodus ecosystem ends and where it deliberately
does not go. Boundary definitions prevent scope creep without requiring a full
architectural review every time a feature request arrives.

---

## What the Nodus ecosystem is

The Nodus ecosystem is a set of coherent libraries that make Nodus credible as an
orchestration DSL across three tiers:

- **Tier 1 (bundled stdlib):** Capabilities for orchestration scripts — HTTP, filesystem,
  subprocess, hashing, datetime, encoding, secrets, test framework, tool registry
- **Tier 2 (registry, v5.0+):** Infrastructure primitives — queue adapters, container
  execution, observability, scheduling, worker pools
- **Tier 3 (registry, v4.0 launch):** Protocol adapters — MCP and A2A
- **Future Tier 3:** Agent primitives, memory, tooling schema — post-v4.0

These tiers share one architectural commitment: Nodus runtime primitives are the source
of truth. Protocols and external systems are adapters.

---

## What the Nodus ecosystem explicitly is not

### Not a general scripting ecosystem

The ecosystem does not compete with PyPI's breadth. It does not pursue:
- Regex libraries
- CSV parsers
- Template engines
- Full string processing libraries
- General math libraries

These belong to the components Nodus orchestrates. The boundary here is the
LANGUAGE_VISION.md principle: "Orchestration Composes; Capabilities Don't."

### Not a web framework ecosystem

Nodus is not a web server. Nodus is not Express. Nodus is not Flask. Nodus is not FastAPI.
The `nodus-lang[server]` optional dependency exposes an embedding host, not a web framework.

Libraries that make Nodus into a general web framework are out of ecosystem scope.

### Not a data-processing ecosystem

Nodus does not provide Pandas, NumPy, or Spark equivalents. Data processing at scale
is a component concern. Nodus calls the component that does the processing.

### Not a protocol-specific ecosystem

Nodus does not become "the MCP language" or "the A2A language." Both are protocol adapters
that plug into Nodus runtime primitives. The ecosystem exists to make Nodus capable with any
protocol, not to be owned by one.

This means: no MCP-specific syntax, no A2A-specific types, no protocol-specific opcodes.

---

## The adapter pattern: who is in the ecosystem

A library is part of the Nodus ecosystem if it:

1. Uses `std:tool.register()` to register tools (once available in v4.0)
2. Uses `NodusRuntime` for script execution
3. Targets orchestration use cases, not general scripting
4. Is distributed through the Nodus registry under the `nodus-` namespace

A library that imports Nodus as a subprocess runner or uses it incidentally is not
part of the ecosystem — it is a Nodus user. Ecosystem membership requires an
architectural relationship.

---

## Registry governance

The Nodus registry curates orchestration-focused libraries. Quality and architectural
coherence are prioritized over quantity. Criteria:

- Does the library target orchestration or automation use cases?
- Does it use Nodus runtime primitives (tools, workflows, embedding API)?
- Does it follow the `nodus-<purpose>` naming convention?
- Does it follow the err record shape convention?
- Is it maintained and tested?

The registry is not yet operational as of 3.0.2. Registry governance will be defined
before the v4.0 launch.

---

## Companion library boundary rules

For nodus-mcp and nodus-a2a specifically:

| Rule | nodus-mcp | nodus-a2a |
|------|-----------|-----------|
| Uses `std:tool` for tool registration | Yes | Yes |
| No MCP-specific or A2A-specific language syntax | Enforced | Enforced |
| No new opcodes | Enforced (`BYTECODE_VERSION=4` stable) | Enforced |
| Protocol adapter only — does not own the architecture | Yes | Yes |

---

## Reconsideration triggers

See `docs/governance/LIBRARY_ECOSYSTEM.md §"Reconsideration triggers"` for the
three triggers that would warrant revisiting these boundaries.

---

## Related documents

- `docs/governance/LIBRARY_ECOSYSTEM.md` — tier structure and architectural commitment
- `docs/governance/NODUS_POSITIONING.md` — language identity
- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — current ecosystem state
