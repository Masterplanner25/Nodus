# v5.16.0 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.16.0` live on PyPI; GitHub release `v5.16.0` created
(tag `v5.16.0` → `2341db7`).
**Date:** 2026-11-11

Four questions, three of them tooled.

## 1. Do published ranges still admit 5.16.0?

`tools.check_downstream_constraints` resolves each range with `packaging`
against **published** metadata. **8/8 admit 5.16.0.**

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | >=4.0.0 | ok |
| nodus-extension | 0.1.2 | >=4.0.0 | ok |
| nodus-jupyter | 0.1.0 | >=4.0.0 | ok |
| nodus-mcp | 0.1.6 | >=4.0.0 | ok |
| nodus-mcp-server | 0.1.16 | >=5.15.1 | ok |
| nodus-native-memory-engine | 0.1.1 | >=4.0.0 | ok |
| nodus-sdk | 0.2.0 | >=4.0.0 | ok |
| nodus-workflow-ai | 0.1.0 | >=5.8.0 | ok |

## 2. Has any companion drifted from what it published?

`tools.check_publish_drift` downloads each published sdist and compares file
contents. **All 13 companions match what they published** (exit 0).

## 3. Non-PyPI consumers

`nodus_gate --consumers`: **1/3 in step, 2 flagged** (advisory).

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | keyword set unchanged: `durable_spawn` is a builtin, not a keyword, and 5.16.0 adds no keyword |
| nodus-run-action (v1.0.17) | **needs republish** | tracks `nodus_version`; the README pin moves 5.15.1 → 5.16.0 |
| nodus-wiki (`efc7126`) | **needs republish** | tracks `nodus_version`; the version banners move 5.15.1 → 5.16.0 |

Both flagged consumers track `nodus_version` by construction, so every bump
flags them; that is the mechanism working. **Their flags are not cleared here**
(the rule: clear a flag only after republishing). Both are outward-facing pushes
to their own repos. The wiki goes live on push with nothing in between, so they
are follow-ups, not part of this record.

## 4. Work left behind in companion checkouts

`git status` on each registered dependent:

| checkout | branch | state |
|---|---|---|
| `C:\dev\nodus-mcp` | main | clean |
| `C:\dev\nodus-mcp-server` | main | one untracked file, `Session Handoff Summary.md`: a working note, not release work; left alone |
| `C:\dev\nodus-extension` | main | clean |
| `C:\dev\nodus-sdk` | main | clean |
| `C:\dev\nodus-native-memory-engine` | main | clean |
| `C:\dev\nodus-jupyter` | master | clean |
| `C:\dev\nodus-workflow-ai` | main | clean |
| `C:\dev\a2a-wire-pub` | main | clean |

`nodus-mcp-server` is back on `main` (it was on `ci/add-workflow` at 5.15.1).

**One stale path found.** `CLAUDE.md` and `docs/ecosystem/COMPANION_REPOS.md`
named the wire checkout as `C:\codev\a2a-wire-pub`, which no longer exists. The
checkout is `C:\dev\a2a-wire-pub` (remote `Masterplanner25/nodus-a2a-wire`),
which is where `tools/nodus_lang_dependents.json`, and so Gate 10a, already
pointed. Corrected in the same PR as this record.

## Summary

| question | result |
|---|---|
| ranges admit 5.16.0 | **8/8 yes** |
| companion drift | **13/13 match** |
| non-PyPI consumers | 1/3 in step; run-action and wiki need a version-string republish (advisory) |
| work left behind | none; one untracked note in nodus-mcp-server, and one stale checkout path in the docs (fixed) |
