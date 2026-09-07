# v5.12.0 — Stage 5 post-publish eval

**Date:** 2026-09-06
**Target:** `pip install nodus-lang==5.12.0` from PyPI, fresh venv, empty project
**Verdict:** **PASS.** Everything the release claims works as a new user would
meet it. No defect found; nothing to supersede.

Stage 5 asks a different question from Gate 10: not *"what can I make fail?"*
against a local wheel, but *"does this work the way someone arriving new would
expect?"* against the thing actually published. At 5.7.1 that distinction
mattered — Stage 5 found #662 by using two new features in one program, where
neither was broken alone.

---

## Install

```
attempt 1: index lag, retrying
installed on attempt 2

resolved: ...\s5\.venv\Lib\site-packages\nodus\__init__.py
version:  5.12.0
```

The first `pip install` failed and the second succeeded ~20s later. That is the
documented index lag, and it is why `pip install <name>==<version>` is the only
authoritative check — PyPI's JSON API serves stale data after an upload and has
reported *zero files* for a version that had just landed (5.6.0).

Resolved from `site-packages`, not a checkout: this eval ran from a temp
directory, so the repo-root `nodus.py` shim was never in play.

---

## What a new user meets

A project with a `nodus.toml`, a `src/main.nd` holding a two-step workflow whose
steps race one state cell, and one misspelled type annotation.

### The headline: `nodus check --staged`

```
  [ 1 found]   concurrent-write (#547)
                ...src\main.nd: in workflow 'tally', steps 'north' and 'south' both write
                state 'total' and nothing orders them. ... Declare `with { merge: "sum" }`
                (or "append") to combine them, or `merge: "any"` for deliberate
                last-write-wins.
  [ok]          default-store-sqlite (#797)
  [not checked] record-equality (#545)
                not checkable from source: ... Run the program or its tests with
                NODUS_STAGED_FLIP_REPORT=<path> set, then re-run this
  [ 1 found]   unknown-type-name (#609)
  [ok]          worker-dispatcher (#798)

2 thing(s) to fix before 6.0.0; 1 could not be checked from source
  For the rest, run your program or tests with NODUS_STAGED_FLIP_REPORT=<path> set,
  then re-run this.
```

Project discovery worked with no argument — it found the root, the entry point,
and the workflow inside it. Every flip is named, the unanswerable one says so,
and the summary never claims readiness. That is R4 holding in the shipped
artifact, which is where it matters.

### The two halves join

```
$ NODUS_STAGED_FLIP_REPORT=staged.jsonl nodus run eq.nd
$ cat staged.jsonl
{"flip": "record-equality", "message": "two distinct records with equal fields
 compared as not equal; `==` becomes structural at 6.0.0 ..."}

$ NODUS_STAGED_FLIP_REPORT=staged.jsonl nodus check --staged
  [ 1 found]   record-equality (#545)  [from a run]
```

`[not checked]` → `[from a run]`, and the "collect the rest" hint stops once you
have. The flip nothing static can reach is answered by the mechanism built for
it, from the published package.

### Each fix, exercised

| | |
|---|---|
| **#791** `workflow cleanup --dry-run --force` | `Error: unknown flag '--dry-run' for 'nodus workflow cleanup'.` — exit 1, nothing deleted. This is the one that destroyed state. |
| **#794** the four phantom `nodus test` flags | 0 mentions in `--help`; `--watch` is refused by name |
| **#807** `nodus check src` | *"No Nodus project in 'src': no nodus.toml. The project root is '…\proj' — run this from there, or name a file directly."* — no errno |
| **#174** the store notice | `becomes SQLite at 6.0.0` reaches a plain `nodus run`, on the second run once the store holds records |
| the program itself | `nodus run` with no argument found and ran the project |

---

## Nothing found

No defect, no surprise, nothing that would make 5.12.0 a release to supersede.
The GitHub release can be created (step 11), which is deliberately last: release
immutability is permanent, so a bad version can be left unreferenced on PyPI but
a GitHub release asserting it could never be corrected.

## Carried forward

Both follow-ups are from Gate 10 and neither is a defect in the release:

1. **`DEPENDENTS` is missing `nodus-workflow-ai`**, which declares
   `nodus-lang>=5.8.0`. Run by hand this cycle: 28 passed. The registry's
   criterion (*imports* nodus-lang) is narrower than the risk, since a package
   that emits Nodus source or shells out to the CLI can break without importing.
2. **The release probes are not run by CI**, which is why a stale
   `--allow-paths` line survived a change that fixed the identical line in a
   test.
