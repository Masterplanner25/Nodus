# v5.3.0 — Stage 6 Downstream Sweep

What did this release break or leave behind? Four questions, three of them tooled.

| | |
|---|---|
| Release | nodus-lang 5.3.0, published 2026-08-25 |
| Date | 2026-08-25 |
| Verdict | **PASS** — one consumer was stale and has been republished |

---

## 1. Do published companion ranges still admit the new version?

```
companion                    published  nodus-lang range           verdict
------------------------------------------------------------------------------
nodus-mcp                    0.1.3      >=4.0.0                    ok
nodus-mcp-server             0.1.12     >=4.0.5                    ok
nodus-extension              0.1.2      >=4.0.0                    ok
nodus-sdk                    0.1.2      >=4.0.0                    ok
nodus-native-memory-engine   0.1.1      >=4.0.0                    ok
nodus-jupyter                0.1.0      >=4.0.0                    ok

All 6 companions admit nodus-lang 5.3.0.          exit 0
```

Resolved with `packaging` against **published** PyPI metadata, not read by eye.
That distinction is the whole lesson of 5.0.0: five of six companions published
`nodus-lang<5.0.0`, `pip install nodus-lang==5.0.0 nodus-mcp` was
`ResolutionImpossible`, and the sweep that quarter transcribed five of six ranges
with the upper bound dropped. `>=4.0.0,<5.0.0` reads as "admits 4.x", which is
what the eye checks for; the clause that forbids the new version sits at the far
end of the string.

All six float, per the policy decided 2026-08-17 that companions do not cap
`nodus-lang`.

---

## 2. Has any companion drifted from what it published?

```
companion                    verdict  detail
------------------------------------------------------------------------------
nodus-a2a                    ok       6 files identical to 0.1.0
nodus-extension              ok       16 files identical to 0.1.2
nodus-jupyter                ok       4 files identical to 0.1.0
nodus-mcp                    ok       14 files identical to 0.1.3
nodus-mcp-server             ok       4 files identical to 0.1.12
nodus-memory                 ok       7 files identical to 0.1.0
nodus-native-memory-engine   ok       1 files identical to 0.1.1
nodus-sdk                    ok       14 files identical to 0.1.2
nodus-store-sql              ok       6 files identical to 0.1.0

All 9 companions match what they published.       exit 0
```

Content comparison against each downloaded sdist. Not a git heuristic: counting
commits since the version bump produced **four false positives** at v4.2.0,
because a commit can touch only docs, only CI, or only tests.

---

## 3. Non-PyPI consumers — one was stale

The content-hash sweep above works by hashing published sdists, so anything not
on PyPI is structurally invisible to it. Both such consumers have shipped stale
before.

```
  [ok] nodus-vscode (0.1.3) — keywords unchanged
  [--] nodus-run-action (v1.0.3) — NEEDS REPUBLISH
       nodus_version moved: 5.2.0 -> 5.3.0
```

**nodus-vscode** needs nothing: 5.3.0 added no language keywords. `writable_paths`
is a constructor argument and `--writable-paths` a CLI flag; neither is grammar.

**nodus-run-action was republished.** Its README documents a pinned `version:`
for reproducible CI, and that pin is what new users copy into their workflows, so
a stale one hands them an old runtime.

```
README.md:62   version: '5.2.0'  ->  '5.3.0'
README.md:85   version: '5.2.0'  ->  '5.3.0'
```

Committed (`3d11f9a`), tagged `v1.0.4`, and the floating `v1` moved. Verified by
dereferencing rather than trusting `rev-parse`, which returns the tag object for
an annotated tag rather than the commit:

```
$ git ls-remote origin 'refs/tags/v1^{}'
3d11f9a254d453851b11e69983e0d1cb406b4ee5   refs/tags/v1^{}
$ git rev-parse HEAD
3d11f9a254d453851b11e69983e0d1cb406b4ee5
```

`tools/consumers.json` updated to `v1.0.4` / `5.3.0` **after** the republish, in
the same commit as this document — a flag cleared before the work is done is
worse than no flag.

```
  [ok] nodus-vscode (0.1.3) — keywords unchanged
  [ok] nodus-run-action (v1.0.4) — nodus_version unchanged
Consumers: PASS — 2/2 in step
```

---

## 4. Work left behind

Every checkout, by hand — the one question with no tool.

```
nodus-mcp                    main     clean
nodus-a2a                    main     clean
nodus-memory                 main     clean
nodus-native-memory-engine   main     clean
nodus-extension              main     clean
nodus-mcp-server             main     clean
nodus-jupyter                master   clean
nodus-vscode                 main     clean
nodus-run-action             main     clean
nodus-workflow               main     clean
nodus-sdk                    main     clean
nodus-store-sql              master   clean
```

Twelve checkouts, nothing uncommitted. Note `nodus-jupyter` and `nodus-store-sql`
are on `master`, not `main` — a recurring trip hazard when scripting across them.

---

## What this sweep does not answer

- **Whether the #490 manifest break affects anyone.** No companion ships a
  `nodus.toml`, so nothing here is exposed — but a third-party project with an
  unknown table in its manifest will stop loading, and there is no way to survey
  those. It is in the CHANGELOG and the release notes.
- **Whether companions would *benefit* from 5.3.0.** They admit it and their
  suites pass against it (721 tests, Gate 10a). None yet uses `writable_paths` or
  the new capability names; whether any should is a separate question.
- **aindy-runtime.** Not a first-party checkout and not in the sweep. It consumes
  the VM as a guest execution engine and was the reported source of #473's
  provenance, so the capability vocabulary is the part most likely to matter to
  it.
