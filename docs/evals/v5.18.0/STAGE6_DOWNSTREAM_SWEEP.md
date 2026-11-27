# v5.18.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.18.0` live on PyPI; GitHub release `v5.18.0` created

**Date:** 2026-11-26

## 1. Do published ranges still admit 5.18.0?

`python -m tools.check_downstream_constraints` resolves each companion's
**published** range with `packaging`. Exit 0.

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | >=4.0.0 | ok |
| nodus-extension | 0.1.2 | >=4.0.0 | ok |
| nodus-jupyter | 0.1.0 | >=4.0.0 | ok |
| nodus-mcp | 0.1.6 | >=4.0.0 | ok |
| nodus-mcp-server | 0.2.1 | >=5.15.1 | ok |
| nodus-native-memory-engine | 0.1.1 | >=4.0.0 | ok |
| nodus-sdk | 0.2.0 | >=4.0.0 | ok |
| nodus-workflow-ai | 0.1.0 | >=5.8.0 | ok |

All 8 admit 5.18.0.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` compares file contents from each published
sdist with the checkout. Exit 0: **all 13 companions match what they
published.** No companion changed this cycle.

## 3. Non-PyPI consumers

`nodus_gate --consumers` before: 1/3 in step. After republishing: **3/3 in
step.**

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | tracks keywords, and 5.18.0 adds none: `str_join` is a builtin |
| nodus-run-action | **republished v1.0.20** | the README pin moved 5.17.0 → 5.18.0. `v1.0.20` was tagged, the floating `v1` moved to the same commit (`606f830`), and the GitHub release was created. No action code changed |
| nodus-wiki | **republished `c34c6ea`** | the version banners on Home, Getting-Started, Roadmap, _Footer and _Sidebar, and Security's supported row is now 5.18.x. **Security gained a note:** anything relying on `max_memory_mb` should be on 5.18.0, the same kind of note as its 5.6.0 one for capability policies. **Embedding-API's `max_memory_mb` row said only "Memory ceiling for the run."** It now says what it bounds (growth in process RSS), when it is checked, and that a single allocation is served first. `compile_functions` still says "5.17.0" as the version it arrived in, which is history, so it was left alone |

`tools/consumers.json` records the new `published` and `fingerprint` values in
the post-release PR.

## 4. Work left behind in companion checkouts

Each checkout was fetched, then checked for its branch, uncommitted changes, and
commits ahead of or behind its upstream.

| checkout | branch | state |
|---|---|---|
| `C:\dev\a2a-wire-pub` | main | clean, level with origin |
| `C:\dev\nodus-a2a` | main | clean, level with origin |
| `C:\dev\nodus-extension` | main | clean, level with origin |
| `C:\dev\nodus-jupyter` | master | clean, level with origin |
| `C:\dev\nodus-mcp` | main | clean, level with origin |
| `C:\dev\nodus-mcp-server` | main | clean, level with origin |
| `C:\dev\nodus-memory` | main | clean, level with origin |
| `C:\dev\nodus-native-memory-engine` | main | clean, level with origin |
| `C:\dev\nodus-run-action` | main | clean, level with origin (after the v1.0.20 push) |
| `C:\dev\nodus-sdk` | main | clean, level with origin |
| `C:\dev\nodus-store-sql` | master | clean, level with origin |
| `C:\dev\nodus-vscode` | main | clean, level with origin |
| `C:\dev\nodus-workflow` (nodus-flow) | main | clean, level with origin |
| `C:\dev\nodus-workflow-ai` | main | clean, level with origin |
| `C:\dev\Nodus Wiki\nodus-wiki` | master | clean, level with origin (after the `c34c6ea` push) |

## Verdict

**Nothing downstream is broken or left behind.**
- Every published range admits 5.18.0.
- Every companion matches what it published.
- Both stale consumers are republished.
- Every checkout is clean.

Gate 10a passed on its first round, so no companion needed a change for this
release.
