# v5.14.0 — Stage 6 downstream republish sweep

**Date:** 2026-09-18
**Trigger:** `nodus-lang 5.14.0` live on PyPI; GitHub release `v5.14.0` created
after the upload
**Verdict:** **CLEAN.** Nothing left behind; both stale consumers republished
before their flags were cleared.

Stage 6 asks *"what downstream did this break or leave behind?"* Four
questions, three of them tooled.

---

## 1. Do published ranges still admit the new version?

```
python -m tools.check_downstream_constraints
```

| companion | published | nodus-lang range | verdict |
|---|---|---|---|
| nodus-a2a-wire | 0.1.0 | `>=4.0.0` | ok |
| nodus-extension | 0.1.2 | `>=4.0.0` | ok |
| nodus-jupyter | 0.1.0 | `>=4.0.0` | ok |
| nodus-mcp | 0.1.3 | `>=4.0.0` | ok |
| nodus-mcp-server | 0.1.13 | `>=4.0.5` | ok |
| nodus-native-memory-engine | 0.1.1 | `>=4.0.0` | ok |
| nodus-sdk | 0.1.2 | `>=4.0.0` | ok |
| nodus-workflow-ai | 0.1.0 | `>=5.8.0` | ok |

**8/8 admit 5.14.0.** Resolved with `packaging` against published metadata, as
the #445 lesson requires — never by eye.

---

## 2. Has a companion drifted from what it published?

```
python -m tools.check_publish_drift
```

**13/13 match what they published**, file contents compared against each
published sdist. `nodus-mcp-server` compares against **0.1.13** now — cut on
2026-09-17 during this cycle's example sweep, when restarting the server after
a mistaken kill showed its `--http` mode had answered every request with a 500
since 0.1.11 and that a fresh install failed at import under mcp 2.x. Both are
in that release's changelog; neither was caused by nodus-lang.

---

## 3. Non-PyPI consumers

```
nodus_gate --consumers --strict
```

Before this sweep: **1/3 in step**, two stale — both because `nodus_version`
moved, which is by construction.

| consumer | tracks | republished as | flag cleared |
|---|---|---|---|
| nodus-vscode | keywords | — (in step; the keyword set did not move) | n/a |
| nodus-run-action | nodus_version | **v1.0.15** — README examples pin `5.14.0` | `fingerprint` → 5.14.0, `published` → v1.0.15 |
| nodus-wiki | nodus_version | **`69300aa`** on `Masterplanner25/Nodus.wiki` | `fingerprint` → 5.14.0, `published` → 69300aa |

After: **3/3 in step**, `--strict`.

The wiki got substance rather than a banner bump, as at 5.13.0. Its Security
page described `serve`'s confinement without knowing that through 5.13.0 a
step past the budget **hung the request forever** — the page now says so, tells
operators of 5.13.0-or-earlier not to accept workflow submissions from callers
they do not trust to terminate, and documents `--time-limit` / `timeout_ms`.
The version banner moved on Home, Getting-Started, Roadmap and the footer.

Both flags were cleared **after** the republish, in the same commit as the
fingerprint, per the rule: a flag cleared before the work is done is worse than
no flag.

---

## 4. Work left behind?

Every companion checkout, by hand:

| checkout | branch | dirty | unpushed |
|---|---|---|---|
| nodus-mcp, nodus-a2a, a2a-wire-pub, nodus-memory, nodus-native-memory-engine, nodus-extension, nodus-sdk, nodus-workflow-ai, nodus-mcp-server, nodus-workflow, nodus-vscode, nodus-run-action | main | 0 | 0 |
| nodus-store-sql, nodus-jupyter, nodus-wiki | master | 0 | 0 |

**15 checkouts, all clean, nothing unpushed.**

---

## Left open, on purpose

- **nodus-mcp-server#3** — the port to mcp 2.x. 0.1.13 pins `mcp<2` so fresh
  installs work; the port is real work and not a release blocker.
- The first HTTP request of any process still pays the CA-bundle load once
  (#855 made it once per process, not zero). Stated in the changelog and the
  orchestration example; not a downstream concern.
