# v5.10.0 — Stage 6 downstream republish sweep

**Verdict: clear.** All four questions answered; one consumer needed
republishing and was republished before its flag was cleared.

| question | tool | result |
|---|---|---|
| Do published ranges still admit the new version? | `check_downstream_constraints` | **7/7 admit 5.10.0**, exit 0 |
| Has a companion drifted from what it published? | `check_publish_drift` | **13/13 match**, exit 0 |
| Any non-PyPI consumer left behind? | `nodus_gate --consumers` | 1 stale → **republished**, now 2/2 |
| Work left behind in a checkout? | by hand | **14 checkouts clean and pushed** |

---

## 1. Ranges — 7/7 admit 5.10.0

```
nodus-mcp-server             0.1.12     >=4.0.5      ok
nodus-extension              0.1.2      >=4.0.0      ok
nodus-sdk                    0.1.2      >=4.0.0      ok
nodus-native-memory-engine   0.1.1      >=4.0.0      ok
nodus-jupyter                0.1.0      >=4.0.0      ok
nodus-workflow-ai            0.1.0      >=5.8.0      ok
```

Resolved with `packaging` against **published** metadata, never read by eye. Five
of six companions once published `nodus-lang<5.0.0`, making 5.0.0 unadoptable for
anyone using the ecosystem — and the sweep that should have caught it transcribed
the ranges with the upper bound dropped, because `>=4.0.0,<5.0.0` reads as
"admits 4.x" and the clause that forbids the new version sits at the far end of
the string (#445).

No caps to check this time: companions do not cap `nodus-lang` (policy,
2026-08-17).

## 2. Drift — 13/13 match what they published

Including `nodus-container`, published during this cycle and registered in
`check_publish_drift.py` in its publishing commit. That registration matters:
`nodus-flow` sat outside this sweep under two different names, which is the
comment sitting directly above the entry.

## 3. Non-PyPI consumers — one was stale, and is not now

`nodus-vscode` (0.1.5) — keywords unchanged; 5.10.0 adds no keyword.

`nodus-run-action` — **needed republishing**: it tracks `nodus_version`, and its
README pins the version new users copy into their own workflows. A stale pin
hands them an old runtime.

Republished as **v1.0.11** — both pinned examples updated, committed, tagged,
pushed — and only then were `fingerprint` and `published` updated in
`tools/consumers.json`, in that order. The manifest is explicit that a flag
cleared before the work is done is worse than no flag. `--consumers --strict`
now passes 2/2.

> One self-inflicted false alarm worth recording. `git tag -l | tail -4` showed
> `v1.0.9` as the highest tag while the manifest claimed `v1.0.10`, and I was a
> step from reporting a discrepancy. Tags sort **lexically**: `v1.0.10` sorts
> before `v1.0.6`. The manifest was right. Check with `git tag -l "vX.Y.Z"`, not
> by eye on a sorted tail.

## 4. Work left behind — none

`git status` and unpushed-commit count across all fourteen checkouts
(`nodus-mcp`, `nodus-a2a`, `nodus-memory`, `nodus-native-memory-engine`,
`nodus-extension`, `nodus-sdk`, `nodus-store-sql`, `nodus-workflow-ai`,
`nodus-jupyter`, `nodus-mcp-server`, `nodus-workflow`, `nodus-vscode`,
`nodus-run-action`, `a2a-wire-pub`): all clean, nothing unpushed.

---

## Ecosystem after this release

**37 standalone companions, 38 PyPI projects** counting `nodus-lang` —
re-derived during this cycle by probing every `nodus-*` name in
`docs/ecosystem/README.md`, not by incrementing. Four listed names deliberately
do not resolve: `nodus-vscode` (Marketplace), `nodus-run-action` (GitHub Action),
`nodus-event` (not implemented) and `nodus-scheduler` (written in Nodus, with no
registry to publish to).

`nodus-container` 0.1.0 was published during this cycle — the first companion
shipped without a repository of its own, from `packages/nodus-container/`.
