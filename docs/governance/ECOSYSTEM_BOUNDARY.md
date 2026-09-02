# Ecosystem Boundary

**Last reviewed:** 2026-09-01, against 5.9.0
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

- **Tier 1 — bundled stdlib.** Capabilities for orchestration scripts, shipped
  inside `nodus-lang`.
- **Tier 2 — infrastructure primitives.** Queue adapters, container execution,
  observability, scheduling, worker pools.
- **Tier 3 — protocol adapters and agent runtime.** MCP, A2A, agent primitives,
  memory, tooling schema.

**Tier membership is listed in `LIBRARY_ECOSYSTEM.md`; what has actually shipped
is in `docs/ecosystem/README.md`.** Neither list is restated here.

These tiers share one architectural commitment: Nodus runtime primitives are the source
of truth. Protocols and external systems are adapters.

**Tiers 2 and 3 ship on PyPI, not through a Nodus registry** — see *Distribution*
below. The tier labels in this document previously said "(registry, v5.0+)" and
"(registry, v4.0 launch)", which named both the wrong channel and dates that have
passed.

---

## What the Nodus ecosystem explicitly is not

### Not a general scripting ecosystem

The ecosystem does not compete with PyPI's breadth. It does not pursue:
- Regex libraries
- CSV parsers
- Template engines
- Full string libraries
- General math libraries — linear algebra, statistics, matrices, complex numbers

These belong to the components Nodus orchestrates. The boundary here is the
LANGUAGE_VISION.md principle: "Orchestration Composes; Capabilities Don't."

**Note what this does not exclude.** `std:strings` (11 functions) and `std:math`
(26, including bitwise) are bundled Tier 1 modules and always have been. The
boundary is against *libraries* of general-purpose breadth, not against a narrow
capability that happens to touch strings or arithmetic. The last two bullets read
"full string processing libraries" and "general math libraries" until 2026-09-01,
which appeared to rule out two modules that ship — the same wording problem
`STDLIB_PHILOSOPHY.md` carried, in the second of the two documents that state
this boundary.

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

1. Uses `std:tool.register()` to register tools
2. Uses `NodusRuntime` for script execution
3. Targets orchestration use cases, not general scripting
4. Is published under the `nodus-` namespace

A library that imports Nodus as a subprocess runner or uses it incidentally is not
part of the ecosystem — it is a Nodus user. Ecosystem membership requires an
architectural relationship.

The contract a companion must meet is
`docs/governance/COMPANION_LIBRARY_CONTRACT.md`; the checkout paths and per-repo
gotchas are in `docs/ecosystem/COMPANION_REPOS.md`.

---

## Distribution

**Companions are distributed on PyPI under the `nodus-` namespace.** Two
consumers are not: `nodus-vscode` (VS Code Marketplace) and `nodus-run-action`
(GitHub Action). Those two are tracked in `tools/consumers.json` and reported by
`nodus_gate --consumers`, because the Stage 6 sweep hashes published sdists and
structurally cannot see either.

The package-manager surface (`nodus install`, `nodus login`, `--registry`) exists
and takes a registry URL, but no first-party package is distributed that way.

Curation criteria, applied at publish time rather than by a registry:

- Does the library target orchestration or automation use cases?
- Does it use Nodus runtime primitives (tools, workflows, embedding API)?
- Does it follow the `nodus-<purpose>` naming convention?
- Does it follow the err record shape convention?
- Is it maintained and tested?

**This section previously said "The registry is not yet operational as of 3.0.2.
Registry governance will be defined before the v4.0 launch."** v4.0 launched, and
five minors have shipped since; registry governance was never defined because the
ecosystem went to PyPI instead. The membership criterion above read *"is
distributed through the Nodus registry"*, which **no ecosystem member satisfied**
— a governing test that every real member failed, for nine releases.

---

## Companion library boundary rules

These apply to **every** companion, not only the two protocol adapters this table
originally named:

| Rule | Status |
|------|--------|
| Registers tools through `std:tool`, not a private mechanism | Required |
| No protocol-specific language syntax | Enforced — no companion has ever added grammar |
| No new opcodes | Enforced — `BYTECODE_VERSION` is **4** and the set is frozen at **49**, checked by `nodus_gate --opcodes` |
| Adapter only — does not own the architecture | Required |
| Does not cap `nodus-lang` | Required — decided 2026-08-17; a hard upper bound turns every major into a two-repo release train. See `tools/check_downstream_constraints.py` |

The third row is the only one a gate can check, and it checks it in the core repo
rather than per companion: an opcode cannot be added by a companion at all.

---

## Reconsideration triggers

See `docs/governance/LIBRARY_ECOSYSTEM.md §"Reconsideration triggers"` for the
three triggers that would warrant revisiting these boundaries.

---

## Related documents

- `docs/governance/LIBRARY_ECOSYSTEM.md` — tier structure and architectural commitment
- `docs/governance/NODUS_POSITIONING.md` — language identity
- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — current ecosystem state
