# Stage 6 — downstream sweep, v5.1.0

Date: 2026-08-20

Stage 6 asks **"what did this release break or leave behind?"** It has three parts,
and each exists because a previous release got that part wrong.

---

## 1. Do published companions admit 5.1.0?

Resolved from **published** PyPI metadata with `packaging`, not read by eye:

```
companion                    published  nodus-lang range   verdict
nodus-mcp                    0.1.3      >=4.0.0            ok
nodus-mcp-server             0.1.12     >=4.0.5            ok
nodus-extension              0.1.2      >=4.0.0            ok
nodus-sdk                    0.1.2      >=4.0.0            ok
nodus-native-memory-engine   0.1.1      >=4.0.0            ok
nodus-jupyter                0.1.0      >=4.0.0            ok

All 6 companions admit nodus-lang 5.1.0.
```

Confirmed by actually installing them together — see POSTPUBLISH_EVAL §3. A passing
range check and a passing install are different claims, and at 5.0.0 the sweep made
the first and skipped the second.

## 2. Has any companion drifted from what it published?

**New tool this cycle: `tools/check_publish_drift.py`.** Until now this step was done
by hand, and at v4.2.0 counting commits since the version bump produced **four false
positives** — a commit can touch only docs, only CI, or only tests, and none of those
change what an installer receives.

The tool downloads each published sdist and compares **file contents** under the
package directory, plus the declared dependency list. Nothing else: docs, tests and CI
are real changes but they are not what an installed package is.

```
companion                    verdict  detail
nodus-a2a                    ok       6 files identical to 0.1.0
nodus-extension              ok       16 files identical to 0.1.2
nodus-jupyter                ok       4 files identical to 0.1.0
nodus-mcp                    ok       14 files identical to 0.1.3
nodus-mcp-server             ok       4 files identical to 0.1.12
nodus-memory                 ok       7 files identical to 0.1.0
nodus-native-memory-engine   ok       1 files identical to 0.1.1
nodus-sdk                    ok       14 files identical to 0.1.2
nodus-store-sql              ok       6 files identical to 0.1.0

All 9 companions match what they published.
```

Two companions initially reported `SKIP` because the tool had their package
directories wrong. **A skip was not counted as a pass** — the paths were corrected and
both then checked clean. The tool exits 2 on any skip for exactly this reason.

`nodus-native-memory-engine` showing a single Python file is correct: it is a Rust
extension with a thin Python shim.

## 3. Non-PyPI consumers

The content-hash sweep above structurally cannot see these — they are not on PyPI —
and both have shipped stale in the past. `nodus_gate --consumers` covers them by
recording, in `tools/consumers.json`, the fingerprint of whatever each must stay in
step with, measured in *this* repo.

### `nodus-run-action` — was stale, now republished

The gate flagged it the moment the version moved:

```
[--] nodus-run-action (v1.0.1) — NEEDS REPUBLISH
     nodus_version moved: 5.0.4 -> 5.1.0
```

Its README documents a pinned `version:` for reproducible CI, and that pin is what new
users copy, so a stale pin hands them an old runtime. **This is the gate's first catch
on a real release**, and it caught it at the version bump rather than after publish.

Republished as **v1.0.2**: README examples pin `5.1.0`, tagged, `v1` moved. Verified
that both refs dereference to the released commit on the remote, not just locally:

```
49f6c7270638dccb77c0a654fce7252dfacd2f7a  refs/tags/v1^{}
49f6c7270638dccb77c0a654fce7252dfacd2f7a  refs/tags/v1.0.2^{}
```

The action's own `version` input still defaults to `''` (latest); only the documented
pins moved.

The manifest was updated **after** the republish, in that order — a flag cleared before
the work is done is worse than no flag.

### `nodus-vscode` — in step

```
[ok] nodus-vscode (0.1.3) — keywords unchanged
```

5.1.0 adds no keywords. `on`, `merge` and `durable` are option keys inside `with { }`,
not keywords, and `when` shipped in the extension's 0.1.3 during the previous cycle.
No republish needed.

Final: **`Consumers: PASS — 2/2 in step`**.

## 4. Work left behind in checkouts

Every companion checkout, checked for uncommitted or unpushed work:

```
nodus-mcp                    branch=main     dirty=0  unpushed=0
nodus-sdk                    branch=main     dirty=0  unpushed=0
nodus-extension              branch=main     dirty=0  unpushed=0
nodus-mcp-server             branch=main     dirty=0  unpushed=0
nodus-jupyter                branch=master   dirty=0  unpushed=0
nodus-native-memory-engine   branch=main     dirty=0  unpushed=0
nodus-memory                 branch=main     dirty=0  unpushed=0
nodus-a2a                    branch=main     dirty=0  unpushed=0
nodus-store-sql              branch=master   dirty=0  unpushed=0
nodus-workflow               branch=main     dirty=0  unpushed=0
nodus-vscode                 branch=main     dirty=0  unpushed=0
nodus-run-action             branch=main     dirty=0  unpushed=0
```

Nothing left behind. `nodus-jupyter` and `nodus-store-sql` are on `master` rather than
`main` — long-standing, not a finding.

## 5. Verdict

**No downstream breakage.** One consumer was stale and has been republished; one tool
gap was closed by writing the drift checker this step has always required.

## 6. Follow-ups filed

- **#528** — the dependent-suite gate reports `1 failed` and *"Do not publish"*
  **without naming the failing test**, which is not enough to tell a known flake from a
  real break. Hit during this release's Gate 10.
