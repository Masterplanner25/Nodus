# Stdlib Philosophy

**Last reviewed:** 2026-09-01, against 5.9.0
**Status:** Summary — `LIBRARY_ECOSYSTEM.md` holds the tier lists and the ceiling
**Maintainer:** Shawn Knight (Masterplanner25)

> **Note:** This document was referenced from `docs/governance/LIBRARY_ECOSYSTEM.md`
> as a "Phase 4 deliverable" that was never created. This stub satisfies the
> reference and states the philosophy inline. If a fuller treatment is needed,
> expand here rather than creating another doc.

---

## The one principle

**Capabilities stay narrow. Orchestration composes.**

Stdlib modules provide focused operations. Orchestration patterns (retry, backoff,
parallelism, error recovery, rate limiting) are expressed through workflow primitives
and through modules that compose them — never baked into a capability function.

`std:http.get()` will never have a `retries` parameter. `std:subprocess.run()` will
never have `retry_on_failure`. Capability namespaces stay narrow regardless of demand.

Note what this does *not* forbid: `std:retry` and `std:circuit_breaker` both ship
in Tier 1. The rule is about where orchestration logic **lives**, not whether the
stdlib may contain any. A separate module you compose is the intended shape; a
parameter on a capability call is the one ruled out.

---

## What "narrow" means in practice

A capability is narrow when:
- It does one thing: HTTP GET, run a subprocess, hash a string
- It returns the raw result: response body, exit code, hash bytes
- It does not add orchestration logic (retry, circuit breaker, backoff)
- It does not add policy logic (rate limiting, quota enforcement)

Orchestration logic belongs in workflow steps, or in a module that composes
workflow primitives. Policy logic belongs in libraries.

---

## The Tier 1 ceiling

Tier 1 (bundled stdlib) is the set of capabilities that make Nodus credible as an
orchestration DSL. **The membership list lives in
[`LIBRARY_ECOSYSTEM.md § "Tier 1 — Bundled stdlib"`](./LIBRARY_ECOSYSTEM.md), and
only there.** Do not restate it here — see below for what happened when this
document did.

The ceiling, stated there and repeated here because it is the philosophy rather
than the inventory:

> No general-purpose scripting expansion — **regex, CSV, full string library**.
> These belong to the components Nodus orchestrates, not to Nodus itself.

Also outside it: template engines, ORMs, web framework primitives, vendor SDKs.

The ceiling exists because Nodus competes on orchestration primitives, not stdlib
breadth. Python has 30 years of stdlib investment that Nodus cannot and should not
replicate. The conditions under which the ceiling is revisited are the
reconsideration triggers in `LIBRARY_ECOSYSTEM.md` — for Tier 1 specifically, 10+
issues across distinct use cases requesting the same general-purpose addition.

### Why the lists that used to be here are gone

Reviewed against the tree on 2026-09-01. This document carried its own two-sided
enumeration, and both sides were wrong:

- **"In Tier 1" named nine capabilities.** `src/nodus/stdlib/` ships around twenty
  modules. Missing from the list: `json`, `math`, `strings`, `collections`,
  `path`, `env`, `time`, `async`, `sys`, `identity`, `effects`, `memory`, `retry`,
  `circuit_breaker`, `runtime`, `utils`, `tools`, `agent`, `bool`.
- **"Not in Tier 1" named "full string processing" and "general math"** — and
  `std:strings` and `std:math` are bundled Tier 1 modules, listed as such in the
  document this one names as authoritative. The two are not general-purpose
  libraries (11 and 26 functions; no regex, no formatting, no linear algebra, no
  statistics), so the intent was sound and only the wording excluded them. But a
  governing sentence that appears to rule out a module that ships is a sentence
  someone will act on.

The fix is not a corrected list. Two lists of one membership will drift again,
which is this repository's most-documented failure shape. **Name the set once.**

---

## Where this is expressed in full

All five references verified present 2026-09-01:

- `docs/language/LANGUAGE_VISION.md §6` — "Orchestration Composes; Capabilities Don't"
- `docs/governance/LIBRARY_ECOSYSTEM.md § "Tier 1 — Bundled stdlib"` — the membership list and the ceiling
- `docs/governance/LIBRARY_ECOSYSTEM.md § "What this ecosystem explicitly does NOT pursue"` — the not-pursued list with rationale
- `docs/language/STYLE_GUIDE.md §18` — "Retry, Backoff, and Recovery"
- `docs/language/DESIGN.md § "Capability Surfaces Stay Narrow"`

The last two carried an `(assumed; verify)` annotation from 2026-05-29. Both
exist and say what this document claims they say; the annotation is resolved.
