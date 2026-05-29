<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Ecosystem Maturity Rubric

**Version:** 3.0.2 / ecosystem pre-launch
**Status:** Governing document
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This rubric defines a consistent vocabulary for assessing the maturity of Nodus companion
libraries. It distinguishes between architectural maturity, implementation completeness,
operational readiness, and production credibility. These are different dimensions that
often diverge.

Apply this rubric before describing any library's readiness to users, operators, or
dependent libraries.

---

## Maturity dimensions

Each dimension is assessed independently. A library can be architecturally strong and
operationally immature simultaneously.

### Dimension 1: Architectural coherence

Does the library's design make sense for its role in the ecosystem?

| Level | Meaning |
|-------|---------|
| **Coherent** | Design decisions are documented, justified, and consistent with Nodus primitives. No obvious structural contradictions. |
| **Partially coherent** | Core design is sound but some integration points or protocol mappings are unclear or provisional. |
| **Incoherent** | Significant design contradictions or unresolved questions that would require rework. |

### Dimension 2: Implementation completeness

What fraction of the stated scope is implemented and tested?

| Level | Meaning |
|-------|---------|
| **Complete** | All in-scope features are implemented with test coverage ≥ 80% and no known functionality gaps. |
| **Substantially complete** | ≥ 80% of in-scope features implemented; remaining gaps are documented deferrals, not oversights. |
| **Partial** | Implementation covers core cases; known significant gaps that are not yet scheduled. |
| **Stub** | Only scaffolding or a thin subset implemented. |

### Dimension 3: Operational readiness

Can an engineer run this in a production system today?

| Level | Meaning |
|-------|---------|
| **Production-credible** | Documentation is complete. Known limitations are documented. Upgrade paths exist. Observability hooks are in place. The library has been used in a real system (or rigorously tested against a real system). |
| **Prepared** | Library is built and tested. It has not been used in production. Known limitations are documented but may be incomplete. Operational procedures (monitoring, upgrade, failure handling) are partial. |
| **Development-only** | Suitable for development use. Would require hardening before production use. May lack error handling, retry logic, or observability. |
| **Experimental** | Proof of concept. Not suitable for production. Breaking changes expected. |

### Dimension 4: Stability commitment

What is the library's backward compatibility commitment?

| Level | Meaning |
|-------|---------|
| **Stable** | Explicit semver commitment. Breaking changes only in major versions. |
| **Pre-stable** | No backward compatibility commitment. Breaking changes may occur in any release. |
| **Pre-release** | Version `< 1.0.0`. By convention, no backward compatibility guarantee. |

### Dimension 5: Publication status

Is the library accessible to users?

| Level | Meaning |
|-------|---------|
| **Published** | Available on PyPI or the Nodus registry. Can be installed by any user. |
| **Prepared-unpublished** | Built, tested, packaged — but not yet on any registry. Cannot be installed by users. |
| **Development-only** | Only available as a development checkout. No distribution package. |

---

## Composite maturity labels

These labels summarize across all five dimensions for quick communication.

| Label | Meaning |
|-------|---------|
| **Production-ready** | Coherent + Complete + Production-credible + Stable + Published |
| **Pre-production** | Coherent + Complete + Prepared + Pre-stable + Published |
| **Launch-ready** | Coherent + Complete + Prepared + Pre-stable + Prepared-unpublished |
| **Development-complete** | Coherent + Substantially complete + Development-only + Pre-release + Development-only |
| **Early/real-but-early** | Coherent or Partially coherent + Partial + Development-only + Pre-release + Development-only |

---

## What these labels do NOT imply

- **"Coherent" does not mean "complete"** — a library can have an excellent architecture
  and implement only half of it.
- **"Prepared" does not mean "proven"** — a prepared library has not been used in a real
  system under real load with real failure modes.
- **"Published" does not mean "stable"** — a v0.1 published library may still break between
  versions.
- **"Production-credible" does not mean "battle-tested"** — it means the library meets the
  bar for a cautious production deployment, not that it has been through one.

---

## Applying the rubric

When writing about a companion library:

1. Pick the correct dimension for the claim you're making
2. Use the level vocabulary (not "ready," "mature," "solid," "working")
3. If a library rates differently on different dimensions, say so explicitly
4. Do not use the composite label unless all five dimensions support it

**Example (correct):**
> nodus-mcp v0.1.0 is architecturally coherent, implementation-complete for its stated
> scope (stdio and HTTP transports, no OAuth), and prepared-but-unpublished. It is not
> yet production-credible: it has not been used in a real system and lacks operational
> procedures for upgrade and monitoring. Publication waits for the coordinated launch.

**Example (incorrect):**
> nodus-mcp is ready to use and has everything you need.

---

## Related documents

- `docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md` — current-state assessment using this rubric
- `docs/governance/ECOSYSTEM_90_DAY_CHECKLIST.md` — what needs to happen before production claim
- `docs/governance/LIBRARY_ECOSYSTEM.md` — ecosystem architecture
