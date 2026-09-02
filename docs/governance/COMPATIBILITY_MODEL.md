# Compatibility Model

**Last reviewed:** 2026-09-01, against 5.9.0
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
| Add new syntax as a **reserved** keyword | Breaking (keyword collision) | Major |
| Add new syntax as a **contextual** keyword | Non-breaking | Minor |
| Remove a deprecated feature | Breaking | Major, with prior deprecation |
| Add new stdlib function to existing module | Non-breaking | Minor |
| Fix a bug where behavior was wrong but programs relied on it | Breaking | Major (if relied on) |
| Fix a bug where behavior was wrong and no correct program relied on it | Non-breaking | Patch |
| Change an experimental surface | Non-breaking | Any |

**Contextual keywords are the row that carries the practice.** `over`, `until`,
`budget`, `reached`, `retry` (5.0.0) and `each` (5.6.0) all shipped in minors and
all remain usable as identifiers — which is the whole reason they were made
contextual. Add one to a set in `lexer.py` and read it from there; a bare string
literal in `parser.py` is invisible to `lexer.ALL_KEYWORDS`, which editors, docs
and `nodus_gate --consumers` all read
([#480](https://github.com/Masterplanner25/Nodus/issues/480)).

### 1.3 The v2.x exception (historical)

The v2.x cycle operated without strict semver. `json.parse` behavior changed in v2.1.0
without a major version bump. This exception is closed — v3.0 and later apply strict semver.

See `docs/governance/VERSIONING.md` and `docs/release.md` for the full policy.

### 1.4 No source compatibility guarantee for experimental surfaces

Experimental surfaces carry no source compatibility guarantee. They may change in any
release. Scripts using them must track `CHANGELOG.md`.

**Which surfaces those are is in `LANGUAGE_STABILITY_INDEX.md` and is not restated
here.** This paragraph used to name "workflows, goals, coroutines, channels" — and
`workflow` / `goal` / `step` and `spawn` / `coroutine` / `channel` all graduated to
**Mostly Stable** at v4.0.5. `STABILITY.md` carried the same wrong classification and
was corrected in the same review; two documents restating one classification is how it
went wrong in both.

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
- An event subscription API and module loading hooks are still unimplemented as of
  5.9.0, and will be additive when shipped

**Three additions since this section was written are worth naming**, because each is
a supported surface an embedder may depend on: `capability_policy` and
`approval_channel` (#405), the per-runtime state parameters `memory_store` /
`agent_registry` / `workflow_runner` / `share_process_state` (#185, #390), and
`agent_timeout_ms` (#424). `GATED_BUILTINS` and `NodusRuntime.active_vm()` are
published surfaces too (#441-#444).

**Do not add `**kwargs` to `NodusRuntime.__init__`, and keep the confinement flags
keyword-only.** With a catch-all, a renamed flag is silently swallowed and the guest
runs unconfined with every mock-based test on the embedder's side still green. Both
are pinned by test.

---

## 3. Bytecode compatibility

### 3.1 Bytecode version

The bytecode version is `BYTECODE_VERSION = 4`, located in `src/nodus/compiler/compiler.py`.
When the bytecode format changes (new opcodes, changed operand layout, changed serialization),
the bytecode version is bumped.

### 3.2 Bytecode compatibility commitment

- The VM will not execute bytecode from a different `BYTECODE_VERSION`
- When `BYTECODE_VERSION` bumps, all cached bytecode (`.nodus/cache/`) is invalidated and
  recompiled transparently. So does a `nodus-lang` version change, and — since
  [#704](https://github.com/Masterplanner25/Nodus/issues/704) — a change to the
  source's **content**: the key is `source_sha256`, not path + mtime, because two
  edits inside the platform's timestamp resolution were one program to the old key
- Applications that persist compiled bytecode (not just source) must recompile on version bump
- The opcode set is **frozen as of v1.0** and requires the opcode addition procedure in
  `RELEASE_CHECKLIST.md`, now enforced by `nodus_gate --opcodes`

**The freeze has been broken once, in minors, and that is recorded rather than
tidied.** `MOD` and `RESET_LOCAL_IDX` were added after v1.0 without a major bump and
without `BYTECODE_VERSION` moving — 49 active opcodes today, not the 47 frozen. It
was found by a doc sweep in 2026-08-07, not by a gate, which is why the gate exists
now ([#366](https://github.com/Masterplanner25/Nodus/issues/366)); `BYTECODE_VERSION`
was deliberately left at 4. Read "new opcodes only in majors" as the intent the gate
now protects, not as a claim about what has always happened.

### 3.3 No bytecode cross-version portability

Nodus does not guarantee that bytecode compiled by version `X.Y.Z` will execute on
version `X.Y+1.Z`. Source compatibility is guaranteed; bytecode portability is not. Always
distribute `.nd` source, not compiled bytecode.

---

## 4. Library and package compatibility

### 4.1 Standard library modules

Changes to stdlib module APIs follow source compatibility rules (§1). Modules marked
Stable in `LANGUAGE_STABILITY_INDEX.md` are subject to major-version-only breaking changes.

### 4.2 Companion library compatibility

Companion libraries maintain independent semver and ship on **PyPI** — there is no
Nodus registry, and this section said "registry libraries" until 2026-09-01. A
companion's compatibility with `nodus-lang` is declared via its `requires-python` and
its `nodus-lang>=X.Y.Z` floor.

### 4.3 Companion libraries do not cap `nodus-lang`

**Decided 2026-08-17. This reverses F0-07, recorded below.** A companion declares a
floor (`nodus-lang>=X.Y.Z`) and no upper bound.

A hard upper bound on a first-party dependency turns every major into a two-repo
release train with consumers frozen in between. The companion's own suite catches a
real break; a cap earns its place once a break is *known*, not before.

Never read a range by eye — run `tools/check_downstream_constraints.py`, which
resolves ranges with `packaging` against **published** metadata. A floated cap
sitting unreleased in a companion's `main` helps nobody.

### 4.3a Decision record — F0-07 (2026-05-29): cap companions at `<5.0.0` — **REVERSED**

**Original decision:** cap the `nodus-lang` dependency at `<5.0.0`, on the reasoning
that a v0.1 adapter validated only against 4.x must not claim forward-compatibility
with an unreleased major, and that an open bound would let `pip` silently resolve a
major the companion had never been tested against.

**What happened.** Five of six companions published `nodus-lang<5.0.0`, so
`pip install nodus-lang==5.0.0 nodus-mcp` was `ResolutionImpossible` and
**5.0.0 was unadoptable for anyone using the ecosystem** ([#445](https://github.com/Masterplanner25/Nodus/issues/445)).
The cap did not create a deliberate re-validation point; it created an outage that
nobody here noticed. It was reported by the aindy-runtime team.

**Two things it cost, both worth keeping:**

- **`>=4.0.0,<5.0.0` reads as "admits 4.x", which is what the eye checks for.** The
  clause that forbids the new version is at the far end of the string. The Stage 6
  sweep had asked exactly this question and transcribed five of six ranges with the
  upper bound dropped. That is not a lapse more care fixes — resolve it with
  `packaging`.
- **A passing companion suite says nothing about installability.** Every dependent
  suite passed against 5.0.0, run against dev source. Those companions could not have
  been reached through a normal `pip install` at all.

**Status:** superseded by §4.3. `nodus-mcp` declares `nodus-lang>=4.0.0`, uncapped.
Kept here rather than deleted, because the reasoning was sound and still reads
convincingly — which is exactly why the outcome is worth recording next to it.

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

Checked 2026-09-01 against 5.9.0:
- `.tl` legacy extension — still accepted, still warns, no removal date set
- `language.py` / `language.bat` launchers (warned; no removal date set)
- `math.log_base` (removed in 3.0.2 — replaced by `math.log(n, base)`)

**Three changes are staged to become errors at 6.0.0** and warn today, which is a
deprecation in everything but name: an unrecognised type name (#609), a concurrent
write that loses an update (#547), and record equality (#545). A project that is
clean now can still be red at the major, so treat those warnings as a to-do list.

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
