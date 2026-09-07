# v5.12.0 — Gate 10 creator validation (pre-publish)

**Date:** 2026-09-06
**Artifact:** `dist/nodus_lang-5.12.0-py3-none-any.whl`, built from the tagged
tree (`v5.12.0` → `4ec6f4d`)
**Verdict:** **PASS.** Both halves green. Cleared to publish.

Gate 10 asks *"what can I make fail?"* against a local wheel, before anything
immutable exists. It has two halves and the first is not optional: 5.0.3 shipped
with 32 green probes and broke `nodus-sdk` at construction, because probes
validate nodus-lang against itself and nothing in them constructs a dependent.

---

## 10a — dependent suites, before the upload

```
companion                      verdict   detail
nodus-mcp                      PASS      363 passed in 40.94s
nodus-mcp-server               PASS       25 passed in  1.17s
nodus-extension                PASS      126 passed in 29.42s
nodus-sdk                      PASS       99 passed in 11.53s
nodus-native-memory-engine     PASS       76 passed in  0.47s
nodus-jupyter                  PASS       32 passed in  2.59s

All 6 dependent suites pass.        exit 0
```

721 tests. Run with nothing else going, per the 5.1.0 lesson where a concurrent
probe run turned `nodus-mcp` red and three serial re-runs were green.

### A coverage gap in the gate itself

`nodus-workflow-ai` declares `nodus-lang>=5.8.0` and is **not** in
`DEPENDENTS`. Its suite was run by hand for this release: **28 passed** against
5.12.0, so nothing here is at risk.

The registry's criterion is *"companions that import nodus-lang"*, and by that
criterion the exclusion is correct — the package never imports it. It **emits
Nodus source**: `bridge.py` turns a validated plan into a graph, and its only
imports are `typing` and its own `validation` module.

But that criterion is narrower than the risk. A package that generates Nodus
source, or shells out to the CLI, can be broken by a nodus-lang change without
importing anything — #791 is precisely that shape, since a flag it passes could
now be refused. Worth widening the registry from *imports* to *declares a
dependency*; 28 tests cost 0.65s. **Filed rather than changed mid-release.**

---

## 10b — adversarial probes against the wheel

```
115/115 probes passed        exit 0
```

Run from `%TEMP%` — outside the checkout — against
`.venv-validation`, with `--require-installed`.

### The wrong-tree trap fired, and the guard caught it

Installing the wheel and importing from **inside** the repo resolved to the
source tree, not the wheel:

```
installed at: C:\dev\Coding Language\nodus.py          # from inside the repo
resolved:     ...\.venv-validation\Lib\site-packages\nodus\__init__.py   # from %TEMP%
```

That is the repo-root `nodus.py` shim, and it is how 5.0.3 shipped past 32 green
probes run against the wrong tree — recurring at 5.5.0 and 5.6.0. The header and
`--require-installed` exist because reading the path is not enough; this cycle
they were the difference between validating the artifact and validating the
checkout.

### One probe was stale, and it was the probes doing their job

`probe_graph_does_not_execute` failed on the first run:

```
[FAIL] 5.4.0: `nodus graph` plans without executing the file
       static plan failed:
```

Not a regression. The probe passed `--allow-paths` to `nodus graph`, which has
**never declared that flag** — it was swallowed as a positional and did nothing.
#791 makes an undeclared flag an error, so the probe started failing on a
command that works correctly:

```
$ nodus graph probe.nd --allow-paths .
Error: unknown flag '--allow-paths' for 'nodus graph'.
$ nodus graph probe.nd
{"workflow": "w", "nodes": ["a", "b"], "edges": [["a", "b"]], ...}
```

The flag never mattered to the probe: its assertion is that the file is **not**
executed, so the write it would have permitted never happens. Removed, matching
the same correction made to `test_graph_static_plan.py` when #791 landed — that
one was caught by CI, and this one was not, because CI does not run the probes.

### What the 5.12.0 probes assert

Ten new ones, written **before** the tag, testing the release's *claims* rather
than its code:

| | |
|---|---|
| the readiness report names **every** registered flip, including the one it cannot check | R4: a report that omits what it did not look at is the comfortable lie |
| a clean run never says "ready" | the wording carries #545's unanswerable-ness |
| the static concurrent-write check excludes pairs `after` already orders | it is not "every pair that touches the cell" |
| `StagedFlipWarning` stays a `DeprecationWarning` subclass | every embedder filter written for the general case keeps working |
| the register ships **inside the package** | `check --staged` reads it at run time; a missing `package-data` entry would break the headline feature for every user while working here |
| `nodus test` no longer advertises `--watch`/`--parallel`/`--seed`/`--coverage-per-test` | #794 |
| `workflow cleanup` refuses `--dry-run` | #791, the one that deleted |
| a non-project directory gets a message, not an errno | #807 |
| README names `check --staged` and `NODUS_STAGED_FLIP_REPORT` | the permanent PyPI page |
| no document still calls 5.11.0 current | the other side of the `--versions` run |

---

## Artifact checks

- `twine check`: **PASSED** on both the wheel and the sdist.
- The wheel carries `nodus/support/staged_flips.json`, `nodus/llms.txt`,
  `nodus/tooling/staged_readiness.py`, `nodus/cli/flags.py` and
  `nodus/support/staging.py`; the register reads back with all five flips.
- No language keyword was added, and `nodus_gate --consumers` reports 2/2 in
  step — that phase hashes `ALL_KEYWORDS`, so the editor grammar cannot be
  behind (Gate 3b/3c).

## Follow-ups, not blockers

1. **Widen `DEPENDENTS`** to include `nodus-workflow-ai`, and consider changing
   the criterion from *imports* to *declares a dependency*.
2. **The probes are not run by CI**, which is why the stale `--allow-paths` line
   survived a change that fixed the identical line in a test. Worth deciding
   whether that is acceptable — they need a built wheel and a clean venv, so
   running them on every PR is not free.
