# v5.9.0 — Stage 6, downstream sweep

**Verdict: clean, after one republish.** Nothing was broken and nothing blocked.
The four questions Stage 6 asks, answered.

| question | answer |
|---|---|
| Do published ranges still admit the new version? | **yes, 7/7** |
| Has a companion drifted from what it published? | **no, 12/12 identical** |
| Are non-PyPI consumers left behind? | one was — **`nodus-run-action`, republished as v1.0.10** |
| Is work left behind in any checkout? | **no, 14/14 clean** |

---

## 1. Ranges — all 7 admit 5.9.0

```
companion                    published  nodus-lang range   verdict
nodus-mcp                    0.1.3      >=4.0.0            ok
nodus-mcp-server             0.1.12     >=4.0.5            ok
nodus-extension              0.1.2      >=4.0.0            ok
nodus-sdk                    0.1.2      >=4.0.0            ok
nodus-native-memory-engine   0.1.1      >=4.0.0            ok
nodus-jupyter                0.1.0      >=4.0.0            ok
nodus-workflow-ai            0.1.0      >=5.8.0            ok

All 7 companions admit nodus-lang 5.9.0.      EXIT=0
```

Resolved with `packaging` against **published** metadata, never read by eye. That
rule exists because five of six companions once published `nodus-lang<5.0.0`,
making 5.0.0 unadoptable for anyone using the ecosystem — and the sweep that
should have caught it transcribed five of six ranges with the upper bound
dropped. `>=4.0.0,<5.0.0` reads as "admits 4.x", which is what the eye checks
for; the clause that forbids the new version sits at the far end of the string.

The policy since 2026-08-17 is that companions do **not** cap `nodus-lang`, and
the table above shows it holding: every range is a floor with no ceiling.

`nodus-workflow-ai`'s `>=5.8.0` floor is the one worth noting — it was registered
before that version existed, was unsatisfiable for a day, and is now two releases
inside its range.

## 2. Drift — all 12 match what they published

```
All 12 companions match what they published.      EXIT=0
```

File contents compared against each downloaded sdist, not version strings. Exit
**0**, not 2 — no companion was skipped, and a skip is not a pass.

## 3. Non-PyPI consumers — one was stale, and is now republished

```
[ok] nodus-vscode (0.1.5)      keywords unchanged
[--] nodus-run-action (v1.0.9) NEEDS REPUBLISH
     nodus_version moved: 5.8.0 -> 5.9.0
```

**`nodus-run-action` pins a `version:` in its README examples**, and that pin is
what a new user copies into their own CI. Left stale it silently hands them a
runtime two releases old — which is exactly the failure the `--consumers` phase
was built to surface, because Stage 6's drift sweep hashes published sdists and
structurally cannot see a GitHub Action or a VSIX.

**Republished, then cleared — in that order.** The rule is that a flag is cleared
only *after* the work is done, with `fingerprint` and `published` updated in the
same commit; a flag cleared before is worse than no flag.

```
nodus-run-action  6f56222  pin README examples to nodus-lang 5.9.0
                  tagged v1.0.10, and `v1` moved to it
tools/consumers.json  published v1.0.9 -> v1.0.10
                      fingerprint  5.8.0 -> 5.9.0
```

Re-run afterwards:

```
[ok] nodus-vscode (0.1.5)       keywords unchanged
[ok] nodus-run-action (v1.0.10) nodus_version unchanged
Consumers: PASS — 2/2 in step
```

Only the documented examples moved; the action's own `version` input still
defaults to empty, meaning latest. And `v1` is a moving major tag, so it had to be
force-updated to the new commit — a user pinned to `@v1` gets the corrected
README's behaviour, and one pinned to `@v1.0.9` keeps exactly what they had.

Worth noting what this consumer is *for*: a CI pin is the place an old runtime
goes unnoticed longest. Nobody re-reads a working workflow file. That is why the
`--consumers` phase exists at all — Stage 6's drift sweep hashes published sdists
and structurally cannot see a GitHub Action.

`nodus-vscode` is genuinely in step: the keyword set it highlights is unchanged by
this release. That check reads `lexer.ALL_KEYWORDS` from this tree rather than a
sibling checkout, which is why it works on CI — and why 5.6.0's `each` was
invisible to it until `ALL_KEYWORDS` learned the word.

## 4. Work left behind — none

All 14 checkouts clean, nothing uncommitted, nothing unpushed:

```
nodus-mcp, nodus-a2a, a2a-wire-pub, nodus-memory,
nodus-native-memory-engine, nodus-extension, nodus-sdk,
nodus-store-sql (master), nodus-workflow-ai, nodus-jupyter (master),
nodus-mcp-server, nodus-workflow, nodus-vscode, nodus-run-action
```

Checked at `C:\codev\a2a-wire-pub` for the wire adapter, not
`C:\codev\nodus-a2a-wire` — that path is a worktree of the *coordinator* repo's
old history, so a status check there answers about the wrong project.

---

## Follow-up

**None outstanding.** The one item this sweep found — `nodus-run-action`'s stale
CI pin — was republished as `v1.0.10` and its flag cleared afterwards, so
`--consumers` reports 2/2 in step.
