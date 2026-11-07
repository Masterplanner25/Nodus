# v5.15.1 — Stage 6 downstream republish sweep

**Trigger:** `nodus-lang 5.15.1` live on PyPI; GitHub release `v5.15.1` created
(tag `v5.15.1` → `d6f0abf`).
**Date:** 2026-11-07

Four questions, three tooled.

## 1. Do published ranges still admit 5.15.1?

`tools.check_downstream_constraints` — resolved with `packaging` against
**published** metadata. **8/8 admit 5.15.1.**

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | >=4.0.0 | ok |
| nodus-extension | 0.1.2 | >=4.0.0 | ok |
| nodus-jupyter | 0.1.0 | >=4.0.0 | ok |
| nodus-mcp | 0.1.5 | >=4.0.0 | ok |
| nodus-mcp-server | 0.1.15 | >=5.15.0 | ok |
| nodus-native-memory-engine | 0.1.1 | >=4.0.0 | ok |
| nodus-sdk | 0.2.0 | >=4.0.0 | ok |
| nodus-workflow-ai | 0.1.0 | >=5.8.0 | ok |

## 2. Has any companion drifted from what it published?

`tools.check_publish_drift` — downloads each published sdist and compares file
contents. **All 13 companions match what they published** (exit 0). No drift.

## 3. Non-PyPI consumers

`nodus_gate --consumers`. **1/3 in step; 2 flagged** (advisory):

| consumer | state | note |
|---|---|---|
| nodus-vscode (0.1.6) | **ok** | keyword set unchanged; 5.15.1 adds no keyword |
| nodus-run-action (v1.0.16) | **needs republish** | tracks `nodus_version`; README pin 5.15.0 → 5.15.1 |
| nodus-wiki (`b9550c2`) | **needs republish** | tracks `nodus_version`; version banners 5.15.0 → 5.15.1 |

Both flagged consumers track `nodus_version` **by construction**, so they go
stale on every version bump — that is the mechanism working, not a regression.
Their flags are **not cleared here**: the sweep rule is "clear a flag only after
republishing." For this patch the only change either needs is the version string
(5.15.0 → 5.15.1); the deep structural corrections the wiki once needed were done
in earlier cycles. Follow-up (own repos, outward-facing):
- **nodus-run-action** — bump the pinned `version:` in README examples, tag the
  action, then update `fingerprint`/`published` in `tools/consumers.json`.
- **nodus-wiki** — bump the version banners on Home, Getting-Started, Roadmap,
  `_Footer`, `_Sidebar` and the two agent-skill pages, push to `master` (goes
  live immediately), then update `fingerprint`/`published`.

## 4. Work left behind in companion checkouts

`git status` on each registered dependent: **all clean.** One note:
`nodus-mcp-server` is checked out on branch `ci/add-workflow` (its PR #9 CI
branch). That PR's 3.10 cells were red against published 5.15.0 — the symptom
that surfaced #893. With 5.15.1 now on PyPI, re-running #9's CI should turn those
cells green; merging #9 is a tracked follow-up, not part of this release.

## Summary

| question | result |
|---|---|
| ranges admit 5.15.1 | **8/8 yes** |
| companion drift | **13/13 match** |
| non-PyPI consumers | 1/3 in step; run-action + wiki need a version-string republish (advisory) |
| work left behind | all checkouts clean |
