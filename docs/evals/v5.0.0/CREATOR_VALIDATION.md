# Gate 10 — creator validation, v5.0.0

**Pre-publish.** Run against the **built wheel** in a clean venv, before any
upload. Protocol: [`EVAL_PREPUBLISH.md`](../../governance/EVAL_PREPUBLISH.md).

| | |
|---|---|
| Artifact | `dist/nodus_lang-5.0.0-py3-none-any.whl` |
| Built from | tag `v5.0.0` → `25356ed` |
| Venv | `.venv-validation`, wheel only, no dev tree on the path |
| `nodus --version` | `Nodus 5.0.0` |
| Date | 2026-08-17 |
| Verdict | **PASS — no findings** |

`twine check`: PASSED for both the wheel and the sdist.

---

## 1. Standard eval scripts

All three from `tests/eval/`, run through the installed console script.

| Script | Result |
|---|---|
| `quirk_probe.nd` | `ALL QUIRKS CONFIRMED` |
| `language_exerciser.nd` | `ALL EXERCISES PASSED` |
| `framework_capabilities.nd` | `ALL FRAMEWORK PROBES PASSED` |

## 2. Adversarial probes

This release's headline claims, each attacked from the clean venv. The point of
running these here rather than in the dev tree is that a claim can be true of
`src/` and false of what ships.

| # | Claim under attack | Result |
|---|---|---|
| A1 | A bare `NodusRuntime()` denies subprocess | `ok=False`, and the error names the flag: *"pass `allow_subprocess=True` to NodusRuntime to allow it"* |
| A2 | The documented grant works | `ok=True`, `stdout='ran'` |
| A3 | A guest cannot forge a workflow run record | `ok=False`; the file still reads `{"real": true}` |
| A4 | The floor beats a policy that allows everything | `ok=False` — a permissive policy cannot override it |
| A5 | Capabilities are per-category, not all-or-nothing | subprocess granted while network denied → `ok=True` |
| A6 | `ask` with no approval channel denies | `ok=False`, *"needs a human (no approval channel configured)"* |
| A7 | **`nodus run` is deliberately NOT sandboxed** | `rc=0`, `out='ran'` — the CLI exemption holds in the shipped artifact |
| A8 | `goal … over …` runs | `rc=0`, `iterations=3.0` |
| A9 | A mistyped checkpoint is a **compile** error | `rc=1`, *"goal 'reach' waits on checkpoint \"good_enuf\""* |
| A10 | `nodus fmt` output still parses | `rc=0`, round-tripped as `step a with { retries: 2, retry_delay_ms: 5 } {` |

A7 is worth stating explicitly because it is the one place this release is
*deliberately* inconsistent: embedded runtimes deny by default, the CLI does not.
Verifying it here means the split survived packaging rather than being an
artifact of how the dev tree is wired.

A9 and A10 are the two guards added this cycle, checked end to end from the
console script — the compile-time checkpoint check and the formatter round-trip.

## 3. Gates

| Gate | Result |
|---|---|
| `--static` | 135/135 symbols |
| `--runtime` | **239/239** blocks |
| `--closed-issues --section 5.0.0` | **7/7** referenced issues have a regression test |
| `--contracts` | 6/6 |
| `--opcodes` | 26/26, 49 opcodes, `BYTECODE_VERSION` **4** (unchanged) |
| `ruff` | clean |
| CI (clean runner) | pass, 5m47s |

The closed-issues gate was run with `--section 5.0.0`, **not** against
`[Unreleased]`. After the cut, `[Unreleased]` is empty and the default invocation
reports a pass having checked nothing — the trap `CLAUDE.md` names.

## 4. Known issues shipping with this release

Recorded here because a clean run is evidence and silence is not.

- **The local suite is unreliable on the build machine.** Subprocess-based tests
  with 10 s timeouts fail intermittently, naming a different test each run, and
  suite wall-clock moved from ~7 min to ~13 min over the session with nothing
  else running. Every such failure passed in isolation, and one
  (`test_len_returns_int.py`) was verified to fail identically **with and
  without** the change under test. CI on a clean runner passed every PR in
  5–6 min. This is a build-environment problem, not a release defect, but it
  means "the local suite is green" was not available as a signal for this cut.
- **`test_scheduler_fairness::test_long_running_task_rotates_with_budget`** —
  the pre-existing flake `CLAUDE.md` documents.
- **`nodus-vscode` is not republished.** The grammar was updated for the five new
  `goal` keywords (`0aa588c`) but the VSIX upload is manual (Gate 3b), so
  `over`/`until`/`budget`/`reached`/`retry` will not highlight until it ships.
  **This is the one outstanding item for Stage 6.**

## 5. Not covered

- No adversarial probing of the deferred capability work — layered rule sources,
  approval caching, attenuation, and routing `ask` to `workflow_wait` are not
  implemented, so there is nothing to attack.
- Performance was not benchmarked for this cut. The one hot-path change
  (a dict lookup per builtin call) was measured during development as no
  regression in VM construction or warm import; the builtin-loop benchmark was
  discarded as too noisy on this machine to resolve an effect that small.
