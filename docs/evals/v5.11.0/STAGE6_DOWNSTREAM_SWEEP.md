# v5.11.0 — Stage 6 downstream sweep

**Verdict: the ecosystem admits 5.11.0, and one consumer needed republishing.**
It was republished in this pass rather than recorded as an action, so the flag is
cleared against work that is actually done.

| question | tool | result |
|---|---|---|
| do published ranges still admit the new version? | `check_downstream_constraints` | **7/7 ok**, exit 0 |
| has a companion drifted from what it published? | `check_publish_drift` | **13/13 match**, exit 0 |
| are non-PyPI consumers left behind? | `nodus_gate --consumers` | 1 stale → **republished** → 2/2 in step |
| is work left uncommitted in a checkout? | `git status` each | all clean |

---

## 1. Ranges — resolved, not read

```
nodus-mcp                    0.1.3      >=4.0.0      ok
nodus-mcp-server             0.1.12     >=4.0.5      ok
nodus-extension              0.1.2      >=4.0.0      ok
nodus-sdk                    0.1.2      >=4.0.0      ok
nodus-native-memory-engine   0.1.1      >=4.0.0      ok
nodus-jupyter                0.1.0      >=4.0.0      ok
nodus-workflow-ai            0.1.0      >=5.8.0      ok
```

Resolved with `packaging` against **published** metadata, which is the whole
point of the tool. `>=4.0.0,<5.0.0` reads as "admits 4.x" to a human eye and the
clause that forbids the new version sits at the far end of the string — that is
how five of six companions capped 5.0.0 out of existence and made it unadoptable
for anyone using the ecosystem (#445). No cap exists now, by policy: a companion
does not upper-bound `nodus-lang`.

## 2. Drift — file contents, not version strings

All 13 companions are byte-identical to what they published. This compares
downloaded sdists against each checkout, so it catches the case a version
comparison cannot: a companion whose `main` has moved without a release.

## 3. Consumers — one was stale, and is not any more

```
[--] nodus-run-action (v1.0.11)  NEEDS REPUBLISH
     nodus_version moved: 5.10.0 -> 5.11.0
```

`nodus-vscode` was in step (its fingerprint is the keyword set, unchanged this
release — 5.11.0 adds builtins, not keywords).

`nodus-run-action` pins `version: '5.11.0'` in its README examples, and that pin
is what a new user copies into their own workflow. Left stale it hands them an
old runtime, silently and indefinitely. Republished:

- `README.md` examples bumped, commit `3d4cb12`, tagged **v1.0.12**
- `tools/consumers.json` updated in the same commit as this record —
  `published: v1.0.12`, `fingerprint: 5.11.0`
- re-checked: **`Consumers: PASS — 2/2 in step`**

The manifest's own rule is that a flag is cleared only *after* the republish,
never before, because a flag cleared early is worse than no flag. That order was
followed here.

Both non-PyPI consumers exist in this manifest because Stage 6's other two tools
hash published sdists and **structurally cannot see** a VSIX or a GitHub Action.
Both have shipped stale in the past.

## 4. Checkout hygiene

`nodus-mcp`, `nodus-sdk`, `nodus-extension`, `nodus-a2a`, `nodus-memory`,
`nodus-workflow`, `nodus-vscode`, `nodus-run-action` — all report 0 changed
files. Nothing was left half-finished in a sibling repo by this release.

## 5. Not covered here

The wheel's own adversarial validation is `CREATOR_VALIDATION.md`; the published
package's new-user check is `POSTPUBLISH_EVAL.md`. This document answers only
*what did this release break or leave behind downstream*.
