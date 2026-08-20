# Gate 10 — creator validation, v5.1.0

Date: 2026-08-20 · Tag: `v5.1.0` → `4d0cd6a` · Artifact: `nodus_lang-5.1.0-py3-none-any.whl`

Gate 10 asks **"what can I make fail?"** against the built wheel, before it reaches
PyPI. It has two parts and the first is not optional.

---

## 0. Dependent suites — run before the upload

```
companion                      verdict   detail
nodus-mcp                      PASS      363 passed in 56.72s
nodus-mcp-server               PASS      25 passed in 3.96s
nodus-extension                PASS      126 passed in 83.99s
nodus-sdk                      PASS      99 passed in 25.35s
nodus-native-memory-engine     PASS      76 passed in 1.20s
nodus-jupyter                  PASS      32 passed in 7.65s

All 6 dependent suites pass.          — 721 tests
```

### One run went red, and the reason is recorded rather than waved away

An earlier invocation reported `nodus-mcp FAIL — 1 failed, 362 passed`. It was run
**concurrently with the clean-venv wheel install and probe suite**, which is the
concurrency `CLAUDE.md` warns about in the strongest terms. Re-run alone: 363 passed.
Re-run standalone outside the gate: 363 passed. Three green runs bracket one red one
with a known confound, and `nodus-mcp`'s `test_phase_m.py` has two documented
port-conflict-sensitive tests.

**This exposed a real gap in the tool, filed separately:** the gate prints
`1 failed` and *"Do not publish"* without naming the failing test. That is not enough
to distinguish a known flake from a genuine break, which is precisely the judgement
the gate exists to inform. Triage required re-running by hand.

---

## 1. Adversarial probes against the wheel

Installed `nodus_lang-5.1.0-py3-none-any.whl` into a fresh venv created from a
system Python, with **no `PYTHONPATH`**, and confirmed resolution:

```
nodus package: ...\cleanvenv\Lib\site-packages\nodus\__init__.py
version:       5.1.0
```

The probe suite prints that header first on purpose. Gate 10 passed 5.0.3 with 32
green probes while nodus-sdk was broken at construction, and validating the wrong
tree is the failure mode this makes visible.

| probe | claim under attack | result |
|---|---|---|
| `when/met` | a guard whose checkpoint was recorded lets the step run | PASS |
| `when/unmet` | an unmet guard skips the step *and its dependents*; run stays `ok` | PASS |
| `when/typo` | a guard naming a label no step records is refused at compile time | PASS |
| `on/failed` | `on: ["failed"]` runs when the dependency threw | PASS |
| `on/skipped` | `on: ["skipped"]` runs when the dependency's guard was unmet | PASS |
| `on/refused` | an end-of-run conclusion is refused at declaration, not ignored | PASS |
| `on/omitted` | a step whose declared outcome never occurs is `omitted`, not failed | PASS |
| `state/compound` | #518: `counter += 1i` reaches workflow state | PASS |
| `state/durable` | `durable: false` keeps a cell live in memory | PASS |
| `state/merge-bad` | an unimplemented merge policy is refused with a reason | PASS |
| `run_source/#521` | `filename=` is a label, not a program selector | PASS |
| `deny-by-default` | a bare runtime still cannot shell out | PASS |
| `store/#516` | the SQLite workflow store closes its cursors | PASS |

**13/13.**

`run_source/#521` attacks three label forms — bare relative, `./`-prefixed and
absolute — and then asserts `run_file` *still reads the file*, because a fix that
broke that half would be worse than the bug.

`store/#516` disables the garbage collector around the claim, so a collection cannot
paper over a leaked cursor.

## 2. Standard eval scripts, through the wheel's own CLI

```
$ nodus --version
Nodus 5.1.0
quirk_probe              ALL QUIRKS CONFIRMED
language_exerciser       ALL EXERCISES PASSED
framework_capabilities   ALL FRAMEWORK PROBES PASSED
```

## 3. Distribution metadata

`twine check` PASSED on both artifacts. The long description was inspected inside the
wheel rather than assumed, because `readme = "README.md"` means whatever it says at
tag time is the PyPI page forever:

| check | result |
|---|---|
| `Version:` | 5.1.0 |
| carries the 5.1.0 "Recent:" paragraph | yes |
| lists all seven task statuses | yes |
| carries the #521 behaviour-change note | yes |
| still advertises 5.0.4 as current | **no** |

That last row is the one that has gone wrong before — 5.0.1's PyPI page still says
"v5.0.0 stable on PyPI".

## 4. Gates

| gate | result |
|---|---|
| static | PASS 135/135 symbols |
| runtime | PASS 242/242 blocks |
| closed-issues | PASS **6/6**, as `--section 5.1.0` |
| contracts | PASS 6/6 |
| opcodes | PASS 26/26, 49 opcodes, `BYTECODE_VERSION` 4 |
| consumers | STALE 1/2 at cut — see Stage 6 |
| ruff | clean |
| mypy | clean |

**The closed-issues phase must be run with `--section`.** Run as `--all` after the
cut it reported *"0 passed, 0 failed, 0 missing (of 0 referenced issues)"* — a green
pass that checked nothing, because `[Unreleased]` is empty by then. It did exactly
that on this release. The `--section 5.1.0` run found and verified all six.

## 5. What the pre-tag probe work caught

Gate 10b's probes were written **before** tagging rather than after, and that ordering
paid for itself. Three features in this release touch the same vocabulary — task
statuses, join policies, and step guards — and landed in that order. The guards made
`skipped` and `omitted` real, silently falsifying prose written for the two earlier
features. Four artifacts still described the superseded five-value world:

- the CHANGELOG entry, which said `skipped`/`omitted` "wait on a conditional-edge design (#471)"
- **`README.md`** — which would have been permanent on PyPI
- `docs/guide/workflows-and-tasks.md`, claiming the valid `on:` outcomes were `completed` and `failed`
- the comment above `JOIN_ON_STATES`, saying `skipped` was absent, one line above a tuple containing it

None is a code defect and no behaviour test would have caught any of them. Fixed in
#526, with `TASK_STATUSES` as the single source and `tests/test_status_vocabulary.py`
holding the guide to it.

## 6. Known issues shipping

- **#485** — the emission model behind `merge: "sum"`/`"append"`/`"union"`. `merge:`
  accepts `any` and `once` and **refuses** the folds with a reason, rather than
  accepting a name it does not honour. Prerequisite #518 landed here.
- **#522** — the VM retains an event per function call and return, unbounded: ~1.5×
  throughput and ~23 bytes per instruction of live memory. Pre-existing, not a
  regression.
- **#475** — whether an independent branch should run after a sibling fails. `cancelled`
  makes the affected steps visible; the policy question is still open.

## 7. Not covered

- No PyPy run of the full suite (#516 unblocked it; not repeated here).
- No multi-process or long-soak testing of the new state declarations.
- Windows only. CI covers Linux on every PR, but the wheel validation above was not
  repeated on another platform.
