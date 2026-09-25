# v5.15.0 — Gate 10 creator validation (pre-publish)

**Date:** 2026-09-25
**Artifact:** `dist/nodus_lang-5.15.0-py3-none-any.whl`, built from the tagged
tree (`v5.15.0` → `d3e9c07`)
**Verdict:** **PASS.** Both halves green, the first only after a real failure was
fixed. Cleared to publish.

Gate 10 asks *"what can I make fail?"* against a local wheel, before anything
immutable exists. Two halves, and the first is not optional: 5.0.3 shipped with
32 green probes and broke `nodus-sdk` at construction, because probes validate
nodus-lang against itself and nothing in them constructs a dependent.

This cycle is the clearest demonstration yet of why 10a runs before the upload,
and of why its verdict is not a formality — it went red twice for two different
reasons, and neither was a nodus-lang regression.

---

## 10a — dependent suites, before the upload

```
PYTHONPATH="…/src;…" python -m tools.check_dependent_suites
```

Run with nothing else going. No suite, gate or server was running locally; the
release PR's CI had already finished on a remote runner.

### First run: exit 2 before it started — a checkout that did not resolve

`nodus-a2a-wire` is registered at `C:\codev\a2a-wire-pub` and that directory no
longer exists; the repo had been moved to `C:\dev\a2a-wire-pub`. A missing
checkout is **exit 2**, which is not a pass — *an unrun suite covers nothing*.

Verified it was the right repo before repointing the registry rather than
assuming a like-named directory: correct remote
(`Masterplanner25/nodus-a2a-wire`), and `10746ce` at the base of its 17-commit
history, exactly as `CLAUDE.md` records. Registry path corrected, note extended
with when and why the move was noticed.

**That entry is a canary, not a component.** Its nodus-lang link is a *dev
extra* — published metadata is `nodus-lang>=4.0.0; extra == "dev"` and its
runtime `dependencies` list is empty. It is registered anyway because Gate 10a
runs *suites*, and one of its tests imports nodus-lang under `PYTHONPATH=src`.
Do not remove it for having empty runtime deps.

### Second run: one NEW failure — and it was not ours

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | **FAIL** | 2 failed, 363 passed in 41.16s |
| nodus-mcp-server | PASS | 27 passed, 2 warnings in 2.15s |
| nodus-extension | PASS | 126 passed in 24.19s |
| nodus-sdk | PASS | 111 passed, 1 warning in 7.45s |
| nodus-native-memory-engine | PASS | 76 passed in 1.09s |
| nodus-jupyter | PASS | 32 passed in 1.80s |
| nodus-workflow-ai | PASS | 28 passed in 0.51s |
| nodus-a2a-wire | PASS | 188 passed in 13.65s |

The gate classified them correctly, which is what #528 added it for:

```
NEW    tests/test_invariants.py::test_version_is_not_dev
known  tests/test_phase_m.py::test_m2_bearer_wrong_returns_401  (recorded flake)
```

**The NEW one was a real, shipped defect in nodus-mcp with nothing to do with
this release.** `test_version_is_not_dev` asserts the package's two version
sources agree, and they did not:

```
AssertionError: version mismatch: __init__.py has '0.1.3', pyproject.toml has '0.1.4'
```

`git log -S` pinned it to `3966a56` — the mcp SDK 2.x port, cut as 0.1.4 earlier
in this same session — which bumped `pyproject.toml` and left
`src/nodus_mcp/__init__.py` on the 0.1.3 release value. PyPI has 0.1.4, so **the
published 0.1.4 reports the wrong number**: `nodus-mcp --version` and both serve
banners print 0.1.3. PyPI is immutable, so 0.1.4 keeps it; the repo is correct
now (`51cb91d`) and a future release will be consistent.

Established as independent of nodus-lang rather than assumed — the test reads
only that package's own two files. The gate refused to publish anyway, and that
is the right rule: it cannot know that from the outside, and 5.0.3 shipped a
broken `nodus-sdk` by not asking.

The second failure is the recorded port-conflict flake. Per the standard, a
recorded flake changes the advice and never the verdict, so it was re-run
serially: **1 passed in 3.06s**.

### Third run: clean

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | **365** passed, 2 warnings in 37.97s |
| nodus-mcp-server | PASS | 27 passed, 2 warnings in 1.99s |
| nodus-extension | PASS | 126 passed in 22.67s |
| nodus-sdk | PASS | 111 passed, 1 warning in 5.51s |
| nodus-native-memory-engine | PASS | 76 passed in 0.26s |
| nodus-jupyter | PASS | 32 passed in 1.23s |
| nodus-workflow-ai | PASS | 28 passed in 0.45s |
| nodus-a2a-wire | PASS | 188 passed in 13.63s |

**All 8 dependent suites pass — exit code 0.** 953 tests. nodus-mcp is 365
rather than 363 because the two previously-failing tests now pass; the flake did
not recur on the clean run either.

`nodus-sdk` is 111 rather than last cycle's 99: its 0.1.3 (2026-09-20) added the
twelve guest-driven bridge tests that exist because none of its 99 tests had ever
run a `.nd` program through a bridge.

---

## 10b — adversarial validation against the wheel

```powershell
cd $env:TEMP\...\g10b     # outside the repo
venv-val\Scripts\python.exe tests\eval\release_claims_probe.py `
  --repo "C:\dev\Coding Language" --require-installed
```

Clean venv, the built wheel installed **with the `[http]` extra** — without it
the #855 trust-store probe refuses rather than passing vacuously, which is why
CI's `probes` job installs it too.

The header is the first thing printed, and it is the check that matters:

```
package   …\scratchpad\venv-val\Lib\site-packages\nodus
version   5.15.0
import    …\scratchpad\venv-val\Lib\site-packages\nodus\__init__.py
repo      C:\dev\Coding Language
```

**`site-packages`, not `src`.** The repo-root `nodus.py` shim inserts `src/` on
`sys.path` and re-execs from there, so any process whose CWD is the checkout
validates the *source tree* no matter what is installed — no `PYTHONPATH`,
nothing in `pip list`. That is how 5.0.3 shipped past 32 green probes, and it
recurred at 5.5.0 and 5.6.0. `--require-installed` exits **2** rather than
relying on anyone reading the header.

**136/136 probes passed.**

### Probes written before the tag

Six new ones this cycle, 130 → 136. They are the only check that reads the
release's *claims* rather than its code, which is why they are written before
step 6 and not after: run after the tag, a correction to the README would be
impossible, and `readme = "README.md"` makes it the permanent PyPI page.

| probe | what it reads |
|---|---|
| a resumed step reaches the host's tool handler | #868, the reported symptom end to end |
| a parked run older than the scan bound is still findable | #869, across `list_runs`, the sweep and `list_all_runs` |
| a resume inherits the caller's bounds | #873, all four bounds plus the step remainder |
| the terminal record cap can see the records it deletes | #875, a cap of 2 leaves 2 files |
| README names the 5.15.0 surface | the prose this release ships |
| no stale '5.14.0 is current' claim survives | the seven documents that carry a currency claim |

**The count moving is the wiring check.** `main()` invokes probes from an
explicit list, so a decorated function nobody calls is dead code that reads as
live — 129/129 stayed 129/129 when a probe was added earlier this session, and
only the unchanged count showed it. 130 → 136 here.

Three of the behavioural ones were falsified against neutered fixes, and each
failed with the symptom it exists to catch:

```
FAIL | a resumed step reaches the host's tool handler | returned 'error'
FAIL | a parked run older than the scan bound is findable | aged out of list_runs
FAIL | a resume inherits the caller's bounds | the deadline was not inherited
```

---

## What this gate did not cover

**The full local suite is not this cycle's evidence.** The box was at 0.2–0.4 GB
free of 7.7 GB throughout — the thrashing condition `CLAUDE.md` documents, where
process creation stalls on hard page faults and every timeout-shaped failure is
untrustworthy. A local run was started and stopped rather than reported.

CI on a clean runner is the arbiter, and it ran both `unittest discover` and
`pytest` on the release PR (#881): **all six checks green**, `test` at 12m59s and
13m56s on the two runs.

Stage 5 (against the published package) and Stage 6 (companions) are still owed
and are recorded separately.
