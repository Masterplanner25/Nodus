# v5.13.0 — Stage 6 downstream republish sweep

**Date:** 2026-09-08
**Verdict:** **PASS.** Nothing broken, two consumers republished, nothing left behind.

Stage 6 asks the question the other two stages structurally cannot: *what did this
release break or leave stale downstream?* Gate 10 validates nodus-lang against a
local wheel, Stage 5 against the published one — neither of them looks outward.

---

## 1. Do published ranges still admit 5.13.0?

`python -m tools.check_downstream_constraints` — exit **0**.

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | `>=4.0.0` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |
| nodus-mcp | 0.1.3 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.12 | `>=4.0.5` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.2 | `>=4.0.0` | ok |
| nodus-workflow-ai | 0.1.0 | `>=5.8.0` | ok |

**All 8 admit 5.13.0.** Every range is a floor with no cap, which is the policy
decided 2026-08-17 and the reason this is now a formality rather than the trap it
was at 5.0.0 — where five of six companions published `<5.0.0` and made
`pip install nodus-lang==5.0.0 nodus-mcp` a `ResolutionImpossible`, found by the
aindy-runtime team rather than by us.

The ranges are resolved with `packaging` against *published* metadata, never read
by eye: `>=4.0.0,<5.0.0` reads as "admits 4.x", and the clause that forbids the
new version sits at the far end of the string.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` — exit **0**.

**All 13 companions match what they published**, compared by downloading each
published sdist and diffing file contents rather than trusting a version string.
No unpublished work is sitting in a checkout.

## 3. Non-PyPI consumers

`nodus_gate --consumers` flagged **two**, both because `nodus_version` moved.
Both were republished before their flags were cleared, which is the rule: a flag
cleared before the work is done is worse than no flag.

### `nodus-run-action` → **v1.0.14**

Its README documents a pinned `version:` for reproducible CI, and the pin is what
new users copy — so a stale one hands them an old runtime. Two pins updated to
`'5.13.0'`, committed and tagged.

### The GitHub wiki → **7ffcdd9**

Version banners on Home, Getting-Started, Roadmap and `_Footer`, **plus the
substance**. A banner bump alone would have left the wiki claiming 5.13.0 while
describing a language without `copy()` — which is precisely the failure this
surface already had, documenting v4.1.1 for twelve minors across a major whose
deny-by-default change breaks embedders.

What changed beyond the banners:

- `copy(value)` added to the built-in table, with what it preserves and refuses.
- **The aliasing rule stated for the first time**: containers alias, assignment
  binds rather than copies, and a workflow `state` cell is the exception because
  it owns its value.
- `list_push` documented as in-place, since `xs = list_push(xs, v)` reads
  functional and is not.
- `ensure_dir`'s real semantics — idempotent on a directory, `io_error` on a
  file, and it reported success for every failure before 5.13.0.
- **Security page**: the supported-versions table, and the `nodus serve` section,
  which listed subprocess, network and env only. That is the confinement 5.10.0
  gave it; the filesystem arrived in 5.13.0. Anyone still on 5.12.0 or earlier is
  now told to treat `serve` as having no filesystem boundary.

The wiki is the one surface here with no PR and no CI — a push goes straight
live — which is why it is tracked in `tools/consumers.json` at all.

`nodus-vscode` needed nothing: it tracks the keyword set, and this release added
a builtin rather than a keyword, so its fingerprint is unchanged.

**After republishing: `Consumers: PASS — 3/3 in step`.**

## 4. Work left behind

`git status` across all 14 checkouts: **every one clean, on its expected branch,
with nothing unpushed.**

```
nodus-mcp, nodus-a2a, nodus-memory, nodus-native-memory-engine, nodus-extension,
nodus-sdk, nodus-workflow-ai, nodus-mcp-server, nodus-workflow, nodus-vscode,
nodus-run-action        -> main
nodus-store-sql, nodus-jupyter -> master
a2a-wire-pub            -> main
```

---

## Follow-up for the next cycle

The `points_at` version claim in `ECOSYSTEM_READINESS_ASSESSMENT.md` still names
5.12.0. That is correct until this directory exists, and it is the one claim whose
right value changes *because of* the commit that carries it — so it moves to
5.13.0 in the same commit that adds these three eval documents, and
`nodus_gate --versions` is expected to fail once on that PR.
