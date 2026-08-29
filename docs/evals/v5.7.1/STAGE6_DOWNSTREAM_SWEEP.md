# v5.7.1 — Stage 6 downstream republish sweep

**Date:** 2026-08-29
**Verdict:** pass — 6/6 ranges · 11/11 no drift · 2/2 consumers · 13/13 checkouts clean

Four questions. Three are tooled; the fourth is done by hand, and this cycle the
fourth is the one that found something.

---

## 1. Do published ranges still admit the new version?

```
PYTHONPATH="src;." python -m tools.check_downstream_constraints
```

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-mcp | 0.1.3 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.12 | `>=4.0.5` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.2 | `>=4.0.0` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |

**All 6 admit 5.7.1.** Every range floats — the policy decided 2026-08-17 after
five of six companions published `<5.0.0` caps and made 5.0.0 unadoptable. Ranges
are resolved with `packaging` against **published** metadata rather than read by
eye, because `>=4.0.0,<5.0.0` reads as "admits 4.x" and the clause that forbids
the new version is at the far end of the string.

## 2. Has a companion drifted from what it published?

```
PYTHONPATH="src;." python -m tools.check_publish_drift
```

**11/11 match**, by downloading each published sdist and comparing file contents —
not by counting commits, which gave four false positives at v4.2.0 because a
commit can touch only docs, only CI, or only tests.

```
nodus-a2a 0.1.0 · nodus-a2a-wire 0.1.0 · nodus-extension 0.1.2 · nodus-flow 0.2.0
nodus-jupyter 0.1.0 · nodus-mcp 0.1.3 · nodus-mcp-server 0.1.12 · nodus-memory 0.1.0
nodus-native-memory-engine 0.1.1 · nodus-sdk 0.1.2 · nodus-store-sql 0.1.0
```

## 3. Non-PyPI consumers left behind

```
Consumers: PASS — 2/2 in step
```

Both needed republishing this cycle, and both were done:

| consumer | was | now | why it moved |
|---|---|---|---|
| **nodus-vscode** | 0.1.4 | **0.1.5** | two new keywords, `extern` (#489) and `compensates` (#577) |
| **nodus-run-action** | v1.0.7 | **v1.0.8** | its README pins the nodus-lang version, which every release moves |

`nodus-run-action`'s pins had gone stale across **two** releases — they read
5.6.0 — because the 5.7.0 cycle stopped before Stage 6 when that release was
found defective after its upload. Now 5.7.1.

The floating `v1` tag was moved and verified **by resolution on the remote**,
since `rev-parse` on an annotated tag returns the tag object rather than the
commit:

```
HEAD              ca0507d
v1.0.8 resolves   ca0507d
v1 resolves       ca0507d
remote v1^{}      ca0507d
remote v1.0.8^{}  ca0507d
```

Both flags were cleared **after** the republish, with `fingerprint` and
`published` moving in the same commit.

## 4. Work left behind — and what it caught

`git status` across 13 checkouts: **all clean, no uncommitted work.**

But the branch column was not clean, and this is the finding:

> **`nodus-vscode` was sitting on `extern-keyword-489`, 2 commits ahead of
> `main`, and `main` had neither keyword.**

So the **published 0.1.5 existed only on a branch**. `main` still carried 0.1.4's
grammar. Anyone working from `main` — the obvious thing to do next — would have
lost both keywords, and a republish from there would have shipped a regression
that `nodus_gate --consumers` could not see, because the fingerprint it compares
had already been marked in step.

Merged (fast-forward) and pushed. `main` now reports version 0.1.5 with both
keywords present.

**Nothing tooled would have caught this.** The content-hash sweep only reads
PyPI, and the consumers check deliberately reads no sibling checkout. It is the
by-hand question, and it earned its place.

---

## Carried forward

- **5.7.0 is superseded**, on PyPI with no GitHub release. The rule is recorded
  in `CLAUDE.md`: when a release is found defective between the upload and the
  GitHub release, stop and cut both artifacts at the next version.
- **#664** — `nodus run` has no extern pre-flight and its call-site error does not
  mention the declaration. Filed from Stage 5, not a blocker.
- **Throughput unmeasured.** Nothing in 5.7.1 is on an execution path, but that is
  not a measurement.
