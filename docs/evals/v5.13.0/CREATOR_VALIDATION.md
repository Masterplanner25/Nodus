# v5.13.0 — Gate 10 creator validation (pre-publish)

**Date:** 2026-09-08
**Artifact:** `dist/nodus_lang-5.13.0-py3-none-any.whl`, built from the tagged
tree (`v5.13.0` → `7006846`)
**Verdict:** **PASS.** Both halves green. Cleared to publish.

Gate 10 asks *"what can I make fail?"* against a local wheel, before anything
immutable exists. It has two halves and the first is not optional: 5.0.3 shipped
with 32 green probes and broke `nodus-sdk` at construction, because probes
validate nodus-lang against itself and nothing in them constructs a dependent.

---

## 10a — dependent suites, before the upload

```
PYTHONPATH="…/src;…" python -m tools.check_dependent_suites
```

Run with nothing else going, for the reason recorded at 5.1.0: a clean-venv
install running alongside turned `nodus-mcp` red, and three serial re-runs were
green.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 363 passed in 57.17s |
| nodus-a2a-wire | PASS | 188 passed in 13.71s |
| nodus-extension | PASS | 126 passed in 28.81s |
| nodus-sdk | PASS | 99 passed in 5.99s |
| nodus-native-memory-engine | PASS | 76 passed in 2.13s |
| nodus-jupyter | PASS | 32 passed in 2.18s |
| nodus-workflow-ai | PASS | 28 passed in 0.59s |
| nodus-mcp-server | PASS | 25 passed in 1.79s |

**All 8 dependent suites pass — exit code 0.** 937 tests.

Exit 0 is the only pass. **2** would mean a checkout was missing or a suite timed
out, which is an unrun suite rather than a passing one, and **3** would mean every
failure matched a recorded flake — also not a pass, since letting one through
rebuilds "re-run until green" one level up. Neither occurred.

`nodus-sdk` is the one that matters most here for historical reasons: it is the
companion 5.0.3 broke, by assigning a public attribute the subclass defines as a
read-only property. This release adds a builtin and changes `RuntimeService`'s
constructor default; both are the kind of change that reaches a dependent.

---

## 10b — adversarial probes against the wheel

```
cd $TEMP                                   # outside the repo
.venv-validation/Scripts/python.exe tests/eval/release_claims_probe.py \
    --repo "C:/dev/Coding Language" --require-installed
```

**121/121 probes passed** against `nodus_lang-5.13.0-py3-none-any.whl` installed
into a clean venv. Exit code 0.

### The wrong-tree trap fired, and the guard caught it

The first resolution check was run from the repo root and reported:

```
installed version: 5.13.0
resolved from    : C:\dev\Coding Language\nodus.py
```

That is the source tree, not the wheel. The repo-root `nodus.py` shim puts
`src/` on `sys.path` and re-execs from there, so **any** process whose CWD is the
checkout resolves `nodus` to the working tree no matter what is installed — no
`PYTHONPATH`, nothing in `pip list`. It is how 5.0.3 shipped past 32 green
probes, and it recurred at 5.5.0 and 5.6.0.

Re-run from a temp directory:

```
resolved from    : …/.venv-validation/Lib/site-packages/nodus/__init__.py
```

`--require-installed` exists so this cannot be missed by someone not reading the
header, and it is now the fourth cycle in which the trap has been live rather
than theoretical.

### What the 5.13.0 probes assert

Six were written **before the tag**, which is the rule this project keeps for a
reason: they read the release's *claims*, and at 5.1.0 writing them early caught
four artifacts describing a vocabulary the release did not have — one of them
`README.md`, which `readme = "README.md"` makes the permanent PyPI page.

| probe | what would have to break |
|---|---|
| `copy()` is deep, preserves shared structure, refuses a live handle | all three #814 decisions, each of which could have gone the other way |
| a workflow state cell owns its value | #822 — mutating a container read out of a cell changes the cell again |
| `fs.ensure_dir` refuses a path that is a file | #845 — it reports success for a directory it did not make |
| `nodus serve` confines the filesystem by default | #843, **both halves**: the sentinel default, and the roots being installed through the normalising setter rather than assigned raw |
| README names the 5.13.0 surface | the permanent PyPI page stops describing what shipped |
| no stale "5.12.0 is current" claim survives | prose still calling the previous release current |

The `nodus serve` probe asserts on the **source** rather than on behaviour,
deliberately. #843 had two defects — an unconfined default and a raw assignment
that skipped path normalisation — and the second made the jail refuse
*everything*, so a behavioural probe checking only "outside is denied" would pass
against it.

### A probe that nearly went in silent

The six were spliced into the file correctly and the suite reported **115/115 —
unchanged**. The `@probe` decorator only *wraps* a function; `main()` calls each
probe by name, so a probe that is defined and never called is invisible. Nothing
failed; the count simply did not move, and only noticing that gave it away.

Fixed by wiring all six into `main()`, then confirmed falsifiable: renaming
`copy(value)` in the README turned the README probe red (120/121).

---

## Artifact checks

| check | result |
|---|---|
| `twine check dist/*` | PASSED |
| wheel built from the tagged tree | `v5.13.0` → `7006846` |
| version files agree | `version.py` and `pyproject.toml` both 5.13.0 |
| `llms.txt` packaged copy in step | `tools.sync_llms_txt` re-run after the version-claim edits |
| `nodus_gate --versions` | 13/13 after the bump (10 were stale before it) |
| `--closed-issues --section 5.13.0` | 9/9 |

---

## Follow-ups, not blockers

- **`nodus_gate --consumers` reports two stale**, both because `nodus_version`
  moved: `nodus-run-action` (its README documents a pinned `version:` that new
  users copy) and the GitHub wiki. Stage 6 work, tracked there.
- **Four `test_cli_completion.py::BashExecutionTests` fail on this host** with
  `TimeoutExpired`. Their code is unchanged since v5.12.0 — `git diff
  v5.12.0..HEAD` over the completion surface is empty — and this box's `bash`
  hangs on `bash --version` alone. CI installs the completion shells explicitly
  and passed the release PR. Environmental, not a regression.
- **`test_server.py::…dead_letter_list_and_replay`** failed under full-suite load
  and passes in isolation: the documented load-flake class for this box.
