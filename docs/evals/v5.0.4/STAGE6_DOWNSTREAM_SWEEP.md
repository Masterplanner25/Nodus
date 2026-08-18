# Stage 6 — downstream republish sweep, v5.0.4

**Date:** 2026-08-17 · **Verdict: clean. One companion republished
(`nodus-extension` 0.1.2).**

---

## 0. Note on this sweep's standing

For every previous release, Stage 6 was the **first** time a dependent suite ran
against the new version. That is how v5.0.3 shipped a broken `nodus-sdk`: Gate 10
passed it with 32 green probes because Gate 10 validates nodus-lang against
itself, and Stage 6 found the break only after the upload, when PyPI was already
immutable.

From 5.0.4, **the dependent suites run at Gate 10 step 0, before publication**
(`tools/check_dependent_suites.py`). Stage 6 keeps what only makes sense
afterwards: published dependency ranges, and content drift against published
artifacts.

## 1. Dependency ranges

```
Do published companions admit nodus-lang 5.0.4?

companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.2      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.0.4.
```

## 2. Do they still work under 5.0.4?

Run at Gate 10 step 0, before the upload:

| Companion | Result |
|---|---|
| nodus-mcp | 363 passed |
| nodus-mcp-server | 25 passed |
| nodus-extension | 126 passed |
| nodus-sdk | **99 passed** — was 29 failed / 10 errors under 5.0.3 |
| nodus-native-memory-engine | 76 passed |
| nodus-jupyter | 32 passed |

Re-confirmed from PyPI after publication: `nodus-lang 5.0.4` + `nodus-sdk 0.1.2`
installs, `NodusSDKRuntime()` constructs, and the #185 memory isolation still
holds — so the repair did not buy compatibility by reverting the fix.

## 3. Content drift

```
nodus-mcp                    0.1.3      current (42 files match)
nodus-mcp-server             0.1.12     current (11 files match)
nodus-extension              0.1.2      current (30 files match)
nodus-sdk                    0.1.2      current (25 files match)
nodus-native-memory-engine   0.1.1      current (1 files match)
nodus-jupyter                0.1.0      current (6 files match)

No content drift.
```

### `nodus-extension` 0.1.2 — the one republish

The first pass flagged `tests/test_invariants.py` and `tests/test_phase_a.py` as
drift. Both asserted a hardcoded `"0.1.0"` and broke the moment 0.1.1 shipped —
a bump made earlier the same day to float the `nodus-lang` cap. The published
0.1.1 sdist therefore carried two failing tests that said nothing about the
package, which is the only reason this warranted a release rather than a commit.
They now compare against packaging metadata, so a bump cannot make them stale.

**The `nodus-native-memory-engine` case looked identical and was not.** Its
`test_version_matches_metadata` failed the same way, but that test compares
`__version__` to the *installed* dist-info and was correctly reporting a stale
editable install; the published artifact was fine. Changing that test would have
silenced a working check. `pip install -e . --no-deps` fixed it. Worth recording
because the two presented the same way and needed opposite responses.

### A note on reading the drift check

Immediately after publishing, the check reported `nodus-extension 0.1.1  DRIFT`
against a 0.1.2 that had just uploaded — the PyPI JSON API was still cached.
Notably the *simple* index lagged in the opposite direction a moment later,
listing only 0.1.0 and 0.1.1 while the JSON API already showed 0.1.2. Neither is
authoritative on its own straight after an upload. **Wait and re-run; do not act
on a single post-upload reading**, and never re-upload on the strength of one.

## 4. Working-tree drift

`git status --porcelain` across all twelve checkouts: **0 uncommitted files.**

## 5. Editor and CI surfaces — checked by hand

- **`nodus-vscode` 0.1.2** — no republish needed. 5.0.4 adds no keyword and no
  syntax; the change is a private attribute rename.
- **`nodus-run-action` v1.0.0** — pins a nodus-lang version in YAML, invisible to
  the content-hash sweep by construction. Users pinning `'5.0.3'` **should move**:
  that release breaks `nodus-sdk`.

## 6. Carried forward

- **5.0.3 should be treated as superseded**, not merely older. It is the one
  release in the 5.0.x line that breaks a first-party companion.
- The gate ordering changed as a direct result; see `RELEASE_GATES.md` Gate 10
  step 0, which records the failure that motivated it.
