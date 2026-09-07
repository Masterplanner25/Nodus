# v5.12.0 — Stage 6 downstream sweep

**Date:** 2026-09-06
**Verdict:** **clean**, after republishing one consumer.

Stage 6 asks what the release broke or left behind downstream. Four questions,
three of them tooled.

---

## 1. Do published ranges still admit the new version?

```
All 7 companions admit nodus-lang 5.12.0.        exit 0
```

| companion | published | range |
|---|---|---|
| nodus-mcp | 0.1.3 | `>=4.0.0` |
| nodus-mcp-server | 0.1.12 | `>=4.0.5` |
| nodus-extension | 0.1.2 | `>=4.0.0` |
| nodus-sdk | 0.1.2 | `>=4.0.0` |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` |
| nodus-jupyter | 0.1.0 | `>=4.0.0` |
| nodus-workflow-ai | 0.1.0 | `>=5.8.0` |

Every floor, no cap — the 2026-08-17 policy holding. This is the question that
made 5.0.0 unadoptable (#445): five of six companions capped `<5.0.0`, the sweep
transcribed the ranges by eye, and `>=4.0.0,<5.0.0` reads as *"admits 4.x"*
because the clause that forbids the new version sits at the far end of the
string. Resolved with `packaging` against **published** metadata, never read.

## 2. Has any companion drifted from what it published?

```
All 13 companions match what they published.     exit 0
```

File contents compared against each downloaded sdist, not version strings.

## 3. Non-PyPI consumers left behind

The drift sweep hashes sdists, so it structurally cannot see a VS Code extension
or a GitHub Action. `nodus_gate --consumers` covers those, and it found one:

```
[--] nodus-run-action (v1.0.12) — NEEDS REPUBLISH
     nodus_version moved: 5.11.0 -> 5.12.0
```

Its README pins `version: '5.12.0'` in two examples, and that pin is what a new
user copies for reproducible CI — stale, it hands them an old runtime.

**Republished as `v1.0.13`, then** `tools/consumers.json` updated in the same
change. That order is the rule: a flag cleared before the work is done is worse
than no flag.

```
Consumers: PASS — 2/2 in step
```

`nodus-vscode` needed nothing: no keyword was added this release, and that entry
tracks a hash of `ALL_KEYWORDS`.

## 4. Work left behind

`git status` on each checkout, which nothing automates:

```
13 repositories — 0 uncommitted, 0 unpushed
```

Two are on `master` rather than `main` (`nodus-store-sql`, `nodus-jupyter`),
which is expected and recorded in `COMPANION_REPOS.md`.

---

## Follow-ups

Neither is a defect in 5.12.0; both are gaps in the machinery, found by it.

1. **`DEPENDENTS` is missing `nodus-workflow-ai`.** It declares
   `nodus-lang>=5.8.0` and is not in `tools/check_dependent_suites.py`. Run by
   hand at Gate 10: **28 passed**. The registry's criterion is *"companions that
   import nodus-lang"* and by that criterion the exclusion is right — the
   package never imports it, it **emits Nodus source**. But that is narrower
   than the risk: a generator, or anything shelling out to the CLI, can be
   broken without importing, and #791 is exactly that shape.
2. **The release probes are not run by CI.** A stale `--allow-paths` on
   `nodus graph` survived in `release_claims_probe.py` through the very change
   (#791) that fixed the identical line in `test_graph_static_plan.py` — because
   CI ran the test and not the probe. Running them per-PR is not free (they need
   a built wheel and a clean venv), so this is a decision rather than an
   oversight to correct.
