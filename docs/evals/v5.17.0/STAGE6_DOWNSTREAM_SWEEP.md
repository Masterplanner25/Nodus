# v5.17.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.17.0` live on PyPI; GitHub release `v5.17.0` created

**Date:** 2026-11-22

## 1. Do published ranges still admit 5.17.0?

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

All 8 admit 5.17.0.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` compares file contents from each published
sdist with the checkout. Exit 0: **all 13 companions match what they
published.**

That includes the three companions whose tests changed this cycle:
nodus-a2a-wire#2, nodus-extension#4 and nodus-native-memory-engine#4, which
replaced the pinned `BYTECODE_VERSION == 4` invariant that Gate 10a caught. The
changes are test-only, so there's nothing to republish. The drift check compares
shipped files and agrees.

## 3. Non-PyPI consumers

`nodus_gate --consumers` before: 1/3 in step. After republishing: **3/3 in
step.**

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | tracks keywords, and 5.17.0 adds none: `substring`, `str_span` and `str_span_until` are builtins |
| nodus-run-action | **republished v1.0.19** | the README pin moved 5.16.0 → 5.17.0; `v1.0.19` was tagged, the floating `v1` moved to the same commit (`6bcd581`), and the GitHub release was created. No action code changed |
| nodus-wiki | **republished `40f863d`** | the version banners on Home, Getting-Started, Roadmap, _Footer and _Sidebar, and Security's supported row is now 5.17.x. **Embedding-API listed 27 of the constructor's 28 parameters:** `compile_functions`, new in 5.17.0, was missing, and is added to the signature, the count and the table. The two agent-skill pages and Coroutines-and-Channels say "5.16.0" only as the version durable coroutines arrived in, which is history, so they were left alone |

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
| `C:\dev\nodus-run-action` | main | clean, level with origin |
| `C:\dev\nodus-sdk` | main | clean, level with origin |
| `C:\dev\nodus-store-sql` | master | clean, level with origin |
| `C:\dev\nodus-vscode` | main | clean, level with origin |
| `C:\dev\nodus-workflow` (nodus-flow) | main | clean, level with origin |
| `C:\dev\nodus-workflow-ai` | main | clean, level with origin |
| `C:\dev\Nodus Wiki\nodus-wiki` | master | clean. It had **no upstream configured**, so `git pull` refused before the edit. Local `master` already matched `origin/master` (`6cf69d7`). Upstream set to `origin/master` after the push |

`nodus-mcp-server`'s untracked handoff note, recorded at 5.16.0, is gone.

## Verdict

**Nothing downstream is broken or left behind.**
- Every published range admits 5.17.0.
- Every companion matches what it published.
- Both stale consumers are republished.
- Every checkout is clean.

The one break this release could have caused downstream, three companions' test
suites pinned to `BYTECODE_VERSION == 4`, was caught by Gate 10a before the
upload and fixed in those repos. It never reached a published artifact.
