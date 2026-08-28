# v5.6.0 — Stage 6 downstream sweep

Four questions. Three are tooled; the fourth is `git status` in each checkout.

**Verdict: clear, with one consumer outstanding by design** — `nodus-vscode`
needs a Marketplace upload, and its flag is deliberately left standing until
that happens.

---

## 1. Do published ranges still admit the new version?

```
companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.2      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.6.0.                            exit 0
```

Every range floats. This is the check that mattered at 5.0.0, where five of six
companions published `nodus-lang<5.0.0` and made the release unadoptable —
`pip install nodus-lang==5.0.0 nodus-mcp` was `ResolutionImpossible`, found by
the aindy-runtime team rather than by us. The sweep that cycle asked this exact
question and transcribed five of six ranges with the upper bound dropped, which
is why it is resolved with `packaging` against **published** metadata now and
never read by eye.

## 2. Has any companion drifted from what it published?

```
All 11 companions match what they published.                        exit 0
```

`nodus-a2a` 0.1.0, `nodus-a2a-wire` 0.1.0, `nodus-extension` 0.1.2,
`nodus-flow` 0.2.0, `nodus-jupyter` 0.1.0, `nodus-mcp` 0.1.3,
`nodus-mcp-server` 0.1.12, `nodus-memory` 0.1.0,
`nodus-native-memory-engine` 0.1.1, `nodus-sdk` 0.1.2, `nodus-store-sql` 0.1.0.

Content-compared against each published sdist, not inferred from commit counts —
a git heuristic gave four false positives at v4.2.0, because a commit can touch
only docs, only CI, or only tests. Exit 0, not 2, so nothing was skipped.

## 3. Non-PyPI consumers

These are invisible to the sweep above by construction: neither is on PyPI, so a
content hash of published sdists structurally cannot see them.

### `nodus-run-action` — republished, flag cleared

`nodus_version` moved 5.5.0 → 5.6.0. Its README pins a version for reproducible
CI, and **that pin is what new users copy**, so a stale one hands them an old
runtime.

Done in order: pins updated → `v1.0.7` tagged and pushed → the floating `v1` tag
moved → *then* `fingerprint` and `published` updated here, in the same commit.

The `v1` move is verified by dereferencing, because `rev-parse` on an annotated
tag returns the tag object rather than the commit:

```
HEAD:        5134e2590a3eed502123ac29fa2f7bd080e8dff2
v1 (remote): 5134e2590a3eed502123ac29fa2f7bd080e8dff2
v1.0.7:      5134e2590a3eed502123ac29fa2f7bd080e8dff2
```

### `nodus-vscode` — packaged, awaiting a Marketplace upload

```
[--] nodus-vscode (0.1.3) — NEEDS REPUBLISH
     keywords moved: 602761bf77ebb21e -> 526b2f659e90124e
```

`each` is new in #480, and the TextMate grammar lists every keyword explicitly,
so an unnamed one renders as a plain identifier. That is the two-release
regression `tests/test_keyword_coverage.py` exists to prevent — and how this was
found, from the fingerprint *not* moving when it should have.

Prepared: grammar fix committed (`03aa535`), version bumped to 0.1.4 and pushed
(`31d9978`), `nodus-lang-0.1.4.vsix` packaged and verified by reading the
grammar back out of the zip rather than trusting the build.

**The flag stays set until the VSIX is actually uploaded.** Clearing it on the
strength of a built artifact would be exactly the "flag cleared before the work
is done" this manifest warns is worse than no flag.

## 4. Work left behind

`git status` in each checkout. Eleven of twelve clean; one was not:

```
nodus-workflow    M packaging/nodus-workflow-shim/README.md
```

A correction left uncommitted during the #483 rename earlier in this cycle. The
deprecation shim's README claimed it "ships no code of its own" — it re-exports
`nodus_flow` so existing `import nodus_workflow` keeps working, with a
`DeprecationWarning`. Telling a reader their code will break when it will not is
the wrong direction to be wrong in. Committed (`07f64a7`).

Not republished: `nodus-workflow` is a frozen deprecation alias receiving no
further releases, so its PyPI page keeps the old sentence. Worth a republish
only if the alias is touched for another reason.

---

## Ecosystem state after this release

- **36 PyPI projects** — nodus-lang plus 35 companions, all admitting 5.6.0
- **2 non-PyPI consumers** — one republished, one prepared and pending
- **12 checkouts** — all clean
