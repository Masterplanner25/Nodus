# v5.19.0 — Gate 10 creator validation (pre-publish)

**Artifact:** `nodus_lang-5.19.0-py3-none-any.whl` and `nodus_lang-5.19.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.19.0` → `f7954f2`)

**Date:** 2026-11-26

5.19.0 is a minor. Its theme is **compile-to-Python graduating**:

- **#976: compile-to-Python is on by default** for `nodus run` and
  `NodusRuntime`, and moves from Experimental to Mostly Stable. It was opt-in
  for 5.17.0 and 5.18.0, as its design decided. The opt-outs are
  `nodus run --no-compile`, `NodusRuntime(compile_functions=False)` and
  `NODUS_COMPILE_FUNCTIONS=0`, which overrides the other two for the whole
  process.
- **#969: the three fused instructions are stable.** All 52 opcodes are
  stable, and `BYTECODE_VERSION` stays 5.
- **#1007: compile-to-Python works without the optimizer.** Under `--no-opt`,
  functions with parameters had stayed interpreted.
- **#1004: the `max_memory_mb` error quotes the limit the host set**, not the
  absolute ceiling.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run with nothing else going. **Exit 0 on the first round**, with no timeouts and
no recorded flakes matched.

This is the gate the default change most needed. Every companion that builds a
`NodusRuntime` now runs compiled code without asking for it, and none of the
eight suites changed result.

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 48.97s |
| nodus-mcp-server | PASS | 78 passed, 2 warnings in 9.63s |
| nodus-extension | PASS | 126 passed in 21.53s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 15.55s |
| nodus-native-memory-engine | PASS | 76 passed in 1.44s |
| nodus-jupyter | PASS | 32 passed in 1.43s |
| nodus-workflow-ai | PASS | 28 passed in 0.38s |
| nodus-a2a-wire | PASS | 188 passed in 15.24s |

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation`, upgraded in place from 5.18.0
with `--force-reinstall --no-deps`. The extras the probes need were already
installed there. The probes ran from `%TEMP%`, outside the repo, with
`--require-installed`, and with `NODUS_COMPILE_FUNCTIONS` unset so the default
was what ran:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.19.0
```

**168/168 probes passed. Exit code 0.** Eight are new this cycle, written before
the tag. CI's `probes` job also ran them against its own wheel on PR #1010.

- **#976, the default:** a `NodusRuntime` with no argument compiles the hot
  function, and `compile_functions=False` compiles none. Both give the same
  output and the same 716 instructions.
- **#976, the environment:** `NODUS_COMPILE_FUNCTIONS` set to `0`, `off` or a
  typo turns compilation off even with `compile_functions=True`, and `1`
  turns it on even with `False`.
- **#976, the CLI:** `nodus run --no-compile` runs and prints the right result,
  and `--compile --no-compile` together exits 2.
- **#1004:** the memory error reads "this run grew the process by 61.1 MB, past
  its 16 MB limit (159 MB resident)" for `max_memory_mb=16`.
- **#1007:** the same function compiles with and without the optimizer.
- **#969:** `BYTECODE_REFERENCE.md` counts 52 stable and 0 provisional, with no
  entry still marked provisional.
- **The README names the 5.19.0 surface,** including all three opt-outs.
- **No document still calls 5.18.0 current.**

## Found while preparing the release

**PyPy made a deadline test race the clock.**
`test_module_call_run_bounds.py::test_the_deadline_stops_a_loop_inside_a_stdlib_function`
ran a 300,000-element stdlib loop under `timeout_ms=100`, sized for "about 3 s
of work" interpreted. Once compiled by default, PyPy finished it inside the
deadline on one of the two CI runs of #1009. The bound was not missed: compiled
code stops at the deadline (0.11 s on CPython). The workload is now 5,000,000
elements, which no mode finishes in 100 ms. **Expect this class of test to
recur.** A test that sizes work to outlast a bound has to be sized for compiled
code now.

**The A/B for #969 found #1007.** With fusion disabled, compile-to-Python compiled
none of the frontend's functions. It could not translate `STORE_ARG`, so
`--no-opt` had been silently interpreting every function with parameters since
5.17.0. That was noticed at compile-to-Python's phase 3 and recorded only in a
private note, not filed. It was fixed before the default changed.

**`--compile` could not stay a silent no-op.** `test_cli_command_table` fails on
a flag that is declared but read by no code (#794). So `--compile` alone asks for
the default, and `--compile --no-compile` is refused instead of one quietly
winning.

**One behaviour change** has a row in the release sequence's "What is not
additive" table: compiled by default. It names the three opt-outs, and which one
to reach for if compiled code is suspected of a defect.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` before the bump: every phase PASS (runtime 303/303,
  opcodes 39/39, closed-issues 4/4, shapes 0 new)
- `nodus_gate --open-claims --strict` PASS after `tools.refresh_issue_states`
- `nodus_gate --closed-issues --section 5.19.0` → 4/4
- `nodus_gate --versions` after the bump → 13/13 against 5.19.0
- `twine check` PASSED on both artifacts
- CI on PR #1010 (merged as `f7954f2`): `compiled`, `probes`, `py310-floor`,
  `pypy`, `security`, `test` all green on both runs. The full suite now runs
  with compilation on by default.
