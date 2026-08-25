# Stage 6 — Downstream republish sweep, v5.4.0

**After the publish.** Four questions: do downstream ranges still admit the new
version, has any companion drifted from what it published, has a non-PyPI
consumer been left behind, and is there work sitting in a checkout.

| | |
|---|---|
| Release | `nodus-lang` 5.4.0, published 2026-08-25 |
| Verdict | **Clean.** 6/6 ranges admit it · 9/9 no drift · 2/2 consumers in step (one republished) · 12/12 checkouts clean |

---

## 1. Do published companions admit 5.4.0?

`python -m tools.check_downstream_constraints` — resolves **published** PyPI
metadata, never a local `pyproject.toml`, because a floated cap sitting unreleased
in a companion's `main` helps nobody.

| Companion | Published | `nodus-lang` range | Verdict |
|---|---|---|---|
| nodus-mcp | 0.1.3 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.12 | `>=4.0.5` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.2 | `>=4.0.0` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |

**All six float**, per the policy decided at 5.0.0 after five companions capped
`<5.0.0` and made that release unadoptable. Nothing to do.

## 2. Has any companion drifted from what it published?

`python -m tools.check_publish_drift` — downloads each published sdist and
compares file contents. Not a git heuristic: counting commits since a version
bump gave four false positives at v4.2.0, because a commit can touch only docs,
only CI, or only tests.

**9/9 identical**: nodus-a2a (0.1.0), nodus-extension (0.1.2), nodus-jupyter
(0.1.0), nodus-mcp (0.1.3), nodus-mcp-server (0.1.12), nodus-memory (0.1.0),
nodus-native-memory-engine (0.1.1), nodus-sdk (0.1.2), nodus-store-sql (0.1.0).
Exit 0 — no skips, and a skip would not have been a pass.

## 3. Non-PyPI consumers

`nodus_gate --consumers`. These are invisible to the content-hash sweep above by
construction — a VS Code extension and a GitHub Action are not on PyPI — and both
have shipped stale before.

| Consumer | Tracks | Before | Action |
|---|---|---|---|
| nodus-vscode | keywords | `602761bf77ebb21e` | none — 5.4.0 added no keywords, so the published 0.1.3 grammar is still correct |
| nodus-run-action | `nodus_version` | `5.3.0` → stale | **republished** |

**nodus-run-action republished as v1.0.5.** Its README documents a pinned
`version:` for reproducible CI, and that pin is what new users copy — going stale
hands them an old runtime. Both examples moved to `5.4.0`, tagged `v1.0.5`, and
the floating `v1` moved with it.

Verified by dereferencing rather than trusting `rev-parse`, which returns the tag
object for an annotated tag:

```
v1 dereferenced: cb9ceb19
v1.0.5:          cb9ceb19
main:            cb9ceb19
```

The flag in `tools/consumers.json` was cleared **after** the republish, with
`fingerprint` and `published` updated in the same commit — a flag cleared before
the work is done is worse than no flag. `--consumers` now reports 2/2 in step.

## 4. Work left behind

`git status` on every checkout, by hand — the one question with no tool.

**12/12 clean**, nothing uncommitted, nothing unpushed: nodus-mcp, nodus-a2a,
nodus-memory, nodus-native-memory-engine, nodus-extension, nodus-mcp-server,
nodus-jupyter, nodus-vscode, nodus-run-action, nodus-workflow, nodus-sdk,
nodus-store-sql.

(nodus-jupyter and nodus-store-sql are on `master`, not `main` — long-standing,
recorded in the 2026-07-05 sweep, not drift.)

---

## Follow-up carried out of this release

**`tools/dependent_flakes.json` overstates its evidence.** The `nodus-mcp` entry
says its port-binding tests *"pass individually and in serial full-suite runs"*.
The second half held during Gate 10a (2/2 full serial runs green, 363 tests
each). The first did not — running `test_phase_m.py` alone failed once in seven
attempts. The classification is right and the release verdict is unaffected; only
the evidence sentence is too strong, and that file's own instructions say `why`
should record what was actually established. Worth a one-line correction next
time that file is touched.
