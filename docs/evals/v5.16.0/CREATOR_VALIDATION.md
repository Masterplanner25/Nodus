# v5.16.0 — Gate 10 creator validation (pre-publish)

**Artifact:** `nodus_lang-5.16.0-py3-none-any.whl` and `nodus_lang-5.16.0.tar.gz`,
built from a clean worktree of the tagged tree (`v5.16.0` → `2341db7`)

**Date:** 2026-11-11

5.16.0 is a minor. Its theme is **durable coroutines** (#180), shipped
Experimental: `durable_spawn(key, fn, args)` runs a function as a coroutine backed
by a run record, each `checkpoint` it reaches is written down before it goes on,
and re-running the program with the same key resumes after the last one. Around it:

- **#917**: a rebuild that re-runs a top-level effect warns (`StagedFlipWarning`),
  and 6.0.0 will refuse it. `nodus check --staged` finds them from source (#922).
- **#911 / #912**: a checkpoint inside a `for` over a list; cancelling a durable
  run from outside (`nodus workflow cancel --key`).
- **#909 / #908**: a rebuild no longer re-runs `main()` or restarts spawned work;
  `NodusRuntime.sweep()` runs on VMs configured like the runtime's own.
- **#907 / #920 / #921**: `nodus run` streams output; a failed resume or replay
  exits 1; a call's error points at the call.
- **#927**: the VM dispatch loop is ~1.6× faster on CPython on compiler-like code.

## Gate 10a — dependent suites (before upload)

```
PYTHONPATH="src;." python -m tools.check_dependent_suites
```

Run with nothing else going, at 0.8 GB free. No timeouts. **Exit code 0.**

| companion | verdict | detail |
|---|---|---|
| nodus-mcp | PASS | 376 passed, 2 warnings in 49.75s |
| nodus-mcp-server | PASS | 45 passed, 2 warnings in 2.44s |
| nodus-extension | PASS | 126 passed in 20.77s |
| nodus-sdk | PASS | 132 passed, 2 skipped, 1 warning in 17.71s |
| nodus-native-memory-engine | PASS | 76 passed in 1.34s |
| nodus-jupyter | PASS | 32 passed in 1.38s |
| nodus-workflow-ai | PASS | 28 passed in 0.36s |
| nodus-a2a-wire | PASS | 188 passed in 13.52s |

## Gate 10b — adversarial probes against the wheel

The wheel was installed into `.venv-validation` (upgraded in place) with the
`[http]` extra. The probes ran from the session scratchpad, outside the repo,
with `--require-installed`:

```
package   C:\dev\Coding Language\.venv-validation\Lib\site-packages\nodus
version   5.16.0
```

**143/143 probes passed. Exit code 0.** Six are new this cycle, written before
the tag:

- **A durable coroutine resumes at its last checkpoint after a real crash.** A
  child process running the installed package is killed with `os._exit` between
  two checkpoints. The next process resumes at `fetched`: the work before it does
  not run again, and the state is the checkpoint's (`total=10`, so the run
  finishes at 15). A third run of the finished key does nothing.
- **`durable_spawn` refuses a store whose claims are not exclusive across
  processes,** and the message names `NODUS_WORKFLOW_STORE_BACKEND=sqlite`.
- **A `checkpoint` that can record nothing names `durable_spawn`.** Inside a
  function it is a run-time error; at module level it is a syntax error; and a
  user function named `checkpoint` still runs, so the word is not reserved.
- **A failed `nodus workflow resume` exits 1 (#920),** and still prints the
  runner's answer.
- **The README names the 5.16.0 surface.**
- **No document still calls 5.15.1 current.**

The single `Sandbox error … Execution timed out` line on stderr is the #862
probe's expected result, reported as PASS.

## Found while preparing the release

**The release notes disagreed with the code and with each other.** The
durable-coroutine entries were written stage by stage, and four still said #180
"stays open" when it had closed. The stage-1 entry said `checkpoint` outside a
step is a compile-time error. Run against the tree, that was true only at module
level: inside a function it compiles (`nodus check` says OK) and fails at run
time. The later entry was right and the earlier one had not been revisited. Both
were reconciled in the release PR, since `[5.16.0]` is also the GitHub release
body.

**`skills/nodus.skill` taught that `checkpoint` is valid only in a step body.**
The example added for the durable case was run before it was written.

## Other pre-tag checks

- `ruff check src/ tests/` clean · `mypy src/nodus/ --no-site-packages` 0 errors
- `nodus_gate --all` before the bump: every phase PASS (runtime 303/303,
  closed-issues 9/9, shapes 0 new, flips 6 staged)
- `nodus_gate --closed-issues --section 5.16.0` → 9/9
- `nodus_gate --versions` after the bump → 13/13 against 5.16.0
- `twine check` PASSED on both artifacts
- CI on PR #933 (merged as `2341db7`): `security`, `probes`, `py310-floor`,
  `test` all green on both the push and pull_request runs
