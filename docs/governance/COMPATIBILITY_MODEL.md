<!-- Authored by Codex during non coding session. Needs review before repo commit and push. -->

# Compatibility Model

**Version:** 3.0.2
**Status:** Governing document — supersedes `docs/governance/COMPATIBILITY.md` for policy;
COMPATIBILITY.md remains as the deprecation timeline record.
**Maintainer:** Shawn Knight (Masterplanner25)

---

## Purpose

This document answers: *what breaks, and when?* It is a policy document, not a timeline.
For the timeline of specific deprecations and removals, see `docs/governance/COMPATIBILITY.md`.

---

## 1. Source compatibility

### 1.1 What source compatibility means

Source compatibility means that a `.nd` script that runs correctly on version `X.Y.Z` will
run correctly on a later version without modification, *for the stable language surfaces*
defined in `docs/governance/LANGUAGE_STABILITY_INDEX.md`.

### 1.2 Breaking vs. non-breaking source changes

| Change type | Classification | Version bump required |
|-------------|----------------|----------------------|
| Remove a stable language construct | Breaking | Major |
| Change behavior of a stable construct | Breaking | Major |
| Add new syntax (reserved keywords) | Breaking (keyword collision) | Major |
| Remove a deprecated feature | Breaking | Major, with prior deprecation |
| Add new stdlib function to existing module | Non-breaking | Minor |
| Fix a bug where behavior was wrong but programs relied on it | Breaking | Major (if relied on) |
| Fix a bug where behavior was wrong and no correct program relied on it | Non-breaking | Patch |
| Change an experimental surface | Non-breaking | Any |

### 1.3 The v2.x exception (historical)

The v2.x cycle operated without strict semver. `json.parse` behavior changed in v2.1.0
without a major version bump. This exception is closed — v3.0 and later apply strict semver.

See `docs/governance/VERSIONING.md` and `docs/release.md` for the full policy.

### 1.4 No source compatibility guarantee for experimental surfaces

Experimental surfaces (workflows, goals, coroutines, channels, new v4.0 stdlib modules)
carry no source compatibility guarantee. They may change in any release. Scripts using
experimental surfaces must track CHANGELOG.md.

---

## 2. Embedding API compatibility

### 2.1 What the embedding API is

The embedding API is the Python-level interface for host applications embedding Nodus:

- `NodusRuntime(...)` and its constructor parameters
- `run_source()`, `run_file()`, `register_function()`, `reset()`
- The result dict shape from `run_source()` / `run_file()`
- `from nodus import NodusRuntime`

### 2.2 Embedding API stability commitment

The embedding API is **stable since v1.0 (2026-03-15)**. The commitment is:

- Existing code that constructs `NodusRuntime` with any documented parameters will not
  break in a minor or patch release
- New optional constructor parameters may be added in minor releases
- Result dict keys (`ok`, `stdout`, `stderr`, `error`) are stable
- Removal of any stable embedding API function requires a major version bump

### 2.3 Embedding API non-stable areas

- `host_globals` and `initial_globals` are Mostly Stable: the passing convention is stable
  but the semantics may be refined
- The event subscription API (not yet implemented in 3.0.2) will be additive when shipped
- Module loading hooks (not yet in 3.0.2) will be additive when shipped

---

## 3. Bytecode compatibility

### 3.1 Bytecode version

The bytecode version is `BYTECODE_VERSION = 4`, located in `src/nodus/compiler/compiler.py`.
When the bytecode format changes (new opcodes, changed operand layout, changed serialization),
the bytecode version is bumped.

### 3.2 Bytecode compatibility commitment

- The VM will not execute bytecode from a different `BYTECODE_VERSION`
- When `BYTECODE_VERSION` bumps, all cached bytecode (`.nodus/cache/`) is invalidated and
  recompiled transparently
- Applications that persist compiled bytecode (not just source) must recompile on version bump
- The opcode set is **frozen as of v1.0** — new opcodes may only be added in major versions,
  and require the opcode addition procedure in `RELEASE_CHECKLIST.md`

### 3.3 No bytecode cross-version portability

Nodus does not guarantee that bytecode compiled by version `X.Y.Z` will execute on
version `X.Y+1.Z`. Source compatibility is guaranteed; bytecode portability is not. Always
distribute `.nd` source, not compiled bytecode.

---

## 4. Library and package compatibility

### 4.1 Standard library modules

Changes to stdlib module APIs follow source compatibility rules (§1). Modules marked
Stable in `LANGUAGE_STABILITY_INDEX.md` are subject to major-version-only breaking changes.

### 4.2 Registry library compatibility

Registry libraries (`nodus-mcp`, `nodus-a2a`, future libraries) maintain independent
semver. A registry library's compatibility with `nodus-lang` is declared via its
`requires-python` and `nodus-lang>=X.Y.Z` dependency specifier.

### 4.3 Companion library dependency on nodus-lang 4.0.0

Both `nodus-mcp` and `nodus-a2a` declare `nodus-lang>=4.0.0` as a dependency. This means:
- Neither library can be used with nodus-lang 3.0.2
- Both libraries wait for the coordinated three-artifact launch (nodus-lang 4.0.0 + nodus-mcp
  0.1.0 + nodus-a2a 0.1.0) before being published
- Until the launch, both libraries are development-only (not on PyPI)

---

## 5. Deprecation policy

### 5.1 Deprecation signals

A feature is deprecated when:
1. A CHANGELOG entry records the deprecation with a reason
2. The CLI emits a warning when the deprecated feature is used
3. The feature appears in `docs/governance/COMPATIBILITY.md` with a timeline

### 5.2 Minimum deprecation lifetime

Deprecated features remain supported for at least one major version cycle after the
deprecation announcement, except for security-critical removals (sandbox bypass fixes
are applied as patches regardless of deprecation state).

### 5.3 Currently deprecated items

See `docs/governance/COMPATIBILITY.md` for the current deprecation timeline.

As of 3.0.2:
- `.tl` legacy extension (warned; no removal date set)
- `language.py` / `language.bat` launchers (warned; no removal date set)
- `math.log_base` (removed in 3.0.2 — replaced by `math.log(n, base)`)

---

## 6. Security exception

Security fixes that close sandbox bypasses or path traversal vulnerabilities are applied
as **patch releases** regardless of whether they break scripts that relied on the bug.
Scripts relying on a sandbox bypass were relying on a bug, not a feature.

Example: `allowed_paths` enforcement (BUG-046, v2.1.1) was applied as a patch even though
it changed observable behavior for scripts that bypassed the sandbox.

---

## 7. Compatibility reading order

When multiple documents make compatibility claims:

1. This document (COMPATIBILITY_MODEL.md) — authoritative policy
2. `docs/governance/LANGUAGE_STABILITY_INDEX.md` — per-surface classification
3. `docs/governance/VERSIONING.md` — version bump rules
4. `docs/governance/COMPATIBILITY.md` — deprecation timeline
5. CHANGELOG.md — specific version history

Lower-numbered documents win in case of conflict.
