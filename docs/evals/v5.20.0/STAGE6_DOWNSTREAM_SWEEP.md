# v5.20.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.20.0` live on PyPI; GitHub release `v5.20.0` created

**Date:** 2026-11-27

## 1. Do published ranges still admit 5.20.0?

`python -m tools.check_downstream_constraints` resolves each companion's
**published** range with `packaging`. Exit 0: **all 8 companions admit
5.20.0.** The ranges are unchanged from 5.19.0's sweep: six at `>=4.0.0`,
nodus-mcp-server at `>=5.15.1`, nodus-workflow-ai at `>=5.8.0`.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` compares file contents from each published
sdist with the checkout. Exit 0: **all 13 companions match what they
published.** No companion changed this cycle, and none needed to.

5.20.0's changes reach companions less than 5.19.0's did. The wider compile
default is in `nodus serve`, `nodus test` and the shared runner, and no companion
suite changed result under it at Gate 10a. `--coverage` is a `nodus test` flag,
which no companion's suite uses.

## 3. Non-PyPI consumers

`nodus_gate --consumers` before: 1/3 in step. After republishing: **3/3 in
step.**

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | tracks keywords, and 5.20.0 adds none |
| nodus-run-action | **republished v1.0.22** | the README pin moved 5.19.0 → 5.20.0. `v1.0.22` was tagged, the floating `v1` moved to the same commit (`e2427d8`), and the GitHub release was created. No action code changed |
| nodus-wiki | **republished `d520b5b`** | the version banners on Home, Getting-Started, Roadmap, _Footer and _Sidebar, and Security's supported row is now 5.20.x. Embedding-API's `compile_functions` row was checked and is still accurate: it describes `NodusRuntime`, which 5.20.0 does not change |

`tools/consumers.json` records the new `published` and `fingerprint` values in
this PR.

## 4. Work left behind in companion checkouts

Each checkout was fetched, then checked for its branch, uncommitted changes, and
commits ahead of or behind its upstream. **All 15 are clean and level with
origin**: a2a-wire-pub, nodus-a2a, nodus-extension, nodus-jupyter, nodus-mcp,
nodus-mcp-server, nodus-memory, nodus-native-memory-engine, nodus-run-action
(after the v1.0.22 push), nodus-sdk, nodus-store-sql, nodus-vscode,
nodus-workflow (nodus-flow), nodus-workflow-ai, and the wiki (after the
`d520b5b` push).

## Verdict

**Nothing downstream is broken or left behind.**
- Every published range admits 5.20.0.
- Every companion matches what it published.
- Both stale consumers are republished.
- Every checkout is clean.

The one defect found after the upload, #1018 (a module's last line counted as
covered), is in `nodus test --coverage` only, and no companion uses it.
