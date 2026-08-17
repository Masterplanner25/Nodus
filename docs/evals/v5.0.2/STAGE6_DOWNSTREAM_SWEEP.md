# Stage 6 — downstream republish sweep, v5.0.2

**Date:** 2026-08-17 · **Verdict: clean. Nothing outstanding.**

Run after PyPI publication and the GitHub release. Purpose: find companions that
the new release breaks, admits by accident, or leaves behind.

---

## 1. Dependency ranges

`tools/check_downstream_constraints.py`, output pasted verbatim — summarising is
what went wrong in the v5.0.0 sweep:

```
Do published companions admit nodus-lang 5.0.2?

companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.1      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.0.2.
```

Exit 0. Reads **published** PyPI metadata and resolves it with `packaging`, so a
cap floated in a companion's `main` but not released would still fail it.

All six float since the 5.0.1 cycle, when five of them were republished to remove
`<5.0.0` caps that had made 5.0.0 unadoptable. Nothing further was needed here.

## 2. Do they still work under 5.0.2?

5.0.2 changes two things a companion could notice, and neither is a surface they
use:

- Annotation and workflow lowerings now emit bound builtin calls (#411). No API
  change; a companion would only see this if it depended on being able to shadow
  `effect_resolve`, `retry_call` or `workflow_state`, which is the behaviour being
  removed.
- The bytecode cache now invalidates across a nodus-lang version change (#449).
  The visible effect is that the **first** run after upgrading recompiles cached
  modules. That is the fix working, and it costs one compile.

No companion declares a dependency on either surface. The compatibility question
was exercised directly at 5.0.1 (every dependent suite run against the new
release); nothing in 5.0.2 changes an API those suites touch.

## 3. Content drift

Published sdist/wheel files hashed against local source, line endings normalised.
No git heuristics, per `CLAUDE.md`.

```
package                      published  verdict
------------------------------------------------------------------------
nodus-mcp                    0.1.3      current (42 files match)
nodus-mcp-server             0.1.12     current (11 files match)
nodus-extension              0.1.1      current (30 files match)
nodus-sdk                    0.1.2      current (25 files match)
nodus-native-memory-engine   0.1.1      current (1 files match)
nodus-jupyter                0.1.0      current (6 files match)

No content drift.
```

`nodus-native-memory-engine` matching only one file is the known consequence of it
publishing no sdist — see
[nodus-native-memory-engine#3](https://github.com/Masterplanner25/nodus-native-memory-engine/issues/3),
filed during the 5.0.1 sweep. Still open, still not caused by any nodus-lang
release; it remains uninstallable on Linux, macOS, or Python 3.12+.

## 4. Working-tree drift

`git status --porcelain` across all twelve checkouts: **0 uncommitted files.**

## 5. Editor and CI surfaces — checked by hand

Neither is on PyPI, so neither is visible to §1 or §3.

- **`nodus-vscode` 0.1.2** — no republish needed. 5.0.2 adds **no keyword and no
  syntax**; the reserved `__nodus_builtin__` prefix is compiler-internal and never
  appears in source (the compiler rejects it), so the TextMate grammar is
  unaffected. Recorded so that "not republished" is a decision rather than an
  omission.
- **`nodus-run-action` v1.0.0** — pins a nodus-lang version in YAML, so it is
  invisible to the content-hash sweep by construction. Users pinning `'5.0.0'` or
  `'5.0.1'` are unaffected and can move to `'5.0.2'` when they choose. Worth their
  while: without #449, a pinned upgrade inside a cached workspace would not apply
  a compiler fix.

## 6. Also noted during the sweep

- **A stale bytecode cache masks compiler changes during development.** This cost
  real time during the #411 work: the fix appeared not to work because `.nodus/`
  held bytecode from the previous compiler. That is exactly what #449 fixes for
  *users*, but a developer editing `src/` in place still has no version bump to
  trigger invalidation. **If a compiler edit seems to have no effect, `rm -rf
  .nodus` before debugging anything else.**
- **The eval scripts had been read doubled in every previous Gate 10** — see
  #453 and this cycle's `CREATOR_VALIDATION.md` §1. Not a companion issue, but it
  is the reason this release's eval line counts differ from 5.0.1's for unchanged
  scripts.
