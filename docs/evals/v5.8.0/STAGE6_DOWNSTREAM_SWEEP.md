# v5.8.0 — Stage 6 downstream republish sweep

**Date:** 2026-08-30
**Verdict:** pass — one consumer was stale, republished, flag cleared

Four questions, three of them tooled.

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

All 6 companions admit nodus-lang 5.8.0.
```

Every dependent floats, per the policy decided 2026-08-17: a companion does not
cap `nodus-lang`, because a hard upper bound on a first-party dependency turns
every major into a two-repo release train. Resolved with `packaging` against
**published** metadata rather than read by eye — the failure that made 5.0.0
unadoptable was five ranges transcribed with the upper bound dropped.

### Declared but not yet published

```
  nodus-workflow-ai          >= 5.8.0      ok
      #93. Needs step names on `task()` (#679), which ship in 5.8.0.
```

`nodus-workflow-ai` is built and its repo exists, but it is **not published** —
the PyPI project has to be created first, and that is deliberately outstanding.
Its floor is registered in `UNPUBLISHED_COMPANIONS` so the gate reports it every
cycle, and it flags `FLOOR UNRELEASED` if the floor ever names a version that does
not exist. With 5.8.0 out, the floor is satisfiable for the first time.

**On publish, move it into `COMPANIONS` in the same commit.**

---

## 2. Has any companion drifted from what it published?

```
companion                    verdict  detail
------------------------------------------------------------------------------
nodus-a2a                    ok       6 files identical to 0.1.0
nodus-a2a-wire               ok       9 files identical to 0.1.0
nodus-extension              ok       16 files identical to 0.1.2
nodus-flow                   ok       7 files identical to 0.2.0
nodus-jupyter                ok       4 files identical to 0.1.0
nodus-mcp                    ok       14 files identical to 0.1.3
nodus-mcp-server             ok       4 files identical to 0.1.12
nodus-memory                 ok       7 files identical to 0.1.0
nodus-native-memory-engine   ok       1 files identical to 0.1.1
nodus-sdk                    ok       14 files identical to 0.1.2
nodus-store-sql              ok       6 files identical to 0.1.0

All 11 companions match what they published.
```

Content compared from the published sdist, not inferred from commit counts — a
git heuristic gave four false positives at v4.2.0, because a commit can touch only
docs, only CI, or only tests.

---

## 3. Non-PyPI consumers left behind

The content-hash sweep above structurally cannot see these: they are not on PyPI.

| Consumer | Before | Action |
|---|---|---|
| `nodus-vscode` 0.1.5 | **in step** | none — 5.8.0 adds no keywords (`cancel`/`wait` are builtins, not keywords) |
| `nodus-run-action` v1.0.8 | **STALE** — `nodus_version` 5.7.1 → 5.8.0 | republished |

### nodus-run-action → v1.0.9

Its README documents a pinned `version:` for reproducible CI, and that pin is what
new users copy — stale, it hands them an old runtime.

1. `README.md` examples pinned to `5.8.0` (two sites)
2. CHANGELOG entry for 1.0.9
3. tagged `v1.0.9`, pushed
4. **floating `v1` moved**, verified against the remote rather than locally —
   `rev-parse` on an annotated tag returns the tag object, not the commit:

```
$ git ls-remote origin 'refs/tags/v1*'
90b00a4617a1b6c9807183586e327a0fee6a702b   refs/tags/v1
90b00a4617a1b6c9807183586e327a0fee6a702b   refs/tags/v1.0.9
$ git rev-parse HEAD
90b00a4617a1b6c9807183586e327a0fee6a702b
```

Flag cleared afterwards, with `fingerprint` and `published` updated in the same
commit as required:

```
  [ok] nodus-vscode (0.1.5)      keywords unchanged
  [ok] nodus-run-action (v1.0.9) nodus_version unchanged

Consumers: PASS  2/2 in step
```

---

## 4. Work left behind in a checkout

All thirteen sibling checkouts clean:

| Checkout | Branch | Dirty |
|---|---|---|
| nodus-mcp, nodus-a2a, nodus-memory, nodus-native-memory-engine, nodus-extension, nodus-mcp-server, nodus-vscode, nodus-run-action, nodus-workflow, nodus-sdk, nodus-workflow-ai | `main` | 0 |
| nodus-jupyter, nodus-store-sql | `master` | 0 |

(`nodus-jupyter` and `nodus-store-sql` are on `master`, not `main` — long-standing
and not a finding.)

---

## Outstanding after this sweep

- **#691** — a step body calling an imported module's function truncates silently
  (found by Stage 5; pre-existing, not a 5.8.0 regression).
- **`nodus-workflow-ai` is unpublished.** Its PyPI project must be created before
  the first upload. Floor `>=5.8.0` is now satisfiable.
