# v5.19.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.19.0` live on PyPI; GitHub release `v5.19.0` created

**Date:** 2026-11-26

## 1. Do published ranges still admit 5.19.0?

`python -m tools.check_downstream_constraints` resolves each companion's
**published** range with `packaging`. Exit 0: **all 8 companions admit
5.19.0.** The ranges are unchanged from 5.18.0's sweep: six at `>=4.0.0`,
nodus-mcp-server at `>=5.15.1`, nodus-workflow-ai at `>=5.8.0`.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` compares file contents from each published
sdist with the checkout. Exit 0: **all 13 companions match what they
published.** No companion changed this cycle.

**None needed to.** Every companion that builds a `NodusRuntime` now runs
compiled code by default, and Gate 10a ran all eight dependent suites that way
before the upload, with no change in result.

## 3. Non-PyPI consumers

`nodus_gate --consumers` before: 1/3 in step. After republishing: **3/3 in
step.**

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | tracks keywords, and 5.19.0 adds none |
| nodus-run-action | **republished v1.0.21** | the README pin moved 5.18.0 → 5.19.0. `v1.0.21` was tagged, the floating `v1` moved to the same commit (`a7bd0c5`), and the GitHub release was created. No action code changed |
| nodus-wiki | **republished `069f441`** | the version banners on Home, Getting-Started, Roadmap, _Footer and _Sidebar, and Security's supported row is now 5.19.x. **Embedding-API's `compile_functions` was stale in substance, not only in version.** It said default `False` and "Experimental, 5.17.0", and named `--compile` as a switch. It now gives the default `True`, Mostly Stable, `--no-compile`, and `NODUS_COMPILE_FUNCTIONS=0` as the process-wide override. The remaining "5.18.0" mentions are history: the release a fix arrived in |

`tools/consumers.json` records the new `published` and `fingerprint` values in
the post-release PR.

## 4. Work left behind in companion checkouts

Each checkout was fetched, then checked for its branch, uncommitted changes, and
commits ahead of or behind its upstream. **All 15 are clean and level with
origin**: a2a-wire-pub, nodus-a2a, nodus-extension, nodus-jupyter, nodus-mcp,
nodus-mcp-server, nodus-memory, nodus-native-memory-engine, nodus-run-action
(after the v1.0.21 push), nodus-sdk, nodus-store-sql, nodus-vscode,
nodus-workflow (nodus-flow), nodus-workflow-ai, and the wiki (after the
`069f441` push).

## Verdict

**Nothing downstream is broken or left behind.**
- Every published range admits 5.19.0.
- Every companion matches what it published.
- Both stale consumers are republished.
- Every checkout is clean.

The change most likely to reach downstream, compiled by default, was run against
every dependent suite before the upload.
