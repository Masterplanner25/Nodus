# v5.21.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.21.0` live on PyPI; GitHub release `v5.21.0` created

**Date:** 2026-11-27

## 1. Do published ranges still admit 5.21.0?

`python -m tools.check_downstream_constraints` resolves each companion's
**published** range with `packaging`. Exit 0: **all 8 companions admit
5.21.0.** The ranges are unchanged from 5.20.0's sweep:
- six companions at `>=4.0.0`;
- nodus-mcp-server at `>=5.15.1`;
- nodus-workflow-ai at `>=5.8.0`.

None has an upper cap, so 6.0.0 will resolve too (G6 of `V6_0_PLAN.md`). It is
re-run at that cut anyway.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` compares the file contents of each
companion's published sdist with its checkout. Exit 0: **all 13 companions match
what they published.** No companion changed this cycle, and none needed to.

The #1021 warning can reach a companion only through `.nd` code it ships that
calls `run_loop()` from an imported module. The `nodus check --staged` sweep
over first-party `.nd` files before this cycle found no such call. Gate 10a's
suites all passed.

## 3. Non-PyPI consumers

`nodus_gate --consumers`: 1/3 in step before republishing, **3/3** after.

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | tracks keywords, and 5.21.0 adds none |
| nodus-run-action | **republished v1.0.23** | The README pin moved from 5.20.0 to 5.21.0. `v1.0.23` was tagged, the floating `v1` was moved to the same commit (`c8257f0`), and the GitHub release was created. No action code changed |
| nodus-wiki | **republished `b795cbe`** | Updated the version banners on Home, Getting-Started, Roadmap, _Footer and _Sidebar. In Security.md the supported row is v5.21.x and "upgrade first" now covers v5.0.x–v5.20.x. No wiki page advises calling `run_loop()` from a library. Embedding-API needs nothing, since 5.21.0 does not change `NodusRuntime`'s constructor |

`tools/consumers.json` records the new `published` and `fingerprint` values in
this PR.

## 4. Work left behind in companion checkouts

Each checkout was fetched, then checked for its branch, uncommitted changes, and
commits ahead of or behind its upstream. **All 15 are clean and level with
origin**: a2a-wire-pub, nodus-a2a, nodus-extension, nodus-jupyter, nodus-mcp,
nodus-mcp-server, nodus-memory, nodus-native-memory-engine, nodus-run-action
(after the v1.0.23 push), nodus-sdk, nodus-store-sql, nodus-vscode,
nodus-workflow (nodus-flow), nodus-workflow-ai, and the wiki (after the
`b795cbe` push).

## Verdict

**Nothing downstream is broken or left behind.**
- Every published range admits 5.21.0.
- Every companion matches what it published.
- Both stale consumers are republished.
- Every checkout is clean.

This was the last 5.x release. From here, `main` takes the 6.0.0 flip PRs.
