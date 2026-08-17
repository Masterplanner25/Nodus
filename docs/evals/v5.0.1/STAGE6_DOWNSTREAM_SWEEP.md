# Stage 6 — downstream republish sweep, v5.0.1

**Date:** 2026-08-17 · **Verdict: clean for this release. One pre-existing
finding filed (`nodus-native-memory-engine` platform coverage).**

Run after PyPI publication and the GitHub release. Purpose: find companions that
the new release breaks, admits by accident, or leaves behind.

This sweep is unusual in that **its own subject matter is the previous sweep's
mistake.** v5.0.0's Stage 6 read six dependency ranges by eye and transcribed five
with the upper bound dropped, concluding "no companion caps its range" when only
one of six could install alongside the release. This one runs a command instead.

---

## 1. Dependency ranges

`tools/check_downstream_constraints.py`, new in this release. Output pasted
verbatim rather than summarised — the summarising is what went wrong last time:

```
Do published companions admit nodus-lang 5.0.1?

companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.1      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.0.1.
```

Exit 0. The check reads **published** PyPI metadata and resolves it with
`packaging`, so a floated cap sitting unreleased in a companion's `main` would
still fail it.

Five of these six were republished today precisely to make this line true —
nodus-mcp 0.1.3, nodus-mcp-server 0.1.12, nodus-extension 0.1.1, nodus-sdk 0.1.2,
nodus-native-memory-engine 0.1.1. Their suites had passed against 5.0.0 unchanged
throughout (363 / 25 / 126 / 99 / 76); only the metadata ever blocked.

### Confirmed by installation, not only by metadata

Metadata analysis is what the last sweep got wrong, so this one also resolves for
real. In a clean venv against PyPI:

```
$ pip install "nodus-lang==5.0.1" "nodus-mcp>=0.1.2"
nodus-lang  5.0.1
nodus-mcp   0.1.3
```

and the full set — nodus-lang with nodus-mcp, nodus-extension, nodus-sdk,
nodus-mcp-server and nodus-jupyter — installs together, runs a script, and still
refuses `subprocess_run` by default.

## 2. Do they still work under 5.0.1?

5.0.1 is additive: new exports, new tests, documentation. No behaviour change, no
new syntax, no bytecode change. The compatibility question was already answered
during the 5.0.0 remediation earlier the same day, when every dependent suite was
run against 5.0.0:

| Companion | Result |
|---|---|
| nodus-mcp | **363 passed** |
| nodus-mcp-server | **25 passed** |
| nodus-extension | **126 passed** |
| nodus-sdk | **99 passed** (was 98 + 1 stale self-version failure; fixed in 0.1.2) |
| nodus-native-memory-engine | **76 passed** |

Note nodus-mcp's `test_phase_m.py::test_m2_bearer_wrong_returns_401` — documented
in `CLAUDE.md` as a pre-existing port-conflict flake and a failure in the 5.0.0
sweep — **passed this time**, consistent with the machine's transient degradation
having cleared.

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

## 4. Finding — `nodus-native-memory-engine` matched only 1 file

Not drift, and the low count is the finding rather than a defect in the check.

That package publishes **no sdist** — only `cp311-win_amd64` wheels, for both
0.1.0 and 0.1.1 — so there is almost nothing to hash. Following that up:

```
0.1.0 ['nodus_native_memory_engine-0.1.0-cp311-cp311-win_amd64.whl']
0.1.1 ['nodus_native_memory_engine-0.1.1-cp311-cp311-win_amd64.whl']
requires_python: >=3.11
```

So `pip install nodus-native-memory-engine` fails with *no matching distribution*
on Linux, on macOS, and on Windows with Python 3.12 or later. Only Windows +
CPython 3.11 can install it, despite `requires_python` advertising `>=3.11`.

The package **already has a pure-Python fallback for every operation** — the
capability to serve other platforms exists and simply isn't published. Filed as
[nodus-native-memory-engine#3](https://github.com/Masterplanner25/nodus-native-memory-engine/issues/3);
fix direction is a `py3-none-any` fallback wheel alongside the platform wheels,
and cibuildwheel for the native path later.

**Pre-existing, not caused by any nodus-lang release**, and it has been true since
0.1.0 in June. Two previous Stage 6 sweeps did not surface it because a
version-and-range check has no reason to look at the artifact list.

## 5. Working-tree drift

`git status --porcelain` across all twelve checkouts: **0 uncommitted files.**

```
nodus-mcp  nodus-mcp-server  nodus-extension  nodus-sdk
nodus-native-memory-engine  nodus-jupyter (master)  nodus-a2a
nodus-memory  nodus-store-sql (master)  nodus-workflow
nodus-vscode  nodus-run-action
```

## 6. Editor and CI surfaces — checked by hand

Neither is on PyPI, so neither is visible to §1 or §3.

- **`nodus-vscode` 0.1.2** — no republish needed. 5.0.1 adds **no keyword and no
  syntax**, so the TextMate grammar is unaffected. This is the check that was
  outstanding at 5.0.0 (the five `goal` keywords) and is genuinely a no-op here;
  recorded so that "not republished" is a decision rather than an omission.
- **`nodus-run-action` v1.0.0** — pins a nodus-lang version in YAML for
  reproducible CI, so it is invisible to the content-hash sweep by construction.
  Users pinning `version: '5.0.0'` are unaffected and can move to `'5.0.1'` at
  their convenience; nothing in the action needs changing.

## 7. Also done during the sweep

- **The `~/.pypirc` token is account-wide, not nodus-lang-scoped.** It published
  all five companions plus nodus-lang without a per-project token. `CLAUDE.md`
  stated that each separate repo needs its own project token; that is wrong and
  has been corrected.
- **`nodus-extension` builds with hatchling, not setuptools.** Current hatchling
  emits `Metadata-Version: 2.5`, which the installed twine 6.2.0 rejects outright
  (`InvalidDistribution`). Built with `PIP_CONSTRAINT` pinning `hatchling==1.27.0`
  to get 2.4, which PyPI accepts and which matches the other four packages.
- **A `nodus-sdk` test had been failing since 2026-07-12** — `test_version_string`
  asserted `0.1.0` while the package was `0.1.1`. The v5.0.0 sweep recorded it as
  a known-stale test rather than fixing it; fixed in 0.1.2.
