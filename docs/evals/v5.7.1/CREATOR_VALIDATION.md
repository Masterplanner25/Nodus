# v5.7.1 — Gate 10 creator validation

**Date:** 2026-08-29
**Wheel:** `nodus_lang-5.7.1-py3-none-any.whl`, built from the tagged tree
**Tag:** `v5.7.1` → `949bea2dbb1cabf474f9a1c4d9b94c61530ae98e` (equal to `HEAD` at build time)
**Verdict:** pass — cleared for upload

5.7.1 is a patch that supersedes 5.7.0. Gate 10 ran in full rather than being
skipped as "just a fix": the change is a scope binding in the analyzer, which
`nodus check` and the LSP both consume, so the surfaces it could break are the
ones the probes read.

See `docs/evals/v5.7.0/CREATOR_VALIDATION.md` for the cycle that produced the
feature set; this document covers the patch that made it usable.

---

## Gate 10a — dependent suites, before the upload

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed in 42.33s
nodus-mcp-server               PASS       25 passed in  1.15s
nodus-extension                PASS      126 passed in 32.13s
nodus-sdk                      PASS       99 passed in  6.40s
nodus-native-memory-engine     PASS       76 passed in  0.55s
nodus-jupyter                  PASS       32 passed in  2.66s

All 6 dependent suites pass.        exit 0
```

**721 companion tests, exit 0.** Exit 0 is the only clearing verdict.

---

## Gate 10b — adversarial validation against the wheel

Clean venv, wheel installed, run from a neutral CWD with `--require-installed`:

```
  package   ...\.venv-validation\Lib\site-packages\nodus
  version   5.7.1
  import    ...\.venv-validation\Lib\site-packages\nodus\__init__.py

72/72 probes passed
```

The 72nd is new and is the point of this release:

> **5.7.1: a step body may read its dependencies, including under `extern`**
> after/each/compensates bind; typos still caught; strict mode accepts a dep read

It deliberately exercises the **pair** — a file that declares an `extern` *and*
reads a dependency by name. That is what 5.7.0's 71 green probes missed: the
compensation probes declared no `extern`, the extern probes read no dependency,
and neither feature is broken alone.

The probe also pins the two properties the fix could lose by binding too much: a
genuine typo is still reported, and `each p in d` binds `p` and not `d`.

---

## Pre-tag gates

| Gate | Result |
|---|---|
| 1 — suite | pytest **2929 passed**, 8 skipped; `unittest` **2678 OK** |
| 2 — ruff / mypy | clean |
| 3 — `nodus_gate --all` | Static 136/136 · Runtime 263/263 · Contracts 6/6 · Opcodes 26/26 · Shapes 0 new |
| 3d — versions | **15/15 agree with 5.7.1**, re-run *after* the bump |
| 4 — closed issues | `--section 5.7.1` → **1/1** (#662) |
| 5 — version sync | `version.py` and `pyproject.toml` both 5.7.1 |

**Step 4c fired again**, one cycle after being written down: the suite went red on
`test_llms_txt_shipped` because the 5.7.1 version-claim edit came after the last
`sync_llms_txt` run. That step exists because the same thing happened during
5.7.0, and it caught the repeat.

---

## What Gate 10 did *not* catch, in this cycle and the last

Worth recording here rather than only in the Stage 5 document, because it is a
statement about this gate's reach.

5.7.0 passed Gate 10 at **71/71** and shipped a defect that made `nodus check`
reject correct programs. Every probe exercised **one feature at a time**; the
defect existed only in the interaction. Gate 10 asks *"what can I make fail?"*
against a local wheel, and the answer was honestly "nothing" — the question just
was not the one that mattered.

**Stage 5 found it**, by running the published package as a new user on a program
using both features. That is the strongest evidence this project has produced for
keeping the two as separate steps rather than folding Stage 5 into Gate 10.

The 5.7.1 probe closes this particular pair. The general lesson — that a probe
per feature does not cover the product of features — is not closed by anything,
and is the thing to remember when adding two surfaces in one release.

---

## Known and accepted

- **#664** — `nodus run` has no extern pre-flight and its call-site error does not
  mention the declaration. Found by Stage 5; defensible behaviour, poor message.
- **`nodus-run-action` stale at gate time**; republished in Stage 6.
- **Throughput unmeasured.** The change is a scope binding in the analyzer, not on
  any execution path — but that is not a measurement.
