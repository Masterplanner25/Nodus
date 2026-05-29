<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Stdlib Philosophy

**Version:** 3.0.2
**Status:** Summary document — philosophy is expressed fully in LIBRARY_ECOSYSTEM.md
**Maintainer:** Shawn Knight (Masterplanner25)

> **Note:** This document was referenced from `docs/governance/LIBRARY_ECOSYSTEM.md`
> as a "Phase 4 deliverable" that was never created. This stub satisfies the reference
> and consolidates the philosophy inline. If a fuller treatment is needed, expand here
> rather than creating another doc.

---

## The one principle

**Capabilities stay narrow. Orchestration composes.**

Stdlib modules provide focused operations. Orchestration patterns (retry, backoff,
parallelism, error recovery, rate limiting) are expressed through workflow primitives,
not baked into capability functions.

`std:http.get()` will never have a `retries` parameter. `std:subprocess.run()` will
never have `retry_on_failure`. Capability namespaces stay narrow regardless of demand.

---

## The Tier 1 ceiling

Tier 1 (bundled stdlib) is the set of capabilities that make Nodus credible as an
orchestration DSL. The ceiling is drawn here:

**In Tier 1:** HTTP client, filesystem, subprocess, hashing, datetime, encoding,
secrets, test framework, tool registry.

**Not in Tier 1:** Regex, CSV, template engines, ORMs, full string processing,
general math, web framework primitives, vendor SDKs.

The ceiling exists because Nodus competes on orchestration primitives, not stdlib
breadth. Python has 30 years of stdlib investment that Nodus cannot and should not
replicate.

---

## What "narrow" means in practice

A capability is narrow when:
- It does one thing: HTTP GET, run a subprocess, hash a string
- It returns the raw result: response body, exit code, hash bytes
- It does not add orchestration logic (retry, circuit breaker, backoff)
- It does not add policy logic (rate limiting, quota enforcement)

Orchestration logic belongs in workflow steps. Policy logic belongs in libraries
that compose workflow primitives.

---

## Where this is expressed in full

The authoritative statements of stdlib philosophy are in:

- `docs/language/LANGUAGE_VISION.md §"Design Philosophy" principle #6` —
  "Orchestration Composes; Capabilities Don't"
- `docs/governance/LIBRARY_ECOSYSTEM.md §"What this ecosystem explicitly does NOT pursue"` —
  the not-pursued list with rationale
- `docs/governance/LIBRARY_ECOSYSTEM.md §"Tier 1 ceiling"` — the specific Tier 1 boundary
- `docs/language/STYLE_GUIDE.md §18` — "Retry, Backoff, and Recovery" (assumed; verify)
- `docs/language/DESIGN.md §"Capability Surfaces Stay Narrow"` (assumed; verify)
