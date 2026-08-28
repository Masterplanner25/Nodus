# v5.6.0 — Creator validation (Gate 10)

Pre-publish. Run against the wheel built from the tagged tree, before upload.

```
package   .../.venv-validation/Lib/site-packages/nodus
version   5.6.0
tag       v5.6.0 -> 32a49ba284150d6d13034da1312f8b3be6557a39 (== HEAD at build)
wheel     dist/nodus_lang-5.6.0-py3-none-any.whl   (488 KB, 176 files)
sdist     dist/nodus_lang-5.6.0.tar.gz             (817 KB)
```

**Verdict: pass.** Gate 10(a) 6/6 dependent suites, Gate 10(b) 59/59 probes,
`twine check` clean on both artifacts.

---

## Gate 10(a) — dependent suites, before the upload

The step that exists because 5.0.3 shipped past 32 green probes and broke
`nodus-sdk` at construction: this gate validates nodus-lang *against its
dependents*, which validating it against itself structurally cannot do.

```
companion                      verdict   detail
------------------------------------------------------------------------------
nodus-mcp                      PASS      363 passed in 45.12s
nodus-mcp-server               PASS      25 passed in 1.23s
nodus-extension                PASS      126 passed in 34.37s
nodus-sdk                      PASS      99 passed in 11.66s
nodus-native-memory-engine     PASS      76 passed in 0.32s
nodus-jupyter                  PASS      32 passed in 1.80s

All 6 dependent suites pass.                                        exit 0
```

Exit **0**, not 2 (a skipped or timed-out suite) and not 3 (every failure
matched a recorded flake). Run with nothing else going, per the 5.1.0 lesson
where a concurrent probe run turned `nodus-mcp` red.

## Gate 10(b) — 59/59 probes against the installed wheel

Twelve are new this cycle. Nine exercise the release's behavioural claims and
three read its prose:

```
[PASS] 5.6.0: a step maps over a list, and stays one step
[PASS] 5.6.0: an empty producer skips, an unmappable one fails
[PASS] 5.6.0: workflows and goals take parameters
[PASS] 5.6.0: a step can declare its output type
[PASS] 5.6.0: a goal can be bounded by what it spends
[PASS] 5.6.0: an unrecognised type name is reported, not silently `any`
[PASS] 5.6.0: the agent registry is a published surface
[PASS] 5.6.0: `each` is a named keyword, so editors can highlight it
[PASS] 5.6.0: RuntimeService.close() waits for its sweeper
[PASS] 5.6.0 prose: nothing still calls 5.5.0 the current release
[PASS] 5.6.0 prose: the guide documents mapping a step over a list
[PASS] 5.6.0 prose: the companion count matches the verified live count
```

---

## What the probes caught, written *before* the tag

Two went red on their first run against the source tree, which is why they are
written before tagging rather than after.

**`README.md:213` still claimed 32 standalone companion packages** against a
verified live count of 35. `pyproject.toml` sets `readme = "README.md"`, so that
sentence would have become the PyPI project page **permanently** — release
immutability means no re-upload. The seven-place sweep that fixed this same
string earlier in the cycle had missed both that paragraph and the summary in
`docs/governance/ECOSYSTEM_READINESS_ASSESSMENT.md`.

This is the 5.1.0 finding repeating exactly: a hand-maintained number, fixed in
the places someone thought to grep, wrong in the ones they did not.

The other red was the probe's own fault — `agent_available()` takes no
arguments — and is worth recording only because a probe that is wrong about the
API is indistinguishable from a release that is, until you read it.

## The wrong-tree trap fired for the third time, and is now a check

Gate 10 requires probes to print the resolved package path first, because
validating the wrong tree is the failure this gate has already had once. The
header earned its place again:

```
  package   C:\dev\Coding Language\src\nodus        <- the SOURCE, not the wheel
  version   5.6.0
```

The cause: the repo-root `nodus.py` shim inserts `src/` on `sys.path` and
re-execs the package from there, so **any** process whose CWD is the repo
resolves `nodus` to the source tree regardless of what is installed. It needs no
`PYTHONPATH` and leaves no trace in `pip list` — the venv genuinely had the wheel.

The history matters more than the mechanism:

| Release | What happened |
|---|---|
| 5.0.3 | Shipped past **32 green probes** run against the wrong tree. Cost a 5.0.4. |
| 5.5.0 | Hit it, caught it by reading the header, and wrote the cause up in full in its own `CREATOR_VALIDATION.md`. |
| 5.6.0 | **Hit it again anyway.** |

A trap documented in the previous release's eval is documented where nobody
reads it at the moment it matters. So it is a check now:
`release_claims_probe.py --require-installed` exits **2** when `nodus` resolves
under `<repo>/src`, and prints the reason unconditionally either way.

Deliberately scoped to `<repo>/src`, not "anywhere under the repo" — the first
version refused this very validation, because `.venv-validation` lives inside
the checkout and resolved correctly. An over-broad guard that refuses valid
setups is worse than none, and it was caught by running it in both directions:
green from the venv, exit 2 against the source tree.

---

## Supporting gates, on the tagged tree

| Gate | Result |
|---|---|
| Full suite | 2839 passed, 3 skipped, 223 subtests |
| ruff / mypy | clean |
| `--static` | 135/135 symbols across 40 documents |
| `--runtime` | 260/260 doc blocks |
| `--closed-issues --section 5.6.0` | 13/13 referenced issues |
| `--contracts` | 6/6 |
| `--opcodes` | 26/26, BYTECODE_VERSION **4** unchanged |
| `--shapes` | 39 known (19 tracked debt), **0 new** |
| `--versions` | 15/15 claims agree with 5.6.0 |
| `twine check` | PASSED on wheel and sdist |

`--closed-issues` under `--all` reports **0 of 0** after the CHANGELOG cut. That
is the vacuous pass the checklist warns about, not a result; the figure above is
the `--section 5.6.0` run.

## Known-stale at publish time

Both consumers are correctly flagged and are Stage 6 work, after the tag:

- **`nodus-vscode` 0.1.3** — keyword fingerprint moved
  (`602761bf77ebb21e → 526b2f659e90124e`) because `each` is new. The grammar fix
  is committed in the checkout (`03aa535`); it needs a version bump and a
  republish. Until then the extension renders `each` as a plain identifier —
  the exact two-release regression `tests/test_keyword_coverage.py` exists to
  prevent, which is how it was found.
- **`nodus-run-action` v1.0.6** — `nodus_version` 5.5.0 → 5.6.0.

Neither is on PyPI, so the Stage 6 content-hash sweep structurally cannot see
them; `nodus_gate --consumers` is what tracks both.
