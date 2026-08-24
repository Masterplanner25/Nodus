# v5.2.0 — Stage 6 Downstream Sweep

What this release broke or left behind downstream. Four questions, three tooled.

| | |
|---|---|
| Release | nodus-lang 5.2.0, <https://pypi.org/project/nodus-lang/5.2.0/> |
| Date | 2026-08-24 |
| Verdict | **PASS** — one consumer republished (`nodus-run-action` v1.0.3) |

---

## Q1 — Do published ranges still admit the new version?

`tools/check_downstream_constraints.py`, which resolves **published** PyPI metadata
with `packaging` rather than reading a range by eye.

```
companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.2      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.2.0.
```

All six float. **This is the question that failed at 5.0.0**, where five of six
published `nodus-lang<5.0.0`, making `pip install nodus-lang==5.0.0 nodus-mcp`
`ResolutionImpossible` — and the sweep at the time transcribed five of six ranges
with the upper bound dropped. Reading `>=4.0.0,<5.0.0` by eye reads as "admits
4.x"; the clause that forbids the new version is at the far end of the string.
The policy since (#445) is that companions do not cap `nodus-lang`, and it holds.

## Q2 — Has a companion drifted from what it published?

`tools/check_publish_drift.py`, which downloads each published sdist and compares
file contents. Not a git heuristic — counting commits since the version bump gave
four false positives at v4.2.0, because a commit can touch only docs, only CI, or
only tests.

```
All 9 companions match what they published.
```

`nodus-a2a`, `nodus-extension`, `nodus-jupyter`, `nodus-mcp`, `nodus-mcp-server`,
`nodus-memory`, `nodus-native-memory-engine`, `nodus-sdk`, `nodus-store-sql` — all
identical to their published artifacts. Nothing to republish for drift.

## Q3 — Which non-PyPI consumers has the release left behind?

`nodus_gate --consumers`. Stage 6's content-hash sweep works by hashing published
sdists and wheels, so anything **not on PyPI is structurally invisible to it** —
which is both non-PyPI consumers, and both have shipped stale before.

**One catch, and it is the reason this phase exists:**

```
[--] nodus-run-action (v1.0.2) — NEEDS REPUBLISH
     nodus_version moved: 5.1.0 -> 5.2.0
     Its README documents a pinned `version:` for reproducible CI. The pin is
     the version new users copy, so it going stale hands them an old runtime.
```

`nodus-vscode` was in step — the keyword set did not change this release, and its
fingerprint tracks keywords rather than the version.

### Republished: nodus-run-action v1.0.3

- README `version:` pins updated `5.1.0` → `5.2.0` (two examples)
- committed and pushed to `main` as `abf8953`
- tagged `v1.0.3`
- **floating `v1` tag moved**, which is the half that gets forgotten

Verified by dereference rather than by `rev-parse`, since `rev-parse` on an
annotated tag returns the tag object rather than the commit:

```
abf89538a9927922891039b903b2813f470b20c4  refs/tags/v1^{}
abf89538a9927922891039b903b2813f470b20c4  refs/tags/v1.0.3^{}
```

Both resolve to the new commit, so `uses: Masterplanner25/nodus-run-action@v1`
now installs 5.2.0.

Flag cleared in `tools/consumers.json` **after** republishing, with `fingerprint`
and `published` updated in the same commit — a flag cleared before the work is
done is worse than no flag. Re-run: `Consumers: PASS — 2/2 in step`.

## Q4 — Work left behind in a checkout?

By hand; there is no tool for this one.

| checkout | branch | uncommitted |
|---|---|---|
| nodus-mcp | main | 0 |
| nodus-mcp-server | main | 0 |
| nodus-extension | main | 0 |
| nodus-sdk | main | 0 |
| nodus-native-memory-engine | main | 0 |
| nodus-jupyter | **master** | 0 |
| nodus-a2a | main | 0 |
| nodus-memory | main | 0 |
| nodus-store-sql | **master** | 0 |
| nodus-vscode | main | 0 |
| nodus-run-action | main | 0 |

All clean. `nodus-jupyter` and `nodus-store-sql` are on `master`, not `main` —
long-standing and recorded, noted here so a future sweep does not read it as
drift.

---

## Companion suites

Run at Gate 10 step 0, **before** the upload, which is the ordering added after
5.0.3 shipped a broken `nodus-sdk` and Stage 6 caught it one release too late:

```
nodus-mcp 363 · nodus-mcp-server 25 · nodus-extension 126
nodus-sdk 99 · nodus-native-memory-engine 76 · nodus-jupyter 32
All 6 dependent suites pass.   (721 tests, exit 0, first run)
```

---

## Not covered

- **Companion co-install against 5.2.0 specifically.** Q1 proves the ranges admit
  it; an actual `pip install nodus-lang==5.2.0 nodus-mcp` resolution was not run.
  The 5.0.0 failure would have been caught by Q1 as it now stands.
- **nodus-vscode republish.** Not required — keywords unchanged — so the
  Marketplace listing still advertises 0.1.3 built against an older runtime. The
  extension spawns the *installed* `nodus.exe`, so LSP behaviour follows whatever
  the user has, not the VSIX.
- **The showcase projects and `packages/` incubators**, which have no published
  artifact to drift from.
